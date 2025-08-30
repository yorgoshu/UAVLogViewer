from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
import uuid
import json

try:
    # ADK imports (1.11.x)
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.events import Event
    from google.genai import types  # Use google.genai.types for Content and Part
    from google.adk.sessions import InMemorySessionService

    ADK_AVAILABLE = True
except Exception as e:
    print(f"Failing to set ADK to true with error: {e}")
    ADK_AVAILABLE = False

from .tools.metrics import compute_metrics, detect_anomalies

app = FastAPI(title="UAV Agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

SESSIONS: Dict[str, Dict[str, Any]] = {}


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    user_message: str
    telemetry: Optional[Dict[str, Any]] = None
    include_digest: bool = True
    digest: Optional[Dict[str, Any]] = None  # <-- add this


class ChatResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]


SYSTEM_PROMPT = (
    "You are an expert UAV log analyst.\n"
    "Rules:\n"
    "1) Never write acknowledgements like 'Understood' or 'ready to analyze'.\n"
    "2) Always answer the user's last request directly.\n"
    "3) If telemetry is missing, ask up to two specific follow-up questions needed to proceed.\n"
    "4) Include units and timestamps in every numeric statement.\n"
    "You may receive a JSON part (MIME application/json) containing {'plot': {expressions, series}}.\n"
    "If not present as a JSON part, it may appear as text under [PLOT_JSON]. Use these samples ({t, v}) for calculations.\n"
)


@app.get("/health")
def health():
    return {"ok": True}


def _sid(given: Optional[str]) -> str:
    sid = given or str(uuid.uuid4())
    if sid not in SESSIONS:
        SESSIONS[sid] = {"history": []}
    return sid


def telemetry_from_plot(plot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert plot.series (list of {name, sample:[{t,v}]}) into a simple telemetry dict
    your metrics/anomaly tools can consume. We also provide convenient keys:
    - 'time' (seconds-ish), 'altitude', 'airspeed' when we can infer them.
    """
    if not plot:
        return None

    series = plot.get("series") or []
    if not isinstance(series, list) or not series:
        return None

    # Collect per-series arrays
    by_name: Dict[str, Dict[str, List[float]]] = {}
    for s in series:
        name = s.get("name")
        sample = s.get("sample") or []
        if not name or not isinstance(sample, list) or not sample:
            continue
        t = [p.get("t") for p in sample if isinstance(p.get("t"), (int, float))]
        v = [p.get("v") for p in sample if isinstance(p.get("v"), (int, float))]
        if not t or not v:
            continue
        # Normalize time to seconds if clearly microseconds or milliseconds
        # (your UI can also send seconds directly; this is just a safety)
        # Heuristic: if median t is huge, assume microseconds or ms.
        mt = t[len(t)//2]
        if mt > 3.6e9:          # likely microseconds
            t = [x / 1e6 for x in t]
        elif mt > 3.6e6:        # likely milliseconds
            t = [x / 1e3 for x in t]
        by_name[name] = {"t": t, "v": v}

    if not by_name:
        return None

    # Convenience keys for downstream metrics
    def pick(*candidates: str):
        for c in candidates:
            if c in by_name:
                return by_name[c]
        return None

    alt = pick("GPS.Alt", "BARO.Alt", "GPS.RawAlt")
    air = pick("ARSP.Airspeed", "NKF1.Spd")

    telemetry: Dict[str, Any] = {"series": by_name}
    if alt:
        telemetry["altitude"] = alt["v"]
        telemetry["time"] = alt["t"]
    elif air:
        telemetry["airspeed"] = air["v"]
        telemetry["time"] = air["t"]
    else:
        # Fall back to any series' time just to have a reference clock
        any_series = next(iter(by_name.values()))
        telemetry["time"] = any_series["t"]

    return telemetry

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    sid = _sid(req.session_id)

    # Pull plot from digest (sent by the UI)
    plot = ((req.digest or {}) if req.digest else {}).get("plot", {})

    # --- Optional digest/anomaly computation ---
    # Prefer req.telemetry if the UI sent it; else adapt from plot.series
    telemetry_payload = req.telemetry or telemetry_from_plot(plot)

    digest, anomalies = None, {}
    if telemetry_payload and req.include_digest:
        try:
            digest = compute_metrics(telemetry_payload)
            anomalies = detect_anomalies(telemetry_payload)
        except Exception as e:
            digest = {"error": f"metric computation failed: {e}"}
            anomalies = {}
    # -------------------------------------------

    # Build user content with optional sections
    user_content = req.user_message
    if digest:
        user_content += "\n\n[FLIGHT_DIGEST]\n" + str(digest)
    if anomalies:
        user_content += "\n\n[ANOMALY_HINTS]\n" + str(anomalies)

    print("=== ADK new_message ===")
    print(user_content)

    if ADK_AVAILABLE:
        # 1) Agent
        agent = Agent(
            name="UAV_Log_Analyst_Agent",
            model=os.environ.get("ADK_MODEL", "gemini-1.5-pro"),
            instruction=SYSTEM_PROMPT,
            tools=[]
        )

        # 2) History -> ADK Event list (Events are used for history, but need to be appended correctly)
        # We will build history_events, but these are appended to the Session via session_service
        # and not passed directly to runner.run_async()
        history_events: List[Event] = []
        for m in SESSIONS[sid]["history"]:
            author = "user" if m.get("role") == "user" else "model"
            event_content = types.Content(role='user', parts=[types.Part.from_text(text=m.get("content", ""))])
            history_events.append(Event(author=author, content=event_content))

        # 3) New message: include TEXT + JSON with broad SDK compatibility
        parts = []

        # -- Text part (prefer from_text, fall back to constructor) --
        try:
            parts.append(types.Part.from_text(text=user_content))
        except Exception:
            # Some SDKs use direct constructor
            parts.append(types.Part(text=user_content))

        # -- JSON plot part (try inline_data paths, else fallback to text) --
        parts = []

        # Text part
        try:
            parts.append(types.Part.from_text(text=user_content))
        except Exception:
            parts.append(types.Part(text=user_content))

        # Plot as *text* (no JSON MIME)
        if plot:
            plot_text = "[PLOT_JSON]\n" + json.dumps({"plot": plot})
            try:
                parts.append(types.Part.from_text(text=plot_text))
            except Exception:
                parts.append(types.Part(text=plot_text))

        new_message_for_runner = types.Content(role="user", parts=parts)

        if plot:
            print(f"[plot] series count: {len(plot.get('series', []))}")

        # 4) Runner with in-memory session service
        session_service = InMemorySessionService()
        runner = Runner(agent=agent, session_service=session_service, app_name="UAV_Agent")

        # --- IMPORTANT: Ensure the session exists in the SessionService and load history ---
        session = await session_service.get_session(app_name="UAV_Agent", user_id=sid, session_id=sid)
        if not session:
            session = await session_service.create_session(app_name="UAV_Agent", user_id=sid, session_id=sid)
            # Load initial history into the ADK Session if it's new
            # Ensure the author is set correctly for historical events
            for event_to_add in history_events:
                await session_service.append_event(session, event_to_add)
        # --- END IMPORTANT SECTION ---

        # 5) Run async and accumulate streamed text
        reply_text = ""
        async for ev in runner.run_async(
            user_id=sid,
            session_id=sid,
            new_message=new_message_for_runner, # Pass types.Content directly here
        ):
            # Some events may be non-text; guard accordingly
            if getattr(ev, "content", None) and getattr(ev.content, "parts", None):
                for part in ev.content.parts:
                    if getattr(part, "text", None):
                        reply_text += part.text
            elif ev.is_error():
                reply_text += f"Error: {ev.error}"
                break

    else:
        reply_text = (
            "ADK not available; echoing. "
            f"Question: {req.user_message}. "
            f"Digest: {list((digest or {}).keys())}; "
            f"Anomalies: {list((anomalies or {}).keys())}"
        )

    # Update our simple in-process history (what the UI reads back)
    SESSIONS[sid]["history"].append({"role": "user", "content": req.user_message})
    SESSIONS[sid]["history"].append({"role": "assistant", "content": reply_text})

    return ChatResponse(session_id=sid, messages=SESSIONS[sid]["history"])

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os, uuid

try:
    from google_adk import Agent, Message, run_agent
    ADK_AVAILABLE = True
except Exception:
    ADK_AVAILABLE = False

from .tools.metrics import compute_metrics, detect_anomalies

app = FastAPI(title="UAV Agent API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

SESSIONS: Dict[str, Dict[str, Any]] = {}

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    user_message: str
    telemetry: Optional[Dict[str, Any]] = None
    include_digest: bool = True

class ChatResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]

SYSTEM_PROMPT = ("You are an expert UAV log analyst. Use provided telemetry digests "
                 "and anomaly hints to answer precisely. Show units/time.")

@app.get("/health")
def health(): return {"ok": True}

def _sid(given: Optional[str]) -> str:
    sid = given or str(uuid.uuid4())
    if sid not in SESSIONS: SESSIONS[sid] = {"history": []}
    return sid

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    sid = _sid(req.session_id)
    digest, anomalies = None, {}
    if req.telemetry and req.include_digest:
        try:
            digest = compute_metrics(req.telemetry)
            anomalies = detect_anomalies(req.telemetry)
        except Exception as e:
            digest, anomalies = {"error": f"metric computation failed: {e}"}, {}

    user_content = req.user_message
    if digest:    user_content += "\n\n[FLIGHT_DIGEST]\n" + str(digest)
    if anomalies: user_content += "\n\n[ANOMALY_HINTS]\n" + str(anomalies)

    if ADK_AVAILABLE:
        agent = Agent(model=os.environ.get("ADK_MODEL", "gemini-1.5-pro"),
                      system_message=SYSTEM_PROMPT, tools=[])
        history = [Message(role=m["role"], content=m["content"]) for m in SESSIONS[sid]["history"]]
        result = run_agent(agent, user_content, history=history)
        reply_text = result.text
    else:
        reply_text = ("ADK not available; echoing. "
                      f"Question: {req.user_message}. "
                      f"Digest: {list((digest or {}).keys())}; "
                      f"Anomalies: {list((anomalies or {}).keys())}")

    SESSIONS[sid]["history"].append({"role": "user", "content": req.user_message})
    SESSIONS[sid]["history"].append({"role": "assistant", "content": reply_text})
    return ChatResponse(session_id=sid, messages=SESSIONS[sid]["history"])

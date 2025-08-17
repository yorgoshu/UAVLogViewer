from typing import Any, Dict, List, Tuple

def _get_series(messages: Dict[str, Any], key_candidates: List[str]) -> List[Tuple[float,float]]:
    time_fields = ["TimeUS", "timeUS", "TimeMS", "timeMS", "T", "Time"]
    series = []
    for msg_name, entries in messages.items():
        if not isinstance(entries, list): continue
        for entry in entries:
            t_key = next((k for k in time_fields if k in entry), None)
            v_key = next((k for k in key_candidates if k in entry), None)
            if t_key and v_key:
                try:
                    t, v = float(entry[t_key]), float(entry[v_key])
                    series.append((t, v))
                except Exception:
                    pass
    return series

def compute_metrics(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    messages = telemetry.get("messages") or telemetry
    digest: Dict[str, Any] = {}

    alt_series = _get_series(messages, ["Alt", "ALT", "RelAlt", "alt", "hmsl"])
    if alt_series: digest["max_altitude_m"] = round(max(v for _, v in alt_series), 2)

    bat_temp = _get_series(messages, ["Temp", "BT", "BattTemp"])
    if bat_temp: digest["max_battery_temp_c"] = round(max(v for _, v in bat_temp), 2)

    bat_volt = _get_series(messages, ["Volt", "V", "Volt1", "Volt2", "Battery"])
    if bat_volt: digest["min_battery_voltage_v"] = round(min(v for _, v in bat_volt), 2)

    gps_sat = _get_series(messages, ["NSats", "Sats", "numSV"])
    if gps_sat:
        first_loss = next(((t, s) for t, s in gps_sat if s < 5), None)
        if first_loss: digest["first_gps_loss_time"] = first_loss[0]

    times = _get_series(messages, ["Alt", "Volt", "R", "Yaw"])
    if times:
        t0, t1 = min(t for t, _ in times), max(t for t, _ in times)
        if t1 > 1e12: duration_s = (t1 - t0) / 1e6
        elif t1 > 1e6: duration_s = (t1 - t0) / 1e3
        else: duration_s = (t1 - t0)
        digest["estimated_flight_time_s"] = round(duration_s, 2)
    return digest

def detect_anomalies(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    messages = telemetry.get("messages") or telemetry
    hints: Dict[str, Any] = {}

    alt_series = sorted(_get_series(messages, ["Alt", "ALT", "RelAlt"]), key=lambda x: x[0])
    drops = []
    for (t0, a0), (t1, a1) in zip(alt_series, alt_series[1:]):
        dt = max(1e-6, t1 - t0)
        if t1 > 1e12: dt_s = dt/1e6
        elif t1 > 1e6: dt_s = dt/1e3
        else: dt_s = dt
        dv = a1 - a0
        if dt_s > 0 and dv/dt_s < -10:
            drops.append({"time": t1, "drop_rate_mps": round(-dv/dt_s, 2)})
    if drops: hints["rapid_altitude_drops"] = drops[:5]

    volt_series = sorted(_get_series(messages, ["Volt", "Volt1", "Volt2", "V"]), key=lambda x: x[0])
    for (t0, v0), (t1, v1) in zip(volt_series, volt_series[1:]):
        if v0 - v1 > 1.0:
            hints.setdefault("voltage_sags", []).append({"time": t1, "delta_v": round(v0 - v1, 2)})
            if len(hints["voltage_sags"]) >= 5: break

    sat_series = sorted(_get_series(messages, ["NSats", "Sats", "numSV"]), key=lambda x: x[0])
    for (t0, s0), (t1, s1) in zip(sat_series, sat_series[1:]):
        if s1 < 5 and s0 >= 5:
            hints.setdefault("gps_drops", []).append({"time": t1, "sats": s1})
            if len(hints["gps_drops"]) >= 5: break

    return hints

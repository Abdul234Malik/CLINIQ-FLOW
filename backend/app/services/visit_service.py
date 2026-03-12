"""Visit service - Supabase-backed CRUD for visits."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.database.supabase import supabase


def create_visit(
    patient_id: str,
    created_by: str | None = None,
    reason_for_visit: str | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    """Create a new visit. Default status: WAITING_FOR_TRIAGE, triage_status: PENDING."""
    visit_id = str(uuid4())
    data = {
        "id": visit_id,
        "patient_id": patient_id,
        "visit_status": "WAITING_FOR_TRIAGE",
        "triage_status": "PENDING",
    }
    if reason_for_visit:
        data["reason_for_visit"] = reason_for_visit
    if department:
        data["department"] = department
    if created_by:
        data["created_by"] = created_by
    try:
        resp = supabase.table("visits").insert(data).execute()
    except Exception as e:
        raise Exception(f"Supabase insert failed: {e}") from e
    if not resp.data:
        raise Exception("Failed to create visit: no data returned")
    return resp.data[0]


def get_visit(visit_id: str) -> dict[str, Any] | None:
    """Get a single visit by id."""
    resp = supabase.table("visits").select("*").eq("id", visit_id).single().execute()
    return resp.data if resp.data else None


def update_visit_status(visit_id: str, status: str) -> None:
    """Update visit_status for a visit (e.g. COMPLETED after exam)."""
    supabase.table("visits").update({"visit_status": status}).eq("id", visit_id).execute()


def get_visits_today_count() -> int:
    """Count visits created today (UTC)."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_str = tomorrow_start.isoformat() + "Z"
    resp = supabase.table("visits").select("*", count="exact").gte("created_at", today_start).lt("created_at", tomorrow_str).execute()
    return getattr(resp, "count", None) or len(resp.data or [])


def get_waiting_for_triage_count() -> int:
    """Count visits with status WAITING_FOR_TRIAGE."""
    resp = supabase.table("visits").select("id", count="exact").eq("visit_status", "WAITING_FOR_TRIAGE").execute()
    return resp.count if hasattr(resp, "count") and resp.count is not None else len(resp.data or [])


def get_waiting_for_doctor_count() -> int:
    """Count visits with status WAITING_FOR_DOCTOR (doctor queue)."""
    resp = supabase.table("visits").select("id", count="exact").eq("visit_status", "WAITING_FOR_DOCTOR").execute()
    return resp.count if hasattr(resp, "count") and resp.count is not None else len(resp.data or [])


def get_queue_counts() -> list[dict[str, Any]]:
    """Return counts by visit_status for dashboard queue."""
    statuses = [
        ("WAITING_FOR_TRIAGE", "Waiting for Triage", "amber"),
        ("IN_TRIAGE", "In Triage", "blue"),
        ("WAITING_FOR_DOCTOR", "Waiting for Doctor", "indigo"),
        ("WITH_DOCTOR", "With Doctor", "green"),
        ("COMPLETED", "Completed", "gray"),
    ]
    result = []
    for status_val, label, color in statuses:
        resp = supabase.table("visits").select("id", count="exact").eq("visit_status", status_val).execute()
        count = resp.count if hasattr(resp, "count") and resp.count is not None else len(resp.data or [])
        result.append({"status": label, "count": count, "color": color})
    return result


def _format_arrival_time(created: Any) -> str:
    """Parse created_at from visit and return formatted time (e.g. 02:30 PM)."""
    if created is None:
        return ""
    if hasattr(created, "isoformat"):
        created = created.isoformat()
    s = str(created).strip() if created else ""
    if not s:
        return ""
    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        elif "+" not in s and "-" not in s[10:] and len(s) >= 19:
            s = s[:19] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.strftime("%I:%M %p")
    except Exception:
        pass
    if len(s) >= 16:
        return s[11:16]
    return s[:19] if s else ""


def get_nurse_queue(limit: int = 50) -> list[dict[str, Any]]:
    """Get visits for nurse triage queue with patient details. WAITING_FOR_TRIAGE first, then others."""
    resp = (
        supabase.table("visits")
        .select("id, patient_id, visit_status, triage_status, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    patient_ids = list({r["patient_id"] for r in rows if r.get("patient_id")})
    patients_map: dict[str, dict] = {}
    if patient_ids:
        try:
            p_resp = supabase.table("patients").select(
                "id, pid, first_name, last_name, age, gender, phone_number"
            ).in_("id", patient_ids).execute()
            for p in (p_resp.data or []):
                pk = p.get("id")
                if pk:
                    patients_map[pk] = p
        except Exception:
            pass
    out = []
    for r in rows:
        patient_id = r.get("patient_id", "")
        p = patients_map.get(patient_id, {})
        name = " ".join(filter(None, [p.get("first_name") or "", p.get("last_name") or ""])).strip() or "Unknown"
        patient_pid = (p.get("pid") or p.get("PID")) if p else None
        created = r.get("created_at")
        time_str = _format_arrival_time(created)
        visit_status = (r.get("visit_status") or "").strip()
        display_status = "Waiting for Triage" if visit_status == "WAITING_FOR_TRIAGE" else "Triaged"
        out.append({
            "id": r.get("id"),
            "visit_id": r.get("id"),
            "patient_id": patient_id,
            "pid": patient_pid,
            "name": name,
            "age": p.get("age"),
            "gender": p.get("gender") or "",
            "arrivalTime": time_str,
            "status": display_status,
            "contact": p.get("phone_number") or "",
            "visit_status": visit_status,
        })
    return out


def get_doctor_queue(limit: int = 50) -> list[dict[str, Any]]:
    """Get visits with WAITING_FOR_DOCTOR status + patient + triage record (vitals, urgency)."""
    resp = (
        supabase.table("visits")
        .select("id, patient_id, visit_status, triage_status, created_at")
        .in_("visit_status", ["WAITING_FOR_DOCTOR", "WITH_DOCTOR"])
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    patient_ids = list({r["patient_id"] for r in rows if r.get("patient_id")})
    visit_ids = [r["id"] for r in rows]

    patients_map: dict[str, dict] = {}
    if patient_ids:
        try:
            p_resp = supabase.table("patients").select(
                "id, pid, first_name, last_name, age, gender"
            ).in_("id", patient_ids).execute()
            for p in p_resp.data or []:
                if p.get("id"):
                    patients_map[p["id"]] = p
        except Exception:
            pass

    triage_map: dict[str, dict] = {}
    if visit_ids:
        try:
            t_resp = supabase.table("triage_records").select(
                "visit_id, vitals, urgency_level"
            ).in_("visit_id", visit_ids).execute()
            for t in t_resp.data or []:
                vid = t.get("visit_id")
                if vid:
                    triage_map[vid] = t
        except Exception:
            pass

    out = []
    for r in rows:
        pid = r.get("patient_id", "")
        p = patients_map.get(pid, {})
        name = " ".join(filter(None, [p.get("first_name"), p.get("last_name")])).strip() or "Unknown"
        triage = triage_map.get(r.get("id", ""), {})
        vitals = triage.get("vitals") or {}
        urgency = (triage.get("urgency_level") or r.get("triage_status") or "normal").lower()
        if urgency not in ("emergency", "urgent", "normal"):
            urgency = "normal" if urgency == "routine" or urgency == "follow-up" else "urgent"
        out.append({
            "id": r.get("id"),
            "visit_id": r.get("id"),
            "patient_id": pid,
            "pid": p.get("pid"),
            "name": name,
            "Age": p.get("age"),
            "age": p.get("age"),
            "gender": p.get("gender") or "",
            "urgency": urgency,
            "status": "Triaged",
            "vitals": vitals,
            "visit_status": r.get("visit_status", ""),
            "active": r.get("visit_status") == "WITH_DOCTOR",
        })
    urgency_order = {"emergency": 0, "urgent": 1, "normal": 2}
    out.sort(key=lambda x: (urgency_order.get(x["urgency"], 2), x.get("visit_id", "")))
    return out


def get_recent_visits(limit: int = 10) -> list[dict[str, Any]]:
    """Get recent visits with patient name. Fetches visits then looks up patient names."""
    resp = (
        supabase.table("visits")
        .select("id, patient_id, visit_status, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    patient_ids = list({r["patient_id"] for r in rows if r.get("patient_id")})
    patients_map = {}
    if patient_ids:
        try:
            p_resp = supabase.table("patients").select("id, first_name, last_name").in_("id", patient_ids).execute()
            for p in (p_resp.data or []):
                pid = p.get("id")
                name = " ".join(filter(None, [p.get("first_name"), p.get("last_name")])).strip() or "Unknown"
                patients_map[pid] = name
        except Exception:
            pass
    out = []
    for r in rows:
        pid = r.get("patient_id", "")
        name = patients_map.get(pid, "Unknown")
        created = r.get("created_at", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                time_str = dt.strftime("%I:%M %p")
            except Exception:
                time_str = created[:16] if len(created) >= 16 else created
        else:
            time_str = ""
        out.append({
            "id": r.get("id"),
            "patient": name,
            "time": time_str,
            "status": (r.get("visit_status") or "").replace("_", " "),
        })
    return out

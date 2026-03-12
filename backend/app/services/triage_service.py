"""Triage service - save and list triage records from Supabase."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.database.supabase import supabase


def get_latest_triage_for_visit(visit_id: str) -> dict[str, Any] | None:
    """Get the most recent triage record for a visit (for vitals in SOAP)."""
    resp = (
        supabase.table("triage_records")
        .select("id, visit_id, vitals, urgency_level, triaged_at")
        .eq("visit_id", visit_id)
        .order("triaged_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def save_triage_record(
    visit_id: str,
    patient_id: str,
    vitals: dict[str, Any],
    urgency_level: str,
    triaged_by: str | None = None,
) -> dict[str, Any]:
    """Save a triage record and update visit status to WAITING_FOR_DOCTOR."""
    record_id = str(uuid4())
    data = {
        "id": record_id,
        "visit_id": visit_id,
        "patient_id": patient_id,
        "vitals": vitals or {},
        "urgency_level": urgency_level or "normal",
        "triaged_by": triaged_by,
    }
    supabase.table("triage_records").insert(data).execute()

    # Update visit: move to WAITING_FOR_DOCTOR, store urgency in triage_status
    supabase.table("visits").update({
        "visit_status": "WAITING_FOR_DOCTOR",
        "triage_status": urgency_level or "COMPLETED",
    }).eq("id", visit_id).execute()

    return {"id": record_id, "visit_id": visit_id}


def get_triage_records(
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    urgency: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """List triage records with patient details. Returns list for Triage Records tab."""
    query = supabase.table("triage_records").select(
        "id, visit_id, patient_id, vitals, urgency_level, triaged_at, triaged_by"
    ).order("triaged_at", desc=True).limit(limit)

    if date_from:
        query = query.gte("triaged_at", date_from)
    if date_to:
        query = query.lte("triaged_at", date_to)
    if urgency:
        query = query.eq("urgency_level", urgency)

    resp = query.execute()
    rows = resp.data or []

    patient_ids = list({r["patient_id"] for r in rows if r.get("patient_id")})
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

    out = []
    for r in rows:
        pid = r.get("patient_id", "")
        p = patients_map.get(pid, {})
        name = " ".join(filter(None, [p.get("first_name"), p.get("last_name")])).strip() or "Unknown"
        vitals = r.get("vitals") or {}
        triaged_at = r.get("triaged_at")

        # Build vitals summary
        parts = []
        if vitals.get("temperature"):
            parts.append(f"{vitals['temperature']}°C")
        if vitals.get("bpSystolic") and vitals.get("bpDiastolic"):
            parts.append(f"{vitals['bpSystolic']}/{vitals['bpDiastolic']}")
        if vitals.get("heartRate"):
            parts.append(f"{vitals['heartRate']} bpm")
        if vitals.get("respiratoryRate"):
            parts.append(f"{vitals['respiratoryRate']} RR")
        vitals_summary = " | ".join(parts) if parts else "—"

        # Format triaged_at
        time_str = ""
        if triaged_at:
            s = triaged_at.isoformat() if hasattr(triaged_at, "isoformat") else str(triaged_at)
            try:
                if s.endswith("Z"):
                    s = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                time_str = dt.strftime("%I:%M %p, %b %d")
            except Exception:
                time_str = s[:16] if len(s) >= 16 else s

        out.append({
            "id": r.get("id"),
            "visit_id": r.get("visit_id"),
            "patient_id": pid,
            "pid": p.get("pid"),
            "name": name,
            "age": p.get("age"),
            "gender": p.get("gender") or "",
            "vitals": vitals,
            "vitalsSummary": vitals_summary,
            "urgencyLevel": r.get("urgency_level") or "normal",
            "triagedAt": time_str,
            "triagedAtRaw": triaged_at,
            "triagedBy": r.get("triaged_by"),
        })

    if search and search.strip():
        q = search.strip().lower()
        out = [
            x for x in out
            if q in (x.get("name") or "").lower()
            or q in (x.get("pid") or "").lower()
            or q in (x.get("id") or "").lower()
        ]

    return out

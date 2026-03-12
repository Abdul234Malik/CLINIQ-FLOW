"""Consultation transcript storage in Supabase."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.database.supabase import supabase
from app.services.triage_service import get_latest_triage_for_visit
from app.services.visit_service import update_visit_status


def save_consultation_transcript(
    visit_id: str,
    transcript: str,
    patient_id: str | None = None,
    doctor_id: str | None = None,
    soap_json: dict[str, Any] | None = None,
    structured_json: dict[str, Any] | None = None,
    prescriptions_json: list[dict[str, Any]] | None = None,
    doctor_notes: str | None = None,
) -> dict[str, Any]:
    """Save full visit record to Supabase and mark visit as COMPLETED.

    Includes transcript, SOAP summary, prescriptions (each with dose_check_result).
    """
    record_id = str(uuid4())
    data: dict[str, Any] = {
        "id": record_id,
        "visit_id": visit_id,
        "transcript": transcript or "",
        "patient_id": patient_id,
        "doctor_id": doctor_id,
    }
    if soap_json is not None:
        data["soap_json"] = soap_json
    if structured_json is not None:
        data["structured_json"] = structured_json
    if prescriptions_json is not None:
        data["prescriptions_json"] = prescriptions_json
    if doctor_notes is not None:
        data["doctor_notes"] = doctor_notes

    supabase.table("consultation_transcripts").insert(data).execute()
    update_visit_status(visit_id, "COMPLETED")
    return {"id": record_id, "visit_id": visit_id}


def get_doctor_examination_records(doctor_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get completed examination records (consultation_transcripts) for a doctor.

    Returns full consultation record: patient details, visit ID, triage data,
    transcript, SOAP, doctor notes, prescriptions with dose validation and overrides.
    """
    resp = (
        supabase.table("consultation_transcripts")
        .select("*")
        .eq("doctor_id", doctor_id)
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
                "id, pid, first_name, last_name, age, gender, date_of_birth, phone_number"
            ).in_("id", patient_ids).execute()
            for p in (p_resp.data or []):
                if p.get("id"):
                    patients_map[p["id"]] = p
        except Exception:
            pass
    out = []
    for r in rows:
        pid = r.get("patient_id", "")
        p = patients_map.get(pid, {})
        name = " ".join(filter(None, [p.get("first_name") or "", p.get("last_name") or ""])).strip() or "Unknown"
        visit_id = r.get("visit_id")
        triage_data = None
        if visit_id:
            triage_row = get_latest_triage_for_visit(visit_id)
            if triage_row:
                triage_data = {
                    "vitals": triage_row.get("vitals") or {},
                    "urgency_level": triage_row.get("urgency_level") or "normal",
                }
        out.append({
            "id": r.get("id"),
            "visit_id": visit_id,
            "patient_id": pid,
            "patient_name": name,
            "pid": p.get("pid"),
            "age": p.get("age"),
            "gender": p.get("gender") or "",
            "date_of_birth": p.get("date_of_birth"),
            "phone_number": p.get("phone_number"),
            "transcript": (r.get("transcript") or "")[:500] + ("…" if len(r.get("transcript") or "") > 500 else ""),
            "transcript_full": r.get("transcript") or "",
            "soap_json": r.get("soap_json"),
            "prescriptions_json": r.get("prescriptions_json") or [],
            "doctor_notes": r.get("doctor_notes"),
            "triage_data": triage_data,
            "created_at": r.get("created_at"),
        })
    return out


def get_latest_transcript(visit_id: str) -> dict[str, Any] | None:
    """Get most recent transcript for a visit."""
    resp = (
        supabase.table("consultation_transcripts")
        .select("*")
        .eq("visit_id", visit_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None

"""Nurse-specific endpoints.

These routes cover intake submission, triage checks, summary generation,
and reading latest intake result for a visit.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.services import triage_service
from app.services import visit_service
from pydantic import BaseModel, Field

from app.schemas.intake import IntakeRequest
from app.services.nlp.soap_formatter import SOAPFormatter
from app.services.nlp.symptom_extractor import SymptomExtractor
from app.services.orchestration.pipeline import process_intake
from app.utils.auth import AuthContext
from app.utils.auth import require_role
from app.utils.errors import error_payload
from app.utils.pydantic_compat import model_to_dict
from app.utils.storage import add_audit_log
from app.utils.storage import create_intake_record
from app.utils.storage import get_latest_intake

router = APIRouter(prefix="/nurse", tags=["Nurse"])


@router.get("/queue")
def nurse_queue_route(
    auth: AuthContext = Depends(require_role("nurse", "admin")),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get triage queue: visits with patient details for nurse dashboard."""
    _ = auth
    return visit_service.get_nurse_queue(limit=limit)


class CompleteTriageRequest(BaseModel):
    visit_id: str = Field(...)
    patient_id: str = Field(...)
    vitals: dict = Field(default_factory=dict)
    urgency_level: str = Field(default="normal")


@router.post("/complete-triage")
def complete_triage_route(
    payload: CompleteTriageRequest,
    auth: AuthContext = Depends(require_role("nurse", "admin")),
):
    """Save triage record (vitals + urgency) and move visit to WAITING_FOR_DOCTOR."""
    triage_service.save_triage_record(
        visit_id=payload.visit_id,
        patient_id=payload.patient_id,
        vitals=payload.vitals,
        urgency_level=payload.urgency_level or "normal",
        triaged_by=auth.user_id,
    )
    return {"ok": True, "visit_id": payload.visit_id}


@router.get("/triage-records")
def triage_records_route(
    auth: AuthContext = Depends(require_role("nurse", "admin")),
    limit: int = Query(default=50, ge=1, le=200),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    urgency: str | None = Query(default=None),
    search: str | None = Query(default=None),
):
    """List triage records for Triage Records tab."""
    _ = auth
    return triage_service.get_triage_records(
        limit=limit,
        date_from=date_from,
        date_to=date_to,
        urgency=urgency,
        search=search,
    )


class SummaryRequest(BaseModel):
    visit_id: str = Field(...)
    transcript: str = Field(..., min_length=3)
    patient_age: str | None = None
    patient_sex: str | None = None


@router.post("/process-intake")
def process_intake_route(
    payload: IntakeRequest,
    auth: AuthContext = Depends(require_role("nurse", "admin")),
):
    try:
        response = process_intake(dict(model_to_dict(payload)))
        create_intake_record(
            intake_id=str(uuid.uuid4()),
            visit_id=payload.visit_id,
            transcript=payload.symptoms_text,
            normalized_text=payload.symptoms_text,
            structured_json=response.get("summary", {}).get("soap", {}),
            urgency_level=response.get("triage", {}).get("urgency_level", "LOW"),
            red_flags=response.get("triage", {}).get("red_flags", []),
            summary_json=response.get("summary", {}),
        )
        add_audit_log(
            audit_id=str(uuid.uuid4()),
            actor_role=auth.role,
            action="nurse_process_intake",
            entity_type="visit",
            entity_id=payload.visit_id,
            metadata={"audit_event_id": response.get("audit_event_id")},
        )
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_payload("INTERNAL_ERROR", "Unable to process intake", str(exc)),
        ) from exc


@router.post("/summary")
def summary_route(
    payload: SummaryRequest,
    auth: AuthContext = Depends(require_role("nurse", "admin")),
):
    _ = auth
    try:
        extractor = SymptomExtractor()
        formatter = SOAPFormatter()
        structured_data, _ = extractor.extract(
            transcript=payload.transcript,
            session_id=f"visit-{payload.visit_id}",
            patient_age=payload.patient_age,
            patient_sex=payload.patient_sex,
        )
        soap_note = formatter.format(structured_data)
        return {
            "visit_id": payload.visit_id,
            "summary": {
                "soap": {
                    "S": soap_note.subjective,
                    "O": soap_note.objective,
                    "A": soap_note.assessment,
                    "P": soap_note.plan,
                },
                "disclaimer": soap_note.disclaimer,
            },
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_payload("INTERNAL_ERROR", "Unable to generate summary", str(exc)),
        ) from exc


@router.get("/visits/{visit_id}/latest-intake")
def latest_intake_route(
    visit_id: str,
    auth: AuthContext = Depends(require_role("nurse", "doctor", "admin")),
):
    _ = auth
    row = get_latest_intake(visit_id)
    if not row:
        raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "No intake found for visit", {"visit_id": visit_id}))

    for field in ("structured_json", "red_flags_json", "summary_json"):
        raw = row.get(field)
        if isinstance(raw, str):
            try:
                row[field] = json.loads(raw)
            except Exception:
                pass
    return row

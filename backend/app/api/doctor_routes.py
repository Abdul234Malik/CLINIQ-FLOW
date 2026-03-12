"""Doctor-facing endpoints.

Handles medication orders, override actions, and doctor queue (triaged patients waiting for consultation).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import transcript_service
from app.services import visit_service
from app.utils.auth import AuthContext
from app.utils.auth import require_role
from app.utils.errors import error_payload
from app.utils.storage import add_audit_log
from app.utils.storage import create_med_order
from app.utils.storage import list_visit_med_orders
from app.utils.storage import log_override

router = APIRouter()


@router.post("/doctor/start-exam")
def start_exam_route(
    visit_id: str = Query(...),
    auth: AuthContext = Depends(require_role("doctor", "admin")),
):
    """Mark visit as WITH_DOCTOR when doctor starts exam (shows In Consultation)."""
    visit_service.update_visit_status(visit_id, "WITH_DOCTOR")
    return {"ok": True, "visit_id": visit_id}


@router.post("/doctor/cancel-exam")
def cancel_exam_route(
    visit_id: str = Query(...),
    auth: AuthContext = Depends(require_role("doctor", "admin")),
):
    """Revert visit to WAITING_FOR_DOCTOR when doctor cancels without saving."""
    visit_service.update_visit_status(visit_id, "WAITING_FOR_DOCTOR")
    return {"ok": True, "visit_id": visit_id}


@router.get("/doctor/examination-records")
def examination_records_route(
    auth: AuthContext = Depends(require_role("doctor", "admin")),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get completed examination records (with transcripts) for this doctor."""
    return transcript_service.get_doctor_examination_records(doctor_id=auth.user_id, limit=limit)


@router.get("/doctor/queue")
def doctor_queue_route(
    auth: AuthContext = Depends(require_role("doctor", "admin")),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get patients who have completed triage and are waiting for doctor consultation."""
    _ = auth
    try:
        return visit_service.get_doctor_queue(limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=error_payload("INTERNAL_ERROR", str(e), None),
        ) from e


class PrescriptionItem(BaseModel):
    drug_name: str = Field(..., min_length=2)
    dose_mg_per_day: int = Field(..., gt=0)
    frequency_per_day: int = Field(..., ge=1)
    duration_days: int | None = Field(None, ge=1)
    is_safe: bool = False
    dose_check_result: dict = Field(default_factory=dict)
    override_reason: str | None = None


class SOAPSummary(BaseModel):
    subjective: str = Field("")
    objective: str = Field("")
    assessment: str = Field("")
    plan: str = Field("")


class SaveVisitRequest(BaseModel):
    visit_id: str = Field(...)
    patient_id: str | None = None
    transcript: str = Field(..., min_length=5)
    soap_summary: SOAPSummary = Field(...)
    prescriptions: list[PrescriptionItem] = Field(default_factory=list)
    doctor_notes: str | None = None


@router.post("/doctor/save-visit")
def save_visit_route(
    payload: SaveVisitRequest,
    auth: AuthContext = Depends(require_role("doctor", "admin")),
):
    """Save full visit record: transcript, SOAP, prescriptions, and mark visit COMPLETED."""
    visit = visit_service.get_visit(payload.visit_id)
    if not visit:
        raise HTTPException(
            status_code=404,
            detail=error_payload("NOT_FOUND", "Visit not found", {"visit_id": payload.visit_id}),
        )

    soap_json = {
        "subjective": payload.soap_summary.subjective,
        "objective": payload.soap_summary.objective,
        "assessment": payload.soap_summary.assessment,
        "plan": payload.soap_summary.plan,
    }

    prescriptions_json = [
        {
            "drug_name": p.drug_name,
            "dose_mg_per_day": p.dose_mg_per_day,
            "frequency_per_day": p.frequency_per_day,
            "duration_days": p.duration_days,
            "is_safe": p.is_safe,
            "dose_check_result": p.dose_check_result,
            "override_reason": p.override_reason,
        }
        for p in payload.prescriptions
    ]

    transcript_service.save_consultation_transcript(
        visit_id=payload.visit_id,
        transcript=payload.transcript,
        patient_id=payload.patient_id,
        doctor_id=auth.user_id,
        soap_json=soap_json,
        prescriptions_json=prescriptions_json,
        doctor_notes=payload.doctor_notes,
    )

    for p in payload.prescriptions:
        med_order_id = str(uuid.uuid4())
        create_med_order(
            med_order_id=med_order_id,
            visit_id=payload.visit_id,
            drug_name=p.drug_name,
            dose_mg_per_day=p.dose_mg_per_day,
            frequency_per_day=p.frequency_per_day,
            dose_check_result=p.dose_check_result,
            is_safe=p.is_safe,
        )
        add_audit_log(
            audit_id=str(uuid.uuid4()),
            actor_role=auth.role,
            action="create_med_order",
            entity_type="med_order",
            entity_id=med_order_id,
            metadata={"visit_id": payload.visit_id, "drug_name": p.drug_name},
        )

    add_audit_log(
        audit_id=str(uuid.uuid4()),
        actor_role=auth.role,
        action="save_visit",
        entity_type="visit",
        entity_id=payload.visit_id,
        metadata={"prescriptions_count": len(payload.prescriptions)},
    )

    return {"ok": True, "visit_id": payload.visit_id}


class OverrideRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class MedOrderCreateRequest(BaseModel):
    visit_id: str = Field(...)
    drug_name: str = Field(..., min_length=2)
    dose_mg_per_day: int = Field(..., gt=0)
    frequency_per_day: int = Field(..., ge=1)
    is_safe: bool = False
    dose_check_result: dict = Field(default_factory=dict)


@router.post("/med-orders")
def create_med_order_route(
    payload: MedOrderCreateRequest,
    auth: AuthContext = Depends(require_role("doctor", "admin")),
):
    try:
        visit = visit_service.get_visit(payload.visit_id)
    except Exception:
        visit = None
    if not visit:
        raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "Visit not found", {"visit_id": payload.visit_id}))

    med_order_id = str(uuid.uuid4())
    med_order = create_med_order(
        med_order_id=med_order_id,
        visit_id=payload.visit_id,
        drug_name=payload.drug_name,
        dose_mg_per_day=payload.dose_mg_per_day,
        frequency_per_day=payload.frequency_per_day,
        dose_check_result=payload.dose_check_result,
        is_safe=payload.is_safe,
    )
    add_audit_log(
        audit_id=str(uuid.uuid4()),
        actor_role=auth.role,
        action="create_med_order",
        entity_type="med_order",
        entity_id=med_order_id,
        metadata={"visit_id": payload.visit_id, "drug_name": payload.drug_name},
    )
    return med_order


@router.get("/visits/{visit_id}/med-orders")
def list_med_orders_route(
    visit_id: str,
    auth: AuthContext = Depends(require_role("doctor", "admin")),
):
    _ = auth
    return {"visit_id": visit_id, "items": list_visit_med_orders(visit_id)}


@router.post("/med-orders/{med_order_id}/override")
def override_med_order(
    med_order_id: str,
    payload: OverrideRequest,
    auth: AuthContext = Depends(require_role("doctor", "admin")),
    x_doctor_id: str | None = Header(default=None, alias="X-Doctor-Id"),
):
    event_id = str(uuid.uuid4())
    log_override(
        event_id=event_id,
        med_order_id=med_order_id,
        override_reason=payload.reason,
        actor_role=auth.role,
        doctor_id=x_doctor_id,
    )
    add_audit_log(
        audit_id=str(uuid.uuid4()),
        actor_role=auth.role,
        action="override_med_order",
        entity_type="med_order",
        entity_id=med_order_id,
        metadata={"doctor_id": x_doctor_id},
    )
    return {
        "override_logged": True,
        "event_id": event_id,
        "med_order_id": med_order_id,
    }

"""AI orchestration endpoints.

This file exposes core demo AI actions:
intake processing, dose checks, triage-only, and summary-only requests.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.schemas.dose import DoseCheckRequest, DoseCheckResponse
from app.schemas.intake import IntakeRequest
from app.services.nlp.soap_formatter import SOAPFormatter
from app.services.nlp.symptom_extractor import SymptomExtractor
from app.services.orchestration.pipeline import process_intake
from app.utils.auth import AuthContext
from app.utils.auth import require_role
from app.utils.errors import error_payload
from app.utils.storage import add_audit_log
from app.utils.storage import create_intake_record
from app.utils.storage import log_dose_check

router = APIRouter()

# Guideline subset for demo use (pediatric mg/kg/day + max daily).
FORMULARY = {
    "amoxicillin": {"min_mg_per_kg_day": 20.0, "max_mg_per_kg_day": 40.0, "max_daily_mg": 1000.0},
    "paracetamol": {"min_mg_per_kg_day": 40.0, "max_mg_per_kg_day": 60.0, "max_daily_mg": 4000.0},
    "ibuprofen": {"min_mg_per_kg_day": 20.0, "max_mg_per_kg_day": 30.0, "max_daily_mg": 2400.0},
    "artemether_lumefantrine": {"min_mg_per_kg_day": 4.0, "max_mg_per_kg_day": 8.0, "max_daily_mg": 480.0},
}


class SummaryRequest(BaseModel):
    visit_id: str = Field(...)
    transcript: str = Field(..., min_length=3)
    patient_age: str | None = None
    patient_sex: str | None = None


@router.post("/process_intake")
def process_intake_route(
    payload: IntakeRequest,
    auth: AuthContext = Depends(require_role("nurse", "doctor", "admin")),
):
    try:
        response = process_intake(payload.model_dump())
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
            action="process_intake",
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


@router.post("/dose-check", response_model=DoseCheckResponse)
def dose_check_route(
    payload: DoseCheckRequest,
    auth: AuthContext = Depends(require_role("doctor", "admin")),
) -> DoseCheckResponse:
    _ = auth
    drug_key = payload.drug.strip().lower()
    rule = FORMULARY.get(drug_key)
    event_id = str(uuid.uuid4())

    if rule is None:
        # Safe fallback for unknown drugs in blocker pass.
        response = DoseCheckResponse(
            safe=True,
            warnings=["No formulary rule found for drug; clinician review required"],
            recommended_range_mg_per_day={"min": 0, "max": payload.chosen_dose_mg_per_day},
            max_mg_per_day=payload.chosen_dose_mg_per_day,
            event_id=event_id,
            allow_override=True,
        )
        log_dose_check(
            event_id=event_id,
            visit_id=payload.visit_id,
            drug_name=payload.drug,
            chosen_dose_mg_per_day=payload.chosen_dose_mg_per_day,
            safe=response.safe,
            warnings=response.warnings,
        )
        return response

    recommended_min = round(rule["min_mg_per_kg_day"] * payload.weight_kg)
    recommended_max = round(rule["max_mg_per_kg_day"] * payload.weight_kg)
    max_daily = round(min(rule["max_daily_mg"], recommended_max))

    warnings = []
    safe = True
    if payload.chosen_dose_mg_per_day < recommended_min:
        safe = False
        warnings.append("Dose is below recommended mg/kg/day range")
    if payload.chosen_dose_mg_per_day > recommended_max:
        safe = False
        warnings.append("Dose exceeds recommended mg/kg/day range")
    if payload.chosen_dose_mg_per_day > max_daily:
        safe = False
        warnings.append("Dose exceeds max daily limit")

    response = DoseCheckResponse(
        safe=safe,
        warnings=warnings,
        recommended_range_mg_per_day={"min": recommended_min, "max": recommended_max},
        max_mg_per_day=max_daily,
        event_id=event_id,
        allow_override=True,
    )
    log_dose_check(
        event_id=event_id,
        visit_id=payload.visit_id,
        drug_name=payload.drug,
        chosen_dose_mg_per_day=payload.chosen_dose_mg_per_day,
        safe=response.safe,
        warnings=response.warnings,
    )
    return response


@router.post("/summary")
def summary_route(
    payload: SummaryRequest,
    auth: AuthContext = Depends(require_role("nurse", "doctor", "admin")),
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

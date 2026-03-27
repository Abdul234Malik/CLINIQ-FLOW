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
from app.services.orchestration.pipeline import process_intake
from app.utils.ai_engine_client import post_json
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

# Adult total daily doses (mg/day) for Clark's/Young's rule when drug not in pediatric formulary.
# Clark's: (weight_kg/68) × adult_dose. Young's: [age/(age+12)] × adult_dose.
ADULT_DOSE_LOOKUP = {
    "metronidazole": 1500,
    "ciprofloxacin": 1000,
    "erythromycin": 1200,
    "azithromycin": 500,
    "cotrimoxazole": 960,
    "co-trimoxazole": 960,
    "ceftriaxone": 2000,
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
        # Drug not in formulary: try Clark's or Young's rule if adult dose is known.
        adult_dose = ADULT_DOSE_LOOKUP.get(drug_key)
        guideline_ref = _dose_guideline_reference(use_clarks=True)
        calc_method: str | None = None
        rec_min, rec_max, max_daily = 0, payload.chosen_dose_mg_per_day, payload.chosen_dose_mg_per_day
        warnings_list = []

        if adult_dose is not None:
            # Apply Clark's Rule (weight known) or Young's Rule (age-based fallback).
            if payload.weight_kg > 0:
                # Clark's: (weight_kg / 68) × adult_dose = pediatric_dose
                estimated = round((payload.weight_kg / 68.0) * adult_dose)
                # Allow ±25% tolerance
                rec_min = max(0, round(estimated * 0.75))
                rec_max = round(estimated * 1.25)
                max_daily = min(rec_max, round(adult_dose * 1.0))  # cap at adult dose
                calc_method = "clarks_rule"
                if payload.chosen_dose_mg_per_day < rec_min:
                    warnings_list.append("Dose below Clark's Rule estimate (±25% tolerance)")
                elif payload.chosen_dose_mg_per_day > rec_max:
                    warnings_list.append("Dose exceeds Clark's Rule estimate (±25% tolerance)")
            elif payload.age_years > 0:
                # Young's: [age / (age + 12)] × adult_dose (cannot use for age 0)
                factor = payload.age_years / (payload.age_years + 12.0)
                estimated = round(factor * adult_dose)
                rec_min = max(0, round(estimated * 0.75))
                rec_max = round(estimated * 1.25)
                max_daily = min(rec_max, round(adult_dose * 1.0))
                calc_method = "youngs_rule"
                if payload.chosen_dose_mg_per_day < rec_min:
                    warnings_list.append("Dose below Young's Rule estimate (±25% tolerance)")
                elif payload.chosen_dose_mg_per_day > rec_max:
                    warnings_list.append("Dose exceeds Young's Rule estimate (±25% tolerance)")

        if not warnings_list and adult_dose is None:
            # No adult dose available - cannot apply Clark's/Young's
            warnings_list = ["No formulary rule found; clinician review required"]
            guideline_ref = _dose_guideline_reference(use_clarks=True)

        # Safe when no warnings (dose in range) or when we only have "clinician review" fallback
        safe_unknown = len(warnings_list) == 0 or "clinician review" in str(warnings_list[0]).lower()
        response = DoseCheckResponse(
            safe=safe_unknown,
            warnings=warnings_list,
            recommended_range_mg_per_day={"min": rec_min, "max": rec_max},
            max_mg_per_day=max_daily,
            event_id=event_id,
            allow_override=True,
            guideline_reference=guideline_ref,
            calculation_method=calc_method,
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
        calculation_method="formulary",
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
        remote = post_json("/ai/summary", payload.model_dump(), timeout_s=20.0)
        if remote is not None:
            return remote
        return _stub_summary(payload.visit_id, payload.transcript)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_payload("INTERNAL_ERROR", "Unable to generate summary", str(exc)),
        ) from exc


def _stub_summary(visit_id: str, transcript: str) -> dict:
    text = (transcript or "").strip()
    return {
        "visit_id": visit_id,
        "summary": {
            "soap": {
                "S": text or "No transcript provided.",
                "O": "",
                "A": "AI service unavailable — clinician review required.",
                "P": "Proceed with clinical assessment.",
            },
            "disclaimer": "This summary is AI-generated for support only. It is not a diagnosis or treatment plan.",
        },
    }


def _dose_guideline_reference(*, use_clarks: bool) -> str:
    if use_clarks:
        return "Clark's Rule: (weight_kg/68) × adult_dose; Young's Rule: [age/(age+12)] × adult_dose."
    return "Formulary mg/kg/day ranges (demo subset)."

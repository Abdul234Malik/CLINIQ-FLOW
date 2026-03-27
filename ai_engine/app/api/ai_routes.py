from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.nlp.soap_formatter import SOAPFormatter
from app.services.nlp.symptom_extractor import SymptomExtractor
from app.services.nlp.vitals_urgency import default_urgency_stub
from app.services.nlp.validators import ClinicalValidator
from app.services.rag.guardrails import apply_guardrails

router = APIRouter(prefix="/ai", tags=["AI"])


class IntakeRequest(BaseModel):
    visit_id: str = Field(..., description="UUID for the visit")
    age_years: int = Field(..., ge=0, le=120)
    weight_kg: float = Field(..., gt=0)
    symptoms_text: str = Field(..., min_length=3)
    duration_days: int | None = Field(None, ge=0)
    vitals: dict | None = None


@router.post("/process_intake")
def process_intake_route(payload: IntakeRequest) -> dict:
    clean_text = payload.symptoms_text
    session_id = f"visit-{payload.visit_id}"

    extractor = SymptomExtractor()
    formatter = SOAPFormatter()
    validator = ClinicalValidator()

    structured_data, _method = extractor.extract(
        transcript=clean_text,
        session_id=session_id,
        patient_age=f"{payload.age_years} years",
    )
    soap_note = formatter.format(structured_data)
    validation = validator.validate_all(structured_data, soap_note)

    urgency = default_urgency_stub()
    triage = {
        "urgency_level": "LOW",
        "red_flags": urgency.get("critical_flags", []),
        "reasons": urgency.get("reasons") or ["Urgency assessed from vitals at triage only"],
    }

    soap = {
        "S": soap_note.subjective,
        "O": soap_note.objective,
        "A": soap_note.assessment,
        "P": soap_note.plan,
    }
    safe = apply_guardrails("\n".join(f"{k}: {v}" for k, v in soap.items()))
    disclaimer = safe.get("disclaimer", soap_note.disclaimer)

    response = {
        "visit_id": payload.visit_id,
        "triage": triage,
        "summary": {"soap": soap, "disclaimer": disclaimer},
        "audit_event_id": str(uuid.uuid4()),
    }
    if validation.warnings:
        response["validation_warnings"] = validation.warnings
    return response


class DoseCheckRequest(BaseModel):
    visit_id: str = Field(..., description="UUID for the visit")
    drug: str = Field(..., min_length=2)
    age_years: int = Field(..., ge=0, le=120)
    weight_kg: float = Field(..., gt=0)
    frequency_per_day: int = Field(..., ge=1)
    chosen_dose_mg_per_day: int = Field(..., gt=0)


@router.post("/dose-check")
def dose_check_route(payload: DoseCheckRequest) -> dict:
    # Guideline subset for demo use (pediatric mg/kg/day + max daily).
    formulary = {
        "amoxicillin": {"min_mg_per_kg_day": 20.0, "max_mg_per_kg_day": 40.0, "max_daily_mg": 1000.0},
        "paracetamol": {"min_mg_per_kg_day": 40.0, "max_mg_per_kg_day": 60.0, "max_daily_mg": 4000.0},
        "ibuprofen": {"min_mg_per_kg_day": 20.0, "max_mg_per_kg_day": 30.0, "max_daily_mg": 2400.0},
        "artemether_lumefantrine": {"min_mg_per_kg_day": 4.0, "max_mg_per_kg_day": 8.0, "max_daily_mg": 480.0},
    }
    adult_dose_lookup = {
        "metronidazole": 1500,
        "ciprofloxacin": 1000,
        "erythromycin": 1200,
        "azithromycin": 500,
        "cotrimoxazole": 960,
        "co-trimoxazole": 960,
        "ceftriaxone": 2000,
    }

    drug_key = payload.drug.strip().lower()
    rule = formulary.get(drug_key)
    event_id = str(uuid.uuid4())

    if rule is None:
        adult_dose = adult_dose_lookup.get(drug_key)
        rec_min, rec_max, max_daily = 0, payload.chosen_dose_mg_per_day, payload.chosen_dose_mg_per_day
        warnings_list: list[str] = []
        calc_method: str | None = None

        if adult_dose is not None:
            if payload.weight_kg > 0:
                estimated = round((payload.weight_kg / 68.0) * adult_dose)
                rec_min = max(0, round(estimated * 0.75))
                rec_max = round(estimated * 1.25)
                max_daily = min(rec_max, round(adult_dose * 1.0))
                calc_method = "clarks_rule"
                if payload.chosen_dose_mg_per_day < rec_min:
                    warnings_list.append("Dose below Clark's Rule estimate (±25% tolerance)")
                elif payload.chosen_dose_mg_per_day > rec_max:
                    warnings_list.append("Dose exceeds Clark's Rule estimate (±25% tolerance)")
            elif payload.age_years > 0:
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
            warnings_list = ["No formulary rule found; clinician review required"]

        safe_unknown = len(warnings_list) == 0 or "clinician review" in str(warnings_list[0]).lower()
        return {
            "safe": safe_unknown,
            "warnings": warnings_list,
            "recommended_range_mg_per_day": {"min": rec_min, "max": rec_max},
            "max_mg_per_day": max_daily,
            "event_id": event_id,
            "allow_override": True,
            "guideline_reference": None,
            "calculation_method": calc_method,
        }

    recommended_min = round(rule["min_mg_per_kg_day"] * payload.weight_kg)
    recommended_max = round(rule["max_mg_per_kg_day"] * payload.weight_kg)
    max_daily = round(min(rule["max_daily_mg"], recommended_max))

    warnings: list[str] = []
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

    return {
        "safe": safe,
        "warnings": warnings,
        "recommended_range_mg_per_day": {"min": recommended_min, "max": recommended_max},
        "max_mg_per_day": max_daily,
        "event_id": event_id,
        "allow_override": True,
        "guideline_reference": None,
        "calculation_method": "formulary",
    }


class SummaryRequest(BaseModel):
    visit_id: str = Field(...)
    transcript: str = Field(..., min_length=3)
    patient_age: str | None = None
    patient_sex: str | None = None


@router.post("/summary")
def summary_route(payload: SummaryRequest) -> dict:
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


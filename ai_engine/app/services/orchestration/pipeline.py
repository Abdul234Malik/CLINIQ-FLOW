from __future__ import annotations

import uuid

from app.services.nlp.deidentify import deidentify_text
from app.services.nlp.soap_formatter import SOAPFormatter
from app.services.nlp.symptom_extractor import SymptomExtractor
from app.services.nlp.validators import ClinicalValidator
from app.services.nlp.vitals_urgency import default_urgency_stub
from app.services.rag.guardrails import apply_guardrails
from app.utils.storage import log_intake


def process_intake(intake: dict) -> dict:
    """
    Contract-compatible intake flow:
    validate input -> de-identify -> extract -> triage -> SOAP -> guardrails.
    """
    visit_id = intake.get("visit_id")
    if not visit_id:
        raise ValueError("visit_id is required")

    clean_text = deidentify_text(intake.get("symptoms_text", ""))
    session_id = f"visit-{visit_id}"

    extractor = SymptomExtractor()
    formatter = SOAPFormatter()
    validator = ClinicalValidator()

    structured_data, _method = extractor.extract(
        transcript=clean_text,
        session_id=session_id,
        patient_age=f"{intake.get('age_years', 0)} years",
    )
    soap_note = formatter.format(structured_data)
    validation = validator.validate_all(structured_data, soap_note)
    # Urgency is assessed from vitals at triage only; no symptom-based urgency
    urgency = default_urgency_stub()
    urgency_level = _to_contract_urgency(urgency.get("level", "non_urgent"))
    triage = {
        "urgency_level": urgency_level,
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

    event_id = str(uuid.uuid4())
    log_intake(
        event_id=event_id,
        visit_id=visit_id,
        urgency_level=urgency_level,
        red_flags=triage["red_flags"],
    )

    response = {
        "visit_id": visit_id,
        "triage": triage,
        "summary": {"soap": soap, "disclaimer": disclaimer},
        "audit_event_id": event_id,
    }

    # TODO: Persist validation/audit details once storage layer is wired.
    if validation.warnings:
        response["validation_warnings"] = validation.warnings

    return response


def _to_contract_urgency(raw_level: str) -> str:
    mapping = {
        "immediate": "EMERGENCY",
        "urgent": "HIGH",
        "standard": "MEDIUM",
        "non_urgent": "LOW",
    }
    return mapping.get((raw_level or "").lower(), "LOW")

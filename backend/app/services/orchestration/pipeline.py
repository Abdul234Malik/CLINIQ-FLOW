from __future__ import annotations

import uuid

from app.utils.ai_engine_client import post_json
from app.utils.storage import log_intake


def process_intake(intake: dict) -> dict:
    """
    Contract-compatible intake flow:
    backend gateway calls AI engine for compute, then logs intake locally.
    """
    visit_id = intake.get("visit_id")
    if not visit_id:
        raise ValueError("visit_id is required")

    response = post_json("/ai/process_intake", intake, timeout_s=20.0) or _stub_process_intake(intake)

    event_id = response.get("audit_event_id") or str(uuid.uuid4())
    triage = response.get("triage") or {}
    log_intake(
        event_id=event_id,
        visit_id=visit_id,
        urgency_level=(triage.get("urgency_level") or "LOW"),
        red_flags=(triage.get("red_flags") or []),
    )
    response["audit_event_id"] = event_id
    return response


def _stub_process_intake(intake: dict) -> dict:
    visit_id = intake.get("visit_id") or "unknown"
    symptoms = (intake.get("symptoms_text") or "").strip()
    soap = {
        "S": symptoms or "No symptoms provided.",
        "O": "",
        "A": "AI service unavailable — clinician review required.",
        "P": "Proceed with clinical assessment.",
    }
    return {
        "visit_id": visit_id,
        "triage": {"urgency_level": "LOW", "red_flags": [], "reasons": ["AI engine unavailable"]},
        "summary": {
            "soap": soap,
            "disclaimer": "This summary is AI-generated for support only. It is not a diagnosis or treatment plan.",
        },
        "audit_event_id": str(uuid.uuid4()),
    }

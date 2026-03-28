# Purpose: Enforce safe language and add disclaimer (no diagnosis / no prescribing).


DISCLAIMER = "CLINIQ-FLOW provides decision support and does not diagnose or prescribe. Clinician judgement is required."


BANNED_IMPERATIVES = [
    "administer", "prescribe", "treat", "give", "start", "stop", "use", "take"
]


def sanitize_text(text: str) -> str:
    if not text:
        return text
    lowered = text.lower()
    for w in BANNED_IMPERATIVES:
        if w in lowered:
            # soft replacement to avoid directive language
            text = text.replace(w, "consider")
            lowered = text.lower()
    return text


def apply_guardrails(summary_text: str) -> dict:
    safe_text = sanitize_text(summary_text)
    return {"text": safe_text, "disclaimer": DISCLAIMER}

from __future__ import annotations

import re

# Conservative text masking for blocker pass.
PHONE_RE = re.compile(r"\b(?:\+?234|0)\d{10}\b")
EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
NAME_RE = re.compile(r"\b(?:my name is|i am|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)")


def deidentify_text(text: str) -> str:
    if not text:
        return text

    masked = PHONE_RE.sub("[PHONE_REDACTED]", text)
    masked = EMAIL_RE.sub("[EMAIL_REDACTED]", masked)
    masked = NAME_RE.sub(lambda m: m.group(0).replace(m.group(1), "[NAME_REDACTED]"), masked)
    return masked

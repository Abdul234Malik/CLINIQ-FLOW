"""Standard API error payload helper (AI Engine)."""

from __future__ import annotations

from typing import Any


def error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


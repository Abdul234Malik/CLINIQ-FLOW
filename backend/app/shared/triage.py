"""Triage response schema.

Represents urgency, red flags, and reasons shown in nurse/doctor UIs.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class TriageResult(BaseModel):
    urgency_level: str = Field(..., description="LOW | MEDIUM | HIGH | EMERGENCY")
    red_flags: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)

"""Dose-check request/response schemas.

Used by the doctor medication safety endpoint.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field


class DoseCheckRequest(BaseModel):
    visit_id: str = Field(..., description="UUID for the visit")
    drug: str = Field(..., min_length=2)
    age_years: int = Field(..., ge=0, le=120)
    weight_kg: float = Field(..., gt=0)
    frequency_per_day: int = Field(..., ge=1)
    chosen_dose_mg_per_day: int = Field(..., gt=0)


class DoseCheckResponse(BaseModel):
    safe: bool
    warnings: List[str]
    recommended_range_mg_per_day: Dict[str, int]
    max_mg_per_day: int
    event_id: str
    allow_override: bool

"""Intake request schema.

Defines the nurse intake payload used for triage and summary processing.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class IntakeRequest(BaseModel):
    visit_id: str = Field(..., description="UUID for the visit")
    age_years: int = Field(..., ge=0, le=120)
    weight_kg: float = Field(..., gt=0)
    symptoms_text: str = Field(..., min_length=3)
    duration_days: Optional[int] = Field(None, ge=0)
    vitals: Optional[Dict[str, Any]] = None

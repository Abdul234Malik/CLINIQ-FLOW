"""RAG (retrieval-augmented generation) API endpoints.

Current implementation is a lightweight contract surface over the existing
`app.services.rag.*` modules. It intentionally supports "graceful degradation"
until a full ingestion + vector DB pipeline is implemented.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.rag.retriever import (
    CLARKS_RULE_FORMULA,
    YOUNGS_RULE_FORMULA,
    get_clarks_rule_text,
    get_youngs_rule_text,
)

router = APIRouter(prefix="/rag", tags=["RAG"])


class GuidelineResponse(BaseModel):
    clarks_rule_formula: str
    youngs_rule_formula: str
    clarks_rule_text: str
    youngs_rule_text: str


@router.get("/guidelines", response_model=GuidelineResponse)
async def guidelines_route() -> GuidelineResponse:
    """Return the bundled guideline texts (static, file-based)."""
    return GuidelineResponse(
        clarks_rule_formula=CLARKS_RULE_FORMULA,
        youngs_rule_formula=YOUNGS_RULE_FORMULA,
        clarks_rule_text=get_clarks_rule_text(),
        youngs_rule_text=get_youngs_rule_text(),
    )


class ContextualDoseRequest(BaseModel):
    drug_name: str = Field(..., min_length=2)
    patient_age: int | None = Field(default=None, ge=0, le=120)
    patient_weight: float | None = Field(default=None, gt=0)
    indication: str | None = None
    top_k: int = Field(default=3, ge=1, le=10)


@router.post("/contextual-dosage")
async def contextual_dosage_route(payload: ContextualDoseRequest) -> dict:
    """Stub endpoint for future semantic retrieval."""
    return {
        "drug": payload.drug_name,
        "patient_context": {
            "age": payload.patient_age,
            "weight_kg": payload.patient_weight,
            "indication": payload.indication,
        },
        "ai_enhanced": False,
        "relevant_guidelines": [],
        "formulas": {"clarks_rule": CLARKS_RULE_FORMULA, "youngs_rule": YOUNGS_RULE_FORMULA},
        "status": "placeholder",
    }


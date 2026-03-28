"""AI Engine main router - combines all API modules."""

from fastapi import APIRouter
from app.api import nlp_routes, asr_routes, rag_routes, health

router = APIRouter()

# Mount health endpoints
router.include_router(health.router, tags=["health"])

# Mount AI service endpoints (with /api prefix for organization)
router.include_router(nlp_routes.router, prefix="/nlp", tags=["nlp"])
router.include_router(asr_routes.router, prefix="/asr", tags=["asr"])
router.include_router(rag_routes.router, prefix="/rag", tags=["rag"])

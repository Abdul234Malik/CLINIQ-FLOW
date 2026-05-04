"""AI Engine main router - combines all API modules."""

from fastapi import APIRouter, Depends
from app.api import nlp_routes, asr_routes, rag_routes, health
from app.utils.auth import require_role

router = APIRouter()

# Mount health endpoints
router.include_router(health.router, tags=["health"])

# Mount AI service endpoints (protected by shared secret token).
_authz = [Depends(require_role("service"))]
router.include_router(nlp_routes.router, prefix="/nlp", tags=["nlp"], dependencies=_authz)
router.include_router(asr_routes.router, tags=["asr"], dependencies=_authz)
router.include_router(rag_routes.router, tags=["rag"], dependencies=_authz)

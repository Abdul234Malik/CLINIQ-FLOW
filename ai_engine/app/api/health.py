"""AI Engine health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    """Liveness probe - service is running."""
    return {"status": "ok", "service": "ai_engine"}


@router.get("/ready")
async def ready():
    """Readiness probe - service is ready to accept requests."""
    return {"status": "ready", "service": "ai_engine"}

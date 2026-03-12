from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dotenv import load_dotenv

from contextlib import asynccontextmanager

from app.api.admin_routes import router as admin_routes_router
from app.api.clinical_routes import router as clinical_routes_router
from app.api.doctor_routes import router as doctor_routes_router
from app.api.nlp_routes import router as nlp_router
from app.api.nurse_routes import router as nurse_routes_router
from app.api.orchestration_routes import router as orchestration_routes_router
from app.api.record_officer_routes import register_router as record_officer_register_router
from app.api.record_officer_routes import router as record_officer_routes_router
from app.api.router import api_router
from app.utils.auth import AuthContext
from app.utils.auth import require_role
from app.utils.errors import error_payload

load_dotenv()

# ASR routes optional (require torch, transformers, pyannote, etc.); use stubs if import fails
_asr_limiter = None
try:
    from app.api.asr_routes import translate_router, conversation_router, lifespan
    from app.services.asr.post_process import limiter as _asr_limiter
except Exception:
    translate_router = APIRouter(prefix="/translate", tags=["Translation"])
    conversation_router = APIRouter(prefix="/conversation", tags=["Conversation"])

    @translate_router.post("/chunk")
    async def _stub_chunk(auth: AuthContext = Depends(require_role("doctor", "nurse", "admin"))):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "error": "ASR not available",
                "detail": "Install ASR deps: pip install torch transformers pyannote.audio pydub. Add HF_TOKEN to .env.",
            },
        )

    @asynccontextmanager
    async def lifespan(app):
        yield


app = FastAPI(
    title="CliniqFlow API",
    description="AI-assisted pre-consultation platform for Nigerian paediatric healthcare",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,  # Use custom docs below (unpkg CDN; jsdelivr often times out)
    redoc_url=None,
)

if _asr_limiter is not None:
    app.state.limiter = _asr_limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Hamids router for ASR
app.include_router(translate_router)
app.include_router(conversation_router)

# Malik router kept active for Supabase-first endpoints under /api.
app.include_router(api_router, prefix="/api")

# Existing NLP service endpoints.
app.include_router(nlp_router)

# Legacy import kept for reference:
# from app.api.asr_routes import router as asr_router
# Commented out because ASR module can fail import/startup in API mode.
try:
    from app.api.asr_routes import router as asr_router
except Exception:
    asr_router = APIRouter(prefix="/asr", tags=["ASR"])

    class ASRTranscribeRequest(BaseModel):
        audio_base64: str | None = None
        transcript_hint: str | None = None
        language: str | None = Field(default="en")

    @asr_router.post("/transcribe")
    async def transcribe_route(
        payload: ASRTranscribeRequest,
        auth: AuthContext = Depends(require_role("nurse", "doctor", "admin")),
    ):
        _ = auth
        transcript = (payload.transcript_hint or "").strip()
        if not transcript:
            raise HTTPException(
                status_code=422,
                detail=error_payload(
                    "VALIDATION_ERROR",
                    "Either transcript_hint or audio_base64 is required",
                    None,
                ),
            )
        return {
            "transcript": transcript,
            "confidence": 0.75,
            "language": payload.language or "en",
            "engine": "stub_asr",
        }

# Contract-compatible route stack retained for frontend/test compatibility.
app.include_router(admin_routes_router, prefix="/admin", tags=["Admin"])
app.include_router(asr_router)
app.include_router(orchestration_routes_router, prefix="/ai", tags=["Orchestration"])
app.include_router(clinical_routes_router)
app.include_router(nurse_routes_router)
app.include_router(record_officer_register_router)  # /register-patient (avoids /patients/{id} conflict)
app.include_router(record_officer_routes_router)
app.include_router(doctor_routes_router, tags=["Doctor"])


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload("VALIDATION_ERROR", "Request validation failed", exc.errors()),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload("HTTP_ERROR", str(exc.detail), None),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_request, exc: Exception) -> JSONResponse:
    import os
    import traceback
    import logging
    logger = logging.getLogger("uvicorn.error")
    logger.exception("Unhandled exception: %s", exc)
    msg = str(exc) or type(exc).__name__
    if os.environ.get("DEBUG"):
        msg = f"{type(exc).__name__}: {msg}\n{traceback.format_exc()}"
    return JSONResponse(
        status_code=500,
        content=error_payload("INTERNAL_ERROR", msg[:2000], None),
    )


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    """Swagger UI using unpkg CDN (avoids jsdelivr timeouts)."""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url or "/docs/oauth2-redirect",
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css",
    )


@app.get("/docs/oauth2-redirect", include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    """ReDoc using unpkg CDN."""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://unpkg.com/redoc@next/bundles/redoc.standalone.js",
        redoc_css_url="https://unpkg.com/redoc@next/bundles/redoc.standalone.css",
    )


@app.get("/", tags=["Root"])
async def root():
    return {"message": "CliniqFlow API is running", "docs": "/docs"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "cliniq-flow-backend"}

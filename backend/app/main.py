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
# NOTE: NLP routes moved to AI Engine (port 8001). Backend calls via REST API.
from app.api.nurse_routes import router as nurse_routes_router
from app.api.orchestration_routes import router as orchestration_routes_router  # Calls AI Engine endpoints
from app.api.asr_stub_routes import router as asr_stub_routes_router
from app.api.record_officer_routes import register_router as record_officer_register_router
from app.api.record_officer_routes import router as record_officer_routes_router
from app.api.router import api_router
from app.utils.auth import AuthContext
from app.utils.auth import require_role
from app.utils.errors import error_payload

load_dotenv()

# NOTE: ASR routes moved to AI Engine (port 8001). Backend calls via REST API.
# Removed ASR imports (torch, transformers, pyannote) - handled by AI Engine
_asr_limiter = None

# Simple lifespan (no ASR initialization needed in backend)
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
# NOTE: ASR routers removed (moved to AI Engine on port 8001)

# Supabase-first endpoints under /api
app.include_router(api_router, prefix="/api")

# NOTE: NLP service endpoints removed (moved to AI Engine on port 8001)

# NOTE: ASR endpoints moved to AI Engine (port 8001)
# Frontend → Backend (/ai/*) → AI Engine (port 8001)
# No stub needed - requests go to AI Engine directly via orchestration_routes

# Register all business logic routers
app.include_router(admin_routes_router, prefix="/admin", tags=["Admin"])
app.include_router(orchestration_routes_router, prefix="/ai", tags=["Orchestration"])  # Calls AI Engine
app.include_router(asr_stub_routes_router)
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

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai_routes import router as ai_router
from app.api.asr_transcribe_routes import router as asr_transcribe_router
from app.api.nlp_routes import router as nlp_router

load_dotenv()


@asynccontextmanager
async def _noop_lifespan(_app: FastAPI):
    yield


def _asr_lifespan():
    try:
        from app.services.asr.post_process import lifespan as asr_lifespan
        return asr_lifespan
    except Exception:
        return _noop_lifespan


app = FastAPI(
    title="CliniqFlow AI Engine",
    description="AI compute service (NLP, RAG, ASR). Intended to run behind the backend gateway.",
    version="0.1.0",
    lifespan=_asr_lifespan(),
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("AI_ENGINE_CORS_ORIGIN", "http://localhost:5173"),
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Core compute endpoints
app.include_router(nlp_router)
app.include_router(ai_router)
app.include_router(asr_transcribe_router)


# Optional ASR translation/conversation endpoints (may fail import if deps missing)
try:
    from app.api.asr_routes import conversation_router, translate_router

    app.include_router(translate_router)
    app.include_router(conversation_router)
except Exception:
    pass


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "cliniq-flow-ai-engine"}


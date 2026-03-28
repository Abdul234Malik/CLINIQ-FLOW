"""AI Engine - FastAPI application for NLP, ASR, and RAG services."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ai_engine.app.api.router import router
import os
from dotenv import load_dotenv

load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="CLINIQ-FLOW AI Engine",
    version="1.0.0",
    description="AI services for clinical data extraction, audio transcription, and medical guidelines retrieval"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://localhost:3000", "localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include main router
app.include_router(router)


@app.get("/")
async def root():
    """AI Engine root endpoint."""
    return {
        "service": "CLINIQ-FLOW AI Engine",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "nlp": "/nlp/*",
            "asr": "/asr/*",
            "rag": "/rag/*",
        }
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AI_ENGINE_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)

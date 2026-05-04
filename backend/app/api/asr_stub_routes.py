"""ASR stub endpoints (Backend).

The production ASR implementation lives in the AI Engine service. These routes
exist so the Backend can run (and tests can pass) without the heavy ASR stack.
"""

from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.utils.auth import require_role
from app.utils.errors import error_payload

router = APIRouter(prefix="/asr", tags=["ASR"])


class ASRTranscribeRequest(BaseModel):
    audio_base64: str | None = None
    transcript_hint: str | None = None
    language: str | None = Field(default="en")


@router.post("/transcribe")
async def transcribe_route(
    payload: ASRTranscribeRequest,
    _auth=Depends(require_role("nurse", "doctor", "admin")),
):
    transcript = (payload.transcript_hint or "").strip()
    if not transcript and payload.audio_base64:
        try:
            raw = base64.b64decode(payload.audio_base64, validate=False)
            transcript = f"[audio-bytes:{len(raw)}] transcription_placeholder"
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=error_payload("VALIDATION_ERROR", "Invalid base64 audio payload", str(exc)),
            ) from exc

    if not transcript:
        raise HTTPException(
            status_code=422,
            detail=error_payload("VALIDATION_ERROR", "Either transcript_hint or audio_base64 is required", None),
        )

    return {
        "transcript": transcript,
        "confidence": 0.75,
        "language": payload.language or "en",
        "engine": "stub_asr",
        "request_id": str(uuid.uuid4()),
    }


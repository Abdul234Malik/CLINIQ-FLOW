
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request,Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import librosa
import numpy as np
import soundfile as sf
import tempfile
import os
import logging
import time
import uuid
from contextlib import asynccontextmanager
from collections import defaultdict
from dotenv import load_dotenv

import uvicorn
from app.services.asr.post_process import verify_key,diarized,formated, model_manager,CACHE_DIR,MAX_FILE_MB,SAMPLE_RATE,MIN_DURATION_S,session_store,logger,ALLOWED_ORIGINS,limiter,lifespan,ALLOWED_TYPES
load_dotenv()


# app = FastAPI(title="Nigerian Medical Live Speech Translation API", version="1.0.0", lifespan=lifespan)
# app.state.limiter = limiter
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=ALLOWED_ORIGINS,
#     allow_methods=["POST", "GET", "DELETE"],
#     allow_headers=["Authorization", "Content-Type"],
# )

# @app.get("/health")
# def health_check():
    
#     return {
#         "status":          "ok",
#         "model_loaded":    model_manager.model_loaded,
#         "device":          model_manager.device,
#         "whisper_cached":  os.path.exists(os.path.join(CACHE_DIR, "config.json")),
        
#         "diarizer_loaded": model_manager.diarizer is not None,
#         "active_sessions": len(session_store),
#     }


# from pydub import AudioSegment
# import soundfile as sf
# import os

# # to tell pydub exactly where ffmpeg is

# FFMPEG_PATH  = r"C:\ffmpeg\bin\ffmpeg.exe"
# FFPROBE_PATH = r"C:\ffmpeg\bin\ffprobe.exe"

# if os.path.exists(FFMPEG_PATH):
#     AudioSegment.converter = FFMPEG_PATH
#     AudioSegment.ffprobe   = FFPROBE_PATH


# @app.post("/translate-chunk")
# @limiter.limit("60/minute")
# async def translate_chunk(
#     request:     Request,
#     file:        UploadFile = File(..., description="Audio file (WAV or MP3)"),
#     session_id:  str        = Form(default="default"),
#     chunk_index: int        = Form(default=0),
#     api_key:     str        = Depends(verify_key),
# ):
#     request_id = str(uuid.uuid4())[:8]

#     logger.info(
#         f"[{request_id}] Chunk received | "
#         f"session={session_id} | chunk={chunk_index} | file={file.filename}"
#     )
#     start = time.time()

#     # Guard: models must be loaded
#     if not model_manager.model_loaded:
#         raise HTTPException(
#             status_code=503,
#             detail="Model still loading — please try again in a moment."
#         )

#     # Guard: file type 
#     if file.content_type not in ALLOWED_TYPES:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid file type: {file.content_type}. Must be WAV or MP3."
#         )

#     # Read file bytes 
#     contents = await file.read()

#     if len(contents) == 0:
#         raise HTTPException(status_code=400, detail="Empty audio file.")

#     size_mb = len(contents) / (1024 * 1024)
#     if size_mb > MAX_FILE_MB:
#         raise HTTPException(
#             status_code=400,
#             detail=f"File too large: {round(size_mb, 1)}MB. Max is {MAX_FILE_MB}MB."
#         )

#     # Log first bytes to help debug format issues
#     logger.info(f"[{request_id}] File size: {len(contents)} bytes | header: {contents[:12]}")

#     # Save uploaded file with its original extension 
#     original_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".wav"
#     if not original_ext:
#         original_ext = ".wav"

#     with tempfile.NamedTemporaryFile(suffix=original_ext, delete=False) as tmp:
#         tmp.write(contents)
#         tmp_path = tmp.name

#     wav_path = tmp_path + "_converted.wav"

#     try:
#         # Convert to clean 16kHz mono WAV using pydub + ffmpeg 
#         # pydub handles any format: WAV, MP3, M4A, WebM, OGG, etc.
#         # ffmpeg does the actual decoding under the hood
#         logger.info(f"[{request_id}] Converting audio with ffmpeg...")
#         audio_seg = AudioSegment.from_file(tmp_path)           
#         audio_seg = audio_seg.set_frame_rate(SAMPLE_RATE)      
#         audio_seg = audio_seg.set_channels(1)                 
#         audio_seg.export(wav_path, format="wav")              
#         logger.info(f"[{request_id}] Conversion done ✓")

#         # Load converted WAV as numpy array
#         # soundfile reads the clean WAV we just created — always works
#         audio, _ = sf.read(wav_path, dtype='float32', always_2d=False)

#         duration = len(audio) / SAMPLE_RATE

#         if duration < MIN_DURATION_S:
#             raise HTTPException(status_code=400, detail="Audio chunk too short.")

#         logger.info(f"[{request_id}] Audio loaded: {round(duration, 1)} seconds")

#         # Run diarization + translation
#         # Pass numpy array (for Whisper slicing) and wav_path (for pyannote file I/O)
#         segments = diarized(audio, wav_path)

#         elapsed = round(time.time() - start, 2)
#         chunk_conversation = formated(segments)

#         # Store chunk in session 
#         session_chunks = session_store[session_id]

#         while len(session_chunks) <= chunk_index:
#             session_chunks.append(None)

#         session_chunks[chunk_index] = {
#             "chunk_index":  chunk_index,
#             "segments":     segments,
#             "conversation": chunk_conversation,
#             "duration_s":   round(duration, 1),
#             "timestamp":    round(time.time()),
#         }

#         # Build full conversation transcript 
#         full_conversation = "\n\n".join([
#             f"[Chunk {c['chunk_index']}]\n{c['conversation']}"
#             for c in session_chunks
#             if c is not None
#         ])

#         logger.info(f"[{request_id}] Done in {elapsed}s | {len(segments)} speaker segments")

#         return {
#             "request_id":         request_id,
#             "status":             "success",
#             "session_id":         session_id,
#             "chunk_index":        chunk_index,
#             "segments":           segments,
#             "chunk_conversation": chunk_conversation,
#             "full_conversation":  full_conversation,
#             "chunk_duration_s":   round(duration, 1),
#             "elapsed_s":          elapsed,
#             "total_chunks":       len([c for c in session_chunks if c is not None]),
#         }

#     except HTTPException:
#         raise

#     except Exception as e:
#         logger.error(f"[{request_id}] Unexpected error: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail="Internal server error.")

#     finally:
#         # Clean up temp files
#         # Retry loop handles Windows file lock (pyannote may still have file open)
#         for path in [tmp_path, wav_path]:
#             if path and os.path.exists(path):
#                 for _ in range(3):
#                     try:
#                         os.remove(path)
#                         break
#                     except PermissionError:
#                         time.sleep(0.3)  # wait for pyannote to release the file


# @app.get("/conversation/{session_id}")
# async def get_conversation(
#     session_id: str,                          # which session to retrieve
#     api_key:    str = Depends(verify_key),  # auth check
# ):

#     # Return 404 if session doesn't exist in memory
#     if session_id not in session_store:
#         raise HTTPException(status_code=404, detail="Session not found.")

#     chunks = [c for c in session_store[session_id] if c is not None]

#     # Build full conversation text across all chunks
#     full_text = "\n\n".join([
#         f"[Chunk {c['chunk_index']}]\n{c['conversation']}"
#         for c in chunks
#     ])

#     # Flatten all segments from all chunks into one list
#     # This gives every individual speaker turn across the whole consultation
#     all_segments = [seg for c in chunks for seg in c["segments"]]

#     return {
#         "session_id":        session_id,
#         "total_chunks":      len(chunks),        
#         "all_segments":      all_segments,       
#         "full_conversation": full_text,         
#     }


# @app.delete("/conversation/{session_id}")
# async def end_conversation(
#     session_id: str,                         
#     api_key:    str = Depends(verify_key),  
# ):

#     # Return 404 if session doesn't exist
#     if session_id not in session_store:
#         raise HTTPException(status_code=404, detail="Session not found.")

#     # Collect all valid chunks before deleting
#     chunks    = [c for c in session_store[session_id] if c is not None]
#     full_text = "\n\n".join([
#         f"[Chunk {c['chunk_index']}]\n{c['conversation']}"
#         for c in chunks
#     ])

#     # Remove session from memory — frees up RAM
#     del session_store[session_id]

#     logger.info(
#         f"Session {session_id} ended | "
#         f"{len(chunks)} chunks processed | "
#         f"{len(full_text)} characters in transcript"
#     )

#     # Return final transcript so frontend can save or display it
#     return {
#         "status":            "ended",
#         "session_id":        session_id,
#         "total_chunks":      len(chunks),
#         "full_conversation": full_text,  # complete final transcript
#     }


from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request, Form
from pydub import AudioSegment
import shutil
import soundfile as sf
import subprocess
import tempfile
import os
import time
import uuid

from app.utils.auth import AuthContext, require_role
from app.services.asr.post_process import (
    diarized, formated, model_manager,
    session_store, logger, limiter,
    SAMPLE_RATE, MAX_FILE_MB, MIN_DURATION_S, ALLOWED_TYPES
)




# ffmpeg: env FFMPEG_PATH, then PATH, then common Windows install locations including WinGet
def _find_ffmpeg():
    explicit = os.environ.get("FFMPEG_PATH") or os.environ.get("FFMPEG_BIN")
    if explicit:
        ff = os.path.join(explicit, "ffmpeg.exe") if os.path.isdir(explicit) else explicit
        if os.path.isfile(ff):
            base = os.path.dirname(ff)
            fp = os.path.join(base, "ffprobe.exe")
            return ff, fp if os.path.isfile(fp) else ff
    exe = shutil.which("ffmpeg")
    if exe:
        fp = shutil.which("ffprobe")
        return exe, fp or exe.replace("ffmpeg", "ffprobe")
    if os.name == "nt":
        bases = [
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
            r"C:\Program Files (x86)\ffmpeg\bin",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\ffmpeg\bin"),
        ]
        # WinGet: Packages\Gyan.FFmpeg_*\ffmpeg-*-full_build\bin
        winget = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
        if os.path.isdir(winget):
            try:
                for name in os.listdir(winget):
                    if "ffmpeg" in name.lower() and os.path.isdir(os.path.join(winget, name)):
                        pkg = os.path.join(winget, name)
                        for sub in os.listdir(pkg):
                            bin_dir = os.path.join(pkg, sub, "bin")
                            ff = os.path.join(bin_dir, "ffmpeg.exe")
                            if os.path.isfile(ff):
                                fp = os.path.join(bin_dir, "ffprobe.exe")
                                return ff, fp if os.path.isfile(fp) else ff
            except OSError:
                pass
    else:
        bases = ["/usr/bin", "/usr/local/bin"]
    for base in bases:
        if not base:
            continue
        ff = os.path.join(base, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        fp = os.path.join(base, "ffprobe.exe" if os.name == "nt" else "ffprobe")
        if os.path.exists(ff):
            return ff, fp if os.path.exists(fp) else ff
    return None, None
_FFMPEG, _FFPROBE = _find_ffmpeg()
_FFMPEG_BIN = os.path.dirname(os.path.abspath(_FFMPEG)) if _FFMPEG else None
if _FFMPEG:
    AudioSegment.converter = _FFMPEG
    if _FFPROBE:
        AudioSegment.ffprobe = _FFPROBE
    if _FFMPEG_BIN and _FFMPEG_BIN not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")
    logger.info(f"ffmpeg found: {_FFMPEG}")
else:
    logger.warning("ffmpeg NOT found — WebM/MP3 conversion will fail. Install ffmpeg and add to PATH.")


def _convert_to_wav_subprocess(input_path: str, output_path: str, sample_rate: int = 16000) -> None:
    """Convert audio to WAV using ffmpeg subprocess. More reliable than pydub on Windows."""
    if not _FFMPEG:
        raise RuntimeError("ffmpeg not found")
    env = os.environ.copy()
    if _FFMPEG_BIN:
        env["PATH"] = _FFMPEG_BIN + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [_FFMPEG, "-y", "-i", input_path, "-ar", str(sample_rate), "-ac", "1", output_path],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=_FFMPEG_BIN if _FFMPEG_BIN else None,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr or result.stdout or 'unknown'}")


# Translation router
translate_router = APIRouter(prefix="/translate", tags=["Translation"])

#  Conversation router
conversation_router = APIRouter(prefix="/conversation", tags=["Conversation"])

# Mount both ASR sub-routers under a single `/asr/*` prefix so the main app can
# include this module safely.
router = APIRouter(prefix="/asr", tags=["ASR"])
router.include_router(translate_router)
router.include_router(conversation_router)


#  Translation endpoints 

@translate_router.post("/chunk")        # POST /translate/chunk
@limiter.limit("60/minute")
async def translate_chunk(
    request:     Request,
    file:        UploadFile = File(..., description="Audio file (WAV, MP3, WebM)"),
    session_id:  str        = Form(default="default"),
    chunk_index: int        = Form(default=0),
    auth:        AuthContext = Depends(require_role("doctor", "nurse", "admin")),
):
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Chunk received | session={session_id} | chunk={chunk_index} | file={file.filename}")
    start = time.time()

    if not model_manager.model_loaded:
        raise HTTPException(status_code=503, detail="Model still loading — please try again in a moment.")

    ctype = (file.content_type or "application/octet-stream").split(";")[0].strip()
    if ctype not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid file type: {ctype}. Allowed: WAV, MP3, WebM, OGG.")

    contents = await file.read()

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        raise HTTPException(status_code=400, detail=f"File too large: {round(size_mb, 1)}MB. Max is {MAX_FILE_MB}MB.")

    logger.info(f"[{request_id}] File size: {len(contents)} bytes | header: {contents[:12]}")

    original_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".wav"
    if not original_ext:
        original_ext = ".wav"

    with tempfile.NamedTemporaryFile(suffix=original_ext, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    wav_path = tmp_path + "_converted.wav"

    try:
        logger.info(f"[{request_id}] Converting audio with ffmpeg...")
        _convert_to_wav_subprocess(tmp_path, wav_path, SAMPLE_RATE)
        logger.info(f"[{request_id}] Conversion done ✓")

        audio, _ = sf.read(wav_path, dtype='float32', always_2d=False)
        duration  = len(audio) / SAMPLE_RATE

        if duration < MIN_DURATION_S:
            raise HTTPException(status_code=400, detail="Audio chunk too short.")

        logger.info(f"[{request_id}] Audio loaded: {round(duration, 1)} seconds")

        segments = diarized(audio, wav_path)
        elapsed            = round(time.time() - start, 2)
        chunk_conversation = formated(segments)

        session_chunks = session_store[session_id]
        while len(session_chunks) <= chunk_index:
            session_chunks.append(None)

        session_chunks[chunk_index] = {
            "chunk_index":  chunk_index,
            "segments":     segments,
            "conversation": chunk_conversation,
            "duration_s":   round(duration, 1),
            "timestamp":    round(time.time()),
        }

        full_conversation = "\n\n".join([
            f"[Chunk {c['chunk_index']}]\n{c['conversation']}"
            for c in session_chunks if c is not None
        ])

        logger.info(f"[{request_id}] Done in {elapsed}s | {len(segments)} speaker segments")

        return {
            "request_id":         request_id,
            "status":             "success",
            "session_id":         session_id,
            "chunk_index":        chunk_index,
            "segments":           segments,
            "chunk_conversation": chunk_conversation,
            "full_conversation":  full_conversation,
            "chunk_duration_s":   round(duration, 1),
            "elapsed_s":          elapsed,
            "total_chunks":       len([c for c in session_chunks if c is not None]),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {e}", exc_info=True)
        err_msg = str(e)
        detail = f"ASR error: {err_msg}" if os.environ.get("DEBUG") else "Internal server error."
        raise HTTPException(status_code=500, detail=detail)
    finally:
        for path in [tmp_path, wav_path]:
            if path and os.path.exists(path):
                for _ in range(3):
                    try:
                        os.remove(path)
                        break
                    except PermissionError:
                        time.sleep(0.3)


# Conversation endpoints

@conversation_router.get("/{session_id}")       
async def get_conversation(
    session_id: str,
    auth: AuthContext = Depends(require_role("doctor", "nurse", "admin")),
):
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found.")

    chunks       = [c for c in session_store[session_id] if c is not None]
    full_text    = "\n\n".join([f"[Chunk {c['chunk_index']}]\n{c['conversation']}" for c in chunks])
    all_segments = [seg for c in chunks for seg in c["segments"]]

    return {
        "session_id":        session_id,
        "total_chunks":      len(chunks),
        "all_segments":      all_segments,
        "full_conversation": full_text,
    }


@conversation_router.delete("/{session_id}")   
async def end_conversation(
    session_id: str,
    auth: AuthContext = Depends(require_role("doctor", "nurse", "admin")),
):
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found.")

    chunks    = [c for c in session_store[session_id] if c is not None]
    full_text = "\n\n".join([f"[Chunk {c['chunk_index']}]\n{c['conversation']}" for c in chunks])
    del session_store[session_id]

    logger.info(f"Session {session_id} ended | {len(chunks)} chunks | {len(full_text)} chars")

    return {
        "status":            "ended",
        "session_id":        session_id,
        "total_chunks":      len(chunks),
        "full_conversation": full_text,  # complete final transcript
    }


              

# """ASR (audio-to-text) API endpoints.

# These endpoints accept audio/text inputs and return transcript text that can
# be passed into NLP summarization pipelines.
# """

# from __future__ import annotations

# import base64
# import uuid

# from fastapi import APIRouter, Depends, HTTPException
# from pydantic import BaseModel, Field

# from app.utils.auth import require_role
# from app.utils.errors import error_payload

# router = APIRouter(prefix="/asr", tags=["ASR"])


# class ASRTranscribeRequest(BaseModel):
#     audio_base64: str | None = None
#     transcript_hint: str | None = None
#     language: str | None = Field(default="en")


# @router.post("/transcribe")
# async def transcribe_route(
#     payload: ASRTranscribeRequest,
#     _role: str = Depends(require_role("nurse", "doctor", "admin")),
# ):
#     transcript = (payload.transcript_hint or "").strip()
#     if not transcript and payload.audio_base64:
#         try:
#             raw = base64.b64decode(payload.audio_base64, validate=False)
#             transcript = f"[audio-bytes:{len(raw)}] transcription_placeholder"
#         except Exception as exc:
#             raise HTTPException(status_code=400, detail=error_payload("VALIDATION_ERROR", "Invalid base64 audio payload", str(exc)))

#     if not transcript:
#         raise HTTPException(
#             status_code=422,
#             detail=error_payload("VALIDATION_ERROR", "Either transcript_hint or audio_base64 is required", None),
#         )

#     return {
#         "transcript": transcript,
#         "confidence": 0.75,
#         "language": payload.language or "en",
#         "engine": "stub_asr",
#         "request_id": str(uuid.uuid4()),
#     }


# @router.post("/upload")
# async def upload_and_transcribe_route(
#     payload: ASRTranscribeRequest,
#     _role: str = Depends(require_role("nurse", "doctor", "admin")),
# ):
#     raw = base64.b64decode(payload.audio_base64 or "", validate=False) if payload.audio_base64 else b""
#     transcript = payload.transcript_hint or f"[audio-bytes:{len(raw)}] transcription_placeholder"
#     return {
#         "transcript": transcript,
#         "confidence": 0.7,
#         "language": payload.language or "en",
#         "engine": "stub_asr",
#         "request_id": str(uuid.uuid4()),
#     }





# Hamid's Contribution

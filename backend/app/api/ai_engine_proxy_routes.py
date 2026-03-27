from __future__ import annotations

import os
from typing import Iterable

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _ai_engine_url() -> str:
    return (os.getenv("AI_ENGINE_URL") or "http://127.0.0.1:8001").rstrip("/")


def _filter_out_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers:
        lk = key.lower()
        if lk in _HOP_BY_HOP:
            continue
        if lk == "host":
            continue
        out[key] = value
    return out


async def _proxy_request(prefix: str, path: str, request: Request, timeout_s: float) -> Response:
    base = _ai_engine_url()
    upstream = f"{base}{prefix}"
    if path:
        upstream = f"{upstream}/{path}"

    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0)) as client:
            resp = await client.request(
                method=request.method,
                url=upstream,
                params=dict(request.query_params),
                content=body,
                headers=_filter_out_headers(request.headers.items()),
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"AI engine unreachable: {exc}") from exc

    headers = _filter_out_headers(resp.headers.items())
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=headers,
        media_type=resp.headers.get("content-type"),
    )


def build_proxy_router(*, prefix: str, tag: str, timeout_s: float) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy(path: str, request: Request) -> Response:
        return await _proxy_request(prefix, path, request, timeout_s=timeout_s)

    return router


nlp_proxy_router = build_proxy_router(prefix="/nlp", tag="NLP (Proxy)", timeout_s=30.0)
translate_proxy_router = build_proxy_router(prefix="/translate", tag="Translation (Proxy)", timeout_s=180.0)
conversation_proxy_router = build_proxy_router(prefix="/conversation", tag="Conversation (Proxy)", timeout_s=60.0)


asr_proxy_router = APIRouter(prefix="/asr", tags=["ASR (Proxy)"])


class _ASRTranscribeRequest(BaseModel):
    audio_base64: str | None = None
    transcript_hint: str | None = None
    language: str | None = Field(default="en")


@asr_proxy_router.post("/transcribe")
async def asr_transcribe(request: Request) -> Response:
    try:
        return await _proxy_request("/asr", "transcribe", request, timeout_s=120.0)
    except HTTPException:
        payload = {}
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        transcript = str(payload.get("transcript_hint") or "").strip()
        if not transcript:
            return JSONResponse(status_code=503, content={"error": "ASR not available", "detail": "AI engine unreachable"})
        return JSONResponse(
            status_code=200,
            content={
                "transcript": transcript,
                "confidence": 0.75,
                "language": payload.get("language") or "en",
                "engine": "stub_asr",
            },
        )


@asr_proxy_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def asr_proxy(path: str, request: Request) -> Response:
    return await _proxy_request("/asr", path, request, timeout_s=120.0)

from __future__ import annotations

import os

import httpx


def ai_engine_url() -> str:
    return (os.getenv("AI_ENGINE_URL") or "http://127.0.0.1:8001").rstrip("/")


def post_json(path: str, payload: dict, *, timeout_s: float = 20.0) -> dict | None:
    url = f"{ai_engine_url()}{path}"
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0)) as client:
            resp = client.post(url, json=payload)
        if resp.status_code >= 400:
            return None
        return resp.json()
    except Exception:
        return None


"""AI Engine authentication helpers.

AI Engine is intended to be called by the Backend service only.
All protected endpoints require:

  Authorization: Bearer <AI_ENGINE_TOKEN>
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.utils.errors import error_payload

load_dotenv()

bearer_scheme = HTTPBearer()


@dataclass
class AuthContext:
    role: str
    source: str
    metadata: dict[str, Any]


async def get_current_service(
    authorization: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthContext:
    token = (authorization.credentials or "").strip()
    expected = (os.getenv("AI_ENGINE_TOKEN") or "").strip()

    if not expected:
        raise HTTPException(
            status_code=503,
            detail=error_payload("AUTH_UNAVAILABLE", "AI Engine token is not configured", None),
        )

    if token != expected:
        raise HTTPException(
            status_code=401,
            detail=error_payload("UNAUTHORIZED", "Invalid AI Engine token", None),
        )

    return AuthContext(role="service", source="shared_secret", metadata={})


def require_role(*_allowed_roles: str) -> Callable[[AuthContext], AuthContext]:
    """Compatibility shim.

    The AI Engine uses a shared secret token (not end-user roles). If the token
    is valid, allow the request regardless of the provided role list.
    """

    async def dependency(auth: AuthContext = Depends(get_current_service)) -> AuthContext:
        return auth

    return dependency


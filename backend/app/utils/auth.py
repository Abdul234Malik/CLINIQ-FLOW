"""Shared authentication and role-based access control helpers.

Endpoints now use `Authorization: Bearer <token>` consistently.
For local tests only, a stub bearer mode can be enabled with
`CLINIQ_AUTH_MODE=stub`.
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

# Legacy header-based auth kept for future reference:
# from fastapi import Header
#
# def require_role(*allowed_roles: str) -> Callable[[str | None], str]:
#     allowed = {r.lower() for r in allowed_roles}
#
#     def dependency(x_role: str | None = Header(default=None, alias="X-Role")) -> str:
#         role = (x_role or "").strip().lower()
#         if role not in allowed:
#             raise HTTPException(
#                 status_code=403,
#                 detail=error_payload(
#                     "FORBIDDEN",
#                     "Insufficient role for this endpoint",
#                     {"required_any_of": sorted(allowed), "received": role or None},
#                 ),
#             )
#         return role
#
#     return dependency


@dataclass
class AuthContext:
    user_id: str | None
    email: str | None
    role: str
    source: str
    metadata: dict[str, Any]


def _get_supabase_client():
    try:
        from supabase import create_client
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=error_payload("AUTH_UNAVAILABLE", "Supabase auth is not available", None),
        ) from exc

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_anon_key:
        raise HTTPException(
            status_code=503,
            detail=error_payload("AUTH_UNAVAILABLE", "Supabase auth is not configured", None),
        )

    return create_client(supabase_url, supabase_anon_key)


def _stub_auth_context(token: str) -> AuthContext:
    if not token:
        raise HTTPException(
            status_code=401,
            detail=error_payload("UNAUTHORIZED", "Missing bearer token", None),
        )

    fields: dict[str, str] = {}
    for part in token.split("|"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        fields[key.strip().lower()] = value.strip()

    role = fields.get("role", "").lower()
    if not role:
        raise HTTPException(
            status_code=401,
            detail=error_payload("UNAUTHORIZED", "Stub token must include role", None),
        )

    return AuthContext(
        user_id=fields.get("user_id"),
        email=fields.get("email"),
        role=role,
        source="stub",
        metadata=fields,
    )


async def get_current_user(
    authorization: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthContext:
    token = authorization.credentials
    auth_mode = (os.getenv("CLINIQ_AUTH_MODE") or "supabase").strip().lower()

    if auth_mode == "stub":
        return _stub_auth_context(token)

    try:
        supabase = _get_supabase_client()
        user_resp = supabase.auth.get_user(token)
        user = user_resp.user
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=error_payload("UNAUTHORIZED", "Invalid session or token", None),
        ) from exc

    if not user:
        raise HTTPException(
            status_code=401,
            detail=error_payload("UNAUTHORIZED", "Invalid session or token", None),
        )

    metadata = user.user_metadata or {}
    role = (metadata.get("role") or "").strip().lower()
    if not role:
        raise HTTPException(
            status_code=403,
            detail=error_payload("FORBIDDEN", "User role is missing", None),
        )

    return AuthContext(
        user_id=getattr(user, "id", None),
        email=getattr(user, "email", None),
        role=role,
        source="supabase",
        metadata=metadata,
    )


def require_role(*allowed_roles: str) -> Callable[[AuthContext], AuthContext]:
    allowed = {r.lower() for r in allowed_roles}

    async def dependency(auth: AuthContext = Depends(get_current_user)) -> AuthContext:
        if auth.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=error_payload(
                    "FORBIDDEN",
                    "Insufficient role for this endpoint",
                    {"required_any_of": sorted(allowed), "received": auth.role or None},
                ),
            )
        return auth

    return dependency

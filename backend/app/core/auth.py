from dotenv import load_dotenv
load_dotenv()
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import requests
import os

try:
    from jose import jwt
except Exception:
    jwt = None

security = HTTPBearer()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None

# Legacy eager key fetch kept for reference:
# jwks = requests.get(SUPABASE_JWKS_URL).json()


def _get_jwks():
    if not SUPABASE_JWKS_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase JWKS URL is not configured",
        )
    try:
        return requests.get(SUPABASE_JWKS_URL, timeout=10).json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch Supabase JWKS",
        )


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if jwt is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="python-jose is required for Supabase JWT verification",
        )

    # Legacy local stub-token mode kept for reference:
    # auth_mode = (os.getenv("CLINIQ_AUTH_MODE") or "").strip().lower()
    # if auth_mode == "stub" or jwt is None:
    #     fields: dict[str, str] = {}
    #     for part in token.split("|"):
    #         if ":" not in part:
    #             continue
    #         k, v = part.split(":", 1)
    #         fields[k.strip().lower()] = v.strip()
    #     role = fields.get("role")
    #     if not role:
    #         raise HTTPException(
    #             status_code=status.HTTP_401_UNAUTHORIZED,
    #             detail="Invalid authentication token",
    #         )
    #     return {"app_metadata": {"role": role}, **fields}

    try:
        jwks = _get_jwks()
        header = jwt.get_unverified_header(token)
        kid = header["kid"]

        key = next(k for k in jwks["keys"] if k["kid"] == kid)

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience="authenticated"
        )

        return payload

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )


def require_role(required_role: str):
    def role_checker(payload=Depends(verify_token)):
        role = payload.get("app_metadata", {}).get("role")

        if role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )

        return payload

    return role_checker

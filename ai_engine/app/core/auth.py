"""AI Engine authentication - validates shared secret token."""

import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer()

# Shared secret token (set in env var)
AI_ENGINE_TOKEN = os.getenv("AI_ENGINE_TOKEN", "default-dev-token")


def verify_ai_engine_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate X-AI-Engine-Token header for internal Backend→AI Engine communication."""
    token = credentials.credentials
    
    if token != AI_ENGINE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid AI Engine token",
        )
    
    return token

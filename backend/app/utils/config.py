"""Backend configuration - loads and validates environment variables.

This is the single place for all env var configuration used by the backend.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# SUPABASE CONFIGURATION
# ============================================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DATABASE_URL = os.getenv("DATABASE_URL_SUPABASE") or os.getenv("DATABASE_URL")

# ============================================================================
# AI ENGINE CONFIGURATION
# Backend calls AI Engine (port 8001) via REST API for NLP/ASR/RAG services
# ============================================================================
AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:8001")
# Shared secret token for Backend → AI Engine communication (internal service)
AI_ENGINE_TOKEN = os.getenv("AI_ENGINE_TOKEN", "dev-secret-key")

# ============================================================================
# BACKEND CONFIGURATION
# ============================================================================
BACKEND_PORT = int(os.getenv("BACKEND_PORT", 8000))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

"""AI Engine configuration."""

import os
from dotenv import load_dotenv

load_dotenv()

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# AI Engine
AI_ENGINE_TOKEN = os.getenv("AI_ENGINE_TOKEN", "default-dev-token")
AI_ENGINE_PORT = int(os.getenv("AI_ENGINE_PORT", 8001))

# Debug mode
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

import os
from pathlib import Path
from supabase import create_client, Client
from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_BACKEND_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

_auth_mode = (os.getenv("CLINIQ_AUTH_MODE") or "").strip().lower()

if not SUPABASE_URL or not SUPABASE_KEY:
    # Allow non-Supabase modes (tests, local stub auth) to import the app.
    # Routes that actually need Supabase will fail at call time if supabase is None.
    if _auth_mode == "stub" or os.getenv("SKIP_SUPABASE") == "1":
        supabase: Client | None = None
    else:
        raise ValueError("Supabase credentials are not set")
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

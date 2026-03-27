"""Backend entrypoint.

Active path now follows the `malik` branch architecture (DB-linked routers in
`backend/app/main.py`).
"""

import sys
from pathlib import Path

# Ensure `backend/app` is importable as top-level `app` regardless of CWD.
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# uvicorn backend.main:app
from app.main import app  # noqa: E402

# Previous consolidated backend bootstrap kept for reference:
# - app.api.admin_routes / clinical_routes / doctor_routes / nurse_routes
# - app.api.orchestration_routes / nlp_routes / record_officer_routes
# - fallback /asr/transcribe stub in this file
# - startup init_db() and global exception handlers

"""Backend entrypoint.

Active path now follows the `malik` branch architecture (DB-linked routers in
`backend/app/main.py`).
"""

# Legacy single-path import kept for reference:
# from backend.app.main import app

try:
    # Works when launched from repository root:
    # uvicorn backend.main:app --reload
    from backend.app.main import app
except ModuleNotFoundError:
    # Fallback when launched from backend directory:
    # uvicorn main:app --reload
    from app.main import app

# Previous consolidated backend bootstrap kept for reference:
# - app.api.admin_routes / clinical_routes / doctor_routes / nurse_routes
# - app.api.orchestration_routes / nlp_routes / record_officer_routes
# - fallback /asr/transcribe stub in this file
# - startup init_db() and global exception handlers

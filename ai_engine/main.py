"""AI engine entrypoint.

Run from repo root:
  uvicorn ai_engine.main:app --reload --port 8001
"""

from __future__ import annotations

import sys
from pathlib import Path

_ENGINE_DIR = Path(__file__).resolve().parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from app.main import app  # noqa: E402


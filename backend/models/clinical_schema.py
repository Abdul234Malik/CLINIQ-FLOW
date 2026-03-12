"""Compatibility bridge for legacy import paths.

Some modules may still import `backend.models.clinical_schema`.
This re-exports the canonical models from `app.models.clinical_schema`.
"""

from app.models.clinical_schema import *  # noqa: F401,F403

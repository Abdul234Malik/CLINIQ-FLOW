"""Guideline retrieval for dose check and clinical decision support.

Loads Clark's Rule and Young's Rule from rag/files for use when drugs
are not in the main formulary.
"""

from __future__ import annotations

from pathlib import Path

_FILES_DIR = Path(__file__).resolve().parent / "files"

_CLARKS_RULE_FILE = _FILES_DIR / "Clark_Rule_for_Paediatric_Prescription.txt"
_YOUNGS_RULE_FILE = _FILES_DIR / "Young_Rule_for_Paediatric_Prescription.txt"

# Short formula summaries for API responses.
CLARKS_RULE_FORMULA = "(weight_kg / 68) × adult_dose_mg_per_day = estimated_pediatric_dose"
YOUNGS_RULE_FORMULA = "[age / (age + 12)] × adult_dose_mg_per_day = estimated_pediatric_dose"


def _read_file(path: Path) -> str:
    """Read guideline file. Returns empty string if missing."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


def get_clarks_rule_text() -> str:
    """Return Clark's Rule guideline text (weight-based pediatric dosing)."""
    return _read_file(_CLARKS_RULE_FILE)


def get_youngs_rule_text() -> str:
    """Return Young's Rule guideline text (age-based pediatric dosing, when weight unknown)."""
    return _read_file(_YOUNGS_RULE_FILE)


def get_dose_guideline_reference(use_clarks: bool = True) -> str:
    """Return a concise reference for the dose check response."""
    formula = CLARKS_RULE_FORMULA if use_clarks else YOUNGS_RULE_FORMULA
    return (
        f"Drug not in formulary. Consider applying {formula}. "
        "See backend/app/services/rag/files/ for full guidelines. Clinician judgment required."
    )

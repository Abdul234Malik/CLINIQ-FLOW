"""AI Engine storage stubs.

The AI Engine is designed to be stateless. For now, audit/pipeline events are
no-ops to keep the orchestration pipeline contract-compatible.
"""

from __future__ import annotations

from typing import Any


def log_intake(*, event_id: str, visit_id: str, urgency_level: str, red_flags: list[Any]) -> None:
    _ = (event_id, visit_id, urgency_level, red_flags)
    return


"""Pydantic v1/v2 compatibility helpers.

This repo currently mixes `model_dump()` (Pydantic v2) and `dict()` (Pydantic v1)
call sites. Use these helpers to keep runtime compatible with either version.
"""

from __future__ import annotations

from typing import Any, Mapping


def model_to_dict(model: Any, *, mode: str | None = None, exclude_none: bool = False) -> Mapping[str, Any]:
    """Return a dict for a Pydantic model (v1 or v2)."""

    if hasattr(model, "model_dump"):
        kwargs: dict[str, Any] = {"exclude_none": exclude_none}
        if mode is not None:
            kwargs["mode"] = mode
        return model.model_dump(**kwargs)  # type: ignore[attr-defined]

    if hasattr(model, "dict"):
        return model.dict(exclude_none=exclude_none)  # type: ignore[attr-defined]

    raise TypeError(f"Expected a Pydantic model, got: {type(model).__name__}")


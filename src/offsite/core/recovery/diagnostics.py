"""Structured recovery diagnostics for operator-facing failure reporting."""

from __future__ import annotations

from typing import Any

ALLOWED_FAILURE_CATEGORIES = {"integrity", "checkpoint", "schema", "media"}


def build_failure(
    category: str,
    code: str,
    message: str,
    path_rel: str | None = None,
) -> dict[str, Any]:
    """Build deterministic failure diagnostics payload for immutable reports."""
    if category not in ALLOWED_FAILURE_CATEGORIES:
        raise ValueError(f"unsupported failure category: {category}")

    payload: dict[str, Any] = {
        "category": category,
        "code": code,
        "message": message,
    }
    if path_rel is not None:
        payload["path_rel"] = path_rel
    return payload

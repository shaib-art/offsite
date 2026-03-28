"""Checksum primitives used by upload and apply-sync workflows."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return lowercase SHA-256 hex digest for the file at path."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

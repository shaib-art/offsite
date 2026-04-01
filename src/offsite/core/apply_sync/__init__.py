"""Apply-result contract and ingest operations."""

from offsite.core.apply_sync.contract import (
    build_apply_result_envelope,
    validate_apply_result_envelope,
    write_immutable_apply_result,
)
from offsite.core.apply_sync.ingest import IngestResult, ingest_apply_result
from offsite.core.apply_sync.migration import migrate_apply_result_envelope

__all__ = [
    "IngestResult",
    "build_apply_result_envelope",
    "ingest_apply_result",
    "migrate_apply_result_envelope",
    "validate_apply_result_envelope",
    "write_immutable_apply_result",
]

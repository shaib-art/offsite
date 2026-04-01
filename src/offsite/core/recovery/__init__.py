"""Recovery contract and execution primitives for Phase 4."""

from offsite.core.recovery.contract import (
    build_recovery_request,
    validate_recovery_request,
)
from offsite.core.recovery.diagnostics import build_failure
from offsite.core.recovery.executor import (
    RecoveryExecutionError,
    RecoveryExecutionResult,
    execute_recovery,
)

__all__ = [
    "RecoveryExecutionError",
    "RecoveryExecutionResult",
    "build_recovery_request",
    "build_failure",
    "execute_recovery",
    "validate_recovery_request",
]

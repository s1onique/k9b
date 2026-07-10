"""Cursor persistence for automatic diagnosis loop.

This module provides cursor-based pagination to ensure fair queuing:
- Incidents are never permanently starved behind repeatedly selected items
- The next run resumes from where the previous run left off

Cursor file format: JSON with cursor token and schema version.
Cursor file is stored under runs/state/ to avoid being misclassified as an artifact.

Schema Versions:
- SchemaVersion 1: Legacy format with last_incident_id (deprecated)
- SchemaVersion 2: Current format with opaque cursor token

Algebraic Results:
- load_scan_cursor() returns ScanCursorLoadResult (ScanCursorAbsent|Loaded|Reset|ReadDegraded)
- save_scan_cursor() returns CursorPersistenceResult (Succeeded|Degraded)
- clear_scan_cursor() returns CursorPersistenceResult (Succeeded|Degraded)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .incident_diagnosis_cursor_persistence import (
    CursorPersistenceDegraded,
    CursorPersistenceOperation,
    CursorPersistenceResult,
    CursorPersistenceSucceeded,
    CursorResetReason,
    ScanCursorAbsent,
    ScanCursorLoaded,
    ScanCursorLoadResult,
    ScanCursorReadDegraded,
    ScanCursorReset,
    ScanCursorResetDegraded,
)
from .incident_diagnosis_keyset_cursor import (
    CURSOR_SCHEMA_VERSION,
    CURSOR_STATE_SCHEMA_VERSION,
    LEGACY_CURSOR_STATE_SCHEMA_VERSION,
    decode_cursor,
)

if TYPE_CHECKING:
    from .incident_diagnosis_pagination_types import OpaqueCursorToken

_logger = logging.getLogger(__name__)

# Cursor file name for cursor-based pagination
# Stored under runs/state/ to avoid artifact discovery in external-analysis/
_SCAN_CURSOR_FILE = "auto-loop-scan-cursor.json"


def _get_cursor_path(runs_dir: Path) -> Path:
    """Get the cursor file path.

    The runs_dir should be the runs/ directory at the repo root, NOT
    external_analysis_dir. The cursor is stored under:
        {runs_dir}/state/automatic-diagnosis/scan-cursor.json

    Args:
        runs_dir: Path to the runs/ directory at repo root

    Returns:
        Path to the cursor file
    """
    return runs_dir / "state" / "automatic-diagnosis" / _SCAN_CURSOR_FILE


def load_scan_cursor(runs_dir: Path) -> ScanCursorLoadResult:
    """Load the persisted scan cursor from file.

    Returns algebraic result:
    - ScanCursorAbsent: No cursor file exists
    - ScanCursorLoaded: Valid cursor token loaded
    - ScanCursorReset: Legacy/invalid state cleared successfully
    - ScanCursorReadDegraded: File system or cleanup failure

    Legacy format (SchemaVersion 1) is detected and triggers a reset.
    """
    cursor_file = _get_cursor_path(runs_dir)

    try:
        if not cursor_file.exists():
            return ScanCursorAbsent()

        with open(cursor_file) as f:
            data = json.load(f)

        # Check schema version
        schema_version = data.get("schemaVersion")

        # Handle missing schemaVersion (legacy format)
        if schema_version is None:
            # Legacy format - extract last_incident_id
            last_id: str | None = data.get("last_incident_id")
            if last_id:
                _logger.info(
                    "scan-cursor-legacy-reset",
                    extra={
                        "event": "scan-cursor-legacy-reset",
                        "cursor_incident_id": last_id,
                        "reason": "legacy_format_detected",
                    },
                )
                # Clear legacy cursor and check result
                clear_result = clear_scan_cursor(runs_dir)
                match clear_result:
                    case CursorPersistenceSucceeded():
                        return ScanCursorReset(
                            reason=CursorResetReason.LEGACY_FORMAT,
                            observed_schema_version=None,
                        )
                    case CursorPersistenceDegraded(operation=op, message=msg):
                        return ScanCursorResetDegraded(
                            reason=CursorResetReason.LEGACY_FORMAT,
                            observed_schema_version=None,
                            clear_operation=op.value,
                            persistence_error=msg,
                        )
            return ScanCursorAbsent()

        # Handle legacy schema version
        if schema_version == LEGACY_CURSOR_STATE_SCHEMA_VERSION:
            # Legacy schema version - clear and restart
            last_id = data.get("last_incident_id")
            if last_id:
                _logger.info(
                    "scan-cursor-legacy-reset",
                    extra={
                        "event": "scan-cursor-legacy-reset",
                        "cursor_incident_id": last_id,
                        "reason": "legacy_state_schema",
                    },
                )
            clear_result = clear_scan_cursor(runs_dir)
            match clear_result:
                case CursorPersistenceSucceeded():
                    return ScanCursorReset(
                        reason=CursorResetReason.LEGACY_STATE_SCHEMA,
                        observed_schema_version=schema_version,
                    )
                case CursorPersistenceDegraded(operation=op, message=msg):
                    return ScanCursorResetDegraded(
                        reason=CursorResetReason.LEGACY_STATE_SCHEMA,
                        observed_schema_version=schema_version,
                        clear_operation=op.value,
                        persistence_error=msg,
                    )

        # Handle unknown schema version
        if schema_version != CURSOR_STATE_SCHEMA_VERSION:
            _logger.info(
                "scan-cursor-unknown-version-reset",
                extra={
                    "event": "scan-cursor-unknown-version-reset",
                    "schema_version": schema_version,
                },
            )
            clear_result = clear_scan_cursor(runs_dir)
            match clear_result:
                case CursorPersistenceSucceeded():
                    return ScanCursorReset(
                        reason=CursorResetReason.UNKNOWN_STATE_SCHEMA,
                        observed_schema_version=schema_version,
                    )
                case CursorPersistenceDegraded(operation=op, message=msg):
                    return ScanCursorResetDegraded(
                        reason=CursorResetReason.UNKNOWN_STATE_SCHEMA,
                        observed_schema_version=schema_version,
                        clear_operation=op.value,
                        persistence_error=msg,
                    )

        # Schema version matches - validate cursor token
        cursor_token = data.get("cursor")

        # Validate cursor is a non-empty string
        if not isinstance(cursor_token, str) or not cursor_token:
            _logger.info(
                "scan-cursor-invalid-field-reset",
                extra={
                    "event": "scan-cursor-invalid-field-reset",
                    "reason": "invalid_cursor_field",
                },
            )
            clear_result = clear_scan_cursor(runs_dir)
            match clear_result:
                case CursorPersistenceSucceeded():
                    return ScanCursorReset(
                        reason=CursorResetReason.INVALID_CURSOR_FIELD,
                        observed_schema_version=schema_version,
                    )
                case CursorPersistenceDegraded(operation=op, message=msg):
                    return ScanCursorResetDegraded(
                        reason=CursorResetReason.INVALID_CURSOR_FIELD,
                        observed_schema_version=schema_version,
                        clear_operation=op.value,
                        persistence_error=msg,
                    )

        # Decode and validate the token
        _, cursor_error = decode_cursor(cursor_token)
        if cursor_error is not None:
            _logger.info(
                "scan-cursor-decode-error-reset",
                extra={
                    "event": "scan-cursor-decode-error-reset",
                    "reason": f"invalid_cursor_{cursor_error.kind}",
                    "error_message": cursor_error.message,
                },
            )
            clear_result = clear_scan_cursor(runs_dir)
            # Determine specific reset reason based on error kind
            reset_reason = (
                CursorResetReason.UNSUPPORTED_CURSOR_VERSION
                if cursor_error.kind == "unsupported_version"
                else CursorResetReason.INVALID_CURSOR_TOKEN
            )
            match clear_result:
                case CursorPersistenceSucceeded():
                    return ScanCursorReset(
                        reason=reset_reason,
                        observed_schema_version=schema_version,
                    )
                case CursorPersistenceDegraded(operation=op, message=msg):
                    return ScanCursorResetDegraded(
                        reason=reset_reason,
                        observed_schema_version=schema_version,
                        clear_operation=op.value,
                        persistence_error=msg,
                    )

        # Success - return loaded cursor
        from .incident_diagnosis_pagination_types import OpaqueCursorToken
        return ScanCursorLoaded(token=OpaqueCursorToken(cursor_token))

    except json.JSONDecodeError:
        # Corrupted JSON file
        _logger.info(
            "scan-cursor-corrupted-reset",
            extra={
                "event": "scan-cursor-corrupted-reset",
                "reason": "corrupted_state_file",
            },
        )
        clear_result = clear_scan_cursor(runs_dir)
        match clear_result:
            case CursorPersistenceSucceeded():
                return ScanCursorReset(
                    reason=CursorResetReason.CORRUPTED_STATE_FILE,
                    observed_schema_version=None,
                )
            case CursorPersistenceDegraded(operation=op, message=msg):
                return ScanCursorResetDegraded(
                    reason=CursorResetReason.CORRUPTED_STATE_FILE,
                    observed_schema_version=None,
                    clear_operation=op.value,
                    persistence_error=msg,
                )

    except OSError as e:
        # File system error - degraded but recoverable
        _logger.warning(
            "scan-cursor-read-degraded",
            extra={
                "event": "scan-cursor-read-degraded",
                "error": str(e),
            },
        )
        return ScanCursorReadDegraded(message=str(e))


def save_scan_cursor(
    runs_dir: Path,
    token: OpaqueCursorToken,  # noqa: UP037
) -> CursorPersistenceResult:
    """Persist the scan cursor to file (crash-safe).

    Stores the opaque cursor token so the next run can resume after the last page.
    Uses os.replace() for atomic write on POSIX systems.
    This ensures fair queuing: incidents are never permanently starved.

    Cursor format (SchemaVersion 2):
    {
        "schemaVersion": 2,
        "cursor": "opaque-token",
        "savedAt": "2026-07-10T08:00:00+00:00"
    }

    Returns algebraic result:
    - CursorPersistenceSucceeded: Write completed
    - CursorPersistenceDegraded: Write failed but loop can continue
    """
    cursor_file = _get_cursor_path(runs_dir)

    try:
        # Ensure directory exists and write atomically
        cursor_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=cursor_file.parent,
            prefix=".cursor_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({
                    "schemaVersion": CURSOR_STATE_SCHEMA_VERSION,
                    "cursor": token,
                    "savedAt": datetime.now(UTC).isoformat(),
                }, f)
            # Atomic replace on POSIX - documented as atomic on success
            os.replace(tmp_path, cursor_file)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return CursorPersistenceSucceeded()

    except Exception as e:
        # Catch all exceptions including permission errors and filesystem issues
        # The diagnosis loop should continue even if cursor persistence fails
        _logger.warning(
            "Failed to persist scan cursor",
            extra={
                "event": "scan-cursor-persist-failed",
                "error": str(e),
            },
        )
        return CursorPersistenceDegraded(
            operation=CursorPersistenceOperation.SAVE,
            message=str(e),
        )


def clear_scan_cursor(runs_dir: Path) -> CursorPersistenceResult:
    """Clear the persisted scan cursor.

    Called when we've completed a full scan cycle (no more incidents to process).

    Returns algebraic result:
    - CursorPersistenceSucceeded: Clear completed
    - CursorPersistenceDegraded: Clear failed but loop can continue
    """
    cursor_file = _get_cursor_path(runs_dir)

    try:
        if cursor_file.exists():
            cursor_file.unlink()
        return CursorPersistenceSucceeded()
    except OSError as e:
        _logger.warning(
            "Failed to clear scan cursor",
            extra={
                "event": "scan-cursor-clear-failed",
                "error": str(e),
            },
        )
        return CursorPersistenceDegraded(
            operation=CursorPersistenceOperation.CLEAR,
            message=str(e),
        )


# Legacy exports for backward compatibility during transition
def _load_scan_cursor(runs_dir: Path) -> tuple[str | None, str | None]:
    """Legacy wrapper for backward compatibility.

    DEPRECATED: Use load_scan_cursor() which returns ScanCursorLoadResult.

    Returns tuple (token, reset_reason) for compatibility.
    """
    result = load_scan_cursor(runs_dir)

    match result:
        case ScanCursorAbsent():
            return None, None
        case ScanCursorLoaded(token=token):
            return token, None
        case ScanCursorReset(reason=reason):
            return None, reason.value
        case ScanCursorResetDegraded(reason=reason, persistence_error=err):
            _logger.warning(
                "scan-cursor-reset-degraded",
                extra={
                    "event": "scan-cursor-reset-degraded",
                    "reason": reason.value,
                    "persistence_error": err,
                },
            )
            return None, reason.value  # Treat degraded as reset for backward compat
        case ScanCursorReadDegraded(message=message):
            _logger.warning(
                "scan-cursor-read-degraded",
                extra={
                    "event": "scan-cursor-read-degraded",
                    "message": message,
                },
            )
            return None, None  # Treat degraded as absent for backward compat


def _save_scan_cursor(runs_dir: Path, cursor_token: str) -> None:
    """Legacy wrapper for backward compatibility.

    DEPRECATED: Use save_scan_cursor() which returns CursorPersistenceResult.
    """
    from .incident_diagnosis_pagination_types import OpaqueCursorToken
    save_scan_cursor(runs_dir, OpaqueCursorToken(cursor_token))
    # Ignore result for backward compat


def _clear_scan_cursor(runs_dir: Path) -> None:
    """Legacy wrapper for backward compatibility.

    DEPRECATED: Use clear_scan_cursor() which returns CursorPersistenceResult.
    """
    clear_scan_cursor(runs_dir)
    # Ignore result for backward compat


__all__ = [
    "load_scan_cursor",
    "save_scan_cursor",
    "clear_scan_cursor",
    "CURSOR_SCHEMA_VERSION",
    # Legacy exports
    "_clear_scan_cursor",
    "_load_scan_cursor",
    "_save_scan_cursor",
]

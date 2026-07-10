"""Keyset cursor for incident diagnosis pagination.

This module provides:
- IncidentDiagnosisCursor: Versioned cursor using (first_observed_at, incident_id)
- Cursor encoding/decoding with validation
- Cursor error classification

The cursor uses an immutable key (first_observed_at, incident_id) that does not
change when incidents are updated, unlike last_observed_at.

Branded types:
- OpaqueCursorToken: Serialized cursor token
- FirstObservedAtKey: Exact database ordering key
- DiagnosisIncidentId: Unique incident identifier
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_diagnosis_dispatch_contracts import DiagnosisPageIncident


_logger = logging.getLogger(__name__)


# =============================================================================
# Schema Version
# =============================================================================

# Current cursor schema version - increment when breaking changes occur
# v2: changed from reserialized datetime to exact database ordering key (R13)
CURSOR_SCHEMA_VERSION = 2

# Separate versions for token vs state schema
CURSOR_TOKEN_SCHEMA_VERSION = 2
CURSOR_STATE_SCHEMA_VERSION = 2
LEGACY_CURSOR_STATE_SCHEMA_VERSION = 1

# Maximum token length to prevent DoS
MAX_TOKEN_LENGTH = 2048

# Maximum incident ID length to prevent DoS
MAX_INCIDENT_ID_LENGTH = 256


# =============================================================================
# Cursor Dataclass
# =============================================================================


@dataclass(frozen=True, slots=True)
class IncidentDiagnosisCursor:
    """Versioned keyset cursor for incident diagnosis pagination.

    The cursor encodes a stable ordering key (first_observed_at_text, incident_id)
    stored as the EXACT text representation from the database. This ensures the
    cursor key matches the database ordering exactly, avoiding issues where
    datetime.isoformat() produces different text for equivalent timestamps
    (e.g., "Z" vs "+00:00" for UTC).

    Attributes:
        schema_version: Schema version for forward compatibility
        first_observed_at_text: EXACT text representation of first_observed_at from database
        incident_id: Unique incident identifier
    """

    schema_version: int
    first_observed_at_text: str  # Stored as text to match database ordering exactly
    incident_id: str


# =============================================================================
# Cursor Error Types
# =============================================================================


class CursorErrorKind:
    """Error kinds for cursor decoding failures."""

    INVALID_FORMAT = "invalid_format"
    UNSUPPORTED_VERSION = "unsupported_version"
    MISSING_FIELD = "missing_field"
    INVALID_TYPE = "invalid_type"
    NAIVE_TIMESTAMP = "naive_timestamp"
    TOKEN_TOO_LONG = "token_too_long"
    INCIDENT_ID_TOO_LONG = "incident_id_too_long"
    INCIDENT_ID_EMPTY = "incident_id_empty"
    DECODE_ERROR = "decode_error"


@dataclass(frozen=True, slots=True)
class CursorDecodeError:
    """Structured error from cursor decoding.

    Attributes:
        kind: Error kind from CursorErrorKind
        message: Human-readable error message
        field: Optional field name that caused the error
    """

    kind: str
    message: str
    field: str | None = None


# =============================================================================
# Cursor Encoding/Decoding
# =============================================================================


def encode_cursor(cursor: IncidentDiagnosisCursor) -> str:
    """Encode a cursor to an opaque URL-safe token.

    The token format is versioned to allow future schema changes.

    Args:
        cursor: The cursor to encode

    Returns:
        URL-safe base64-encoded token
    """
    # R10: Use first_observed_at_text (exact database text) for cursor key
    payload = {
        "v": cursor.schema_version,
        "ts": cursor.first_observed_at_text,
        "id": cursor.incident_id,
    }
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).decode("ascii")


def decode_cursor(token: str) -> tuple[IncidentDiagnosisCursor | None, CursorDecodeError | None]:
    """Decode an opaque cursor token.

    This function validates:
    - Token length is within bounds
    - Token is valid base64 (STRICT validation)
    - Token is valid JSON
    - Schema version is supported
    - All required fields are present with correct types
    - Timestamp is timezone-aware
    - Incident ID length is within bounds

    Args:
        token: URL-safe base64-encoded cursor token

    Returns:
        Tuple of (cursor, None) on success, or (None, error) on failure
    """
    # Check token length first to prevent DoS
    if len(token) > MAX_TOKEN_LENGTH:
        return None, CursorDecodeError(
            kind=CursorErrorKind.TOKEN_TOO_LONG,
            message=f"Token exceeds maximum length of {MAX_TOKEN_LENGTH}",
            field="token",
        )

    try:
        # Decode base64 - use STRICT validation
        # Use b64decode with validate=True and altchars for URL-safe encoding
        # This rejects any non-base64 characters before the padding check
        try:
            # b64decode with validate=True rejects invalid characters
            # altchars handles URL-safe base64 (+/ → -_)
            json_bytes = base64.b64decode(
                token.encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
        except Exception:
            return None, CursorDecodeError(
                kind=CursorErrorKind.INVALID_FORMAT,
                message="Token is not valid base64",
                field="token",
            )

        # Parse JSON
        try:
            data = json.loads(json_bytes.decode("utf-8"))
        except Exception:
            return None, CursorDecodeError(
                kind=CursorErrorKind.INVALID_FORMAT,
                message="Token is not valid JSON",
                field="token",
            )

        # Validate data is a dict
        if not isinstance(data, dict):
            return None, CursorDecodeError(
                kind=CursorErrorKind.INVALID_TYPE,
                message=f"Expected object, got {type(data).__name__}",
                field=None,
            )

        # Check schema version
        schema_version = data.get("v")
        if schema_version is None:
            return None, CursorDecodeError(
                kind=CursorErrorKind.MISSING_FIELD,
                message="Missing schema version",
                field="v",
            )

        # Use type() check to reject bool (bool is subclass of int in Python)
        if type(schema_version) is not int:
            return None, CursorDecodeError(
                kind=CursorErrorKind.INVALID_TYPE,
                message=f"Schema version must be int, got {type(schema_version).__name__}",
                field="v",
            )

        if schema_version != CURSOR_SCHEMA_VERSION:
            return None, CursorDecodeError(
                kind=CursorErrorKind.UNSUPPORTED_VERSION,
                message=f"Unsupported cursor version {schema_version}, expected {CURSOR_SCHEMA_VERSION}",
                field="v",
            )

        # Check timestamp field
        ts_value = data.get("ts")
        if ts_value is None:
            return None, CursorDecodeError(
                kind=CursorErrorKind.MISSING_FIELD,
                message="Missing timestamp",
                field="ts",
            )

        if not isinstance(ts_value, str):
            return None, CursorDecodeError(
                kind=CursorErrorKind.INVALID_TYPE,
                message=f"Timestamp must be string, got {type(ts_value).__name__}",
                field="ts",
            )

        # Parse and validate timestamp
        try:
            dt = datetime.fromisoformat(ts_value)
        except ValueError:
            return None, CursorDecodeError(
                kind=CursorErrorKind.INVALID_FORMAT,
                message="Invalid ISO timestamp format",
                field="ts",
            )

        # Check timezone awareness
        if dt.tzinfo is None:
            return None, CursorDecodeError(
                kind=CursorErrorKind.NAIVE_TIMESTAMP,
                message="Timestamp must be timezone-aware",
                field="ts",
            )

        # Check incident ID field
        incident_id = data.get("id")
        if incident_id is None:
            return None, CursorDecodeError(
                kind=CursorErrorKind.MISSING_FIELD,
                message="Missing incident ID",
                field="id",
            )

        if not isinstance(incident_id, str):
            return None, CursorDecodeError(
                kind=CursorErrorKind.INVALID_TYPE,
                message=f"Incident ID must be string, got {type(incident_id).__name__}",
                field="id",
            )

        if len(incident_id) > MAX_INCIDENT_ID_LENGTH:
            return None, CursorDecodeError(
                kind=CursorErrorKind.INCIDENT_ID_TOO_LONG,
                message=f"Incident ID exceeds maximum length of {MAX_INCIDENT_ID_LENGTH}",
                field="id",
            )

        # R10: Reject empty incident IDs
        if not incident_id:
            return None, CursorDecodeError(
                kind=CursorErrorKind.INCIDENT_ID_EMPTY,
                message="Incident ID must not be empty",
                field="id",
            )

        # R10: Store both datetime (for API) and text (for cursor key)
        return IncidentDiagnosisCursor(
            schema_version=schema_version,
            first_observed_at_text=ts_value,  # Store exact text for cursor key
            incident_id=incident_id,
        ), None

    except Exception as e:
        _logger.warning(
            "Unexpected cursor decode error",
            extra={
                "event": "cursor-decode-error",
                "error": str(e),
            },
        )
        return None, CursorDecodeError(
            kind=CursorErrorKind.DECODE_ERROR,
            message=f"Failed to decode cursor: {e}",
            field=None,
        )


# =============================================================================
# Page Limit Type
# =============================================================================


# Maximum allowed page limit for diagnosis
MAX_DIAGNOSIS_PAGE_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class DiagnosisPageLimit:
    """Validated page limit for diagnosis pagination.

    Attributes:
        value: The page limit value (1 to MAX_DIAGNOSIS_PAGE_LIMIT)

    Raises:
        TypeError: If value is not an integer (rejects booleans explicitly)
        ValueError: If value is out of valid range
    """

    value: int

    def __post_init__(self) -> None:
        # Use type() check to reject booleans explicitly (bool is subclass of int in Python)
        if type(self.value) is not int:
            raise TypeError(
                f"page limit must be an integer, got {type(self.value).__name__}"
            )
        if self.value < 1:
            raise ValueError("page limit must be positive")
        if self.value > MAX_DIAGNOSIS_PAGE_LIMIT:
            raise ValueError(f"page limit exceeds maximum of {MAX_DIAGNOSIS_PAGE_LIMIT}")


# =============================================================================
# Safe Cursor Construction
# =============================================================================


def cursor_after_page_incident(
    incident: DiagnosisPageIncident,
) -> IncidentDiagnosisCursor:
    """Create a cursor from a page incident.

    This is the PREFERRED way to create cursors - it guarantees the
    first_observed_at_key matches the database ordering exactly.

    Args:
        incident: A DiagnosisPageIncident from a page

    Returns:
        IncidentDiagnosisCursor with schema version
    """
    return IncidentDiagnosisCursor(
        schema_version=CURSOR_SCHEMA_VERSION,
        first_observed_at_text=incident.first_observed_at_key,
        incident_id=incident.incident_id,
    )


def make_cursor(
    first_observed_at: datetime,
    incident_id: str,
    first_observed_at_text: str | None = None,
) -> IncidentDiagnosisCursor:
    """Create a new cursor with the current schema version.

    DEPRECATED: Use cursor_after_page_incident() when possible.
    This function is kept for backward compatibility with tests.

    Args:
        first_observed_at: When the incident was first observed (for API use)
        incident_id: Unique incident identifier
        first_observed_at_text: EXACT database text for cursor key

    Returns:
        IncidentDiagnosisCursor with current schema version
    """
    # Require exact text - do not fall back to isoformat
    if first_observed_at_text is None:
        raise ValueError(
            "first_observed_at_text is required for cursor creation. "
            "Use cursor_after_page_incident() instead."
        )
    return IncidentDiagnosisCursor(
        schema_version=CURSOR_SCHEMA_VERSION,
        first_observed_at_text=first_observed_at_text,
        incident_id=incident_id,
    )


def make_test_cursor(
    first_observed_at_text: str,
    incident_id: str,
) -> IncidentDiagnosisCursor:
    """Create a cursor for testing purposes only.

    This function should ONLY be used in tests, never in production code.
    It allows creating cursors with arbitrary text for testing edge cases.

    Args:
        first_observed_at_text: EXACT timestamp text
        incident_id: Incident ID

    Returns:
        IncidentDiagnosisCursor with current schema version
    """
    return IncidentDiagnosisCursor(
        schema_version=CURSOR_SCHEMA_VERSION,
        first_observed_at_text=first_observed_at_text,
        incident_id=incident_id,
    )


__all__ = [
    "CURSOR_SCHEMA_VERSION",
    "CURSOR_TOKEN_SCHEMA_VERSION",
    "CURSOR_STATE_SCHEMA_VERSION",
    "LEGACY_CURSOR_STATE_SCHEMA_VERSION",
    "MAX_TOKEN_LENGTH",
    "MAX_INCIDENT_ID_LENGTH",
    "MAX_DIAGNOSIS_PAGE_LIMIT",
    "DiagnosisPageLimit",
    "IncidentDiagnosisCursor",
    "CursorErrorKind",
    "CursorDecodeError",
    "encode_cursor",
    "decode_cursor",
    "cursor_after_page_incident",
    "make_cursor",
    "make_test_cursor",
]

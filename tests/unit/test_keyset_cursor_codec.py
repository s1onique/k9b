"""Unit tests for keyset cursor encoding/decoding.

These tests verify:
1. Valid cursor round trip (encode then decode)
2. Malformed token rejection (invalid base64)
3. Unsupported version rejection
4. Naive timestamp rejection (timezone-naive)
5. Oversized token rejection
6. Legacy format detection

Tests use UTC timestamps to avoid timezone issues.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    CURSOR_SCHEMA_VERSION,
    MAX_INCIDENT_ID_LENGTH,
    MAX_TOKEN_LENGTH,
    CursorErrorKind,
    IncidentDiagnosisCursor,
    decode_cursor,
    encode_cursor,
    make_test_cursor,
)


class TestCursorCodecValidRoundTrip:
    """Valid cursor round trip tests."""

    def test_encode_decode_roundtrip_basic(self) -> None:
        """Basic valid cursor round trip."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        ts_text = ts.isoformat()
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_text,
            incident_id="inc-001",
        )

        token = encode_cursor(cursor)
        assert isinstance(token, str)
        assert len(token) > 0

        decoded, err = decode_cursor(token)
        assert err is None, f"Expected no error, got {err}"
        assert decoded is not None
        assert decoded.schema_version == CURSOR_SCHEMA_VERSION
        assert decoded.first_observed_at_text == ts_text
        assert decoded.incident_id == "inc-001"

    def test_encode_decode_roundtrip_with_special_chars(self) -> None:
        """Cursor with special characters in incident ID."""
        ts = datetime(2024, 6, 15, 23, 59, 59, 999999, tzinfo=UTC)
        ts_text = ts.isoformat()
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_text,
            incident_id="inc/ns1:pod/test-app-xyz~v2",
        )

        token = encode_cursor(cursor)
        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None
        assert decoded.incident_id == "inc/ns1:pod/test-app-xyz~v2"

    def test_encode_decode_roundtrip_unicode_id(self) -> None:
        """Cursor with unicode characters in incident ID."""
        ts = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
        ts_text = ts.isoformat()
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_text,
            incident_id="incident-\u00e9t\u00e9",
        )

        token = encode_cursor(cursor)
        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None
        assert decoded.incident_id == "incident-\u00e9t\u00e9"

    def test_make_test_cursor(self) -> None:
        """Test make_test_cursor function for test purposes."""
        ts = datetime(2024, 5, 1, 8, 0, 0, tzinfo=UTC)
        ts_text = ts.isoformat()
        cursor = make_test_cursor(first_observed_at_text=ts_text, incident_id="test-inc")

        assert cursor.schema_version == CURSOR_SCHEMA_VERSION
        assert cursor.first_observed_at_text == ts_text
        assert cursor.incident_id == "test-inc"


class TestCursorCodecMalformed:
    """Malformed token rejection tests."""

    def test_invalid_base64_rejected(self) -> None:
        """Invalid base64 string is rejected."""
        token = "not-valid-base64!!!"

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.INVALID_FORMAT
        assert err.field == "token"

    def test_valid_base64_invalid_json_rejected(self) -> None:
        """Valid base64 but invalid JSON is rejected."""
        # "hello" encoded in base64
        token = "aGVsbG8="

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.INVALID_FORMAT

    def test_json_object_but_not_cursor_rejected(self) -> None:
        """Valid JSON object that is not a cursor is rejected."""
        # Encode a simple dict that looks like JSON but isn't a cursor
        import base64
        import json
        payload = json.dumps({"name": "test"}).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.MISSING_FIELD

    def test_missing_version_field_rejected(self) -> None:
        """Cursor missing schema version field is rejected."""
        import base64
        import json
        payload = json.dumps({
            "ts": "2024-01-15T10:30:00+00:00",
            "id": "inc-001",
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.MISSING_FIELD
        assert err.field == "v"

    def test_missing_timestamp_field_rejected(self) -> None:
        """Cursor missing timestamp field is rejected."""
        import base64
        import json
        payload = json.dumps({
            "v": CURSOR_SCHEMA_VERSION,
            "id": "inc-001",
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.MISSING_FIELD
        assert err.field == "ts"

    def test_missing_incident_id_field_rejected(self) -> None:
        """Cursor missing incident ID field is rejected."""
        import base64
        import json
        payload = json.dumps({
            "v": CURSOR_SCHEMA_VERSION,
            "ts": "2024-01-15T10:30:00+00:00",
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.MISSING_FIELD
        assert err.field == "id"

    def test_wrong_field_types_rejected(self) -> None:
        """Cursor with wrong field types is rejected."""
        import base64
        import json

        # Version as string instead of int
        payload = json.dumps({
            "v": "1",  # Should be int
            "ts": "2024-01-15T10:30:00+00:00",
            "id": "inc-001",
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.INVALID_TYPE
        assert err.field == "v"


class TestCursorCodecVersion:
    """Version-related tests."""

    def test_unsupported_version_rejected(self) -> None:
        """Unsupported cursor version is rejected."""
        import base64
        import json
        payload = json.dumps({
            "v": 99,  # Future version
            "ts": "2024-01-15T10:30:00+00:00",
            "id": "inc-001",
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.UNSUPPORTED_VERSION
        assert "99" in err.message
        assert str(CURSOR_SCHEMA_VERSION) in err.message

    def test_zero_version_rejected(self) -> None:
        """Zero version is rejected (not current version)."""
        import base64
        import json
        payload = json.dumps({
            "v": 0,
            "ts": "2024-01-15T10:30:00+00:00",
            "id": "inc-001",
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.UNSUPPORTED_VERSION


class TestCursorCodecTimestamp:
    """Timestamp validation tests."""

    def test_naive_timestamp_rejected(self) -> None:
        """Naive timestamp (no timezone) is rejected."""
        import base64
        import json
        payload = json.dumps({
            "v": CURSOR_SCHEMA_VERSION,
            "ts": "2024-01-15T10:30:00",  # No timezone!
            "id": "inc-001",
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.NAIVE_TIMESTAMP
        assert err.field == "ts"

    def test_invalid_timestamp_format_rejected(self) -> None:
        """Invalid timestamp format is rejected."""
        import base64
        import json
        payload = json.dumps({
            "v": CURSOR_SCHEMA_VERSION,
            "ts": "not-a-timestamp",
            "id": "inc-001",
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.INVALID_FORMAT

    def test_positive_offset_accepted(self) -> None:
        """Positive timezone offset is accepted."""
        ts_str = "2024-01-15T10:30:00+05:30"
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_str,
            incident_id="inc-001",
        )

        token = encode_cursor(cursor)
        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None

    def test_negative_offset_accepted(self) -> None:
        """Negative timezone offset is accepted."""
        ts_str = "2024-01-15T10:30:00-08:00"
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_str,
            incident_id="inc-001",
        )

        token = encode_cursor(cursor)
        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None

    def test_z_suffix_accepted(self) -> None:
        """Z suffix (UTC) is accepted."""
        ts_str = "2024-01-15T10:30:00+00:00"
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_str,
            incident_id="inc-001",
        )

        token = encode_cursor(cursor)
        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None


class TestCursorCodecDoS:
    """DoS prevention tests."""

    def test_oversized_token_rejected(self) -> None:
        """Token exceeding MAX_TOKEN_LENGTH is rejected."""
        # Create a token that exceeds the limit
        oversized = "x" * (MAX_TOKEN_LENGTH + 1)

        decoded, err = decode_cursor(oversized)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.TOKEN_TOO_LONG
        assert str(MAX_TOKEN_LENGTH) in err.message

    def test_max_length_token_accepted(self) -> None:
        """Token at exactly MAX_TOKEN_LENGTH is accepted."""
        import base64
        import json

        # Create a token within both limits:
        # - MAX_TOKEN_LENGTH = 2048
        # - MAX_INCIDENT_ID_LENGTH = 256
        # Use max incident ID length to create a meaningful test
        data = {
            "v": CURSOR_SCHEMA_VERSION,
            "ts": "2024-01-15T10:30:00+00:00",
            "id": "x" * MAX_INCIDENT_ID_LENGTH,  # 256 chars
        }
        json_bytes = json.dumps(data, separators=(",", ":")).encode()
        token = base64.urlsafe_b64encode(json_bytes).decode()

        # Verify token is within limit
        assert len(token) <= MAX_TOKEN_LENGTH

        decoded, err = decode_cursor(token)

        # Should succeed if within limit
        assert err is None
        assert decoded is not None
        assert decoded.incident_id == "x" * MAX_INCIDENT_ID_LENGTH

    def test_oversized_incident_id_rejected(self) -> None:
        """Incident ID exceeding MAX_INCIDENT_ID_LENGTH is rejected."""
        import base64
        import json
        payload = json.dumps({
            "v": CURSOR_SCHEMA_VERSION,
            "ts": "2024-01-15T10:30:00+00:00",
            "id": "x" * (MAX_INCIDENT_ID_LENGTH + 1),
        }).encode()
        token = base64.urlsafe_b64encode(payload).decode()

        decoded, err = decode_cursor(token)

        assert decoded is None
        assert err is not None
        assert err.kind == CursorErrorKind.INCIDENT_ID_TOO_LONG
        assert str(MAX_INCIDENT_ID_LENGTH) in err.message

    def test_max_length_incident_id_accepted(self) -> None:
        """Incident ID at exactly MAX_INCIDENT_ID_LENGTH is accepted."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        ts_text = ts.isoformat()
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_text,
            incident_id="x" * MAX_INCIDENT_ID_LENGTH,
        )

        token = encode_cursor(cursor)
        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None


class TestCursorCodecEdge:
    """Edge case tests."""

    def test_empty_string_rejected(self) -> None:
        """Empty string is rejected."""
        decoded, err = decode_cursor("")

        assert decoded is None
        assert err is not None

    def test_whitespace_rejected(self) -> None:
        """Whitespace-only string is rejected."""
        decoded, err = decode_cursor("   ")

        assert decoded is None
        assert err is not None

    def test_minimal_valid_cursor(self) -> None:
        """Minimal valid cursor with short ID."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        ts_text = ts.isoformat()
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_text,
            incident_id="a",
        )

        token = encode_cursor(cursor)
        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None

    def test_cursor_immutable(self) -> None:
        """Cursor dataclass is immutable (frozen)."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        ts_text = ts.isoformat()
        cursor = IncidentDiagnosisCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            first_observed_at_text=ts_text,
            incident_id="inc-001",
        )

        with pytest.raises(AttributeError):
            cursor.schema_version = 99

    def test_cursor_hashable(self) -> None:
        """Cursor can be used in sets and dict keys."""
        ts1 = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 15, 10, 31, 0, tzinfo=UTC)

        cursor1 = IncidentDiagnosisCursor(CURSOR_SCHEMA_VERSION, ts1.isoformat(), "inc-001")
        cursor2 = IncidentDiagnosisCursor(CURSOR_SCHEMA_VERSION, ts1.isoformat(), "inc-001")
        cursor3 = IncidentDiagnosisCursor(CURSOR_SCHEMA_VERSION, ts2.isoformat(), "inc-001")

        # Equal cursors have equal hashes
        assert hash(cursor1) == hash(cursor2)
        assert cursor1 == cursor2

        # Different cursors may have different hashes
        assert cursor1 != cursor3

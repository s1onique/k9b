"""R6.1: Cursor validation and self-healing tests.

These tests verify that invalid persisted cursors are detected and self-healed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor import (
    _load_scan_cursor,
    _save_scan_cursor,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    decode_cursor,
    encode_cursor,
    make_test_cursor,
)


@pytest.fixture
def temp_runs_dir(tmp_path: Path) -> Path:
    """Create a temporary runs directory."""
    return tmp_path / "runs"


class TestCursorSelfHealing:
    """R6.1: Tests for cursor self-healing on invalid persisted cursors."""

    def test_invalid_cursor_token_triggers_reset(self, temp_runs_dir: Path) -> None:
        """Invalid cursor token (not base64 or malformed) triggers reset."""
        # Create a cursor file with invalid token (not base64)
        cursor_file = temp_runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        cursor_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cursor_file, "w") as f:
            json.dump({
                "schemaVersion": 2,
                "cursor": "not-a-valid-base64-token!@#$",
                "savedAt": "2026-07-10T00:00:00+00:00",
            }, f)

        # Load should detect invalid token and reset
        loaded_token, reset_reason = _load_scan_cursor(temp_runs_dir)

        assert loaded_token is None
        assert reset_reason is not None
        assert "invalid_cursor" in reset_reason

    def test_missing_cursor_field_triggers_reset(self, temp_runs_dir: Path) -> None:
        """Missing cursor field triggers reset."""
        cursor_file = temp_runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        cursor_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cursor_file, "w") as f:
            json.dump({
                "schemaVersion": 2,
                "savedAt": "2026-07-10T00:00:00+00:00",
            }, f)

        # Load should detect missing cursor and reset
        loaded_token, reset_reason = _load_scan_cursor(temp_runs_dir)

        assert loaded_token is None
        assert reset_reason == "invalid_cursor_field"

    def test_empty_cursor_field_triggers_reset(self, temp_runs_dir: Path) -> None:
        """Empty cursor field triggers reset."""
        cursor_file = temp_runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        cursor_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cursor_file, "w") as f:
            json.dump({
                "schemaVersion": 2,
                "cursor": "",
                "savedAt": "2026-07-10T00:00:00+00:00",
            }, f)

        # Load should detect empty cursor and reset
        loaded_token, reset_reason = _load_scan_cursor(temp_runs_dir)

        assert loaded_token is None
        assert reset_reason == "invalid_cursor_field"

    def test_valid_cursor_still_works(self, temp_runs_dir: Path) -> None:
        """Valid cursor token continues to work."""
        cursor = make_test_cursor(
            first_observed_at_text="2024-06-15T10:30:00+00:00",
            incident_id="incident-05",
        )
        token = encode_cursor(cursor)

        # Save cursor
        _save_scan_cursor(temp_runs_dir, token)

        # Load cursor
        loaded_token, reset_reason = _load_scan_cursor(temp_runs_dir)

        assert loaded_token == token
        assert reset_reason is None

        # Verify cursor can be decoded
        decoded, err = decode_cursor(loaded_token)
        assert err is None
        assert decoded.incident_id == "incident-05"

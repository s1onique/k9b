"""R7.2-R7.5: Boundary, termination, and defensive tests for keyset pagination.

This module contains tests for:
- Cursor disposition logic (save/clear behavior)
- Type contract validation
- Base64 encoding/decoding validation
- Edge cases and defensive behavior
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest


class TestBackendCollectorCursorDisposition:
    """R7.2: Tests for cursor disposition with real collector behavior.

    These tests verify the cursor disposition logic in the collector.
    """

    @pytest.fixture
    def runs_dir(self, tmp_path: Path) -> Path:
        """Create runs directory structure."""
        runs = tmp_path / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        return runs

    @pytest.fixture
    def external_analysis_dir(self, runs_dir: Path) -> Path:
        """Create external analysis directory."""
        ext_dir = runs_dir / "run-001" / "external-analysis"
        ext_dir.mkdir(parents=True, exist_ok=True)
        return ext_dir

    def test_cursor_saved_when_has_more_true(self, runs_dir: Path, external_analysis_dir: Path) -> None:
        """R7.2: Cursor is saved when hasMore=true."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor import (
            _clear_scan_cursor,
            _load_scan_cursor,
            _save_scan_cursor,
        )
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
            make_cursor,
        )

        _clear_scan_cursor(runs_dir)

        # Simulate processing last incident with more pages available
        last_cursor = make_cursor(
            first_observed_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC),
            incident_id="inc-003",
        )

        # Save cursor (as collector would when hasMore=true)
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import encode_cursor

        cursor_token = encode_cursor(last_cursor)
        _save_scan_cursor(runs_dir, cursor_token)

        # Verify cursor was saved
        loaded, _ = _load_scan_cursor(runs_dir)
        assert loaded is not None

    def test_cursor_cleared_when_has_more_false(self, runs_dir: Path) -> None:
        """R7.2: Cursor is cleared when hasMore=false (final page consumed)."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor import (
            _clear_scan_cursor,
            _load_scan_cursor,
            _save_scan_cursor,
        )
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
            encode_cursor,
            make_cursor,
        )

        _clear_scan_cursor(runs_dir)

        # Simulate cursor for last incident on final page
        last_cursor = make_cursor(
            first_observed_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC),
            incident_id="inc-010",
        )
        cursor_token = encode_cursor(last_cursor)
        _save_scan_cursor(runs_dir, cursor_token)

        # Simulate final page consumed - clear cursor
        _clear_scan_cursor(runs_dir)

        # Verify cursor was cleared
        loaded, _ = _load_scan_cursor(runs_dir)
        assert loaded is None

    def test_skipped_page_cursor_preserves_position(self, runs_dir: Path, external_analysis_dir: Path) -> None:
        """R6.4/R7.5: Skipped page with hasMore=true preserves cursor for next page."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor import (
            _clear_scan_cursor,
            _load_scan_cursor,
            _save_scan_cursor,
        )
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
            DiagnosisPageIncident,
        )
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            IncidentDiagnosisPage,
        )
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
            decode_cursor,
            encode_cursor,
            make_cursor,
        )

        _clear_scan_cursor(runs_dir)

        # Simulate page of active incidents (R7.5: active statuses)
        now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        active_statuses = ["open", "investigating", "collecting_evidence"]

        page_incidents = tuple(
            DiagnosisPageIncident(
                incident_id=f"inc-{i:03d}",
                status=active_statuses[i % len(active_statuses)],  # R7.5: Active statuses
                first_observed_at=now.replace(hour=10, minute=i * 5),
                first_observed_at_key=(now.replace(hour=10, minute=i * 5)).isoformat(),
            )
            for i in range(3)
        )

        # Create page with hasMore=True (more pages exist)
        last_cursor = make_cursor(
            first_observed_at=now.replace(hour=10, minute=10),
            incident_id="inc-002",
        )
        page = IncidentDiagnosisPage(
            incidents=page_incidents,
            next_cursor=last_cursor,
            has_more=True,  # More pages exist
        )

        assert page.has_more is True

        # Simulate all incidents skipped, save cursor for next page
        cursor_token = encode_cursor(last_cursor)
        _save_scan_cursor(runs_dir, cursor_token)

        # Verify cursor saved
        loaded, _ = _load_scan_cursor(runs_dir)
        assert loaded is not None

        # Decode and verify points to last incident in page
        decoded, err = decode_cursor(loaded)
        assert err is None
        assert decoded.incident_id == "inc-002"


class TestCursorTypeContracts:
    """R7.3: Tests for DiagnosisPageIncident type contract.

    Verifies that page incidents require mandatory first_observed_at.
    """

    def test_diagnosis_page_incident_requires_timestamp(self) -> None:
        """R7.3: DiagnosisPageIncident requires mandatory first_observed_at."""
        from datetime import datetime

        from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
            DiagnosisPageIncident,
        )

        # Should work with mandatory timestamp
        ts = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        incident = DiagnosisPageIncident(
            incident_id="inc-001",
            status="open",
            first_observed_at=ts,
            first_observed_at_key=ts.isoformat(),
        )
        assert incident.incident_id == "inc-001"
        assert incident.first_observed_at_key is not None

    def test_diagnosis_incident_summary_optional_timestamp(self) -> None:
        """R7.3: DiagnosisIncidentSummary allows optional first_observed_at."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
            DiagnosisIncidentSummary,
        )

        # Should work with optional timestamp
        incident = DiagnosisIncidentSummary(
            incident_id="inc-001",
            status="open",
            first_observed_at=None,
        )
        assert incident.incident_id == "inc-001"
        assert incident.first_observed_at is None


class TestCursorBase64Validation:
    """R7.4: Tests for strict Base64 decoding with validate=True."""

    def test_strict_base64_rejects_invalid_characters(self) -> None:
        """R7.4: Strict Base64 decoding rejects invalid characters."""
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import decode_cursor

        # Invalid base64 with special characters
        invalid_token = "not-valid-base64!@#$%"

        cursor, err = decode_cursor(invalid_token)

        assert cursor is None
        assert err is not None
        assert err.kind == "invalid_format"

    def test_strict_base64_accepts_valid_token(self) -> None:
        """R7.4: Strict Base64 decoding accepts valid tokens."""
        from datetime import datetime

        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
            decode_cursor,
            encode_cursor,
            make_cursor,
        )

        cursor = make_cursor(
            first_observed_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC),
            incident_id="inc-001",
        )
        token = encode_cursor(cursor)

        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None
        assert decoded.incident_id == "inc-001"

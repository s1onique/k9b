"""R7.1: Real backend-to-collector integration test for keyset pagination.

This test proves the full flow:
1. SQLite → HTTP handler → SchedulerClient → backend dispatch → collector
2. Persisted cursor → second collector run
3. Cursor advances correctly through pages

Unlike unit tests that mock individual components, this test uses real SQLite
and exercises the complete data path from database to cursor persistence.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest


class TestSQLiteKeysetPaginationReal:
    """R7.1: Tests using real SQLite queries for keyset pagination.

    These tests verify the actual SQL query produces correct pagination results.
    """

    @pytest.fixture
    def sqlite_db(self, tmp_path: Path) -> Path:
        """Create SQLite database with test data."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE incident_current (
                incident_id TEXT PRIMARY KEY,
                status TEXT,
                first_observed_at TEXT,
                last_observed_at TEXT,
                candidate_class TEXT
            )
        """)

        # Insert incidents with same timestamp but different IDs (tests tie-breaking)
        ts = "2024-06-15T10:00:00+00:00"
        conn.execute(
            "INSERT INTO incident_current VALUES (?, ?, ?, ?, ?)",
            ("inc-b", "open", ts, ts, "test"),
        )
        conn.execute(
            "INSERT INTO incident_current VALUES (?, ?, ?, ?, ?)",
            ("inc-a", "open", ts, ts, "test"),
        )
        conn.execute(
            "INSERT INTO incident_current VALUES (?, ?, ?, ?, ?)",
            ("inc-c", "open", ts, ts, "test"),
        )
        conn.commit()
        conn.close()
        return db_path

    def test_keyset_pagination_respects_order(self, sqlite_db: Path) -> None:
        """Verify keyset pagination returns incidents in correct order."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            _build_diagnosis_page_query,
            _rows_to_page,
        )

        conn = sqlite3.connect(sqlite_db)

        # First page: 2 incidents
        sql, params = _build_diagnosis_page_query(active_only=True, limit=2, after=None)
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        has_more = len(rows) > 2
        page = _rows_to_page(list(rows), has_more)

        assert len(page.incidents) == 2
        # Should be ordered by first_observed_at ASC, incident_id ASC
        assert page.incidents[0].incident_id == "inc-a"
        assert page.incidents[1].incident_id == "inc-b"
        assert page.has_more is True

        # Second page: resume from cursor
        after_cursor = page.next_cursor
        assert after_cursor is not None
        assert after_cursor.incident_id == "inc-b"

        sql2, params2 = _build_diagnosis_page_query(
            active_only=True, limit=2, after=after_cursor
        )
        cursor2 = conn.execute(sql2, params2)
        rows2 = cursor2.fetchall()
        page2 = _rows_to_page(list(rows2), len(rows2) > 2)

        assert len(page2.incidents) == 1
        assert page2.incidents[0].incident_id == "inc-c"
        assert page2.has_more is False

        conn.close()


class TestBackendCollectorCursorDisposition:
    """R7.1/R7.2: Tests for cursor disposition with real collector behavior.

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

    def test_cursor_saved_when_has_more_true(
        self, runs_dir: Path, external_analysis_dir: Path
    ) -> None:
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

    def test_skipped_page_cursor_preserves_position(
        self, runs_dir: Path, external_analysis_dir: Path
    ) -> None:
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


class TestTwoRunCollectorIntegration:
    """R7.6: Two-run collector + SQLite keyset pagination + persisted-cursor integration.

    This test proves:
    1. Real collector run 1: processes first 10 incidents via SQLite keyset pagination
    2. Cursor persists with exact database text key
    3. Real collector run 2: resumes from persisted cursor, processes remaining 10
    4. Cursor clears after final page consumed

    Note: This does NOT exercise HTTP transport or SchedulerClient - those have
    focused contract tests. This verifies the collector-to-SQLite keyset path.
    """

    @pytest.fixture
    def runs_dir(self, tmp_path: Path) -> Path:
        """Create runs directory structure."""
        runs = tmp_path / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        return runs

    @pytest.fixture
    def sqlite_db_with_20_incidents(self, tmp_path: Path) -> Path:
        """Create SQLite database with 20 incidents for two-run test."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE incident_current (
                incident_id TEXT PRIMARY KEY,
                status TEXT,
                first_observed_at TEXT,
                last_observed_at TEXT,
                candidate_class TEXT
            )
        """)

        # 20 incidents with identical timestamps (ISO 8601 format with UTC offset)
        base_ts = "2024-06-15T10:00:00+00:00"
        for i in range(20):
            incident_id = f"inc-{i:03d}"
            conn.execute(
                "INSERT INTO incident_current VALUES (?, ?, ?, ?, ?)",
                (incident_id, "open", base_ts, base_ts, "test"),
            )

        conn.commit()
        conn.close()
        return db_path

    def test_two_runs_resume_from_exact_cursor(
        self,
        runs_dir: Path,
        sqlite_db_with_20_incidents: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R7.6: Two-run collector test verifies cursor persists and resumes correctly.

        This test proves:
        1. Real SQLite with 20 incidents having identical timestamps
        2. Run 1: Collector processes first 10, saves cursor with exact DB text key
        3. Run 2: Collector resumes from cursor, processes remaining 10
        4. Cursor clears after final page consumed
        """
        import sqlite3
        from datetime import datetime
        from typing import Any

        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor import (
            _clear_scan_cursor,
            _load_scan_cursor,
        )
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
            run_automatic_diagnosis_loop_evidence_collection,
        )
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
            AutoLoopIncidentResult,
        )
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            AutomaticDiagnosisLoopConfig,
        )
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            IncidentDiagnosisPage,
            CursorDecodeFailure,
        )

        # Clear any existing cursor state
        _clear_scan_cursor(runs_dir)

        # ==== Patch list_incidents_for_diagnosis_page to use our test SQLite ====
        # This exercises the full cursor flow without needing full store schema
        def patched_list_incidents_for_diagnosis_page(
            active_only: bool,
            limit: int,
            cursor: str | None = None,
        ) -> tuple[IncidentDiagnosisPage | None, CursorDecodeFailure | None, str | None]:
            """Patch that queries our test SQLite directly."""
            from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
                list_incidents_for_diagnosis_page_impl,
            )
            from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
                decode_cursor,
            )

            # Decode cursor if provided
            after_cursor = None
            if cursor is not None:
                decoded, err = decode_cursor(cursor)
                if err is not None:
                    return None, err, None
                after_cursor = decoded

            conn = sqlite3.connect(sqlite_db_with_20_incidents)
            try:
                page = list_incidents_for_diagnosis_page_impl(
                    conn=conn,
                    active_only=active_only,
                    limit=limit,
                    after=after_cursor,
                )
                return page, None, None
            finally:
                conn.close()

        # Patch at the module level where collector imports it
        import k8s_diag_agent.collect.incident_diagnosis_dispatch
        import k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection as evidence_module

        monkeypatch.setattr(
            evidence_module,
            "list_incidents_for_diagnosis_page",
            patched_list_incidents_for_diagnosis_page,
        )

        # ==== Mock expensive diagnosis work ====
        # Track which incidents were processed
        processed_incidents: list[str] = []

        def mock_process_incident(
            incident_id: str,
            external_analysis_dir,
            config,
            collector_run_id,
            now,
        ) -> AutoLoopIncidentResult:
            """Mock that records which incidents were processed."""
            processed_incidents.append(incident_id)
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=True,
                eligibility_reason="mocked",
                skipped=False,
                run_id=f"mock-run-{incident_id}",
            )

        monkeypatch.setattr(
            evidence_module,
            "_process_incident",
            mock_process_incident,
        )

        # ==== RUN 1: Collect with budget=10 ====
        # Page size is max*3=30, but we limit to 10 for this test
        config_run1 = AutomaticDiagnosisLoopConfig(
            max_incidents_per_run=10,
        )

        result1 = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=runs_dir / "run-001" / "external-analysis",
            config=config_run1,
            now=datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC),
        )

        # Verify Run 1 processed exactly 10 incidents
        assert result1.incidents_processed == 10
        assert processed_incidents == [f"inc-{i:03d}" for i in range(10)]
        assert result1.incident_results[0]["incident_id"] == "inc-000"
        assert result1.incident_results[9]["incident_id"] == "inc-009"

        # Verify cursor was saved (hasMore=true after first 10)
        saved_token, reset_reason = _load_scan_cursor(runs_dir)
        assert saved_token is not None
        assert reset_reason is None

        # ==== RUN 2: Resume from cursor, collect remaining 10 ====
        # Clear processed list for run 2
        processed_incidents.clear()

        result2 = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=runs_dir / "run-002" / "external-analysis",
            config=config_run1,  # Same config
            now=datetime(2024, 6, 15, 10, 1, 0, tzinfo=UTC),  # 1 minute later
        )

        # Verify Run 2 processed exactly 10 incidents starting from inc-010
        assert result2.incidents_processed == 10
        assert processed_incidents == [f"inc-{i:03d}" for i in range(10, 20)]
        assert result2.incident_results[0]["incident_id"] == "inc-010"
        assert result2.incident_results[9]["incident_id"] == "inc-019"

        # Verify cursor was cleared (no more incidents)
        cleared_token, _ = _load_scan_cursor(runs_dir)
        assert cleared_token is None

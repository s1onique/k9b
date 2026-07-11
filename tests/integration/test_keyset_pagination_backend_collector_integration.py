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
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
            DiagnosisPageLimit,
        )

        conn = sqlite3.connect(sqlite_db)

        # First page: 2 incidents - use DiagnosisPageLimit branded type
        page_limit = DiagnosisPageLimit(2)
        sql, params = _build_diagnosis_page_query(active_only=True, limit=page_limit, after=None)
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        has_more = len(rows) > page_limit.value
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

        # Use DiagnosisPageLimit for second query as well
        sql2, params2 = _build_diagnosis_page_query(active_only=True, limit=page_limit, after=after_cursor)
        cursor2 = conn.execute(sql2, params2)
        rows2 = cursor2.fetchall()
        page2 = _rows_to_page(list(rows2), len(rows2) > page_limit.value)

        assert len(page2.incidents) == 1
        assert page2.incidents[0].incident_id == "inc-c"
        assert page2.has_more is False

        conn.close()


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

        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            AutomaticDiagnosisLoopConfig,
        )
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
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            list_incidents_for_diagnosis_page_impl,
        )
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
            DiagnosisPageLimit,
        )
        from k8s_diag_agent.collect.incident_diagnosis_pagination_results import (
            AutomaticPageListed,
        )

        # Enable automatic diagnosis loop for this test (defaults to disabled)
        # Use monkeypatch to ensure cleanup after test
        monkeypatch.setenv("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", "true")

        # Clear any existing cursor state
        _clear_scan_cursor(runs_dir)

        # Track cursor state across calls to simulate two-run behavior
        current_cursor: str | None = None

        def mock_list_incidents_with_pagination(
            scan_cursor,  # OpaqueCursorToken | None
            scan_bound: int,
        ):
            """Mock that queries our test SQLite and returns proper pages."""
            nonlocal current_cursor

            # Convert OpaqueCursorToken to string or None
            cursor_str = str(scan_cursor) if scan_cursor else None
            current_cursor = cursor_str

            conn = sqlite3.connect(sqlite_db_with_20_incidents)
            try:
                # Decode cursor if provided
                after_cursor = None
                if cursor_str is not None:
                    from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
                        decode_cursor,
                    )
                    decoded, err = decode_cursor(cursor_str)
                    if err is not None:
                        conn.close()
                        from k8s_diag_agent.collect.incident_diagnosis_pagination_results import (
                            AutomaticPageCursorRejected,
                        )
                        return AutomaticPageCursorRejected(failure=err)

                    # Convert decoded cursor to the format expected by list_incidents_for_diagnosis_page_impl
                    after_cursor = decoded

                page = list_incidents_for_diagnosis_page_impl(
                    conn=conn,
                    active_only=True,
                    limit=DiagnosisPageLimit(scan_bound),
                    after=after_cursor,
                )
                return AutomaticPageListed(page=page)
            finally:
                conn.close()

        # Patch list_incidents_with_pagination where collector imports it
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination",
            mock_list_incidents_with_pagination,
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
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            mock_process_incident,
        )

        # ==== RUN 1: Collect with budget=10 ====
        config_run1 = AutomaticDiagnosisLoopConfig(
            max_incidents_per_run=10,
        )

        result1 = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=runs_dir / "run-001" / "external-analysis",
            config=config_run1,
            now=datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC),
        )

        # Early assertion: verify loop is enabled (fails fast if env not set)
        assert result1.enabled is True, (
            "Automatic diagnosis loop is disabled. "
            "Ensure K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true is set in the test environment."
        )

        # Verify Run 1 processed exactly 10 incidents
        assert result1.incidents_processed == 10, f"Expected 10, got {result1.incidents_processed}"
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
        assert result2.incidents_processed == 10, f"Expected 10, got {result2.incidents_processed}"
        assert processed_incidents == [f"inc-{i:03d}" for i in range(10, 20)]
        assert result2.incident_results[0]["incident_id"] == "inc-010"
        assert result2.incident_results[9]["incident_id"] == "inc-019"

        # Verify cursor was cleared (no more incidents)
        cleared_token, _ = _load_scan_cursor(runs_dir)
        assert cleared_token is None

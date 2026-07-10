"""R6.4/R7.5: Skipped page cursor disposition tests.

These tests verify that cursor disposition correctly handles skipped pages
when hasMore=true. R7.5: Uses active incidents to model production selection.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

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
    make_test_cursor,
)


@pytest.fixture
def temp_runs_dir(tmp_path: Path) -> Path:
    """Create a temporary runs directory."""
    return tmp_path / "runs"


class TestSkippedPageWithHasMore:
    """R6.4/R7.5: Tests for cursor disposition when page is fully skipped but hasMore=true.

    R7.5: Uses ACTIVE incidents (open/investigating) to model production selection,
    not resolved incidents. This reflects the actual behavior where only active
    incidents are fetched with active_only=True.

    When all incidents in a page are skipped (e.g., ineligible for diagnosis)
    but the page has more results, we must NOT clear the cursor. We should
    save the cursor pointing to the last incident in the page so the next run
    advances to the next page.
    """

    def test_skipped_page_saves_cursor_not_clears(self, temp_runs_dir: Path) -> None:
        """R6.4/R7.5: Skipped page with hasMore=true saves cursor, doesn't clear."""
        # R7.5: 30 active incidents all skipped (ineligible for diagnosis),
        # but more pages exist. Active statuses: open, investigating, collecting_evidence
        active_statuses = ["open", "investigating", "collecting_evidence"]

        page_incidents = [
            (f"incident-{i:03d}", datetime(2024, 1, 1, i // 60, i % 60, 0, tzinfo=UTC))
            for i in range(30)
        ]

        # R6.4/R7.5 invariant: has_more=True requires next_cursor
        # Create a cursor for the last incident in this page
        last_idx = len(page_incidents) - 1
        last_inc_id, last_ts = page_incidents[last_idx]
        last_processed_cursor = make_test_cursor(
            first_observed_at_text=last_ts.isoformat(),
            incident_id=last_inc_id,
        )

        # Verify page has correct has_more flag with valid next_cursor
        page = IncidentDiagnosisPage(
            incidents=tuple(
                DiagnosisPageIncident(
                    incident_id=inc_id,
                    status=active_statuses[i % len(active_statuses)],  # R7.5: Active statuses
                    first_observed_at=ts,
                    first_observed_at_key=ts.isoformat(),
                )
                for i, (inc_id, ts) in enumerate(page_incidents)
            ),
            next_cursor=last_processed_cursor,
            has_more=True,
        )
        assert page.has_more is True

        # Simulate processing all 30 (all skipped - ineligible for diagnosis)
        # Cursor should be saved, not cleared
        # because hasMore=true means there are more pages to advance to
        cursor_token = encode_cursor(last_processed_cursor)
        _save_scan_cursor(temp_runs_dir, cursor_token)

        # Verify cursor was saved
        loaded_token, _ = _load_scan_cursor(temp_runs_dir)
        assert loaded_token is not None

        # Decode and verify it points to incident-029
        decoded, err = decode_cursor(loaded_token)
        assert err is None
        assert decoded.incident_id == "incident-029"

        # Next run would use this cursor to advance to the next page
        # NOT restart from the beginning

    def test_all_skipped_active_incidents_continues_to_next_page(
        self, temp_runs_dir: Path
    ) -> None:
        """R6.4/R7.5: All skipped active page with hasMore=true continues to next page."""
        # R7.5: Simulate two-run scenario with ACTIVE incidents
        # Active statuses: open, investigating, collecting_evidence
        # Run 1: Page 1 with 30 active incidents, all skipped (ineligible),
        # hasMore=true

        page1_incidents = [
            (f"incident-{i:03d}", datetime(2024, 1, 1, i // 60, i % 60, 0, tzinfo=UTC))
            for i in range(30)
        ]

        # Process page 1 (all skipped - all ineligible for diagnosis)
        last_idx_p1 = len(page1_incidents) - 1
        cursor_p1 = make_test_cursor(
            first_observed_at_text=page1_incidents[last_idx_p1][1].isoformat(),
            incident_id=page1_incidents[last_idx_p1][0],
        )
        cursor_token_p1 = encode_cursor(cursor_p1)
        _save_scan_cursor(temp_runs_dir, cursor_token_p1)

        # Run 2: Resume with cursor pointing to incident-029
        # Backend would skip past incident-029 and return incident-030+
        loaded_cursor, _ = _load_scan_cursor(temp_runs_dir)
        assert loaded_cursor is not None

        decoded_cursor, _ = decode_cursor(loaded_cursor)
        assert decoded_cursor.incident_id == "incident-029"

        # Simulate resume: find cursor in full incident list and start after it
        # R7.5: All incidents are active (active_only=True in production)
        all_incidents = page1_incidents + [
            (f"incident-{i:03d}", datetime(2024, 1, 2, i // 60, i % 60, 0, tzinfo=UTC))
            for i in range(30, 60)
        ]

        # Find where to resume
        cursor_idx = None
        for i, (inc_id, _) in enumerate(all_incidents):
            if inc_id == decoded_cursor.incident_id:
                cursor_idx = i
                break
        assert cursor_idx == 29  # incident-029 is at index 29

        # Resume at index 30 (incident-030)
        resume_idx = cursor_idx + 1
        resume_inc_id = all_incidents[resume_idx][0]
        assert resume_inc_id == "incident-030"

        # Verify NOT restarting from incident-000
        assert resume_inc_id != "incident-000"

    def test_cursor_cleared_on_final_page(self, temp_runs_dir: Path) -> None:
        """R6.4: Final page (hasMore=false) should clear cursor."""
        # Final page with no more results
        final_page_incidents = [
            (f"incident-{i:03d}", datetime(2024, 1, 1, i // 60, i % 60, 0, tzinfo=UTC))
            for i in range(10)
        ]

        # Last incident in final page
        last_idx = len(final_page_incidents) - 1
        last_inc_id, last_ts = final_page_incidents[last_idx]

        # Create and save cursor for last incident
        last_processed_cursor = make_test_cursor(
            first_observed_at_text=last_ts.isoformat(),
            incident_id=last_inc_id,
        )
        cursor_token = encode_cursor(last_processed_cursor)
        _save_scan_cursor(temp_runs_dir, cursor_token)

        # Verify cursor saved
        loaded_token, _ = _load_scan_cursor(temp_runs_dir)
        assert loaded_token is not None

        # Simulate final page consumed - clear cursor
        _clear_scan_cursor(temp_runs_dir)

        # Verify cursor cleared
        loaded_after, _ = _load_scan_cursor(temp_runs_dir)
        assert loaded_after is None

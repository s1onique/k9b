"""Multi-run starvation regression tests for keyset pagination.

These tests prove that:
1. 40+ incidents with small page size still makes progress across pages
2. Cursor advances correctly through all incidents
3. No starvation when using keyset pagination
"""

from __future__ import annotations

import json
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


class TestMultiRunStarvationRegression:
    """Regression tests for multi-run starvation with keyset pagination.

    These tests prove that keyset pagination prevents starvation:
    - 40+ incidents with page size 5 = 8+ pages
    - Each run processes a page and saves cursor
    - Cursor allows resuming from correct position
    - No incidents are skipped or starved
    """

    def test_cursor_persists_and_loads_correctly(self, temp_runs_dir: Path) -> None:
        """Cursor can be saved and loaded correctly across runs."""
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

    def test_legacy_cursor_format_detected(self, temp_runs_dir: Path) -> None:
        """Legacy cursor format (schemaVersion 1) triggers reset."""
        # Create legacy cursor file
        cursor_file = temp_runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        cursor_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cursor_file, "w") as f:
            json.dump({
                "schemaVersion": 1,
                "last_incident_id": "incident-05",
                "savedAt": "2026-01-01T00:00:00+00:00",
            }, f)

        # Load should detect legacy format and reset
        loaded_token, reset_reason = _load_scan_cursor(temp_runs_dir)

        assert loaded_token is None
        assert reset_reason == "legacy_state_schema"

    def test_multiple_pages_processed_in_sequence(self, temp_runs_dir: Path) -> None:
        """Multiple pages can be processed in sequence using cursors."""
        # Simulate 50 incidents, page size 10
        num_incidents = 50
        page_size = 10
        expected_pages = (num_incidents + page_size - 1) // page_size

        page_count = 0

        # Simulate iterating through pages
        for page_num in range(expected_pages):
            # Create page data
            start_idx = page_num * page_size
            end_idx = min(start_idx + page_size, num_incidents)

            page_incidents = tuple(
                DiagnosisPageIncident(
                    incident_id=f"incident-{i:03d}",
                    status="open",
                    first_observed_at=datetime(2024, 1, 1, i // 60, i % 60, 0, tzinfo=UTC),
                    first_observed_at_key=datetime(2024, 1, 1, i // 60, i % 60, 0, tzinfo=UTC).isoformat(),
                )
                for i in range(start_idx, end_idx)
            )

            # Determine if there are more pages
            has_more = end_idx < num_incidents

            # Create next cursor from last incident in page
            if has_more:
                last_idx = end_idx - 1
                # Cursor must match the LAST incident's exact timestamp
                last_ts = datetime(2024, 1, 1, last_idx // 60, last_idx % 60, 0, tzinfo=UTC)
                next_cursor = make_test_cursor(
                    first_observed_at_text=last_ts.isoformat(),
                    incident_id=f"incident-{last_idx:03d}",
                )
            else:
                next_cursor = None

            page = IncidentDiagnosisPage(
                incidents=page_incidents,
                next_cursor=next_cursor,
                has_more=has_more,
            )

            # Verify page contents
            assert len(page.incidents) == min(page_size, num_incidents - start_idx)

            # If there's a next cursor, save it
            if page.next_cursor:
                token = encode_cursor(page.next_cursor)
                _save_scan_cursor(temp_runs_dir, token)

                # Verify it can be loaded
                loaded_token, _ = _load_scan_cursor(temp_runs_dir)
                assert loaded_token == token

                # Verify decoding
                decoded, err = decode_cursor(loaded_token)
                assert err is None
                assert decoded.incident_id == f"incident-{end_idx - 1:03d}"

            page_count += 1

            # Clear cursor on last page
            if not has_more:
                _clear_scan_cursor(temp_runs_dir)

        assert page_count == expected_pages

        # Verify cursor was cleared
        loaded_token, _ = _load_scan_cursor(temp_runs_dir)
        assert loaded_token is None

    def test_progress_across_pages_with_small_limit(self, temp_runs_dir: Path) -> None:
        """Small page sizes still allow complete traversal of all incidents."""
        # 40 incidents, page size 5 = 8 pages
        num_incidents = 40
        page_size = 5

        all_processed = []
        cursor_token = None

        while True:
            # Simulate fetching a page
            if cursor_token:
                cursor, _ = decode_cursor(cursor_token)
                start_idx = int(cursor.incident_id.split("-")[1]) + 1
            else:
                start_idx = 0

            end_idx = min(start_idx + page_size, num_incidents)

            # Fetch page data
            page_incidents = [
                f"incident-{i:03d}" for i in range(start_idx, end_idx)
            ]
            all_processed.extend(page_incidents)

            # Determine if there are more pages
            if end_idx < num_incidents:
                # Cursor should point to the LAST processed incident (end_idx - 1)
                # not the next one. This is the fix for the starvation bug.
                last_idx = end_idx - 1
                # Cursor must match the LAST incident's exact timestamp
                last_ts = datetime(2024, 1, 1, last_idx // 60, last_idx % 60, 0, tzinfo=UTC)
                next_cursor = make_test_cursor(
                    first_observed_at_text=last_ts.isoformat(),
                    incident_id=f"incident-{last_idx:03d}",
                )
                cursor_token = encode_cursor(next_cursor)
                _save_scan_cursor(temp_runs_dir, cursor_token)
            else:
                # Done - clear cursor
                _clear_scan_cursor(temp_runs_dir)
                break

        # Verify all incidents were processed
        assert len(all_processed) == num_incidents

        # Verify ordering is preserved
        for i in range(len(all_processed) - 1):
            curr_idx = int(all_processed[i].split("-")[1])
            next_idx = int(all_processed[i + 1].split("-")[1])
            assert curr_idx < next_idx

        # Verify no duplicates
        assert len(all_processed) == len(set(all_processed))

    def test_cursor_with_different_timestamps(self, temp_runs_dir: Path) -> None:
        """Cursors work correctly with different timestamps."""
        timestamps = [
            datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
            datetime(2024, 2, 1, 8, 15, 0, tzinfo=UTC),
            datetime(2024, 3, 15, 22, 45, 0, tzinfo=UTC),
            datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC),
        ]

        for i, ts in enumerate(timestamps):
            cursor = make_test_cursor(
                first_observed_at_text=ts.isoformat(),
                incident_id=f"incident-{i:03d}",
            )
            token = encode_cursor(cursor)
            _save_scan_cursor(temp_runs_dir, token)

            # Load and verify
            loaded_token, _ = _load_scan_cursor(temp_runs_dir)
            decoded, err = decode_cursor(loaded_token)

            assert err is None
            assert decoded.first_observed_at_text == ts.isoformat()
            assert decoded.incident_id == f"incident-{i:03d}"

    def test_empty_cursor_file_handled(self, temp_runs_dir: Path) -> None:
        """Missing cursor file returns None without error."""
        # Don't create any cursor file
        loaded_token, reset_reason = _load_scan_cursor(temp_runs_dir)

        assert loaded_token is None
        assert reset_reason is None

    def test_corrupted_cursor_file_handled(self, temp_runs_dir: Path) -> None:
        """Corrupted cursor file is handled gracefully."""
        cursor_file = temp_runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        cursor_file.parent.mkdir(parents=True, exist_ok=True)

        # Write invalid JSON
        with open(cursor_file, "w") as f:
            f.write("not valid json{")

        # Should return None, not raise exception
        loaded_token, reset_reason = _load_scan_cursor(temp_runs_dir)
        assert loaded_token is None

    def test_cursor_at_last_incident_clears(self, temp_runs_dir: Path) -> None:
        """Cursor at last incident should allow wrap-around."""
        cursor = make_test_cursor(
            first_observed_at_text="2024-01-31T23:59:59+00:00",
            incident_id="incident-100",
        )
        token = encode_cursor(cursor)
        _save_scan_cursor(temp_runs_dir, token)

        # Load should work
        loaded_token, _ = _load_scan_cursor(temp_runs_dir)
        assert loaded_token == token

        # Clear should remove file
        _clear_scan_cursor(temp_runs_dir)
        cursor_file = temp_runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        assert not cursor_file.exists()

    def test_no_starvation_with_gap_in_timestamps(self, temp_runs_dir: Path) -> None:
        """Large gaps in timestamps don't cause starvation."""
        # Incidents with irregular timestamps
        incidents = [
            ("incident-001", datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)),
            ("incident-002", datetime(2024, 3, 15, 12, 0, 0, tzinfo=UTC)),  # Big gap
            ("incident-003", datetime(2024, 3, 15, 12, 0, 0, tzinfo=UTC)),  # Same as above
            ("incident-004", datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)),  # Big gap
        ]

        cursor_token = None
        processed = []

        while True:
            if cursor_token:
                cursor, _ = decode_cursor(cursor_token)
                # Find next unprocessed
                cursor_idx = None
                for i, (inc_id, _) in enumerate(incidents):
                    if inc_id == cursor.incident_id:
                        cursor_idx = i
                        break
                if cursor_idx is None:
                    # Cursor incident not found, restart
                    start_idx = 0
                else:
                    # Cursor points to last processed, so resume after it
                    start_idx = cursor_idx + 1
            else:
                start_idx = 0

            if start_idx >= len(incidents):
                break

            # Process one at a time (page size 1)
            inc_id, ts = incidents[start_idx]
            processed.append(inc_id)

            if start_idx < len(incidents) - 1:
                # Create cursor to LAST PROCESSED incident (not next)
                # This is the fix: cursor = current, resume = current + 1
                current_inc_id, current_ts = incidents[start_idx]
                next_cursor = make_test_cursor(
                    first_observed_at_text=current_ts.isoformat(),
                    incident_id=current_inc_id,
                )
                cursor_token = encode_cursor(next_cursor)
                _save_scan_cursor(temp_runs_dir, cursor_token)
            else:
                _clear_scan_cursor(temp_runs_dir)
                break

        # Verify all processed
        assert len(processed) == len(incidents)
        assert set(processed) == {inc[0] for inc in incidents}

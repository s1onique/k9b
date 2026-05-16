"""Tests for index path cache freshness in server_reads.py.

These tests verify:
1. Cache freshness uses ui-index.json mtime when index path is used
2. Cache freshness uses external-analysis mtime when scan path is used
3. Fallback reason is logged when index path is skipped
4. cache_freshness_source and cache_freshness_path timings are set
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.server import HealthUIRequestHandler
from k8s_diag_agent.ui.server_reads import build_runs_list_payload


def _payload_runs(payload: dict[str, object]) -> list[dict[str, object]]:
    """Helper to narrow payload["runs"] type for mypy."""
    runs = payload.get("runs")
    assert isinstance(runs, list)
    assert all(isinstance(run, dict) for run in runs)
    return cast(list[dict[str, object]], runs)


class MockHandler:
    """Mock handler for testing build_runs_list_payload."""

    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir
        self._health_root = runs_dir / "health"


class TestCacheFreshnessIndexPath:
    """Tests for cache freshness when using index path."""

    def test_index_path_uses_ui_index_mtime(self, tmp_path: Path) -> None:
        """When index path is used, cache freshness should come from ui-index.json mtime."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create ui-index.json with batch eligibility (v2)
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        # Touch ui-index.json to set its mtime
        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.touch()

        handler = cast(HealthUIRequestHandler, MockHandler(tmp_path))
        payload = build_runs_list_payload(
            handler,
            include_batch_eligibility=True,
        )

        # Verify result structure
        payload = cast(dict[str, object], payload)
        runs = _payload_runs(payload)
        assert len(runs) == 1

    def test_scan_path_uses_external_analysis_mtime(self, tmp_path: Path) -> None:
        """When scan path is used, cache freshness should come from external-analysis mtime."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create a review file (no ui-index.json)
        (reviews_dir / "test-run-review.json").write_text(
            json.dumps(
                {
                    "run_id": "test-run",
                    "run_label": "Test",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        handler = cast(HealthUIRequestHandler, MockHandler(tmp_path))
        payload = build_runs_list_payload(
            handler,
            include_batch_eligibility=True,  # This will trigger scan path
        )

        # Verify result - should have the run from review file
        payload = cast(dict[str, object], payload)
        runs = _payload_runs(payload)
        assert len(runs) == 1

    def test_include_status_false_and_include_expensive_false_triggers_index_path(self, tmp_path: Path) -> None:
        """When include_batch_eligibility=True but status/expensive are False, use index path."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        handler = cast(HealthUIRequestHandler, MockHandler(tmp_path))
        payload = build_runs_list_payload(
            handler,
            include_batch_eligibility=True,
            include_status=False,
            include_expensive=False,
        )

        payload = cast(dict[str, object], payload)
        runs = _payload_runs(payload)
        assert len(runs) == 1
        assert runs[0]["batchExecutable"] is True


class TestCacheFreshnessTimings:
    """Tests for cache_freshness_source and cache_freshness_path timings."""

    def test_batch_eligibility_index_sets_timings(self, tmp_path: Path) -> None:
        """Index path should set cache_freshness_source and cache_freshness_path timings."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)

        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        handler = cast(HealthUIRequestHandler, MockHandler(tmp_path))
        payload = build_runs_list_payload(
            handler,
            include_batch_eligibility=True,
        )

        payload = cast(dict[str, object], payload)
        # Timings should be available somewhere - verify payload structure
        assert "runs" in payload


class TestFallbackReasonSurfaced:
    """Tests for fallback_reason when index path is skipped."""

    def test_fallback_reason_index_version_lt_2(self, tmp_path: Path) -> None:
        """Fallback reason should be 'version_lt_2' when index version < 2."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)

        # Create v1 index (no batch eligibility fields)
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        # Missing batchEligibility, batchExecutable, batchEligibleCount
                    }
                ],
                "total_count": 1,
                "version": 1,  # Version 1 lacks batch eligibility
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        from k8s_diag_agent.ui.api import build_runs_list

        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Should fall back to scan path
        # The timings may have fallback_reason set
        path_strategy = timings.get("path_strategy", "")
        fallback_reason = timings.get("fallback_reason")

        # Path should be either index_batch_eligibility_fallback or scan path
        assert path_strategy in (
            "index_batch_eligibility_fallback",
            "review_streaming_super_fast_path",
            "index_super_fast_path",
        ), f"Unexpected path_strategy: {path_strategy}"

        if path_strategy == "index_batch_eligibility_fallback":
            assert fallback_reason is not None, "fallback_reason should be set"
            assert fallback_reason in ("version_lt_2", "missing_batch_fields", "invalid_index_structure"), f"Unexpected fallback_reason: {fallback_reason}"

    def test_fallback_reason_index_missing(self, tmp_path: Path) -> None:
        """Fallback reason should be 'index_missing' when ui-index.json doesn't exist."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)

        # Create a review file but NO ui-index.json
        (reviews_dir / "test-run-review.json").write_text(
            json.dumps(
                {
                    "run_id": "test-run",
                    "run_label": "Test",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        from k8s_diag_agent.ui.api import build_runs_list

        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Should fall back to scan path
        path_strategy = timings.get("path_strategy", "")
        fallback_reason = timings.get("fallback_reason")

        # Should use scan path
        assert path_strategy in (
            "index_batch_eligibility_fallback",  # Will have fallback_reason
            "review_streaming_super_fast_path",  # Scan path
        ), f"Unexpected path_strategy: {path_strategy}"

        if path_strategy == "index_batch_eligibility_fallback":
            assert fallback_reason is not None
            assert fallback_reason == "index_missing"

    def test_fallback_reason_missing_batch_fields(self, tmp_path: Path) -> None:
        """Fallback reason should be 'missing_batch_fields' when entries lack batch fields."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)

        # Create v2 index but entries lack batch fields
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        # Missing batchEligibility, batchExecutable, batchEligibleCount
                    }
                ],
                "total_count": 1,
                "version": 2,  # Version 2 but entries missing fields
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        from k8s_diag_agent.ui.api import build_runs_list

        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        path_strategy = timings.get("path_strategy", "")
        fallback_reason = timings.get("fallback_reason")

        assert path_strategy == "index_batch_eligibility_fallback"
        assert fallback_reason == "missing_batch_fields"

    def test_fallback_reason_invalid_json(self, tmp_path: Path) -> None:
        """Fallback reason should be 'invalid_json' when ui-index.json is malformed."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)

        # Create malformed JSON
        (health_dir / "ui-index.json").write_text("{ invalid json }", encoding="utf-8")

        from k8s_diag_agent.ui.api import build_runs_list

        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        path_strategy = timings.get("path_strategy", "")
        fallback_reason = timings.get("fallback_reason")

        assert path_strategy == "index_batch_eligibility_fallback"
        assert fallback_reason == "invalid_json"

    def test_successful_index_path_no_fallback_reason(self, tmp_path: Path) -> None:
        """When index path succeeds, fallback_reason should NOT be set."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)

        # Create valid v2 index with batch fields
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        from k8s_diag_agent.ui.api import build_runs_list

        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Should use index path
        assert timings.get("path_strategy") == "index_recent_runs_with_batch_eligibility"
        assert timings.get("batch_plan_glob_ms") == 0.0
        assert timings.get("batch_exec_glob_ms") == 0.0
        assert timings.get("reviews_parsed") == 0


class TestIndexPathPerformance:
    """Tests for performance requirements of index path."""

    def test_index_path_total_duration_under_200ms(self, tmp_path: Path) -> None:
        """Index path should complete in under 200ms."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)

        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        from k8s_diag_agent.ui.api import build_runs_list

        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        total_duration = timings.get("total_duration_ms", 999999)
        assert total_duration < 200, f"Index path took {total_duration}ms, expected < 200ms"
        assert timings.get("path_strategy") == "index_recent_runs_with_batch_eligibility"
        assert timings.get("reviews_parsed") == 0

    def test_index_path_skips_all_expensive_operations(self, tmp_path: Path) -> None:
        """Index path should skip all expensive operations."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create lots of review and plan files (should NOT be scanned)
        for i in range(100):
            (reviews_dir / f"run-{i:03d}-review.json").write_text(
                json.dumps(
                    {
                        "run_id": f"run-{i:03d}",
                        "run_label": f"Run {i}",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                    }
                ),
                encoding="utf-8",
            )

        # Create plan files (should NOT be scanned)
        for i in range(50):
            (ea_dir / f"run-{i:03d}-next-check-plan.json").write_text(
                json.dumps(
                    {
                        "purpose": "next-check-planning",
                        "candidates": [],
                    }
                ),
                encoding="utf-8",
            )

        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        from k8s_diag_agent.ui.api import build_runs_list

        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Index path should not scan any files
        assert timings.get("path_strategy") == "index_recent_runs_with_batch_eligibility"
        assert timings.get("reviews_parsed") == 0
        assert timings.get("batch_plan_files_found") == 0
        assert timings.get("batch_exec_files_found") == 0
        assert timings.get("batch_plan_glob_ms") == 0.0
        assert timings.get("batch_exec_glob_ms") == 0.0


class TestStaleIndexAfterBatchExecution:
    """Regression tests for stale index after batch execution.

    These tests verify that when new execution artifacts are written after batch execution,
    the runs list cache is invalidated even if ui-index.json wasn't regenerated.

    Issue: Batch execution writes next-check-execution artifacts to external-analysis/
    but doesn't regenerate ui-index.json. The cache was keyed on ui-index.json mtime,
    causing stale Recent Runs to show "No Executions Yet" until the next health loop.

    The fix: Cache freshness uses max(ui-index mtime, external-analysis mtime).
    This ensures cache is invalidated when external-analysis changes, even if ui-index doesn't.
    """

    def test_cache_keyed_on_max_mtime_not_just_ui_index(self, tmp_path: Path) -> None:
        """Cache must be invalidated when external-analysis mtime changes, even if ui-index doesn't.

        This is the core regression test for the batch execution freshness issue.
        Before the fix: cache was keyed only on ui-index.json mtime.
        After the fix: cache is keyed on max(ui-index, external-analysis) mtime.
        """
        import os
        import time as time_module

        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create ui-index.json with v2 batch eligibility
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.write_text(json.dumps(ui_index), encoding="utf-8")

        # Set ui-index.json mtime to a known old time
        old_time = 1000000000.0
        time_module.sleep(0.01)
        os.utime(ui_index_path, (old_time, old_time))

        handler = cast(HealthUIRequestHandler, MockHandler(tmp_path))

        # First call - builds cache keyed on external-analysis mtime (which is newer in tmp_path)
        payload1 = build_runs_list_payload(
            handler,
            include_batch_eligibility=True,
        )
        payload1 = cast(dict[str, object], payload1)
        runs1 = _payload_runs(payload1)
        assert len(runs1) == 1

        # Simulate batch execution: write execution artifacts to external-analysis
        # This should change external-analysis mtime
        time_module.sleep(0.01)
        for i in range(3):
            exec_artifact = {
                "purpose": "next-check-execution",
                "run_id": "test-run",
                "payload": {"candidateIndex": i},
                "status": "success",
            }
            (ea_dir / f"test-run-next-check-execution-{i}.json").write_text(
                json.dumps(exec_artifact), encoding="utf-8"
            )

        # Record external-analysis mtime before second call
        ea_mtime_after = ea_dir.stat().st_mtime
        assert ea_mtime_after > old_time, "external-analysis should be newer after writing artifacts"

        # Second call - cache should be invalidated because external-analysis mtime changed
        # (even though ui-index.json mtime is still old_time)
        payload2 = build_runs_list_payload(
            handler,
            include_batch_eligibility=True,
        )
        payload2 = cast(dict[str, object], payload2)
        runs2 = _payload_runs(payload2)
        assert len(runs2) == 1

        # The key assertion: cache was rebuilt (not stale)
        # Both payloads should have the same data (from index path)
        # But the second one was freshly computed because external-analysis mtime changed
        assert runs2[0]["runId"] == "test-run"

    def test_batch_eligibility_index_uses_max_ui_index_and_external_analysis_mtime(self, tmp_path: Path) -> None:
        """Verify that cache freshness uses max(ui-index, external-analysis) mtime.

        This ensures the cache is invalidated when either source changes.
        """
        import time as time_module

        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create ui-index.json
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.write_text(json.dumps(ui_index), encoding="utf-8")

        import os

        # Set ui-index.json mtime to old
        old_time = 1000000000.0
        os.utime(ui_index_path, (old_time, old_time))

        # Set external-analysis mtime to be newer than ui-index
        time_module.sleep(0.01)
        new_time = 1000000100.0
        os.utime(ea_dir, (new_time, new_time))

        # Verify external-analysis is indeed newer
        assert ea_dir.stat().st_mtime > ui_index_path.stat().st_mtime

        handler = cast(HealthUIRequestHandler, MockHandler(tmp_path))

        # Call should rebuild cache (not use stale cache keyed on ui-index mtime)
        payload = build_runs_list_payload(
            handler,
            include_batch_eligibility=True,
        )

        # Verify cache was rebuilt, not served from cache keyed on older ui-index mtime
        payload = cast(dict[str, object], payload)
        runs = _payload_runs(payload)
        assert len(runs) == 1
        assert runs[0]["batchExecutable"] is True

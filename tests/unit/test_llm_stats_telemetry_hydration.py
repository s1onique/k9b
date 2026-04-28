"""Tests for LLM telemetry latency hydration in server_read_support.

Verifies that _build_llm_stats_for_run correctly computes p50/p95/p99 latency
from artifact duration_ms fields.

Contract:
- Only positive (> 0) durations from successful calls are included in percentiles.
- Zero, negative, missing, or non-numeric durations yield None for percentiles.
- Failed call durations are excluded from percentile computation.
- Both snake_case (duration_ms) and camelCase (durationMs) field names are supported.
- Uses nearest-rank percentile algorithm: index = ceil(p/100 * n) - 1.
"""

import json
import tempfile
import unittest
from pathlib import Path


class LLMStatsTelemetryHydrationTests(unittest.TestCase):
    """Tests for LLM stats latency percentile computation."""

    def test_percentiles_match_expected_values_for_known_durations(self) -> None:
        """Test exact percentile values for durations [100, 200, 300, 400].

        With n=4 and nearest-rank algorithm (index = ceil(p/100 * n) - 1):
        - p50: ceil(0.50 * 4) - 1 = ceil(2) - 1 = 2 - 1 = 1 → values[1] = 200
        - p95: ceil(0.95 * 4) - 1 = ceil(3.8) - 1 = 4 - 1 = 3 → values[3] = 400
        - p99: ceil(0.99 * 4) - 1 = ceil(3.96) - 1 = 4 - 1 = 3 → values[3] = 400
        """
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-exact"

            # Four successful calls with known durations
            for idx, duration in enumerate([100, 200, 300, 400]):
                artifact = {
                    "tool_name": f"provider-{idx}",
                    "status": "success",
                    "timestamp": f"2026-01-01T00:0{idx}:00Z",
                    "duration_ms": duration,
                }
                (external_analysis_dir / f"{run_id}-artifact-{idx}.json").write_text(
                    json.dumps(artifact), encoding="utf-8"
                )

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            self.assertEqual(stats["totalCalls"], 4)
            self.assertEqual(stats["successfulCalls"], 4)
            self.assertEqual(stats["failedCalls"], 0)

            # Exact expected values per nearest-rank algorithm
            self.assertEqual(stats["p50LatencyMs"], 200, "p50 should be 200 (median of [100, 200, 300, 400])")
            self.assertEqual(stats["p95LatencyMs"], 400, "p95 should be 400 (last element)")
            self.assertEqual(stats["p99LatencyMs"], 400, "p99 should be 400 (last element)")

    def test_build_llm_stats_includes_latency_percentiles_from_successful_calls(self) -> None:
        """Test that successful calls with duration data produce non-empty latency percentiles."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-latency"

            # Create artifacts with various successful call durations
            artifacts = [
                {
                    "tool_name": "llamacpp",
                    "status": "success",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "duration_ms": 100,
                    "purpose": "review-enrichment",
                },
                {
                    "tool_name": "llm-autodrilldown",
                    "status": "success",
                    "timestamp": "2026-01-01T00:01:00Z",
                    "duration_ms": 200,
                    "purpose": "auto-drilldown",
                },
                {
                    "tool_name": "next-check-planner",
                    "status": "success",
                    "timestamp": "2026-01-01T00:02:00Z",
                    "duration_ms": 300,
                    "purpose": "next-check-planning",
                },
                {
                    "tool_name": "k8sgpt",
                    "status": "success",
                    "timestamp": "2026-01-01T00:03:00Z",
                    "duration_ms": 400,
                    "purpose": "manual",
                },
                {
                    "tool_name": "llamacpp",
                    "status": "failed",
                    "timestamp": "2026-01-01T00:04:00Z",
                    "duration_ms": 500,
                    "purpose": "manual",
                },
            ]

            for idx, artifact in enumerate(artifacts):
                artifact_path = external_analysis_dir / f"{run_id}-artifact-{idx}.json"
                artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # Verify call counts
            self.assertEqual(stats["totalCalls"], 5)
            self.assertEqual(stats["successfulCalls"], 4)
            self.assertEqual(stats["failedCalls"], 1)

            # Verify latency percentiles are populated (not None)
            self.assertIsNotNone(stats["p50LatencyMs"], "p50 should not be None when successful calls have durations")
            self.assertIsNotNone(stats["p95LatencyMs"], "p95 should not be None when successful calls have durations")
            self.assertIsNotNone(stats["p99LatencyMs"], "p99 should not be None when successful calls have durations")

            # Verify percentiles are reasonable values
            self.assertGreater(stats["p50LatencyMs"], 0)  # type: ignore[misc]
            self.assertGreater(stats["p95LatencyMs"], 0)  # type: ignore[misc]
            self.assertGreater(stats["p99LatencyMs"], 0)  # type: ignore[misc]

            # Verify ordering: p50 <= p95 <= p99
            self.assertLessEqual(stats["p50LatencyMs"], stats["p95LatencyMs"])  # type: ignore[call-overload]
            self.assertLessEqual(stats["p95LatencyMs"], stats["p99LatencyMs"])  # type: ignore[call-overload]

            # Verify provider breakdown is correct
            self.assertEqual(len(stats["providerBreakdown"]), 4)  # type: ignore[arg-type]
            provider_names = {entry["provider"] for entry in stats["providerBreakdown"]}
            self.assertEqual(provider_names, {"llamacpp", "llm-autodrilldown", "next-check-planner", "k8sgpt"})

    def test_build_llm_stats_handles_missing_duration_fields(self) -> None:
        """Test that artifacts without duration fields produce None latency (not zero)."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-no-duration"

            # Create artifacts without duration_ms field
            artifacts = [
                {
                    "tool_name": "llamacpp",
                    "status": "success",
                    "timestamp": "2026-01-01T00:00:00Z",
                    # No duration_ms field
                    "purpose": "review-enrichment",
                },
                {
                    "tool_name": "k8sgpt",
                    "status": "success",
                    "timestamp": "2026-01-01T00:01:00Z",
                    # No duration_ms field
                    "purpose": "manual",
                },
            ]

            for idx, artifact in enumerate(artifacts):
                artifact_path = external_analysis_dir / f"{run_id}-artifact-{idx}.json"
                artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # Verify call counts are still correct
            self.assertEqual(stats["totalCalls"], 2)
            self.assertEqual(stats["successfulCalls"], 2)
            self.assertEqual(stats["failedCalls"], 0)

            # Latency percentiles should be None (not zero) when no durations available
            self.assertIsNone(stats["p50LatencyMs"], "p50 should be None when no duration data exists")
            self.assertIsNone(stats["p95LatencyMs"], "p95 should be None when no duration data exists")
            self.assertIsNone(stats["p99LatencyMs"], "p99 should be None when no duration data exists")

    def test_build_llm_stats_handles_durationms_zero_value(self) -> None:
        """Test that duration_ms=0 is treated as missing (produces None latency)."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-zero-duration"

            # Create artifact with duration_ms = 0 (edge case - effectively missing)
            artifacts = [
                {
                    "tool_name": "llamacpp",
                    "status": "success",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "duration_ms": 0,  # Zero duration is treated as missing
                    "purpose": "review-enrichment",
                },
            ]

            for idx, artifact in enumerate(artifacts):
                artifact_path = external_analysis_dir / f"{run_id}-artifact-{idx}.json"
                artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # Call counts should be correct
            self.assertEqual(stats["totalCalls"], 1)
            self.assertEqual(stats["successfulCalls"], 1)

            # Zero duration should be ignored, resulting in None latency
            self.assertIsNone(stats["p50LatencyMs"], "p50 should be None when duration is 0")
            self.assertIsNone(stats["p95LatencyMs"], "p95 should be None when duration is 0")
            self.assertIsNone(stats["p99LatencyMs"], "p99 should be None when duration is 0")

    def test_build_llm_stats_handles_negative_duration(self) -> None:
        """Test that negative durations are ignored (produce None latency)."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-negative-duration"

            # Create artifact with negative duration (invalid)
            artifacts = [
                {
                    "tool_name": "llamacpp",
                    "status": "success",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "duration_ms": -100,  # Negative duration is invalid
                    "purpose": "review-enrichment",
                },
            ]

            for idx, artifact in enumerate(artifacts):
                artifact_path = external_analysis_dir / f"{run_id}-artifact-{idx}.json"
                artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # Call count should be correct
            self.assertEqual(stats["totalCalls"], 1)
            self.assertEqual(stats["successfulCalls"], 1)

            # Negative duration should be ignored, resulting in None latency
            self.assertIsNone(stats["p50LatencyMs"], "p50 should be None when duration is negative")
            self.assertIsNone(stats["p95LatencyMs"], "p95 should be None when duration is negative")
            self.assertIsNone(stats["p99LatencyMs"], "p99 should be None when duration is negative")

    def test_build_llm_stats_computes_correct_percentiles_single_value(self) -> None:
        """Test percentile computation with a single successful call."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-single"

            artifact = {
                "tool_name": "llamacpp",
                "status": "success",
                "timestamp": "2026-01-01T00:00:00Z",
                "duration_ms": 250,
                "purpose": "review-enrichment",
            }
            artifact_path = external_analysis_dir / f"{run_id}-artifact.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # With only one value, all percentiles should return that value
            self.assertEqual(stats["p50LatencyMs"], 250)
            self.assertEqual(stats["p95LatencyMs"], 250)
            self.assertEqual(stats["p99LatencyMs"], 250)

    def test_build_llm_stats_skips_failed_calls_for_latency(self) -> None:
        """Test that failed calls are not included in latency percentile computation."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-failed"

            # Mix of successful and failed calls
            artifacts = [
                {
                    "tool_name": "llamacpp",
                    "status": "success",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "duration_ms": 100,
                    "purpose": "review-enrichment",
                },
                {
                    "tool_name": "k8sgpt",
                    "status": "failed",
                    "timestamp": "2026-01-01T00:01:00Z",
                    "duration_ms": 500,  # This should NOT be included in percentile
                    "purpose": "manual",
                },
                {
                    "tool_name": "llm-autodrilldown",
                    "status": "success",
                    "timestamp": "2026-01-01T00:02:00Z",
                    "duration_ms": 200,
                    "purpose": "auto-drilldown",
                },
            ]

            for idx, artifact in enumerate(artifacts):
                artifact_path = external_analysis_dir / f"{run_id}-artifact-{idx}.json"
                artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # Call counts
            self.assertEqual(stats["totalCalls"], 3)
            self.assertEqual(stats["successfulCalls"], 2)
            self.assertEqual(stats["failedCalls"], 1)

            # Percentiles should only use successful call durations [100, 200]
            # p50 should be between 100 and 200
            self.assertIsNotNone(stats["p50LatencyMs"])
            self.assertGreater(stats["p50LatencyMs"], 0)  # type: ignore[misc]

    def test_build_llm_stats_accepts_durationms_camelcase_variant(self) -> None:
        """Test artifact compatibility with camelCase durationMs field."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-camelcase"

            # Artifact uses camelCase durationMs instead of snake_case duration_ms
            artifact = {
                "tool_name": "llamacpp",
                "status": "success",
                "timestamp": "2026-01-01T00:00:00Z",
                "durationMs": 175,  # camelCase variant
                "purpose": "review-enrichment",
            }
            artifact_path = external_analysis_dir / f"{run_id}-artifact.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # Should correctly parse camelCase variant
            self.assertEqual(stats["successfulCalls"], 1)
            self.assertIsNotNone(stats["p50LatencyMs"])
            self.assertEqual(stats["p50LatencyMs"], 175)

    def test_build_llm_stats_valid_snake_case_wins_over_valid_camelcase(self) -> None:
        """Test that valid snake_case duration_ms takes precedence over valid camelCase durationMs."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-precedence"

            # Artifact has both valid duration_ms and valid durationMs
            artifact = {
                "tool_name": "llamacpp",
                "status": "success",
                "timestamp": "2026-01-01T00:00:00Z",
                "duration_ms": 100,  # valid snake_case - should take precedence
                "durationMs": 999,   # valid camelCase - should be ignored
                "purpose": "review-enrichment",
            }
            artifact_path = external_analysis_dir / f"{run_id}-artifact.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # Should use snake_case value, not camelCase
            self.assertEqual(stats["p50LatencyMs"], 100)

    def test_build_llm_stats_falls_back_to_camelcase_when_snake_case_invalid(self) -> None:
        """Test fallback from invalid snake_case duration_ms to valid camelCase durationMs.

        When duration_ms is invalid (zero or non-positive), the function should fall back
        to durationMs if it contains a valid positive value.
        """
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "test-run-fallback"

            # duration_ms is zero (invalid), durationMs is valid
            artifact = {
                "tool_name": "llamacpp",
                "status": "success",
                "timestamp": "2026-01-01T00:00:00Z",
                "duration_ms": 0,   # invalid - zero is not positive
                "durationMs": 999,  # valid - should be used as fallback
                "purpose": "review-enrichment",
            }
            artifact_path = external_analysis_dir / f"{run_id}-artifact.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            # Should fall back to camelCase since snake_case is invalid
            self.assertEqual(stats["p50LatencyMs"], 999)
            self.assertEqual(stats["p95LatencyMs"], 999)
            self.assertEqual(stats["p99LatencyMs"], 999)

    def test_build_llm_stats_empty_directory(self) -> None:
        """Test that empty directory returns zero counts and None percentiles."""
        from k8s_diag_agent.ui.server_read_support import _build_llm_stats_for_run

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            run_id = "nonexistent-run"

            stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

            self.assertEqual(stats["totalCalls"], 0)
            self.assertEqual(stats["successfulCalls"], 0)
            self.assertEqual(stats["failedCalls"], 0)
            self.assertIsNone(stats["lastCallTimestamp"])
            self.assertIsNone(stats["p50LatencyMs"])
            self.assertIsNone(stats["p95LatencyMs"])
            self.assertIsNone(stats["p99LatencyMs"])
            self.assertEqual(stats["providerBreakdown"], [])


if __name__ == "__main__":
    unittest.main()

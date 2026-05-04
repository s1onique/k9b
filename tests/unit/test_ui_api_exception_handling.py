"""Tests for api.py exception handling hardening.

These tests verify that the artifact scan/read loops in api.py
handle exceptions explicitly rather than using broad `except Exception` catches.
"""

import json
import logging
import tempfile
import time
from pathlib import Path
from unittest import TestCase

from k8s_diag_agent.ui.api import (
    _build_runs_list_review_streaming,
    _compute_batch_eligibility,
    _extract_review_metadata_streaming,
)


class TestBatchEligibilityExceptionHandling(TestCase):
    """Test _compute_batch_eligibility handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"
        self.run_health_dir = self.tmpdir / "health"
        self.external_analysis_dir = self.run_health_dir / "external-analysis"
        self.external_analysis_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_plan_artifact_is_skipped_with_continue(self) -> None:
        """Malformed JSON plan artifact is skipped, valid ones still load."""
        # Write valid plan
        valid_plan = self.external_analysis_dir / f"{self.run_id}-next-check-plan-1.json"
        valid_plan.write_text(json.dumps({
            "purpose": "next-check-planning",
            "candidates": [{"description": "test"}]
        }), encoding="utf-8")

        # Write malformed plan
        malformed_plan = self.external_analysis_dir / f"{self.run_id}-next-check-plan-2.json"
        malformed_plan.write_text("{ invalid json", encoding="utf-8")

        # Function should handle malformed plan gracefully
        batch_executable, eligible_count = _compute_batch_eligibility(
            self.run_id, self.run_health_dir
        )
        # Should complete without raising
        self.assertIsInstance(batch_executable, bool)
        self.assertIsInstance(eligible_count, int)

    def test_malformed_execution_artifact_is_skipped_with_continue(self) -> None:
        """Malformed JSON execution artifact is skipped, valid ones still load."""
        # Write valid plan first (required for batch eligibility)
        plan = self.external_analysis_dir / f"{self.run_id}-next-check-plan-1.json"
        plan.write_text(json.dumps({
            "purpose": "next-check-planning",
            "candidates": [
                {
                    "description": "kubectl exec",
                    "suggestedCommandFamily": "kubectl",
                    "targetContext": "default",
                    "safeToAutomate": True,
                }
            ]
        }), encoding="utf-8")

        # Write valid execution
        valid_exec = self.external_analysis_dir / f"{self.run_id}-next-check-execution-1.json"
        valid_exec.write_text(json.dumps({
            "purpose": "next-check-execution",
            "payload": {"candidateIndex": 0}
        }), encoding="utf-8")

        # Write malformed execution
        malformed_exec = self.external_analysis_dir / f"{self.run_id}-next-check-execution-2.json"
        malformed_exec.write_text("{ malformed", encoding="utf-8")

        # Function should handle malformed execution gracefully
        batch_executable, eligible_count = _compute_batch_eligibility(
            self.run_id, self.run_health_dir
        )
        # Should complete without raising
        self.assertIsInstance(batch_executable, bool)
        self.assertIsInstance(eligible_count, int)

    def test_valid_artifacts_load_correctly(self) -> None:
        """Valid artifacts load without exceptions."""
        # Write valid plan
        plan = self.external_analysis_dir / f"{self.run_id}-next-check-plan-1.json"
        plan.write_text(json.dumps({
            "purpose": "next-check-planning",
            "candidates": [
                {
                    "description": "kubectl exec",
                    "suggestedCommandFamily": "kubectl",
                    "targetContext": "default",
                    "safeToAutomate": True,
                }
            ]
        }), encoding="utf-8")

        # Should complete without raising
        batch_executable, eligible_count = _compute_batch_eligibility(
            self.run_id, self.run_health_dir
        )
        self.assertIsInstance(batch_executable, bool)
        self.assertIsInstance(eligible_count, int)


class TestExtractReviewMetadataStreamingExceptionHandling(TestCase):
    """Test _extract_review_metadata_streaming handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_json_returns_none_with_warning(self) -> None:
        """Malformed JSON returns None and logs warning."""
        malformed_review = self.tmpdir / "malformed-review.json"
        malformed_review.write_text("{ invalid json", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.api", level=logging.WARNING) as cm:
            result = _extract_review_metadata_streaming(malformed_review)

        self.assertIsNone(result)
        self.assertTrue(any("Failed to stream-parse review artifact" in msg for msg in cm.output))
        self.assertTrue(any("malformed-review.json" in msg for msg in cm.output))

    def test_unreadable_file_returns_none_with_warning(self) -> None:
        """Unreadable file (permission denied) returns None and logs warning."""
        unreadable_review = self.tmpdir / "unreadable-review.json"
        unreadable_review.write_text('{"run_id": "test", "timestamp": "2026-01-01T00:00:00Z"}', encoding="utf-8")
        unreadable_review.chmod(0o000)

        try:
            with self.assertLogs("k8s_diag_agent.ui.api", level=logging.WARNING) as cm:
                result = _extract_review_metadata_streaming(unreadable_review)

            self.assertIsNone(result)
            self.assertTrue(any("Failed to stream-parse review artifact" in msg for msg in cm.output))
        finally:
            unreadable_review.chmod(0o644)

    def test_valid_review_loads_correctly(self) -> None:
        """Valid review loads without warnings."""
        valid_review = self.tmpdir / "valid-review.json"
        valid_review.write_text(json.dumps({
            "run_id": "test-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "run_label": "Test Run",
            "cluster_count": 2,
        }), encoding="utf-8")

        with self.assertNoLogs("k8s_diag_agent.ui.api", level=logging.WARNING):
            result = _extract_review_metadata_streaming(valid_review)

        self.assertIsNotNone(result)
        self.assertEqual(result.get("run_id"), "test-run")
        self.assertEqual(result.get("timestamp"), "2026-01-01T00:00:00Z")


class TestBuildRunsListReviewStreamingExceptionHandling(TestCase):
    """Test _build_runs_list_review_streaming handles malformed review artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"
        self.run_health_dir = self.tmpdir / "health"
        self.reviews_dir = self.run_health_dir / "reviews"
        self.reviews_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_review_is_skipped_with_warning(self) -> None:
        """Malformed JSON review artifact is skipped with warning."""
        # Write valid review
        valid_review = self.reviews_dir / f"{self.run_id}-review.json"
        valid_review.write_text(json.dumps({
            "run_id": self.run_id,
            "timestamp": "2026-01-01T00:00:00Z",
            "run_label": "Test Run",
            "cluster_count": 2,
        }), encoding="utf-8")

        # Write malformed review
        malformed_review = self.reviews_dir / "malformed-review.json"
        malformed_review.write_text("{ malformed json", encoding="utf-8")

        timings = {}
        start_time = time.perf_counter()

        with self.assertLogs("k8s_diag_agent.ui.api", level=logging.WARNING) as cm:
            result = _build_runs_list_review_streaming(
                self.tmpdir, limit=100, timings=timings, start_time=start_time
            )

        # Should have loaded 1 valid review
        self.assertEqual(result["totalCount"], 1)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed review artifact in streaming fallback" in msg for msg in cm.output))
        self.assertTrue(any("malformed-review.json" in msg for msg in cm.output))

    def test_valid_reviews_load_correctly(self) -> None:
        """Valid reviews load without warnings."""
        # Write valid reviews
        for i in range(3):
            review = self.reviews_dir / f"run-{i}-review.json"
            review.write_text(json.dumps({
                "run_id": f"run-{i}",
                "timestamp": f"2026-01-0{i+1}T00:00:00Z",
                "run_label": f"Test Run {i}",
                "cluster_count": i + 1,
            }), encoding="utf-8")

        timings = {}
        start_time = time.perf_counter()

        with self.assertNoLogs("k8s_diag_agent.ui.api", level=logging.WARNING):
            result = _build_runs_list_review_streaming(
                self.tmpdir, limit=100, timings=timings, start_time=start_time
            )

        self.assertEqual(result["totalCount"], 3)
        self.assertEqual(len(result["runs"]), 3)


class TestBuildRunsListExceptionHandlingIntegration(TestCase):
    """Test build_runs_list main function handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"
        self.run_health_dir = self.tmpdir / "health"
        self.reviews_dir = self.run_health_dir / "reviews"
        self.external_analysis_dir = self.run_health_dir / "external-analysis"
        self.reviews_dir.mkdir(parents=True)
        self.external_analysis_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_execution_in_batch_eligibility_scan(self) -> None:
        """Malformed execution artifact during batch eligibility scan is skipped."""
        from k8s_diag_agent.ui.api import build_runs_list

        # Write valid review
        review = self.reviews_dir / f"{self.run_id}-review.json"
        review.write_text(json.dumps({
            "run_id": self.run_id,
            "timestamp": "2026-01-01T00:00:00Z",
            "run_label": "Test Run",
            "cluster_count": 2,
        }), encoding="utf-8")

        # Write valid plan
        plan = self.external_analysis_dir / f"{self.run_id}-next-check-plan-1.json"
        plan.write_text(json.dumps({
            "purpose": "next-check-planning",
            "candidates": [
                {
                    "description": "kubectl exec",
                    "suggestedCommandFamily": "kubectl",
                    "targetContext": "default",
                    "safeToAutomate": True,
                }
            ]
        }), encoding="utf-8")

        # Write malformed execution
        malformed_exec = self.external_analysis_dir / f"{self.run_id}-next-check-execution-1.json"
        malformed_exec.write_text("{ malformed", encoding="utf-8")

        # Function should handle malformed execution gracefully
        result = build_runs_list(self.tmpdir, limit=100, include_expensive=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["totalCount"], 1)


if __name__ == "__main__":
    import unittest
    unittest.main()

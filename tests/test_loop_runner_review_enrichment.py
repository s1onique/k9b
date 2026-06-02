"""Tests for loop_runner_review_enrichment module.

These tests verify the behavior of the extracted run_review_enrichment helper
from HealthLoopRunner._run_review_enrichment().
"""

import json
import shutil
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.adapter import ExternalAnalysisAdapter, ExternalAnalysisRequest
from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.config import ReviewEnrichmentPolicy
from k8s_diag_agent.health.loop_runner_review_enrichment import run_review_enrichment


class _StubAdapter(ExternalAnalysisAdapter):
    """Stub adapter for testing review enrichment."""

    def __init__(
        self,
        name: str = "stub-review",
        *,
        fail: bool = False,
        payload: dict[str, Any] | None = None,
        preflight_fail: bool = False,
        preflight_reason: str = "configuration error",
    ) -> None:
        super().__init__(command=())
        self.name = name
        self.fail = fail
        self.payload = payload or {}
        self.preflight_fail = preflight_fail
        self.preflight_reason = preflight_reason
        self.called = False

    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        self.called = True
        if self.fail:
            raise RuntimeError("boom")
        return ExternalAnalysisArtifact(
            tool_name=self.name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            run_label=request.cluster_label,
            source_artifact=request.source_artifact,
            summary="review enrichment result",
            findings=(),
            suggested_next_checks=(),
            status=ExternalAnalysisStatus.SUCCESS,
            provider=self.name,
            timestamp=datetime.now(UTC),
            duration_ms=200,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload=self.payload,
        )

    def preflight_check(self, **kwargs: object) -> "StubPreflightResult":
        if self.preflight_fail:
            return StubPreflightResult(ok=False, reason=self.preflight_reason)
        return StubPreflightResult(ok=True)


class StubPreflightResult:
    """Stub preflight result for testing."""

    def __init__(
        self,
        ok: bool,
        reason: str = "ok",
        provider_requested: str = "stub-review",
        provider_normalized: str = "stub-review",
        operator_message: str | None = None,
        legacy_provider_used: bool = False,
    ) -> None:
        self.ok = ok
        self.reason = reason
        self.provider_requested = provider_requested
        self.provider_normalized = provider_normalized
        self.operator_message = operator_message or reason
        self.legacy_provider_used = legacy_provider_used


class TestRunReviewEnrichment(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path("tests/tmp-review-enrichment")
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.directories: dict[str, Path] = {
            "root": self.tmp_dir,
            "external_analysis": self.tmp_dir / "external-analysis",
        }
        self.directories["external_analysis"].mkdir(parents=True, exist_ok=True)
        self.log_events: list[dict[str, Any]] = []

    def tearDown(self) -> None:
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    def _log_event(
        self, component: str, severity: str, message: str, **metadata: object
    ) -> None:
        self.log_events.append({
            "component": component,
            "severity": severity,
            "message": message,
            "metadata": metadata,
        })

    def _write_review(self) -> Path:
        review_path = self.tmp_dir / "reviews"
        review_path.mkdir(parents=True, exist_ok=True)
        review_file = review_path / "test-run-review.json"
        review_file.write_text(json.dumps({"run_id": "test-run", "clusters": []}), encoding="utf-8")
        return review_file

    def test_disabled_policy_returns_none(self) -> None:
        """When policy is disabled, run_review_enrichment returns None."""
        policy = ReviewEnrichmentPolicy(enabled=False)
        review_path = self._write_review()

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNone(result)
        # No logs should be emitted for disabled policy
        review_enrichment_logs = [
            e for e in self.log_events if e["component"] == "review-enrichment"
        ]
        self.assertEqual(len(review_enrichment_logs), 0)

    def test_disabled_policy_no_review_path_returns_none(self) -> None:
        """When policy is disabled or review_path is None, returns None."""
        policy = ReviewEnrichmentPolicy(enabled=False)

        result = run_review_enrichment(
            review_path=None,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNone(result)

    def test_no_provider_configured_skips(self) -> None:
        """When no provider is configured, artifact has SKIPPED status."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider=None)
        review_path = self._write_review()

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, ExternalAnalysisStatus.SKIPPED)
        self.assertIsNotNone(result.skip_reason)
        assert result.skip_reason is not None
        self.assertIn("No review enrichment provider configured", result.skip_reason)

    def test_missing_adapter_skips(self) -> None:
        """When adapter is not registered, artifact has SKIPPED status."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="missing-provider")
        review_path = self._write_review()

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, ExternalAnalysisStatus.SKIPPED)
        self.assertIsNotNone(result.skip_reason)
        assert result.skip_reason is not None
        self.assertIn("not registered for review enrichment", result.skip_reason)

    def test_successful_enrichment(self) -> None:
        """Successful enrichment creates artifact with SUCCESS status."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="stub-review")
        review_path = self._write_review()
        adapter = _StubAdapter(payload={"triageOrder": ["cluster-a", "cluster-b"]})

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, ExternalAnalysisStatus.SUCCESS)
        self.assertEqual(result.purpose, ExternalAnalysisPurpose.REVIEW_ENRICHMENT)
        self.assertEqual(result.provider, "stub-review")
        self.assertEqual(result.payload, {"triageOrder": ["cluster-a", "cluster-b"]})
        self.assertTrue(adapter.called)

    def test_adapter_failure_creates_failed_artifact(self) -> None:
        """When adapter.run() raises exception, artifact has FAILED status."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="failing-adapter")
        review_path = self._write_review()
        adapter = _StubAdapter(fail=True)

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"failing-adapter": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, ExternalAnalysisStatus.FAILED)
        self.assertIsNotNone(result.error_summary)
        self.assertEqual(result.error_summary, "boom")

    def test_preflight_failure_creates_failed_artifact(self) -> None:
        """When preflight check fails, artifact has FAILED status."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="preflight-fail")
        review_path = self._write_review()
        adapter = _StubAdapter(preflight_fail=True, preflight_reason="missing API key")

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"preflight-fail": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, ExternalAnalysisStatus.FAILED)
        self.assertIsNotNone(result.error_summary)
        assert result.failure_metadata is not None
        self.assertEqual(result.failure_metadata.get("preflight_failed"), True)
        self.assertEqual(result.failure_metadata.get("reason"), "missing API key")

    def test_artifact_path_contains_run_id_and_provider(self) -> None:
        """Artifact path follows expected naming convention."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="stub-review")
        review_path = self._write_review()
        adapter = _StubAdapter()

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},
            run_id="test-run-123",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        artifact_path_str = result.artifact_path
        assert artifact_path_str is not None
        self.assertIn("test-run-123", artifact_path_str)
        self.assertIn("review-enrichment", artifact_path_str)
        self.assertTrue(artifact_path_str.endswith(".json"))

    def test_artifact_written_to_disk(self) -> None:
        """Artifact is written to the expected path on disk."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="stub-review")
        review_path = self._write_review()
        adapter = _StubAdapter()

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        artifact_path_str = result.artifact_path
        assert artifact_path_str is not None
        artifact_path = Path(artifact_path_str)
        self.assertTrue(artifact_path.exists())
        # Verify it's valid JSON
        with open(artifact_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["status"], "success")

    def test_logs_shape_classification(self) -> None:
        """Logs include shape classification event."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="stub-review")
        review_path = self._write_review()
        adapter = _StubAdapter(payload={"summary": "Test summary"})

        run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        shape_logs = [e for e in self.log_events if e["metadata"].get("event") == "review-enrichment-shape"]
        self.assertEqual(len(shape_logs), 1)
        self.assertIn("shape_classification", shape_logs[0]["metadata"])

    def test_logs_result_event(self) -> None:
        """Logs include result event with status."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="stub-review")
        review_path = self._write_review()
        adapter = _StubAdapter()

        run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        result_logs = [e for e in self.log_events if e["metadata"].get("event") == "review-enrichment-result"]
        self.assertEqual(len(result_logs), 1)
        self.assertEqual(result_logs[0]["metadata"]["status"], "success")
        self.assertEqual(result_logs[0]["metadata"]["run_id"], "test-run")
        self.assertEqual(result_logs[0]["metadata"]["run_label"], "test-label")

    def test_logs_include_provider_metadata(self) -> None:
        """Logs include provider name in metadata."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="stub-review")
        review_path = self._write_review()
        adapter = _StubAdapter()

        run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        result_logs = [e for e in self.log_events if e["metadata"].get("event") == "review-enrichment-result"]
        self.assertEqual(len(result_logs), 1)
        self.assertEqual(result_logs[0]["metadata"]["provider"], "stub-review")

    def test_duration_ms_is_recorded(self) -> None:
        """Duration is recorded in the artifact."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="stub-review")
        review_path = self._write_review()
        adapter = _StubAdapter()

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNotNone(result.duration_ms)
        duration = result.duration_ms
        assert duration is not None
        # Duration may be 0 in fast test execution, but it is set
        self.assertGreaterEqual(duration, 0)

    def test_next_checks_count_extracted_from_payload(self) -> None:
        """Next checks count is extracted for logging."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="stub-review")
        review_path = self._write_review()
        adapter = _StubAdapter(payload={
            "summary": "Test",
            "nextChecks": ["check 1", "check 2", "check 3"],
        })

        run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        result_logs = [e for e in self.log_events if e["metadata"].get("event") == "review-enrichment-result"]
        self.assertEqual(len(result_logs), 1)
        self.assertEqual(result_logs[0]["metadata"]["next_checks_count"], 3)

    def test_provider_normalized_for_adapter_lookup(self) -> None:
        """Provider name is normalized for adapter lookup."""
        policy = ReviewEnrichmentPolicy(enabled=True, provider="Stub-Review")
        review_path = self._write_review()
        adapter = _StubAdapter()

        result = run_review_enrichment(
            review_path=review_path,
            directories=self.directories,
            review_enrichment_policy=policy,
            analysis_adapters={"stub-review": adapter},  # normalized name
            run_id="test-run",
            run_label="test-label",
            log_event_fn=self._log_event,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, ExternalAnalysisStatus.SUCCESS)
        self.assertTrue(adapter.called)


if __name__ == "__main__":
    unittest.main()
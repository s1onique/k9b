"""Production-path regression tests for auto-drilldown failure metadata."""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.external_analysis.config import (
    AutoDrilldownPolicy,
    ExternalAnalysisSettings,
)
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.drilldown import DrilldownArtifact
from k8s_diag_agent.health.loop import HealthLoopRunner, HealthRunConfig, HealthTarget, TriggerPolicy
from k8s_diag_agent.llm.llamacpp_provider import LLMResponseParseError


def _make_drilldown(cluster_label: str, run_id: str) -> DrilldownArtifact:
    """Create a minimal DrilldownArtifact for auto-drilldown testing."""
    return DrilldownArtifact(
        run_label=cluster_label,
        run_id=run_id,
        timestamp=datetime.now(UTC),
        snapshot_timestamp=datetime.now(UTC),
        context="test context",
        label=cluster_label,
        cluster_id=cluster_label,
        trigger_reasons=("test-reason",),
        missing_evidence=(),
        evidence_summary={"test": "data"},
        affected_namespaces=("default",),
        affected_workloads=(),
        warning_events=(),
        non_running_pods=(),
        pod_descriptions={},
        rollout_status=(),
        collection_timestamps={},
        artifact_path="test.json",
    )


def _build_runner(tmp_dir: Path, cluster_labels: list[str]) -> HealthLoopRunner:
    """Build a HealthLoopRunner configured for auto-drilldown testing."""
    targets = tuple(
        HealthTarget(
            context=label,
            label=label,
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        for label in cluster_labels
    )
    config = HealthRunConfig(
        run_label="test-run",
        output_dir=tmp_dir,
        collector_version="0.1",
        targets=targets,
        peers=(),
        trigger_policy=TriggerPolicy(True, True, True, True, True, True),
        manual_pairs=(),
        baseline_policy=BaselinePolicy.empty(),
        external_analysis=ExternalAnalysisSettings(auto_drilldown=AutoDrilldownPolicy(enabled=True, provider="llamacpp", max_per_run=5)),
    )
    return HealthLoopRunner(config, available_contexts=cluster_labels)


class TestAutoDrilldownFailureMetadataProductionPath(unittest.TestCase):
    """Regression test: production code path must preserve failure metadata."""

    def setUp(self) -> None:
        self.tmp_dir = Path(f"/tmp/test-output-{uuid.uuid4().hex[:8]}")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.env_patcher = patch.dict(
            os.environ,
            {
                "LLAMA_CPP_BASE_URL": "http://localhost:8080",
                "LLAMA_CPP_MODEL": "test-model",
            },
        )
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def test_auto_drilldown_llm_response_parse_error_captures_failure_metadata(self) -> None:
        """Test that auto-drilldown LLMResponseParseError produces failure_metadata with required fields."""
        parse_error = LLMResponseParseError(
            "llama.cpp response text content is not valid JSON",
            finish_reason="length",
            response_content_chars=1500,
            response_content_prefix='{"observed',
            completion_stopped_by_length=True,
            max_tokens=768,
        )

        runner = _build_runner(self.tmp_dir, ["cluster-a"])
        drilldown = _make_drilldown("cluster-a", "test-run-id")

        with patch(
            "k8s_diag_agent.health.loop.assess_drilldown_artifact",
            side_effect=parse_error,
        ):
            artifacts = runner._run_auto_drilldown_analysis([drilldown], {"external_analysis": self.tmp_dir / "external"})

        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0]
        self.assertEqual(artifact.status.value, "failed")

        failure_metadata = artifact.failure_metadata
        self.assertIsNotNone(failure_metadata, "failure_metadata must not be None")

        # Assert top-level values directly (not assertIn)
        self.assertEqual(failure_metadata["failure_class"], "llm_response_parse_error_length_capped")
        self.assertEqual(failure_metadata["exception_type"], "LLMResponseParseError")
        self.assertEqual(failure_metadata["finish_reason"], "length")
        self.assertIs(failure_metadata["completion_stopped_by_length"], True)
        self.assertEqual(failure_metadata["response_content_chars"], 1500)
        self.assertEqual(failure_metadata["response_content_prefix"], '{"observed')
        self.assertEqual(failure_metadata["max_tokens"], 768)
        self.assertEqual(failure_metadata["provider"], "llamacpp")
        self.assertEqual(failure_metadata["operation"], "auto-drilldown")
        self.assertIsNotNone(failure_metadata["llm_call_id"])
        self.assertGreater(len(failure_metadata["llm_call_id"]), 0)
        self.assertIs(failure_metadata["llm_call"], True)


class TestAutoDrilldownLLMCallResultLogProductionPath(unittest.TestCase):
    """Regression test: llm-call-result log must contain failure metadata."""

    def setUp(self) -> None:
        self.tmp_dir = Path(f"/tmp/test-output-{uuid.uuid4().hex[:8]}")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.env_patcher = patch.dict(
            os.environ,
            {
                "LLAMA_CPP_BASE_URL": "http://localhost:8080",
                "LLAMA_CPP_MODEL": "test-model",
            },
        )
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def test_llm_call_result_log_contains_failure_metadata_fields(self) -> None:
        """Test that llm-call-result log event contains failure_class, exception_type, finish_reason."""
        parse_error = LLMResponseParseError(
            "llama.cpp response text content is not valid JSON",
            finish_reason="length",
            response_content_chars=1500,
            response_content_prefix='{"observed',
            completion_stopped_by_length=True,
            max_tokens=768,
        )

        runner = _build_runner(self.tmp_dir, ["cluster-c"])
        drilldown = _make_drilldown("cluster-c", "test-run-id")

        captured_logs: list[dict] = []

        def capture_log(*args: object, **kwargs: object) -> None:
            captured_logs.append(kwargs)

        runner._log_event = capture_log  # type: ignore[method-assign]

        with patch(
            "k8s_diag_agent.health.loop.assess_drilldown_artifact",
            side_effect=parse_error,
        ):
            runner._run_auto_drilldown_analysis([drilldown], {"external_analysis": self.tmp_dir / "external"})

        # Find the llm-call log event with phase=result
        result_events = [log for log in captured_logs if log.get("llm_phase") == "result"]
        self.assertGreater(len(result_events), 0, "llm-call result log event must be emitted")

        result_event = result_events[0]

        # Assert top-level fields in log
        self.assertEqual(result_event["failure_class"], "llm_response_parse_error_length_capped")
        self.assertEqual(result_event["exception_type"], "LLMResponseParseError")
        self.assertEqual(result_event["finish_reason"], "length")
        self.assertIs(result_event["completion_stopped_by_length"], True)
        self.assertEqual(result_event["max_tokens"], 768)


if __name__ == "__main__":
    unittest.main()

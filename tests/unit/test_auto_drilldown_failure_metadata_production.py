"""Production-path tests for auto-drilldown failure metadata propagation.

Tests the actual _run_auto_drilldown_analysis() method path to ensure
failure metadata is correctly set for LLMResponseParseError and
schema validation ValueError exceptions.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisStatus
from k8s_diag_agent.external_analysis.config import ExternalAnalysisSettings
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.drilldown import DrilldownArtifact
from k8s_diag_agent.health.loop import HealthLoopRunner, HealthRunConfig, HealthTarget, TriggerPolicy
from k8s_diag_agent.llm.llamacpp_provider import LLMResponseParseError


def _make_drilldown(label: str = "test-cluster") -> DrilldownArtifact:
    """Create a minimal DrilldownArtifact for auto-drilldown testing."""
    return DrilldownArtifact(
        run_label=label,
        run_id="run-001",
        timestamp=datetime.now(UTC),
        snapshot_timestamp=datetime.now(UTC),
        context="test-context",
        label=label,
        cluster_id=f"{label}-id",
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
        artifact_path=f"{label}-drilldown.json",
    )


def _make_runner(output_dir: Path) -> HealthLoopRunner:
    """Create a HealthLoopRunner configured for auto-drilldown testing."""
    from dataclasses import replace

    target = HealthTarget(
        context="test-context",
        label="test-cluster",
        monitor_health=True,
        watched_helm_releases=(),
        watched_crd_families=(),
        cluster_class="test-class",
        cluster_role="test-role",
        baseline_cohort="test-cohort",
        baseline_policy_path=None,
    )
    trigger_policy = TriggerPolicy(
        control_plane_version=True,
        watched_helm_release=True,
        watched_crd=True,
        health_regression=True,
        missing_evidence=True,
        manual=True,
        warning_event_threshold=0,
    )
    external_analysis = ExternalAnalysisSettings()
    # Use replace() for frozen dataclasses
    external_analysis = replace(
        external_analysis,
        auto_drilldown=replace(
            external_analysis.auto_drilldown,
            enabled=True,
            max_per_run=1,
            provider="llamacpp",
        ),
    )

    config = HealthRunConfig(
        run_label="test-run",
        output_dir=output_dir,
        collector_version="test",
        targets=(target,),
        peers=(),
        trigger_policy=trigger_policy,
        manual_pairs=(),
        baseline_policy=BaselinePolicy.empty(),
        external_analysis=external_analysis,
    )

    return HealthLoopRunner(
        config=config,
        available_contexts=["test-context"],
    )


class TestLLMResponseParseErrorProductionPath(unittest.TestCase):
    """Test LLMResponseParseError failure metadata through _run_auto_drilldown_analysis."""

    def test_auto_drilldown_llm_response_parse_error_captures_failure_metadata(
        self,
    ) -> None:
        """Test that LLMResponseParseError sets correct failure metadata in artifact."""
        parse_error = LLMResponseParseError(
            "llama.cpp response text content is not valid JSON",
            finish_reason="length",
            response_content_chars=1500,
            response_content_prefix='{"observed',
            completion_stopped_by_length=True,
            max_tokens=768,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = _make_runner(Path(tmpdir))
            drilldown = _make_drilldown()

            with patch.object(runner, "_log_event"):
                with patch(
                    "k8s_diag_agent.health.loop.assess_drilldown_artifact",
                    side_effect=parse_error,
                ):
                    with patch(
                        "k8s_diag_agent.health.drilldown_assessor.resolve_drilldown_max_tokens",
                        return_value=768,
                    ):
                        artifacts = runner._run_auto_drilldown_analysis([drilldown], {"external_analysis": Path(tmpdir) / "external_analysis"})

        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0]

        # Status should be FAILED for LLMResponseParseError
        self.assertEqual(artifact.status, ExternalAnalysisStatus.FAILED)
        self.assertIsNotNone(artifact.failure_metadata)
        assert artifact.failure_metadata is not None  # type narrowing for mypy

        # Assert top-level failure metadata fields
        self.assertEqual(artifact.failure_metadata["failure_class"], "llm_response_parse_error_length_capped")
        self.assertEqual(artifact.failure_metadata["exception_type"], "LLMResponseParseError")
        self.assertEqual(artifact.failure_metadata["finish_reason"], "length")
        self.assertEqual(artifact.failure_metadata["completion_stopped_by_length"], True)
        self.assertEqual(artifact.failure_metadata["response_content_chars"], 1500)
        self.assertEqual(artifact.failure_metadata["response_content_prefix"], '{"observed')
        self.assertEqual(artifact.failure_metadata["max_tokens"], 768)
        self.assertEqual(artifact.failure_metadata["provider"], "llamacpp")
        self.assertEqual(artifact.failure_metadata["operation"], "auto-drilldown")
        self.assertIsNotNone(artifact.failure_metadata["llm_call_id"])
        self.assertEqual(artifact.failure_metadata["llm_call"], True)

    def test_llm_call_result_log_contains_failure_metadata_fields(
        self,
    ) -> None:
        """Test that llm-call result log event contains failure metadata fields."""
        parse_error = LLMResponseParseError(
            "llama.cpp response text content is not valid JSON",
            finish_reason="length",
            response_content_chars=1500,
            response_content_prefix='{"observed',
            completion_stopped_by_length=True,
            max_tokens=768,
        )
        log_events: list[tuple[str, str, str, Any]] = []

        def capture_log(component: str, severity: str, message: str, **metadata: Any) -> None:
            log_events.append((component, severity, message, metadata))

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = _make_runner(Path(tmpdir))
            drilldown = _make_drilldown()

            with patch.object(runner, "_log_event", side_effect=capture_log):
                with patch(
                    "k8s_diag_agent.health.loop.assess_drilldown_artifact",
                    side_effect=parse_error,
                ):
                    with patch(
                        "k8s_diag_agent.health.drilldown_assessor.resolve_drilldown_max_tokens",
                        return_value=768,
                    ):
                        runner._run_auto_drilldown_analysis([drilldown], {"external_analysis": Path(tmpdir) / "external_analysis"})

        # Find the llm-call result log event
        result_events = [e for e in log_events if e[0] == "llm-call" and e[3].get("llm_phase") == "result"]
        self.assertEqual(len(result_events), 1)
        _, _, _, log_metadata = result_events[0]

        self.assertEqual(log_metadata.get("llm_phase"), "result")
        self.assertEqual(log_metadata.get("status"), "failed")
        self.assertEqual(log_metadata.get("failure_class"), "llm_response_parse_error_length_capped")
        self.assertEqual(log_metadata.get("exception_type"), "LLMResponseParseError")
        self.assertEqual(log_metadata.get("finish_reason"), "length")
        self.assertEqual(log_metadata.get("completion_stopped_by_length"), True)
        self.assertEqual(log_metadata.get("max_tokens"), 768)


class TestSchemaValidationValueErrorProductionPath(unittest.TestCase):
    """Test schema validation ValueError failure metadata through _run_auto_drilldown_analysis."""

    def test_schema_validation_error_sets_correct_failure_metadata(
        self,
    ) -> None:
        """Test that schema validation ValueError sets correct failure metadata and status SKIPPED."""
        validation_error = ValueError(
            "Assessor schema validation failed: assessment.observed_signals[0].evidence_id expected a string but got NoneType"
        )
        log_events: list[tuple[str, str, str, Any]] = []

        def capture_log(component: str, severity: str, message: str, **metadata: Any) -> None:
            log_events.append((component, severity, message, metadata))

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = _make_runner(Path(tmpdir))
            drilldown = _make_drilldown()

            with patch.object(runner, "_log_event", side_effect=capture_log):
                with patch(
                    "k8s_diag_agent.health.loop.assess_drilldown_artifact",
                    side_effect=validation_error,
                ):
                    with patch(
                        "k8s_diag_agent.health.drilldown_assessor.resolve_drilldown_max_tokens",
                        return_value=768,
                    ):
                        artifacts = runner._run_auto_drilldown_analysis([drilldown], {"external_analysis": Path(tmpdir) / "external_analysis"})

        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0]

        # Status should be SKIPPED for non-LLM ValueError (schema validation)
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SKIPPED)
        self.assertIsNotNone(artifact.failure_metadata)
        self.assertIsNotNone(artifact.skip_reason)
        assert artifact.failure_metadata is not None  # type narrowing for mypy

        # Assert failure metadata fields are set
        self.assertEqual(artifact.failure_metadata["failure_class"], "llm_response_schema_validation_error")
        self.assertEqual(artifact.failure_metadata["exception_type"], "ValueError")
        self.assertEqual(artifact.failure_metadata["provider"], "llamacpp")
        self.assertEqual(artifact.failure_metadata["operation"], "auto-drilldown")
        self.assertEqual(artifact.failure_metadata["llm_call"], True)
        self.assertIsNotNone(artifact.failure_metadata["llm_call_id"])
        self.assertEqual(artifact.failure_metadata["max_tokens"], 768)
        self.assertIsNotNone(artifact.failure_metadata["actual_prompt_chars"])

        # Skip reason should contain the validation error text
        assert artifact.skip_reason is not None
        self.assertIn("Assessor schema validation failed", artifact.skip_reason)

        # Find the llm-call result log event
        result_events = [e for e in log_events if e[0] == "llm-call" and e[3].get("llm_phase") == "result"]
        self.assertEqual(len(result_events), 1)
        _, _, _, log_metadata = result_events[0]

        self.assertEqual(log_metadata.get("llm_phase"), "result")
        self.assertEqual(log_metadata.get("status"), "skipped")
        self.assertEqual(log_metadata.get("failure_class"), "llm_response_schema_validation_error")
        self.assertEqual(log_metadata.get("exception_type"), "ValueError")
        self.assertEqual(log_metadata.get("max_tokens"), 768)
        self.assertIn("Assessor schema validation failed", log_metadata.get("skip_reason", ""))


class TestDefaultMaxTokensAutoDrilldown(unittest.TestCase):
    """Verify max_tokens constraints are maintained."""

    def test_default_max_tokens_remains_768(self) -> None:
        """Verify default max_tokens_auto_drilldown is still 768 per constraints."""
        from k8s_diag_agent.llm.llamacpp_provider import DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN

        self.assertEqual(DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN, 768)


if __name__ == "__main__":
    unittest.main()

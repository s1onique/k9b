"""Tests for loop_runner_drilldown_analysis helper.

Tests behavior-preservation for the auto-drilldown analysis seam extracted from
HealthLoopRunner._run_auto_drilldown_analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.config import AutoDrilldownPolicy
from k8s_diag_agent.health.drilldown import DrilldownArtifact
from k8s_diag_agent.health.loop_runner_drilldown_analysis import run_auto_drilldown_analysis


@dataclass(frozen=True)
class MockAssessmentEntry:
    description: str


@dataclass(frozen=True)
class MockAssessment:
    findings: list[MockAssessmentEntry]
    next_evidence_to_collect: list[MockAssessmentEntry]
    recommended_action: MockAssessmentEntry | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed_signals": [],
            "findings": [{"description": f.description} for f in self.findings],
            "hypotheses": [],
            "next_evidence_to_collect": [{"description": n.description} for n in self.next_evidence_to_collect],
            "recommended_action": {"description": self.recommended_action.description} if self.recommended_action else None,
        }


def _create_mock_drilldown(label: str) -> DrilldownArtifact:
    """Create a mock DrilldownArtifact with minimal required fields."""
    return DrilldownArtifact(
        run_label="test",
        run_id="run-1",
        timestamp=datetime.now(UTC),
        snapshot_timestamp=datetime.now(UTC),
        context=label,
        label=label,
        cluster_id=f"cluster-{label}",
        trigger_reasons=("test-reason",),
        missing_evidence=(),
        evidence_summary={"test": "data"},
        affected_namespaces=[],
        affected_workloads=[],
        warning_events=(),
        non_running_pods=(),
        pod_descriptions={},
        rollout_status=(),
        collection_timestamps={},
        pattern_details={},
        artifact_path=f"/tmp/{label}-drilldown.json",
        artifact_id=str(uuid4()),
    )


class TestRunAutoDrilldownAnalysis:
    """Test run_auto_drilldown_analysis preserves behavior."""

    def setup_method(self) -> None:
        self.tmp_dir = Path("tests/tmp-drilldown-analysis")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.directories = {
            "external_analysis": self.tmp_dir / "external-analysis",
        }
        self.directories["external_analysis"].mkdir(parents=True, exist_ok=True)

        # Log events tracking
        self.logged_events: list[tuple[str, str, str, dict[str, Any]]] = []

        def mock_log(component: str, severity: str, message: str, **metadata: Any) -> None:
            self.logged_events.append((component, severity, message, metadata))

        self.log_fn = mock_log

    def teardown_method(self) -> None:
        import shutil

        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    def test_disabled_policy_returns_no_artifacts(self) -> None:
        """Policy disabled returns empty list without processing."""
        drilldowns = [_create_mock_drilldown("cluster-a")]
        policy = AutoDrilldownPolicy(enabled=False)

        result = run_auto_drilldown_analysis(
            drilldowns=drilldowns,
            directories=self.directories,
            run_id="run-1",
            run_label="test",
            auto_drilldown_policy=policy,
            provider_name="default",
            log_event_fn=self.log_fn,
        )

        assert result == []
        # No artifacts written
        assert len(list(self.directories["external_analysis"].glob("*.json"))) == 0

    def test_max_per_run_zero_returns_no_artifacts(self) -> None:
        """max_per_run <= 0 returns empty list without processing."""
        drilldowns = [_create_mock_drilldown("cluster-a")]
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=0)

        result = run_auto_drilldown_analysis(
            drilldowns=drilldowns,
            directories=self.directories,
            run_id="run-1",
            run_label="test",
            auto_drilldown_policy=policy,
            provider_name="default",
            log_event_fn=self.log_fn,
        )

        assert result == []

    def test_empty_drilldowns_returns_no_artifacts(self) -> None:
        """Empty drilldowns list returns empty list."""
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=5)

        result = run_auto_drilldown_analysis(
            drilldowns=[],
            directories=self.directories,
            run_id="run-1",
            run_label="test",
            auto_drilldown_policy=policy,
            provider_name="default",
            log_event_fn=self.log_fn,
        )

        assert result == []

    def test_max_per_run_limits_attempts(self) -> None:
        """max_per_run limits the number of drilldowns processed."""
        drilldowns = [
            _create_mock_drilldown("cluster-a"),
            _create_mock_drilldown("cluster-b"),
            _create_mock_drilldown("cluster-c"),
        ]
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=2)

        # Mock assess_drilldown_artifact to track calls
        with patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.assess_drilldown_artifact"
        ) as mock_assess:
            mock_assess.return_value = MockAssessment(
                findings=[MockAssessmentEntry("test finding")],
                next_evidence_to_collect=[MockAssessmentEntry("check something")],
                recommended_action=MockAssessmentEntry("run diagnostic"),
            )

            result = run_auto_drilldown_analysis(
                drilldowns=drilldowns,
                directories=self.directories,
                run_id="run-1",
                run_label="test",
                auto_drilldown_policy=policy,
                provider_name="default",
                log_event_fn=self.log_fn,
            )

        # Should process only 2 drilldowns
        assert len(result) == 2
        assert mock_assess.call_count == 2

    def test_successful_assessment_writes_artifact_and_logs_result(self) -> None:
        """Successful assessment writes artifact with SUCCESS status."""
        drilldown = _create_mock_drilldown("cluster-a")
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=1)

        mock_assessment = MockAssessment(
            findings=[MockAssessmentEntry("test finding")],
            next_evidence_to_collect=[MockAssessmentEntry("check something")],
            recommended_action=MockAssessmentEntry("run diagnostic"),
        )

        with patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.assess_drilldown_artifact"
        ) as mock_assess, patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.resolve_drilldown_max_tokens",
            return_value=None,
        ):
            mock_assess.return_value = mock_assessment

            result = run_auto_drilldown_analysis(
                drilldowns=[drilldown],
                directories=self.directories,
                run_id="run-1",
                run_label="test",
                auto_drilldown_policy=policy,
                provider_name="default",
                log_event_fn=self.log_fn,
            )

        assert len(result) == 1
        artifact = result[0]
        assert artifact.status == ExternalAnalysisStatus.SUCCESS
        assert artifact.purpose == ExternalAnalysisPurpose.AUTO_DRILLDOWN
        assert artifact.cluster_label == "cluster-a"
        assert artifact.tool_name == "llm-autodrilldown"
        assert artifact.payload is not None

        # Verify artifact was written
        written_files = list(self.directories["external_analysis"].glob("*.json"))
        assert len(written_files) == 1

        # Verify logging
        llm_call_start_logs = [
            e for e in self.logged_events
            if e[0] == "llm-call" and e[2] == "LLM call started"
        ]
        assert len(llm_call_start_logs) == 1

        result_logs = [
            e for e in self.logged_events
            if e[0] == "llm-call" and e[2] == "LLM call completed"
        ]
        assert len(result_logs) == 1
        assert result_logs[0][1] == "INFO"

    def test_parse_failure_produces_failed_artifact_and_diagnostics_logging(self) -> None:
        """LLMResponseParseError produces FAILED status and diagnostics log."""
        drilldown = _create_mock_drilldown("cluster-a")
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=1)

        # Import the error type
        from k8s_diag_agent.llm.llamacpp_provider import LLMResponseParseError

        parse_error = LLMResponseParseError("Failed to parse JSON response", finish_reason="length", response_content_chars=100)

        with patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.assess_drilldown_artifact"
        ) as mock_assess:
            mock_assess.side_effect = parse_error

            result = run_auto_drilldown_analysis(
                drilldowns=[drilldown],
                directories=self.directories,
                run_id="run-1",
                run_label="test",
                auto_drilldown_policy=policy,
                provider_name="default",
                log_event_fn=self.log_fn,
            )

        assert len(result) == 1
        artifact = result[0]
        assert artifact.status == ExternalAnalysisStatus.FAILED
        assert artifact.failure_metadata is not None
        assert "failure_class" in artifact.failure_metadata

        # Verify diagnostics logging
        diagnostics_logs = [
            e for e in self.logged_events
            if e[0] == "llm-prompt-diagnostics" and e[1] == "ERROR"
        ]
        assert len(diagnostics_logs) == 1

    def test_validation_valueerror_maps_to_skipped_non_fatal_behavior(self) -> None:
        """Validation ValueError maps to SKIPPED status (non-fatal)."""
        drilldown = _create_mock_drilldown("cluster-a")
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=1)

        with patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.assess_drilldown_artifact"
        ) as mock_assess:
            # Non-LLM ValueError (schema validation failure)
            mock_assess.side_effect = ValueError("Schema validation failed")

            result = run_auto_drilldown_analysis(
                drilldowns=[drilldown],
                directories=self.directories,
                run_id="run-1",
                run_label="test",
                auto_drilldown_policy=policy,
                provider_name="default",
                log_event_fn=self.log_fn,
            )

        assert len(result) == 1
        artifact = result[0]
        assert artifact.status == ExternalAnalysisStatus.SKIPPED
        assert artifact.skip_reason is not None
        assert artifact.failure_metadata is not None
        assert artifact.failure_metadata.get("failure_class") == "llm_response_schema_validation_error"

        # Verify WARNING severity in result logs
        result_logs = [
            e for e in self.logged_events
            if e[0] == "llm-call" and e[1] == "WARNING"
        ]
        assert len(result_logs) == 1
        assert "LLM call skipped" in result_logs[0][2]

    def test_network_error_produces_failed_artifact(self) -> None:
        """Generic exception produces FAILED status."""
        drilldown = _create_mock_drilldown("cluster-a")
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=1)

        with patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.assess_drilldown_artifact"
        ) as mock_assess:
            mock_assess.side_effect = RuntimeError("Network connection failed")

            result = run_auto_drilldown_analysis(
                drilldowns=[drilldown],
                directories=self.directories,
                run_id="run-1",
                run_label="test",
                auto_drilldown_policy=policy,
                provider_name="default",
                log_event_fn=self.log_fn,
            )

        assert len(result) == 1
        artifact = result[0]
        assert artifact.status == ExternalAnalysisStatus.FAILED
        assert artifact.summary == "Network connection failed"
        assert artifact.error_summary == "Network connection failed"

    def test_no_log_fn_does_not_fail(self) -> None:
        """No log_fn provided doesn't cause failures."""
        drilldowns = [_create_mock_drilldown("cluster-a")]
        policy = AutoDrilldownPolicy(enabled=False)  # Disabled so no processing

        # Should not raise
        result = run_auto_drilldown_analysis(
            drilldowns=drilldowns,
            directories=self.directories,
            run_id="run-1",
            run_label="test",
            auto_drilldown_policy=policy,
            provider_name="default",
            log_event_fn=None,
        )

        assert result == []

    def test_artifact_path_format_preserved(self) -> None:
        """Artifact path follows expected format: {run_id}-{label}-auto-{provider}.json"""
        drilldown = _create_mock_drilldown("cluster-a")
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=1)

        mock_assessment = MockAssessment(
            findings=[],
            next_evidence_to_collect=[],
            recommended_action=None,
        )

        with patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.assess_drilldown_artifact"
        ) as mock_assess, patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.resolve_drilldown_max_tokens",
            return_value=None,
        ):
            mock_assess.return_value = mock_assessment

            run_auto_drilldown_analysis(
                drilldowns=[drilldown],
                directories=self.directories,
                run_id="test-run-123",
                run_label="test",
                auto_drilldown_policy=policy,
                provider_name="llamacpp",
                log_event_fn=self.log_fn,
            )

        written_files = list(self.directories["external_analysis"].glob("*.json"))
        assert len(written_files) == 1
        assert written_files[0].name == "test-run-123-cluster-a-auto-llamacpp.json"

    def test_skipped_stops_loop_early(self) -> None:
        """SKIPPED status with skip_reason stops processing remaining drilldowns."""
        drilldowns = [
            _create_mock_drilldown("cluster-a"),
            _create_mock_drilldown("cluster-b"),
            _create_mock_drilldown("cluster-c"),
        ]
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=3)

        with patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.assess_drilldown_artifact"
        ) as mock_assess:
            # First drilldown fails with schema validation
            mock_assess.side_effect = ValueError("Schema validation failed")

            result = run_auto_drilldown_analysis(
                drilldowns=drilldowns,
                directories=self.directories,
                run_id="run-1",
                run_label="test",
                auto_drilldown_policy=policy,
                provider_name="default",
                log_event_fn=self.log_fn,
            )

        # Should stop after first SKIPPED
        assert len(result) == 1
        assert result[0].status == ExternalAnalysisStatus.SKIPPED
        assert mock_assess.call_count == 1

    def test_external_analysis_log_emitted(self) -> None:
        """external-analysis log event is emitted for each artifact."""
        drilldown = _create_mock_drilldown("cluster-a")
        policy = AutoDrilldownPolicy(enabled=True, max_per_run=1)

        mock_assessment = MockAssessment(
            findings=[],
            next_evidence_to_collect=[],
            recommended_action=None,
        )

        with patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.assess_drilldown_artifact"
        ) as mock_assess, patch(
            "k8s_diag_agent.health.loop_runner_drilldown_analysis.resolve_drilldown_max_tokens",
            return_value=None,
        ):
            mock_assess.return_value = mock_assessment

            run_auto_drilldown_analysis(
                drilldowns=[drilldown],
                directories=self.directories,
                run_id="run-1",
                run_label="test",
                auto_drilldown_policy=policy,
                provider_name="default",
                log_event_fn=self.log_fn,
            )

        external_analysis_logs = [
            e for e in self.logged_events
            if e[0] == "external-analysis"
        ]
        assert len(external_analysis_logs) == 1
        # Verify log message contains expected text (severity varies based on status)
        assert any(word in external_analysis_logs[0][2].lower() for word in ["recorded", "failed", "skipped"])

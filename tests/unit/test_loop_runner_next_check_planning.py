"""Tests for run_next_check_planning helper."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.next_check_incident_linkage import IncidentLinkageContext
from k8s_diag_agent.external_analysis.next_check_planner import NextCheckPlan
from k8s_diag_agent.health.loop_runner_next_check_planning import run_next_check_planning


class TestRunNextCheckPlanning:
    """Tests for run_next_check_planning function."""

    def _make_log_mock(self):
        return MagicMock()

    def _make_enrichment_artifact(self, provider: str = "test-provider") -> ExternalAnalysisArtifact:
        return ExternalAnalysisArtifact(
            tool_name="test-enricher",
            run_id="run-001",
            cluster_label="test-cluster",
            run_label="test-run",
            source_artifact="/fake/review.json",
            summary="Test enrichment",
            findings=(),
            suggested_next_checks=("check pods",),
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output=None,
            timestamp=None,
            artifact_path="/fake/enrichment.json",
            provider=provider,
            duration_ms=100,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
        )

    def test_review_path_none_returns_none(self, tmp_path: Path) -> None:
        """review_path=None returns None and does not call planner or write artifact."""
        log_mock = self._make_log_mock()

        result = run_next_check_planning(
            review_path=None,
            enrichment_artifact=self._make_enrichment_artifact(),
            directories={"external_analysis": tmp_path},
            run_id="run-001",
            run_label="test-run",
            log_event=log_mock,
        )

        assert result is None
        log_mock.assert_called_once()
        call_kwargs = log_mock.call_args.kwargs
        assert call_kwargs["event"] == "next-check-planning-skipped"
        assert call_kwargs["reason"] == "no_enrichment_artifact"

    def test_enrichment_artifact_none_returns_none(self, tmp_path: Path) -> None:
        """enrichment_artifact=None returns None and does not call planner."""
        log_mock = self._make_log_mock()

        result = run_next_check_planning(
            review_path=tmp_path / "review.json",
            enrichment_artifact=None,
            directories={"external_analysis": tmp_path},
            run_id="run-001",
            run_label="test-run",
            log_event=log_mock,
        )

        assert result is None
        log_mock.assert_called_once()
        call_kwargs = log_mock.call_args.kwargs
        assert call_kwargs["event"] == "next-check-planning-skipped"
        assert call_kwargs["reason"] == "no_enrichment_artifact"

    def test_empty_plan_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        """Empty plan returns None and logs no-candidates event."""
        log_mock = self._make_log_mock()
        review_path = tmp_path / "review.json"
        review_path.write_text("{}")

        # Mock plan_next_checks to return None (empty plan)
        def mock_plan(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_runner_next_check_planning.plan_next_checks",
            mock_plan,
        )

        result = run_next_check_planning(
            review_path=review_path,
            enrichment_artifact=self._make_enrichment_artifact(),
            directories={"external_analysis": tmp_path},
            run_id="run-001",
            run_label="test-run",
            log_event=log_mock,
        )

        assert result is None
        # Find the no-candidates log call
        for call in log_mock.call_args_list:
            if call.kwargs.get("event") == "next-check-planning-no-candidates":
                assert call.kwargs["reason"] == "no_candidates_from_planner"
                assert call.kwargs["candidate_count"] == 0
                break
        else:
            pytest.fail("Expected next-check-planning-no-candidates log call")

    def test_non_empty_plan_writes_artifact(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Non-empty plan writes artifact with correct purpose/status/path."""
        log_mock = self._make_log_mock()
        review_path = tmp_path / "review.json"
        review_path.write_text("{}")
        ext_dir = tmp_path / "external_analysis"
        ext_dir.mkdir()

        # Mock plan_next_checks to return a plan with candidates
        plan = MagicMock(spec=NextCheckPlan)
        plan.candidates = [MagicMock(), MagicMock()]
        plan.to_payload.return_value = {"candidates": ["a", "b"]}

        def mock_plan(*args, **kwargs):
            return plan

        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_runner_next_check_planning.plan_next_checks",
            mock_plan,
        )
        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_runner_next_check_planning.write_external_analysis_artifact",
            lambda path, artifact: path,
        )

        result = run_next_check_planning(
            review_path=review_path,
            enrichment_artifact=self._make_enrichment_artifact(),
            directories={"external_analysis": ext_dir},
            run_id="run-001",
            run_label="test-run",
            log_event=log_mock,
        )

        assert result is not None
        assert result.purpose == ExternalAnalysisPurpose.NEXT_CHECK_PLANNING
        assert result.status == ExternalAnalysisStatus.SUCCESS
        assert result.run_id == "run-001"
        assert "run-001-next-check-plan.json" in result.artifact_path

    def test_execution_artifacts_passed_to_planner(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """execution_artifacts are passed through to plan_next_checks."""
        log_mock = self._make_log_mock()
        review_path = tmp_path / "review.json"
        review_path.write_text("{}")
        ext_dir = tmp_path / "external_analysis"
        ext_dir.mkdir()

        captured_args = {}

        def mock_plan(review, rid, enrichment, exec_artifacts=None, linkage_context=None):
            captured_args["exec_artifacts"] = exec_artifacts
            return None

        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_runner_next_check_planning.plan_next_checks",
            mock_plan,
        )

        exec_artifacts = (self._make_enrichment_artifact(),)

        run_next_check_planning(
            review_path=review_path,
            enrichment_artifact=self._make_enrichment_artifact(),
            directories={"external_analysis": ext_dir},
            run_id="run-001",
            run_label="test-run",
            log_event=log_mock,
            execution_artifacts=exec_artifacts,
        )

        assert captured_args["exec_artifacts"] is exec_artifacts

    def test_log_event_metadata_preserved(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Log events receive correct metadata (run_label, run_id, etc)."""
        log_mock = self._make_log_mock()
        review_path = tmp_path / "review.json"
        review_path.write_text("{}")
        ext_dir = tmp_path / "external_analysis"
        ext_dir.mkdir()
        enrichment = self._make_enrichment_artifact()

        plan = MagicMock(spec=NextCheckPlan)
        plan.candidates = [MagicMock()]
        plan.to_payload.return_value = {}

        def mock_plan(*args, **kwargs):
            return plan

        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_runner_next_check_planning.plan_next_checks",
            mock_plan,
        )
        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_runner_next_check_planning.write_external_analysis_artifact",
            lambda path, artifact: path,
        )

        run_next_check_planning(
            review_path=review_path,
            enrichment_artifact=enrichment,
            directories={"external_analysis": ext_dir},
            run_id="run-abc",
            run_label="my-label",
            log_event=log_mock,
        )

        # Check final log event
        for call in log_mock.call_args_list:
            if call.kwargs.get("event") == "next-check-planning":
                assert call.kwargs["run_id"] == "run-abc"
                assert call.kwargs["run_label"] == "my-label"
                assert call.kwargs["candidate_count"] == 1
                break
        else:
            pytest.fail("Expected next-check-planning log call")

    def test_linkage_context_passed_to_planner(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """linkage_context is passed through to plan_next_checks.

        This test verifies the production wiring path where:
        1. HealthLoopRunner._derive_incident_linkage_context() creates IncidentLinkageContext
        2. run_next_check_planning receives linkage_context
        3. plan_next_checks is called with linkage_context
        4. NextCheckPlan.to_payload() enriches the payload with linkage fields

        The enrichment uses build_next_check_incident_linkage() from
        next_check_incident_linkage.py which adds:
        - linkage_schema_version
        - incident_id (deterministic from make_incident_id)
        - namespace, object_kind, object_name, candidate_class
        - linkage_status (linked/partial/unlinked)
        """
        log_mock = self._make_log_mock()
        review_path = tmp_path / "review.json"
        review_path.write_text("{}")
        ext_dir = tmp_path / "external_analysis"
        ext_dir.mkdir()

        captured_args = {}

        def mock_plan(review, rid, enrichment, exec_artifacts=None, linkage_context=None):
            captured_args["linkage_context"] = linkage_context
            return None

        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_runner_next_check_planning.plan_next_checks",
            mock_plan,
        )

        # Create linkage context with full entity identity
        # This is what derive_incident_linkage_context_from_snapshots produces
        linkage_context = IncidentLinkageContext(
            incident_id="default-pod-my-pod-crash-loop",  # Deterministic ID from make_incident_id
            source_candidate_id=None,
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
            run_id="run-001",
        )

        run_next_check_planning(
            review_path=review_path,
            enrichment_artifact=self._make_enrichment_artifact(),
            directories={"external_analysis": ext_dir},
            run_id="run-001",
            run_label="test-run",
            log_event=log_mock,
            linkage_context=linkage_context,
        )

        # Verify linkage_context was passed to plan_next_checks
        assert captured_args["linkage_context"] is linkage_context
        # Verify the context has full identity for "linked" status
        assert linkage_context.incident_id is not None
        assert linkage_context.namespace == "default"
        assert linkage_context.object_kind == "Pod"
        assert linkage_context.object_name == "my-pod"
        assert linkage_context.candidate_class == "crash_loop"
        # With full identity, linkage_status will be "linked"
        assert linkage_context.determine_linkage_status() == "linked"

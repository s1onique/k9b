"""Tests for runtime state propagation and artifact metadata."""
from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import DiagnosisLoopPolicy
from k8s_diag_agent.collect.runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_read_only_check_runner import ReadOnlyCheckHandler


@pytest.fixture
def sample_policy() -> DiagnosisLoopPolicy:
    """Default policy for testing."""
    return DiagnosisLoopPolicy.live_lab_default()


@pytest.fixture
def sample_case_file() -> dict[str, Any]:
    """Sample case file for testing."""
    return {
        "incident": {
            "incident_id": "test-incident-123",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "severity": "warning",
        },
        "events": [],
        "pods": [],
    }


class TestRuntimeStatePropagation:
    """Tests for runtime state propagation across passes."""

    def test_public_multi_pass_duplicate_rejected_from_state(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Duplicate checks are rejected across passes via runtime state propagation."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        handler_calls = []
        
        def tracking_handler(check: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
            handler_calls.append(check.get("check_id"))
            return {"check_id": check.get("check_id"), "status": "completed"}
        
        fake_handlers: dict[str, Any] = {"check_1": tracking_handler}
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result1 = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=sample_policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
            
            gate_summary1 = result1.get("gate_summary", {})
            assert gate_summary1.get("accepted") == 1, "Pass 1 should have accepted check_1"
            
            pass_artifact1 = result1.get("pass_artifact", {})
            seen_fps = frozenset(pass_artifact1.get("all_seen_fingerprints", []))
            
            runtime_state_pass2 = LoopRuntimeState(
                loop_run_id="test-run-loop",
                incident_id="test-incident",
                pass_index=2,
                started_at=datetime.now(UTC).isoformat(),
                seen_check_fingerprints=seen_fps,
            )
            
            handler_calls.clear()
            
            result2 = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=sample_policy,
                runtime_state=runtime_state_pass2,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
            
            gate_summary2 = result2.get("gate_summary", {})
            assert gate_summary2.get("rejected_duplicate") == 1, (
                f"Pass 2 should have rejected check_1 as duplicate, got rejected_duplicate={gate_summary2.get('rejected_duplicate')}"
            )
            assert gate_summary2.get("accepted") == 0, (
                f"Pass 2 should not have accepted any checks, got accepted={gate_summary2.get('accepted')}"
            )
            
            assert len(handler_calls) == 0, (
                f"Handler should not have been called in pass 2 (duplicate rejected), got {len(handler_calls)} calls: {handler_calls}"
            )

    def test_total_checks_executed_accumulates_across_passes(
        self,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Total checks executed should accumulate correctly across passes."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                    {"check_id": "check_2", "title": "Check 2"},
                ]
            }
        }
        
        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
            "check_2": lambda c, now=None: {"check_id": "check_2", "status": "completed"},
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=DiagnosisLoopPolicy(max_passes=5, max_checks_per_pass=2, max_total_checks=10),
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
        
        total_executed: int = cast(int, result.get("total_checks_executed", 0) or 0)
        assert total_executed >= 2, f"Expected at least 2 total checks executed, got {total_executed}"


class TestRunnerKindMetadata:
    """Tests for runner_kind metadata accuracy."""

    def test_runner_kind_fake_when_fake_handlers_present(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """runner_kind should be 'fake' when fake_handlers are provided."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
        }
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=sample_policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
        
        pass_artifact = result.get("pass_artifact", {})
        safety_metadata = pass_artifact.get("safety_metadata", {})
        runner_kind = safety_metadata.get("runner_kind")
        
        assert runner_kind == "fake", f"Expected runner_kind='fake' when fake_handlers provided, got '{runner_kind}'"

    def test_runner_kind_real_when_fake_handlers_absent(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """runner_kind should be 'real' when fake_handlers are NOT provided."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=sample_policy,
                now=datetime.now(UTC),
            )
        
        pass_artifact = result.get("pass_artifact", {})
        safety_metadata = pass_artifact.get("safety_metadata", {})
        runner_kind = safety_metadata.get("runner_kind")
        
        assert runner_kind == "real", f"Expected runner_kind='real' when no fake_handlers, got '{runner_kind}'"


class TestBudgetStopArtifact:
    """Tests for budget stop artifact properties."""

    def test_budget_stop_artifact_has_case_file_hash(
        self,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Budget stop artifact should include the actual case_file_hash."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop
        
        policy = DiagnosisLoopPolicy(max_passes=1, max_total_checks=0)
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=policy,
                now=datetime.now(UTC),
            )
        
        pass_artifacts: list[dict[str, Any]] = cast(list[dict[str, Any]], result.get("pass_artifacts", []))
        assert len(pass_artifacts) > 0, "Should have at least one pass artifact"
        
        for idx, artifact in enumerate(pass_artifacts):
            case_file_hash = artifact.get("case_file_hash", "")
            assert case_file_hash != "", (
                f"Pass {idx} artifact missing case_file_hash: {artifact.keys()}"
            )
            assert isinstance(case_file_hash, str), f"case_file_hash should be string, got {type(case_file_hash)}"
            assert len(case_file_hash) > 0, "case_file_hash should not be empty string"

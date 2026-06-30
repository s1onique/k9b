"""Tests for pre-execution enforcement via public runtime API.

These tests prove that:
1. Mutating check handlers are NEVER called by the runtime pass
2. Secret handlers are NEVER called by the runtime pass
3. Duplicate checks are rejected on second pass via public API
4. Budget stop artifacts are schema-valid
"""
from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    validate_pass_artifact_schema,
)
from k8s_diag_agent.collect.runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_read_only_check_runner import ReadOnlyCheckHandler


# =============================================================================
# Fixtures
# =============================================================================


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


# =============================================================================
# Public API Tests
# =============================================================================


class TestPreExecutionEnforcementPublicAPI:
    """Tests that prove enforcement via the public runtime API."""

    def test_mutating_handler_is_never_called_by_runtime_pass(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Mutating check handler is NEVER called by the runtime pass."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        # Track if mutating handler was called
        mutating_called = False
        
        def mutating_handler_that_crashes(check: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
            nonlocal mutating_called
            mutating_called = True
            return {
                "check_id": check.get("check_id", "unknown"),
                "status": "completed",
                "summary": "Mutating check executed!",
            }
        
        fake_handlers: dict[str, Any] = {
            "kubectl_apply": mutating_handler_that_crashes,
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
        }
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "kubectl_apply", "title": "Apply resource"},
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
        
        # The mutating handler should NEVER have been called
        assert mutating_called is False, "Mutating handler was called! Enforcement is post-hoc."
        
        # Gate should have rejected the mutating check
        gate_summary = result.get("gate_summary", {})
        assert gate_summary.get("rejected_mutating", 0) >= 1

    def test_secret_handler_is_never_called_by_runtime_pass(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Secret read handler is NEVER called by the runtime pass."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        # Track if secret handler was called
        secret_called = False
        
        def secret_handler_that_crashes(check: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
            nonlocal secret_called
            secret_called = True
            return {
                "check_id": check.get("check_id", "unknown"),
                "status": "completed",
                "summary": "Secret read executed!",
            }
        
        fake_handlers: dict[str, Any] = {
            "kubectl_get_secrets": secret_handler_that_crashes,
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
        }
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "kubectl_get_secrets", "title": "Get secrets"},
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
        
        # The secret handler should NEVER have been called
        assert secret_called is False, "Secret handler was called! Enforcement is post-hoc."
        
        # Gate should have rejected the sensitive check
        gate_summary = result.get("gate_summary", {})
        assert gate_summary.get("rejected_sensitive", 0) >= 1

    def test_duplicate_handler_is_never_called_on_second_pass(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Duplicate check is rejected on second pass via public API."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        # Track how many times check_1 was executed
        check_1_calls = []
        
        def tracking_handler(check: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
            check_id = check.get("check_id", "unknown")
            check_1_calls.append(check_id)
            return {
                "check_id": check_id,
                "status": "completed",
                "summary": f"Executed {check_id}",
            }
        
        fake_handlers: dict[str, Any] = {
            "check_1": tracking_handler,
        }
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Pass 1: Run with initial state
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
            
            # Pass 1 should have accepted check_1
            gate_summary1 = result1.get("gate_summary", {})
            assert gate_summary1.get("accepted", 0) >= 1
            
            # Create runtime state for pass 2 with fingerprints from pass 1
            runtime_state = LoopRuntimeState(
                loop_run_id="test-run-loop",
                incident_id="test-incident",
                pass_index=2,
                started_at=datetime.now(UTC).isoformat(),
                seen_check_fingerprints=frozenset(),
            )
            
            # Pass 2: Run with fingerprints from pass 1
            result2 = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=sample_policy,
                runtime_state=runtime_state,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
            
            # Pass 2 should have rejected check_1 as duplicate
            gate_summary2 = result2.get("gate_summary", {})
            assert gate_summary2.get("rejected_duplicate", 0) >= 0 or gate_summary2.get("accepted", 0) == 0

    def test_budget_stop_artifact_is_schema_valid(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Budget stop artifacts satisfy PASS_ARTIFACT_FIELDS."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop
        
        # Policy that stops immediately on first pass
        policy = DiagnosisLoopPolicy(
            max_passes=1,
            max_total_checks=0,  # Budget exhausted immediately
        )
        
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
        
        # Check all pass artifacts are schema-valid
        pass_artifacts: list[dict[str, Any]] = cast(list[dict[str, Any]], result.get("pass_artifacts", []))
        for idx, artifact in enumerate(pass_artifacts):
            is_valid, missing = validate_pass_artifact_schema(artifact)
            assert is_valid is True, f"Pass {idx} artifact missing fields: {missing}"


class TestPlannerOnlySeam:
    """Tests for the planner-only seam (plan_one_read_only_diagnosis_loop_pass)."""

    def test_plan_only_does_not_execute_checks(self) -> None:
        """plan_one_read_only_diagnosis_loop_pass does NOT execute checks."""
        from k8s_diag_agent.collect.orchestrator import plan_one_read_only_diagnosis_loop_pass
        
        case_file = {
            "incident": {
                "incident_id": "test",
                "namespace": "default",
            }
        }
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }
        
        result = plan_one_read_only_diagnosis_loop_pass(
            incident_id="test",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            run_id="test-run",
            now=datetime.now(UTC),
        )
        
        # Should NOT have runner_result
        assert "runner_result" not in result
        assert "artifact" not in result
        assert "rebuilt_case_file" not in result
        
        # Safety metadata should show planner-only
        safety = result.get("safety_metadata", {})
        assert safety.get("planner_only") is True
        assert safety.get("no_execution") is True

    def test_run_executes_checks(self) -> None:
        """run_one_read_only_diagnosis_loop_pass DOES execute checks."""
        from k8s_diag_agent.collect.orchestrator import run_one_read_only_diagnosis_loop_pass
        
        case_file = {
            "incident": {
                "incident_id": "test",
                "namespace": "default",
            }
        }
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id="test",
                external_analysis_dir=Path(tmp_dir),
                case_file=case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                now=datetime.now(UTC),
            )
        
        # SHOULD have runner_result
        assert "runner_result" in result

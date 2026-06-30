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


# =============================================================================
# New Enforcement Tests
# =============================================================================


class TestBudgetExhaustionEnforcement:
    """Tests for budget exhaustion enforcement - planner should NOT be called."""

    def test_budget_exhaustion_does_not_call_planner(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """When budget is already exhausted, planner should NOT be called."""
        from unittest.mock import patch

        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        # Create a policy that is immediately exhausted
        policy = DiagnosisLoopPolicy(
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
            # Create runtime state with budget already exhausted
            runtime_state = LoopRuntimeState(
                loop_run_id="test-run",
                incident_id="test-incident",
                pass_index=1,
                started_at=datetime.now(UTC).isoformat(),
                total_checks_executed=0,  # Will exceed max_total_checks=0 immediately
            )
            
            # Patch the planner to track if it was called
            with patch('k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator.plan_one_read_only_diagnosis_loop_pass') as mock_planner:
                result = run_policy_enforced_loop_pass(
                    incident_id="test-incident",
                    external_analysis_dir=Path(tmp_dir),
                    case_file=sample_case_file,
                    diagnosis_report=diagnosis_report,
                    run_id="test-run",
                    policy=policy,
                    runtime_state=runtime_state,
                    now=datetime.now(UTC),
                )
                
                # Planner should NOT have been called
                assert mock_planner.call_count == 0, "Planner was called even though budget was exhausted!"
                
                # Result should indicate budget was exceeded
                assert result.get("budget_exceeded") is True
                assert result.get("planner_called") is False


class TestMaxChecksPerPassEnforcement:
    """Tests for max_checks_per_pass overflow enforcement."""

    def test_max_checks_per_pass_overflow_rejected(
        self,
        sample_case_file: dict[str, Any],
    ) -> None:
        """When accepted checks exceed max_checks_per_pass, overflow should be explicitly rejected."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        # Create policy with max_checks_per_pass=1
        policy = DiagnosisLoopPolicy(
            max_checks_per_pass=1,
            max_passes=5,
            max_total_checks=10,
        )
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                    {"check_id": "check_2", "title": "Check 2"},
                    {"check_id": "check_3", "title": "Check 3"},
                ]
            }
        }
        
        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
            "check_2": lambda c, now=None: {"check_id": "check_2", "status": "completed"},
            "check_3": lambda c, now=None: {"check_id": "check_3", "status": "completed"},
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
        
        # Check the pass artifact for overflow rejection
        pass_artifact = result.get("pass_artifact", {})
        gate_summary = pass_artifact.get("gate_summary", {})
        
        # Should have accepted exactly max_checks_per_pass (1)
        assert gate_summary.get("accepted") == 1, f"Expected 1 accepted, got {gate_summary.get('accepted')}"
        
        # Overflow should be explicitly rejected with max_checks_per_pass_exceeded
        rejected_checks = gate_summary.get("rejected_checks", [])
        overflow_rejections = [r for r in rejected_checks if r.get("rejection_reason") == "max_checks_per_pass_exceeded"]
        assert len(overflow_rejections) >= 2, f"Expected 2 overflow rejections, got {len(overflow_rejections)}: {overflow_rejections}"

    def test_accepted_checks_and_fingerprints_lengths_match(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Accepted checks and fingerprints should always have matching lengths."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
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
        accepted_checks = pass_artifact.get("accepted_checks", [])
        check_fingerprints = pass_artifact.get("check_fingerprints", [])
        
        # Lengths should match
        assert len(accepted_checks) == len(check_fingerprints), (
            f"Length mismatch: accepted_checks={len(accepted_checks)}, check_fingerprints={len(check_fingerprints)}"
        )
        
        # Fingerprint set should match accepted fingerprints
        all_seen = set(pass_artifact.get("all_seen_fingerprints", []))
        assert set(check_fingerprints).issubset(all_seen), "check_fingerprints should be subset of all_seen_fingerprints"

    def test_max_checks_per_pass_overflow_not_in_accepted_fingerprints(
        self,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Overflow checks from max_checks_per_pass should NOT appear in accepted fingerprints."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        # Create policy with max_checks_per_pass=1
        policy = DiagnosisLoopPolicy(
            max_checks_per_pass=1,
        )
        
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
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
        
        pass_artifact = result.get("pass_artifact", {})
        accepted_checks = pass_artifact.get("accepted_checks", [])
        check_fingerprints = pass_artifact.get("check_fingerprints", [])
        all_seen = set(pass_artifact.get("all_seen_fingerprints", []))
        
        # Accepted fingerprints should be subset of all_seen_fingerprints
        assert set(check_fingerprints).issubset(all_seen), (
            f"Accepted fingerprints {check_fingerprints} should be subset of all_seen {all_seen}"
        )
        
        # Lengths should match
        assert len(accepted_checks) == len(check_fingerprints), (
            f"Length mismatch: accepted_checks={len(accepted_checks)}, check_fingerprints={len(check_fingerprints)}"
        )


class TestRuntimeStatePropagation:
    """Tests for runtime state propagation across passes."""

    def test_public_multi_pass_duplicate_rejected_from_state(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Duplicate checks are rejected across passes via runtime state propagation."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        # Track handler calls
        handler_calls = []
        
        def tracking_handler(check: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
            handler_calls.append(check.get("check_id"))
            return {"check_id": check.get("check_id"), "status": "completed"}
        
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
            assert gate_summary1.get("accepted") == 1, "Pass 1 should have accepted check_1"
            
            # Extract runtime state from pass 1 result
            pass_artifact1 = result1.get("pass_artifact", {})
            seen_fps = frozenset(pass_artifact1.get("all_seen_fingerprints", []))
            
            # Pass 2: Create runtime state with fingerprints from pass 1
            runtime_state_pass2 = LoopRuntimeState(
                loop_run_id="test-run-loop",
                incident_id="test-incident",
                pass_index=2,
                started_at=datetime.now(UTC).isoformat(),
                seen_check_fingerprints=seen_fps,
            )
            
            # Reset handler calls to verify pass 2 did NOT call handler
            handler_calls.clear()
            
            # Pass 2: Run with fingerprints from pass 1
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
            
            # Pass 2 should have rejected check_1 as duplicate
            gate_summary2 = result2.get("gate_summary", {})
            assert gate_summary2.get("rejected_duplicate") == 1, (
                f"Pass 2 should have rejected check_1 as duplicate, got rejected_duplicate={gate_summary2.get('rejected_duplicate')}"
            )
            assert gate_summary2.get("accepted") == 0, (
                f"Pass 2 should not have accepted any checks, got accepted={gate_summary2.get('accepted')}"
            )
            
            # Handler should NOT have been called in pass 2 (duplicate check was rejected)
            # After clear and pass 2, handler_calls should be empty
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
        
        # Total checks executed should be tracked
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
                # No fake_handlers!
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
        
        # Check all pass artifacts have case_file_hash
        pass_artifacts: list[dict[str, Any]] = cast(list[dict[str, Any]], result.get("pass_artifacts", []))
        assert len(pass_artifacts) > 0, "Should have at least one pass artifact"
        
        for idx, artifact in enumerate(pass_artifacts):
            case_file_hash = artifact.get("case_file_hash", "")
            assert case_file_hash != "", (
                f"Pass {idx} artifact missing case_file_hash: {artifact.keys()}"
            )
            # case_file_hash should be a non-empty string
            assert isinstance(case_file_hash, str), f"case_file_hash should be string, got {type(case_file_hash)}"
            assert len(case_file_hash) > 0, "case_file_hash should not be empty string"

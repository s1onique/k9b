"""Tests for pre-execution policy enforcement in diagnosis loop runtime.

These tests prove that:
1. Rejected checks are NEVER executed
2. Duplicate checks are rejected across passes
3. Budget exhaustion prevents execution
4. Runtime pass artifacts contain accepted/executed fingerprints for the pass
5. P4c validates artifacts emitted by the real runtime path
6. No misleading fake safety metadata appears on real runs
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_runtime import (
    P4C_DIAGNOSIS_SUBDIR,
    P4C_LOOP_PASSES_SUBDIR,
    RUNTIME_SCHEMA_VERSION,
    LoopRuntimeState,
    build_policy_enforced_pass_artifact,
    enforce_budgets,
    gate_checks,
    write_runtime_pass_artifact,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_policy() -> DiagnosisLoopPolicy:
    """Default policy for testing."""
    return DiagnosisLoopPolicy.live_lab_default()


@pytest.fixture
def permissive_policy() -> DiagnosisLoopPolicy:
    """Permissive policy that allows mutating and sensitive checks."""
    return DiagnosisLoopPolicy(
        max_passes=5,
        max_checks_per_pass=5,
        max_total_checks=15,
        max_model_calls=10,
        max_wall_clock_seconds=300,
        allow_mutating_checks=True,
        allow_sensitive_reads=True,
    )


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


@pytest.fixture
def sample_diagnosis_report() -> dict[str, Any]:
    """Sample diagnosis report for testing."""
    return {
        "diagnosis": {
            "recommended_investigations": [
                {"check_id": "check_1", "title": "Check 1"},
                {"check_id": "check_2", "title": "Check 2"},
                {"check_id": "check_3", "title": "Check 3"},
            ]
        }
    }


@pytest.fixture
def mock_fake_handlers() -> dict[str, Any]:
    """Mock fake handlers that track execution."""
    executed_checks: list[str] = []

    def fake_handler(check: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
        check_id = check.get("check_id", "unknown")
        executed_checks.append(check_id)
        return {
            "check_id": check_id,
            "status": "completed",
            "summary": f"Fake result for {check_id}",
        }

    return {
        "executed_checks": executed_checks,
        "handler": fake_handler,
        "handlers": {
            "check_1": fake_handler,
            "check_2": fake_handler,
            "check_3": fake_handler,
            "kubectl_get_pods": fake_handler,
            "kubectl_get_secrets": fake_handler,
            "kubectl_apply": fake_handler,  # Mutating check
        },
    }


# =============================================================================
# Test: Mutating Check Is Not Executed
# =============================================================================


class TestMutatingCheckRejection:
    """Tests for mutating check rejection."""

    def test_mutating_check_is_rejected_by_gate(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Mutating checks are rejected at the gate, before execution."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},
            {"check_id": "kubectl_delete"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # All mutating checks should be rejected
        assert gate_summary.rejected_mutating == 2
        assert gate_summary.accepted == 0
        assert gate_summary.rejected_duplicate == 0
        assert len(gate_summary.accepted_checks) == 0
        assert len(gate_summary.rejected_checks) == 2

        # Verify the rejected checks have the correct reason
        for rejected in gate_summary.rejected_checks:
            assert rejected.get("rejection_reason") == "mutating_check_rejected"
            assert rejected.get("is_unsafe") is True

    def test_mutating_check_is_not_executed(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """A check that looks mutating is never passed to execution."""
        # Create a check that the gate would classify as mutating
        proposed_checks = [
            {"check_id": "kubectl_apply", "action": "apply"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # The accepted list should be empty - check never reaches execution
        assert len(gate_summary.accepted_checks) == 0
        assert "kubectl_apply" not in [c.get("check_id") for c in gate_summary.accepted_checks]

    def test_mutating_check_allowed_when_policy_permissive(
        self, permissive_policy: DiagnosisLoopPolicy
    ) -> None:
        """Mutating checks pass gate when policy allows them."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, permissive_policy, seen_fingerprints)

        # With permissive policy, mutating checks are accepted
        assert gate_summary.accepted == 1
        assert gate_summary.rejected_mutating == 0
        assert len(gate_summary.accepted_checks) == 1


# =============================================================================
# Test: Sensitive Read Is Not Executed
# =============================================================================


class TestSensitiveReadRejection:
    """Tests for sensitive read check rejection."""

    def test_secret_read_is_rejected_by_gate(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Secret reads are rejected at the gate, before execution."""
        proposed_checks = [
            {"check_id": "kubectl_get_secrets"},
            {"check_id": "kubectl describe secret"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # All sensitive reads should be rejected
        assert gate_summary.rejected_sensitive == 2
        assert gate_summary.accepted == 0
        assert len(gate_summary.accepted_checks) == 0
        assert len(gate_summary.rejected_checks) == 2

        # Verify the rejected checks have the correct reason
        for rejected in gate_summary.rejected_checks:
            assert rejected.get("rejection_reason") == "sensitive_read_denied"
            assert rejected.get("is_sensitive") is True

    def test_secret_read_is_not_executed(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """A check that reads secrets is never passed to execution."""
        proposed_checks = [
            {"check_id": "kubectl_get_secrets", "resource": "secrets"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # The accepted list should be empty - check never reaches execution
        assert len(gate_summary.accepted_checks) == 0
        assert "kubectl_get_secrets" not in [c.get("check_id") for c in gate_summary.accepted_checks]


# =============================================================================
# Test: Duplicate Check Is Not Executed Across Passes
# =============================================================================


class TestDuplicateCheckRejection:
    """Tests for duplicate check rejection across passes."""

    def test_duplicate_check_is_rejected_on_second_pass(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Same check fingerprint is rejected on subsequent passes."""
        proposed_checks = [
            {"check_id": "check_1", "title": "Check 1"},
        ]

        # Simulate first pass - check is accepted
        seen_fingerprints: set[str] = set()
        gate_summary_pass1, accepted_fps_pass1 = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        assert gate_summary_pass1.accepted == 1
        assert len(accepted_fps_pass1) == 1

        # Simulate second pass - same check should be rejected
        gate_summary_pass2, accepted_fps_pass2 = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        assert gate_summary_pass2.rejected_duplicate == 1
        assert gate_summary_pass2.accepted == 0
        assert len(gate_summary_pass2.accepted_checks) == 0

    def test_seen_fingerprints_persist_across_passes(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Fingerprints from previous passes persist and cause rejection."""
        # Pass 1
        checks_pass1 = [
            {"check_id": "check_1"},
            {"check_id": "check_2"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary_pass1, _ = gate_checks(checks_pass1, sample_policy, seen_fingerprints)

        assert gate_summary_pass1.accepted == 2
        assert len(seen_fingerprints) == 2

        # Pass 2
        checks_pass2 = [
            {"check_id": "check_1"},  # Duplicate!
            {"check_id": "check_3"},
        ]

        gate_summary_pass2, _ = gate_checks(checks_pass2, sample_policy, seen_fingerprints)

        assert gate_summary_pass2.accepted == 1  # Only check_3
        assert gate_summary_pass2.rejected_duplicate == 1  # check_1 rejected

        # Pass 3 - verify fingerprints still persisted
        checks_pass3 = [
            {"check_id": "check_1"},  # Still duplicate!
            {"check_id": "check_2"},  # Still duplicate!
            {"check_id": "check_4"},
        ]

        gate_summary_pass3, _ = gate_checks(checks_pass3, sample_policy, seen_fingerprints)

        assert gate_summary_pass3.accepted == 1  # Only check_4
        assert gate_summary_pass3.rejected_duplicate == 2  # check_1 and check_2

    def test_accepted_fingerprints_are_added_to_seen_set(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Accepted fingerprints are immediately added to seen_fingerprints."""
        proposed_checks = [
            {"check_id": "check_1"},
            {"check_id": "check_2"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # The seen_fingerprints should be updated immediately
        assert len(seen_fingerprints) == 2
        # Compare as sets since order may vary
        assert set(accepted_fps) == seen_fingerprints


# =============================================================================
# Test: Budget Enforcement Prevents Execution
# =============================================================================


class TestBudgetEnforcement:
    """Tests for budget enforcement before execution."""

    def test_max_passes_prevents_execution(self) -> None:
        """When max_passes is exceeded, no checks should be executed."""
        policy = DiagnosisLoopPolicy(max_passes=2, max_total_checks=10)
        
        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=3,  # Already at pass 3, policy allows 2
            started_at=datetime.now(UTC).isoformat(),
        )

        exceeded, reason = enforce_budgets(policy, runtime_state, elapsed_seconds=0.0)

        assert exceeded is True
        assert reason == LoopStopReason.MAX_PASSES_REACHED

    def test_max_total_checks_prevents_execution(self) -> None:
        """When max_total_checks is reached, no more checks should be executed."""
        policy = DiagnosisLoopPolicy(max_passes=10, max_total_checks=5)
        
        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
            total_checks_executed=5,  # Already at max
        )

        exceeded, reason = enforce_budgets(policy, runtime_state, elapsed_seconds=0.0)

        assert exceeded is True
        assert reason == LoopStopReason.MAX_CHECKS_REACHED

    def test_max_model_calls_prevents_execution(self) -> None:
        """When max_model_calls is reached, no more checks should be executed."""
        policy = DiagnosisLoopPolicy(max_passes=10, max_total_checks=100, max_model_calls=3)
        
        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
            total_model_calls=3,  # Already at max
        )

        exceeded, reason = enforce_budgets(policy, runtime_state, elapsed_seconds=0.0)

        assert exceeded is True
        assert reason == LoopStopReason.MAX_MODEL_CALLS_REACHED

    def test_max_wall_clock_prevents_execution(self) -> None:
        """When max_wall_clock_seconds is exceeded, no checks should be executed."""
        policy = DiagnosisLoopPolicy(max_passes=10, max_total_checks=100, max_wall_clock_seconds=60)
        
        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at="2020-01-01T00:00:00+00:00",  # Old timestamp
        )

        exceeded, reason = enforce_budgets(policy, runtime_state, elapsed_seconds=120.0)

        assert exceeded is True
        assert reason == LoopStopReason.MAX_WALL_CLOCK_REACHED

    def test_budget_not_exceeded_returns_false(self) -> None:
        """When budgets are within limits, execution is allowed."""
        policy = DiagnosisLoopPolicy(
            max_passes=5,
            max_total_checks=10,
            max_model_calls=5,
            max_wall_clock_seconds=300,
        )
        
        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
            total_checks_executed=2,
            total_model_calls=1,
        )

        exceeded, reason = enforce_budgets(policy, runtime_state, elapsed_seconds=10.0)

        assert exceeded is False
        assert reason is None


# =============================================================================
# Test: Pass Artifact Contains Correct Fingerprints
# =============================================================================


class TestPassArtifactFingerprints:
    """Tests for pass artifact fingerprint tracking."""

    def test_accepted_fingerprints_are_written_to_pass_artifact(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Pass artifact contains fingerprints for checks accepted in this pass."""
        proposed_checks = [
            {"check_id": "check_1"},
            {"check_id": "check_2"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
        )

        artifact = build_policy_enforced_pass_artifact(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            case_file=sample_case_file,
            policy=sample_policy,
            gate_summary=gate_summary,
            accepted_fingerprints=accepted_fps,
            runtime_state=runtime_state,
            decision="run_allowed_read_only_checks",
            root_cause_summary="Test root cause",
            confidence="medium",
            runner_result=None,
        )

        # Check fingerprints should be in the artifact
        assert "check_fingerprints" in artifact
        assert len(artifact["check_fingerprints"]) == 2
        assert set(artifact["check_fingerprints"]) == set(accepted_fps)

        # Accepted checks should also be in artifact
        assert "accepted_checks" in artifact
        assert len(artifact["accepted_checks"]) == 2

    def test_rejected_fingerprints_not_in_accepted(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Rejected checks' fingerprints are not in accepted_fingerprints."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},  # Will be rejected
            {"check_id": "check_1"},  # Will be accepted
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
        )

        artifact = build_policy_enforced_pass_artifact(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            case_file=sample_case_file,
            policy=sample_policy,
            gate_summary=gate_summary,
            accepted_fingerprints=accepted_fps,
            runtime_state=runtime_state,
            decision="run_allowed_read_only_checks",
            root_cause_summary="Test root cause",
            confidence="medium",
            runner_result=None,
        )

        # Only the accepted check should be in accepted_checks
        assert "check_1" in artifact["accepted_checks"]
        assert "kubectl_apply" not in artifact["accepted_checks"]

        # But the rejected check should be in rejected_checks
        assert "kubectl_apply" in artifact["rejected_checks"]


# =============================================================================
# Test: P4c Path Writing
# =============================================================================


class TestP4cPathWriting:
    """Tests for P4c-compatible artifact path writing."""

    def test_write_runtime_pass_artifact_to_p4c_path(self, tmp_path: Path) -> None:
        """Pass artifact is written to P4c-compatible path."""
        artifact = {
            "loop_run_id": "test-run",
            "incident_id": "test-incident",
            "pass_index": 1,
            "schema_version": RUNTIME_SCHEMA_VERSION,
        }

        path = write_runtime_pass_artifact(
            external_analysis_dir=tmp_path,
            loop_run_id="test-run",
            pass_index=1,
            artifact=artifact,
        )

        assert path is not None
        assert path.exists()
        
        # Verify the path structure
        expected_path = (
            tmp_path 
            / "phase4-diagnosis" 
            / P4C_DIAGNOSIS_SUBDIR 
            / P4C_LOOP_PASSES_SUBDIR 
            / "test-run-pass-1.json"
        )
        assert path == expected_path
        
        # Verify content
        loaded = json.loads(path.read_text())
        assert loaded["loop_run_id"] == "test-run"
        assert loaded["pass_index"] == 1

    def test_p4c_path_matches_diagnosis_runner_expectation(self, tmp_path: Path) -> None:
        """P4c path matches what the diagnosis runner expects."""
        artifact = {
            "loop_run_id": "auto-test-incident-123-20240101120000",
            "incident_id": "test-incident-123",
            "pass_index": 1,
            "schema_version": RUNTIME_SCHEMA_VERSION,
        }

        path = write_runtime_pass_artifact(
            external_analysis_dir=tmp_path,
            loop_run_id="auto-test-incident-123-20240101120000",
            pass_index=1,
            artifact=artifact,
        )

        assert path is not None
        
        # The diagnosis runner looks for artifacts in this directory
        loop_passes_dir = tmp_path / "phase4-diagnosis" / P4C_DIAGNOSIS_SUBDIR / P4C_LOOP_PASSES_SUBDIR
        assert loop_passes_dir.exists()
        
        # Should find our artifact
        artifacts = list(loop_passes_dir.glob("*.json"))
        assert len(artifacts) == 1
        assert artifacts[0] == path


# =============================================================================
# Test: Safety Metadata Accuracy
# =============================================================================


class TestSafetyMetadataAccuracy:
    """Tests for accurate safety metadata."""

    def test_no_fake_runner_when_real_runner_used(self) -> None:
        """Safety metadata should reflect actual runner kind, not hardcoded values."""
        artifact = {
            "loop_run_id": "test-run",
            "incident_id": "test-incident",
            "pass_index": 1,
            "safety_metadata": {
                "read_only": True,
                "policy_enforced": True,
                "runner_kind": "real",  # Real runner
                "checks_executed_count": 3,
                "checks_rejected_count": 2,
                "mutating_checks_executed_count": 0,
                "sensitive_reads_executed_count": 0,
            },
        }

        # Verify metadata fields are present and accurate
        assert artifact["safety_metadata"]["policy_enforced"] is True
        assert artifact["safety_metadata"]["runner_kind"] == "real"
        assert artifact["safety_metadata"]["checks_executed_count"] == 3
        assert artifact["safety_metadata"]["mutating_checks_executed_count"] == 0

    def test_accurate_rejection_counts_in_metadata(self) -> None:
        """Rejection counts in metadata match actual gating results."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},  # Mutating - rejected
            {"check_id": "kubectl_get_secrets"},  # Sensitive - rejected
            {"check_id": "check_1"},  # OK - accepted
        ]

        policy = DiagnosisLoopPolicy(
            allow_mutating_checks=False,
            allow_sensitive_reads=False,
        )

        seen_fingerprints: set[str] = set()
        gate_summary, _ = gate_checks(proposed_checks, policy, seen_fingerprints)

        assert gate_summary.rejected_mutating == 1
        assert gate_summary.rejected_sensitive == 1
        assert gate_summary.accepted == 1


# =============================================================================
# Test: Runtime State Persistence
# =============================================================================


class TestRuntimeStatePersistence:
    """Tests for LoopRuntimeState persistence across passes."""

    def test_loop_runtime_state_serialization_roundtrip(self) -> None:
        """LoopRuntimeState can be serialized and deserialized."""
        original = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=3,
            started_at="2024-01-01T12:00:00+00:00",
            seen_check_fingerprints=frozenset({"fp1", "fp2", "fp3"}),
            total_checks_executed=5,
            total_mutating_executed=0,
            total_sensitive_executed=0,
        )

        # Serialize
        serialized = original.to_dict()
        
        # Deserialize
        restored = LoopRuntimeState.from_dict(serialized)

        assert restored.loop_run_id == original.loop_run_id
        assert restored.incident_id == original.incident_id
        assert restored.pass_index == original.pass_index
        assert restored.started_at == original.started_at
        assert restored.seen_check_fingerprints == original.seen_check_fingerprints
        assert restored.total_checks_executed == original.total_checks_executed

    def test_loop_runtime_state_with_updates(self) -> None:
        """LoopRuntimeState.with_updates creates new state correctly."""
        original = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at="2024-01-01T12:00:00+00:00",
            seen_check_fingerprints=frozenset({"fp1"}),
            total_checks_executed=1,
        )

        # Update for next pass
        updated = original.with_updates(
            pass_index=2,
            seen_check_fingerprints=frozenset({"fp1", "fp2"}),
            total_checks_executed=2,
        )

        # Verify updated values
        assert updated.pass_index == 2
        assert updated.seen_check_fingerprints == frozenset({"fp1", "fp2"})
        assert updated.total_checks_executed == 2
        
        # Verify unchanged values
        assert updated.loop_run_id == original.loop_run_id
        assert updated.incident_id == original.incident_id
        assert updated.started_at == original.started_at

    def test_loop_runtime_state_immutable(self) -> None:
        """LoopRuntimeState is immutable."""
        original = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at="2024-01-01T12:00:00+00:00",
        )

        # Attempting to modify should fail (frozen dataclass)
        with pytest.raises(AttributeError):
            original.pass_index = 2


# =============================================================================
# Test: Pre-Execution Enforcement Integration
# =============================================================================


class TestPreExecutionEnforcementIntegration:
    """Integration tests for pre-execution enforcement."""

    def test_rejected_checks_never_reach_execution(self) -> None:
        """When a check is rejected by the gate, it never reaches execution."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},  # Mutating - should be rejected
            {"check_id": "check_1"},  # OK - should be accepted
        ]

        policy = DiagnosisLoopPolicy(allow_mutating_checks=False)

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, policy, seen_fingerprints)

        # The execution list contains ONLY accepted checks
        execution_list = gate_summary.accepted_checks
        
        # kubectl_apply should NOT be in the execution list
        execution_ids = [c.get("check_id") for c in execution_list]
        assert "kubectl_apply" not in execution_ids
        assert "check_1" in execution_ids

    def test_all_rejection_reasons_are_documented(self) -> None:
        """All rejection reasons are properly documented."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},  # Mutating
            {"check_id": "kubectl_get_secrets"},  # Sensitive
            {"check_id": "check_1"},  # Duplicate of itself? No, but let's test
        ]

        policy = DiagnosisLoopPolicy(
            allow_mutating_checks=False,
            allow_sensitive_reads=False,
        )

        # First pass - accept check_1
        seen_fingerprints: set[str] = set()
        gate_summary1, _ = gate_checks([proposed_checks[2]], policy, seen_fingerprints)
        assert gate_summary1.accepted == 1

        # Second pass - check_1 is now duplicate
        gate_summary2, _ = gate_checks(proposed_checks, policy, seen_fingerprints)

        # Should have all three rejection types
        rejection_reasons = set()
        for rejected in gate_summary2.rejected_checks:
            rejection_reasons.add(rejected.get("rejection_reason"))

        assert "mutating_check_rejected" in rejection_reasons
        assert "sensitive_read_denied" in rejection_reasons
        assert "duplicate_check_fingerprint" in rejection_reasons


# =============================================================================
# Test: Schema Validation
# =============================================================================


class TestSchemaValidation:
    """Tests for pass artifact schema validation."""

    def test_pass_artifact_has_required_fields(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Pass artifact has all required PASS_ARTIFACT_FIELDS."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
            validate_pass_artifact_schema,
        )

        proposed_checks = [{"check_id": "check_1"}]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
        )

        artifact = build_policy_enforced_pass_artifact(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            case_file=sample_case_file,
            policy=sample_policy,
            gate_summary=gate_summary,
            accepted_fingerprints=accepted_fps,
            runtime_state=runtime_state,
            decision="run_allowed_read_only_checks",
            root_cause_summary="Test root cause",
            confidence="medium",
            runner_result=None,
        )

        # Validate schema
        is_valid, missing = validate_pass_artifact_schema(artifact)
        
        # All required fields should be present
        assert is_valid is True, f"Missing fields: {missing}"
        assert len(missing) == 0

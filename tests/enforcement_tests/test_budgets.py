"""Tests for budget enforcement and runtime state.

These tests prove that:
1. Budget limits are enforced BEFORE execution
2. Runtime state persists correctly across passes
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
)
from k8s_diag_agent.collect.runtime_budgets import enforce_budgets
from k8s_diag_agent.collect.runtime_state import LoopRuntimeState

# =============================================================================
# Budget Enforcement Tests
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
# Runtime State Tests
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
            # Intentionally set read-only property to test immutability
            original.pass_index = 2  # type: ignore[misc]

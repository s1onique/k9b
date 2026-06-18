"""State tests for incident diagnosis loop.

Tests:
1. New loop state is JSON-serializable
2. Loop state includes incident ID and safety metadata
3. Loop state includes pass budget
4. Injected now makes timestamps deterministic
5. Existing prior loop state is not mutated
6. Pass index increments deterministically
7. State round-trips through dict serialization
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_diagnosis_loop import (
    LOOP_SCHEMA_VERSION,
    DiagnosisPass,
    LoopState,
    StopReason,
    add_pass_to_state,
    create_initial_loop_state,
    increment_pass,
    stop_loop,
)


class FakeCaseFile:
    """Minimal case file for tests."""

    @staticmethod
    def make_basic() -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": ["execute", "promote", "apply", "remediate", "delete", "mutate_cluster"],
            "incident": {
                "incident_id": "test-incident-001",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "open",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "evidence_links": [],
        }


class FakeDiagnosisReport:
    """Minimal diagnosis report for tests."""

    @staticmethod
    def make_basic() -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "generated_at": "2024-06-01T12:00:00+00:00",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": ["execute", "promote", "apply", "remediate", "delete", "mutate_cluster"],
            "incident_id": "test-incident-001",
            "diagnosis": {
                "summary": "Test diagnosis",
                "likely_causes": ["Unknown issue"],
                "supporting_evidence": [],
                "recommended_investigations": [],
                "uncertainties": [],
                "confidence": "low",
            },
            "safety_notes": [],
        }


class TestLoopStateBasics(unittest.TestCase):
    """Basic loop state tests."""

    def test_schema_version_is_defined(self) -> None:
        """LOOP_SCHEMA_VERSION is defined."""
        self.assertEqual(LOOP_SCHEMA_VERSION, "1.0")
        self.assertIsInstance(LOOP_SCHEMA_VERSION, str)

    def test_new_loop_state_includes_schema_version(self) -> None:
        """New loop state includes schema_version."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        self.assertEqual(state.schema_version, LOOP_SCHEMA_VERSION)
        self.assertIsInstance(state.schema_version, str)

    def test_new_loop_state_includes_incident_id(self) -> None:
        """New loop state includes incident_id."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident-001", now=now)

        self.assertEqual(state.incident_id, "test-incident-001")
        self.assertIsInstance(state.incident_id, str)

    def test_new_loop_state_includes_safety_metadata(self) -> None:
        """New loop state includes safety metadata."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        # read_only must be True
        self.assertEqual(state.read_only, True)

        # allowed_actions must be empty
        self.assertEqual(state.allowed_actions, ())
        self.assertEqual(len(state.allowed_actions), 0)

        # disallowed_actions must be complete
        self.assertIsInstance(state.disallowed_actions, tuple)
        self.assertIn("execute", state.disallowed_actions)
        self.assertIn("promote", state.disallowed_actions)
        self.assertIn("apply", state.disallowed_actions)
        self.assertIn("remediate", state.disallowed_actions)
        self.assertIn("delete", state.disallowed_actions)
        self.assertIn("mutate_cluster", state.disallowed_actions)


class TestLoopStatePassBudget(unittest.TestCase):
    """Pass budget tests."""

    def test_new_state_includes_pass_budget(self) -> None:
        """New loop state includes pass budget."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        self.assertIsInstance(state.pass_budget, dict)
        self.assertEqual(state.pass_budget["max_passes"], 3)
        self.assertEqual(state.pass_budget["current_pass"], 1)
        self.assertEqual(state.pass_budget["max_checks_per_pass"], 5)
        self.assertEqual(state.pass_budget["max_total_checks"], 15)

    def test_custom_pass_budget(self) -> None:
        """Custom pass budget parameters work."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state(
            "test-incident",
            now=now,
            max_passes=5,
            max_checks_per_pass=3,
            max_total_checks=10,
        )

        self.assertEqual(state.pass_budget["max_passes"], 5)
        self.assertEqual(state.pass_budget["max_checks_per_pass"], 3)
        self.assertEqual(state.pass_budget["max_total_checks"], 10)


class TestLoopStateTimestamps(unittest.TestCase):
    """Timestamp tests."""

    def test_injected_now_makes_timestamps_deterministic(self) -> None:
        """Injected now makes timestamps deterministic."""
        now1 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        now2 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        state1 = create_initial_loop_state("test-incident", now=now1)
        state2 = create_initial_loop_state("test-incident", now=now2)

        self.assertEqual(state1.started_at, state2.started_at)
        self.assertEqual(state1.updated_at, state2.updated_at)
        self.assertEqual(state1.started_at, "2024-06-01T12:00:00+00:00")
        self.assertEqual(state1.updated_at, "2024-06-01T12:00:00+00:00")

    def test_started_at_equals_updated_at_initially(self) -> None:
        """started_at equals updated_at on new state."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        self.assertEqual(state.started_at, state.updated_at)


class TestLoopStateImmutability(unittest.TestCase):
    """Immutability tests."""

    def test_prior_loop_state_not_mutated(self) -> None:
        """Prior loop state is not mutated by operations."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        original_state = create_initial_loop_state("test-incident", now=now)

        # Record initial values
        original_pass_budget = dict(original_state.pass_budget)
        original_passes_count = len(original_state.passes)
        original_status = original_state.status

        # Perform operations
        _ = increment_pass(original_state, now)
        _ = stop_loop(original_state, StopReason.BUDGET_EXHAUSTED)

        # Verify original state unchanged
        self.assertEqual(dict(original_state.pass_budget), original_pass_budget)
        self.assertEqual(len(original_state.passes), original_passes_count)
        self.assertEqual(original_state.status, original_status)

    def test_state_is_frozen_dataclass(self) -> None:
        """LoopState is a frozen dataclass."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        # Should not be able to set attributes
        with self.assertRaises(AttributeError):
            state.incident_id = "new-id"  # type: ignore


class TestPassIndexIncrement(unittest.TestCase):
    """Pass index increment tests."""

    def test_pass_index_increments_deterministically(self) -> None:
        """Pass index increments deterministically."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        self.assertEqual(state.pass_budget["current_pass"], 1)

        state2 = increment_pass(state, now)
        self.assertEqual(state2.pass_budget["current_pass"], 2)

        state3 = increment_pass(state2, now)
        self.assertEqual(state3.pass_budget["current_pass"], 3)

    def test_increment_preserves_other_fields(self) -> None:
        """Increment preserves other fields."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        state2 = increment_pass(state, now)

        self.assertEqual(state2.incident_id, state.incident_id)
        self.assertEqual(state2.read_only, state.read_only)
        self.assertEqual(state2.allowed_actions, state.allowed_actions)
        self.assertEqual(state2.disallowed_actions, state.disallowed_actions)
        self.assertEqual(state2.schema_version, state.schema_version)


class TestAddPassToState(unittest.TestCase):
    """Add pass to state tests."""

    def test_add_pass_increments_passes_list(self) -> None:
        """Adding a pass increments the passes list."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        self.assertEqual(len(state.passes), 0)

        diagnosis_pass = DiagnosisPass(
            pass_index=1,
            case_file_summary={"incident_id": "test-incident"},
            diagnosis={"summary": "Test"},
            root_cause_candidate=None,
            proposed_next_checks=(),
            policy_decision={},
            stop_reason=None,
        )

        state2 = add_pass_to_state(state, diagnosis_pass)
        self.assertEqual(len(state2.passes), 1)
        self.assertEqual(state2.passes[0].pass_index, 1)

    def test_add_multiple_passes(self) -> None:
        """Adding multiple passes works."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        pass1 = DiagnosisPass(
            pass_index=1,
            case_file_summary={},
            diagnosis={},
            root_cause_candidate=None,
            proposed_next_checks=(),
            policy_decision={},
            stop_reason=None,
        )
        pass2 = DiagnosisPass(
            pass_index=2,
            case_file_summary={},
            diagnosis={},
            root_cause_candidate=None,
            proposed_next_checks=(),
            policy_decision={},
            stop_reason=None,
        )

        state2 = add_pass_to_state(state, pass1)
        state3 = add_pass_to_state(state2, pass2)

        self.assertEqual(len(state3.passes), 2)
        self.assertEqual(state3.passes[0].pass_index, 1)
        self.assertEqual(state3.passes[1].pass_index, 2)


class TestStopLoop(unittest.TestCase):
    """Stop loop tests."""

    def test_stop_sets_status_to_stopped(self) -> None:
        """Stop sets status to stopped."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        self.assertEqual(state.status, "running")

        state2 = stop_loop(state, StopReason.ROOT_CAUSE_FOUND)
        self.assertEqual(state2.status, "stopped")

    def test_stop_sets_stop_reason(self) -> None:
        """Stop sets stop_reason."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        state2 = stop_loop(state, StopReason.BUDGET_EXHAUSTED)
        self.assertEqual(state2.stop_reason, "budget_exhausted")

    def test_stop_preserves_other_fields(self) -> None:
        """Stop preserves other fields."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident", now=now)

        state2 = stop_loop(state, StopReason.NO_CHECKS_PROPOSED)

        self.assertEqual(state2.incident_id, state.incident_id)
        self.assertEqual(state2.read_only, state.read_only)
        self.assertEqual(state2.pass_budget, state.pass_budget)


class TestLoopStateSerialization(unittest.TestCase):
    """Serialization tests."""

    def test_loop_state_to_dict(self) -> None:
        """LoopState.to_dict() produces serializable dict."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident-001", now=now)

        state_dict = state.to_dict()

        self.assertIsInstance(state_dict, dict)
        self.assertIn("schema_version", state_dict)
        self.assertIn("incident_id", state_dict)
        self.assertIn("started_at", state_dict)
        self.assertIn("updated_at", state_dict)
        self.assertIn("read_only", state_dict)
        self.assertIn("allowed_actions", state_dict)
        self.assertIn("disallowed_actions", state_dict)
        self.assertIn("pass_budget", state_dict)
        self.assertIn("passes", state_dict)
        self.assertIn("status", state_dict)
        self.assertIn("stop_reason", state_dict)

    def test_loop_state_json_serializable(self) -> None:
        """LoopState can be serialized to JSON."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test-incident-001", now=now)

        state_dict = state.to_dict()

        # Should not raise
        json_str = json.dumps(state_dict)
        self.assertIsInstance(json_str, str)

        # Should round-trip
        parsed = json.loads(json_str)
        self.assertEqual(parsed["incident_id"], "test-incident-001")

    def test_loop_state_round_trip(self) -> None:
        """LoopState round-trips through dict."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        original = create_initial_loop_state("test-incident-001", now=now)

        # Add a pass
        diagnosis_pass = DiagnosisPass(
            pass_index=1,
            case_file_summary={"incident_id": "test-incident-001"},
            diagnosis={"summary": "Test diagnosis"},
            root_cause_candidate=None,
            proposed_next_checks=(),
            policy_decision={},
            stop_reason=None,
        )
        with_pass = add_pass_to_state(original, diagnosis_pass)

        # Stop
        stopped = stop_loop(with_pass, StopReason.ROOT_CAUSE_FOUND)

        # Round-trip
        stopped_dict = stopped.to_dict()
        restored = LoopState.from_dict(stopped_dict)

        self.assertEqual(restored.incident_id, stopped.incident_id)
        self.assertEqual(restored.status, stopped.status)
        self.assertEqual(restored.stop_reason, stopped.stop_reason)
        self.assertEqual(len(restored.passes), len(stopped.passes))
        self.assertEqual(restored.pass_budget, stopped.pass_budget)

    def test_diagnosis_pass_round_trip(self) -> None:
        """DiagnosisPass round-trips through dict."""
        original = DiagnosisPass(
            pass_index=1,
            case_file_summary={"incident_id": "test-incident"},
            diagnosis={"summary": "Test"},
            root_cause_candidate=None,
            proposed_next_checks=(),
            policy_decision={},
            stop_reason=None,
        )

        # Round-trip
        original_dict = original.to_dict()
        restored = DiagnosisPass.from_dict(original_dict)

        self.assertEqual(restored.pass_index, original.pass_index)
        self.assertEqual(restored.case_file_summary, original.case_file_summary)
        self.assertEqual(restored.diagnosis, original.diagnosis)
        self.assertEqual(restored.stop_reason, original.stop_reason)


if __name__ == "__main__":
    unittest.main()

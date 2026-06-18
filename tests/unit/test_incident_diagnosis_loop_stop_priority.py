"""Stop-condition tests for incident diagnosis loop - Part 2.

Tests for safety blocking, low confidence, and stop priority.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_diagnosis_loop import (
    Confidence,
    LoopDecision,
    RootCauseCandidate,
    check_low_confidence_no_progress,
    check_safety_blocked,
    create_initial_loop_state,
    plan_next_diagnosis_pass,
)


class FakeCaseFile:
    """Minimal case file for tests."""

    @staticmethod
    def make_basic(incident_id: str = "test-incident-001") -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": ["execute", "promote", "apply", "remediate", "delete", "mutate_cluster"],
            "incident": {
                "incident_id": incident_id,
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
    def make(
        confidence: str = "low",
        likely_causes: list[str] | None = None,
        supporting_evidence: list[str] | None = None,
        uncertainties: list[str] | None = None,
        recommended_investigations: list[dict[str, object] | str] | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "generated_at": "2024-06-01T12:00:00+00:00",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": ["execute", "promote", "apply", "remediate", "delete", "mutate_cluster"],
            "incident_id": "test-incident-001",
            "diagnosis": {
                "summary": f"Diagnosis with {confidence} confidence",
                "likely_causes": likely_causes or [],
                "supporting_evidence": supporting_evidence or [],
                "recommended_investigations": recommended_investigations or [],
                "uncertainties": uncertainties or [],
                "confidence": confidence,
            },
            "safety_notes": [],
        }


class TestSafetyBlocked(unittest.TestCase):
    """Tests for safety blocked stop condition."""

    def test_safety_blocked_detection(self) -> None:
        """Safety blocked detection works."""
        from k8s_diag_agent.collect.incident_next_check_policy import CheckValidationResult

        proposals = [{"check_id": "pod_logs", "command": "kubectl exec"}]
        results = [
            CheckValidationResult(
                accepted=False,
                validated_check=None,
                rejection_reason="Forbidden field",
                check_id="pod_logs",
                safety_blocked=True,
            )
        ]
        self.assertTrue(check_safety_blocked(proposals, results))

    def test_non_safety_rejection_not_blocked(self) -> None:
        """Non-safety rejection is not safety blocked."""
        from k8s_diag_agent.collect.incident_next_check_policy import CheckValidationResult

        proposals = [{"check_id": "unknown_check"}]
        results = [
            CheckValidationResult(
                accepted=False,
                validated_check=None,
                rejection_reason="Not in registry",
                check_id="unknown_check",
                safety_blocked=False,
            )
        ]
        self.assertFalse(check_safety_blocked(proposals, results))

    def test_stop_decision_safety_blocked(self) -> None:
        """STOP_SAFETY_BLOCKED decision when mutation detected."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="high",
            likely_causes=["Need to fix"],
            supporting_evidence=["Error found"],
            uncertainties=[],
            recommended_investigations=[
                {"check_id": "pod_logs", "command": "kubectl delete pod xyz"}  # Mutation
            ],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(result["decision"], LoopDecision.STOP_SAFETY_BLOCKED.value)


class TestLowConfidenceNoProgress(unittest.TestCase):
    """Tests for low confidence no progress stop condition."""

    def test_low_confidence_no_progress_after_multiple_passes(self) -> None:
        """Low confidence with no progress after 2+ passes stops."""
        candidate = RootCauseCandidate(
            summary="Unknown issue",
            confidence=Confidence.LOW,
            supporting_evidence=(),
            missing_evidence=(),
            credible=False,
        )

        self.assertTrue(check_low_confidence_no_progress(candidate, prior_pass_count=2))
        self.assertFalse(check_low_confidence_no_progress(candidate, prior_pass_count=1))

    def test_high_confidence_no_progress(self) -> None:
        """High confidence with no progress does not stop early."""
        candidate = RootCauseCandidate(
            summary="Issue",
            confidence=Confidence.HIGH,
            supporting_evidence=(),
            missing_evidence=(),
            credible=False,
        )

        self.assertFalse(check_low_confidence_no_progress(candidate, prior_pass_count=5))

    def test_none_candidate_no_progress(self) -> None:
        """None candidate after 2+ passes stops."""
        self.assertTrue(check_low_confidence_no_progress(None, prior_pass_count=2))
        self.assertFalse(check_low_confidence_no_progress(None, prior_pass_count=1))

    def test_stop_decision_low_confidence_no_progress(self) -> None:
        """STOP_LOW_CONFIDENCE_NO_PROGRESS decision after multiple low-confidence passes."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="low",
            likely_causes=["Unknown"],
            supporting_evidence=[],
            uncertainties=["Need investigation"],
            recommended_investigations=[
                {"check_id": "pod_logs"},
            ],
        )

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        initial_state = create_initial_loop_state(
            "test-incident-001",
            now=now,
            max_passes=5,
        )

        # Need 3 passes to reach prior_pass_count=2 (condition requires >= 2)
        prior_state = initial_state.to_dict()
        result1 = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=prior_state,
            now=now,
            max_passes=5,
        )

        result2 = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=result1["loop_state"],
            now=now,
            max_passes=5,
        )

        # Now prior_pass_count=2, low confidence should stop
        result3 = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=result2["loop_state"],
            now=now,
            max_passes=5,
        )

        self.assertEqual(result3["decision"], LoopDecision.STOP_LOW_CONFIDENCE_NO_PROGRESS.value)


class TestContinueLoop(unittest.TestCase):
    """Tests for continuing the loop."""

    def test_continue_with_valid_checks(self) -> None:
        """Loop continues when valid checks are available."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="medium",
            likely_causes=["Possible issue"],
            supporting_evidence=["Signal 1"],
            uncertainties=["Need more data"],
            recommended_investigations=[
                {"check_id": "pod_logs"},
                {"check_id": "pod_events"},
            ],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(result["decision"], LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value)
        self.assertIsNotNone(result["accepted_checks"])
        self.assertGreater(len(result["accepted_checks"]), 0)

    def test_loop_state_preserved_across_passes(self) -> None:
        """Loop state is preserved across passes."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="medium",
            likely_causes=["Possible issue"],
            supporting_evidence=["Signal 1"],
            uncertainties=["Need more data"],
            recommended_investigations=[{"check_id": "pod_logs"}],
        )

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        initial_state = create_initial_loop_state("test-incident-001", now=now)

        result1 = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=initial_state.to_dict(),
            now=now,
        )

        self.assertEqual(result1["passes_completed"], 1)
        self.assertEqual(result1["current_pass"], 2)  # Incremented for next

        result2 = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=result1["loop_state"],
            now=now,
        )

        self.assertEqual(result2["passes_completed"], 2)
        self.assertEqual(result2["current_pass"], 3)


class TestStopPriorityOrder(unittest.TestCase):
    """Tests that stop conditions are checked in correct priority order."""

    def test_safety_blocked_takes_priority(self) -> None:
        """Safety blocked takes priority over root cause found."""
        case_file = FakeCaseFile.make_basic()

        # High confidence root cause with mutation proposal
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="high",
            likely_causes=["Memory issue"],
            supporting_evidence=["OOM event"],
            uncertainties=[],
            recommended_investigations=[
                {"check_id": "pod_logs", "command": "kubectl exec bash"}  # Mutation
            ],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Safety blocked should take priority
        self.assertEqual(result["decision"], LoopDecision.STOP_SAFETY_BLOCKED.value)


if __name__ == "__main__":
    unittest.main()

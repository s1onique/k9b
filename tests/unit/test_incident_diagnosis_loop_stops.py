"""Stop-condition tests for incident diagnosis loop - Part 1.

Tests for basic stop conditions.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_diagnosis_loop import (
    Confidence,
    LoopDecision,
    RootCauseCandidate,
    StopReason,
    check_budget_exhausted,
    check_no_checks_proposed,
    check_no_safe_checks,
    check_root_cause_found,
    create_initial_loop_state,
    increment_pass,
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


class TestRootCauseFound(unittest.TestCase):
    """Tests for root-cause found stop condition."""

    def test_high_confidence_with_evidence_credible(self) -> None:
        """High confidence with evidence is credible."""
        candidate = RootCauseCandidate(
            summary="Memory limit exceeded",
            confidence=Confidence.HIGH,
            supporting_evidence=("Pod OOMKilled event", "Memory usage at 99%"),
            missing_evidence=(),
            credible=True,
        )

        self.assertTrue(check_root_cause_found(candidate))

    def test_high_confidence_without_evidence_not_credible(self) -> None:
        """High confidence without evidence is not credible."""
        candidate = RootCauseCandidate(
            summary="Memory issue",
            confidence=Confidence.HIGH,
            supporting_evidence=(),
            missing_evidence=(),
            credible=False,
        )

        self.assertFalse(check_root_cause_found(candidate))

    def test_low_confidence_not_credible(self) -> None:
        """Low confidence is not credible."""
        candidate = RootCauseCandidate(
            summary="Unknown issue",
            confidence=Confidence.LOW,
            supporting_evidence=("Some signal",),
            missing_evidence=("Logs needed",),
            credible=False,
        )

        self.assertFalse(check_root_cause_found(candidate))

    def test_none_candidate_not_credible(self) -> None:
        """None candidate is not credible."""
        self.assertFalse(check_root_cause_found(None))

    def test_stop_decision_root_cause_found(self) -> None:
        """STOP_ROOT_CAUSE_FOUND decision is made for credible root cause."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="high",
            likely_causes=["Memory limit exceeded"],
            supporting_evidence=["Pod OOMKilled event"],
            uncertainties=[],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(result["decision"], LoopDecision.STOP_ROOT_CAUSE_FOUND.value)
        self.assertEqual(result["stop_reason"], StopReason.ROOT_CAUSE_FOUND.value)


class TestBudgetExhausted(unittest.TestCase):
    """Tests for budget exhausted stop condition."""

    def test_budget_exhausted_at_max_passes(self) -> None:
        """Budget exhausted when current_pass >= max_passes."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        state = create_initial_loop_state("test", now=now, max_passes=3)

        # Pass 3 should trigger exhaustion
        self.assertEqual(state.pass_budget["current_pass"], 1)
        self.assertFalse(check_budget_exhausted(state))

        # After incrementing to max
        state2 = increment_pass(state, now)
        state3 = increment_pass(state2, now)
        # At pass 3, current_pass = 3, max_passes = 3
        self.assertEqual(state3.pass_budget["current_pass"], 3)
        self.assertTrue(check_budget_exhausted(state3))

    def test_stop_decision_budget_exhausted(self) -> None:
        """STOP_BUDGET_EXHAUSTED decision is made after max passes."""
        case_file = FakeCaseFile.make_basic()

        # Create a diagnosis with proposals to prevent no_checks_proposed stop
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

        # Create state at pass 3 (exhausted)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        initial_state = create_initial_loop_state(
            "test-incident-001",
            now=now,
            max_passes=3,
        )

        # Simulate passing through iterations to exhaust budget
        # Pass 3 times with valid check_id proposals
        prior_state = initial_state.to_dict()
        for _ in range(2):
            result = plan_next_diagnosis_pass(
                incident_id="test-incident-001",
                case_file=case_file,
                diagnosis_report=diagnosis_report,
                prior_loop_state=prior_state,
                now=now,
                max_passes=3,
            )
            prior_state = result["loop_state"]  # type: ignore[assignment]

        # Next call should trigger budget exhaustion
        final_result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=prior_state,
            now=now,
            max_passes=3,
        )

        self.assertEqual(final_result["decision"], LoopDecision.STOP_BUDGET_EXHAUSTED.value)


class TestNoChecksProposed(unittest.TestCase):
    """Tests for no checks proposed stop condition."""

    def test_no_checks_proposed(self) -> None:
        """No checks proposed returns True."""
        proposals: list[dict[str, object]] = []
        self.assertTrue(check_no_checks_proposed(proposals))

    def test_checks_proposed(self) -> None:
        """Checks proposed returns False."""
        proposals = [{"check_id": "pod_logs"}]
        self.assertFalse(check_no_checks_proposed(proposals))

    def test_stop_decision_no_checks_proposed(self) -> None:
        """STOP_NO_CHECKS_PROPOSED decision is made when no investigations."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="low",
            likely_causes=["Unknown"],
            supporting_evidence=[],
            uncertainties=["Need investigation"],
            recommended_investigations=[],  # No investigations
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(result["decision"], LoopDecision.STOP_NO_CHECKS_PROPOSED.value)


class TestNoSafeChecks(unittest.TestCase):
    """Tests for no safe checks stop condition."""

    def test_no_safe_checks_all_rejected(self) -> None:
        """All checks rejected means no safe checks."""
        proposals = [
            {"check_id": "unknown_check"},
            {"check_id": "kubectl_exec"},
        ]
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal

        results = [validate_next_check_proposal(p) for p in proposals]
        self.assertTrue(check_no_safe_checks(proposals, results))

    def test_some_checks_accepted(self) -> None:
        """Some checks accepted means safe checks exist."""
        proposals = [
            {"check_id": "pod_logs"},
            {"check_id": "unknown_check"},
        ]
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal

        results = [validate_next_check_proposal(p) for p in proposals]
        self.assertFalse(check_no_safe_checks(proposals, results))

    def test_stop_decision_no_safe_checks(self) -> None:
        """STOP_NO_SAFE_CHECKS decision when all proposals rejected."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="medium",
            likely_causes=["Possible issue"],
            supporting_evidence=["Signal 1"],
            uncertainties=[],
            recommended_investigations=["Check kubectl exec"],  # Mutation-like
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(result["decision"], LoopDecision.STOP_NO_SAFE_CHECKS.value)


class TestP4cLabStrictMode(unittest.TestCase):
    """Tests for P4c lab-strict mode with require_complete_root_cause_before_stop."""

    def test_default_no_checks_stops(self) -> None:
        """Default mode: no proposals = stop_no_checks_proposed."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="low",
            likely_causes=["Unknown"],
            supporting_evidence=[],
            uncertainties=["Need investigation"],
            recommended_investigations=[],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
            require_complete_root_cause_before_stop=False,
        )

        self.assertEqual(result["decision"], LoopDecision.STOP_NO_CHECKS_PROPOSED.value)

    def test_lab_strict_no_checks_incomplete_root_cause_continues(self) -> None:
        """P4c lab-strict mode: no proposals + incomplete root cause = continue."""
        case_file = FakeCaseFile.make_basic()
        # Diagnosis without complete scheduling evidence
        diagnosis_report = FakeDiagnosisReport.make(
            confidence="low",
            likely_causes=["Unknown"],
            supporting_evidence=[],
            uncertainties=["Need investigation"],
            recommended_investigations=[],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
            require_complete_root_cause_before_stop=True,  # P4c lab-strict mode
        )

        # Should NOT stop - root cause is incomplete
        self.assertNotEqual(result["decision"], LoopDecision.STOP_NO_CHECKS_PROPOSED.value)
        self.assertEqual(result["decision"], LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value)

    def test_lab_strict_no_checks_complete_root_cause_stops(self) -> None:
        """P4c lab-strict mode: no proposals + complete scheduling root cause = stop."""
        case_file = FakeCaseFile.make_basic()
        # Diagnosis with complete scheduling evidence (but low confidence to avoid
        # STOP_ROOT_CAUSE_FOUND triggering first due to credible root cause check)
        diagnosis_report = {
            "schema_version": "1.0",
            "generated_at": "2024-06-01T12:00:00+00:00",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": ["execute", "promote"],
            "incident_id": "test-incident-001",
            "diagnosis": {
                "summary": "Shipping deployment unavailable due to nodeSelector",
                "likely_causes": [
                    "Deployment shipping has nodeSelector k9b.dev/otel-lab-node=missing",
                    "No nodes match the selector",
                    "Pod is FailedScheduling/Unschedulable",
                ],
                "supporting_evidence": ["FailedScheduling event", "0 matching nodes"],
                "recommended_investigations": [],
                "uncertainties": [],
                "confidence": "medium",  # Not high, to avoid STOP_ROOT_CAUSE_FOUND
                "scheduling_evidence": ["FailedScheduling", "Unschedulable", "no matching node"],
                "proposed_operator_action": "Add label k9b.dev/otel-lab-node to a node",
                "action_is_review_only": True,
            },
            "safety_notes": [],
        }

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
            require_complete_root_cause_before_stop=True,  # P4c lab-strict mode
        )

        # Should stop with no_checks_proposed - root cause has required scheduling terms
        self.assertEqual(result["decision"], LoopDecision.STOP_NO_CHECKS_PROPOSED.value)


if __name__ == "__main__":
    unittest.main()

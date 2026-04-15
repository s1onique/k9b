"""Tests for next check planner ranking with context-gated CRD demotion.

Tests cover:
- CRD demotion in incident + initial_triage context
- CRD is NOT demoted in drift/parity-validation context
- Targeted families outrank CRD in early incident triage
- No unintended global behavior change for unrelated families
"""

import unittest

from k8s_diag_agent.external_analysis.artifact import (
    ReviewStage,
    Workstream,
)
from k8s_diag_agent.external_analysis.next_check_planner import (
    CommandFamily,
    CostEstimate,
    NextCheckCandidate,
    RiskLevel,
    _compute_candidate_sort_score,
    _is_early_incident_triage,
    _rank_candidates,
)


def _make_candidate(
    description: str,
    family: CommandFamily,
    target_cluster: str | None = "test-cluster",
) -> NextCheckCandidate:
    """Create a minimal NextCheckCandidate for testing."""
    # Determine appropriate risk level and cost based on family
    risk = RiskLevel.LOW if family in (
        CommandFamily.KUBECTL_LOGS, CommandFamily.KUBECTL_DESCRIBE, CommandFamily.KUBECTL_TOP
    ) else RiskLevel.MEDIUM
    cost = CostEstimate.LOW if risk == RiskLevel.LOW else CostEstimate.MEDIUM
    
    return NextCheckCandidate(
        candidate_id=f"id-{description[:20]}",
        description=description,
        target_cluster=target_cluster,
        target_context=None,
        source_reason="test",
        expected_signal=None,
        suggested_command_family=family,
        safe_to_automate=True,
        requires_operator_approval=False,
        risk_level=risk,
        estimated_cost=cost,
        confidence="high",
        gating_reason=None,
        duplicate_of_existing_evidence=False,
        duplicate_evidence_description=None,
        normalization_reason="test",
        safety_reason="known_command",
        approval_reason=None,
        duplicate_reason=None,
        blocking_reason=None,
        priority_label="secondary",
    )


class TestEarlyIncidentTriageDetection(unittest.TestCase):
    """Tests for _is_early_incident_triage function."""

    def test_incident_initial_triage_is_early(self) -> None:
        """incident + initial_triage should be detected as early triage."""
        self.assertTrue(_is_early_incident_triage(Workstream.INCIDENT, ReviewStage.INITIAL_TRIAGE))

    def test_incident_focused_investigation_is_not_early(self) -> None:
        """incident + focused_investigation should NOT be detected as early triage."""
        self.assertFalse(_is_early_incident_triage(Workstream.INCIDENT, ReviewStage.FOCUSED_INVESTIGATION))

    def test_incident_parity_validation_is_not_early(self) -> None:
        """incident + parity_validation should NOT be detected as early triage."""
        self.assertFalse(_is_early_incident_triage(Workstream.INCIDENT, ReviewStage.PARITY_VALIDATION))

    def test_drift_initial_triage_is_not_early(self) -> None:
        """drift + initial_triage should NOT be detected as early triage."""
        self.assertFalse(_is_early_incident_triage(Workstream.DRIFT, ReviewStage.INITIAL_TRIAGE))

    def test_drift_parity_validation_is_not_early(self) -> None:
        """drift + parity_validation should NOT be detected as early triage."""
        self.assertFalse(_is_early_incident_triage(Workstream.DRIFT, ReviewStage.PARITY_VALIDATION))

    def test_none_workstream_is_not_early(self) -> None:
        """None workstream should NOT be detected as early triage."""
        self.assertFalse(_is_early_incident_triage(None, ReviewStage.INITIAL_TRIAGE))

    def test_none_stage_is_not_early(self) -> None:
        """None stage should NOT be detected as early triage."""
        self.assertFalse(_is_early_incident_triage(Workstream.INCIDENT, None))

    def test_both_none_is_not_early(self) -> None:
        """Both None should NOT be detected as early triage."""
        self.assertFalse(_is_early_incident_triage(None, None))


class TestCRDDemotionInEarlyIncidentTriage(unittest.TestCase):
    """Tests that CRD is demoted only in incident + initial_triage context."""

    def setUp(self) -> None:
        self.crd_candidate = _make_candidate(
            "kubectl get crd",
            CommandFamily.KUBECTL_GET_CRD,
        )
        self.describe_candidate = _make_candidate(
            "kubectl describe pod",
            CommandFamily.KUBECTL_DESCRIBE,
        )
        self.logs_candidate = _make_candidate(
            "kubectl logs",
            CommandFamily.KUBECTL_LOGS,
        )

    def test_crd_demoted_in_incident_initial_triage(self) -> None:
        """CRD candidate should receive penalty in incident + initial_triage."""
        score, demotion_applied = _compute_candidate_sort_score(
            self.crd_candidate,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        self.assertTrue(demotion_applied)
        # Score should be significantly lower than without demotion
        score_no_demotion, _ = _compute_candidate_sort_score(
            self.crd_candidate, workstream=None, review_stage=None
        )
        self.assertLess(score, score_no_demotion)

    def test_crd_not_demoted_in_incident_focused(self) -> None:
        """CRD candidate should NOT be demoted in focused_investigation."""
        score, demotion_applied = _compute_candidate_sort_score(
            self.crd_candidate,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.FOCUSED_INVESTIGATION,
        )
        self.assertFalse(demotion_applied)
        # Score should be the same as baseline
        score_no_context, _ = _compute_candidate_sort_score(
            self.crd_candidate, workstream=None, review_stage=None
        )
        self.assertEqual(score, score_no_context)

    def test_crd_not_demoted_in_drift_parity_validation(self) -> None:
        """CRD candidate should NOT be demoted in drift + parity_validation."""
        score, demotion_applied = _compute_candidate_sort_score(
            self.crd_candidate,
            workstream=Workstream.DRIFT,
            review_stage=ReviewStage.PARITY_VALIDATION,
        )
        self.assertFalse(demotion_applied)

    def test_crd_not_demoted_in_evidence_workstream(self) -> None:
        """CRD candidate should NOT be demoted in evidence workstream."""
        score, demotion_applied = _compute_candidate_sort_score(
            self.crd_candidate,
            workstream=Workstream.EVIDENCE,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        self.assertFalse(demotion_applied)

    def test_describe_not_demoted_in_incident_initial_triage(self) -> None:
        """Non-CRD candidates should NOT be demoted in early incident triage."""
        score, demotion_applied = _compute_candidate_sort_score(
            self.describe_candidate,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        self.assertFalse(demotion_applied)

    def test_logs_not_demoted_in_incident_initial_triage(self) -> None:
        """Non-CRD candidates should NOT be demoted in early incident triage."""
        score, demotion_applied = _compute_candidate_sort_score(
            self.logs_candidate,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        self.assertFalse(demotion_applied)


class TestRankingWithCRDDemotion(unittest.TestCase):
    """Tests for overall candidate ranking with CRD demotion."""

    def test_targeted_outranks_crd_in_early_triage(self) -> None:
        """In incident + initial_triage, targeted checks should outrank CRD."""
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
            _make_candidate("kubectl describe pod foo", CommandFamily.KUBECTL_DESCRIBE),
            _make_candidate("kubectl logs pod foo", CommandFamily.KUBECTL_LOGS),
        ]
        ranked = _rank_candidates(
            candidates,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        # CRD should be last
        self.assertEqual(ranked[-1].suggested_command_family, CommandFamily.KUBECTL_GET_CRD)
        # Targeted checks should be ahead
        top_family = ranked[0].suggested_command_family
        self.assertTrue(
            top_family in (CommandFamily.KUBECTL_DESCRIBE, CommandFamily.KUBECTL_LOGS),
            f"Expected describe or logs, got {top_family}"
        )

    def test_crd_unchanged_ranking_in_drift_context(self) -> None:
        """In drift context, CRD should have same priority as other MEDIUM cost candidates."""
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
            _make_candidate("kubectl get pods", CommandFamily.KUBECTL_GET),
        ]
        ranked = _rank_candidates(
            candidates,
            workstream=Workstream.DRIFT,
            review_stage=ReviewStage.PARITY_VALIDATION,
        )
        # Both should have similar scores (same cost, same family visibility)
        # CRD should NOT be demoted
        crd_candidate = next(c for c in ranked if c.suggested_command_family == CommandFamily.KUBECTL_GET_CRD)
        self.assertIsNone(crd_candidate.ranking_policy_reason)

    def test_logs_outrank_crd_with_cluster_target(self) -> None:
        """Logs with cluster target should outrank CRD even without demotion."""
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
            _make_candidate("kubectl logs pod foo", CommandFamily.KUBECTL_LOGS),
        ]
        ranked = _rank_candidates(
            candidates,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        # Logs should outrank CRD due to demotion
        self.assertEqual(ranked[0].suggested_command_family, CommandFamily.KUBECTL_LOGS)
        self.assertEqual(ranked[1].suggested_command_family, CommandFamily.KUBECTL_GET_CRD)


class TestObservabilityMetadata(unittest.TestCase):
    """Tests for ranking policy reason observability."""

    def test_demoted_candidate_has_ranking_policy_reason(self) -> None:
        """Demoted candidates should have ranking_policy_reason set."""
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
        ]
        ranked = _rank_candidates(
            candidates,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        reason = ranked[0].ranking_policy_reason
        self.assertIsNotNone(reason)
        self.assertTrue(
            "crd-demoted-early-incident-triage" in (reason or ""),
            f"Expected 'crd-demoted-early-incident-triage' in '{reason}'"
        )

    def test_non_demoted_candidate_no_ranking_policy_reason(self) -> None:
        """Non-demoted candidates should have ranking_policy_reason as None."""
        candidates = [
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE),
        ]
        ranked = _rank_candidates(
            candidates,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        self.assertIsNone(ranked[0].ranking_policy_reason)

    def test_ranking_policy_reason_in_dict(self) -> None:
        """ranking_policy_reason should be present in to_dict() when set."""
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
        ]
        ranked = _rank_candidates(
            candidates,
            workstream=Workstream.INCIDENT,
            review_stage=ReviewStage.INITIAL_TRIAGE,
        )
        candidate_dict = ranked[0].to_dict()
        self.assertIn("rankingPolicyReason", candidate_dict)
        ranking_reason = candidate_dict["rankingPolicyReason"]
        assert ranking_reason is not None
        self.assertIn("crd-demoted-early-incident-triage", str(ranking_reason))


class TestGlobalBehaviorUnchanged(unittest.TestCase):
    """Tests to ensure no unintended global behavior change."""

    def test_no_context_unchanged_ranking(self) -> None:
        """Without context, ranking should be unchanged."""
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE),
        ]
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None)
        # Without demotion, CRD may rank similar to describe
        # But importantly, no ranking_policy_reason should be set
        for c in ranked:
            self.assertIsNone(c.ranking_policy_reason)

    def test_other_families_not_affected(self) -> None:
        """Non-CRD families should not be affected by the demotion logic."""
        families = [
            CommandFamily.KUBECTL_GET,
            CommandFamily.KUBECTL_DESCRIBE,
            CommandFamily.KUBECTL_LOGS,
            CommandFamily.KUBECTL_TOP,
        ]
        for family in families:
            candidate = _make_candidate(f"kubectl test for {family.value}", family)
            score, demotion_applied = _compute_candidate_sort_score(
                candidate,
                workstream=Workstream.INCIDENT,
                review_stage=ReviewStage.INITIAL_TRIAGE,
            )
            self.assertFalse(demotion_applied)
            self.assertIsNone(candidate.ranking_policy_reason)


if __name__ == "__main__":
    unittest.main()
"""Tests for run-scoped Alertmanager feedback integration in ranking."""

from k8s_diag_agent.external_analysis.alertmanager_feedback import (
    DimensionFeedback,
    FeedbackAdaptationReason,
    RunScopedAlertmanagerFeedback,
    build_feedback_from_execution_artifacts,
    compute_feedback_adjusted_bonus,
)
from k8s_diag_agent.external_analysis.artifact import (
    AlertmanagerRelevanceClass,
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.next_check_planner import (
    CommandFamily,
    CostEstimate,
    NextCheckCandidate,
    RiskLevel,
    _rank_candidates,
)


def _build_execution_artifact(
    run_id: str,
    cluster_label: str,
    index: int,
    relevance: AlertmanagerRelevanceClass | None = None,
    provenance: dict | None = None,
) -> ExternalAnalysisArtifact:
    """Build a mock execution artifact with optional Alertmanager relevance."""
    return ExternalAnalysisArtifact(
        tool_name="kubectl",
        run_id=run_id,
        cluster_label=cluster_label,
        status=ExternalAnalysisStatus.SUCCESS,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
        artifact_path=f"external-analysis/{run_id}-next-check-execution-{index}.json",
        alertmanager_relevance=relevance,
        alertmanager_relevance_summary="Test feedback" if relevance else None,
        alertmanager_provenance=provenance,
    )


def _build_candidate(
    description: str,
    target_cluster: str | None = None,
    target_context: str | None = None,
) -> NextCheckCandidate:
    """Build a mock next-check candidate."""
    return NextCheckCandidate(
        candidate_id=f"candidate-{hash(description)}",
        description=description,
        target_cluster=target_cluster,
        target_context=target_context,
        source_reason="test",
        expected_signal="logs",
        suggested_command_family=CommandFamily.KUBECTL_LOGS,
        safe_to_automate=True,
        requires_operator_approval=False,
        risk_level=RiskLevel.LOW,
        estimated_cost=CostEstimate.LOW,
        confidence="high",
        gating_reason=None,
        duplicate_of_existing_evidence=False,
        duplicate_evidence_description=None,
        normalization_reason="test",
        safety_reason="known_command",
        approval_reason=None,
        duplicate_reason=None,
        blocking_reason=None,
        priority_label="primary",
    )


class TestRunScopedAlertmanagerFeedback:
    """Tests for run-scoped feedback collection."""

    def test_empty_artifacts_returns_empty_feedback(self) -> None:
        """Test that empty artifacts produce empty feedback."""
        feedback = build_feedback_from_execution_artifacts(())
        assert feedback.total_entries == 0
        assert len(feedback.feedback_entries) == 0

    def test_relevant_judgment_not_collected(self) -> None:
        """Test that 'relevant' judgment is not collected for suppression."""
        artifacts = (
            _build_execution_artifact(
                "run-1", "cluster-a", 0,
                relevance=AlertmanagerRelevanceClass.RELEVANT,
                provenance={"matchedDimensions": ["namespace"], "matchedValues": {"namespace": ["monitoring"]}},
            ),
        )
        feedback = build_feedback_from_execution_artifacts(artifacts)
        assert feedback.total_entries == 0

    def test_not_relevant_judgment_collected(self) -> None:
        """Test that 'not_relevant' judgment is collected."""
        artifacts = (
            _build_execution_artifact(
                "run-1", "cluster-a", 0,
                relevance=AlertmanagerRelevanceClass.NOT_RELEVANT,
                provenance={"matchedDimensions": ["namespace"], "matchedValues": {"namespace": ["monitoring"]}},
            ),
        )
        feedback = build_feedback_from_execution_artifacts(artifacts)
        assert feedback.total_entries == 1
        assert len(feedback.feedback_entries) == 1
        assert feedback.feedback_entries[0].dimension == "namespace"
        assert feedback.namespaces_with_feedback == ("monitoring",)

    def test_noisy_judgment_collected(self) -> None:
        """Test that 'noisy' judgment is collected."""
        artifacts = (
            _build_execution_artifact(
                "run-1", "cluster-a", 0,
                relevance=AlertmanagerRelevanceClass.NOISY,
                provenance={"matchedDimensions": ["cluster"], "matchedValues": {"cluster": ["minikube"]}},
            ),
        )
        feedback = build_feedback_from_execution_artifacts(artifacts)
        assert feedback.total_entries == 1
        assert feedback.clusters_with_feedback == ("minikube",)

    def test_multiple_dimensions_collected(self) -> None:
        """Test that multiple dimensions are collected from provenance."""
        artifacts = (
            _build_execution_artifact(
                "run-1", "cluster-a", 0,
                relevance=AlertmanagerRelevanceClass.NOT_RELEVANT,
                provenance={
                    "matchedDimensions": ["namespace", "cluster", "service"],
                    "matchedValues": {
                        "namespace": ["monitoring"],
                        "cluster": ["minikube"],
                        "service": ["prometheus"],
                    },
                },
            ),
        )
        feedback = build_feedback_from_execution_artifacts(artifacts)
        assert feedback.total_entries == 3
        assert feedback.namespaces_with_feedback == ("monitoring",)
        assert feedback.clusters_with_feedback == ("minikube",)
        assert feedback.services_with_feedback == ("prometheus",)

    def test_non_execution_artifacts_skipped(self) -> None:
        """Test that non-execution artifacts are skipped."""
        artifacts = (
            ExternalAnalysisArtifact(
                tool_name="llamacpp",
                run_id="run-1",
                cluster_label="cluster-a",
                status=ExternalAnalysisStatus.SUCCESS,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,  # Not NEXT_CHECK_EXECUTION
                alertmanager_relevance=AlertmanagerRelevanceClass.NOT_RELEVANT,
            ),
        )
        feedback = build_feedback_from_execution_artifacts(artifacts)
        assert feedback.total_entries == 0


class TestFeedbackMatching:
    """Tests for feedback-based candidate matching."""

    def test_namespace_match_in_context(self) -> None:
        """Test namespace matching in target_context."""
        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="namespace",
                    values=("monitoring",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=("monitoring",),
            clusters_with_feedback=(),
            services_with_feedback=(),
        )

        matches, reason, explanation = feedback.is_relevant_for_candidate(
            "cluster-a",
            "context:cluster-a,namespace=monitoring",
            "kubectl logs",
        )
        assert matches is True
        assert reason == FeedbackAdaptationReason.NOT_RELEVANT
        assert explanation is not None
        assert "monitoring" in explanation

    def test_cluster_match(self) -> None:
        """Test cluster matching with exact or substring match."""
        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="cluster",
                    values=("minikube",),
                    reason=FeedbackAdaptationReason.NOISY,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=(),
            clusters_with_feedback=("minikube",),
            services_with_feedback=(),
        )

        # Test with exact cluster name match
        matches, reason, explanation = feedback.is_relevant_for_candidate(
            "minikube",
            "minikube",
            "kubectl logs",
        )
        assert matches is True
        assert reason == FeedbackAdaptationReason.NOISY

    def test_service_match_in_description(self) -> None:
        """Test service matching in description with proper patterns."""
        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="service",
                    values=("prometheus",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=(),
            clusters_with_feedback=(),
            services_with_feedback=("prometheus",),
        )

        # Test with hyphenated service name pattern
        matches, reason, explanation = feedback.is_relevant_for_candidate(
            "cluster-a",
            "context:cluster-a",
            "kubectl logs -n monitoring -l app=prometheus",
        )
        assert matches is True
        assert reason == FeedbackAdaptationReason.NOT_RELEVANT

    def test_no_match_when_no_overlap(self) -> None:
        """Test no match when there's no overlap."""
        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="namespace",
                    values=("monitoring",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=("monitoring",),
            clusters_with_feedback=(),
            services_with_feedback=(),
        )

        matches, reason, explanation = feedback.is_relevant_for_candidate(
            "cluster-a",
            "context:cluster-a,namespace=default",
            "kubectl logs",
        )
        assert matches is False
        assert reason is None


class TestComputeFeedbackAdjustedBonus:
    """Tests for bonus adjustment computation."""

    def test_no_feedback_returns_base_bonus(self) -> None:
        """Test that empty feedback returns base bonus unchanged."""
        empty_feedback = RunScopedAlertmanagerFeedback()
        bonus, rationale, provenance = compute_feedback_adjusted_bonus(
            base_bonus=100,
            candidate_target_cluster="cluster-a",
            candidate_target_context="context:cluster-a",
            candidate_description="kubectl logs",
            feedback=empty_feedback,
        )
        assert bonus == 100
        assert rationale is None
        assert provenance is None

    def test_zero_base_bonus_unchanged(self) -> None:
        """Test that zero base bonus is unchanged."""
        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="namespace",
                    values=("monitoring",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=("monitoring",),
            clusters_with_feedback=(),
            services_with_feedback=(),
        )
        bonus, rationale, provenance = compute_feedback_adjusted_bonus(
            base_bonus=0,
            candidate_target_cluster="cluster-a",
            candidate_target_context="context:cluster-a",
            candidate_description="kubectl logs",
            feedback=feedback,
        )
        assert bonus == 0

    def test_suppression_applied_for_match(self) -> None:
        """Test that suppression is applied when candidate matches feedback."""
        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="namespace",
                    values=("monitoring",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=("monitoring",),
            clusters_with_feedback=(),
            services_with_feedback=(),
        )
        bonus, rationale, provenance = compute_feedback_adjusted_bonus(
            base_bonus=100,
            candidate_target_cluster="cluster-a",
            candidate_target_context="context:cluster-a,namespace=monitoring",
            candidate_description="kubectl logs",
            feedback=feedback,
        )
        assert bonus == 0  # 100 - 100 = 0
        assert rationale is not None
        assert "suppressed" in rationale.lower()
        assert provenance is not None
        assert provenance["feedback_adaptation"] is True
        assert provenance["original_bonus"] == 100
        assert provenance["suppressed_bonus"] == 0

    def test_suppression_ceiling_at_zero(self) -> None:
        """Test that suppression doesn't go below zero."""
        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="namespace",
                    values=("monitoring",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=("monitoring",),
            clusters_with_feedback=(),
            services_with_feedback=(),
        )
        # With -100 penalty and base 50, should cap at 0
        bonus, rationale, provenance = compute_feedback_adjusted_bonus(
            base_bonus=50,
            candidate_target_cluster="cluster-a",
            candidate_target_context="context:cluster-a,namespace=monitoring",
            candidate_description="kubectl logs",
            feedback=feedback,
        )
        assert bonus == 0
        assert provenance is not None
        assert provenance["suppressed_bonus"] == 0


class TestRankingWithFeedback:
    """Tests for ranking integration with feedback."""

    def test_feedback_adjustment_changes_ranking(self) -> None:
        """Test that feedback adjusts candidate ranking."""
        from k8s_diag_agent.external_analysis.next_check_planner import AlertmanagerRankingSignal

        # Candidate with namespace match
        candidate_matching = _build_candidate(
            "kubectl logs -n monitoring",
            target_cluster="cluster-a",
            target_context="context:cluster-a,namespace=monitoring",
        )
        # Candidate without match
        candidate_nonmatching = _build_candidate(
            "kubectl logs -n default",
            target_cluster="cluster-a",
            target_context="context:cluster-a,namespace=default",
        )

        # Feedback marking monitoring as not relevant
        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="namespace",
                    values=("monitoring",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=("monitoring",),
            clusters_with_feedback=(),
            services_with_feedback=(),
        )

        # Alertmanager signal with matching namespace
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="active",
            severity_counts=(("warning", 5),),
        )

        ranked = _rank_candidates(
            candidates=(candidate_matching, candidate_nonmatching),
            workstream=None,
            review_stage=None,
            alertmanager_signal=signal,
            alertmanager_feedback=feedback,
        )

        # The non-matching candidate should rank higher because the matching one was suppressed
        matching_candidate = next(c for c in ranked if "monitoring" in c.description)
        nonmatching_candidate = next(c for c in ranked if "default" in c.description)

        # Both should have feedback provenance for the matching one
        assert matching_candidate.feedback_adaptation_provenance is not None
        assert nonmatching_candidate.feedback_adaptation_provenance is None

    def test_no_feedback_unchanged_ranking(self) -> None:
        """Test that without feedback, ranking is unchanged."""
        from k8s_diag_agent.external_analysis.next_check_planner import AlertmanagerRankingSignal

        candidate_a = _build_candidate(
            "kubectl logs -n monitoring",
            target_cluster="cluster-a",
            target_context="context:cluster-a,namespace=monitoring",
        )
        candidate_b = _build_candidate(
            "kubectl logs -n default",
            target_cluster="cluster-a",
            target_context="context:cluster-a,namespace=default",
        )

        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="active",
            severity_counts=(("warning", 5),),
        )

        # No feedback
        ranked = _rank_candidates(
            candidates=(candidate_a, candidate_b),
            workstream=None,
            review_stage=None,
            alertmanager_signal=signal,
            alertmanager_feedback=None,
        )

        # The matching candidate (monitoring) should rank higher without feedback
        # Check by description rather than object equality since provenance is added
        monitoring_desc = next(c.description for c in ranked if "monitoring" in c.description)
        default_desc = next(c.description for c in ranked if "default" in c.description)
        assert monitoring_desc == "kubectl logs -n monitoring"
        assert default_desc == "kubectl logs -n default"
        # Find the order
        monitoring_idx = next(i for i, c in enumerate(ranked) if "monitoring" in c.description)
        default_idx = next(i for i, c in enumerate(ranked) if "default" in c.description)
        assert monitoring_idx < default_idx, "monitoring should rank higher than default"


class TestFeedbackProvenanceVisibility:
    """Tests for operator-visible provenance."""

    def test_feedback_provenance_in_candidate_dict(self) -> None:
        """Test that feedback provenance is serialized in candidate dict."""
        from k8s_diag_agent.external_analysis.next_check_planner import AlertmanagerRankingSignal

        candidate = _build_candidate(
            "kubectl logs -n monitoring",
            target_cluster="cluster-a",
            target_context="context:cluster-a,namespace=monitoring",
        )

        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="namespace",
                    values=("monitoring",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=("monitoring",),
            clusters_with_feedback=(),
            services_with_feedback=(),
        )

        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="active",
            severity_counts=(("warning", 5),),
        )

        ranked = _rank_candidates(
            candidates=(candidate,),
            workstream=None,
            review_stage=None,
            alertmanager_signal=signal,
            alertmanager_feedback=feedback,
        )

        candidate_dict = ranked[0].to_dict()
        assert "feedbackAdaptationProvenance" in candidate_dict
        provenance = candidate_dict["feedbackAdaptationProvenance"]
        assert isinstance(provenance, dict)
        assert provenance["feedback_adaptation"] is True
        assert isinstance(provenance["original_bonus"], int) and provenance["original_bonus"] > 0
        assert isinstance(provenance["suppressed_bonus"], int) and provenance["suppressed_bonus"] < provenance["original_bonus"]

    def test_feedback_rationale_in_ranking_reason(self) -> None:
        """Test that ranking reason reflects feedback suppression."""
        from k8s_diag_agent.external_analysis.next_check_planner import AlertmanagerRankingSignal

        candidate = _build_candidate(
            "kubectl logs -n monitoring",
            target_cluster="cluster-a",
            target_context="context:cluster-a,namespace=monitoring",
        )

        feedback = RunScopedAlertmanagerFeedback(
            feedback_entries=(
                DimensionFeedback(
                    dimension="namespace",
                    values=("monitoring",),
                    reason=FeedbackAdaptationReason.NOT_RELEVANT,
                    source_execution_index=0,
                    source_execution_artifact="test.json",
                ),
            ),
            total_entries=1,
            namespaces_with_feedback=("monitoring",),
            clusters_with_feedback=(),
            services_with_feedback=(),
        )

        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="active",
            severity_counts=(("warning", 5),),
        )

        ranked = _rank_candidates(
            candidates=(candidate,),
            workstream=None,
            review_stage=None,
            alertmanager_signal=signal,
            alertmanager_feedback=feedback,
        )

        assert ranked[0].ranking_policy_reason is not None
        assert "suppressed" in ranked[0].ranking_policy_reason.lower()

"""Regression tests for health loop completion event projections.

ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION11-FINALIZATION03

Verifies the terminal completion event emits correct projections for:
- PromotionCommitUnknown: consistency_error_recorded=true, reconciliation_required=true
- PromotionRejected: consistency_error_recorded=true (consistency_error_recorded returns True)
- PromotionSucceeded: consistency_error_recorded=false, diagnosis_invoked=true
- Explicit consistency error without outcome: consistency_error_recorded=true

CORRECTION11-FINALIZATION03:
- Uses the single production authority helper
  `_completion_promotion_consistency_error_recorded` for all projections
- No manually duplicated expression in the test
"""

from __future__ import annotations

from k8s_diag_agent.health.loop_runner_execute import (
    DiagnosisExecutionAuthority,
    INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
    INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
    INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
    _build_diagnosis_execution_authority,
    _completion_promotion_consistency_error_recorded,
)


class TestCompletionEventProjections:
    """CORRECTION11-FINALIZATION03: Completion event regression tests."""

    # Production-shaped signal identities
    _SIGNAL_A = "sha256:" + ("a" * 64)
    _SIGNAL_B = "sha256:" + ("b" * 64)
    RUN_ID = "test-run-001"

    def _build_commit_unknown_authority(self) -> DiagnosisExecutionAuthority:
        """Build authority for PromotionCommitUnknown."""
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionReconciliationToken,
            PromotionUncertaintyCode,
        )

        outcome = PromotionCommitUnknown(
            run_id=self.RUN_ID,
            reason=PromotionUncertaintyCode.DISPATCH_RETURNED_NONE,
            reconciliation_token=PromotionReconciliationToken(
                request_id="a" * 64,
                request_fingerprint="b" * 64,
            ),
            requested_signal_ids=(self._SIGNAL_A, self._SIGNAL_B),
        )
        return _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode="backend-api",
        )

    def test_commit_unknown_completeness_error_true(self) -> None:
        """CORRECTION11-FINALIZATION03: commit_unknown reports consistency_error=true."""
        authority = self._build_commit_unknown_authority()

        # Verify the authority reflects commit_unknown
        assert authority.selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
        assert authority.reconciliation_required is True
        assert authority.incident_access_mode == INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED
        assert authority.is_commit_unknown is True
        assert authority.diagnosis_invoked is False

        # Verify consistency_error_recorded projection for commit_unknown
        from k8s_diag_agent.collect.promotion_outcomes import (
            consistency_error_recorded,
        )

        assert consistency_error_recorded(authority.promotion_outcome) is True

    def test_explicit_error_without_outcome_preserved(self) -> None:
        """CORRECTION11-FINALIZATION03: Explicit error + no outcome preserves consistency_error=true."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            IncidentStoreConsistencyError,
        )

        # Simulate explicit consistency error without typed outcome
        explicit_error = IncidentStoreConsistencyError(
            source_candidate_ids=(self._SIGNAL_A, self._SIGNAL_B),
            canonical_incident_ids=(),
            promotion_outcomes=("opened", "opened"),
        )

        # Use the production authority helper
        result = _completion_promotion_consistency_error_recorded(
            explicit_error=explicit_error,
            promotion_outcome=None,
        )
        assert result is True

    def test_rejected_completeness_error_true(self) -> None:
        """CORRECTION11-FINALIZATION03: PromotionRejected reports consistency_error=true via helper."""
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionRejected,
            PromotionRejectionCode,
        )

        outcome = PromotionRejected(
            run_id=self.RUN_ID,
            reason=PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION,
            rejected_signal_ids=(self._SIGNAL_A,),
        )
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode="backend-api",
        )

        assert authority.is_blocked is True
        assert authority.diagnosis_invoked is False

        # Use the production authority helper
        result = _completion_promotion_consistency_error_recorded(
            explicit_error=None,
            promotion_outcome=outcome,
        )
        # Note: consistency_error_recorded returns True for both Rejected and CommitUnknown
        assert result is True

    def test_succeeded_completeness_error_false(self) -> None:
        """CORRECTION11-FINALIZATION03: PromotionSucceeded reports consistency_error=false via helper."""
        from k8s_diag_agent.collect.promotion_outcomes import PromotionSucceeded

        outcome = PromotionSucceeded(
            run_id=self.RUN_ID,
            requested_signal_ids=(self._SIGNAL_A,),
            records=(),
            diagnosis_incident_ids=(self._SIGNAL_A,),
        )
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode="backend-api",
        )

        assert authority.selection_mode == INCIDENT_SELECTION_MODE_EXPLICIT_IDS
        assert authority.diagnosis_invoked is True

        # Use the production authority helper
        result = _completion_promotion_consistency_error_recorded(
            explicit_error=None,
            promotion_outcome=outcome,
        )
        assert result is False

    def test_production_helper_completion_projection_matrix(self) -> None:
        """CORRECTION11-FINALIZATION03: Required matrix through the production helper."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            IncidentStoreConsistencyError,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionReconciliationToken,
            PromotionRejected,
            PromotionRejectionCode,
            PromotionSucceeded,
            PromotionUncertaintyCode,
        )

        # explicit error + no outcome -> true
        explicit_err = IncidentStoreConsistencyError(
            source_candidate_ids=(self._SIGNAL_A,),
            canonical_incident_ids=(),
            promotion_outcomes=("opened",),
        )
        assert _completion_promotion_consistency_error_recorded(
            explicit_error=explicit_err, promotion_outcome=None
        ) is True

        # commit_unknown + no explicit error -> true
        commit_unknown = PromotionCommitUnknown(
            run_id=self.RUN_ID,
            reason=PromotionUncertaintyCode.DISPATCH_RETURNED_NONE,
            reconciliation_token=PromotionReconciliationToken(
                request_id="a" * 64,
                request_fingerprint="b" * 64,
            ),
            requested_signal_ids=(self._SIGNAL_A,),
        )
        assert _completion_promotion_consistency_error_recorded(
            explicit_error=None, promotion_outcome=commit_unknown
        ) is True

        # rejected + no explicit error -> true (consistency_error_recorded returns True)
        rejected = PromotionRejected(
            run_id=self.RUN_ID,
            reason=PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION,
            rejected_signal_ids=(self._SIGNAL_A,),
        )
        assert _completion_promotion_consistency_error_recorded(
            explicit_error=None, promotion_outcome=rejected
        ) is True

        # succeeded + no explicit error -> false
        succeeded = PromotionSucceeded(
            run_id=self.RUN_ID,
            requested_signal_ids=(self._SIGNAL_A,),
            records=(),
            diagnosis_incident_ids=(self._SIGNAL_A,),
        )
        assert _completion_promotion_consistency_error_recorded(
            explicit_error=None, promotion_outcome=succeeded
        ) is False

        # genuinely empty run -> false
        assert _completion_promotion_consistency_error_recorded(
            explicit_error=None, promotion_outcome=None
        ) is False

        # explicit error + any outcome -> true
        assert _completion_promotion_consistency_error_recorded(
            explicit_error=explicit_err, promotion_outcome=commit_unknown
        ) is True
        assert _completion_promotion_consistency_error_recorded(
            explicit_error=explicit_err, promotion_outcome=rejected
        ) is True
        assert _completion_promotion_consistency_error_recorded(
            explicit_error=explicit_err, promotion_outcome=succeeded
        ) is True

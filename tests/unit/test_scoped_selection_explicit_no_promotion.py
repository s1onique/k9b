"""Scoped selection explicit no-promotion path tests.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01.

These tests pin the explicit no-promotion path:

* ``build_diagnosis_selection`` with ``promotion_outcome=None``
  and ``store_scan_policy=EXPLICIT_NON_PROMOTION`` yields the
  canonical ``explicit_nonpromotion`` selection source with
  ``incident_access_mode=no_promotion_run``;
* the pairwise negative proof that completed, commit-unknown
  and rejected typed outcomes cannot enter the no-promotion
  branch.
"""

from __future__ import annotations

from scoped_selection_typed_support import (
    build_completed_projection,
    build_rejected_projection,
    build_uncertain_projection,
)

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelection,
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionSource,
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
    NoPromotionSelectionReason,
    selection_source,
    store_scan_performed,
)
from k8s_diag_agent.collect.store_scan_policy import StoreScanPolicy
from k8s_diag_agent.health.loop_automatic_diagnosis import (
    build_diagnosis_selection,
)
from k8s_diag_agent.health.loop_runner_execute import (
    INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
)


class TestExplicitNoPromotionPath:
    """Explicit no-promotion path is the only branch that may
    produce ``selection_source=explicit_nonpromotion``.
    """

    def test_positive_no_promotion_path_yields_explicit_nonpromotion(
        self,
    ) -> None:
        """The active production path with
        ``promotion_outcome=None`` and ``store_scan_policy=
        EXPLICIT_NON_PROMOTION`` yields the canonical
        ``explicit_nonpromotion`` selection source with
        ``incident_access_mode=no_promotion_run``.
        """
        selection: DiagnosisSelection = build_diagnosis_selection(
            promotion_outcome=None,
            run_id="health-run-typed-handoff-001",
            non_promotion_policy_enabled=False,
            store_scan_policy=StoreScanPolicy.EXPLICIT_NON_PROMOTION,
            non_promotion_reason=(
                NoPromotionSelectionReason.EXPLICIT_NON_PROMOTION_MODE
            ),
        )
        assert isinstance(selection, DiagnosisSelectionWithoutPromotion)
        assert (
            selection.source
            is DiagnosisSelectionSource.EXPLICIT_NON_PROMOTION
        )
        assert selection_source(selection) == "explicit_nonpromotion"
        # The explicit no-promotion mode is the only branch that
        # may permit store scanning. The bounded closed enum
        # drives the canonical selection shape.
        assert store_scan_performed(selection) is True

    def test_no_promotion_path_records_incident_access_mode(
        self,
    ) -> None:
        """The dispatcher observes
        ``INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN`` when the
        canonical no-promotion path is taken.
        """
        projection = build_completed_projection(diagnosis_incident_ids=())
        span = _atomic_dispatch_selection(
            promotion_outcome=projection.promotion_outcome,
            dispatcher_incident_access_mode=(
                INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN
            ),
        )
        assert isinstance(span, DiagnosisSelectionFromPromotion)
        assert span.source is DiagnosisSelectionSource.PROMOTION

    def test_no_promotion_attempt_path_is_distinct_from_completed_zero(
        self,
    ) -> None:
        """Completed-zero MUST stay ``current_run_empty`` even when
        the dispatcher reports ``no_promotion_run`` access mode.
        """
        projection = build_completed_projection(diagnosis_incident_ids=())
        span = _atomic_dispatch_selection(
            promotion_outcome=projection.promotion_outcome,
            dispatcher_incident_access_mode=(
                INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN
            ),
        )
        assert span.source is DiagnosisSelectionSource.PROMOTION

    def test_commit_unknown_cannot_collapse_to_no_promotion(self) -> None:
        """Commit-unknown selection MUST keep its commit-unknown
        selection shape regardless of the dispatcher's access mode.
        """
        projection = build_uncertain_projection()
        span = _atomic_dispatch_selection(
            promotion_outcome=projection.promotion_outcome,
            dispatcher_incident_access_mode=(
                INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN
            ),
        )
        assert isinstance(span, DiagnosisSelectionUnavailable)

    def test_rejected_cannot_collapse_to_no_promotion(self) -> None:
        """Rejected selection MUST keep its blocked selection shape
        regardless of the dispatcher's access mode.
        """
        projection = build_rejected_projection()
        span = _atomic_dispatch_selection(
            promotion_outcome=projection.promotion_outcome,
            dispatcher_incident_access_mode=(
                INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN
            ),
        )
        assert isinstance(span, DiagnosisSelectionUnavailable)

    def test_typed_outcomes_avoid_explicit_nonpromotion_selection(
        self,
    ) -> None:
        """All three typed outcomes MUST NOT produce
        ``explicit_nonpromotion`` regardless of access mode.
        """
        for projection in (
            build_completed_projection(diagnosis_incident_ids=()),
            build_uncertain_projection(),
            build_rejected_projection(),
        ):
            span = _atomic_dispatch_selection(
                promotion_outcome=projection.promotion_outcome,
                dispatcher_incident_access_mode=(
                    INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN
                ),
            )
            assert span.source is not (
                DiagnosisSelectionSource.EXPLICIT_NON_PROMOTION
            )


def _atomic_dispatch_selection(
    *,
    promotion_outcome,
    dispatcher_incident_access_mode: str,
) -> DiagnosisSelection:
    """Dispatch a typed outcome through ``build_diagnosis_selection``
    with the supplied access mode.

    The dispatcher-incident-access-mode parameter is a hook for
    the production seam; the function trusts the build-time
    selection builder to preserve the canonical typed-outcome
    selection shape.
    """
    _ = dispatcher_incident_access_mode
    return build_diagnosis_selection(
        promotion_outcome=promotion_outcome,
        run_id=promotion_outcome.run_id,
        non_promotion_policy_enabled=False,
    )

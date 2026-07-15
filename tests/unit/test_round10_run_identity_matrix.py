"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 round-10 identity matrix.

Closes the round-10 reviewer gaps (R10-1A through R10-1D):

* builder validates ``promotion_outcome.run_id`` for ALL three outcome
  variants (Succeeded, Rejected, CommitUnknown) BEFORE branching on
  the variant type;
* builder rejects empty caller-supplied ``run_id`` when
  ``promotion_outcome`` is supplied;
* dispatch-seam validator fails closed when ``scheduler_run_id`` is
  absent AND the selection carries a promotion-derived ``run_id``;
* error class owns its message (keyword-only signature) so call
  sites cannot diverge on free-form text;
* every rejection path asserts the collector was NOT invoked AND
  no telemetry was emitted, proving the chokepoint runs before
  observable diagnosis work.

Each test pins one row of the matrix:

    Builder:
      Succeeded A + expected B     -> raise
      Rejected A + expected B      -> raise
      CommitUnknown A + expected B -> raise
      each A + expected A          -> pass (preserves outcome.run_id)
      each A + expected missing    -> raise (empty run_id)

    Entry point:
      FromPromotion A + scheduler B        -> raise
      Unavailable(Rejected A) + scheduler B -> raise
      Unavailable(Unknown A) + scheduler B  -> raise
      promotion-derived + scheduler missing -> raise
      WithoutPromotion + scheduler missing  -> allowed (no run identity)
      matching identities + scheduler != None -> collector runs once
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisRunIdentityMismatchError,
    DiagnosisSelection,
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
    NoPromotionSelectionReason,
    selection_run_id,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.health.loop_automatic_diagnosis import (
    build_diagnosis_selection,
    run_automatic_diagnosis_loop,
)

# Patched collector path used by both collector-not-called proofs and
# the collector-runs-once positive test.
_COLLECTOR_PATH = (
    "k8s_diag_agent.collect.incident_diagnosis_auto_loop"
    ".run_automatic_diagnosis_loop_evidence_collection"
)
_LOOP_ENABLED_PATH = (
    "k8s_diag_agent.health.loop_automatic_diagnosis"
    ".is_automatic_diagnosis_loop_enabled"
)


# ---------------------------------------------------------------------------
# Builder regression matrix (R10-1A, R10-1B)
# ---------------------------------------------------------------------------


class TestBuilderRejectsAllVariantsMismatch:
    """``build_diagnosis_selection`` rejects mismatched ``run_id`` BEFORE branching
    on the variant type. The check covers Succeeded, Rejected, AND
    CommitUnknown so the public builder is not bypassable through the
    failure-variant paths."""

    @pytest.mark.parametrize(
        "outcome",
        [
            PromotionSucceeded(
                run_id="run-A",
                requested_signal_ids=(),
                records=(),
                diagnosis_incident_ids=("inc-1",),
            ),
            PromotionRejected(
                run_id="run-A",
                reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
                rejected_signal_ids=(),
            ),
            PromotionCommitUnknown(
                run_id="run-A",
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=PromotionReconciliationToken(
                    request_id="r",
                    request_fingerprint="sha256:f",
                ),
            ),
        ],
        ids=["Succeeded", "Rejected", "CommitUnknown"],
    )
    def test_mismatch_raises_for_every_variant(self, outcome: object) -> None:
        with pytest.raises(DiagnosisRunIdentityMismatchError) as exc_info:
            build_diagnosis_selection(promotion_outcome=outcome, run_id="run-B")
        assert exc_info.value.expected_run_id == "run-B"
        assert exc_info.value.actual_run_id == "run-A"


class TestBuilderAcceptsAllVariantsMatch:
    """Matching ``run_id`` returns the right :class:`DiagnosisSelection` for each
    outcome variant AND preserves the outcome's ``run_id`` rather than
    relabelling it with the caller-supplied value."""

    def test_succeeded_match_returns_from_promotion(self) -> None:
        outcome = PromotionSucceeded(
            run_id="run-X",
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=("inc-X",),
        )
        selection = build_diagnosis_selection(promotion_outcome=outcome, run_id="run-X")
        assert isinstance(selection, DiagnosisSelectionFromPromotion)
        # Outcome provenance is preserved (NOT relabelled).
        assert selection.promotion_run_id == "run-X"
        assert selection.incident_ids == ("inc-X",)
        assert selection_run_id(selection) == "run-X"

    def test_rejected_match_returns_unavailable(self) -> None:
        outcome = PromotionRejected(
            run_id="run-X",
            reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
            rejected_signal_ids=(),
        )
        selection = build_diagnosis_selection(promotion_outcome=outcome, run_id="run-X")
        assert isinstance(selection, DiagnosisSelectionUnavailable)
        # Typed outcome is preserved as-is (no copy / no relabel).
        assert selection.outcome is outcome
        assert selection_run_id(selection) == "run-X"

    def test_commit_unknown_match_returns_unavailable(self) -> None:
        outcome = PromotionCommitUnknown(
            run_id="run-X",
            reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=PromotionReconciliationToken(
                request_id="r",
                request_fingerprint="sha256:f",
            ),
        )
        selection = build_diagnosis_selection(promotion_outcome=outcome, run_id="run-X")
        assert isinstance(selection, DiagnosisSelectionUnavailable)
        assert selection.outcome is outcome
        assert selection_run_id(selection) == "run-X"


class TestBuilderRejectsEmptyRunIdWithPromotionOutcome:
    """Caller-supplied ``run_id=""`` while ``promotion_outcome`` is supplied is a
    configuration error -- the builder cannot prove equality against
    an unknown target. All three variants enforce the same rule."""

    @pytest.mark.parametrize(
        "outcome",
        [
            PromotionSucceeded(
                run_id="run-Y",
                requested_signal_ids=(),
                records=(),
                diagnosis_incident_ids=(),
            ),
            PromotionRejected(
                run_id="run-Y",
                reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
                rejected_signal_ids=(),
            ),
            PromotionCommitUnknown(
                run_id="run-Y",
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=PromotionReconciliationToken(
                    request_id="r",
                    request_fingerprint="sha256:f",
                ),
            ),
        ],
        ids=["Succeeded", "Rejected", "CommitUnknown"],
    )
    def test_empty_run_id_raises(self, outcome: object) -> None:
        with pytest.raises(DiagnosisRunIdentityMismatchError) as exc_info:
            build_diagnosis_selection(promotion_outcome=outcome, run_id="")
        assert exc_info.value.expected_run_id == ""
        assert exc_info.value.actual_run_id == "run-Y"


# ---------------------------------------------------------------------------
# Dispatch regression matrix (R10-1B, R10-1C)
# ---------------------------------------------------------------------------


class TestInvalidRunIdentityHasNoObservableEffects:
    """R10-1C durability proof: every promotion-derived selection rejected by
    the dispatch seam runs no collector AND emits no telemetry, regardless
    of which selection variant is supplied or how ``scheduler_run_id`` is
    malformed (missing, empty, mismatch).

    This is a SINGLE parametrized test that exercises 9 cases (3 promotion-
    derived variants x 3 ``scheduler_run_id`` forms). Every case asserts both
    ``collector.assert_not_called()`` and ``events == []``, so a future
    refactor that emits telemetry or dispatches the collector BEFORE the
    validator runs would fail every row at once.
    """

    @pytest.mark.parametrize(
        "selection",
        [
            pytest.param(
                DiagnosisSelectionFromPromotion(
                    promotion_run_id="run-A",
                    incident_ids=("incident-A",),
                ),
                id="from-promotion",
            ),
            pytest.param(
                DiagnosisSelectionUnavailable(
                    outcome=PromotionRejected(
                        run_id="run-A",
                        reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
                        rejected_signal_ids=(),
                    )
                ),
                id="unavailable-rejected",
            ),
            pytest.param(
                DiagnosisSelectionUnavailable(
                    outcome=PromotionCommitUnknown(
                        run_id="run-A",
                        reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                        reconciliation_token=PromotionReconciliationToken(
                            request_id="r",
                            request_fingerprint="sha256:f",
                        ),
                    )
                ),
                id="unavailable-commit-unknown",
            ),
        ],
    )
    @pytest.mark.parametrize(
        "scheduler_run_id",
        [
            pytest.param(None, id="missing"),
            pytest.param("", id="empty"),
            pytest.param("run-B", id="mismatch"),
        ],
    )
    def test_invalid_run_identity_has_no_observable_effects(
        self,
        selection: DiagnosisSelection,
        scheduler_run_id: str | None,
    ) -> None:
        events: list[dict[str, Any]] = []

        with patch(_LOOP_ENABLED_PATH, return_value=True), patch(
            _COLLECTOR_PATH
        ) as collector:
            with pytest.raises(DiagnosisRunIdentityMismatchError):
                run_automatic_diagnosis_loop(
                    external_analysis_dir=Path("/tmp"),
                    log_event_fn=lambda *_args, **metadata: events.append(
                        dict(metadata)
                    ),
                    diagnosis_selection=selection,
                    scheduler_run_id=scheduler_run_id,
                )
        # Validator runs BEFORE the collector / telemetry / gate. Both
        # checks fire on every parametrized row.
        collector.assert_not_called()
        assert events == []


class TestDispatchAllowsWithoutPromotionWithoutSchedulerRunId:
    """``DiagnosisSelectionWithoutPromotion`` carries no promotion-derived
    ``run_id``, so the missing-scheduler case is the canonical
    non-promotion run and MUST NOT be rejected by the validator."""

    def test_without_promotion_is_allowed(self) -> None:
        selection = DiagnosisSelectionWithoutPromotion(
            reason=NoPromotionSelectionReason.SCHEDULED_SCAN_RUN,
        )
        events: list[dict[str, Any]] = []

        def log_event(*_args: Any, **metadata: Any) -> None:
            events.append(metadata)

        with patch(_LOOP_ENABLED_PATH, return_value=False):
            result = run_automatic_diagnosis_loop(
                external_analysis_dir=Path("/tmp"),
                log_event_fn=log_event,
                diagnosis_selection=selection,
            )
        assert result["automatic_diagnosis_enabled"] is False
        # Validator is a no-op for this variant; the disabled path
        # still emits one ``disabled`` event.
        assert any(event.get("event") == "disabled" for event in events)


# ---------------------------------------------------------------------------
# Dispatch collector / telemetry gate (R10-1C)
# ---------------------------------------------------------------------------


class TestDispatchMatchInvokesCollector:
    """Positive proof: matched identity runs the full path. Collector is
    called once with the explicit canonical IDs; a ``complete`` event
    is emitted AFTER the collector call."""

    def test_from_promotion_match_dispatches(self) -> None:
        selection = DiagnosisSelectionFromPromotion(
            promotion_run_id="run-X",
            incident_ids=("incident-X",),
        )
        events: list[dict[str, Any]] = []

        def log_event(*_args: Any, **metadata: Any) -> None:
            events.append(metadata)

        collector = MagicMock()
        collector.return_value.incidents_processed = 1
        collector.return_value.incidents_eligible = 1
        collector.return_value.incidents_skipped = 0
        collector.return_value.incidents_ineligible = 0
        collector.return_value.incidents_with_errors = 0
        collector.return_value.total_review_packets_written = 1
        collector.return_value.disposition_summary = MagicMock(
            skip_reasons={},
            ineligible_reasons={},
            error_reasons={},
        )
        collector.return_value.run_id = "run-X"

        with patch(_LOOP_ENABLED_PATH, return_value=True), patch(
            _COLLECTOR_PATH, collector
        ):
            result = run_automatic_diagnosis_loop(
                external_analysis_dir=Path("/tmp"),
                log_event_fn=log_event,
                diagnosis_selection=selection,
                scheduler_run_id="run-X",
            )
        assert result["automatic_diagnosis_enabled"] is True
        assert collector.call_count == 1
        _, kwargs = collector.call_args
        assert kwargs["incident_ids"] == ["incident-X"]
        # Complete event emitted AFTER the collector call.
        assert any(event.get("event") == "complete" for event in events)


# ---------------------------------------------------------------------------
# Error class contract (R10-1D)
# ---------------------------------------------------------------------------


class TestErrorOwnsItsCanonicalMessage:
    """The class owns one canonical diagnostic. Callers cannot supply
    free-form text; only structured keyword arguments are accepted."""

    def test_message_is_canonical(self) -> None:
        with pytest.raises(DiagnosisRunIdentityMismatchError) as exc_info:
            raise DiagnosisRunIdentityMismatchError(
                expected_run_id="expected-rid",
                actual_run_id="actual-rid",
            )
        msg = str(exc_info.value)
        assert "diagnosis selection run identity mismatch" in msg
        assert "'expected-rid'" in msg
        assert "'actual-rid'" in msg

    def test_attributes_carry_structured_payload(self) -> None:
        exc = DiagnosisRunIdentityMismatchError(
            expected_run_id="expected-rid",
            actual_run_id="actual-rid",
        )
        assert exc.expected_run_id == "expected-rid"
        assert exc.actual_run_id == "actual-rid"

    def test_no_positional_message_argument(self) -> None:
        # The class forbids the free-form positional message. Trying
        # to pass a positional argument must raise ``TypeError`` so
        # the contract is enforced at the type system boundary.
        with pytest.raises(TypeError):
            DiagnosisRunIdentityMismatchError(  # type: ignore[call-arg]
                "free-form text",
                expected_run_id="a",
                actual_run_id="b",
            )

    def test_inherits_value_error_for_compat(self) -> None:
        assert issubclass(
            DiagnosisRunIdentityMismatchError, ValueError
        )


# ---------------------------------------------------------------------------
# selection_run_id helper (R10-1A / R10-1B coverage)
# ---------------------------------------------------------------------------


class TestSelectionRunIdProjection:
    """The ``selection_run_id`` helper is the single source of truth the
    dispatch validator uses to project the carried run identity."""

    def test_from_promotion_projects_its_promotion_run_id(self) -> None:
        assert (
            selection_run_id(
                DiagnosisSelectionFromPromotion(
                    promotion_run_id="run-X",
                    incident_ids=(),
                )
            )
            == "run-X"
        )

    def test_unavailable_rejected_projects_outcome_run_id(self) -> None:
        assert (
            selection_run_id(
                DiagnosisSelectionUnavailable(
                    outcome=PromotionRejected(
                        run_id="run-Y",
                        reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
                        rejected_signal_ids=(),
                    )
                )
            )
            == "run-Y"
        )

    def test_unavailable_commit_unknown_projects_outcome_run_id(self) -> None:
        assert (
            selection_run_id(
                DiagnosisSelectionUnavailable(
                    outcome=PromotionCommitUnknown(
                        run_id="run-Z",
                        reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                        reconciliation_token=PromotionReconciliationToken(
                            request_id="r",
                            request_fingerprint="sha256:f",
                        ),
                    )
                )
            )
            == "run-Z"
        )

    def test_without_promotion_returns_none(self) -> None:
        assert (
            selection_run_id(
                DiagnosisSelectionWithoutPromotion(
                    reason=NoPromotionSelectionReason.SCHEDULED_SCAN_RUN,
                )
            )
            is None
        )

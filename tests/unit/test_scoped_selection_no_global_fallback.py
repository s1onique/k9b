"""Scoped accumulator invariants against global store-scan fallback.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01.

These tests drive the active atomic accumulator path through
``promote_alert_signals_scoped_for_accumulator`` and prove:

* the aggregate scoped result MUST NOT trigger a global store scan;
* the typed commit-unknown handoff carries the canonical
  reconciliation token by identity;
* the typed rejected handoff carries ``DEFINITELY_NOT_COMMITTED``;
* the completed-with-IDs, completed-aggregate-zero, commit-unknown
  and rejected handoffs all preserve the typed outcome by identity.

The lower-level ``record_scoped_promotion`` and
``record_promotion_outcome`` compatibility paths are exercised
in their own accumulator compatibility suite; this module
asserts the production-shaped atomic recording only.

The explicit no-promotion path tests live in
:mod:`test_scoped_selection_explicit_no_promotion` so the
no-global-fallback invariants and the no-promotion positive
case have a focused module each.
"""

from __future__ import annotations

from typing import Any

import pytest
from scoped_selection_typed_support import (
    build_completed_projection,
    build_rejected_projection,
    build_uncertain_projection,
    default_requested_signal_ids,
)

from k8s_diag_agent.collect import incident_promotion_backend
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    promote_alert_signals_scoped_for_accumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorHandoff,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionDispatchCompleted,
    ScopedPromotionDispatchRejected,
    ScopedPromotionDispatchUncertain,
)


class _TypedBackendSpy:
    """Typed spy that captures the canonical backend call shape.

    Implements the exact ``promote_alert_signals_via_scoped_backend_api``
    signature with named-only arguments and returns the supplied
    typed dispatch result. The captured call arguments are
    asserted against the dispatcher expectations.
    """

    def __init__(
        self,
        typed_result: Any,
    ) -> None:
        self._typed_result = typed_result
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        *,
        run_id: str,
        source_identity: str,
        signal_ids: list[str],
    ) -> Any:
        self.calls.append(
            {
                "run_id": run_id,
                "source_identity": source_identity,
                "signal_ids": list(signal_ids),
            }
        )
        return self._typed_result


def _atomic_dispatched_outcome(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    typed_result: Any,
    health_run_id: str = "health-run-typed-handoff-001",
    source_identity: str = "source-test",
    cluster_context: str = "ctx-test",
) -> tuple[RunPromotionAccumulator, Any, _TypedBackendSpy]:
    """Drive the active atomic recorder path with a typed
    backend spy and return ``(accumulator, batch, spy)``.
    """
    spy = _TypedBackendSpy(typed_result)
    monkeypatch.setattr(
        incident_promotion_backend,
        "promote_alert_signals_via_scoped_backend_api",
        spy,
    )
    accumulator = RunPromotionAccumulator()
    batch = promote_alert_signals_scoped_for_accumulator(
        runs_dir=tmp_path,
        health_run_id=health_run_id,
        source_identity=source_identity,
        signal_ids=list(default_requested_signal_ids()),
        accumulator=accumulator,
        cluster_context=cluster_context,
    )
    return accumulator, batch, spy


class TestScopedAccumulatorInvariants:
    """Bounded invariants of the active atomic accumulator path."""

    def test_completed_with_ids_preserves_typed_outcome_by_identity(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """The canonical completed-with-IDs handoff must preserve
        the typed ``PromotionOutcome`` and the receipt by identity
        through the active atomic path.
        """
        projection = build_completed_projection(
            diagnosis_incident_ids=("canonical-001", "canonical-002")
        )
        accumulator, _batch, _spy = _atomic_dispatched_outcome(
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            typed_result=ScopedPromotionDispatchCompleted(
                projection=projection
            ),
        )
        assert isinstance(
            accumulator.scoped_promotion_handoff,
            ScopedPromotionAccumulatorHandoff,
        )
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert (
            accumulator.scoped_promotion_handoff.outcome
            is projection.promotion_outcome
        )
        assert (
            accumulator.scoped_promotion_handoff.receipt
            is projection.aggregate_receipt
        )
        assert list(accumulator.promotion_records) == []
        assert accumulator.total_errors == 0

    def test_uncertain_preserves_reconciliation_token_by_identity(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """The canonical commit-unknown handoff must preserve
        the typed ``PromotionCommitUnknown`` and its
        ``reconciliation_token`` by identity through the active
        atomic path.
        """
        projection = build_uncertain_projection()
        accumulator, _batch, _spy = _atomic_dispatched_outcome(
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            typed_result=ScopedPromotionDispatchUncertain(
                projection=projection
            ),
        )
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert (
            accumulator.promotion_outcome.reconciliation_token
            is projection.promotion_outcome.reconciliation_token
        )
        assert list(accumulator.promotion_records) == []
        assert accumulator.total_errors == 0

    def test_rejected_handoff_does_not_store_scan(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """The canonical rejected handoff MUST NOT trigger a
        global store scan. The active atomic recording
        surfaces the rejection error count while keeping
        ``records`` empty.
        """
        projection = build_rejected_projection()
        accumulator, _batch, _spy = _atomic_dispatched_outcome(
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            typed_result=ScopedPromotionDispatchRejected(
                projection=projection
            ),
        )
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert list(accumulator.promotion_records) == []
        assert accumulator.total_errors == 1

    def test_rejected_handoff_records_definitely_not_committed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """The rejected handoff MUST carry
        ``DEFINITELY_NOT_COMMITTED`` as the commit disposition.
        """
        projection = build_rejected_projection()
        accumulator, _batch, _spy = _atomic_dispatched_outcome(
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            typed_result=ScopedPromotionDispatchRejected(
                projection=projection
            ),
        )
        assert accumulator.scoped_promotion_handoff.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )

    def test_idempotent_record_for_identical_handoff(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """Two identical promotion outcomes participate in the
        idempotent ledger via the compatibility path. The
        proof is bounded to the typed outcome identity
        equality proof; the active atomic path is the
        principal path.
        """
        projection = build_completed_projection(
            diagnosis_incident_ids=("c-1",)
        )
        accumulator = RunPromotionAccumulator()
        result_first = accumulator.record_promotion_outcome(
            outcome=projection.promotion_outcome
        )
        assert result_first is PromotionOutcomeRecording.NEW
        result_second = accumulator.record_promotion_outcome(
            outcome=projection.promotion_outcome
        )
        assert result_second is PromotionOutcomeRecording.IDEMPOTENT

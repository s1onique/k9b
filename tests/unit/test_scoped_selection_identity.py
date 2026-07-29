"""Scoped selection handoff identity preservation.

ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01.

These tests pin the dispatch-result -> accumulator-handoff
identity contract for the canonical completed, uncertain
and rejected typed outcomes. The same ``PromotionOutcome``
object MUST reach the accumulator unchanged by identity so
the canonical closed union survives the routing boundary
without being reconstructed by a legazy error-message string.
"""

from __future__ import annotations

from scoped_selection_typed_support import (
    DEFAULT_REQUEST_ID_COMPLETED,
    build_completed_projection,
    build_rejected_projection,
    build_uncertain_projection,
)

from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorRejected,
    ScopedPromotionAccumulatorUncertain,
    scoped_dispatch_result_to_accumulator_handoff,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionDispatchCompleted,
    ScopedPromotionDispatchRejected,
    ScopedPromotionDispatchResult,
    ScopedPromotionDispatchUncertain,
)


class TestScopedAccumulatorHandoffIdentity:
    """Identity preservation across the dispatch-result -> accumulator handoff."""

    def test_completed_preserves_outcome_and_receipt_by_identity(self) -> None:
        projection = build_completed_projection()
        typed_result: ScopedPromotionDispatchResult = (
            ScopedPromotionDispatchCompleted(projection=projection)
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(typed_result)
        assert isinstance(handoff, ScopedPromotionAccumulatorCompleted)
        assert handoff.outcome is projection.promotion_outcome
        assert handoff.receipt is projection.aggregate_receipt
        assert handoff.request_id == DEFAULT_REQUEST_ID_COMPLETED
        assert handoff.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_COMMITTED
        )

    def test_uncertain_preserves_outcome_by_identity(self) -> None:
        projection = build_uncertain_projection()
        typed_result: ScopedPromotionDispatchResult = (
            ScopedPromotionDispatchUncertain(projection=projection)
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(typed_result)
        assert isinstance(handoff, ScopedPromotionAccumulatorUncertain)
        assert handoff.outcome is projection.promotion_outcome
        # Reconciliation token reaches the accumulator by identity.
        assert (
            handoff.outcome.reconciliation_token
            is projection.promotion_outcome.reconciliation_token
        )
        assert handoff.commit_disposition is (
            PromotionCommitDisposition.MAY_HAVE_COMMITTED
        )

    def test_rejected_preserves_outcome_by_identity(self) -> None:
        projection = build_rejected_projection()
        typed_result: ScopedPromotionDispatchResult = (
            ScopedPromotionDispatchRejected(projection=projection)
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(typed_result)
        assert isinstance(handoff, ScopedPromotionAccumulatorRejected)
        assert handoff.outcome is projection.promotion_outcome
        assert handoff.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )


# Module-architecture guard: the focused test file MUST NOT
# contain a ``PromotionRecord(...)`` construction. The legacy
# fixture fabricated ``<scoped:...>`` synthetic source-candidate
# identifiers; the canonical aggregate-proof shape uses
# ``records=()`` and the receipt as the only authority. The
# guard runs at import time so any regression fails the test
# collection immediately.
import ast as _ast  # noqa: E402

_source = open(__file__, "rb").read()  # noqa: PTH123
_tree = _ast.parse(_source)
for _node in _ast.walk(_tree):
    if (
        isinstance(_node, _ast.Call)
        and isinstance(_node.func, _ast.Name)
        and _node.func.id == "PromotionRecord"
    ):
        raise AssertionError(
            "test_scoped_selection_identity.py MUST NOT construct "
            "PromotionRecord -- the canonical aggregate proof uses "
            "records=() and the receipt as the only authority. "
            f"Found construction at line {_node.lineno}."
        )
del _ast, _source, _tree, _node

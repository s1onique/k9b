"""Success-path client-to-mapper tests.

ACT-K9B-HULK-PROMOTION-TYPED-DISPATCH-RESULT-AND-SUMMARY-CONVERGENCE01.

Covers the canonical success and aggregate-zero cases. The
completed projection carries the ``PromotionSucceeded`` outcome,
the aggregate receipt (the bounded evidence of the attempt),
the deterministic request fingerprint, and the
``DEFINITELY_COMMITTED`` disposition.
"""

from __future__ import annotations

import json

from scoped_client_mapper_support import (
    REQUEST_ID,
    RUN_ID,
    run_round_trip,
    valid_canonical_payload,
)

from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionSucceeded,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionCompletedProjection,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpSucceeded,
    ScopedPromotionReceipt,
    scoped_promotion_request_fingerprint,
)


class TestScopedSuccessProjection:
    def test_canonical_success_with_actionable_ids(self) -> None:
        """Canonical success: aggregate receipt + actionable IDs."""
        def handler(request) -> None:
            request.respond(
                200,
                json.dumps(
                    valid_canonical_payload(("inc-001",))
                ).encode(),
            )

        context, transport, projection = run_round_trip(handler)
        assert isinstance(transport, ScopedPromotionHttpSucceeded)
        assert isinstance(projection, ScopedPromotionCompletedProjection)
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionSucceeded)
        assert outcome.run_id == RUN_ID
        assert outcome.diagnosis_incident_ids == ("inc-001",)
        assert projection.aggregate_receipt is not None
        assert isinstance(
            projection.aggregate_receipt, ScopedPromotionReceipt
        )
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_COMMITTED
        )
        assert projection.requires_reconciliation is False
        assert projection.request_id == REQUEST_ID
        assert projection.request_fingerprint == (
            scoped_promotion_request_fingerprint(context.request)
        )
        assert len(projection.request_fingerprint) == 64

    def test_aggregate_successful_zero(self) -> None:
        """Aggregate zero: completed with no actionable IDs."""
        def handler(request) -> None:
            request.respond(
                200,
                json.dumps(valid_canonical_payload(())).encode(),
            )

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, ScopedPromotionHttpSucceeded)
        assert isinstance(projection, ScopedPromotionCompletedProjection)
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionSucceeded)
        assert outcome.diagnosis_incident_ids == ()
        assert projection.aggregate_receipt is not None
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_COMMITTED
        )

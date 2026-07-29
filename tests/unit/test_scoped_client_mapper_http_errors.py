"""HTTP-response client-to-mapper tests.

ACT-K9B-HULK-PROMOTION-TYPED-DISPATCH-RESULT-AND-SUMMARY-CONVERGENCE01.

Covers the terminal HTTP outcomes: 2xx that is not a successful
wire parse (202, 204, empty body, malformed JSON, invalid
schema), 401 / 403 (authentication rejected), and
non-validated 4xx / 5xx errors (commit-unknown). A malformed
``500`` MUST NOT become authentication rejection.
"""

from __future__ import annotations

import json

from scoped_client_mapper_support import (
    _LoopboxRequest,
    run_round_trip,
)

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpRejected,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionCommitUnknown,
    PromotionRejectionCode,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionRejectedProjection,
    ScopedPromotionUncertainProjection,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpAuthenticationRejected,
)


class TestScopedHttpErrors:
    def test_202_accepted(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(202, b"")

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, PromotionHttpAccepted)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_ACCEPTED_WITHOUT_RESULT
        )
        assert projection.commit_disposition is (
            PromotionCommitDisposition.MAY_HAVE_COMMITTED
        )
        assert projection.requires_reconciliation is True

    def test_204_no_content(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(204, b"")

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, PromotionHttpNoContent)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_NO_CONTENT_AFTER_SEND
        )

    def test_empty_200_body(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, b"")

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, PromotionHttpInvalidJson)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_INVALID_JSON
        )

    def test_malformed_json(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, b"not json at all {{{")

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, PromotionHttpInvalidJson)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_INVALID_JSON
        )

    def test_invalid_scoped_schema(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps({"ok": True}).encode())

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, PromotionHttpInvalidSchema)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_INVALID_SCHEMA
        )

    def test_401_authentication_rejected(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                401, json.dumps({"message": "unauthorized"}).encode()
            )

        _, transport, projection = run_round_trip(handler)
        assert isinstance(
            transport, ScopedPromotionHttpAuthenticationRejected
        )
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        assert projection.promotion_outcome.reason is (
            PromotionRejectionCode.AUTHENTICATION_REJECTED
        )
        assert projection.requires_reconciliation is False

    def test_403_authentication_rejected(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                403, json.dumps({"message": "forbidden"}).encode()
            )

        _, transport, projection = run_round_trip(handler)
        assert isinstance(
            transport, ScopedPromotionHttpAuthenticationRejected
        )
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        assert projection.promotion_outcome.reason is (
            PromotionRejectionCode.AUTHENTICATION_REJECTED
        )

    def test_untyped_400(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(400, json.dumps({"error": "bad"}).encode())

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, PromotionHttpRejected)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.PROMOTION_HTTP_ERROR_UNCERTAIN
        )
        assert isinstance(
            projection.promotion_outcome, PromotionCommitUnknown
        )

    def test_untyped_409(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(409, json.dumps({"error": "conflict"}).encode())

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, PromotionHttpRejected)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.PROMOTION_HTTP_ERROR_UNCERTAIN
        )

    def test_malformed_500_remains_commit_unknown(self) -> None:
        """A malformed ``500`` MUST NOT become authentication rejection."""
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                500, b"internal server error stack trace..."
            )

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, PromotionHttpRejected)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.PROMOTION_HTTP_ERROR_UNCERTAIN
        )
        # Never an authentication rejection.
        assert not (
            isinstance(projection, ScopedPromotionRejectedProjection)
            and projection.promotion_outcome.reason
            is PromotionRejectionCode.AUTHENTICATION_REJECTED
        )

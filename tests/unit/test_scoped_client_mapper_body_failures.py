"""Body-failure client-to-mapper tests.

ACT-K9B-HULK-PROMOTION-TYPED-DISPATCH-RESULT-AND-SUMMARY-CONVERGENCE01.

Covers ``Content-Length`` mismatch (short read) and bounded-cap
oversize (body limit) responses. Body-read failures differ from
dispatch failures: the response headers were received, so the
mapper projects them to the uncertain branch via the closed
HTTP_RESPONSE_SHORT_READ / HTTP_RESPONSE_BODY_LIMIT_EXCEEDED
codes.
"""

from __future__ import annotations

from scoped_client_mapper_support import (
    _LoopboxRequest,
    run_round_trip,
)

from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionUncertainProjection,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpBodyLimitExceeded,
    ScopedPromotionHttpShortRead,
)


class TestScopedBodyFailures:
    def test_body_limit_exceeded(self) -> None:
        """Body exceeds the bounded cap: body limit variant."""
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                200,
                b"x" * 1024,
                content_length=2 * 1024 * 1024,
            )

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, ScopedPromotionHttpBodyLimitExceeded)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_RESPONSE_BODY_LIMIT_EXCEEDED
        )

    def test_short_read(self) -> None:
        """``Content-Length`` declares more bytes than received: short read."""
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                200,
                b"incomplete",
                content_length=1024,
            )

        _, transport, projection = run_round_trip(handler)
        assert isinstance(transport, ScopedPromotionHttpShortRead)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_RESPONSE_SHORT_READ
        )

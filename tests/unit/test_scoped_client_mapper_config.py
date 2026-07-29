"""Configuration-reason client-to-mapper tests.

ACT-K9B-HULK-PROMOTION-TYPED-DISPATCH-RESULT-AND-SUMMARY-CONVERGENCE01.

Proves the typed client distinguishes ``MISSING_BACKEND_URL``
from ``MISSING_INTERNAL_TOKEN``. Each missing-field case maps
to the closed ``CONFIGURATION_BLOCKED`` rejection code via
the typed ``ScopedPromotionHttpBeforeSendFailed`` variant.
"""

from __future__ import annotations

from scoped_client_mapper_support import (
    LoopbackServer,
    scoped_context,
)

from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionRejected,
    PromotionRejectionCode,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionRejectedProjection,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedBeforeSendFailureReason,
    ScopedPromotionHttpBeforeSendFailed,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
    ScopedSchedulerClient,
)


class TestScopedConfigurationReasonIdentity:
    """Distinguish missing URL from missing token at the typed seam."""

    def test_missing_backend_url_returns_typed_before_send_failure(self) -> None:
        client = ScopedSchedulerClient(base_url="", token="placeholder")
        context = scoped_context()
        transport = client.promote_alert_signals_scoped(context=context)
        projection = _map(transport, context)
        assert isinstance(transport, ScopedPromotionHttpBeforeSendFailed)
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        assert transport.reason_code is (
            ScopedBeforeSendFailureReason.MISSING_BACKEND_URL
        )
        assert projection.promotion_outcome.reason is (
            PromotionRejectionCode.CONFIGURATION_BLOCKED
        )
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )
        assert projection.requires_reconciliation is False
        assert isinstance(projection.promotion_outcome, PromotionRejected)

    def test_missing_token_returns_typed_before_send_failure(self) -> None:
        with LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token=None)
            context = scoped_context()
            transport = client.promote_alert_signals_scoped(context=context)
            projection = _map(transport, context)
        assert isinstance(transport, ScopedPromotionHttpBeforeSendFailed)
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        assert transport.reason_code is (
            ScopedBeforeSendFailureReason.MISSING_INTERNAL_TOKEN
        )
        assert projection.promotion_outcome.reason is (
            PromotionRejectionCode.CONFIGURATION_BLOCKED
        )


def _map(transport, context):
    from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
        map_scoped_http_transport_to_promotion_outcome,
    )

    return map_scoped_http_transport_to_promotion_outcome(
        transport, context=context
    )

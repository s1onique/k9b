"""Dispatch-failure client-to-mapper tests.

ACT-K9B-HULK-PROMOTION-TYPED-DISPATCH-RESULT-AND-SUMMARY-CONVERGENCE01.

Covers read / connect / pre-connect / dispatch-level failures
that prevent the typed client from confirming whether the
request reached the wire. The mapper projects these to either
``ScopedPromotionRejectedProjection`` (pre-connect proof) or
``ScopedPromotionUncertainProjection`` (transmission unknown).
"""

from __future__ import annotations

import socket
import urllib.error as urllib_error
from unittest.mock import patch

from scoped_client_mapper_support import (
    LoopbackServer,
    scoped_context,
)

from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionRejectionCode,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionRejectedProjection,
    ScopedPromotionUncertainProjection,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpBeforeSendFailed,
    ScopedPromotionHttpDispatchUncertain,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
    ScopedSchedulerClient,
)


class TestScopedDispatchFailures:
    """Dispatch / pre-connect failures that the real client surfaces."""

    def test_read_timeout(self) -> None:
        """``TimeoutError`` from ``urllib`` → dispatch-uncertain TIMEOUT."""
        with LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token="placeholder")
            context = scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=TimeoutError("read timeout"),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.001
                )
                from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
                    map_scoped_http_transport_to_promotion_outcome,
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpDispatchUncertain)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND
        )

    def test_connection_lost_post_send(self) -> None:
        """``ConnectionResetError`` → dispatch-uncertain CONNECTION_LOST."""
        with LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token="placeholder")
            context = scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=ConnectionResetError("connection reset"),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.001
                )
                from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
                    map_scoped_http_transport_to_promotion_outcome,
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpDispatchUncertain)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        assert projection.promotion_outcome.reason is (
            PromotionUncertaintyCode.HTTP_CONNECTION_LOST_AFTER_SEND
        )

    def test_dns_failure(self) -> None:
        """DNS failure → rejected with BACKEND_UNREACHABLE."""
        with LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token="placeholder")
            context = scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=urllib_error.URLError(
                    socket.gaierror(-2, "Name or service not known")
                ),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.5
                )
                from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
                    map_scoped_http_transport_to_promotion_outcome,
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpBeforeSendFailed)
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        assert projection.promotion_outcome.reason is (
            PromotionRejectionCode.BACKEND_UNREACHABLE
        )

    def test_connection_refused(self) -> None:
        """``ConnectionRefusedError`` → rejected with BACKEND_UNREACHABLE."""
        with LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token="placeholder")
            context = scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=urllib_error.URLError(
                    ConnectionRefusedError("connection refused")
                ),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.5
                )
                from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
                    map_scoped_http_transport_to_promotion_outcome,
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpBeforeSendFailed)
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        assert projection.promotion_outcome.reason is (
            PromotionRejectionCode.BACKEND_UNREACHABLE
        )

    def test_generic_transmission_unknown(self) -> None:
        """Unknown ``URLError`` → dispatch-uncertain TRANSMISSION_UNKNOWN."""
        with LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token="placeholder")
            context = scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=urllib_error.URLError(
                    OSError(0, "ephemeral low-level failure")
                ),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.001
                )
                from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
                    map_scoped_http_transport_to_promotion_outcome,
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpDispatchUncertain)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        reason = projection.promotion_outcome.reason
        assert reason in (
            PromotionUncertaintyCode.HTTP_TRANSMISSION_UNKNOWN,
            PromotionUncertaintyCode.HTTP_CONNECTION_LOST_AFTER_SEND,
        )

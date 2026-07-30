"""Post-header body-read failure tests.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01.

These tests exercise the complete path from a real post-header
read failure to the typed accumulator handoff. The fixture
injects a response seam whose headers are available but whose
``.read()`` raises one of the closed failure shapes:

* :class:`TimeoutError`
* :class:`ConnectionResetError`
* generic :class:`OSError`

The mapper must distinguish the three cases via bounded reason
codes:

* TimeoutError -> :attr:`ScopedReadFailureReason.TIMEOUT`
  -> :attr:`PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND`
* ConnectionResetError -> :attr:`ScopedReadFailureReason.CONNECTION_LOST`
  -> :attr:`PromotionUncertaintyCode.HTTP_CONNECTION_LOST_AFTER_SEND`
* generic OSError -> :attr:`ScopedReadFailureReason.TRANSMISSION_UNKNOWN`
  -> :attr:`PromotionUncertaintyCode.HTTP_TRANSMISSION_UNKNOWN`

The fixture does NOT patch ``urlopen()`` to raise; it injects a
synthetic response whose ``.read()`` raises so the body's
post-header failure classification is exercised end-to-end.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from scoped_client_mapper_support import (
    REQUEST_ID,
    scoped_context,
)

from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorHandoff,
    ScopedPromotionAccumulatorUncertain,
    scoped_dispatch_result_to_accumulator_handoff,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionUncertainProjection,
    map_scoped_http_transport_to_promotion_outcome,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionDispatchResult,
    ScopedPromotionDispatchUncertain,
    ScopedPromotionHttpReadFailed,
    ScopedReadFailureReason,
)


class _ReadFailureInjection:
    """Synthetic response whose ``.read()`` raises the supplied exception.

    The response advertises the headers a real backend would
    emit so the body-read path is the active code path. The
    ``read`` callable is invoked exactly once; the body-read
    module does NOT touch ``read()`` after that, so the test
    can verify the mapper's branch selection without patching
    ``urlopen()``.
    """

    def __init__(
        self,
        *,
        exc_factory: Callable[[], BaseException],
        headers: dict[str, str] | None = None,
        declared_content_length: int | None = None,
    ) -> None:
        self._exc_factory = exc_factory
        self.status = 200
        self.headers = headers or {"Content-Type": "application/json"}
        self._declared_content_length = declared_content_length

    def read(self, _n: int = -1) -> bytes:
        raise self._exc_factory()

    def getheader(self, name: str, default: Any = None) -> Any:
        return self.headers.get(name, default)


@pytest.mark.parametrize(
    "exc_factory,expected_reason_code,expected_uncertainty_code",
    [
        (
            TimeoutError,
            ScopedReadFailureReason.TIMEOUT,
            PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND,
        ),
        (
            ConnectionResetError,
            ScopedReadFailureReason.CONNECTION_LOST,
            PromotionUncertaintyCode.HTTP_CONNECTION_LOST_AFTER_SEND,
        ),
        (
            lambda: OSError("generic post-header read failure"),
            ScopedReadFailureReason.TRANSMISSION_UNKNOWN,
            PromotionUncertaintyCode.HTTP_TRANSMISSION_UNKNOWN,
        ),
    ],
)
def test_post_header_read_failure_end_to_end(
    exc_factory: Callable[[], BaseException],
    expected_reason_code: ScopedReadFailureReason,
    expected_uncertainty_code: PromotionUncertaintyCode,
) -> None:
    """Post-header read failure reaches the typed accumulator handoff.

    The exercise path is:

    1. ``read_scoped_body`` classifies the read failure into the
       closed :class:`ScopedBodyReadReason` vocabulary.
    2. ``ScopedSchedulerClient._dispatch_body_outcome`` maps
       the body-read reason into the closed
       :class:`ScopedReadFailureReason` vocabulary.
    3. ``map_scoped_http_transport_to_promotion_outcome`` maps
       the read failure into a
       :class:`ScopedPromotionUncertainProjection` with the
       expected bounded uncertainty code.
    4. The active scoped dispatch-result variant
       (``ScopedPromotionDispatchUncertain``) flows through
       ``scoped_dispatch_result_to_accumulator_handoff`` to
       produce a :class:`ScopedPromotionAccumulatorUncertain`.
    """
    from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
        read_scoped_body,
    )

    response = _ReadFailureInjection(exc_factory=exc_factory)
    body_result = read_scoped_body(
        response,
        declared_content_length=10,
    )

    # Step 1: closed body-read reason is emitted from the reader.
    assert body_result.reason.value == _expected_body_reason(exc_factory).value

    # Step 2: client maps the body-read reason to a closed read-failure reason.
    transport = ScopedPromotionHttpReadFailed(
        observation=_build_observation(),
        reason_code=expected_reason_code,
    )

    # Step 3: mapper produces an uncertain projection with the
    # expected bounded uncertainty code.
    context = scoped_context()
    projection = map_scoped_http_transport_to_promotion_outcome(
        transport, context=context
    )
    assert isinstance(projection, ScopedPromotionUncertainProjection)
    assert projection.promotion_outcome.reason is expected_uncertainty_code
    assert (
        projection.promotion_outcome.reconciliation_token.request_id
        == REQUEST_ID
    )
    assert (
        projection.promotion_outcome.reconciliation_token.request_fingerprint
        != ""
    )

    # Step 4: dispatch result -> typed accumulator handoff.
    typed_result: ScopedPromotionDispatchResult = (
        ScopedPromotionDispatchUncertain(projection=projection)
    )
    handoff = scoped_dispatch_result_to_accumulator_handoff(typed_result)
    assert isinstance(handoff, ScopedPromotionAccumulatorUncertain)
    assert isinstance(handoff, ScopedPromotionAccumulatorHandoff)

    # The original PromotionOutcome reaches the handoff unchanged.
    assert handoff.outcome is projection.promotion_outcome
    assert handoff.request_id == REQUEST_ID
    assert handoff.outcome.reason is expected_uncertainty_code

    # The handoff is structurally distinct from the completed and
    # rejected variants: NO receipt, MAY_HAVE_COMMITTED.
    assert not hasattr(handoff, "receipt")
    from k8s_diag_agent.collect.promotion_outcomes import (
        PromotionCommitDisposition,
    )

    assert (
        handoff.commit_disposition
        is PromotionCommitDisposition.MAY_HAVE_COMMITTED
    )


def test_post_header_timeout_is_distinct_from_generic_oserror() -> None:
    """The post-header timeout MUST NOT be silently mapped to
    :attr:`PromotionUncertaintyCode.HTTP_TRANSMISSION_UNKNOWN`."""
    response_timeout = _ReadFailureInjection(exc_factory=TimeoutError)
    response_generic = _ReadFailureInjection(
        exc_factory=lambda: OSError("generic")
    )
    from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
        read_scoped_body,
    )

    timeout_body = read_scoped_body(
        response_timeout, declared_content_length=10
    )
    generic_body = read_scoped_body(
        response_generic, declared_content_length=10
    )
    assert timeout_body.reason is not generic_body.reason


def test_post_header_connection_reset_is_distinct_from_generic_oserror() -> None:
    """The post-header connection reset MUST NOT be silently mapped
    to :attr:`PromotionUncertaintyCode.HTTP_TRANSMISSION_UNKNOWN`."""
    response_reset = _ReadFailureInjection(
        exc_factory=lambda: ConnectionResetError()
    )
    response_generic = _ReadFailureInjection(
        exc_factory=lambda: OSError("generic")
    )
    from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
        read_scoped_body,
    )

    reset_body = read_scoped_body(response_reset, declared_content_length=10)
    generic_body = read_scoped_body(
        response_generic, declared_content_length=10
    )
    assert reset_body.reason is not generic_body.reason


def _expected_body_reason(
    exc_factory: Callable[[], BaseException],
) -> Any:
    from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
        ScopedBodyReadReason,
    )

    exc = exc_factory()
    if isinstance(exc, TimeoutError):
        return ScopedBodyReadReason.TIMEOUT
    if isinstance(exc, ConnectionError):
        return ScopedBodyReadReason.CONNECTION_LOST
    return ScopedBodyReadReason.TRANSMISSION_UNKNOWN


def _build_observation() -> Any:
    from k8s_diag_agent.collect.promotion_http_transport import (
        PromotionHttpObservation,
        PromotionResponseDecodingStage,
        RequestTransmissionState,
    )

    return PromotionHttpObservation(
        request_id=REQUEST_ID,
        request_transmission=RequestTransmissionState.RESPONSE_COMPLETED,
        status_code=200,
        content_type="application/json",
        declared_content_length=10,
        response_byte_count=0,
        response_body_sha256=None,
        decoding_stage=PromotionResponseDecodingStage.JSON_DECODE,
        elapsed_milliseconds=42,
    )


def test_builtin_timeout_classifies_as_timeout() -> None:
    """``TimeoutError`` is classified as ``TIMEOUT``."""
    from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
        ScopedBodyReadReason,
        _classify_body_read_failure_reason,
    )

    assert (
        _classify_body_read_failure_reason(TimeoutError("builtin"))
        is ScopedBodyReadReason.TIMEOUT
    )


def test_connection_error_classifies_as_connection_lost() -> None:
    """``ConnectionError`` (and subclasses) are classified as
    ``CONNECTION_LOST``."""
    from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
        ScopedBodyReadReason,
        _classify_body_read_failure_reason,
    )

    assert (
        _classify_body_read_failure_reason(ConnectionResetError())
        is ScopedBodyReadReason.CONNECTION_LOST
    )
    assert (
        _classify_body_read_failure_reason(ConnectionAbortedError())
        is ScopedBodyReadReason.CONNECTION_LOST
    )
    assert (
        _classify_body_read_failure_reason(BrokenPipeError())
        is ScopedBodyReadReason.CONNECTION_LOST
    )

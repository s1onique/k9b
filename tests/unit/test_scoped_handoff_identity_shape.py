"""Request-identity shape invariants for typed scoped handoffs.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-
ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

Every typed scoped-accumulator handoff declares both a ``request_id``
and a ``request_fingerprint``. Both fields have a SHAPE-only
authority in this ACT:

* ``request_id`` MUST be a non-empty string bounded by
  ``MAX_REQUEST_ID_LENGTH``.
* ``request_fingerprint`` MUST be a canonical SHA-256 (64
  lower-case hex chars).

The accumulator's derivable projections
(``scoped_promotion_request_id``,
``scoped_promotion_request_fingerprint``) MUST agree with the
handoff's fields by identity and MUST be empty strings before any
handoff is recorded.

Each test in this matrix constructs a deliberately malformed handoff
(by passing raw values into the closed-union dataclass's
``__post_init__`` validation gate) and verifies the construction
fault is detected with the right exception class.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)

# Imports kept local to avoid cycles during pytest collection.
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_recorder import (  # noqa: E402
    ScopedPromotionAtomicRecorderMixin,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    MAX_REQUEST_ID_LENGTH,
)
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
)

# ---------------------------------------------------------------------------
# Identity projections on an empty accumulator
# ---------------------------------------------------------------------------


class TestIdentityProjectionEmpty:
    """Identity projections are derived and empty when no handoff exists."""

    def test_empty_accumulator_identity_fields_are_empty(self) -> None:
        acc = RunPromotionAccumulator()
        assert acc.scoped_promotion_handoff is None
        assert acc.scoped_promotion_request_id == ""
        assert acc.scoped_promotion_request_fingerprint == ""

    def test_assignment_to_request_id_is_forbidden(self) -> None:
        acc = RunPromotionAccumulator()
        with pytest.raises(AttributeError, match="forbidden"):
            acc.scoped_promotion_request_id = "manual-override"  # type: ignore[misc]

    def test_assignment_to_request_fingerprint_is_forbidden(self) -> None:
        acc = RunPromotionAccumulator()
        with pytest.raises(AttributeError, match="forbidden"):
            acc.scoped_promotion_request_fingerprint = "f" * 64  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Request id shape rejections (handoff construction invariant)
# ---------------------------------------------------------------------------


class TestRequestIdShapeRejections:
    """``request_id`` MUST be a bounded non-empty string."""

    def test_request_id_none_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="non-empty"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=None,  # type: ignore[arg-type]
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_request_id_non_string_int_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="non-empty"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=123,  # type: ignore[arg-type]
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_request_id_empty_string_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="non-empty"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id="",
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_request_id_over_max_length_is_rejected(self) -> None:
        handoff = completed_handoff()
        too_long = "x" * (MAX_REQUEST_ID_LENGTH + 1)
        with pytest.raises(ValueError, match="exceeds"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=too_long,
                request_fingerprint=handoff.request_fingerprint,
            )


# ---------------------------------------------------------------------------
# Request fingerprint shape rejections (handoff construction invariant)
# ---------------------------------------------------------------------------


class TestRequestFingerprintShapeRejections:
    """``request_fingerprint`` MUST be a canonical SHA-256."""

    def test_fingerprint_none_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="canonical"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint=None,  # type: ignore[arg-type]
            )

    def test_fingerprint_too_short_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="canonical"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint="a" * 63,
            )

    def test_fingerprint_too_long_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="canonical"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint="a" * 65,
            )

    def test_fingerprint_uppercase_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="canonical"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint=("A" + "a" * 63),
            )

    def test_fingerprint_non_hex_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="canonical"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint="g" * 64,
            )

    def test_fingerprint_with_sha256_prefix_is_rejected(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(ValueError, match="canonical"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint="sha256:" + "a" * 64,
            )


# ---------------------------------------------------------------------------
# Handoff must agree with the outcome's reconciliation token / signal_ids.
# ---------------------------------------------------------------------------


class TestIdentityWithOutcomeAgreement:
    """Successful handoff construction requires outcome <=> receipt agreement."""

    def test_outcome_run_id_mismatch_is_rejected(self) -> None:
        from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
            ScopedPromotionReceipt,
        )
        from tests.unit.scoped_handoff_atomic_support import (
            _make_bound,
        )

        handoff = completed_handoff(run_id="run-correct")
        # A separate receipt bound to a different run id will trigger the
        # outcome-vs-receipt run_id check below.
        wrong_bound = _make_bound(
            run_id="run-different",
            requested_signal_ids=handoff.outcome.requested_signal_ids,
            diagnosis_incident_ids=(),
        )
        wrong_receipt = ScopedPromotionReceipt(bound=wrong_bound)
        with pytest.raises(ValueError, match="run_id"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=wrong_receipt,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_requested_signal_ids_mismatch_is_rejected(self) -> None:
        handoff = completed_handoff(
            requested_signal_ids=("sig-a", "sig-b")
        )
        from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
            ScopedPromotionReceipt,
        )
        from tests.unit.scoped_handoff_atomic_support import (
            _make_bound,
        )
        wrong_bound = _make_bound(
            run_id=handoff.outcome.run_id,
            requested_signal_ids=("sig-x", "sig-y"),
            diagnosis_incident_ids=(),
        )
        wrong_receipt = ScopedPromotionReceipt(bound=wrong_bound)
        with pytest.raises(ValueError, match="requested_signal_ids"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=wrong_receipt,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )


# ---------------------------------------------------------------------------
# Accumulator identity is derived once a handoff is recorded.
# ---------------------------------------------------------------------------


class TestIdentityProjectionAfterRecord:
    """Once a handoff is recorded, identity fields follow the handoff verbatim."""

    def test_identity_fields_track_recorded_handoff(self) -> None:
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-corr03",),
        )
        acc = RunPromotionAccumulator()
        from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
            PromotionOutcomeRecording,
        )
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff,
            batch=__import__(
                "tests.unit.scoped_handoff_atomic_support",  # noqa: E402
                fromlist=["make_completed_batch"],
            ).make_completed_batch(handoff=handoff),
        )
        assert recording is PromotionOutcomeRecording.NEW
        assert acc.scoped_promotion_handoff is handoff
        assert acc.scoped_promotion_request_id == handoff.request_id
        assert (
            acc.scoped_promotion_request_fingerprint
            == handoff.request_fingerprint
        )


# ---------------------------------------------------------------------------
# Sanity: the test module actually exercises the new mixin.
# ---------------------------------------------------------------------------


def test_atomic_mixin_present_on_accumulator() -> None:
    """``RunPromotionAccumulator`` MUST inherit the atomic recorder mixin."""
    assert issubclass(
        RunPromotionAccumulator, ScopedPromotionAtomicRecorderMixin
    )

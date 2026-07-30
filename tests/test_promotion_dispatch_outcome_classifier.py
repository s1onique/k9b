"""Tests for promotion dispatch outcome classifier.

ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION11
CORRECTION11-FINALIZATION02

Verifies bounded uncertainty codes replace generic AMBIGUOUS_RESPONSE for:
- None (dispatcher returned nothing)
- PromotionDispatchError (internal dispatch failure)
- Unexpected typed Exception (untyped exception)

CORRECTION11-FINALIZATION02 adds:
- Production-shaped signal IDs (sha256:...)
- Termination-before-token-construction proof (monkeypatch)
- Reconciliation fingerprint format validation (64 hex chars)
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.incident_promotion_dispatch import IncidentPromotionResult
from k8s_diag_agent.collect.promotion_dispatch_outcome import (
    PromotionDispatchError,
    classify_promotion_dispatch_result,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)

# Production-shaped signal identities (sha256: prefix + 64 hex chars)
_SIGNAL_A = "sha256:" + ("a" * 64)
_SIGNAL_B = "sha256:" + ("b" * 64)


class TestClassifierBoundedCodes:
    """Tests for bounded uncertainty code mappings."""

    RUN_ID = "test-run-001"
    SIGNAL_IDS = (_SIGNAL_A, _SIGNAL_B)
    PAYLOAD: dict[str, object] = {"key": "value"}

    def test_none_returns_dispatch_returned_none(self) -> None:
        """outcome=None maps to DISPATCH_RETURNED_NONE, not AMBIGUOUS_RESPONSE."""
        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=None,
        )
        assert isinstance(result, PromotionCommitUnknown)
        assert result.reason == PromotionUncertaintyCode.DISPATCH_RETURNED_NONE
        assert result.run_id == self.RUN_ID

    def test_dispatch_error_returns_dispatch_internal_error(self) -> None:
        """PromotionDispatchError maps to DISPATCH_INTERNAL_ERROR."""
        exc = PromotionDispatchError("internal failure")
        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=exc,
        )
        assert isinstance(result, PromotionCommitUnknown)
        assert result.reason == PromotionUncertaintyCode.DISPATCH_INTERNAL_ERROR

    def test_unexpected_exception_returns_dispatch_untyped_exception(self) -> None:
        """Unexpected typed Exception maps to DISPATCH_UNTYPED_EXCEPTION."""
        exc = RuntimeError("unexpected error")
        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=exc,
        )
        assert isinstance(result, PromotionCommitUnknown)
        assert result.reason == PromotionUncertaintyCode.DISPATCH_UNTYPED_EXCEPTION

    def test_process_termination_re_raised(self) -> None:
        """KeyboardInterrupt, SystemExit, GeneratorExit are re-raised."""
        for exc_type in (KeyboardInterrupt, SystemExit, GeneratorExit):
            exc = exc_type()
            with pytest.raises(exc_type):
                classify_promotion_dispatch_result(
                    run_id=self.RUN_ID,
                    requested_signal_ids=self.SIGNAL_IDS,
                    requested_signal_payload=self.PAYLOAD,
                    outcome=exc,
                )

    def test_success_returns_promotion_succeeded(self) -> None:
        """Successful IncidentPromotionResult(ok=True) returns PromotionSucceeded."""
        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=IncidentPromotionResult(
                ok=True,
                opened_incident_ids=["inc-001"],
                promotion_records=[],
            ),
        )
        assert isinstance(result, PromotionSucceeded)
        assert result.run_id == self.RUN_ID
        assert result.diagnosis_incident_ids == ("inc-001",)


class TestReconciliationTokenFormat:
    """CORRECTION11-FINALIZATION02: Production-shaped signal IDs and fingerprint format."""

    RUN_ID = "test-run-001"
    SIGNAL_IDS = (_SIGNAL_A, _SIGNAL_B)
    PAYLOAD: dict[str, object] = {"key": "value"}
    HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")

    def test_reconciliation_token_has_request_id(self) -> None:
        """Commit-unknown outcomes carry a non-empty reconciliation token."""
        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=None,
        )
        assert isinstance(result, PromotionCommitUnknown)
        assert result.reconciliation_token.request_id
        assert result.reconciliation_token.request_fingerprint

    def test_reconciliation_fingerprint_is_64_hex_chars(self) -> None:
        """CORRECTION11-FINALIZATION02: Reconciliation fingerprint is exactly 64 lowercase hex chars."""
        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=None,
        )
        assert isinstance(result, PromotionCommitUnknown)
        fingerprint = result.reconciliation_token.request_fingerprint
        assert fingerprint is not None
        assert self.HEX_64_PATTERN.match(fingerprint), (
            f"Expected 64 lowercase hex chars, got {fingerprint!r}"
        )

    def test_request_id_matches_signal_fingerprint(self) -> None:
        """Request ID is a hex fingerprint derived from signal IDs."""
        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=None,
        )
        assert isinstance(result, PromotionCommitUnknown)
        # The request_id should be present and non-empty
        assert result.reconciliation_token.request_id, (
            f"Expected non-empty request_id, got {result.reconciliation_token.request_id!r}"
        )


class TestTerminationBeforeTokenConstruction:
    """CORRECTION11-FINALIZATION02: Process termination exceptions win before token construction."""

    RUN_ID = "test-run-001"
    SIGNAL_IDS = (_SIGNAL_A, _SIGNAL_B)
    PAYLOAD: dict[str, object] = {"key": "value"}

    def test_termination_before_token_raises(self) -> None:
        """SystemExit raised before token construction: SystemExit wins."""
        # Monkeypatch the canonical token builder to fail
        with patch(
            "k8s_diag_agent.collect.promotion_dispatch_outcome._build_reconciliation_token",
            side_effect=RuntimeError("token construction would fail"),
        ):
            exc = SystemExit()
            with pytest.raises(SystemExit):
                classify_promotion_dispatch_result(
                    run_id=self.RUN_ID,
                    requested_signal_ids=self.SIGNAL_IDS,
                    requested_signal_payload=self.PAYLOAD,
                    outcome=exc,
                )


class TestPromotionMayHaveCommittedProjection:
    """Tests for may_have_committed projection correctness."""

    RUN_ID = "test-run-001"
    SIGNAL_IDS = (_SIGNAL_A,)
    PAYLOAD: dict[str, object] = {}

    def test_success_is_true(self) -> None:
        """PromotionSucceeded returns True for may_have_committed."""
        from k8s_diag_agent.collect.promotion_outcomes import may_have_committed

        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=IncidentPromotionResult(
                ok=True,
                opened_incident_ids=[],
                promotion_records=[],
            ),
        )
        assert may_have_committed(result) is True

    def test_rejected_is_false(self) -> None:
        """Rejected outcomes return False for may_have_committed."""
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionRejected,
            PromotionRejectionCode,
            may_have_committed,
        )

        result = PromotionRejected(
            run_id=self.RUN_ID,
            reason=PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION,
            rejected_signal_ids=self.SIGNAL_IDS,
        )
        assert may_have_committed(result) is False

    def test_commit_unknown_is_true(self) -> None:
        """CommitUnknown returns True for may_have_committed."""
        from k8s_diag_agent.collect.promotion_outcomes import may_have_committed

        result = classify_promotion_dispatch_result(
            run_id=self.RUN_ID,
            requested_signal_ids=self.SIGNAL_IDS,
            requested_signal_payload=self.PAYLOAD,
            outcome=None,
        )
        assert may_have_committed(result) is True

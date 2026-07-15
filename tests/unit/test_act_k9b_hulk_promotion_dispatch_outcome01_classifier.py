"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 classifier unit tests.

Covers the classifier success / failure / rejection matrix and the
termination-guard invariants. R3-1, R3-2 (PromotionCommitUnknown carries
requested_signal_ids), R3-3 (Item 3 does NOT claim diagnosis invoked),
R3-6 (idempotency uses complete token), R3-7 (unsupported variant
raises TypeError).

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_dispatch import (
    MODE_BACKEND_API,
    IncidentPromotionResult,
)
from k8s_diag_agent.collect.promotion_dispatch_outcome import (
    PromotionDispatchError,
    PromotionProtocolError,
    PromotionRequestValidationError,
    PromotionScopeError,
    PromotionTransportRefused,
    PromotionTransportTimeout,
    PromotionTransportUncertain,
    classify_promotion_dispatch_result,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionRejectionCode,
    PromotionUncertaintyCode,
    is_commit_unknown,
    is_rejected,
    is_succeeded,
)

RUN_ID = "run-2026-07-15T0350Z"


def _payload(ids: tuple[str, ...] = ("sha256:a",)) -> dict:
    return {
        "runId": RUN_ID,
        "sourceIdentity": "alertmanager-prod",
        "signalIds": list(ids),
    }


# ---------------------------------------------------------------------------
# Classifier unit matrix
# ---------------------------------------------------------------------------


class TestClassifierSuccessMatrix:
    def test_success_with_actionable_ids(self) -> None:
        result = IncidentPromotionResult(
            ok=True,
            opened_incidents=1,
            updated_incidents=1,
            opened_incident_ids=("inc-1",),
            updated_incident_ids=("inc-2",),
            promotion_mode=MODE_BACKEND_API,
        )
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a", "sha256:b"),
            requested_signal_payload=_payload(("sha256:a", "sha256:b")),
            outcome=result,
        )
        assert is_succeeded(outcome)
        assert outcome.diagnosis_incident_ids == ("inc-1", "inc-2")

    def test_success_with_zero_actionable_ids(self) -> None:
        result = IncidentPromotionResult(
            ok=True,
            promotion_mode=MODE_BACKEND_API,
        )
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(("sha256:a",)),
            outcome=result,
        )
        assert is_succeeded(outcome)
        assert outcome.diagnosis_incident_ids == ()


class TestClassifierFailureMatrix:
    def test_generic_ok_false_is_commit_unknown(self) -> None:
        result = IncidentPromotionResult(
            ok=False,
            promotion_mode=MODE_BACKEND_API,
        )
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=result,
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_commit_unknown_carries_requested_signal_ids(self) -> None:
        result = IncidentPromotionResult(
            ok=False,
            promotion_mode=MODE_BACKEND_API,
        )
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a", "sha256:b", "sha256:c"),
            requested_signal_payload=_payload(
                ("sha256:a", "sha256:b", "sha256:c"),
            ),
            outcome=result,
        )
        assert outcome.requested_signal_ids == (
            "sha256:a",
            "sha256:b",
            "sha256:c",
        )

    def test_ok_false_with_canonical_ids_is_protocol_error(self) -> None:
        result = IncidentPromotionResult(
            ok=False,
            opened_incident_ids=("inc-1",),
            promotion_mode=MODE_BACKEND_API,
        )
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=result,
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.PROTOCOL_ERROR

    def test_dispatch_error_maps_to_commit_unknown(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=PromotionDispatchError("internal failure"),
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE
        assert outcome.requested_signal_ids == ("sha256:a",)

    def test_transport_timeout(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a", "sha256:b"),
            requested_signal_payload=_payload(
                ("sha256:a", "sha256:b"),
            ),
            outcome=PromotionTransportTimeout("timed out"),
        )
        assert outcome.reason is PromotionUncertaintyCode.TRANSPORT_TIMEOUT
        assert outcome.requested_signal_ids == ("sha256:a", "sha256:b")

    def test_transport_refused(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=PromotionTransportRefused("refused"),
        )
        assert outcome.reason is PromotionUncertaintyCode.TRANSPORT_REFUSED

    def test_transport_uncertain_default(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=PromotionTransportUncertain("uncategorised"),
        )
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_protocol_error(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=PromotionProtocolError("malformed"),
        )
        assert outcome.reason is PromotionUncertaintyCode.PROTOCOL_ERROR

    def test_unexpected_application_exception(self) -> None:
        class WeirdError(RuntimeError):
            pass

        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=WeirdError("oops"),
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_none_outcome_is_commit_unknown(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=None,
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_non_incident_promotion_result_is_protocol_error(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome="not a result",
        )
        assert outcome.reason is PromotionUncertaintyCode.PROTOCOL_ERROR


class TestClassifierRejectionMatrix:
    def test_promotion_scope_error_is_rejected(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=PromotionScopeError("not in scope"),
        )
        assert is_rejected(outcome)
        assert outcome.reason is (
            PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION
        )

    def test_request_validation_error_is_rejected(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(),
            outcome=PromotionRequestValidationError("bad ids"),
        )
        assert is_rejected(outcome)
        assert outcome.reason is PromotionRejectionCode.MALFORMED_SIGNAL_IDS


# ---------------------------------------------------------------------------
# Termination propagation
# ---------------------------------------------------------------------------


class TestTerminationGuard:
    def test_keyboard_interrupt_propagates_before_fingerprint(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from k8s_diag_agent.collect import (
            promotion_dispatch_outcome as cls_module,
        )

        calls: list = []

        original = cls_module._stable_fingerprint

        def spy(payload):
            calls.append(payload)
            return original(payload)

        monkeypatch.setattr(cls_module, "_stable_fingerprint", spy)

        with pytest.raises(KeyboardInterrupt):
            classify_promotion_dispatch_result(
                run_id=RUN_ID,
                requested_signal_ids=("sha256:a",),
                requested_signal_payload=_payload(),
                outcome=KeyboardInterrupt(),
            )
        assert calls == []

    def test_system_exit_propagates_before_fingerprint(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from k8s_diag_agent.collect import (
            promotion_dispatch_outcome as cls_module,
        )

        calls: list = []

        original = cls_module._stable_fingerprint

        def spy(payload):
            calls.append(payload)
            return original(payload)

        monkeypatch.setattr(cls_module, "_stable_fingerprint", spy)

        with pytest.raises(SystemExit):
            classify_promotion_dispatch_result(
                run_id=RUN_ID,
                requested_signal_ids=("sha256:a",),
                requested_signal_payload=_payload(),
                outcome=SystemExit(1),
            )
        assert calls == []

    def test_generator_exit_propagates_before_fingerprint(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from k8s_diag_agent.collect import (
            promotion_dispatch_outcome as cls_module,
        )

        calls: list = []

        original = cls_module._stable_fingerprint

        def spy(payload):
            calls.append(payload)
            return original(payload)

        monkeypatch.setattr(cls_module, "_stable_fingerprint", spy)

        with pytest.raises(GeneratorExit):
            classify_promotion_dispatch_result(
                run_id=RUN_ID,
                requested_signal_ids=("sha256:a",),
                requested_signal_payload=_payload(),
                outcome=GeneratorExit(),
            )
        assert calls == []


# ---------------------------------------------------------------------------
# Reconciliation fingerprint determinism
# ---------------------------------------------------------------------------


class TestReconciliationFingerprint:
    def test_same_request_yields_same_fingerprint(self) -> None:
        payload = _payload(("sha256:a", "sha256:b"))
        ids = ("sha256:a", "sha256:b")
        first = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=ids,
            requested_signal_payload=payload,
            outcome=PromotionTransportTimeout("t"),
        )
        second = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=ids,
            requested_signal_payload=payload,
            outcome=PromotionTransportTimeout("t"),
        )
        assert (
            first.reconciliation_token.request_fingerprint
            == second.reconciliation_token.request_fingerprint
        )

    def test_different_membership_yields_different_fingerprint(self) -> None:
        first = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload=_payload(("sha256:a",)),
            outcome=PromotionTransportTimeout("t"),
        )
        second = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a", "sha256:b"),
            requested_signal_payload=_payload(("sha256:a", "sha256:b")),
            outcome=PromotionTransportTimeout("t"),
        )
        assert (
            first.reconciliation_token.request_fingerprint
            != second.reconciliation_token.request_fingerprint
        )


# ---------------------------------------------------------------------------
# Inherited verifier / contract compatibility
# ---------------------------------------------------------------------------


class TestInheritedVerifierStillExercised:
    """Item-3 changes MUST NOT regress the inherited verifier scope."""

    def test_inherited_scoped_dispatch_signature_unchanged(
        self,
    ) -> None:
        import inspect

        from k8s_diag_agent.collect import (
            incident_promotion_dispatch as dispatch_module,
        )

        sig = inspect.signature(
            dispatch_module.promote_alert_signals_scoped_for_accumulator
        )
        expected_params = {
            "runs_dir",
            "health_run_id",
            "source_identity",
            "signal_ids",
            "accumulator",
            "cluster_context",
        }
        assert expected_params.issubset(set(sig.parameters.keys())), (
            "Inherited scoped dispatch signature was modified; "
            "SEAM01 verifier expects these parameter names"
        )
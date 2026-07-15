"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 direct tests.

Covers direct classifier invariants, telemetry projection (R3-2, R3-3,
R3-7), and reconciliation-token determinism.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PromotionRecord,
)
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
    promotion_outcome_event_fields,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
    is_commit_unknown,
    is_rejected,
    is_succeeded,
)

# ---------------------------------------------------------------------------
# Telemetry projection tests (R3-2, R3-3, R3-7)
# ---------------------------------------------------------------------------


class TestTelemetryProjection:
    def test_succeeded_projection(self) -> None:
        records = (
            PromotionRecord(
                source_candidate_id="cand-1",
                canonical_incident_id="inc-1",
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            ),
            PromotionRecord(
                source_candidate_id="cand-2",
                canonical_incident_id="inc-2",
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            ),
        )
        outcome = PromotionSucceeded(
            run_id="run",
            requested_signal_ids=("sha256:a", "sha256:b"),
            records=records,
            diagnosis_incident_ids=("inc-1",),
        )
        projection = promotion_outcome_event_fields(outcome)
        assert projection["promotion_outcome"] == "succeeded"
        assert projection["promotion_outcome_reason"] == ""
        assert projection["promotion_may_have_committed"] is True
        assert projection["diagnosis_handoff_available"] is True
        assert projection["diagnosis_handoff_incident_count"] == 1
        assert projection["diagnosis_invoked"] is False
        assert projection["promotion_consistency_error_recorded"] is False
        assert projection["promotion_outcome_available"] is True
        assert projection["reconciliation_required"] is False
        assert projection["requested_signal_count"] == 2
        assert projection["canonical_incident_id_count"] == 1
        assert projection["promotion_record_count"] == 2
        # R3-3: Item 3 does NOT claim diagnosis actually ran.
        assert "promotion_propagated_to_diagnosis" not in projection

    def test_rejected_projection(self) -> None:
        outcome = PromotionRejected(
            run_id="run",
            reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
            rejected_signal_ids=("sha256:a", "sha256:b"),
        )
        projection = promotion_outcome_event_fields(outcome)
        assert projection["promotion_outcome"] == "rejected"
        assert projection["promotion_outcome_reason"] == "worklist_inconsistent"
        assert projection["promotion_may_have_committed"] is False
        assert projection["diagnosis_handoff_available"] is False
        assert projection["diagnosis_handoff_incident_count"] == 0
        assert projection["promotion_consistency_error_recorded"] is True
        assert projection["reconciliation_required"] is False
        assert projection["canonical_incident_id_count"] == 0
        assert projection["requested_signal_count"] == 2

    def test_commit_unknown_projection_uses_carried_ids(self) -> None:
        """R3-2: ``requested_signal_count`` is non-zero when ``PromotionCommitUnknown``
        carries a non-empty ``requested_signal_ids``."""
        outcome = PromotionCommitUnknown(
            run_id="run",
            reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
            reconciliation_token=PromotionReconciliationToken(
                request_id="req",
                request_fingerprint="sha256:abc",
            ),
            requested_signal_ids=("sha256:a", "sha256:b", "sha256:c"),
        )
        projection = promotion_outcome_event_fields(outcome)
        assert projection["promotion_outcome"] == "commit_unknown"
        assert projection["promotion_outcome_reason"] == "transport_timeout"
        assert projection["requested_signal_count"] == 3
        assert projection["reconciliation_required"] is True
        assert projection["promotion_consistency_error_recorded"] is True
        assert projection["canonical_incident_id_count"] == 0
        assert projection["diagnosis_handoff_available"] is False

    def test_unknown_variant_raises_type_error(self) -> None:
        """R3-7: unsupported variants raise ``TypeError``."""
        with pytest.raises(TypeError):
            promotion_outcome_event_fields("not a PromotionOutcome")


# ---------------------------------------------------------------------------
# Direct classifier unit-coverage
# ---------------------------------------------------------------------------


class TestDirectClassifierInvariants:
    """The classifier itself satisfies the production matrix."""

    def test_success_with_ids(self) -> None:
        result = IncidentPromotionResult(
            ok=True,
            scanned=2,
            firing=2,
            opened_incidents=1,
            updated_incidents=1,
            promotion_mode=MODE_BACKEND_API,
            opened_incident_ids=("inc-1",),
            updated_incident_ids=("inc-2",),
            promotion_records=(),
        )
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a", "sha256:b"),
            requested_signal_payload={
                "runId": "run",
                "signalIds": ["sha256:a", "sha256:b"],
            },
            outcome=result,
        )
        assert is_succeeded(outcome)
        assert outcome.diagnosis_incident_ids == ("inc-1", "inc-2")

    def test_success_with_empty_ids(self) -> None:
        result = IncidentPromotionResult(
            ok=True,
            scanned=33,
            firing=33,
            promotion_mode=MODE_BACKEND_API,
        )
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=result,
        )
        assert is_succeeded(outcome)
        assert outcome.diagnosis_incident_ids == ()

    def test_generic_failure_is_commit_unknown(self) -> None:
        result = IncidentPromotionResult(
            ok=False,
            scanned=2,
            firing=2,
            promotion_mode=MODE_BACKEND_API,
        )
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a", "sha256:b"),
            requested_signal_payload={"runId": "run"},
            outcome=result,
        )
        assert is_commit_unknown(outcome)

    def test_ok_false_with_ids_is_protocol_error(self) -> None:
        result = IncidentPromotionResult(
            ok=False,
            scanned=2,
            firing=2,
            opened_incident_ids=("inc-1",),
            promotion_mode=MODE_BACKEND_API,
        )
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=result,
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.PROTOCOL_ERROR

    def test_dispatch_error_is_commit_unknown(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionDispatchError("internal error"),
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_request_validation_error_is_rejected(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionRequestValidationError("bad ids"),
        )
        assert is_rejected(outcome)
        assert outcome.reason is PromotionRejectionCode.MALFORMED_SIGNAL_IDS

    def test_transport_timeout(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionTransportTimeout("timeout"),
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.TRANSPORT_TIMEOUT

    def test_transport_refused(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionTransportRefused("refused"),
        )
        assert outcome.reason is PromotionUncertaintyCode.TRANSPORT_REFUSED

    def test_protocol_error(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionProtocolError("malformed"),
        )
        assert outcome.reason is PromotionUncertaintyCode.PROTOCOL_ERROR

    def test_transport_uncertain_default(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionTransportUncertain("uncategorised"),
        )
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_unexpected_application_exception(self) -> None:
        class WeirdError(RuntimeError):
            pass

        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=WeirdError("oops"),
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_none_outcome_is_commit_unknown(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=None,
        )
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_non_incident_result_is_protocol_error(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome="not a result",
        )
        assert outcome.reason is PromotionUncertaintyCode.PROTOCOL_ERROR

    def test_promotion_scope_error_is_rejected(self) -> None:
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionScopeError("not in scope"),
        )
        assert is_rejected(outcome)
        assert outcome.reason is (
            PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION
        )


# ---------------------------------------------------------------------------
# Reconciliation token / fingerprint determinism
# ---------------------------------------------------------------------------


class TestReconciliationTokenDeterminism:
    """Same logical request -> same fingerprint."""

    def test_same_request_same_fingerprint(self) -> None:
        payload = {"runId": "run", "sourceIdentity": "src", "signalIds": ["a", "b"]}
        ids = ("a", "b")
        first = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=ids,
            requested_signal_payload=payload,
            outcome=PromotionTransportTimeout("t"),
        )
        second = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=ids,
            requested_signal_payload=payload,
            outcome=PromotionTransportTimeout("t"),
        )
        assert first.reconciliation_token.request_fingerprint == (
            second.reconciliation_token.request_fingerprint
        )

    def test_different_membership_different_fingerprint(self) -> None:
        first = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("a",),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionTransportTimeout("t"),
        )
        second = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("a", "b"),
            requested_signal_payload={"runId": "run"},
            outcome=PromotionTransportTimeout("t"),
        )
        assert (
            first.reconciliation_token.request_fingerprint
            != second.reconciliation_token.request_fingerprint
        )

    def test_dict_key_ordering_is_deterministic(self) -> None:
        # The classifier sorts JSON dict keys when computing the
        # fingerprint (sort_keys=True in the helper).
        first = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run", "signalIds": ["sha256:a"]},
            outcome=PromotionTransportTimeout("t"),
        )
        second = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"signalIds": ["sha256:a"], "runId": "run"},
            outcome=PromotionTransportTimeout("t"),
        )
        assert (
            first.reconciliation_token.request_fingerprint
            == second.reconciliation_token.request_fingerprint
        )
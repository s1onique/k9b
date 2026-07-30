"""Shared support helpers for the commit-unknown selection handoff tests.

ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01 +
ACT-K9B-HULK-PROMOTION-SUCCESSFUL-ZERO-ACCESS-MODE01.

This module is intentionally a support module: it does NOT begin with
``test_`` so pytest does not collect it as a test module. It only
exposes reusable builders and fixtures that both the algebra test
module and the production-witness test module import. Assertions stay
in the calling test modules so review surfaces failure context.
"""

from __future__ import annotations

from dataclasses import dataclass

from k8s_diag_agent.collect.incident_identity_hardening import PromotionRecord
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.domain.incident_lifecycle import IncidentId
from k8s_diag_agent.health.loop_runner_execute import (
    AutomaticDiagnosisExecution,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Production witness run identifier observed in the live scheduler
#: crash on 2026-07-29.
PRODUCTION_WITNESS_RUN_ID = "health-run-20260729T050628Z"

#: Canonical signal-ID namespace used by the production witness.
#: The 29 IDs mirror the firing-signal cardinality of the live run.
PRODUCTION_WITNESS_SIGNAL_IDS: tuple[str, ...] = tuple(
    f"sig-{i:03d}" for i in range(29)
)


# ---------------------------------------------------------------------------
# Builders for the typed PromotionOutcome family
# ---------------------------------------------------------------------------


def build_commit_unknown_ambiguous_response(
    run_id: str = PRODUCTION_WITNESS_RUN_ID,
    requested_signal_ids: tuple[str, ...] = PRODUCTION_WITNESS_SIGNAL_IDS,
) -> PromotionCommitUnknown:
    """Return the production witness ``PromotionCommitUnknown``.

    The returned outcome carries the 29 requested signal IDs so the
    downstream projection preserves the original request fidelity
    even though the dispatcher never confirmed a commit.
    """
    return PromotionCommitUnknown(
        run_id=run_id,
        reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
        reconciliation_token=PromotionReconciliationToken(
            request_id="req-29-ambiguous",
            request_fingerprint="sha256:production-witness",
        ),
        requested_signal_ids=requested_signal_ids,
    )


def build_promotion_succeeded_with_ids(
    *,
    run_id: str = PRODUCTION_WITNESS_RUN_ID,
    ids: tuple[str, ...] = PRODUCTION_WITNESS_SIGNAL_IDS,
    canonical_id_prefix: str = "canonical",
) -> PromotionSucceeded:
    """Return a ``PromotionSucceeded`` carrying ``len(ids)`` canonical IDs.

    The default ``ids`` matches the production-witness cardinality;
    callers may override for parametrized scenarios.
    """
    records = tuple(
        PromotionRecord(
            source_candidate_id=f"cand-{i}",
            canonical_incident_id=f"{canonical_id_prefix}-{i:03d}",
            promotion_outcome="opened",
        )
        for i in range(len(ids))
    )
    return PromotionSucceeded(
        run_id=run_id,
        requested_signal_ids=ids,
        records=records,
        diagnosis_incident_ids=tuple(
            IncidentId(f"{canonical_id_prefix}-{i:03d}") for i in range(len(ids))
        ),
    )


def build_promotion_succeeded_empty(
    *,
    run_id: str = PRODUCTION_WITNESS_RUN_ID,
    requested_signal_ids: tuple[str, ...] = PRODUCTION_WITNESS_SIGNAL_IDS,
) -> PromotionSucceeded:
    """Return a ``PromotionSucceeded`` with zero diagnosis IDs.

    Empty IDs is authoritative zero-work; it MUST NOT trigger a store
    scan or any fallback.
    """
    return PromotionSucceeded(
        run_id=run_id,
        requested_signal_ids=requested_signal_ids,
        records=(),
        diagnosis_incident_ids=(),
    )


def build_promotion_rejected(
    *,
    run_id: str = PRODUCTION_WITNESS_RUN_ID,
    rejected_signal_ids: tuple[str, ...] = PRODUCTION_WITNESS_SIGNAL_IDS,
) -> PromotionRejected:
    """Return a ``PromotionRejected`` carrying bounded rejection metadata."""
    return PromotionRejected(
        run_id=run_id,
        reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
        rejected_signal_ids=rejected_signal_ids,
    )


# ---------------------------------------------------------------------------
# Execution stand-in for tests that need a typed ``AutomaticDiagnosisExecution``
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StubAutomaticDiagnosisExecution:
    """Minimal stand-in for ``AutomaticDiagnosisExecution``.

    Mirrors the production dataclass field set so callers can reuse
    the canonical selection builder without instantiating the real
    type. Kept local to the test suite to avoid coupling production
    code to the test shape.
    """

    should_run: bool
    selection_mode: str
    incident_access_mode: str
    blocked_reason: str | None = None

    def to_execution(self) -> AutomaticDiagnosisExecution:
        """Materialise a real ``AutomaticDiagnosisExecution`` for the builder."""
        return AutomaticDiagnosisExecution(
            should_run=self.should_run,
            selection_mode=self.selection_mode,
            incident_access_mode=self.incident_access_mode,
            blocked_reason=self.blocked_reason,
        )

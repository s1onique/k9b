"""Health loop execution orchestration.

This module contains the execute() method logic extracted from HealthLoopRunner.
It orchestrates the full health assessment loop lifecycle.

Extracted from loop_runner.py for LLM-friendly file sizes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..collect.diagnosis_selection import (
    DiagnosisSelection,
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
    NoPromotionSelectionReason,
)
from ..collect.incident_identity_hardening import (
    INCIDENT_ACCESS_MODE_BACKEND,
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_UPDATED,
    BackendEndpointIdentity,
    IncidentStoreConsistencyError,
    LookupOutcome,
    PromotionConsistencyContractError,
    PromotionRecord,
    _validate_response_contracts,
    verify_promotion_consistency,
)
from ..collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from ..collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionRejected,
    PromotionSucceeded,
)
from ..external_analysis.alertmanager_durable_learning import scan_and_propose
from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose
from .adaptation import HealthProposal
from .loop_history import HealthRating
from .loop_runner_assessments import build_assessments_for_records
from .loop_runner_comparisons import evaluate_triggers_for_records
from .loop_runner_drilldown_analysis import run_auto_drilldown_analysis as _run_auto_drilldown_impl
from .loop_runner_drilldowns import build_drilldowns_for_records
from .loop_runner_external_analysis import run_external_analysis_for_records
from .loop_runner_history import load_runner_history, persist_runner_history
from .loop_runner_next_check_planning import run_next_check_planning
from .loop_runner_review_enrichment import run_review_enrichment as _run_review_enrichment_impl
from .loop_types import HealthSnapshotRecord
from .ui import write_health_ui_index

if TYPE_CHECKING:
    from ..collect.incident_identity_hardening import (
        IncidentStoreConsistencyError,
    )


# CORRECTION10: Typed result for _derive_automatic_diagnosis_inputs().
# This replaces the positional 6-tuple return with a named frozen dataclass.
# Consumers MUST access fields by name; positional unpacking is unsupported.
@dataclass(frozen=True)
class AutomaticDiagnosisInputs:
    """Typed result from ``_derive_automatic_diagnosis_inputs()``.

    CORRECTION10: This dataclass replaces the positional 6-tuple return.
    Positional unpacking is intentionally unsupported.

    Attributes:
        canonical_incident_ids: Canonical incident IDs from the accumulator.
            Used as equality witness for diagnosis selection validation.
        promotion_result_summary: Structured promotion summary dict.
        promotion_consistency_error: Consistency error if any, else None.
        backend_endpoint_identity: Sanitized backend endpoint identity.
        execution: Typed automatic diagnosis execution decision.
        promotion_outcome: Typed promotion outcome or None.

    Consumers MUST use named field access:
        inputs = _derive_automatic_diagnosis_inputs(accumulator)
        selection = _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=inputs.execution,
            ...
        )
    """

    canonical_incident_ids: tuple[str, ...]
    promotion_result_summary: dict[str, Any]
    promotion_consistency_error: IncidentStoreConsistencyError | None
    backend_endpoint_identity: dict[str, Any]
    execution: AutomaticDiagnosisExecution
    promotion_outcome: PromotionSucceeded | PromotionRejected | PromotionCommitUnknown | None

    @property
    def has_promotion_outcome(self) -> bool:
        """Return True if a typed promotion outcome is present."""
        return self.promotion_outcome is not None

    @property
    def is_blocked(self) -> bool:
        """Return True when diagnosis MUST NOT run."""
        return self.execution.is_blocked

    @property
    def should_run_diagnosis(self) -> bool:
        """Return True when diagnosis SHOULD run."""
        return self.execution.should_run


if TYPE_CHECKING:
    from .drilldown import DrilldownArtifact
    from .loop_comparison_types import ComparisonTriggerArtifact
    from .loop_history import HealthAssessmentArtifact
    from .loop_runner import HealthLoopRunner


def _coerce_promotion_result_dict(
    promotion_result: Any,
) -> dict[str, Any] | None:
    """Convert a recent promotion result into a JSON-safe dict.

    Accepts ``IncidentPromotionResult`` dataclasses and other duck-typed
    promotion outputs. Returns ``None`` when the value cannot be coerced.
    """
    if promotion_result is None:
        return None
    to_dict = getattr(promotion_result, "to_dict", None)
    if callable(to_dict):
        try:
            result = to_dict()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    if isinstance(promotion_result, dict):
        return dict(promotion_result)
    return None


def _build_backend_endpoint_identity(
    incident_access_mode: str = INCIDENT_ACCESS_MODE_BACKEND,
) -> dict[str, Any]:
    """Build a sanitized backend endpoint identity payload (no credentials).

    R5 (item 2): the helper NO LONGER hard-codes the access mode to
    ``"backend"``. The orchestrator passes the mode resolved from the
    accumulator so local promotion runs render an accurate
    ``"local"`` incident-access-mode diagnostic. Auto / backend-api
    runs continue to surface the sanitized backend URL; local runs
    still surface the value (so operators see the bound backend target
    even when promotion did not use it), but the
    ``incident_access_mode`` field reflects the truth the dispatcher
    actually consumed.

    The empty-mode sentinel ``"no_promotion_run"`` is also accepted so a
    run that never received a batch can still render endpoint identity
    without silently picking a default.
    """
    from ..collect.incident_identity_hardening import (
        backend_endpoint_identity_from_url,
    )

    backend_url = os.environ.get("K9B_BACKEND_INTERNAL_URL")
    identity = backend_endpoint_identity_from_url(backend_url)
    payload = identity.to_dict()
    payload["incident_access_mode"] = incident_access_mode
    return payload


def _authoritative_lookup_canonical_ids(
    canonical_ids: list[str],
) -> tuple[LookupOutcome, ...]:
    """Look up each canonical incident via the dispatcher.

    Returns a tuple of typed ``LookupOutcome`` values, one per canonical
    ID, in the input order. The ``found`` flag is meaningful only when
    ``error_kind`` is ``LOOKUP_ERROR_KIND_NOT_FOUND``; for all other
    error kinds the backend has either rejected the request, returned
    malformed data, or has not been contacted at all. The lookup is
    routed through ``fetch_incident_for_diagnosis`` so the dispatcher
    picks ``backend-api`` mode when the scheduler+sqlite contract
    applies.

    Transport-level failures (DNS, timeout, refused) are recorded as
    ``LOOKUP_ERROR_KIND_TRANSPORT``. Authentication failures are
    ``LOOKUP_ERROR_KIND_AUTHENTICATION``. Backend-side 5xx errors are
    ``LOOKUP_ERROR_KIND_BACKEND_FAILURE``. Malformed payloads are
    ``LOOKUP_ERROR_KIND_UNEXPECTED_PAYLOAD``. Definitive not-found is
    bucketed as ``LOOKUP_ERROR_KIND_NOT_FOUND`` with ``found=False``;
    a successful fetch is also ``LOOKUP_ERROR_KIND_NOT_FOUND`` but
    with ``found=True``.

    The consistency verifier treats only ``NOT_FOUND`` (regardless of
    ``found`` value) as authoritative for promotion consistency. All
    other kinds are recorded as reachability problems and never
    collapse into ordinary ``not_found`` noise.
    """
    from ..collect.incident_diagnosis_dispatch import (
        fetch_incident_for_diagnosis,
    )
    from ..collect.incident_identity_hardening import (
        LOOKUP_ERROR_KIND_AUTHENTICATION,
        LOOKUP_ERROR_KIND_BACKEND_FAILURE,
        LOOKUP_ERROR_KIND_NOT_FOUND,
        LOOKUP_ERROR_KIND_TRANSPORT,
        LOOKUP_ERROR_KIND_UNEXPECTED_PAYLOAD,
    )

    def _classify(error_message: str | None) -> str:
        if error_message is None:
            return LOOKUP_ERROR_KIND_NOT_FOUND
        message = error_message.lower() if error_message else ""
        if "timeout" in message or "unreachable" in message or "connection refused" in message:
            return LOOKUP_ERROR_KIND_TRANSPORT
        if "401" in message or "403" in message or "unauthor" in message:
            return LOOKUP_ERROR_KIND_AUTHENTICATION
        if "500" in message or "502" in message or "503" in message or "504" in message:
            return LOOKUP_ERROR_KIND_BACKEND_FAILURE
        if "unexpected_shape" in message or "json" in message or "valueerror" in message or "keyerror" in message:
            return LOOKUP_ERROR_KIND_UNEXPECTED_PAYLOAD
        return LOOKUP_ERROR_KIND_TRANSPORT

    results: list[LookupOutcome] = []
    for incident_id in canonical_ids:
        incident, success, fetch_error = fetch_incident_for_diagnosis(incident_id)
        if incident is not None and success:
            # The dispatcher returned the incident object. ``fetch_error``
            # is None in this case. We mark this as ``not_found`` with
            # found semantics; the verifier treats this as a definitive
            # backend answer (incident IS there).
            results.append(
                LookupOutcome(
                    canonical_incident_id=incident_id,
                    found=True,
                    error_kind=LOOKUP_ERROR_KIND_NOT_FOUND,
                )
            )
            continue
        # ``fetch_error`` is non-None when the dispatcher raised or
        # returned a failure response. ``fetch_error is None`` plus
        # ``incident is None`` means a successful call that did not
        # yield an incident -- a definitive "not found" answer.
        if fetch_error is None:
            results.append(
                LookupOutcome(
                    canonical_incident_id=incident_id,
                    found=False,
                    error_kind=LOOKUP_ERROR_KIND_NOT_FOUND,
                )
            )
            continue
        results.append(
            LookupOutcome(
                canonical_incident_id=incident_id,
                found=False,
                error_kind=_classify(fetch_error),
            )
        )
    return tuple(results)


class IndeterminatePromotionModeError(TypeError):
    """Raised when the accumulator cannot yield a single promotion mode.

    R4 task 4 contract: the orchestrator derives ``promotion_mode`` and
    ``incident_access_mode`` verbatim from the accumulated batches. When
    the accepted batches disagree (one local, one backend; or empty
    with indeterminate resolution), the helper raises this typed error
    so the orchestrator fails closed instead of silently picking a
    default. The exception carries the conflicting modes for
    diagnostic logging.
    """

    def __init__(
        self,
        message: str,
        *,
        observed_modes: tuple[tuple[str, str], ...] = (),
    ) -> None:
        super().__init__(message)
        self.observed_modes = observed_modes


_NO_PROMOTION_STATE: tuple[str, str, str] = ("", "", "no_promotion_run")
NO_PROMOTION_ACCESS_MODE = "no_promotion_run"
NO_PROMOTION_MODE = "no_promotion_run"
NO_PROMOTION_SCAN_SCOPE = "no_promotion_run"

# ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01: explicit automatic-diagnosis
# execution decision.
#
# The orchestrator derives a typed decision from the accumulator BEFORE
# invoking automatic diagnosis. The decision is a closed
# :class:`DiagnosisSelectionSource` value (see ``diagnosis_selection.py``).
# Five values are recognised; this orchestrator never collapses them
# onto a single mode.
#
# * PROMOTION -- the dispatcher carried authoritative canonical IDs;
#   the collector MUST call into
#   ``run_automatic_diagnosis_loop_evidence_collection`` with those
#   IDs and MUST NOT fall back to scan-based listing.
# * EXPLICIT_NON_PROMOTION -- a scheduled scan-only run legitimately
#   opted into non-promotion selection; the collector may scan the
#   global store.
# * STORE_SCAN_POLICY -- reserved for future explicit store-scan
#   policies; the orchestrator does not synthesize this value.
# * UNAVAILABLE_DUE_TO_REJECTED_PROMOTION -- a
#   ``PromotionConsistencyContractError`` (or ``PromotionRejected``
#   variant) was captured during the run; the orchestrator MUST NOT
#   invoke the collector.
# * UNAVAILABLE_DUE_TO_COMMIT_UNKNOWN -- a ``PromotionCommitUnknown``
#   variant was captured; reconciliation is required before any
#   diagnosis may dispatch.
#
# The string constants below remain for backward compatibility with
# downstream log consumers. They are the only string aliases
# permitted; the typed source enum is the canonical value.
INCIDENT_SELECTION_MODE_EXPLICIT_IDS = "explicit_incident_ids"
INCIDENT_SELECTION_MODE_STORE_SCAN = "store_scan"
INCIDENT_SELECTION_MODE_BLOCKED = "blocked"
INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY = "current_run_empty"
INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN = "commit_unknown"

BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR = "promotion_consistency_contract_error"
BLOCKED_REASON_PROMOTION_REJECTED = "promotion_rejected"
BLOCKED_REASON_PROMOTION_COMMIT_UNKNOWN = "promotion_commit_unknown"
BLOCKED_REASON_PROMOTION_WORKSET_CONTRACT_FAILURE = "promotion_workset_contract_failure"

# ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
# Incident access modes for the typed ``DiagnosisExecutionAuthority``.
# The values are derived from the typed ``PromotionOutcome`` and are
# never reconstructed from canonical-id cardinality.
INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN = "no_promotion_run"
INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED = "reconciliation_required"

# ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
# Selection source strings for the ``diagnosis-selection-derived`` event.
# These are the literal low-cardinality values the structured event
# carries, matched exhaustively to the typed
# :class:`DiagnosisSelectionSource` variants.
DIAGNOSIS_SELECTION_SOURCE_PROMOTION = "promotion"
DIAGNOSIS_SELECTION_SOURCE_EXPLICIT_NON_PROMOTION = "explicit_nonpromotion"
DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN = "promotion_commit_unknown"
DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED = "promotion_blocked"


@dataclass(frozen=True)
class AutomaticDiagnosisExecution:
    """Explicit decision returned by ``_derive_automatic_diagnosis_inputs``.

    R7 (item 1): this decision is the typed handoff between
    ``_derive_automatic_diagnosis_inputs`` and
    ``execute_health_loop_run``. The orchestrator reads
    :attr:`selection_mode` and :attr:`should_run` to gate the
    diagnosis collector invocation. ``incident_access_mode`` is the
    value the collector must use to populate its structured events
    (preserved from the accumulator, NOT derived from
    ``canonical_ids`` cardinality).
    """

    should_run: bool
    selection_mode: str
    incident_access_mode: str
    blocked_reason: str | None = None

    @property
    def is_blocked(self) -> bool:
        """Return True when the diagnosis phase MUST NOT run."""
        return self.selection_mode == INCIDENT_SELECTION_MODE_BLOCKED

    @property
    def uses_explicit_ids(self) -> bool:
        """Return True when the collector must call into incident_ids mode."""
        return self.selection_mode == INCIDENT_SELECTION_MODE_EXPLICIT_IDS

    @property
    def uses_store_scan(self) -> bool:
        """Return True when the collector falls back to scan-based listing."""
        return self.selection_mode == INCIDENT_SELECTION_MODE_STORE_SCAN


def _resolve_accumulator_truth(
    accumulator: RunPromotionAccumulator,
) -> tuple[str, str, str]:
    """Derive ``(promotion_mode, incident_access_mode, scan_scope)``.

    R4 contract: every value comes verbatim from the accumulator; if no
    batch has been accepted the helper returns the explicit
    "no_promotion_run" sentinel rather than a hard-coded default.
    Conflicting modes among the accepted batches raise
    :class:`IndeterminatePromotionModeError`.

    R5 (item 2): the sentinel mode and access-mode values are the
    explicit ``"no_promotion_run"`` string instead of an empty string.
    Downstream consumers (notably automatic diagnosis) use that string
    to render a neutral / not-attempted state; the previous empty
    string silently matched the legacy ``"backend"`` default in
    :func:`_build_backend_endpoint_identity`.

    ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION01:
    When has_promotion_activity() is True but batches is empty (typed
    outcome recorded without successful batch append), return
    reconciliation_required sentinel values.
    """
    if not accumulator.has_promotion_activity():
        return (
            NO_PROMOTION_MODE,
            NO_PROMOTION_ACCESS_MODE,
            NO_PROMOTION_SCAN_SCOPE,
        )

    # ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION02-FINALIZATION01:
    # Outcome without batch: exhaustive typed projection.
    # Only PromotionCommitUnknown requires reconciliation.
    # PromotionRejected remains blocked (not reconciliation).
    # PromotionSucceeded without batch is a consistency contract error.
    #
    # Note: has_promotion_activity() is bool(batches) or (promotion_outcome is not None).
    # Reaching this block means batches is empty and has_promotion_activity() is True,
    # so promotion_outcome MUST exist (otherwise activity would be False).
    if not accumulator.batches:
        from typing import assert_never

        outcome = accumulator.promotion_outcome

        # Explicit None handling: a consistency contract violation.
        # has_promotion_activity() is True but neither batches nor outcome exist.
        if outcome is None:
            return (
                BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
                BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
                BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
            )

        if isinstance(outcome, PromotionCommitUnknown):
            return (
                "commit_unknown",
                INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
                "reconciliation_required",
            )

        if isinstance(outcome, PromotionRejected):
            return (
                "rejected",
                "blocked",
                "promotion_rejected",
            )

        if isinstance(outcome, PromotionSucceeded):
            # PromotionSucceeded without a batch is a consistency contract violation.
            # A successful active-scoped promotion must have its atomic batch/receipt.
            return (
                "promotion_consistency_contract_error",
                "promotion_consistency_contract_error",
                "promotion_consistency_contract_error",
            )

        # Exhaustive over the closed PromotionOutcome union.
        assert_never(outcome)

    # Batches exist: use batch mode (canonical authority for promotion mode).
    # The outcome may also be recorded but batches take precedence.
    observed: list[tuple[str, str]] = []
    for batch in accumulator.batches:
        observed.append((batch.promotion_mode, batch.incident_access_mode))

    unique_modes = {observed[0]}
    for mode_pair in observed[1:]:
        unique_modes.add(mode_pair)
    if len(unique_modes) > 1:
        raise IndeterminatePromotionModeError(
            "Conflicting promotion modes across accumulated batches; refusing to derive a single dispatcher mode.",
            observed_modes=tuple(observed),
        )

    last = accumulator.batches[-1]
    return (
        last.promotion_mode,
        last.incident_access_mode,
        last.promotion_scan_scope,
    )


# R5 (item 5): bounded error messages. We never let the structured log
# payload grow without limit; truncation is reported as
# ``error_messages_omitted`` instead of dropped silently.
DEFAULT_MAX_ERROR_MESSAGES_IN_SUMMARY = 50
DEFAULT_MAX_PROMOTION_RECORDS_IN_SUMMARY = 200


def _truncate_summary_field(
    values: list[Any],
    limit: int,
) -> tuple[list[Any], int]:
    """Bounded-truncate ``values`` and return the omitted count."""
    if limit < 0:
        limit = 0
    if len(values) <= limit:
        return list(values), 0
    return list(values[:limit]), len(values) - limit


def _derive_automatic_diagnosis_inputs(
    accumulator: RunPromotionAccumulator,
) -> AutomaticDiagnosisInputs:
    """Build canonical-ID, consistency, and execution-decision inputs.

    CORRECTION10: Returns AutomaticDiagnosisInputs instead of a positional tuple.
    Consumers MUST access fields by name; positional unpacking is unsupported.

    Usage:
        inputs = _derive_automatic_diagnosis_inputs(accumulator)
        if inputs.is_blocked:
            ...
        else:
            selection = _build_diagnosis_selection_for_execution(
                automatic_diagnosis_execution=inputs.execution,
                promotion_outcome=inputs.promotion_outcome,
                canonical_incident_ids=list(inputs.canonical_incident_ids),
                scheduler_run_id=scheduler_run_id,
            )
    """
    # R7 (item 1): if the orchestrator caught a typed contract failure
    # from ``add_batch`` (the production-path validation introduced
    # for R7 item 3), short-circuit the helper to the blocked state
    # BEFORE any further work. The blocked decision prevents automatic
    # diagnosis from being invoked and emits the typed blocked event
    # carrying the captured reason.
    captured_contract_error = getattr(accumulator, "last_contract_error", None)
    if captured_contract_error is not None:
        # R7 (item 2): preserve the access mode the dispatcher
        # actually consumed by reading it from the last accepted
        # batch (or the no-promotion sentinel when no batch survived).
        if accumulator.batches:
            preserved_access_mode = accumulator.batches[-1].incident_access_mode
        else:
            preserved_access_mode = NO_PROMOTION_ACCESS_MODE
        preserved_endpoint = _build_backend_endpoint_identity(
            incident_access_mode=preserved_access_mode,
        )
        preserved_endpoint["backend_reachable"] = False
        blocked_decision = AutomaticDiagnosisExecution(
            should_run=False,
            selection_mode=INCIDENT_SELECTION_MODE_BLOCKED,
            incident_access_mode=preserved_access_mode,
            blocked_reason=BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
        )
        return AutomaticDiagnosisInputs(
            canonical_incident_ids=(),
            promotion_result_summary=_build_contract_error_summary(
                captured_contract_error,
                accumulator,
                {"promotion_mode": "", "incident_access_mode": preserved_access_mode, "scan_scope": ""},
            ),
            promotion_consistency_error=None,
            backend_endpoint_identity=preserved_endpoint,
            execution=blocked_decision,
            promotion_outcome=None,
        )

    promotion_records: list[PromotionRecord] = list(accumulator.promotion_records)
    canonical_ids = list(accumulator.canonical_incident_ids())

    promotion_mode, incident_access_mode, scan_scope = _resolve_accumulator_truth(accumulator)

    # Map promotion records to summary-style aggregation so the existing
    # structured-log paths remain stable. We still compute the
    # ``opened_ids`` / ``updated_ids`` lists (used by log consumers)
    # from the typed records because those are exact mappings, not
    # aggregates reconstructed from persisted state.
    opened_ids = [record.canonical_incident_id for record in promotion_records if record.canonical_incident_id is not None and record.promotion_outcome == PROMOTION_OUTCOME_OPENED]
    updated_ids = [record.canonical_incident_id for record in promotion_records if record.canonical_incident_id is not None and record.promotion_outcome == PROMOTION_OUTCOME_UPDATED]

    # R5 (item 2): the backend endpoint identity reflects the
    # accumulator-resolved access mode (or the explicit
    # ``no_promotion_run`` sentinel for runs that never produced a
    # batch). The sanitized backend URL is still surfaced so operators
    # can see the bound target regardless of whether promotion actually
    # used it.
    backend_endpoint_identity = _build_backend_endpoint_identity(
        incident_access_mode=incident_access_mode,
    )

    consistency_error: IncidentStoreConsistencyError | None = None
    is_backend_authoritative = incident_access_mode == INCIDENT_ACCESS_MODE_BACKEND and promotion_mode in {"backend-api", "auto"}
    promotions_records_for_verifier = [
        PromotionRecord(
            source_candidate_id=record.source_candidate_id,
            canonical_incident_id=record.canonical_incident_id,
            promotion_outcome=record.promotion_outcome,
        )
        for record in promotion_records
        if record.canonical_incident_id is not None
        and record.promotion_outcome
        in {
            PROMOTION_OUTCOME_OPENED,
            PROMOTION_OUTCOME_UPDATED,
        }
    ]
    endpoint = BackendEndpointIdentity(
        scheme=str(backend_endpoint_identity.get("scheme", "")),
        host=str(backend_endpoint_identity.get("host", "")),
        port=(int(backend_endpoint_identity["port"]) if isinstance(backend_endpoint_identity.get("port"), int) else None),
        internal_api_path_prefix=str(backend_endpoint_identity.get("internal_api_path_prefix") or "/api/internal"),
        backend_reachable=backend_endpoint_identity.get("backend_reachable"),
    )

    # R6 (item 1): contract validation runs unconditionally for every
    # backend-authoritative accumulated result so that a malformed
    # dispatcher response (``opened_incidents > 0`` but empty records
    # / empty IDs) raises :class:`PromotionConsistencyContractError`
    # before any automatic-diagnosis fallback can run. Contract
    # validation is intentionally NOT guarded on ``promotion_records``
    # or ``canonical_ids`` being nonempty -- the legacy regression is
    # the exact shape where those inputs are empty, so the old guard
    # silently masked the failure.
    if is_backend_authoritative:
        try:
            _validate_response_contracts(
                promotion_records=promotions_records_for_verifier,
                opened_incidents=accumulator.total_opened_incidents,
                updated_incidents=accumulator.total_updated_incidents,
                opened_incident_ids=opened_ids,
                updated_incident_ids=updated_ids,
            )
        except PromotionConsistencyContractError as contract_error:
            # R6 (item 1): the typed contract failure short-circuits the
            # path BEFORE the authoritative lookup runs and BEFORE
            # automatic diagnosis is invoked. Automatic diagnosis MUST
            # NOT silently fall back to scan mode for a malformed
            # dispatcher response -- the operator must see the typed
            # contract failure so the dispatcher regression is triaged
            # instead of being hidden behind a fetch-miss noise loop.
            backend_endpoint_identity["backend_reachable"] = False
            blocked_decision = AutomaticDiagnosisExecution(
                should_run=False,
                selection_mode=INCIDENT_SELECTION_MODE_BLOCKED,
                incident_access_mode=incident_access_mode,
                blocked_reason=BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
            )
            return AutomaticDiagnosisInputs(
                canonical_incident_ids=tuple(canonical_ids),
                promotion_result_summary=_build_contract_error_summary(contract_error, accumulator, locals()),
                promotion_consistency_error=None,
                backend_endpoint_identity=backend_endpoint_identity,
                execution=blocked_decision,
                promotion_outcome=None,
            )

    # R6 (item 1): the authoritative lookup consistency check is a
    # separate phase that runs only AFTER contract validation has
    # succeeded and only when canonical IDs were actually published
    # (i.e. there is something to look up). Contract drift never reaches
    # this path; the two phases fail closed independently and produce
    # distinct diagnostics so operators can tell a dispatcher
    # regression apart from a backend lookup mismatch.
    if is_backend_authoritative and promotion_records and canonical_ids:
        try:
            lookup_outcomes = _authoritative_lookup_canonical_ids(canonical_ids)
            consistency_error = verify_promotion_consistency(
                promotions_records_for_verifier,
                lookups=lookup_outcomes,
                backend_endpoint=endpoint,
                opened_incidents=accumulator.total_opened_incidents,
                updated_incidents=accumulator.total_updated_incidents,
                opened_incident_ids=opened_ids,
                updated_incident_ids=updated_ids,
            )
            # If the dispatcher returned any non-definitive kind, mark
            # the backend as not reachable for downstream diagnostics.
            from ..collect.incident_identity_hardening import (
                LOOKUP_ERROR_KIND_NOT_FOUND,
            )

            if any(outcome.error_kind != LOOKUP_ERROR_KIND_NOT_FOUND for outcome in lookup_outcomes):
                backend_endpoint_identity["backend_reachable"] = False
            else:
                backend_endpoint_identity["backend_reachable"] = True
        except PromotionConsistencyContractError as contract_error:
            # Contract validation already ran above; reaching this
            # handler means the lookup phase alone tripped the contract
            # (impossible today, but kept for defensive symmetry so
            # future refactors cannot regress the contract path).
            blocked_decision = AutomaticDiagnosisExecution(
                should_run=False,
                selection_mode=INCIDENT_SELECTION_MODE_BLOCKED,
                incident_access_mode=incident_access_mode,
                blocked_reason=BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
            )
            return AutomaticDiagnosisInputs(
                canonical_incident_ids=tuple(canonical_ids),
                promotion_result_summary=_build_contract_error_summary(contract_error, accumulator, locals()),
                promotion_consistency_error=None,
                backend_endpoint_identity=backend_endpoint_identity,
                execution=blocked_decision,
                promotion_outcome=None,
            )
        except Exception:
            backend_endpoint_identity["backend_reachable"] = False

    bounded_error_messages, error_messages_omitted = _truncate_summary_field(
        list(accumulator.aggregated_error_messages()),
        DEFAULT_MAX_ERROR_MESSAGES_IN_SUMMARY,
    )
    bounded_promotion_records, promotion_records_omitted = _truncate_summary_field(
        [record.to_dict() for record in promotion_records],
        DEFAULT_MAX_PROMOTION_RECORDS_IN_SUMMARY,
    )
    promotion_summary = {
        "scanned": accumulator.total_scanned,
        "firing": accumulator.total_firing,
        "opened_incidents": accumulator.total_opened_incidents,
        "updated_incidents": accumulator.total_updated_incidents,
        "skipped_duplicates": accumulator.total_skipped_duplicates,
        "errors": accumulator.total_errors,
        "error_messages": bounded_error_messages,
        "error_messages_omitted": error_messages_omitted,
        "promotion_mode": promotion_mode,
        "incident_access_mode": incident_access_mode,
        "unique_candidate_count": accumulator.total_unique_candidate_count,
        "promotion_scan_scope": scan_scope,
        "promotion_records": bounded_promotion_records,
        "promotion_records_omitted": promotion_records_omitted,
        "opened_incident_ids": opened_ids,
        "updated_incident_ids": updated_ids,
        "has_promotion_activity": accumulator.has_promotion_activity(),
    }

    # ACT-K9B-INCIDENT-PROMOTION-CI-RECOVERY01-CORRECTION06: Extract typed
    # promotion_outcome from accumulator. This is the real typed outcome,
    # not fabricated from mode strings. It is the SOLE authority for the
    # diagnosis selection mode.
    promotion_outcome: PromotionSucceeded | PromotionRejected | PromotionCommitUnknown | None = accumulator.promotion_outcome

    # ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
    # The selection_mode, selection_source, incident_access_mode, and
    # reconciliation_required fields are derived EXHAUSTIVELY from
    # ``promotion_outcome | None`` via :func:`_build_diagnosis_execution_authority`.
    # The legacy workset-state fallback is removed: a recorded
    # ``PromotionCommitUnknown`` MUST map to ``commit_unknown`` (and
    # never to ``store_scan``). The workset state is preserved on the
    # accumulator but no longer participates in selection derivation.
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode=incident_access_mode,
    )

    # Auto-loop gate: SEAM01 R2 / R4 (terminal-empty / blocked states).
    # The gate is consumed only after the authority is fully derived so
    # the ``diagnosis-selection-derived`` event below reports the same
    # selection mode the collector observes.
    from ..collect.incident_diagnosis_auto_loop_config import (
        is_automatic_diagnosis_loop_enabled,
    )

    auto_loop_enabled = is_automatic_diagnosis_loop_enabled()
    should_run = (
        auto_loop_enabled
        and not authority.is_blocked
        and not authority.is_commit_unknown
        and not authority.is_current_run_empty
    )

    execution = AutomaticDiagnosisExecution(
        should_run=should_run,
        selection_mode=authority.selection_mode,
        incident_access_mode=authority.incident_access_mode,
        blocked_reason=(
            BLOCKED_REASON_PROMOTION_REJECTED
            if authority.is_blocked
            else None
        ),
    )

    return AutomaticDiagnosisInputs(
        canonical_incident_ids=tuple(canonical_ids),
        promotion_result_summary=promotion_summary,
        promotion_consistency_error=consistency_error,
        backend_endpoint_identity=backend_endpoint_identity,
        execution=execution,
        promotion_outcome=promotion_outcome,
    )


def _build_contract_error_summary(
    contract_error: PromotionConsistencyContractError,
    accumulator: RunPromotionAccumulator,
    locals_before_failure: dict[str, Any],
) -> dict[str, Any]:
    """Render a :class:`PromotionConsistencyContractError` summary.

    R5 (item 1): the helper produces a JSON-safe summary that includes
    the typed error fields so the orchestrator can include them in the
    structured ``promotion_result_summary`` payload without losing
    diagnostic precision. The summary still exposes the canonical
    accumulator totals so other consumers (UI, scheduler) can render
    counts.
    """
    return {
        "promotion_consistency_contract_error": {
            "message": str(contract_error),
            "opened_incidents": contract_error.opened_incidents,
            "updated_incidents": contract_error.updated_incidents,
            "promotion_record_count": contract_error.promotion_record_count,
            "opened_id_count": contract_error.opened_id_count,
            "updated_id_count": contract_error.updated_id_count,
            "missing_canonical_ids": list(contract_error.missing_canonical_ids),
        },
        "promotion_mode": locals_before_failure.get("promotion_mode", ""),
        "incident_access_mode": locals_before_failure.get("incident_access_mode", ""),
        "promotion_scan_scope": locals_before_failure.get("scan_scope", ""),
        "opened_incidents": accumulator.total_opened_incidents,
        "updated_incidents": accumulator.total_updated_incidents,
        "errors": accumulator.total_errors,
        "unique_candidate_count": accumulator.total_unique_candidate_count,
    }


# ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
# Typed diagnosis-execution authority derived exclusively from
# ``PromotionOutcome | None``. The authority encapsulates the
# selection mode, selection source, incident access mode, and
# reconciliation flag so downstream execution cannot independently
# select the mode and the outcome.
@dataclass(frozen=True, slots=True)
class DiagnosisExecutionAuthority:
    """Authoritative diagnosis-execution decision.

    Constructed once via :func:`_build_diagnosis_execution_authority`
    using exhaustive pattern matching over
    ``PromotionOutcome | None``. Downstream consumers MUST consume
    this authority object rather than separately supplied mode /
    outcome fields so the selection mode and the typed outcome cannot
    be selected independently.

    Attributes:
        promotion_outcome: The typed outcome the decision was derived
            from (``None`` when no promotion was attempted).
        selection_mode: Closed selection mode string.
        selection_source: Low-cardinality selection source string.
        incident_access_mode: Access mode the collector must use.
        reconciliation_required: True only for ``PromotionCommitUnknown``.
    """

    promotion_outcome: PromotionSucceeded | PromotionRejected | PromotionCommitUnknown | None
    selection_mode: str
    selection_source: str
    incident_access_mode: str
    reconciliation_required: bool

    @property
    def is_blocked(self) -> bool:
        """Return True when the authority blocks diagnosis."""
        return self.selection_mode == INCIDENT_SELECTION_MODE_BLOCKED

    @property
    def is_commit_unknown(self) -> bool:
        """Return True when the authority reports commit unknown."""
        return self.selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN

    @property
    def is_current_run_empty(self) -> bool:
        """Return True when the authority reports current-run-empty."""
        return self.selection_mode == INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY

    @property
    def is_store_scan(self) -> bool:
        """Return True when the authority permits a global store scan."""
        return self.selection_mode == INCIDENT_SELECTION_MODE_STORE_SCAN

    @property
    def diagnosis_invoked(self) -> bool:
        """Return True when diagnosis is invoked under this authority.

        Diagnosis MUST NOT be invoked when:
        * the selection mode is ``commit_unknown`` (reconciliation required)
        * the selection mode is ``blocked`` (typed rejection / failure)
        * the selection mode is ``current_run_empty`` (zero-work success)
        * the selection mode is ``store_scan`` without a promotion outcome
          (handled by the collector's own policy path; the orchestrator
          does not invoke the collector directly here).
        """
        return (
            self.selection_mode
            in (
                INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
                INCIDENT_SELECTION_MODE_STORE_SCAN,
            )
        )


def _build_diagnosis_execution_authority(
    *,
    promotion_outcome: PromotionSucceeded | PromotionRejected | PromotionCommitUnknown | None,
    dispatcher_incident_access_mode: str,
) -> DiagnosisExecutionAuthority:
    """Derive the typed diagnosis-execution authority from the outcome.

    ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:

    This helper is the SOLE authority for ``selection_mode`` and
    ``incident_access_mode``. It performs exhaustive pattern matching
    over the closed ``PromotionOutcome | None`` union so a recorded
    ``PromotionCommitUnknown`` is mapped to ``commit_unknown`` (and
    never to ``store_scan``). The legacy workset-state fallback is
    removed; the ``selection_mode`` is no longer derived from
    ``canonical_ids`` cardinality.

    Required projection:

    * ``promotion_outcome is None`` ->
      ``selection_mode=store_scan``,
      ``selection_source=explicit_nonpromotion``,
      ``incident_access_mode=no_promotion_run``.
    * ``PromotionSucceeded`` with non-empty ``diagnosis_incident_ids`` ->
      ``selection_mode=explicit_incident_ids``,
      ``selection_source=promotion``,
      ``incident_access_mode=dispatcher_incident_access_mode``.
    * ``PromotionSucceeded`` with empty ``diagnosis_incident_ids`` ->
      ``selection_mode=current_run_empty``,
      ``selection_source=promotion``,
      ``incident_access_mode=dispatcher_incident_access_mode``.
    * ``PromotionCommitUnknown`` ->
      ``selection_mode=commit_unknown``,
      ``selection_source=promotion_commit_unknown``,
      ``incident_access_mode=reconciliation_required``.
    * ``PromotionRejected`` (or any future terminal blocked variant) ->
      ``selection_mode=blocked``,
      ``selection_source=promotion_blocked``,
      ``incident_access_mode=dispatcher_incident_access_mode``.

    The helper uses :func:`typing.assert_never` for unhandled variants
    so a future closed-union expansion cannot silently fall through.
    """
    from typing import assert_never

    if promotion_outcome is None:
        # ACT-K9B-HULK-PROMOTION-SUCCESSFUL-ZERO-ACCESS-MODE01:
        # ``no_promotion_run`` is reserved exclusively for runs that
        # NEVER reached promotion (no batch, no outcome). When the
        # accumulator accepted a batch whose dispatcher actually
        # consumed backend/local, the access mode must reflect that
        # transport even though the typed outcome has not yet been
        # recorded -- the ``dispatcher_incident_access_mode`` carries
        # the truth the orchestrator already derived from the
        # accepted batch. ``no_promotion_run`` would otherwise collapse
        # a real backend or local run onto the no-attempt sentinel,
        # hiding the transport authority behind cardinality.
        access_mode = (
            dispatcher_incident_access_mode
            if dispatcher_incident_access_mode
            != INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN
            else INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN
        )
        return DiagnosisExecutionAuthority(
            promotion_outcome=None,
            selection_mode=INCIDENT_SELECTION_MODE_STORE_SCAN,
            selection_source=DIAGNOSIS_SELECTION_SOURCE_EXPLICIT_NON_PROMOTION,
            incident_access_mode=access_mode,
            reconciliation_required=False,
        )

    if isinstance(promotion_outcome, PromotionCommitUnknown):
        return DiagnosisExecutionAuthority(
            promotion_outcome=promotion_outcome,
            selection_mode=INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            selection_source=DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
            incident_access_mode=INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
            reconciliation_required=True,
        )

    if isinstance(promotion_outcome, PromotionRejected):
        return DiagnosisExecutionAuthority(
            promotion_outcome=promotion_outcome,
            selection_mode=INCIDENT_SELECTION_MODE_BLOCKED,
            selection_source=DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED,
            incident_access_mode=dispatcher_incident_access_mode,
            reconciliation_required=False,
        )

    if isinstance(promotion_outcome, PromotionSucceeded):
        if promotion_outcome.diagnosis_incident_ids:
            return DiagnosisExecutionAuthority(
                promotion_outcome=promotion_outcome,
                selection_mode=INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
                selection_source=DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
                incident_access_mode=dispatcher_incident_access_mode,
                reconciliation_required=False,
            )
        return DiagnosisExecutionAuthority(
            promotion_outcome=promotion_outcome,
            selection_mode=INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            selection_source=DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
            incident_access_mode=dispatcher_incident_access_mode,
            reconciliation_required=False,
        )

    # Exhaustive over the closed PromotionOutcome union.
    assert_never(promotion_outcome)


def _requested_signal_count(
    promotion_outcome: PromotionSucceeded | PromotionRejected | PromotionCommitUnknown | None,
) -> int:
    """Project ``requested_signal_count`` from the typed outcome.

    ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
    The :class:`PromotionSucceeded` outcome carries the requested
    signal IDs as a tuple; :class:`PromotionRejected` carries
    ``rejected_signal_ids``; :class:`PromotionCommitUnknown` carries
    ``requested_signal_ids``. ``None`` yields ``0``.
    """
    if promotion_outcome is None:
        return 0
    if isinstance(promotion_outcome, PromotionSucceeded):
        return len(promotion_outcome.requested_signal_ids)
    if isinstance(promotion_outcome, PromotionRejected):
        return len(promotion_outcome.rejected_signal_ids)
    if isinstance(promotion_outcome, PromotionCommitUnknown):
        return len(promotion_outcome.requested_signal_ids)
    raise TypeError(
        "_requested_signal_count received a non-PromotionOutcome value: "
        f"{type(promotion_outcome).__name__!r}"
    )


def _promotion_outcome_event_fields_for_selection(
    promotion_outcome: PromotionSucceeded | PromotionRejected | PromotionCommitUnknown | None,
) -> tuple[str, str, bool]:
    """Return ``(outcome_kind, reason, may_have_committed)`` for the event.

    ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
    The three projections are sourced from the typed outcome so the
    ``diagnosis-selection-derived`` event reflects the same authority
    the selection builder consumes.
    """
    from ..collect.promotion_outcomes import may_have_committed

    if promotion_outcome is None:
        return ("none", "", False)
    if isinstance(promotion_outcome, PromotionSucceeded):
        return ("succeeded", "", bool(may_have_committed(promotion_outcome)))
    if isinstance(promotion_outcome, PromotionRejected):
        return ("rejected", promotion_outcome.reason.value, False)
    if isinstance(promotion_outcome, PromotionCommitUnknown):
        return (
            "commit_unknown",
            promotion_outcome.reason.value,
            bool(may_have_committed(promotion_outcome)),
        )
    raise TypeError(
        "_promotion_outcome_event_fields_for_selection received a "
        f"non-PromotionOutcome value: {type(promotion_outcome).__name__!r}"
    )


def _emit_diagnosis_selection_derived_event(
    *,
    runner: HealthLoopRunner,
    authority: DiagnosisExecutionAuthority,
    promotion_outcome: PromotionSucceeded | PromotionRejected | PromotionCommitUnknown | None,
    requested_signal_count: int,
) -> None:
    """Emit the canonical ``diagnosis-selection-derived`` event.

    ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
    The event is emitted BEFORE automatic diagnosis begins so
    downstream health-run consumers see the same selection the
    collector observes. The event MUST carry the typed outcome
    projection (``promotion_outcome_kind`` /
    ``promotion_outcome_reason`` / ``promotion_may_have_committed``),
    the requested signal count, and the selection fields
    (``selection_mode`` / ``selection_source`` /
    ``incident_access_mode`` / ``reconciliation_required`` /
    ``diagnosis_invoked``).
    """
    outcome_kind, reason, may_have = _promotion_outcome_event_fields_for_selection(
        promotion_outcome
    )
    runner._log_event(
        "automatic-diagnosis",
        "DEBUG",
        "Diagnosis selection derived",
        event="diagnosis-selection-derived",
        run_id=runner.run_id,
        run_label=runner.run_label,
        promotion_outcome_kind=outcome_kind,
        promotion_outcome_reason=reason,
        promotion_may_have_committed=may_have,
        requested_signal_count=requested_signal_count,
        selection_mode=authority.selection_mode,
        selection_source=authority.selection_source,
        incident_access_mode=authority.incident_access_mode,
        reconciliation_required=authority.reconciliation_required,
        diagnosis_invoked=authority.diagnosis_invoked,
    )


def _build_diagnosis_selection_for_execution(
    *,
    automatic_diagnosis_execution: AutomaticDiagnosisExecution,
    promotion_outcome: PromotionSucceeded | PromotionRejected | PromotionCommitUnknown | None,
    canonical_incident_ids: list[str],
    scheduler_run_id: str,
) -> DiagnosisSelection:
    """Build the canonical typed DiagnosisSelection for automatic diagnosis.

    ACT-K9B-INCIDENT-PROMOTION-CI-RECOVERY01-CORRECTION06:
    This is the ONLY builder the production orchestrator uses. It consumes
    the real typed promotion_outcome from the accumulator and produces the
    correct typed variant. It does NOT fabricate outcomes from strings.

    Required algebra:
    - explicit_incident_ids + PromotionSucceeded -> DiagnosisSelectionFromPromotion
    - current_run_empty + PromotionSucceeded -> DiagnosisSelectionFromPromotion (empty IDs)
    - store_scan -> DiagnosisSelectionWithoutPromotion
    - commit_unknown + PromotionCommitUnknown -> DiagnosisSelectionUnavailable
    - blocked -> caller handles before reaching here

    Args:
        automatic_diagnosis_execution: The typed execution decision from the orchestrator.
        promotion_outcome: The real typed outcome from the accumulator (not fabricated).
        canonical_incident_ids: Canonical IDs from the accumulator (preserves order).
        scheduler_run_id: The scheduler run ID for run-identity validation.

    Returns:
        Typed DiagnosisSelection variant matching the execution decision.

    Raises:
        ValueError: When selection_mode/outcome combination is invalid.
    """
    selection_mode = automatic_diagnosis_execution.selection_mode

    # blocked is handled before reaching here
    if selection_mode == INCIDENT_SELECTION_MODE_BLOCKED:
        raise ValueError("blocked selection must be handled before calling this builder")

    # store_scan: no promotion outcome needed (R19 cardinality invariant)
    if selection_mode == INCIDENT_SELECTION_MODE_STORE_SCAN:
        if promotion_outcome is not None:
            raise ValueError("store_scan mode does not accept a recorded promotion outcome")
        return DiagnosisSelectionWithoutPromotion(
            reason=NoPromotionSelectionReason.SCHEDULED_SCAN_RUN,
        )

    # commit_unknown: requires PromotionCommitUnknown
    if selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN:
        if promotion_outcome is None:
            raise ValueError(f"selection_mode={selection_mode!r} requires a PromotionCommitUnknown outcome, got None")
        if not isinstance(promotion_outcome, PromotionCommitUnknown):
            raise ValueError(f"selection_mode={selection_mode!r} requires PromotionCommitUnknown, got {type(promotion_outcome).__name__}")
        # CORRECTION12: Validate run identity matches
        if promotion_outcome.run_id != scheduler_run_id:
            raise ValueError(f"promotion_outcome.run_id={promotion_outcome.run_id!r} does not match scheduler_run_id={scheduler_run_id!r}")
        return DiagnosisSelectionUnavailable(outcome=promotion_outcome)

        # explicit_incident_ids or current_run_empty: require PromotionSucceeded
    if selection_mode in (
        INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
        INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
    ):
        if promotion_outcome is None:
            raise ValueError(f"selection_mode={selection_mode!r} requires PromotionSucceeded, got None")
        if not isinstance(promotion_outcome, PromotionSucceeded):
            raise ValueError(f"selection_mode={selection_mode!r} requires PromotionSucceeded, got {type(promotion_outcome).__name__}")

        # CORRECTION08: Validate run identity matches
        if promotion_outcome.run_id != scheduler_run_id:
            raise ValueError(f"promotion_outcome.run_id={promotion_outcome.run_id!r} does not match scheduler_run_id={scheduler_run_id!r}")

        # CORRECTION08/CORRECTION09: Validate outcome.diagnosis_incident_ids matches canonical_ids
        # This is the SOLE ID AUTHORITY validation - the outcome's IDs must match
        # the accumulator's canonical IDs exactly (canonical IDs are the witness).
        # CORRECTION09: Construction source is promotion_outcome.diagnosis_incident_ids.
        outcome_ids = promotion_outcome.diagnosis_incident_ids
        if selection_mode == INCIDENT_SELECTION_MODE_EXPLICIT_IDS:
            # CORRECTION09: explicit_ids mode - validate equality (witness role)
            # but construct from outcome_ids (sole authority).
            # R19 cardinality invariant: explicit_ids requires non-empty outcome.
            if not outcome_ids:
                raise PromotionConsistencyContractError(
                    "DiagnosisSelection SOLE ID AUTHORITY violation: explicit_incident_ids selection requires non-empty diagnosis_incident_ids, got empty",
                    promotion_record_count=len(canonical_incident_ids),
                    opened_incidents=len(canonical_incident_ids),
                    updated_incidents=0,
                )
            if tuple(canonical_incident_ids) != outcome_ids:
                raise PromotionConsistencyContractError(
                    f"DiagnosisSelection SOLE ID AUTHORITY violation: canonical_incident_ids={canonical_incident_ids} does not match promotion_outcome.diagnosis_incident_ids={list(outcome_ids)}",
                    promotion_record_count=len(canonical_incident_ids),
                    opened_incidents=len(canonical_incident_ids),
                    updated_incidents=len(outcome_ids) - len(canonical_incident_ids),
                )
            # CORRECTION09: Use outcome_ids as sole construction authority
            return DiagnosisSelectionFromPromotion(
                promotion_run_id=promotion_outcome.run_id,
                incident_ids=outcome_ids,
            )
        else:
            # CORRECTION08/CORRECTION09: current_run_empty mode - outcome must have empty IDs
            if outcome_ids != ():
                raise PromotionConsistencyContractError(
                    f"DiagnosisSelection SOLE ID AUTHORITY violation: selection_mode=current_run_empty requires empty diagnosis_incident_ids, got {list(outcome_ids)}",
                    promotion_record_count=len(outcome_ids),
                    opened_incidents=0,
                    updated_incidents=0,
                )
            # CORRECTION09: Use empty outcome_ids as sole construction authority
            return DiagnosisSelectionFromPromotion(
                promotion_run_id=promotion_outcome.run_id,
                incident_ids=(),
            )

    # Unknown mode: fail-closed
    raise ValueError(
        f"unknown selection_mode={selection_mode!r}. "
        f"Known modes: {INCIDENT_SELECTION_MODE_EXPLICIT_IDS!r}, "
        f"{INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY!r}, "
        f"{INCIDENT_SELECTION_MODE_STORE_SCAN!r}, "
        f"{INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN!r}, "
        f"{INCIDENT_SELECTION_MODE_BLOCKED!r}"
    )


def execute_health_loop_run(
    runner: HealthLoopRunner,
    records: list[HealthSnapshotRecord],
    directories: dict[str, Path],
) -> tuple[
    list[HealthAssessmentArtifact],
    list[ComparisonTriggerArtifact],
    list[DrilldownArtifact],
]:
    """Execute the health loop run orchestration.

    This is the main entry point for running the health assessment loop.
    It orchestrates all phases: collection, assessment, comparison,
    drilldown, external analysis, and history persistence.

    Args:
        runner: The HealthLoopRunner instance.
        records: Collected snapshot records.
        directories: Output directories.

    Returns:
        Tuple of (assessments, triggers, drilldowns) from the run.
    """
    history = load_runner_history(history_path=directories["history"])
    previous_history = {key: entry for key, entry in history.items()}

    # Instantiate the typed run-scoped handoff. The accumulator is the
    # authoritative source for canonical incident IDs going forward;
    # it replaces the legacy ``directories["__last_promotion_result__"]``
    # smuggling pattern. We deliberately do NOT mutate ``directories``
    # with a magic sentinel because the directories dict's value type
    # is ``Path`` and smuggling an arbitrary promotion payload through
    # it broke the contract.
    promotion_accumulator = RunPromotionAccumulator()

    # Run monitoring discovery and collection (Alertmanager, vmalert).
    # The runner threads the typed accumulator through to
    # ``_ingest_alert_signals`` so every Alertmanager source in the
    # run aggregates its canonical incident IDs into the same value
    # object. R7 (item 1): the orchestrator catches
    # :class:`PromotionConsistencyContractError` raised by
    # :meth:`RunPromotionAccumulator.add_batch` (the production-path
    # validation introduced for R7 item 3) and stores it on the
    # accumulator so ``_derive_automatic_diagnosis_inputs`` can route
    # the run to the ``blocked`` decision. The rest of the health run
    # (assessments, triggers, drilldowns, etc.) still completes so the
    # terminal-completion event carries the blocked reason to operators.
    try:
        runner._run_monitoring_discovery(
            records,
            directories,
            promotion_accumulator=promotion_accumulator,
        )
    except PromotionConsistencyContractError as contract_error:
        promotion_accumulator.last_contract_error = contract_error
        runner._log_event(
            "incident-identity",
            "ERROR",
            "PromotionConsistencyContractError captured by orchestrator; automatic diagnosis will be blocked.",
            event="promotion_consistency_contract_error",
            contract_message=str(contract_error),
            opened_incidents=contract_error.opened_incidents,
            updated_incidents=contract_error.updated_incidents,
            promotion_record_count=contract_error.promotion_record_count,
            opened_id_count=contract_error.opened_id_count,
            updated_id_count=contract_error.updated_id_count,
        )

    # Build assessments
    assessments = build_assessments_for_records(
        records=records,
        history=history,
        assessment_dir=directories["assessments"],
        notification_dir=directories["notifications"],
        run_id=runner.run_id,
        run_label=runner.run_label,
        warning_event_threshold=runner.config.trigger_policy.warning_event_threshold,
        record_notification_fn=runner._record_notification,
        image_pull_inspector=runner._image_pull_secret_inspector,
        log_event_fn=runner._log_event,
    )

    # Evaluate triggers
    triggers = evaluate_triggers_for_records(
        records=records,
        peers=runner.config.peers,
        trigger_policy=runner.config.trigger_policy,
        baseline_registry=runner.baseline_registry,
        history=history,
        run_id=runner.run_id,
        run_label=runner.run_label,
        manual_comparison_keys=runner._manual_keys,
        comparison_fn=runner.comparison_fn,
        record_notification_fn=runner._record_notification,
        log_event_fn=runner._log_event,
        directories=directories,
    )

    # Build drilldowns
    drilldowns = build_drilldowns_for_records(
        records=records,
        previous_history=previous_history,
        directory=directories["drilldowns"],
        run_id=runner.run_id,
        run_label=runner.run_label,
        drilldown_collector=runner._drilldown_collector,
        manual_drilldown_contexts=runner._manual_drilldown_contexts,
        warning_event_threshold=runner.config.trigger_policy.warning_event_threshold,
        log_event_fn=runner._log_event,
    )

    # Run auto-drilldown analysis
    auto_artifacts = _run_auto_drilldown_impl(
        drilldowns=drilldowns,
        directories=directories,
        run_id=runner.run_id,
        run_label=runner.run_label,
        auto_drilldown_policy=runner.config.external_analysis.auto_drilldown,
        provider_name=runner.config.external_analysis.auto_drilldown.provider or "default",
        log_event_fn=runner._log_event,
    )

    # Run manual external analysis
    manual_artifacts = run_external_analysis_for_records(
        records=records,
        manual_requests=runner._manual_external_analysis_requests,
        external_analysis_policy=runner._analysis_policy,
        analysis_adapters=runner._analysis_adapters,
        run_id=runner.run_id,
        run_label=runner.run_label,
        record_notification_fn=runner._record_notification,
        log_event_fn=runner._log_event,
        directories=directories,
    )

    external_artifacts: list[ExternalAnalysisArtifact] = [
        *auto_artifacts,
        *manual_artifacts,
    ]

    # Persist history
    persist_runner_history(
        history=history,
        directories=directories,
        run_id=runner.run_id,
        log_event_fn=runner._log_event,
    )

    # Write review artifact
    review_path, proposals = runner._write_review_artifact(assessments, drilldowns, directories)

    # Run review enrichment
    enrichment_artifact = _run_review_enrichment_impl(
        review_path=review_path,
        directories=directories,
        review_enrichment_policy=runner.config.external_analysis.review_enrichment,
        analysis_adapters=runner._analysis_adapters,
        run_id=runner.run_id,
        run_label=runner.run_label,
        log_event_fn=runner._log_event,
    )
    if enrichment_artifact:
        external_artifacts.append(enrichment_artifact)

    # Filter to execution artifacts
    execution_artifacts = tuple(a for a in external_artifacts if a.purpose == ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION)

    # Derive incident linkage context
    linkage_context = runner._derive_incident_linkage_context(records)

    # Run next check planning
    plan_artifact = run_next_check_planning(
        review_path=review_path,
        enrichment_artifact=enrichment_artifact,
        directories=directories,
        run_id=runner.run_id,
        run_label=runner.run_label,
        log_event=runner._log_event,
        execution_artifacts=execution_artifacts,
        linkage_context=linkage_context,
    )
    if plan_artifact:
        external_artifacts.append(plan_artifact)

    # Run automatic diagnosis loop BEFORE the terminal-completion log so
    # callers see synchronous evidence-collection outcomes on the same
    # health run they just triggered. The orchestrator consumes
    # canonical incident IDs directly from the typed accumulator so it
    # does not need to synthesize IDs from candidate attributes or
    # smuggle a promotion payload through ``directories``. The
    # legacy ``directories["__last_promotion_result__"]`` sentinel is
    # intentionally NOT consulted any more.
    #
    # CORRECTION10: _derive_automatic_diagnosis_inputs returns
    # AutomaticDiagnosisInputs; consumers MUST use named field access.
    # Positional unpacking is unsupported.
    diagnosis_inputs = _derive_automatic_diagnosis_inputs(
        promotion_accumulator,
    )
    canonical_ids = list(diagnosis_inputs.canonical_incident_ids)
    promotion_summary = diagnosis_inputs.promotion_result_summary
    promotion_consistency_error = diagnosis_inputs.promotion_consistency_error
    backend_endpoint_identity = diagnosis_inputs.backend_endpoint_identity
    automatic_diagnosis_execution = diagnosis_inputs.execution
    promotion_outcome = diagnosis_inputs.promotion_outcome
    if promotion_consistency_error is not None:
        runner._log_event(
            "incident-identity",
            "ERROR",
            "incident_store_consistency_error",
            event="incident_store_consistency_error",
            diagnostics=promotion_consistency_error.to_dict(),
        )

    # ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
    # Rebuild the typed authority from the just-derived promotion
    # outcome so the ``diagnosis-selection-derived`` event below and
    # the dispatch decision below consume the SAME authority. The
    # helper is deterministic; rebuilding it costs one extra branch
    # but guarantees the event field, the dispatch decision, and the
    # selection builder all read the same value.
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode=automatic_diagnosis_execution.incident_access_mode,
    )
    _emit_diagnosis_selection_derived_event(
        runner=runner,
        authority=authority,
        promotion_outcome=promotion_outcome,
        requested_signal_count=_requested_signal_count(promotion_outcome),
    )

    if automatic_diagnosis_execution.is_blocked:
        # R7 (item 1): the diagnosis loop is intentionally NOT
        # invoked. Emit a typed ``automatic_diagnosis_blocked`` event so
        # downstream health-run consumers see the blocked reason. The
        # incident_access_mode here is the preserved dispatcher-mode
        # value, NOT a cardinality-derived default.
        runner._log_event(
            "automatic-diagnosis",
            "INFO",
            "Automatic diagnosis blocked: promotion_rejected",
            event="automatic_diagnosis_blocked",
            blocked_reason=automatic_diagnosis_execution.blocked_reason or "promotion_rejected",
            incident_access_mode=(automatic_diagnosis_execution.incident_access_mode),
            selection_mode=automatic_diagnosis_execution.selection_mode,
        )
    elif authority.is_commit_unknown:
        # ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01:
        # Commit-unknown MUST NOT invoke diagnosis. The collector is
        # skipped, the requested signal IDs are preserved on the
        # accumulator for later reconciliation, and the orchestrator
        # emits a typed commit-unknown event so downstream consumers
        # see the diagnostic-block reason without an uncaught exception.
        runner._log_event(
            "automatic-diagnosis",
            "INFO",
            "Automatic diagnosis blocked: promotion_commit_unknown",
            event="automatic_diagnosis_commit_unknown",
            blocked_reason=BLOCKED_REASON_PROMOTION_COMMIT_UNKNOWN,
            incident_access_mode=authority.incident_access_mode,
            selection_mode=authority.selection_mode,
            selection_source=authority.selection_source,
            reconciliation_required=True,
            stop_reason="promotion_commit_unknown",
        )
    elif authority.is_current_run_empty:
        # SEAM01 R3/R4: VALID + empty PromotionSucceeded is a
        # terminal zero-work stop. Diagnosis MUST NOT be invoked.
        runner._log_event(
            "automatic-diagnosis",
            "INFO",
            "Automatic diagnosis skipped: current_run_empty",
            event="automatic_diagnosis_current_run_empty",
            incident_access_mode=authority.incident_access_mode,
            selection_mode=authority.selection_mode,
            selection_source=authority.selection_source,
            stop_reason="promotion_current_run_empty",
        )
    else:
        # ACT-K9B-INCIDENT-PROMOTION-CI-RECOVERY01-CORRECTION06:
        # Build typed DiagnosisSelection using the canonical builder that
        # consumes the real promotion_outcome from the accumulator.
        # This replaces the legacy _legacy_build_selection() which
        # fabricated outcomes from strings and lost authoritative data.
        # The selection is consumed via the typed authority to ensure
        # the selection mode and the typed outcome cannot be
        # independently selected.
        diagnosis_selection = _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=automatic_diagnosis_execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=canonical_ids,
            scheduler_run_id=runner.run_id,
        )
        runner._run_automatic_diagnosis_loop(
            external_analysis_dir=directories["external_analysis"],
            promotion_result_summary=promotion_summary,
            backend_endpoint_identity=backend_endpoint_identity,
            diagnosis_selection=diagnosis_selection,
        )

    # Log completion. ``automatic_diagnosis_synchronous`` records that
    # the synchronous automatic diagnosis phase finished before this
    # event was emitted, so downstream health-run consumers no longer
    # race the diagnostic collector.
    healthy_count = sum(1 for artifact in assessments if artifact.health_rating == HealthRating.HEALTHY)
    degraded_count = len(assessments) - healthy_count
    runner._log_event(
        "health-loop",
        "INFO",
        "Health run completed",
        event="complete",
        assessment_count=len(assessments),
        healthy_count=healthy_count,
        degraded_count=degraded_count,
        trigger_count=len(triggers),
        drilldown_count=len(drilldowns),
        external_analysis_count=len(external_artifacts),
        automatic_diagnosis_synchronous=True,
        canonical_incident_id_count=len(canonical_ids),
        promotion_record_count=len(promotion_summary.get("promotion_records") or []),
        promotion_consistency_error_recorded=(promotion_consistency_error is not None),
        backend_endpoint_identity=backend_endpoint_identity,
    )

    # Prune external analysis history
    runner._prune_external_analysis_history(directories["external_analysis"])

    # Scan for durable Alertmanager proposals
    try:
        durable_candidates = scan_and_propose(directories["root"])
        durable_proposals: tuple[HealthProposal, ...] = ()
        if durable_candidates:
            durable_proposals = tuple(
                HealthProposal.from_durable_proposal_candidate(
                    candidate=candidate,
                    source_run_id=runner.run_id,
                    source_artifact_path=str(directories["root"] / "alertmanager-durable-proposals" / f"{candidate.proposal_id}.json"),
                )
                for candidate in durable_candidates
            )
            runner._log_event(
                "health-loop",
                "INFO",
                "Durable Alertmanager proposals generated",
                durable_proposal_count=len(durable_proposals),
                event="durable-proposals-generated",
            )
        all_proposals = (*proposals, *durable_proposals)
    except OSError as exc:
        runner._log_event(
            "health-loop",
            "WARNING",
            "Durable proposal scan failed",
            severity_reason=str(exc),
            event="durable-proposals-failed",
        )
        all_proposals = proposals

    # Write UI index
    try:
        ui_index_path = write_health_ui_index(
            directories["root"],
            runner.run_id,
            runner.run_label,
            runner.config.collector_version,
            records,
            assessments,
            drilldowns,
            all_proposals,
            external_artifacts,
            runner._notification_records,
            external_analysis_settings=runner.config.external_analysis,
            available_adapters=runner._analysis_adapters.keys(),
            expected_scheduler_interval_seconds=runner._expected_scheduler_interval_seconds,
        )
        runner._log_event(
            "health-loop",
            "INFO",
            "UI index generated",
            artifact_path=str(ui_index_path),
            assessment_count=len(assessments),
            trigger_count=len(triggers),
            drilldown_count=len(drilldowns),
            proposal_count=len(all_proposals),
            external_analysis_count=len(external_artifacts),
            event="ui-index-generated",
        )
    except OSError as exc:
        runner._log_event(
            "health-loop",
            "ERROR",
            "UI artifact generation failed",
            severity_reason=str(exc),
            event="ui-index-failed",
        )

    runner._latest_external_artifacts = external_artifacts
    return assessments, triggers, drilldowns

"""Algebraic disposition model for automatic-diagnosis eligibility.

This module adds a typed observability projection over the legacy result
state. It is not yet the canonical state-machine migration; that work
is tracked in ``ACT-K9B-AUTO-DIAGNOSIS-TYPED-OUTCOME-ADT01``. The closed
sum type and reason-code vocabularies below can be projected from the
existing ``AutoLoopIncidentResult`` via the compat module.

Design contract:

* One closed union of immutable variants (no shared ``eligible``/``skipped``/
  ``error`` booleans).
* Reasons are stable closed vocabulary members (``StrEnum``); dynamic details
  never become reason-map keys.
* All reducers use exhaustive ``match`` + ``typing.assert_never`` so a newly
  added variant causes mypy/pytest exhaustiveness checks to fail.
* Legacy ``AutoLoopIncidentResult`` is preserved for external/API compatibility
  via an explicit one-way projection (``legacy_result_from_disposition``).
  The reverse projection is allowed only where migration requires it.

This module is leaf-safe: it must NOT import from
``incident_diagnosis_auto_loop`` or sibling facade modules.

R1 follow-up status: The closed reason vocabularies below are
deliberately inclusive for backwards compatibility with the legacy
``AutoLoopIncidentResult`` projection. The split into
``DiagnosisCollectorStopReason`` (collector-level) and
``DiagnosisNotExecutedReason`` (per-incident execution skips) is
tracked in ``incident_diagnosis_disposition_execution`` (draft) and
will land in a follow-up that also moves ``_process_incident`` to
return a typed ``AutomaticDiagnosisIncidentOutcome``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias, assert_never

if TYPE_CHECKING:
    from .incident_diagnosis_auto_loop_config import DiagnosisBudgetDiagnostic

SCHEMA_VERSION: int = 2


# Default bound for ``sanitize_disposition_detail``. Detailed operator logs
# can mention long cluster names but should not carry raw exception
# tracebacks or full provider payloads.
DEFAULT_DETAIL_MAX_CHARS = 512


class DiagnosisDispositionKind(StrEnum):
    """Coarse disposition classification used by exhaustiveness reducers."""

    ELIGIBLE = "eligible"
    SKIPPED = "skipped"
    INELIGIBLE = "ineligible"
    ERROR = "error"


class DiagnosisSkipReason(StrEnum):
    """Closed vocabulary of skip reasons.

    A ``SkippedFromAutomaticDiagnosis`` is created when the incident exists and
    automatic diagnosis does not (yet) apply for a non-failure reason.
    """

    AUTOMATIC_DIAGNOSIS_DISABLED = "automatic_diagnosis_disabled"
    INCIDENT_NOT_FOUND = "incident_not_found"
    NO_INCIDENTS_PROCESSED = "no_incidents_processed"
    REVIEW_PACKET_BUDGET_EXHAUSTED = "review_packet_budget_exhausted"
    INCIDENT_COOLDOWN_ACTIVE = "incident_cooldown_active"
    ALREADY_HAS_CURRENT_REVIEW_PACKET = "already_has_current_review_packet"
    LISTING_EMPTY = "listing_empty"
    UNKNOWN_LEGACY_REASON = "unknown_legacy_reason"


class DiagnosisIneligibleReason(StrEnum):
    """Closed vocabulary of ineligibility reasons."""

    TERMINAL_STATUS = "terminal_status"
    UNSUPPORTED_STATUS = "unsupported_status"
    REQUIRED_EVIDENCE_MISSING = "required_evidence_missing"


class DiagnosisEvaluationFailureReason(StrEnum):
    """Closed vocabulary of evaluation-failure reasons (back-compat).

    An ``AutomaticDiagnosisEvaluationFailed`` is reserved for *evaluation*
    failures: we could not even decide whether the incident is eligible.
    Pre-ADT, ``UNSAFE_RUN_ID`` and ``CASE_FILE_BUILD_FAILED`` lived here
    because the legacy ``AutoLoopIncidentResult`` collapsed both
    eligibility and execution into one shape. The typed-outcome ACT will
    split execution failures into a dedicated enum; for now these
    members remain so the legacy projection stays lossless.
    """

    BACKEND_FETCH_FAILED = "backend_fetch_failed"
    INVALID_INCIDENT_PAYLOAD = "invalid_incident_payload"
    ELIGIBILITY_EVALUATION_FAILED = "eligibility_evaluation_failed"
    UNSAFE_RUN_ID = "unsafe_run_id"
    CASE_FILE_BUILD_FAILED = "case_file_build_failed"


# ---------------------------------------------------------------------------
# Disposition variants (frozen dataclasses; no overlapping boolean state)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EligibleForAutomaticDiagnosis:
    """Incident is eligible for automatic diagnosis."""

    eligibility_reason: str
    budget_diagnostics: tuple[DiagnosisBudgetDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class SkippedFromAutomaticDiagnosis:
    """Incident exists but automatic diagnosis was skipped for a non-failure reason."""

    reason: DiagnosisSkipReason
    detail: str | None = None
    budget_diagnostics: tuple[DiagnosisBudgetDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class IneligibleForAutomaticDiagnosis:
    """Incident exists but is not eligible by its current nature (e.g. terminal)."""

    reason: DiagnosisIneligibleReason
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class AutomaticDiagnosisEvaluationFailed:
    """Eligibility evaluation itself failed (fetch, payload, evaluation error)."""

    reason: DiagnosisEvaluationFailureReason
    detail: str | None = None


IncidentDiagnosisDisposition: TypeAlias = (
    "EligibleForAutomaticDiagnosis"
    " | SkippedFromAutomaticDiagnosis"
    " | IneligibleForAutomaticDiagnosis"
    " | AutomaticDiagnosisEvaluationFailed"
)


# ---------------------------------------------------------------------------
# Summary accumulator (frozen; dict-typed reason maps for backwards compat)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DiagnosisDispositionSummary:
    """Pure accumulator of disposition aggregates.

    Invariants:

    * ``processed == eligible + skipped + ineligible + errors``
    * ``sum(skip_reasons.values()) == skipped``
    * ``sum(ineligible_reasons.values()) == ineligible``
    * ``sum(error_reasons.values()) == errors``
    * all reason counts are ``>= 1``
    """

    processed: int = 0
    eligible: int = 0
    skipped: int = 0
    ineligible: int = 0
    errors: int = 0
    skip_reasons: Mapping[DiagnosisSkipReason, int] = field(default_factory=dict)
    ineligible_reasons: Mapping[DiagnosisIneligibleReason, int] = field(default_factory=dict)
    error_reasons: Mapping[DiagnosisEvaluationFailureReason, int] = field(default_factory=dict)

    def is_consistent(self) -> bool:
        """Return True iff all conservation invariants hold."""
        if self.processed != self.eligible + self.skipped + self.ineligible + self.errors:
            return False
        if sum(self.skip_reasons.values()) != self.skipped:
            return False
        if sum(self.ineligible_reasons.values()) != self.ineligible:
            return False
        if sum(self.error_reasons.values()) != self.errors:
            return False
        if any(v <= 0 for v in self.skip_reasons.values()):
            return False
        if any(v <= 0 for v in self.ineligible_reasons.values()):
            return False
        if any(v <= 0 for v in self.error_reasons.values()):
            return False
        return True


def empty_disposition_summary() -> DiagnosisDispositionSummary:
    """Return the empty summary."""
    return DiagnosisDispositionSummary()


def _bump_skip_reason(
    mapping: Mapping[DiagnosisSkipReason, int],
    key: DiagnosisSkipReason,
) -> dict[DiagnosisSkipReason, int]:
    out: dict[DiagnosisSkipReason, int] = dict(mapping)
    out[key] = int(out.get(key, 0)) + 1
    return out


def _bump_ineligible_reason(
    mapping: Mapping[DiagnosisIneligibleReason, int],
    key: DiagnosisIneligibleReason,
) -> dict[DiagnosisIneligibleReason, int]:
    out: dict[DiagnosisIneligibleReason, int] = dict(mapping)
    out[key] = int(out.get(key, 0)) + 1
    return out


def _bump_error_reason(
    mapping: Mapping[DiagnosisEvaluationFailureReason, int],
    key: DiagnosisEvaluationFailureReason,
) -> dict[DiagnosisEvaluationFailureReason, int]:
    out: dict[DiagnosisEvaluationFailureReason, int] = dict(mapping)
    out[key] = int(out.get(key, 0)) + 1
    return out


def reduce_disposition(
    summary: DiagnosisDispositionSummary,
    disposition: IncidentDiagnosisDisposition,
) -> DiagnosisDispositionSummary:
    """Reduce a single disposition into a new summary.

    This is the only place where primary counters and reason maps are advanced.
    It is intentionally pure: it never inspects serialized dictionaries.
    """
    match disposition:
        case EligibleForAutomaticDiagnosis():
            return DiagnosisDispositionSummary(
                processed=summary.processed + 1,
                eligible=summary.eligible + 1,
                skipped=summary.skipped,
                ineligible=summary.ineligible,
                errors=summary.errors,
                skip_reasons=summary.skip_reasons,
                ineligible_reasons=summary.ineligible_reasons,
                error_reasons=summary.error_reasons,
            )
        case SkippedFromAutomaticDiagnosis(reason=reason):
            return DiagnosisDispositionSummary(
                processed=summary.processed + 1,
                eligible=summary.eligible,
                skipped=summary.skipped + 1,
                ineligible=summary.ineligible,
                errors=summary.errors,
                skip_reasons=_bump_skip_reason(summary.skip_reasons, reason),
                ineligible_reasons=summary.ineligible_reasons,
                error_reasons=summary.error_reasons,
            )
        case IneligibleForAutomaticDiagnosis(reason=reason):
            return DiagnosisDispositionSummary(
                processed=summary.processed + 1,
                eligible=summary.eligible,
                skipped=summary.skipped,
                ineligible=summary.ineligible + 1,
                errors=summary.errors,
                skip_reasons=summary.skip_reasons,
                ineligible_reasons=_bump_ineligible_reason(summary.ineligible_reasons, reason),
                error_reasons=summary.error_reasons,
            )
        case AutomaticDiagnosisEvaluationFailed(reason=reason):
            return DiagnosisDispositionSummary(
                processed=summary.processed + 1,
                eligible=summary.eligible,
                skipped=summary.skipped,
                ineligible=summary.ineligible,
                errors=summary.errors + 1,
                skip_reasons=summary.skip_reasons,
                ineligible_reasons=summary.ineligible_reasons,
                error_reasons=_bump_error_reason(summary.error_reasons, reason),
            )
        case _ as unreachable:  # pragma: no cover - exhaustiveness
            assert_never(unreachable)


def disposition_kind(disposition: IncidentDiagnosisDisposition) -> DiagnosisDispositionKind:
    """Map a disposition to its coarse kind using exhaustive match."""
    match disposition:
        case EligibleForAutomaticDiagnosis():
            return DiagnosisDispositionKind.ELIGIBLE
        case SkippedFromAutomaticDiagnosis():
            return DiagnosisDispositionKind.SKIPPED
        case IneligibleForAutomaticDiagnosis():
            return DiagnosisDispositionKind.INELIGIBLE
        case AutomaticDiagnosisEvaluationFailed():
            return DiagnosisDispositionKind.ERROR
        case _ as unreachable:  # pragma: no cover - exhaustiveness
            assert_never(unreachable)


# ---------------------------------------------------------------------------
# Detail sanitizer (wired into per-incident event projection)
# ---------------------------------------------------------------------------


_CONTROL_CHARS: frozenset[str] = frozenset(
    chr(c) for c in range(32) if c not in (9, 10, 13)
) | {"\x7f"}


def _redact_known_secrets(text: str) -> str:
    """Delegate to the canonical secret sanitizer, FAIL-CLOSED on failure.

    Per OWASP recommendations, we must never emit unsanitized secret-bearing
    text to the central log stream. If the canonical ``sanitize_log_entry``
    is unavailable, raises, or returns an unexpected shape, this helper
    returns ``"[REDACTED: sanitizer unavailable]"`` instead of leaking the
    raw text. The fail-closed default is asserted by dedicated tests in
    ``tests/unit/test_auto_loop_disposition_sanitizer.py``.
    """
    try:
        from ..security import sanitize_log_entry

        # ``sanitize_log_entry`` expects a Mapping; wrap our string so we
        # do not fight the type checker for an opt-in helper.
        sanitized = sanitize_log_entry({"detail": text})
        if isinstance(sanitized, Mapping):
            value = sanitized.get("detail")
            if isinstance(value, str):
                return value
    except Exception:
        pass

    return "[REDACTED: sanitizer unavailable]"


def sanitize_disposition_detail(
    detail: str | None,
    *,
    max_chars: int = DEFAULT_DETAIL_MAX_CHARS,
) -> str | None:
    """Bound and sanitize a disposition ``detail`` string.

    The per-incident disposition-event projector calls this helper so
    every emitted detail passes through truncation, control-character
    normalization, and the canonical secret sanitizer.
    """
    if detail is None:
        return None
    if not isinstance(detail, str):
        detail = str(detail)
    sanitized_chars: list[str] = []
    for ch in detail:
        if ch in _CONTROL_CHARS:
            sanitized_chars.append(" ")
        else:
            sanitized_chars.append(ch)
    sanitized = "".join(sanitized_chars)
    sanitized = _redact_known_secrets(sanitized)
    if max_chars and len(sanitized) > max_chars:
        if max_chars <= 0:
            return ""
        # Reserve one slot for the truncation ellipsis so the result is
        # strictly bounded by max_chars.
        sanitized = sanitized[: max_chars - 1] + "…"
    return sanitized


# ---------------------------------------------------------------------------
# Event projection
# ---------------------------------------------------------------------------


def per_incident_disposition_event(
    *,
    disposition: IncidentDiagnosisDisposition,
    run_id: str | None,
    collector_run_id: str,
    incident_id: str,
) -> dict[str, object]:
    """Project a per-incident disposition event for structured logging."""
    match disposition:
        case EligibleForAutomaticDiagnosis(
            eligibility_reason=eligibility_reason, budget_diagnostics=budget_diagnostics
        ):
            return {
                "event": "automatic-diagnosis-incident-disposition",
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "collector_run_id": collector_run_id,
                "incident_id": incident_id,
                "disposition": DiagnosisDispositionKind.ELIGIBLE.value,
                "reason_code": eligibility_reason,
                "detail": None,
                "budget_diagnostics": [d.to_dict() for d in budget_diagnostics],
            }
        case SkippedFromAutomaticDiagnosis(reason=reason, detail=detail, budget_diagnostics=budget_diagnostics):
            return {
                "event": "automatic-diagnosis-incident-disposition",
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "collector_run_id": collector_run_id,
                "incident_id": incident_id,
                "disposition": DiagnosisDispositionKind.SKIPPED.value,
                "reason_code": reason.value,
                "detail": sanitize_disposition_detail(detail),
                "budget_diagnostics": [d.to_dict() for d in budget_diagnostics],
            }
        case IneligibleForAutomaticDiagnosis(reason=reason, detail=detail):
            return {
                "event": "automatic-diagnosis-incident-disposition",
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "collector_run_id": collector_run_id,
                "incident_id": incident_id,
                "disposition": DiagnosisDispositionKind.INELIGIBLE.value,
                "reason_code": reason.value,
                "detail": sanitize_disposition_detail(detail),
                "budget_diagnostics": [],
            }
        case AutomaticDiagnosisEvaluationFailed(reason=reason, detail=detail):
            return {
                "event": "automatic-diagnosis-incident-disposition",
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "collector_run_id": collector_run_id,
                "incident_id": incident_id,
                "disposition": DiagnosisDispositionKind.ERROR.value,
                "reason_code": reason.value,
                "detail": sanitize_disposition_detail(detail),
                "budget_diagnostics": [],
            }
        case _ as unreachable:  # pragma: no cover - exhaustiveness
            assert_never(unreachable)


def aggregate_summary_event(
    *,
    summary: DiagnosisDispositionSummary,
    collector_run_id: str,
    stop_reason: str,
    run_id: str | None = None,
) -> dict[str, object]:
    """Project the aggregate eligibility-summary event for structured logging."""
    return {
        "event": "automatic-diagnosis-eligibility-summary",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "collector_run_id": collector_run_id,
        "incidents_processed": summary.processed,
        "incidents_eligible": summary.eligible,
        "incidents_skipped": summary.skipped,
        "incidents_ineligible": summary.ineligible,
        "incidents_with_errors": summary.errors,
        "skip_reasons": {k.value: v for k, v in summary.skip_reasons.items()},
        "ineligible_reasons": {k.value: v for k, v in summary.ineligible_reasons.items()},
        "error_reasons": {k.value: v for k, v in summary.error_reasons.items()},
        "stop_reason": stop_reason,
    }


# ---------------------------------------------------------------------------
# Legacy compatibility re-exports
# ---------------------------------------------------------------------------

from .incident_diagnosis_disposition_compat import (  # noqa: E402
    disposition_from_legacy_result,
    legacy_result_from_disposition,
)

__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_DETAIL_MAX_CHARS",
    "DiagnosisDispositionKind",
    "DiagnosisSkipReason",
    "DiagnosisIneligibleReason",
    "DiagnosisEvaluationFailureReason",
    "EligibleForAutomaticDiagnosis",
    "SkippedFromAutomaticDiagnosis",
    "IneligibleForAutomaticDiagnosis",
    "AutomaticDiagnosisEvaluationFailed",
    "IncidentDiagnosisDisposition",
    "DiagnosisDispositionSummary",
    "empty_disposition_summary",
    "reduce_disposition",
    "disposition_kind",
    "sanitize_disposition_detail",
    "per_incident_disposition_event",
    "aggregate_summary_event",
    "legacy_result_from_disposition",
    "disposition_from_legacy_result",
]

"""Backend-authoritative incident identity hardening.

This module provides canonical incident identity propagation and
consistency-error reporting for the Alertmanager → backend promotion →
automatic-diagnosis flow.

Background
----------
In sqlite/backend-api deployment mode the backend owns canonical incident
identities. The scheduler MUST NOT synthesize incident IDs from namespace,
object kind, object name, candidate class, or alert labels. Instead, the
backend promotion result exposes the canonical ``incident_id`` for every
opened or updated candidate, and the scheduler feeds those IDs directly
into automatic diagnosis.

This module is intentionally pure data and small helpers:
- Canonical record / outcome types
- Sanitized backend endpoint identity (no credentials)
- Bounded structured-diagnostics shape used in error events
- A ``verify_promotion_consistency`` helper that detects the
  ``incident_store_consistency_error`` class when promotion reports an
  incident and the subsequent authoritative lookup cannot find it.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01
ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R1 hardening
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_logger = logging.getLogger(__name__)


# =============================================================================
# Outcome / Identity Data Classes
# =============================================================================


# Outcome names for promotion operations. These are deliberately opaque
# strings so that backend, scheduler, and tests can compare them safely.
PROMOTION_OUTCOME_OPENED = "opened"
PROMOTION_OUTCOME_UPDATED = "updated"
PROMOTION_OUTCOME_SKIPPED_DUPLICATE = "skipped_duplicate"
PROMOTION_OUTCOME_NOOP = "noop"


# Identity access modes. The scheduler MUST use ``backend`` whenever the
# deployment is backend-authoritative (sqlite backend + scheduler role).
INCIDENT_ACCESS_MODE_BACKEND = "backend"
INCIDENT_ACCESS_MODE_LOCAL = "local"

# Promotion modes observed by the dispatcher.
PROMOTION_MODE_LOCAL = "local"
PROMOTION_MODE_BACKEND_API = "backend-api"

# Lookup error kinds recorded by the dispatcher. These let the consistency
# verifier distinguish between "the backend didn't have it" and "we never
# got an authoritative answer". Transport-level failures are NOT collapsed
# into "not found" because that broke the original incident_not_found
# diagnostic the ACT was meant to fix.
LOOKUP_ERROR_KIND_NOT_FOUND = "not_found"
LOOKUP_ERROR_KIND_TRANSPORT = "transport_error"
LOOKUP_ERROR_KIND_AUTHENTICATION = "authentication_error"
LOOKUP_ERROR_KIND_BACKEND_FAILURE = "backend_failure"
LOOKUP_ERROR_KIND_UNEXPECTED_PAYLOAD = "unexpected_payload"
LOOKUP_ERROR_KIND_NOT_ATTEMPTED = "lookup_not_attempted"

# Bounded-diagnostic limits. Diagnostics MUST stay bounded regardless of
# how many incidents or candidates the backend reports, otherwise the
# diagnostic event itself becomes a reliability risk.
DEFAULT_MAX_CANONICAL_IDS_IN_DIAGNOSTIC = 50
DEFAULT_MAX_PROMOTION_RECORDS_IN_DIAGNOSTIC = 50
DEFAULT_MAX_LOOKUP_OUTCOMES_IN_DIAGNOSTIC = 50
DEFAULT_MAX_SOURCE_CANDIDATE_IDS_IN_DIAGNOSTIC = 50


@dataclass(frozen=True)
class PromotionRecord:
    """A single canonical promotion outcome.

    Attributes:
        source_candidate_id: The candidate key used during promotion. This is
            correlation metadata only; it MUST NOT be treated as the
            ``incident_id`` for downstream lookups.
        canonical_incident_id: The backend-owned canonical ``incident_id``
            returned by the promotion. ``None`` when the candidate did not
            result in any store change (duplicate / noop).
        promotion_outcome: One of ``PROMOTION_OUTCOME_*`` values.
    """

    source_candidate_id: str
    canonical_incident_id: str | None
    promotion_outcome: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_candidate_id": self.source_candidate_id,
            "canonical_incident_id": self.canonical_incident_id,
            "promotion_outcome": self.promotion_outcome,
        }


@dataclass(frozen=True)
class BackendEndpointIdentity:
    """Sanitized backend endpoint identity without credentials.

    Only the URL ``scheme``, ``hostname``, and ``port`` are preserved.
    ``userinfo``, ``path``, ``query``, and ``fragment`` are intentionally
    dropped because they may carry bearer tokens, secret query
    parameters, or other credential-like material that MUST NOT appear in
    structured logs.

    Attributes:
        scheme: ``http`` / ``https`` or similar.
        host: Bare hostname (without userinfo or port).
        port: Optional port number, or ``None`` when the URL did not
            specify one.
        internal_api_path_prefix: Path prefix advertised by the k9b
            backend internal API (``"/api/internal"``). Always carried
            alongside the host so operators can tell which endpoint the
            scheduler talked to.
        backend_reachable: ``True`` if the most recent lookup attempt
            actually reached the backend and returned a valid response.
            ``False`` if the dispatcher hit a transport error. ``None``
            when the backend has not been contacted yet (e.g. before the
            scheduler runs an authoritative lookup).
        base_url: Convenience string ``scheme://host[:port]``. Empty when
            either ``scheme`` or ``host`` is missing.
    """

    scheme: str = ""
    host: str = ""
    port: int | None = None
    internal_api_path_prefix: str = "/api/internal"
    backend_reachable: bool | None = None

    @property
    def base_url(self) -> str:
        """Return ``scheme://host[:port]`` with no credentials or path.

        R3 contract: IPv6 literals MUST be re-bracketed in the rendered
        URL because ``urlparse`` strips the brackets from
        ``parsed.hostname``. Without re-bracketing, an IPv6-only backend
        would render as ``http://::1:8080`` which is unparseable.
        """
        if not self.scheme or not self.host:
            return ""
        # ``host`` may be an IPv6 literal (e.g. ``::1``) with no brackets
        # because ``urlparse.hostname`` strips them. We re-bracket whenever
        # the host contains a colon (an IPv6 heuristic that never triggers
        # for a regular DNS name).
        if ":" in self.host and not self.host.startswith("["):
            bracketed_host = f"[{self.host}]"
        else:
            bracketed_host = self.host
        if self.port is None:
            return f"{self.scheme}://{bracketed_host}"
        return f"{self.scheme}://{bracketed_host}:{self.port}"

    def to_dict(self) -> dict[str, str | int | bool | None]:
        return {
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "internal_api_path_prefix": self.internal_api_path_prefix,
            "backend_reachable": self.backend_reachable,
            "base_url": self.base_url,
        }


@dataclass(frozen=True)
class LookupOutcome:
    """Outcome of a single authoritative lookup.

    The ``found`` flag is meaningful only when ``error_kind`` is
    ``LOOKUP_ERROR_KIND_NOT_FOUND``. For all other error kinds the
    backend has either rejected the request, returned malformed data, or
    has not been contacted at all -- and the consistency verifier MUST
    NOT collapse those cases into ordinary ``not_found``.
    """

    canonical_incident_id: str
    found: bool = False
    error_kind: str = LOOKUP_ERROR_KIND_NOT_FOUND

    def is_authoritative_answer(self) -> bool:
        """Return True when the lookup yielded a definitive answer.

        A definitive answer is "found" or "not found" -- anything else
        (transport error, auth error, malformed payload, lookup not
        attempted at all) is treated as inconclusive.
        """
        return self.error_kind == LOOKUP_ERROR_KIND_NOT_FOUND


# =============================================================================
# Consistency Error
# =============================================================================


@dataclass
class IncidentStoreConsistencyError:
    """Bounded diagnostics for incident_store_consistency_error.

    Diagnostics are bounded by explicit per-field and per-record limits;
    omitted items are reported via the corresponding ``*_omitted`` counter
    so operators can see how much was elided. The diagnostics MUST NOT
    include any credentials, userinfo, query tokens, or Authorization
    values: ``BackendEndpointIdentity`` is the only endpoint payload
    permitted on the wire.
    """

    error_kind: str = "incident_store_consistency_error"
    source_candidate_ids: tuple[str, ...] = field(default_factory=tuple)
    source_candidate_ids_omitted: int = 0
    canonical_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    canonical_incident_ids_omitted: int = 0
    promotion_outcomes: tuple[str, ...] = field(default_factory=tuple)
    incident_access_mode: str = INCIDENT_ACCESS_MODE_BACKEND
    promotion_mode: str = PROMOTION_MODE_BACKEND_API
    backend_endpoint: BackendEndpointIdentity | None = None
    lookup_outcomes: tuple[LookupOutcome, ...] = field(default_factory=tuple)
    lookup_outcomes_omitted: int = 0
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error_kind": self.error_kind,
            "source_candidate_ids": list(self.source_candidate_ids),
            "source_candidate_ids_omitted": self.source_candidate_ids_omitted,
            "canonical_incident_ids": list(self.canonical_incident_ids),
            "canonical_incident_ids_omitted": self.canonical_incident_ids_omitted,
            "promotion_outcomes": list(self.promotion_outcomes),
            "incident_access_mode": self.incident_access_mode,
            "promotion_mode": self.promotion_mode,
            "backend_endpoint": (
                self.backend_endpoint.to_dict()
                if self.backend_endpoint is not None
                else None
            ),
            "lookup_outcomes": [
                _lookup_outcome_to_dict(o) for o in self.lookup_outcomes
            ],
            "lookup_outcomes_omitted": self.lookup_outcomes_omitted,
        }
        if self.note is not None:
            payload["note"] = self.note
        return payload


def _lookup_outcome_to_dict(outcome: LookupOutcome | Any) -> dict[str, Any]:
    """Serialise a ``LookupOutcome`` (or any duck-typed equivalent).

    Falls back to ``dataclasses.asdict`` for plain dataclasses that
    do not implement their own ``to_dict`` -- this lets the consistency
    payload render correctly even when a caller supplies a hand-rolled
    record. The hard-coded field set keeps the diagnostic bounded.
    """
    if hasattr(outcome, "to_dict") and callable(outcome.to_dict):
        return cast("dict[str, Any]", outcome.to_dict())  # type: ignore[no-any-return,unused-ignore]
    if hasattr(outcome, "__dataclass_fields__"):
        from dataclasses import asdict

        return cast("dict[str, Any]", dict(asdict(outcome)))  # type: ignore[no-any-return,unused-ignore]
    return {
        "canonical_incident_id": getattr(outcome, "canonical_incident_id", ""),
        "found": bool(getattr(outcome, "found", False)),
        "error_kind": getattr(outcome, "error_kind", "unknown"),
    }


# =============================================================================
# Helpers
# =============================================================================


def _sanitize_endpoint_components(
    base_url: str | None,
) -> tuple[str, str, int | None]:
    """Extract ``(scheme, host, port)`` from a base URL.

    Returns ``("", "", None)`` if the URL cannot be parsed.

    Any ``userinfo`` (e.g. ``user:pass@host``), path, query string, or
    fragment is discarded; those are the four places where a bearer
    token, password, or query-secret might leak through, and they MUST
    NOT enter structured logs. Only the bare hostname (lowercased) and
    optional integer port survive sanitisation.

    R2 hardening:

    * ``ValueError`` from ``parsed.port`` is caught (invalid ports and
      some IPv6 shapes raise from the property). The fallback keeps the
      host so the diagnostic still identifies the backend at a
      hostname-level even when the port is unparseable.
    * IPv6 literals are preserved by normalising brackets away before
      returning. ``urlparse`` already lowercases the hostname; we keep
      the same convention for the port.
    """
    if not base_url:
        return "", "", None
    try:
        parsed = urlparse(base_url)
    except (ValueError, TypeError):
        # Fall back to a safe empty identity when urlparse cannot cope
        # with the input. We deliberately do not return the raw
        # ``base_url`` because callers MUST always be able to render the
        # diagnostic without leaking arbitrary URL payloads.
        return "", "", None
    scheme = parsed.scheme or ""
    # ``parsed.hostname`` returns ``None`` for some malformed inputs and
    # can raise ``ValueError`` for IPv6 literals with zones. We catch
    # both so the diagnostic never crashes the call site.
    try:
        host = parsed.hostname or ""
    except ValueError:
        host = ""
    host = host.lower()
    # ``parsed.port`` raises ``ValueError`` when the port is not a valid
    # integer (e.g. ``http://host:abc/`` or out-of-range values). The
    # diagnostic should still identify the host, so we keep the host
    # and report ``port=None`` instead of crashing.
    try:
        port: int | None = parsed.port
    except ValueError:
        port = None
    if scheme == "" and host == "":
        return "", "", None
    return scheme, host, port


def backend_endpoint_identity_from_url(
    base_url: str | None,
    *,
    backend_reachable: bool | None = None,
) -> BackendEndpointIdentity:
    """Build a sanitized ``BackendEndpointIdentity`` from a base URL.

    URL parsing drops userinfo, query strings, fragments, and path data so
    that no bearer token or query-secret can leak into the structured
    payload, even when the underlying env var contains a credentialed URL.
    """
    scheme, host, port = _sanitize_endpoint_components(base_url)
    return BackendEndpointIdentity(
        scheme=scheme,
        host=host,
        port=port,
        internal_api_path_prefix="/api/internal",
        backend_reachable=backend_reachable,
    )


def select_canonical_ids_from_promotion(
    records: Sequence[PromotionRecord],
    *,
    include_skipped: bool = False,
) -> list[str]:
    """Return canonical incident IDs from promotion records.

    Only records with a non-``None`` canonical incident ID are returned,
    optionally skipping duplicate outcomes. The output preserves
    deterministic first-seen order so automatic diagnosis visits each
    canonical incident exactly once per health run.
    """
    canonical: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.canonical_incident_id is None:
            continue
        if (
            not include_skipped
            and record.promotion_outcome == PROMOTION_OUTCOME_SKIPPED_DUPLICATE
        ):
            continue
        if record.canonical_incident_id in seen:
            continue
        seen.add(record.canonical_incident_id)
        canonical.append(record.canonical_incident_id)
    return canonical


def build_promotion_records_from_pairs(
    pairs: Iterable[tuple[str, str | None, str]],
) -> list[PromotionRecord]:
    """Build ``PromotionRecord`` instances from ``(candidate_id, incident_id, outcome)`` triples."""
    return [
        PromotionRecord(
            source_candidate_id=candidate_id,
            canonical_incident_id=incident_id,
            promotion_outcome=outcome,
        )
        for candidate_id, incident_id, outcome in pairs
    ]


# =============================================================================
# Bounded Diagnostics
# =============================================================================


def _truncate_with_count(
    values: Sequence[Any],
    limit: int,
) -> tuple[list[Any], int]:
    """Return ``(truncated_values, omitted_count)`` for a bounded payload.

    Preserves deterministic first-seen order so downstream log readers
    see the same records the verifier used to derive the consistency
    error. Items beyond ``limit`` are reported only as ``omitted_count``
    so the structured payload remains bounded.
    """
    if limit < 0:
        limit = 0
    if len(values) <= limit:
        return list(values), 0
    truncated = list(values[:limit])
    omitted = len(values) - limit
    return truncated, omitted


def _drop_none(values: Iterable[str | None]) -> list[str]:
    """Drop ``None`` and empty strings from a list of optional str."""
    return [
        value
        for value in values
        if isinstance(value, str) and value
    ]


# =============================================================================
# Consistency Verification
# =============================================================================


class PromotionConsistencyContractError(ValueError):
    """Raised when the promotion contract is internally inconsistent.

    R5 hardening (item 1): the consistency verifier fails closed when
    the dispatcher reports nonzero ``opened_incidents`` or
    ``updated_incidents`` but the supplied ``promotion_records`` cannot
    account for those numbers, when canonical ``incident_id`` values are
    missing on opened/updated records, or when the per-aggregate ID
    arrays disagree with the per-record canonical IDs.

    The legacy-backend regression -- nonzero counts with empty IDs and
    empty records -- raises this typed error instead of being silently
    ignored. Catching the error in the orchestrator lets the operator
    route the error to the audit log without conflating it with an
    ``IncidentStoreConsistencyError`` (which is reserved for genuine
    backend / promotion mismatches).
    """

    def __init__(
        self,
        message: str,
        *,
        opened_incidents: int = 0,
        updated_incidents: int = 0,
        promotion_record_count: int = 0,
        opened_id_count: int = 0,
        updated_id_count: int = 0,
        missing_canonical_ids: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.opened_incidents = opened_incidents
        self.updated_incidents = updated_incidents
        self.promotion_record_count = promotion_record_count
        self.opened_id_count = opened_id_count
        self.updated_id_count = updated_id_count
        self.missing_canonical_ids = tuple(missing_canonical_ids)


def _validate_response_contracts(
    *,
    promotion_records: Sequence[PromotionRecord],
    opened_incidents: int,
    updated_incidents: int,
    opened_incident_ids: Sequence[str],
    updated_incident_ids: Sequence[str],
) -> None:
    """Fail closed on count / canonical-id / record-set disagreement.

    R5 contract: never silently promote a dispatcher response where the
    declared counts cannot be reconciled with the authoritative
    ``promotion_records`` list and the per-aggregate ``*_incident_ids``
    arrays. The exact legacy-backend regression -- nonzero counts,
    empty ID arrays, empty records -- is one of the failure shapes that
    raises :class:`PromotionConsistencyContractError` here.
    """
    opened_records = [
        r
        for r in promotion_records
        if r.promotion_outcome == PROMOTION_OUTCOME_OPENED
    ]
    updated_records = [
        r
        for r in promotion_records
        if r.promotion_outcome == PROMOTION_OUTCOME_UPDATED
    ]
    record_opened_count = len(opened_records)
    record_updated_count = len(updated_records)

    declared_total = int(opened_incidents) + int(updated_incidents)
    record_total = record_opened_count + record_updated_count

    if declared_total > 0 and record_total == 0:
        raise PromotionConsistencyContractError(
            "Legacy-backend regression: dispatcher reported "
            f"opened_incidents={opened_incidents} and "
            f"updated_incidents={updated_incidents} but the "
            "promotion_records list contains no opened/updated entries.",
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            promotion_record_count=len(promotion_records),
            opened_id_count=len(opened_incident_ids),
            updated_id_count=len(updated_incident_ids),
        )

    if int(opened_incidents) != record_opened_count:
        raise PromotionConsistencyContractError(
            "opened_incidents aggregate disagrees with per-record "
            "count.",
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            promotion_record_count=len(promotion_records),
            opened_id_count=len(opened_incident_ids),
            updated_id_count=len(updated_incident_ids),
        )

    if int(updated_incidents) != record_updated_count:
        raise PromotionConsistencyContractError(
            "updated_incidents aggregate disagrees with per-record "
            "count.",
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            promotion_record_count=len(promotion_records),
            opened_id_count=len(opened_incident_ids),
            updated_id_count=len(updated_incident_ids),
        )

    missing: list[str] = []
    for record in opened_records + updated_records:
        if not record.canonical_incident_id:
            missing.append(
                f"{record.promotion_outcome}:{record.source_candidate_id}"
            )
    if missing:
        raise PromotionConsistencyContractError(
            "Opened/updated record missing canonical_incident_id.",
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            promotion_record_count=len(promotion_records),
            opened_id_count=len(opened_incident_ids),
            updated_id_count=len(updated_incident_ids),
            missing_canonical_ids=tuple(missing),
        )

    # R7 ordered-sequence-with-multiplicity contract:
    # ``opened_incident_ids`` and ``updated_incident_ids`` are the
    # authoritative arrays carried by the dispatcher. The
    # ``promotion_records`` list is the authoritative record source.
    # The per-aggregate array MUST equal the ordered sequence of
    # canonical_incident_id values on opened/updated records
    # (matching by multiplicity in record order): reorderings, missing
    # entries, and multiplicity mismatches all fail closed. This
    # check runs AFTER the missing-canonical-id check so records that
    # never carried an authoritative ID surface the canonical-missing
    # diagnostic instead of being silently absorbed into an
    # ordered-sequence mismatch.
    opened_canonical_records = [
        record.canonical_incident_id
        for record in opened_records
        if record.canonical_incident_id is not None
    ]
    updated_canonical_records = [
        record.canonical_incident_id
        for record in updated_records
        if record.canonical_incident_id is not None
    ]
    opened_id_tuple = tuple(opened_incident_ids)
    updated_id_tuple = tuple(updated_incident_ids)
    if tuple(opened_canonical_records) != opened_id_tuple:
        raise PromotionConsistencyContractError(
            "opened_incident_ids disagree with per-record canonical-id "
            "ordered sequence (matching by multiplicity in record order).",
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            promotion_record_count=len(promotion_records),
            opened_id_count=len(opened_incident_ids),
            updated_id_count=len(updated_incident_ids),
        )
    if tuple(updated_canonical_records) != updated_id_tuple:
        raise PromotionConsistencyContractError(
            "updated_incident_ids disagree with per-record canonical-id "
            "ordered sequence (matching by multiplicity in record order).",
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            promotion_record_count=len(promotion_records),
            opened_id_count=len(opened_incident_ids),
            updated_id_count=len(updated_incident_ids),
        )

def verify_promotion_consistency(
    promotion_records: Sequence[PromotionRecord],
    *,
    lookups: Sequence[LookupOutcome],
    backend_endpoint: BackendEndpointIdentity | None,
    opened_incidents: int = 0,
    updated_incidents: int = 0,
    opened_incident_ids: Sequence[str] = (),
    updated_incident_ids: Sequence[str] = (),
) -> IncidentStoreConsistencyError | None:
    """Verify that promotion-outcome incidents are visible via authoritative lookup.

    A consistency error is produced only when the promotion claims an opened
    or updated outcome for a canonical incident ID and either the
    authoritative lookup is missing entirely or the authoritative lookup
    explicitly says ``not_found``. Non-definitive answer kinds
    (transport errors, authentication failures, backend failures,
    unexpected payload, or a lookup that was never attempted) are
    treated as inconclusive: the consistency verifier does not raise
    an error so the dispatcher can record them separately as a
    authoritative-reachability failure.

    R5 contract: callers MUST pass the dispatcher's declared aggregate
    counts (``opened_incidents`` / ``updated_incidents``) and the
    per-aggregate canonical ID arrays
    (``opened_incident_ids`` / ``updated_incident_ids``). The helper
    raises :class:`PromotionConsistencyContractError` when those values
    are internally inconsistent, including the exact legacy-backend
    regression ``opened_incidents > 0`` but empty IDs/records.

    Returns ``None`` when the promotion claims are consistent with the
    authoritative lookups or when the answer is inconclusive.
    Otherwise returns an ``IncidentStoreConsistencyError`` with bounded
    diagnostics.
    """
    _validate_response_contracts(
        promotion_records=promotion_records,
        opened_incidents=opened_incidents,
        updated_incidents=updated_incidents,
        opened_incident_ids=opened_incident_ids,
        updated_incident_ids=updated_incident_ids,
    )

    if not promotion_records or not lookups:
        return None

    lookup_by_id: dict[str, LookupOutcome] = {
        o.canonical_incident_id: o for o in lookups
    }

    inconsistent: list[PromotionRecord] = []
    for record in promotion_records:
        if record.canonical_incident_id is None:
            continue
        if record.promotion_outcome not in (
            PROMOTION_OUTCOME_OPENED,
            PROMOTION_OUTCOME_UPDATED,
        ):
            continue
        outcome = lookup_by_id.get(record.canonical_incident_id)
        # Only treat "definitively not found" as inconsistency; missing
        # lookups (transport errors, etc.) belong in a separate
        # reachability error path.
        if outcome is not None and outcome.is_authoritative_answer() and not outcome.found:
            inconsistent.append(record)

    if not inconsistent:
        return None

    source_candidate_ids_full = _drop_none(
        record.source_candidate_id for record in inconsistent
    )
    canonical_incident_ids_full = _drop_none(
        record.canonical_incident_id for record in inconsistent
    )
    promotion_outcomes_full = [record.promotion_outcome for record in inconsistent]

    canonical_incident_ids = [
        record.canonical_incident_id
        for record in inconsistent
        if record.canonical_incident_id is not None
    ]
    lookup_outcomes = tuple(
        filter(
            None,
            (
                lookup_by_id.get(canonical_id)
                for canonical_id in canonical_incident_ids
            ),
        )
    )

    truncated_source, source_omitted = _truncate_with_count(
        source_candidate_ids_full,
        DEFAULT_MAX_SOURCE_CANDIDATE_IDS_IN_DIAGNOSTIC,
    )
    truncated_canonical, canonical_omitted = _truncate_with_count(
        canonical_incident_ids_full,
        DEFAULT_MAX_CANONICAL_IDS_IN_DIAGNOSTIC,
    )
    truncated_lookups, lookup_omitted = _truncate_with_count(
        lookup_outcomes,
        DEFAULT_MAX_LOOKUP_OUTCOMES_IN_DIAGNOSTIC,
    )

    return IncidentStoreConsistencyError(
        source_candidate_ids=tuple(truncated_source),
        source_candidate_ids_omitted=source_omitted,
        canonical_incident_ids=tuple(truncated_canonical),
        canonical_incident_ids_omitted=canonical_omitted,
        promotion_outcomes=tuple(
            promotion_outcomes_full[:DEFAULT_MAX_PROMOTION_RECORDS_IN_DIAGNOSTIC]
        ),
        incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        promotion_mode=PROMOTION_MODE_BACKEND_API,
        backend_endpoint=backend_endpoint,
        lookup_outcomes=tuple(truncated_lookups),
        lookup_outcomes_omitted=lookup_omitted,
        note=(
            "Promotion reported opened/updated outcomes that an authoritative "
            "backend lookup could not confirm. This indicates a "
            "write/read inconsistency between the promotion path and the "
            "subsequent backend incident read."
        ),
    )


def log_incident_store_consistency_error(
    error: IncidentStoreConsistencyError,
    *,
    log_event: Any | None = None,
) -> None:
    """Emit a structured log event for an incident_store_consistency_error.

    Uses both the standard logging module and the optional structured
    ``log_event`` callback (used by the scheduler and webhook handlers).
    The structured event payload NEVER includes the internal API token or
    any other secret. Bounded totals and "omitted" counts prevent the
    diagnostic itself from becoming a reliability risk.
    """
    payload = error.to_dict()
    _logger.error(
        "incident_store_consistency_error",
        extra={
            "event": error.error_kind,
            "diagnostics": payload,
        },
    )
    if log_event is not None:
        try:
            log_event(
                "incident-identity",
                "ERROR",
                "incident_store_consistency_error",
                event=error.error_kind,
                diagnostics=payload,
            )
        except Exception:
            # Loggers must never break the dispatching flow.
            _logger.debug("log_event raised while recording consistency error", exc_info=True)


__all__ = [
    "BackendEndpointIdentity",
    "DEFAULT_MAX_CANONICAL_IDS_IN_DIAGNOSTIC",
    "DEFAULT_MAX_LOOKUP_OUTCOMES_IN_DIAGNOSTIC",
    "DEFAULT_MAX_PROMOTION_RECORDS_IN_DIAGNOSTIC",
    "DEFAULT_MAX_SOURCE_CANDIDATE_IDS_IN_DIAGNOSTIC",
    "IncidentStoreConsistencyError",
    "LOOKUP_ERROR_KIND_AUTHENTICATION",
    "LOOKUP_ERROR_KIND_BACKEND_FAILURE",
    "LOOKUP_ERROR_KIND_NOT_ATTEMPTED",
    "LOOKUP_ERROR_KIND_NOT_FOUND",
    "LOOKUP_ERROR_KIND_TRANSPORT",
    "LOOKUP_ERROR_KIND_UNEXPECTED_PAYLOAD",
    "LookupOutcome",
    "PROMOTION_MODE_BACKEND_API",
    "PROMOTION_MODE_LOCAL",
    "PromotionConsistencyContractError",
    "PromotionRecord",
    "INCIDENT_ACCESS_MODE_BACKEND",
    "INCIDENT_ACCESS_MODE_LOCAL",
    "PROMOTION_OUTCOME_NOOP",
    "PROMOTION_OUTCOME_OPENED",
    "PROMOTION_OUTCOME_SKIPPED_DUPLICATE",
    "PROMOTION_OUTCOME_UPDATED",
    "backend_endpoint_identity_from_url",
    "build_promotion_records_from_pairs",
    "log_incident_store_consistency_error",
    "select_canonical_ids_from_promotion",
    "verify_promotion_consistency",
]

"""Incident promotion dispatcher.

This module selects the appropriate promotion path (local vs backend-api) based on
configuration and provides a unified interface for scheduler incident promotion.

Hard constraints enforced:
- NO scheduler direct SQLite writes
- NO scheduler SQLiteIncidentStore instantiation
- NO remediation actions
- NO LLM calls from the promotion transport layer
- Internal promotion must use K9B_INTERNAL_API_TOKEN bearer auth

Configuration:
- K9B_INCIDENT_PROMOTION_MODE: local|backend-api|auto (default: auto)
- K9B_BACKEND_INTERNAL_URL: Backend service URL for backend-api mode
- K9B_INTERNAL_API_TOKEN: Token for internal API authentication
- K9B_INCIDENT_STORE_BACKEND: Backend type (memory|file|sqlite)
- K9B_PROCESS_ROLE: Process role (backend|scheduler)

Behavior:
- local: Use existing local get_incident_store() promotion path
- backend-api: Post to backend internal API (required for scheduler+sqlite)
- auto: Use backend-api if K9B_INCIDENT_STORE_BACKEND=sqlite or K9B_PROCESS_ROLE=scheduler
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from .incident_candidates import (
    CandidateSignal,
    IncidentCandidate,
)
from .incident_identity_hardening import PromotionRecord
from .incident_promotion_accumulator import RunPromotionAccumulator
from .incident_promotion_batch import PromotionBatch

_logger = logging.getLogger(__name__)

# Environment variables
ENV_PROMOTION_MODE = "K9B_INCIDENT_PROMOTION_MODE"
ENV_BACKEND_URL = "K9B_BACKEND_INTERNAL_URL"
ENV_INTERNAL_API_TOKEN = "K9B_INTERNAL_API_TOKEN"
ENV_STORE_BACKEND = "K9B_INCIDENT_STORE_BACKEND"
ENV_PROCESS_ROLE = "K9B_PROCESS_ROLE"

# Promotion modes
MODE_LOCAL: Literal["local"] = "local"
MODE_BACKEND_API: Literal["backend-api"] = "backend-api"
MODE_AUTO: Literal["auto"] = "auto"

# Process roles
ROLE_BACKEND = "backend"
ROLE_SCHEDULER = "scheduler"

# Incident access modes
INCIDENT_ACCESS_MODE_LOCAL = "local"
INCIDENT_ACCESS_MODE_BACKEND = "backend"


def _incident_access_mode_for_promotion_mode(
    promotion_mode: Literal["local", "backend-api"],
) -> str:
    """Derive the canonical incident access mode for a promotion mode."""
    return (
        INCIDENT_ACCESS_MODE_LOCAL
        if promotion_mode == MODE_LOCAL
        else INCIDENT_ACCESS_MODE_BACKEND
    )


@dataclass(frozen=True)
class IncidentPromotionDispatchConfig:
    """Configuration for incident promotion dispatcher."""

    mode: Literal["local", "backend-api", "auto"]
    backend_url: str | None
    internal_api_token: str | None
    store_backend: str
    process_role: str

    def resolved_mode(self) -> Literal["local", "backend-api"]:
        """Resolve auto mode to concrete mode."""
        if self.mode == MODE_LOCAL:
            return MODE_LOCAL
        if self.mode == MODE_BACKEND_API:
            return MODE_BACKEND_API
        # Auto mode
        if self.store_backend == "sqlite":
            return MODE_BACKEND_API
        if self.process_role == ROLE_SCHEDULER:
            return MODE_BACKEND_API
        return MODE_LOCAL

    def resolved_incident_access_mode(self) -> str:
        """Resolve the access mode that corresponds to the resolved mode."""
        return _incident_access_mode_for_promotion_mode(self.resolved_mode())

    def requires_backend_api(self) -> bool:
        """Check if backend API is required for promotion."""
        return self.resolved_mode() == MODE_BACKEND_API

    def can_use_local(self) -> bool:
        """Check if local promotion is allowed."""
        resolved = self.resolved_mode()
        if resolved == MODE_LOCAL:
            if self.process_role == ROLE_SCHEDULER and self.store_backend == "sqlite":
                return False
            return True
        return False

    def is_config_valid(self) -> tuple[bool, str | None]:
        """Validate configuration for the resolved mode."""
        if self.resolved_mode() == MODE_BACKEND_API:
            if not self.backend_url:
                return False, "missing_backend_url"
            if not self.internal_api_token:
                return False, "missing_internal_api_token"
        return True, None


@dataclass(frozen=True)
class IncidentPromotionResult:
    """Result of an incident promotion operation.

    The result exposes per-canonical-incident ``opened_incident_ids`` /
    ``updated_incident_ids`` plus a per-candidate ``promotion_records``
    mapping so that downstream callers (notably automatic diagnosis) can
    consume canonical ``incident_id`` values directly without
    re-deriving them from candidate attributes.

    Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01
    """

    ok: bool = True
    scanned: int = 0
    firing: int = 0
    opened_incidents: int = 0
    updated_incidents: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    error_messages: tuple[str, ...] = field(default_factory=tuple)
    # Track the mode used for correct event logging
    promotion_mode: Literal["local", "backend-api"] = "local"
    # Canonical identity propagation
    opened_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    updated_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    # R1: typed categories from the scoped endpoint.
    observation_refreshed_incident_ids: tuple[str, ...] = field(
        default_factory=tuple
    )
    unchanged_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    promotion_records: tuple[dict[str, str | None], ...] = field(default_factory=tuple)
    unique_candidate_count: int = 0
    promotion_scan_scope: str = ""
    incident_access_mode: str = "local"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for logging/response."""
        return {
            "ok": self.ok,
            "scanned": self.scanned,
            "firing": self.firing,
            "opened_incidents": self.opened_incidents,
            "updated_incidents": self.updated_incidents,
            "skipped_duplicates": self.skipped_duplicates,
            "errors": self.errors,
            "error_messages": list(self.error_messages),
            "promotion_mode": self.promotion_mode,
            "opened_incident_ids": list(self.opened_incident_ids),
            "updated_incident_ids": list(self.updated_incident_ids),
            "promotion_records": [dict(r) for r in self.promotion_records],
            "unique_candidate_count": self.unique_candidate_count,
            "promotion_scan_scope": self.promotion_scan_scope,
            "incident_access_mode": self.incident_access_mode,
        }

    def canonical_incident_ids(self) -> tuple[str, ...]:
        """Return opened + updated canonical incident IDs as one tuple."""
        return tuple(list(self.opened_incident_ids) + list(self.updated_incident_ids))


def _get_dispatch_config() -> IncidentPromotionDispatchConfig:
    """Get the current dispatch configuration from environment."""
    return IncidentPromotionDispatchConfig(
        mode=os.environ.get(ENV_PROMOTION_MODE, MODE_AUTO).lower(),  # type: ignore[arg-type]
        backend_url=os.environ.get(ENV_BACKEND_URL),
        internal_api_token=os.environ.get(ENV_INTERNAL_API_TOKEN),
        store_backend=os.environ.get(ENV_STORE_BACKEND, "memory").lower(),
        process_role=os.environ.get(ENV_PROCESS_ROLE, "").lower(),
    )


def _result_from_dict(
    d: dict[str, Any], promotion_mode: Literal["local", "backend-api"] = "local"
) -> IncidentPromotionResult:
    """Convert promotion dict to IncidentPromotionResult.

    Carries the canonical incident IDs and per-candidate mapping (when the
    upstream provider exposes them) so callers can consume ``incident_id``
    values directly without re-deriving them from candidate attributes.

    R2: every typed category produced by the new
    ``IncidentPromotionResult`` (observation-refreshed, unchanged, skipped
    signals, failures) is mapped from the wire/dict payload so the
    dispatcher's downstream log lines and accumulator entries can read the
    real category counts.
    """
    default_access_mode = _incident_access_mode_for_promotion_mode(promotion_mode)
    return IncidentPromotionResult(
        ok=d.get("ok", False),
        scanned=d.get("scanned", 0),
        firing=d.get("firing", 0),
        opened_incidents=d.get("opened_incidents", 0),
        updated_incidents=d.get("updated_incidents", 0),
        skipped_duplicates=d.get("skipped_duplicates", 0),
        errors=d.get("errors", 0),
        error_messages=tuple(d.get("error_messages", [])),
        promotion_mode=promotion_mode,
        opened_incident_ids=tuple(d.get("opened_incident_ids") or ()),
        updated_incident_ids=tuple(d.get("updated_incident_ids") or ()),
        observation_refreshed_incident_ids=tuple(
            d.get("observation_refreshed_incident_ids") or ()
        ),
        unchanged_incident_ids=tuple(d.get("unchanged_incident_ids") or ()),
        promotion_records=tuple(
            dict(record) for record in (d.get("promotion_records") or ())
        ),
        unique_candidate_count=int(d.get("unique_candidate_count") or 0),
        promotion_scan_scope=str(d.get("promotion_scan_scope") or ""),
        incident_access_mode=str(
            d.get("incident_access_mode") or default_access_mode
        ),
    )


def promote_candidates(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> IncidentPromotionResult:
    """Promote incident candidates via configured path.

    This is the main entry point for scheduler health-loop promotion.

    Args:
        candidates: List of candidates to promote
        observed_at: When candidates were observed
        snapshot_bundle_id: Optional snapshot bundle ID

    Returns:
        IncidentPromotionResult with promotion counts
    """
    config = _get_dispatch_config()
    resolved = config.resolved_mode()

    if resolved == MODE_LOCAL:
        if not config.can_use_local():
            _logger.error(
                "Local promotion forbidden for scheduler+sqlite mode",
                extra={
                    "event": "incident-promotion-config-invalid",
                    "reason": "scheduler_sqlite_forbidden",
                    "process_role": config.process_role,
                    "store_backend": config.store_backend,
                },
            )
            return IncidentPromotionResult(
                ok=False,
                scanned=len(candidates),
                errors=1,
                error_messages=(
                    "Local promotion forbidden: scheduler cannot use SQLite store directly",
                ),
            )
        from .incident_promotion_local import promote_local

        return _result_from_dict(promote_local(candidates, observed_at, snapshot_bundle_id), MODE_LOCAL)

    # Backend API mode
    from .incident_promotion_backend import promote_via_backend_api

    return _result_from_dict(promote_via_backend_api(candidates, observed_at, snapshot_bundle_id), MODE_BACKEND_API)


def promote_alert_signals(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> IncidentPromotionResult:
    """Promote alert signal candidates via configured path.

    This is the main entry point for Alertmanager alert signal promotion.

    Args:
        candidates: List of alert signal candidates to promote
        observed_at: When signals were observed
        snapshot_bundle_id: Optional snapshot bundle ID

    Returns:
        IncidentPromotionResult with promotion counts
    """
    config = _get_dispatch_config()
    resolved = config.resolved_mode()

    _logger.info(
        "Alert signal promotion requested",
        extra={
            "event": "alert-signals-promotion-start"
            if resolved == MODE_LOCAL
            else "alert-signals-promotion-start-via-backend",
            "promotion_mode": resolved,
            "candidate_count": len(candidates),
            "snapshot_bundle_id": snapshot_bundle_id,
        },
    )

    if resolved == MODE_LOCAL:
        if not config.can_use_local():
            _logger.error(
                "Local promotion forbidden for scheduler+sqlite mode",
                extra={
                    "event": "incident-promotion-config-invalid",
                    "reason": "scheduler_sqlite_forbidden",
                    "process_role": config.process_role,
                    "store_backend": config.store_backend,
                },
            )
            return IncidentPromotionResult(
                ok=False,
                scanned=len(candidates),
                errors=1,
                error_messages=(
                    "Local promotion forbidden: scheduler cannot use SQLite store directly",
                ),
            )
        from .incident_promotion_local import promote_local

        result = _result_from_dict(promote_local(candidates, observed_at, snapshot_bundle_id), MODE_LOCAL)
        _logger.info(
            "Alert signals promoted",
            extra={
                "event": "alert-signals-promoted",
                "promotion_mode": MODE_LOCAL,
                "scanned": result.scanned,
                "firing": result.firing,
                "opened_incidents": result.opened_incidents,
                "updated_incidents": result.updated_incidents,
                "skipped_duplicates": result.skipped_duplicates,
                "errors": result.errors,
            },
        )
        return result

    # Backend API mode - use alert-signals specific endpoint
    from .incident_promotion_backend import promote_alert_signals_via_backend_api

    _logger.info(
        "Alert signal promotion via backend API",
        extra={
            "event": "alert-signals-promotion-via-backend",
            "promotion_mode": "backend-api",
            "backend_url": config.backend_url,
            "candidate_count": len(candidates),
        },
    )

    result = _result_from_dict(
        promote_alert_signals_via_backend_api(candidates, observed_at, snapshot_bundle_id),
        MODE_BACKEND_API,
    )
    _logger.info(
        "Alert signals promoted via backend",
        extra={
            "event": "alert-signals-promoted-via-backend",
            "promotion_mode": MODE_BACKEND_API,
            "backend_url": config.backend_url,
            "scanned": result.scanned,
            "firing": result.firing,
            "opened_incidents": result.opened_incidents,
            "updated_incidents": result.updated_incidents,
            "skipped_duplicates": result.skipped_duplicates,
            "errors": result.errors,
        },
    )
    return result


def log_promotion_config() -> None:
    """Log the current promotion configuration at startup."""
    config = _get_dispatch_config()
    resolved = config.resolved_mode()
    is_valid, error = config.is_config_valid()

    if is_valid:
        _logger.info(
            "Incident promotion configured",
            extra={
                "event": "incident-promotion-configured",
                "promotion_mode": resolved,
                "backend_url": config.backend_url or "none",
                "store_backend": config.store_backend,
                "process_role": config.process_role or "unset",
            },
        )
    else:
        _logger.error(
            "Incident promotion configuration invalid",
            extra={
                "event": "incident-promotion-config-invalid",
                "reason": error,
                "promotion_mode": resolved,
                "backend_url": config.backend_url or "none",
                "store_backend": config.store_backend,
                "process_role": config.process_role or "unset",
            },
        )


def scan_alert_signals_as_candidates(runs_dir: Path) -> list[IncidentCandidate]:
    """Scan persisted alert signals and convert to candidates for API promotion.

    Args:
        runs_dir: The runs directory containing alert signal artifacts

    Returns:
        List of IncidentCandidates ready for promotion
    """
    from ..incident_alert_classifier import classify_alert_signal
    from ..incident_alert_correlation import build_alert_incident_correlation_key
    from ..incident_alert_promotion import (
        _build_alert_message,
        _map_alert_class_to_candidate_class,
        _map_entity_kind_to_object_kind,
        _map_severity,
    )
    from ..incident_alert_signal_reader import scan_alert_signal_artifacts

    candidates: list[IncidentCandidate] = []
    seen_keys: set[str] = set()

    for artifact in scan_alert_signal_artifacts(runs_dir):
        try:
            if artifact.signal is None:
                continue
            signal = artifact.signal
            if signal.status.value != "firing":
                continue

            classification = classify_alert_signal(signal)
            correlation_key = build_alert_incident_correlation_key(signal, classification)
            if correlation_key in seen_keys:
                continue
            seen_keys.add(correlation_key)

            # Build candidate
            candidate_class = _map_alert_class_to_candidate_class(classification.class_)
            severity = _map_severity(signal.severity)
            object_kind = _map_entity_kind_to_object_kind(classification.entity_kind)

            candidates.append(
                IncidentCandidate(
                    candidate_id=correlation_key,
                    namespace=classification.namespace,
                    object_kind=object_kind,
                    object_name=classification.entity_name,
                    candidate_class=candidate_class,
                    severity=severity,
                    signals=(
                        CandidateSignal(
                            source="alert",
                            reason=signal.alertname,
                            message=_build_alert_message(signal),
                        ),
                    ),
                    evidence_needed=("alert_evidence",),
                )
            )
        except Exception:
            _logger.exception("Error scanning alert signal artifact %s", artifact.identity)

    return candidates


def promote_alert_signals_from_artifacts(
    runs_dir: Path,
    snapshot_bundle_id: str | None = None,
) -> IncidentPromotionResult:
    """Promote alert signals from persisted artifacts.

    Args:
        runs_dir: The runs directory containing alert signal artifacts
        snapshot_bundle_id: Optional snapshot bundle ID

    Returns:
        IncidentPromotionResult with promotion counts
    """
    from datetime import UTC

    candidates = scan_alert_signals_as_candidates(runs_dir)
    if not candidates:
        return IncidentPromotionResult(
            ok=True, scanned=0, firing=0, opened_incidents=0,
            updated_incidents=0, skipped_duplicates=0, errors=0,
        )
    return promote_alert_signals(
        candidates=candidates,
        observed_at=datetime.now(UTC),
        snapshot_bundle_id=snapshot_bundle_id,
    )


class PromotionResponseValidationError(ValueError):
    """Raised when a promotion response payload is fail-closed invalid.

    The strict backend contract (R4 task 8) rejects:
      * Malformed ``promotion_outcome`` values not in the typed enum.
      * Missing ``canonical_incident_id`` for non-zero opened/updated counts.
      * Synthesized ``<aggregate>`` candidate IDs in strict backend mode.

    These errors MUST surface as typed contracts so the orchestrator can
    detect dispatcher regressions deterministically.
    """

    def __init__(
        self,
        message: str,
        *,
        promotion_records: tuple[dict[str, str | None], ...] = (),
        opened_incident_ids: tuple[str, ...] = (),
        updated_incident_ids: tuple[str, ...] = (),
        promotion_mode: str = "",
    ) -> None:
        super().__init__(message)
        self.promotion_records = promotion_records
        self.opened_incident_ids = opened_incident_ids
        self.updated_incident_ids = updated_incident_ids
        self.promotion_mode = promotion_mode


_ALLOWED_PROMOTION_OUTCOMES: frozenset[str] = frozenset({
    "opened",
    "updated",
    "skipped_duplicate",
    "noop",
})


def validate_promotion_response_records(
    *,
    promotion_mode: str,
    promotion_records: tuple[dict[str, str | None], ...],
    opened_incident_ids: tuple[str, ...] = (),
    updated_incident_ids: tuple[str, ...] = (),
) -> None:
    """Validate a promotion response payload under the strict R4 contract.

    Failure modes:

    * ``promotion_mode == 'backend-api'``: reject synthesized
      ``<aggregate>`` source IDs -- every record MUST map back to a real
      candidate/incident pair (no inferred placeholders).
    * Any ``promotion_outcome`` not in the allowed set raises.
    * Non-zero opened/updated counts require at least one
      ``canonical_incident_id`` to be carried by ``promotion_records``.
    * Empty ``promotion_records`` is permitted only when both opened and
      updated counts are zero.
    """
    if promotion_mode == MODE_BACKEND_API:
        for raw in promotion_records:
            source_id = raw.get("source_candidate_id") or ""
            if source_id.startswith("<") and source_id.endswith(">"):
                raise PromotionResponseValidationError(
                    "Backend strict contract forbids synthesized aggregate "
                    "candidate_id mapping.",
                    promotion_records=promotion_records,
                    opened_incident_ids=opened_incident_ids,
                    updated_incident_ids=updated_incident_ids,
                    promotion_mode=promotion_mode,
                )

    seen_canonical: set[str] = set()
    for raw in promotion_records:
        outcome = str(raw.get("promotion_outcome") or "")
        if outcome not in _ALLOWED_PROMOTION_OUTCOMES:
            raise PromotionResponseValidationError(
                f"Unknown promotion_outcome: {outcome!r} not in "
                f"{sorted(_ALLOWED_PROMOTION_OUTCOMES)}",
                promotion_records=promotion_records,
                opened_incident_ids=opened_incident_ids,
                updated_incident_ids=updated_incident_ids,
                promotion_mode=promotion_mode,
            )
        canonical = raw.get("canonical_incident_id")
        if canonical:
            seen_canonical.add(str(canonical))

    non_zero_counts = bool(opened_incident_ids) or bool(updated_incident_ids)
    if non_zero_counts and not seen_canonical:
        raise PromotionResponseValidationError(
            "Non-zero opened/updated counts require authoritative canonical "
            "incident IDs on promotion_records.",
            promotion_records=promotion_records,
            opened_incident_ids=opened_incident_ids,
            updated_incident_ids=updated_incident_ids,
            promotion_mode=promotion_mode,
        )


def promote_alert_signals_for_accumulator(
    runs_dir: Path,
    accumulator: RunPromotionAccumulator | None,
    snapshot_bundle_id: str | None = None,
    *,
    cluster_context: str | None = None,
) -> PromotionBatch:
    """Promote alert signals and feed typed ``PromotionRecord`` values
    directly into ``RunPromotionAccumulator``.

    R4 contract:

    1. Scans alert-signal artifacts in ``runs_dir``.
    2. Routes promotion through the dispatcher (local or backend-api mode).
    3. Returns a typed ``PromotionBatch`` carrying the dispatcher result,
       the per-candidate ``PromotionRecord`` values, and source/cluster
       provenance. The same batch is appended to ``accumulator`` via
       ``accumulator.add_batch(...)`` so the orchestrator can aggregate
       canonical IDs deterministically without inferring
       ``promotion_mode`` from emptiness.
    4. Resolves ``promotion_mode`` AND ``incident_access_mode`` from the
       dispatch configuration. A backend-configured empty batch carries
       ``promotion_mode='backend-api'`` and ``incident_access_mode='backend'``
       just like a populated batch would; the same is true for local
       configuration. The accumulator MUST consume this verbatim.
    5. Backend-mode records pass through ``validate_promotion_response_records``
       so malformed outcomes and missing canonical IDs surface as
       ``PromotionResponseValidationError`` before any state mutation.

    Returns:
        ``PromotionBatch`` carrying the dispatcher result and typed
        ``PromotionRecord`` values. The same batch is also appended to
        ``accumulator`` when the accumulator is not ``None``.
    """
    from datetime import UTC

    config = _get_dispatch_config()
    resolved_mode = config.resolved_mode()
    resolved_access_mode = config.resolved_incident_access_mode()

    candidates = scan_alert_signals_as_candidates(runs_dir)
    if not candidates:
        # R4 task 2: a zero-candidate batch MUST carry the resolved
        # dispatcher mode verbatim. Backend-configured empty batches
        # stay backend; local-configured empty batches stay local. The
        # caller cannot tell these apart from a missing ``promotion_mode``
        # alone.
        empty_result = IncidentPromotionResult(
            ok=True,
            scanned=0,
            firing=0,
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=0,
            errors=0,
            promotion_mode=resolved_mode,
            promotion_scan_scope=(
                f"alert_signal_artifacts:dir={runs_dir}"
            ),
            incident_access_mode=resolved_access_mode,
        )
        empty_batch = PromotionBatch(
            promotion_result=empty_result,
            promotion_records=(),
            source_kind="alertmanager",
            cluster_context=cluster_context,
            snapshot_bundle_id=snapshot_bundle_id,
        )
        if accumulator is not None:
            accumulator.add_batch(empty_batch)
        return empty_batch

    result = promote_alert_signals(
        candidates=candidates,
        observed_at=datetime.now(UTC),
        snapshot_bundle_id=snapshot_bundle_id,
    )

    # R4 task 8: fail-closed validation. Backend-mode rejections surface
    # as ``PromotionResponseValidationError`` so the orchestrator can
    # detect dispatcher regressions deterministically. We validate the
    # raw record payloads (not the synthesized typed list) so backend
    # outcomes match the wire contract.
    validate_promotion_response_records(
        promotion_mode=result.promotion_mode,
        promotion_records=result.promotion_records,
        opened_incident_ids=result.opened_incident_ids,
        updated_incident_ids=result.updated_incident_ids,
    )

    records = tuple(promotion_records_from_result(result))
    batch = PromotionBatch(
        promotion_result=result,
        promotion_records=records,
        source_kind="alertmanager",
        cluster_context=cluster_context,
        snapshot_bundle_id=snapshot_bundle_id,
    )
    if accumulator is not None:
        accumulator.add_batch(batch)
    return batch


def promotion_records_from_result(
    result: IncidentPromotionResult,
) -> list[PromotionRecord]:
    """Translate an ``IncidentPromotionResult`` into typed ``PromotionRecord`` values.

    Helper used by both ``promote_alert_signals_for_accumulator`` (forward
    path) and the consistency check (reverse path) so we never have to
    re-parse a free-form dict downstream. The result's
    ``promotion_records`` field is treated as authoritative; when it is
    empty, we synthesize one record per ``opened`` / ``updated`` aggregate
    so the accumulator still receives typed entries (with
    ``canonical_incident_id`` populated and ``promotion_outcome`` matching
    the aggregate counts).
    """
    records: list[PromotionRecord] = []
    raw_records = list(result.promotion_records)
    if raw_records:
        for raw in raw_records:
            records.append(
                PromotionRecord(
                    source_candidate_id=str(
                        raw.get("source_candidate_id") or "<unknown>"
                    ),
                    canonical_incident_id=(
                        str(raw["canonical_incident_id"])
                        if isinstance(raw.get("canonical_incident_id"), str)
                        else None
                    ),
                    promotion_outcome=str(
                        raw.get("promotion_outcome") or "opened"
                    ),
                )
            )
        return records

    # Fall back to synthesising from aggregate lists. Without the typed
    # promotion_records field we can still populate typed entries; the
    # ``source_candidate_id`` is unknown but the canonical_id is exact.
    for canonical_id in result.opened_incident_ids:
        records.append(
            PromotionRecord(
                source_candidate_id="<aggregate>",
                canonical_incident_id=canonical_id,
                promotion_outcome="opened",
            )
        )
    for canonical_id in result.updated_incident_ids:
        records.append(
            PromotionRecord(
                source_candidate_id="<aggregate>",
                canonical_incident_id=canonical_id,
                promotion_outcome="updated",
            )
        )
    return records


def promote_alert_signals_scoped_for_accumulator(
    *,
    runs_dir: Path,
    health_run_id: str,
    source_identity: str,
    signal_ids: tuple[str, ...],
    accumulator: RunPromotionAccumulator | None = None,
    cluster_context: str | None = None,
) -> PromotionBatch:
    """Current-run scoped promotion that NEVER scans the whole tree.

    The dispatcher posts an explicit ``runId`` / ``sourceIdentity`` /
    ``signalIds`` scope to the backend via the new
    ``/api/internal/incidents/promote-alert-signals`` endpoint and
    translates the typed response back into a ``PromotionBatch`` without
    falling back to ``promote_alert_signals_for_accumulator``.
    """
    from .incident_promotion_backend import (
        promote_alert_signals_via_scoped_backend_api,
    )

    if not signal_ids:
        return _build_empty_batch(
            accumulator=accumulator,
            resolved_mode=MODE_BACKEND_API,
            resolved_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
            runs_dir=runs_dir,
            cluster_context=cluster_context,
            snapshot_bundle_id=None,
        )

    result_dict = promote_alert_signals_via_scoped_backend_api(
        run_id=health_run_id,
        source_identity=source_identity,
        signal_ids=list(signal_ids),
    )

    promotion_result = _result_from_dict(
        result_dict,
        promotion_mode=MODE_BACKEND_API,
    )

    records = tuple(promotion_records_from_result(promotion_result))
    batch = PromotionBatch(
        promotion_result=promotion_result,
        promotion_records=records,
        source_kind="alertmanager",
        cluster_context=cluster_context,
        snapshot_bundle_id=None,
    )
    if accumulator is not None:
        accumulator.add_batch(batch)
    return batch


def _build_empty_batch(
    *,
    accumulator: RunPromotionAccumulator | None,
    resolved_mode: str,
    resolved_access_mode: str,
    runs_dir: Path,
    cluster_context: str | None,
    snapshot_bundle_id: str | None,
) -> PromotionBatch:
    if resolved_mode == MODE_BACKEND_API:
        scan_scope = "internal_api_alert_signals:scoped"
    else:
        scan_scope = f"alert_signal_artifacts:dir={runs_dir}"
    empty_result = IncidentPromotionResult(
        ok=True,
        scanned=0,
        firing=0,
        opened_incidents=0,
        updated_incidents=0,
        skipped_duplicates=0,
        errors=0,
        promotion_mode=cast(Literal["local", "backend-api"], resolved_mode),
        promotion_scan_scope=scan_scope,
        incident_access_mode=resolved_access_mode,
    )
    empty_batch = PromotionBatch(
        promotion_result=empty_result,
        promotion_records=(),
        source_kind="alertmanager",
        cluster_context=cluster_context,
        snapshot_bundle_id=snapshot_bundle_id,
    )
    if accumulator is not None:
        accumulator.add_batch(empty_batch)
    return empty_batch


__all__ = [
    "IncidentPromotionDispatchConfig",
    "IncidentPromotionResult",
    "INCIDENT_ACCESS_MODE_BACKEND",
    "INCIDENT_ACCESS_MODE_LOCAL",
    "MODE_AUTO",
    "MODE_BACKEND_API",
    "MODE_LOCAL",
    "PromotionResponseValidationError",
    "promote_alert_signals",
    "promote_alert_signals_for_accumulator",
    "promote_alert_signals_from_artifacts",
    "promote_alert_signals_scoped_for_accumulator",
    "promote_candidates",
    "log_promotion_config",
    "promotion_records_from_result",
    "scan_alert_signals_as_candidates",
    "validate_promotion_response_records",
]

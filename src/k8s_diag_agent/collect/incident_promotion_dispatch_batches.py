"""Empty / no-work batch construction and alert-signal scanning.

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

This module owns the SINGLE canonical entry point for:

* empty / no-work :class:`PromotionBatch` construction (preserves
  distinct states for ``local zero candidates``,
  ``backend/scoped aggregate successful zero``,
  ``configuration rejection``, ``commit-unknown result``, and
  ``definite rejection``);
* :func:`scan_alert_signals_as_candidates` -- convert persisted
  alert-signal artifacts into :class:`IncidentCandidate` values;
* :func:`promotion_records_from_result` -- convert the typed
  result into :class:`PromotionRecord` values;
* :func:`promote_alert_signals_for_accumulator` -- the
  accumulator-bound legacy dispatch that hands a typed
  :class:`PromotionBatch` to the accumulator.

The active typed scoped dispatch lives in
:mod:`incident_promotion_dispatch_scoped`; this module only
handles the legacy non-scoped path and the alert-signal scanning
utilities.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from .incident_candidates import CandidateSignal, IncidentCandidate
from .incident_identity_hardening import PromotionRecord
from .incident_promotion_accumulator import RunPromotionAccumulator
from .incident_promotion_batch import PromotionBatch
from .incident_promotion_dispatch_config import _get_dispatch_config
from .incident_promotion_dispatch_validation import (
    validate_promotion_response_records,
)
from .incident_promotion_result_contract import (
    IncidentPromotionResult,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alert-signal scanning
# ---------------------------------------------------------------------------


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
            correlation_key = build_alert_incident_correlation_key(
                signal, classification
            )
            if correlation_key in seen_keys:
                continue
            seen_keys.add(correlation_key)

            # Build candidate
            candidate_class = _map_alert_class_to_candidate_class(
                classification.class_
            )
            severity = _map_severity(signal.severity)
            object_kind = _map_entity_kind_to_object_kind(
                classification.entity_kind
            )

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
            _logger.exception(
                "Error scanning alert signal artifact %s", artifact.identity
            )

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
    candidates = scan_alert_signals_as_candidates(runs_dir)
    if not candidates:
        return IncidentPromotionResult(
            ok=True,
            scanned=0,
            firing=0,
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=0,
            errors=0,
        )
    # Local import to avoid circular dependency between the façade
    # and the batch utilities.
    from .incident_promotion_dispatch import promote_alert_signals

    return promote_alert_signals(
        candidates=candidates,
        observed_at=datetime.now(UTC),
        snapshot_bundle_id=snapshot_bundle_id,
    )


# ---------------------------------------------------------------------------
# Records translation
# ---------------------------------------------------------------------------


def promotion_records_from_result(
    result: IncidentPromotionResult,
) -> list[PromotionRecord]:
    """Translate an ``IncidentPromotionResult`` into typed ``PromotionRecord`` values.

    Helper used by both ``promote_alert_signals_for_accumulator``
    (forward path) and the consistency check (reverse path) so we
    never have to re-parse a free-form dict downstream. The result's
    ``promotion_records`` field is treated as authoritative; when it
    is empty, we synthesize one record per ``opened`` / ``updated``
    aggregate so the accumulator still receives typed entries (with
    ``canonical_incident_id`` populated and ``promotion_outcome``
    matching the aggregate counts).
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

    # Fall back to synthesising from aggregate lists. Without the
    # typed promotion_records field we can still populate typed
    # entries; the ``source_candidate_id`` is unknown but the
    # canonical_id is exact.
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


# ---------------------------------------------------------------------------
# Accumulator-bound legacy dispatch
# ---------------------------------------------------------------------------


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
       ``accumulator.add_batch(...)`` so the orchestrator can
       aggregate canonical IDs deterministically without inferring
       ``promotion_mode`` from emptiness.
    4. Resolves ``promotion_mode`` AND ``incident_access_mode`` from
       the dispatch configuration. A backend-configured empty batch
       carries ``promotion_mode='backend-api'`` and
       ``incident_access_mode='backend'`` just like a populated batch
       would; the same is true for local configuration. The
       accumulator MUST consume this verbatim.
    5. Backend-mode records pass through
       ``validate_promotion_response_records`` so malformed outcomes
       and missing canonical IDs surface as
       ``PromotionResponseValidationError`` before any state mutation.

    Returns:
        ``PromotionBatch`` carrying the dispatcher result and typed
        ``PromotionRecord`` values. The same batch is also appended
        to ``accumulator`` when the accumulator is not ``None``.
    """
    config = _get_dispatch_config()
    resolved_mode = config.resolved_mode()
    resolved_access_mode = config.resolved_incident_access_mode()

    candidates = scan_alert_signals_as_candidates(runs_dir)
    if not candidates:
        # R4 task 2: a zero-candidate batch MUST carry the resolved
        # dispatcher mode verbatim. Backend-configured empty batches
        # stay backend; local-configured empty batches stay local.
        # The caller cannot tell these apart from a missing
        # ``promotion_mode`` alone.
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

    from .incident_promotion_dispatch import promote_alert_signals

    result = promote_alert_signals(
        candidates=candidates,
        observed_at=datetime.now(UTC),
        snapshot_bundle_id=snapshot_bundle_id,
    )

    # R4 task 8: fail-closed validation. Backend-mode rejections
    # surface as ``PromotionResponseValidationError`` so the
    # orchestrator can detect dispatcher regressions deterministically.
    # We validate the raw record payloads (not the synthesized typed
    # list) so backend outcomes match the wire contract.
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


__all__ = [
    "scan_alert_signals_as_candidates",
    "promote_alert_signals_from_artifacts",
    "promotion_records_from_result",
    "promote_alert_signals_for_accumulator",
]
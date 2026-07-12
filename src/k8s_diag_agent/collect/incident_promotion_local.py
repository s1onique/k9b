"""Local incident promotion implementation.

This module provides the local promotion path for incident candidates,
used when the scheduler runs in the same process as the incident store.

R1 hardening:

* Use the typed ``promote_candidates_with_records`` boundary so the
  caller correlates ``IncidentCandidate`` -> ``PromotionRecord``
  directly, never via post-hoc ``zip(..., strict=False)``.
* Surface canonical IDs and per-candidate ``PromotionRecord`` values
  through the dispatcher's ``IncidentPromotionResult`` shape.

R4 hardening:

* Local promotion MUST call the polymorphic ``store.promote_candidates_with_records(...)``
  so SQLite-backed stores activate their durable override. The free
  helper in ``incident_store_promotion_helpers`` is reserved for the
  in-memory base implementation only; the verifier rejects production
  invocations of the free helper outside that boundary.
* The store is always obtained through
  ``incident_store_provider.get_incident_store()`` unless the caller
  pre-supplies it; the polymorphic method on the returned object is the
  only path that local promotion uses.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .incident_candidates import IncidentCandidate

_logger = logging.getLogger(__name__)


class LocalPromotionStoreContractError(RuntimeError):
    """Raised when local promotion cannot drive a polymorphic store.

    The R4 contract insists that local promotion calls the polymorphic
    ``store.promote_candidates_with_records(...)`` method. If the store
    instance does not implement that method (e.g. somebody hands us a
    test stub that only exposes the free helper), this error raises
    rather than silently falling back to ``zip`` correlation or any
    other legacy shape.
    """

    pass


def promote_local(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
    store: object | None = None,
) -> dict[str, object]:
    """Promote candidates via the local incident store.

    R4 contract: delegates to ``store.promote_candidates_with_records(...)``
    so the store polymorphic boundary is the single source of truth.
    The SQLite override at ``incident_store_sqlite.promote_candidates_with_records``
    is the only path that performs durable writes; the free helper in
    ``incident_store_promotion_helpers`` is intentionally NOT called
    from production code (it is restricted to the in-memory base
    implementation).

    Args:
        candidates: List of candidates to promote
        observed_at: When candidates were observed
        snapshot_bundle_id: Optional snapshot bundle ID
        store: Optional pre-obtained store instance. When ``None`` we
            obtain one through ``incident_store_provider``.

    Returns:
        Dict with promotion counts plus per-canonical-incident IDs and
        typed ``PromotionRecord`` values. ``opened_incident_ids`` /
        ``updated_incident_ids`` are the canonical incident IDs the store
        owns; ``promotion_records`` is the canonical
        ``source_candidate_id`` -> ``canonical_incident_id`` mapping for
        downstream canonical-id consumption.
    """
    if store is None:
        from .incident_store_provider import get_incident_store

        store = get_incident_store()

    # R4 contract: the local path MUST call the polymorphic
    # ``store.promote_candidates_with_records(...)`` so SQLite-backed
    # stores activate their durable override. We refuse to fall back to
    # the free helper; if the store doesn't expose the polymorphic
    # method, raise a typed error instead of silently regressing.
    polymorphic_promote = getattr(store, "promote_candidates_with_records", None)
    if polymorphic_promote is None or not callable(polymorphic_promote):
        raise LocalPromotionStoreContractError(
            "Store does not expose promote_candidates_with_records; "
            "local promotion requires the polymorphic method so SQLite "
            "override is invoked when present."
        )

    try:
        outcomes = polymorphic_promote(
            candidates=candidates,
            observed_at=observed_at,
            snapshot_bundle_id=snapshot_bundle_id,
        )
    except Exception as exc:
        _logger.exception("Local promotion failed")
        return {
            "ok": False,
            "scanned": len(candidates),
            "firing": len(candidates),
            "opened_incidents": 0,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 1,
            "error_messages": [str(exc)],
            "opened_incident_ids": [],
            "updated_incident_ids": [],
            "promotion_records": [],
            "unique_candidate_count": 0,
            "promotion_scan_scope": "",
            "incident_access_mode": "local",
        }

    # Aggregate per-canonical-incident statistics without resorting to
    # ``zip`` inference. Each ``PromotionOutcome`` already carries the
    # authoritative ``canonical_incident_id`` so the aggregator can
    # dedupe and tally directly.
    from .incident_promotion_accumulator import RunPromotionAccumulator

    accumulator = RunPromotionAccumulator()
    opened: list[str] = []
    updated: list[str] = []
    for outcome in outcomes:
        record = outcome.record
        accumulator.add_record(record)
        canonical_id = record.canonical_incident_id
        if canonical_id is None:
            continue
        if record.promotion_outcome == "opened":
            opened.append(canonical_id)
        elif record.promotion_outcome == "updated":
            updated.append(canonical_id)
    return {
        "ok": True,
        "scanned": len(candidates),
        "firing": len(candidates),
        "opened_incidents": len(opened),
        "updated_incidents": len(updated),
        "skipped_duplicates": 0,
        "errors": 0,
        "error_messages": [],
        "opened_incident_ids": opened,
        "updated_incident_ids": updated,
        "promotion_records": [r.to_dict() for r in accumulator.promotion_records],
        "unique_candidate_count": len(accumulator.promotion_records),
        "promotion_scan_scope": f"local_promotion:bundle={snapshot_bundle_id or 'none'}",
        "incident_access_mode": "local",
    }

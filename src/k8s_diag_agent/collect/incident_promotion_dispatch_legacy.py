"""Legacy result-conversion adapter for the dispatcher.

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

This module owns the SINGLE legacy adapter that converts a free-form
``dict`` payload into the typed
:class:`IncidentPromotionResult`.  The active scoped dispatcher
does NOT consume this adapter; it consumes
:class:`ScopedPromotionDispatchResult` directly through
:func:`scoped_dispatch_result_to_accumulator_handoff`.

This legacy adapter exists only for the legacy non-scoped local
and backend-api dispatcher paths that still publish free-form
dicts from older backend code.  A future removal of the legacy
paths MUST also remove this module.
"""

from __future__ import annotations

from typing import Any, Literal

from .incident_promotion_dispatch_config import (
    _incident_access_mode_for_promotion_mode,
)
from .incident_promotion_result_contract import IncidentPromotionResult


def _result_from_dict(
    d: dict[str, Any],
    promotion_mode: Literal["local", "backend-api"] = "local",
) -> IncidentPromotionResult:
    """Convert promotion dict to ``IncidentPromotionResult``.

    Carries the canonical incident IDs and per-candidate mapping (when
    the upstream provider exposes them) so callers can consume
    ``incident_id`` values directly without re-deriving them from
    candidate attributes.

    R2: every typed category produced by the new
    ``IncidentPromotionResult`` (observation-refreshed, unchanged,
    skipped signals, failures) is mapped from the wire/dict payload
    so the dispatcher's downstream log lines and accumulator entries
    can read the real category counts.
    """
    default_access_mode = _incident_access_mode_for_promotion_mode(
        promotion_mode
    )
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


__all__ = [
    "_result_from_dict",
]
"""Backend-api-mode dispatcher.

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

This module owns the SINGLE backend-api-mode promotion dispatcher for
the legacy alert-signal promotion path.  The backend-api path
delegates the heavy lifting to the existing
:func:`k8b_diag_agent.collect.incident_promotion_backend.promote_alert_signals_via_backend_api`
function and consumes the result through the legacy
:func:`_result_from_dict` adapter.

The active typed scoped dispatch (consumed by the accumulator)
lives in :mod:`incident_promotion_dispatch_scoped`.  This module
exists only for the legacy non-scoped backend-api path.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .incident_candidates import IncidentCandidate
from .incident_promotion_dispatch_config import (
    IncidentPromotionDispatchConfig,
)
from .incident_promotion_dispatch_legacy import _result_from_dict
from .incident_promotion_result_contract import IncidentPromotionResult

_logger = logging.getLogger(__name__)


def dispatch_backend_promotion(
    config: IncidentPromotionDispatchConfig,
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None,
) -> IncidentPromotionResult:
    """Run the backend-api-mode promotion path for alert signals.

    Returns the typed :class:`IncidentPromotionResult` from
    :func:`promote_alert_signals_via_backend_api`.
    """
    from .incident_promotion_backend import (
        promote_alert_signals_via_backend_api,
    )
    from .incident_promotion_dispatch_constants import MODE_BACKEND_API

    _logger.info(
        "Alert signal promotion via backend API",
        extra={
            "event": "alert-signals-promotion-via-backend",
            "promotion_mode": "backend-api",
            "backend_url": config.backend_url,
            "candidate_count": len(candidates),
        },
    )
    return _result_from_dict(
        promote_alert_signals_via_backend_api(
            candidates, observed_at, snapshot_bundle_id
        ),
        MODE_BACKEND_API,
    )


__all__ = [
    "dispatch_backend_promotion",
]
"""Local-mode dispatcher.

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

This module owns the SINGLE local-mode promotion dispatcher.  The
local path delegates the heavy lifting to the existing
:func:`k8s_diag_agent.collect.incident_promotion_local.promote_local`
function and consumes the result through the legacy
:func:`_result_from_dict` adapter.

The local path is rejected when ``process_role == 'scheduler'`` AND
``store_backend == 'sqlite'``.  In that configuration the dispatcher
returns a fail-closed :class:`IncidentPromotionResult` so the
orchestrator can detect the misconfiguration deterministically.
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


def dispatch_local_promotion(
    config: IncidentPromotionDispatchConfig,
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None,
) -> IncidentPromotionResult:
    """Run the local-mode promotion path.

    Returns the typed :class:`IncidentPromotionResult` from
    :func:`promote_local`.  When the local path is forbidden
    (``process_role == 'scheduler'`` AND
    ``store_backend == 'sqlite'``) the dispatcher fails closed with
    a one-error result so the orchestrator can detect the
    misconfiguration.
    """
    from .incident_promotion_dispatch_constants import MODE_LOCAL
    from .incident_promotion_local import promote_local

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

    return _result_from_dict(
        promote_local(candidates, observed_at, snapshot_bundle_id),
        MODE_LOCAL,
    )


__all__ = [
    "dispatch_local_promotion",
]
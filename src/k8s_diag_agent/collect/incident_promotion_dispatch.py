"""Incident promotion dispatcher (façade).

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

This module is the public façade for the incident promotion
dispatcher.  It exposes the stable re-export surface and the two
top-level entry points
:func:`promote_candidates` and :func:`promote_alert_signals`.  All
implementation lives in focused, single-responsibility submodules:

* :mod:`incident_promotion_dispatch_config` -- configuration +
  ``IncidentPromotionDispatchConfig`` + ``_get_dispatch_config``
* :mod:`incident_promotion_dispatch_local` -- local-mode dispatch
* :mod:`incident_promotion_dispatch_backend` -- backend-api-mode
  dispatch
* :mod:`incident_promotion_dispatch_scoped` -- active typed
  scoped dispatch (consumed by the accumulator)
* :mod:`incident_promotion_dispatch_batches` -- empty / no-work
  batch construction + alert-signal scanning
* :mod:`incident_promotion_dispatch_validation` -- strict R4
  validation contract
* :mod:`incident_promotion_dispatch_legacy` -- legacy
  ``_result_from_dict`` adapter for the non-scoped paths

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
- auto: Use backend-api if K9B_INCIDENT_STORE_BACKEND=sqlite or
  K9B_PROCESS_ROLE=scheduler
"""

from __future__ import annotations

import logging
from datetime import datetime

from .incident_candidates import IncidentCandidate
from .incident_promotion_batch import PromotionBatch  # noqa: F401
from .incident_promotion_dispatch_backend import (
    dispatch_backend_promotion,
)
from .incident_promotion_dispatch_batches import (
    promote_alert_signals_for_accumulator,
    promote_alert_signals_from_artifacts,
    promotion_records_from_result,
    scan_alert_signals_as_candidates,
)
from .incident_promotion_dispatch_config import (
    IncidentPromotionDispatchConfig,
    _get_dispatch_config,
    log_promotion_config,
)
from .incident_promotion_dispatch_constants import (
    INCIDENT_ACCESS_MODE_BACKEND,
    INCIDENT_ACCESS_MODE_LOCAL,
    MODE_AUTO,
    MODE_BACKEND_API,
    MODE_LOCAL,
)
from .incident_promotion_dispatch_local import (
    dispatch_local_promotion,
)
from .incident_promotion_dispatch_scoped import (
    promote_alert_signals_scoped_for_accumulator,
)
from .incident_promotion_dispatch_validation import (
    PromotionResponseValidationError,
    validate_promotion_response_records,
)
from .incident_promotion_result_contract import (
    IncidentPromotionResult,
)

_logger = logging.getLogger(__name__)


def promote_candidates(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> IncidentPromotionResult:
    """Promote incident candidates via configured path.

    Top-level entry point for scheduler health-loop promotion.  Routes
    to the local or backend-api dispatcher based on the resolved
    dispatch mode.
    """
    config = _get_dispatch_config()
    if config.resolved_mode() == MODE_LOCAL:
        return dispatch_local_promotion(
            config=config,
            candidates=candidates,
            observed_at=observed_at,
            snapshot_bundle_id=snapshot_bundle_id,
        )
    return dispatch_backend_promotion(
        config=config,
        candidates=candidates,
        observed_at=observed_at,
        snapshot_bundle_id=snapshot_bundle_id,
    )


def promote_alert_signals(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> IncidentPromotionResult:
    """Promote alert signal candidates via configured path.

    Top-level entry point for Alertmanager alert signal promotion.
    Routes to the local or backend-api dispatcher based on the
    resolved dispatch mode.
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
        return dispatch_local_promotion(
            config=config,
            candidates=candidates,
            observed_at=observed_at,
            snapshot_bundle_id=snapshot_bundle_id,
        )
    return dispatch_backend_promotion(
        config=config,
        candidates=candidates,
        observed_at=observed_at,
        snapshot_bundle_id=snapshot_bundle_id,
    )


__all__ = [
    # Re-exports
    "INCIDENT_ACCESS_MODE_BACKEND",
    "INCIDENT_ACCESS_MODE_LOCAL",
    "IncidentPromotionDispatchConfig",
    "IncidentPromotionResult",
    "MODE_AUTO",
    "MODE_BACKEND_API",
    "MODE_LOCAL",
    "PromotionResponseValidationError",
    # Top-level entry points
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
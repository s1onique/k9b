"""Compatibility facade for internal incident promotion handlers.

The alert-signal implementation lives in
:mod:`server_incident_internal_promotion_handlers`; the candidate implementation
lives in :mod:`server_incident_internal_promotion_candidates`. This module
intentionally preserves the historical import path for both handlers.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05-CI-SHARD-PORTABILITY-AND-PROMOTION-REGRESSION-CLOSURE01
: ``_log_promotion_result`` is re-exported here so production tests
that import the canonical owner via the historical import path
``k8s_diag_agent.ui.server_incident_internal_handlers`` see the same
single implementation owner (``server_incident_internal_promotion_handlers``)
as the production caller. The canonical owner remains
``server_incident_internal_promotion_handlers`` -- this module is a
shim, NOT a duplicate implementation, so a future second
implementation is forbidden at AST level by the
``PRIVATE_HELPER_PUBLIC_FACADE=false`` invariant.
"""

from .server_incident_internal_promotion_candidates import handle_promote_candidates
from .server_incident_internal_promotion_handlers import (
    _log_promotion_result,
    handle_promote_alert_signals,
)

__all__ = [
    "_log_promotion_result",
    "handle_promote_alert_signals",
    "handle_promote_candidates",
]

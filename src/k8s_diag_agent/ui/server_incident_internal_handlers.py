"""Compatibility facade for internal incident promotion handlers.

The alert-signal implementation lives in
:mod:`server_incident_internal_promotion_handlers`; the candidate implementation
lives in :mod:`server_incident_internal_promotion_candidates`. This module
intentionally preserves the historical import path for both handlers.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION06:

``_log_promotion_result`` is intentionally NOT re-exported here.
Tests MUST import it from the canonical owner
``k8s_diag_agent.ui.server_incident_internal_promotion_handlers``.
Re-exporting the private helper would create two public import
paths for the same implementation and contradict the typed
single-owner contract.

The canonical owner remains
``server_incident_internal_promotion_handlers``; this module is a
strict shim that does NOT surface any private helpers, so the
``PRIVATE_HELPER_PUBLIC_FACADE=false`` invariant is preserved.
"""

from .server_incident_internal_promotion_candidates import handle_promote_candidates
from .server_incident_internal_promotion_handlers import (
    handle_promote_alert_signals,
)

__all__ = [
    "handle_promote_alert_signals",
    "handle_promote_candidates",
]

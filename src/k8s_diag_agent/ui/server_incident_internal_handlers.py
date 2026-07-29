"""Compatibility facade for internal incident promotion handlers.

The alert-signal implementation lives in
:mod:`server_incident_internal_promotion_handlers`; the candidate implementation
lives in :mod:`server_incident_internal_promotion_candidates`. This module
intentionally preserves the historical import path for both handlers.
"""

from .server_incident_internal_promotion_candidates import handle_promote_candidates
from .server_incident_internal_promotion_handlers import handle_promote_alert_signals

__all__ = [
    "handle_promote_alert_signals",
    "handle_promote_candidates",
]

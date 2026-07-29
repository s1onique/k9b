"""Compatibility facade for internal incident promotion handlers.

The implementations live in :mod:`server_incident_internal_promotion_handlers`;
this module intentionally preserves the historical import path.
"""

from .server_incident_internal_promotion_candidates import handle_promote_candidates
from .server_incident_internal_promotion_handlers import handle_promote_alert_signals

__all__ = [
    "handle_promote_alert_signals",
    "handle_promote_candidates",
]

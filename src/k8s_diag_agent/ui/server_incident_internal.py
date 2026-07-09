"""Internal API handlers for scheduler/backend incident promotion boundary.

This module provides internal endpoints for the scheduler to submit incident
promotion requests to the backend, which owns the SQLite store.

Security:
- All internal endpoints require bearer token authentication
- Token is configured via K9B_INTERNAL_API_TOKEN environment variable
- Tokens are NOT logged
- Endpoints are fail-closed (reject if token is missing when required)

Hard constraints:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation

This module re-exports the split components for backward compatibility.
"""

from __future__ import annotations

from .server_incident_internal_auth import (
    ENV_INTERNAL_API_TOKEN,
    _get_internal_api_token,
    _validate_internal_token,
)
from .server_incident_internal_client import (
    SchedulerClient,
    create_scheduler_client,
)
from .server_incident_internal_handlers import (
    handle_promote_alert_signals,
    handle_promote_candidates,
)
from .server_incident_internal_models import (
    PromoteAlertSignalsRequest,
    PromoteCandidatesRequest,
    PromotionResponse,
)
from .server_incident_internal_read_handlers import (
    handle_get_incident,
    handle_list_incidents,
)

__all__ = [
    # Models
    "PromotionResponse",
    "PromoteAlertSignalsRequest",
    "PromoteCandidatesRequest",
    # Authentication
    "ENV_INTERNAL_API_TOKEN",
    "_validate_internal_token",
    "_get_internal_api_token",
    # Handlers
    "handle_get_incident",
    "handle_list_incidents",
    "handle_promote_alert_signals",
    "handle_promote_candidates",
    # Client
    "SchedulerClient",
    "create_scheduler_client",
]

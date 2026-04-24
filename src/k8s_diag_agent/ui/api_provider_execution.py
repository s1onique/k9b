"""Provider-execution serialization functions for the operator UI.

This module contains serializer functions for provider-execution-related payloads:
- Provider execution summary payload
- Provider execution branch payload

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from .api_payloads import (
    ProviderExecutionBranchPayload,
    ProviderExecutionPayload,
)
from .model import (
    ProviderExecutionBranchView,
    ProviderExecutionView,
)


def _serialize_provider_execution(view: ProviderExecutionView | None) -> ProviderExecutionPayload | None:
    """Serialize provider execution view to payload dict."""
    if not view:
        return None
    payload: ProviderExecutionPayload = {}
    if view.auto_drilldown:
        payload["autoDrilldown"] = _serialize_provider_execution_branch(view.auto_drilldown)
    if view.review_enrichment:
        payload["reviewEnrichment"] = _serialize_provider_execution_branch(view.review_enrichment)
    return payload or None


def _serialize_provider_execution_branch(
    branch: ProviderExecutionBranchView,
) -> ProviderExecutionBranchPayload:
    """Serialize provider execution branch view to payload dict."""
    return {
        "enabled": branch.enabled,
        "provider": branch.provider,
        "maxPerRun": branch.max_per_run,
        "eligible": branch.eligible,
        "attempted": branch.attempted,
        "succeeded": branch.succeeded,
        "failed": branch.failed,
        "skipped": branch.skipped,
        "unattempted": branch.unattempted,
        "budgetLimited": branch.budget_limited,
        "notes": branch.notes,
    }

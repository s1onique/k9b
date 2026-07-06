"""Read-only API handlers for incident store.

This module provides read-only access to the in-memory IncidentStore.
It exposes:
- GET /api/incidents - list all incidents with optional status filter
- GET /api/incidents/{incident_id} - get a specific incident

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only)

Uses api_incident_reads serializers for typed payloads.

Optional content index support:
- When K9B_CONTENT_INDEX_ENABLED=true, attempts to read from the SQLite
  content index first.
- Falls back to direct incident store read if index is unavailable,
  missing, or stale.
- Fallback is transparent to callers and emits OTel span attributes.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from ..content_index import (
    ContentIndexConfig,
    load_content_index_config_from_env,
)
from ..content_index.readpath import (
    FallbackReason as ReadpathFallbackReason,
)
from ..content_index.readpath import (
    get_incident_from_index,
    list_incidents_from_index,
    record_fallback_span,
    record_success_span,
)
from ..content_index.readpath_projection import (
    safe_index_detail_to_api_payload,
    safe_index_summary_to_api_payload,
)
from ..observability import (
    trace_incident_store_get,
    trace_incident_store_list,
)
from ..ui.api_incident_reads import (
    build_incident_detail_payload,
    build_incident_summary_payload,
)
from ..ui.api_payloads import IncidentDetailPayload, IncidentSummaryPayload
from .incident_lifecycle import Incident, IncidentStatus
from .incident_next_check_artifacts import load_next_check_plan_payloads_for_incident
from .incident_store_provider import get_incident_store

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

# Lazy-loaded content index config (loaded once per module import)
_content_index_config: ContentIndexConfig | None = None


def _get_content_index_config() -> ContentIndexConfig:
    """Get or create the content index configuration.

    Uses lazy loading to avoid importing content_index modules unless needed.
    """
    global _content_index_config
    if _content_index_config is None:
        _content_index_config = load_content_index_config_from_env()
    return _content_index_config


def handle_list_incidents(
    status: str | None = None,
) -> dict[str, list[IncidentSummaryPayload] | int]:
    """List incidents from the in-memory store.

    When content index is enabled and available, this first attempts to read
    from the index. Falls back to direct incident store read on any index failure.

    Args:
        status: Optional status filter (e.g., "open", "collecting_evidence")

    Returns:
        Dict with "incidents" list and "total" count
    """
    # Try content index first if enabled
    config = _get_content_index_config()
    if config.enabled:
        index_result = list_incidents_from_index(config)
        if index_result.index_available and index_result.data is not None:
            # Success from index - convert projections to API payloads
            record_success_span(
                "k9b.content_index.project_response",
                enabled=True,
                schema_version=index_result.schema_version or "unknown",
                count=index_result.count,
            )
            # Convert raw projections to typed API payloads
            raw_incidents = index_result.data.get("incidents", [])
            api_incidents: list[IncidentSummaryPayload] = []
            for raw_incident in raw_incidents:
                api_incident = safe_index_summary_to_api_payload(
                    raw_incident,
                    ReadpathFallbackReason.PROJECTION_ERROR,
                )
                if api_incident is not None:
                    api_incidents.append(api_incident)
                else:
                    # Malformed projection - fall back to direct read
                    _logger.debug(
                        "Malformed summary projection, falling back to direct read"
                    )
                    record_fallback_span(
                        "k9b.content_index.fallback",
                        reason=ReadpathFallbackReason.PROJECTION_ERROR,
                        enabled=True,
                        schema_version=index_result.schema_version,
                    )
                    # Fall through to direct read
                    return _direct_list_incidents(status)

            return {
                "incidents": api_incidents,
                "total": len(api_incidents),
            }
        else:
            # Fallback to direct read
            record_fallback_span(
                "k9b.content_index.fallback",
                reason=index_result.fallback_reason or ReadpathFallbackReason.INDEX_NOT_AVAILABLE,
                enabled=True,
                schema_version=index_result.schema_version,
            )

    # Direct incident store read (default path)
    return _direct_list_incidents(status)


def _direct_list_incidents(
    status: str | None,
) -> dict[str, list[IncidentSummaryPayload] | int]:
    """Direct incident store read for list operations.

    Args:
        status: Optional status filter.

    Returns:
        Dict with "incidents" list and "total" count.
    """
    store = get_incident_store()

    # Parse status filter if provided
    status_filter: IncidentStatus | None = None
    if status is not None:
        try:
            status_filter = IncidentStatus(status)
        except ValueError:
            # Invalid status value - return empty list
            return {"incidents": [], "total": 0}

    def _list_incidents() -> tuple:
        return store.list_incidents(status=status_filter)

    incidents = trace_incident_store_list(
        _list_incidents,
        attributes={"k9b.item.kind": "incident"},
    )

    def _project_incidents() -> list:
        return [build_incident_summary_payload(inc) for inc in incidents]

    projected = trace_incident_store_list(
        _project_incidents,
        attributes={"k9b.projection_kind": "incident_summary"},
    )

    return {
        "incidents": projected,
        "total": len(incidents),
    }


def handle_get_incident(
    incident_id: str,
    external_analysis_dir: Path | None = None,
) -> IncidentDetailPayload | None:
    """Get a specific incident by ID.

    When content index is enabled and available, this first attempts to read
    from the index. Falls back to direct incident store read on any index failure.

    Note: The content index provides only the core incident fields. When
    external_analysis_dir is provided, the direct read path populates additional
    fields like suggested_checks and automatic_diagnosis_review from artifacts.
    The index path does NOT populate these fields.

    Args:
        incident_id: The incident ID to look up
        external_analysis_dir: Optional path to external-analysis directory
            for loading:
            - Next-check plan artifacts to populate suggested_checks
            - Automatic diagnosis review packet summaries

    Returns:
        Incident detail dict if found, None if not found

    Note:
        When external_analysis_dir is None, suggested_checks will be empty
        and automatic_diagnosis_review will indicate no packet available.
        When provided, both fields are populated from linked artifacts.
        Missing or malformed artifacts do not cause errors - they are skipped.
    """
    # Try content index first if enabled
    # Note: Index doesn't have suggested_checks or automatic_diagnosis_review fields
    config = _get_content_index_config()
    if config.enabled:
        index_result = get_incident_from_index(config, incident_id)
        if index_result.index_available:
            if index_result.data is not None:
                # Success from index - convert projection to API payload
                record_success_span(
                    "k9b.content_index.project_response",
                    enabled=True,
                    schema_version=index_result.schema_version or "unknown",
                    count=index_result.count,
                )
                # Convert raw projection to typed API payload
                api_incident = safe_index_detail_to_api_payload(
                    index_result.data,
                    ReadpathFallbackReason.PROJECTION_ERROR,
                )
                if api_incident is not None:
                    return api_incident
                else:
                    # Malformed projection - fall back to direct read
                    _logger.debug(
                        "Malformed detail projection for %s, falling back to direct read",
                        incident_id,
                    )
                    record_fallback_span(
                        "k9b.content_index.fallback",
                        reason=ReadpathFallbackReason.PROJECTION_ERROR,
                        enabled=True,
                        schema_version=index_result.schema_version,
                    )
            else:
                # Not in index, but index is valid - try direct read
                record_fallback_span(
                    "k9b.content_index.fallback",
                    reason=ReadpathFallbackReason.INDEX_NOT_AVAILABLE,
                    enabled=True,
                    schema_version=index_result.schema_version,
                )
        else:
            # Fallback to direct read
            record_fallback_span(
                "k9b.content_index.fallback",
                reason=index_result.fallback_reason or ReadpathFallbackReason.INDEX_NOT_AVAILABLE,
                enabled=True,
                schema_version=index_result.schema_version,
            )

    # Direct incident store read (default path or when extras needed)
    return _direct_get_incident(incident_id, external_analysis_dir)


def _direct_get_incident(
    incident_id: str,
    external_analysis_dir: Path | None,
) -> IncidentDetailPayload | None:
    """Direct incident store read for get operations.

    Args:
        incident_id: The incident ID to look up.
        external_analysis_dir: Optional path to external-analysis directory.

    Returns:
        IncidentDetailPayload if found, None otherwise.
    """
    store = get_incident_store()

    def _get_incident() -> Incident | None:
        return store.get_incident(incident_id)

    incident = trace_incident_store_get(
        _get_incident,
        attributes={"k9b.item.kind": "incident"},
    )

    if incident is None:
        return None

    # Load next-check plan payloads if external_analysis_dir is available
    plan_payloads: tuple[Mapping[str, object], ...] = ()
    if external_analysis_dir is not None:
        plan_payloads = load_next_check_plan_payloads_for_incident(
            incident,
            external_analysis_dir,
        )

    def _build_payload() -> IncidentDetailPayload:
        return build_incident_detail_payload(
            incident,
            external_analysis_dir=external_analysis_dir,
            next_check_plan_payloads=plan_payloads,
        )

    return cast(
        IncidentDetailPayload | None,
        trace_incident_store_get(
            _build_payload,
            attributes={"k9b.projection_kind": "incident_detail"},
        ),
    )


__all__ = [
    "handle_list_incidents",
    "handle_get_incident",
]

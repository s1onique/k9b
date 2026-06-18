"""Read-only incident case-file packet builder for LLM-assisted diagnosis.

This module provides a deterministic, bounded, read-only incident case-file packet
that assembles the trustworthy context needed for future LLM-assisted incident diagnosis.

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic ordering with bounded counts
- Explicit safety metadata

The packet is structured for:
- Operator review (human-readable)
- LLM prompting (structured, bounded)
- Audit trail (immutable timestamps)
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ..ui.api_incident_reads import build_incident_detail_payload
from ..ui.incident_suggested_checks import build_suggested_checks_from_next_check_plan_payload
from .incident_next_check_artifacts import load_next_check_plan_payloads_for_incident
from .incident_store_provider import get_incident_store

if TYPE_CHECKING:
    pass

# Packet schema version for tracking structure evolution
PACKET_SCHEMA_VERSION = "1.0"

# Disallowed actions for safety boundary
DISALLOWED_ACTIONS: list[str] = [
    "execute",
    "promote",
    "apply",
    "remediate",
    "delete",
    "mutate_cluster",
]

# Bounded limits for safety
DEFAULT_MAX_SIGNALS = 20
DEFAULT_MAX_EVENTS = 50
DEFAULT_MAX_SUGGESTED_CHECKS = 20

__all__ = [
    "build_incident_case_file",
    "PACKET_SCHEMA_VERSION",
    "DISALLOWED_ACTIONS",
]


# =============================================================================
# Public API
# =============================================================================


def build_incident_case_file(
    incident_id: str,
    *,
    external_analysis_dir: Path | None = None,
    now: datetime | None = None,
    max_signals: int = DEFAULT_MAX_SIGNALS,
    max_events: int = DEFAULT_MAX_EVENTS,
    max_suggested_checks: int = DEFAULT_MAX_SUGGESTED_CHECKS,
) -> dict[str, object] | None:
    """Build a read-only incident case-file packet for LLM-assisted diagnosis.

    This function assembles a deterministic, bounded, read-only packet containing:
    - Incident identity and status
    - Incident signals with run_ids
    - Linked evidence/artifacts (safe references only)
    - Suggested checks from safe next-check plan artifacts
    - Timeline/events (bounded count)
    - Safety boundary metadata

    Args:
        incident_id: The incident ID to build case-file for
        external_analysis_dir: Optional path to external-analysis directory
            for loading next-check plan artifacts
        now: Optional datetime for packet generation timestamp.
            If None, uses current time. Provided for deterministic testing.
        max_signals: Maximum number of signals to include (default 20)
        max_events: Maximum number of timeline events to include (default 50)
        max_suggested_checks: Maximum number of suggested checks (default 20)

    Returns:
        Case-file packet dict if incident found, None otherwise.
        Returns None for unknown incidents (consistent with nearby code).

    Read-only guarantee:
        This function only reads from the incident store and loads artifacts.
        It does not mutate the incident, store, or artifacts.

    Safety boundary:
        The packet always includes:
        - read_only: true
        - allowed_actions: []
        - disallowed_actions: [execute, promote, apply, remediate, delete, mutate_cluster]
    """
    # Use provided now or current time (timezone-aware UTC)
    generated_at = now if now is not None else datetime.now(UTC)

    # Fetch incident from store (read-only)
    store = get_incident_store()
    incident = store.get_incident(incident_id)

    if incident is None:
        return None

    # Load next-check plan payloads if external_analysis_dir is available
    plan_payloads: tuple[Mapping[str, object], ...] = ()
    if external_analysis_dir is not None:
        plan_payloads = load_next_check_plan_payloads_for_incident(
            incident,
            external_analysis_dir,
        )

    # Build base detail payload (includes signals, events, evidence links)
    detail_payload = build_incident_detail_payload(incident, next_check_plan_payloads=plan_payloads)

    # Extract and bound suggested checks
    suggested_checks = _build_bounded_suggested_checks(
        incident_id=incident_id,
        plan_payloads=plan_payloads,
        max_suggested_checks=max_suggested_checks,
    )

    # Build timeline (bounded)
    # Cast needed because TypedDicts have structural typing incompatible with dict[str, object]
    events = _build_bounded_timeline(
        events=cast("list[dict[str, object]]", detail_payload.get("events", [])),
        max_events=max_events,
    )

    # Build signals (bounded)
    signals = _build_bounded_signals(
        signals=cast("list[dict[str, object]]", detail_payload.get("signals", [])),
        max_signals=max_signals,
    )

    # Build the case-file packet
    packet: dict[str, object] = {
        # Schema version for tracking structure evolution
        "schema_version": PACKET_SCHEMA_VERSION,
        # Generation timestamp (deterministic for tests)
        "generated_at": generated_at.isoformat(),
        # Safety boundary - explicit read-only contract
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": list(DISALLOWED_ACTIONS),
        # Incident identity
        "incident": {
            "incident_id": detail_payload["incident_id"],
            "namespace": detail_payload["namespace"],
            "object_kind": detail_payload["object_kind"],
            "object_name": detail_payload["object_name"],
            "raw_object_kind": detail_payload.get("raw_object_kind"),
            "candidate_class": detail_payload.get("candidate_class"),
            "severity": detail_payload["severity"],
            "status": detail_payload["status"],
            "first_observed_at": detail_payload["first_observed_at"],
            "last_observed_at": detail_payload["last_observed_at"],
        },
        # Signals (bounded)
        "signals": signals,
        # Evidence links (safe artifact references only)
        "evidence_links": detail_payload.get("evidence_links", []),
        # Timeline events (bounded)
        "events": events,
        # Suggested checks from safe linked artifacts (bounded)
        "suggested_checks": suggested_checks,
    }

    return packet


# =============================================================================
# Internal Bounded Helpers
# =============================================================================


def _build_bounded_signals(
    signals: list[dict[str, object]],
    max_signals: int,
) -> list[dict[str, object]]:
    """Bound and order signals deterministically.

    Takes first max_signals signals.
    Signals are already ordered by occurrence in the incident.

    Args:
        signals: List of signal payloads
        max_signals: Maximum number to include

    Returns:
        Bounded signals list
    """
    return signals[:max_signals]


def _build_bounded_timeline(
    events: list[dict[str, object]],
    max_events: int,
) -> list[dict[str, object]]:
    """Bound and order timeline events deterministically.

    Takes first max_events events (already sorted by occurred_at in incident model).

    Args:
        events: List of event payloads
        max_events: Maximum number to include

    Returns:
        Bounded events list
    """
    return events[:max_events]


def _build_bounded_suggested_checks(
    incident_id: str,
    plan_payloads: tuple[Mapping[str, object], ...],
    max_suggested_checks: int,
) -> list[dict[str, Any]]:
    """Build bounded suggested checks from plan payloads.

    Extracts checks from each payload, applies bounds, preserves order.

    Args:
        incident_id: The incident ID to match against
        plan_payloads: Pre-loaded next-check plan payloads
        max_suggested_checks: Maximum number to include

    Returns:
        Bounded suggested checks list
    """
    all_checks: list[dict[str, Any]] = []

    for plan_payload in plan_payloads:
        # Cast needed because IncidentSuggestedCheckPayload is TypedDict, not dict
        checks = cast(
            "list[dict[str, Any]]",
            build_suggested_checks_from_next_check_plan_payload(incident_id, plan_payload),
        )
        all_checks.extend(checks)

    return all_checks[:max_suggested_checks]

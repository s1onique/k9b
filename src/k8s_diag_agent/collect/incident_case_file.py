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

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ..ui.api_incident_reads import build_incident_detail_payload
from ..ui.incident_suggested_checks import build_suggested_checks_from_next_check_plan_payload
from .incident_diagnosis_loop_pass_artifacts import (
    load_diagnosis_loop_pass_artifacts_for_incident,
)
from .incident_next_check_artifacts import load_next_check_plan_payloads_for_incident
from .incident_prior_analysis import load_prior_analysis_for_incident
from .incident_read_only_check_artifacts import (
    load_read_only_check_result_artifacts_for_incident,
)
from .incident_scheduling_root_cause import (
    extract_scheduling_root_cause,
)
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
DEFAULT_MAX_PRIOR_ANALYSIS = 10
DEFAULT_MAX_READ_ONLY_CHECK_RESULTS = 10
DEFAULT_MAX_DIAGNOSIS_LOOP_PASSES = 10

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
    max_prior_analysis: int = DEFAULT_MAX_PRIOR_ANALYSIS,
    read_only_check_result_run_ids: Sequence[str] | None = None,
    diagnosis_loop_pass_run_ids: Sequence[str] | None = None,
) -> dict[str, object] | None:
    """Build a read-only incident case-file packet for LLM-assisted diagnosis.

    This function assembles a deterministic, bounded, read-only packet containing:
    - Incident identity and status
    - Incident signals with run_ids
    - Linked evidence/artifacts (safe references only)
    - Suggested checks from safe next-check plan artifacts
    - Prior analysis from linked analysis artifacts (bounded)
    - Diagnosis loop passes from loop-pass artifacts (bounded)
    - Timeline/events (bounded count)
    - Safety boundary metadata

    Args:
        incident_id: The incident ID to build case-file for
        external_analysis_dir: Optional path to external-analysis directory
            for loading next-check plan artifacts and prior analysis
        now: Optional datetime for packet generation timestamp.
            If None, uses current time. Provided for deterministic testing.
        max_signals: Maximum number of signals to include (default 20)
        max_events: Maximum number of timeline events to include (default 50)
        max_suggested_checks: Maximum number of suggested checks (default 20)
        max_prior_analysis: Maximum number of prior analysis entries (default 10)
        read_only_check_result_run_ids: Optional explicit list of run_ids to load
            read-only check result artifacts for. These are validated with
            is_safe_run_id() and checked for incident_id match. Use this to include
            artifacts written in the current orchestrator pass that may not yet be
            linked from incident signals.
        diagnosis_loop_pass_run_ids: Optional explicit list of run_ids to load
            diagnosis loop pass artifacts for. These are validated with
            is_safe_run_id() and checked for incident_id match. Use this to include
            artifacts written in the current orchestrator pass.

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
        - prior_analysis entries contain no action-control fields
        - diagnosis_loop_passes entries contain no action-control fields
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

    # Load prior analysis if external_analysis_dir is available
    prior_analysis: list[dict[str, object]] = []
    if external_analysis_dir is not None:
        prior_analysis = load_prior_analysis_for_incident(
            incident,
            external_analysis_dir,
            max_items=max_prior_analysis,
        )

    # Load read-only check results if external_analysis_dir is available
    read_only_check_results: list[dict[str, object]] = []
    if external_analysis_dir is not None:
        read_only_check_results = load_read_only_check_result_artifacts_for_incident(
            incident,
            external_analysis_dir,
            max_artifacts=DEFAULT_MAX_READ_ONLY_CHECK_RESULTS,
            explicit_run_ids=read_only_check_result_run_ids,
        )

    # Load diagnosis loop pass artifacts if external_analysis_dir is available
    diagnosis_loop_passes: list[dict[str, object]] = []
    if external_analysis_dir is not None:
        diagnosis_loop_passes = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,
            external_analysis_dir,
            max_artifacts=DEFAULT_MAX_DIAGNOSIS_LOOP_PASSES,
            explicit_run_ids=diagnosis_loop_pass_run_ids,
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
        # Prior analysis from linked artifacts (bounded, clearly labeled as model context)
        "prior_analysis": prior_analysis,
        # Read-only check results from fake runner artifacts (bounded, labeled as fake)
        # Note: These are fake runner outputs until real collectors are wired.
        # Treat as bounded diagnostic evidence, not remediation instructions.
        "read_only_check_results": read_only_check_results,
        # Diagnosis loop passes from loop-pass artifacts (bounded, labeled as deterministic)
        # Note: These are deterministic one-pass loop results, not model output.
        # Treat as bounded diagnostic evidence breadcrumbs, not new evidence by itself.
        "diagnosis_loop_passes": diagnosis_loop_passes,
    }

    # P4C SCHEDULING ROOT-CAUSE: Extract and include scheduling evidence in the packet.
    # This ensures scheduling root-cause is deterministic and durable across evidence boundaries.
    # The scheduling evidence is extracted from incident + case file and included in the packet
    # for downstream consumers (LLM diagnosis, review packet, P4c outcome validation).
    # Note: extract_scheduling_root_cause() handles both dict and object types via _get_field().
    scheduling_evidence = extract_scheduling_root_cause(
        incident=incident,  # Pass Incident object directly - _get_field handles both types
        case_file=packet,
    )
    if scheduling_evidence.root_cause_summary:
        packet["scheduling_evidence"] = scheduling_evidence.to_dict()

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

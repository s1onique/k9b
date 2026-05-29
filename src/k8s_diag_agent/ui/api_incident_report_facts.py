"""Incident report cross-cluster and vmalert payload builders.

This module contains the payload builders for cross-cluster findings and
vmalert discovery/rule-state context sections.

Extracted from api_incident_report.py to keep that module below 500 lines.
These builders are re-exported from api_incident_report.py for backward compatibility.

Truthfulness rules enforced by the builders:
- Facts are deterministic/evidence-backed only.
- Inferences are explicitly labeled as inferences.
- Unknowns/missing evidence are explicit.
- Provider-assisted content is never classified as deterministic fact.
- Source artifact refs are preserved where available; absent provenance is left
  empty/unknown rather than fabricated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..security.kubectl_context import sanitize_operator_text
from .api_incident_report_worklist_state import _sanitize_target_cluster
from .api_payloads import (
    CrossClusterFindingPayload,
    VmalertDiscoveryContextPayload,
    VmalertRuleStateContextPayload,
    VmalertSourceSummaryPayload,
)

if TYPE_CHECKING:
    from .model import UIIndexContext

# Re-export claim builder functions from api_incident_report_claims for backward compatibility
from .api_incident_report_claims import (  # noqa: F401
    _build_assessment_derived_claims,
    _build_finding_facts,
    _build_inference_claims,
    _build_recommendation_claims,
    _build_unknown_claims,
    _deduplicate_refs,
    _derive_fleet_aware_checks,
    _filter_refs_preserving_minimum,
)


def _build_cross_cluster_findings_payload(
    context: UIIndexContext,
) -> list[CrossClusterFindingPayload] | None:
    """Build cross-cluster findings from comparison trigger artifacts.

    Cross-cluster findings represent fleet-level drift patterns that involve
    multiple clusters. They are distinct from per-cluster observations and
    surface drift that individual cluster assessments may miss.

    Taxonomy mapping:
    - observed claims: deterministic drift signals (e.g., helm release diff count)
    - hypothesis claims: speculative explanations of why drift exists
    - unknown claims: missing fleet context

    Args:
        context: UI index context containing run data with comparison triggers.

    Returns:
        List of CrossClusterFindingPayload or None if no triggers exist.
    """
    # Load comparison triggers from notification_history
    # suspicious-comparison notifications contain trigger_reasons and comparison_summary
    # Note: notification.details is a tuple of (label, value) tuples, not a dict
    raw_triggers: list[dict[str, object]] = []
    for notification in context.notification_history:
        if notification.kind == "suspicious-comparison":
            # Convert tuple of tuples to dict for easier access
            details_dict: dict[str, str] = {}
            for label, value in notification.details:
                details_dict[label] = value

            # Parse trigger_reasons from string representation
            reasons_str = details_dict.get("reasons", "[]")
            trigger_reasons: list[str] = []
            if reasons_str.startswith("[") and reasons_str.endswith("]"):
                try:
                    import ast
                    trigger_reasons = ast.literal_eval(reasons_str)
                    if not isinstance(trigger_reasons, list):
                        trigger_reasons = []
                except (ValueError, SyntaxError):
                    trigger_reasons = []

            # Parse comparison_summary/differences from string representation
            differences_str = details_dict.get("differences", "{}")
            comparison_summary: dict[str, int] = {}
            if differences_str.startswith("{") and differences_str.endswith("}"):
                try:
                    import ast
                    parsed = ast.literal_eval(differences_str)
                    if isinstance(parsed, dict):
                        for k, v in parsed.items():
                            if isinstance(v, (int, float)):
                                comparison_summary[str(k)] = int(v)
                except (ValueError, SyntaxError):
                    pass

            trigger: dict[str, object] = {
                "primary_label": notification.cluster_label or "",
                "secondary_label": details_dict.get("secondary_cluster", ""),
                "trigger_reasons": trigger_reasons,
                "comparison_summary": comparison_summary,
                "comparison_intent": details_dict.get("intent", "suspicious-drift"),
                "artifact_path": notification.artifact_path,
                "timestamp": notification.timestamp,
            }
            raw_triggers.append(trigger)

    if not raw_triggers:
        return None

    findings: list[CrossClusterFindingPayload] = []
    for trigger_raw in raw_triggers:
        if not isinstance(trigger_raw, dict):
            continue

        # Sanitize cluster labels for operator-facing display
        primary = _sanitize_target_cluster(str(trigger_raw.get("primary_label", "")))
        secondary = _sanitize_target_cluster(str(trigger_raw.get("secondary_label", "")))

        # Skip if either cluster label is an internal marker only
        if not primary and not secondary:
            continue

        # Parse drift counts from comparison_summary
        comparison_summary_raw = trigger_raw.get("comparison_summary") or {}
        drift_counts: dict[str, int] = {}
        if isinstance(comparison_summary_raw, dict):
            for key, value in comparison_summary_raw.items():
                if isinstance(value, (int, str)):
                    drift_counts[str(key)] = int(value) if isinstance(value, int) else int(value) if str(value).isdigit() else 0

        # Parse trigger reasons - deterministic signals that fired the comparison
        trigger_reasons_raw = trigger_raw.get("trigger_reasons") or []
        parsed_trigger_reasons: list[str] = []
        if isinstance(trigger_reasons_raw, list):
            for reason in trigger_reasons_raw:
                if reason:
                    parsed_trigger_reasons.append(sanitize_operator_text(str(reason)) or str(reason))

        # Build fleet-aware recommendations based on drift categories
        recommended_next_checks = _derive_fleet_aware_checks(drift_counts, parsed_trigger_reasons)

        # Parse timestamp for provenance
        timestamp_value = trigger_raw.get("timestamp")
        timestamp_str: str | None = None
        if isinstance(timestamp_value, str):
            timestamp_str = timestamp_value

        # Parse artifact path for provenance
        artifact_path: str | None = None
        if trigger_raw.get("artifact_path"):
            artifact_path = str(trigger_raw.get("artifact_path"))

        findings.append(
            {
                "primaryCluster": primary or secondary or "unknown",
                "secondaryCluster": secondary or primary or "unknown",
                "driftCounts": drift_counts,
                "intent": str(trigger_raw.get("comparison_intent", "suspicious-drift")),
                "triggerReasons": parsed_trigger_reasons,
                "artifactPath": artifact_path,
                "timestamp": timestamp_str,
                "recommendedNextChecks": recommended_next_checks,
            }
        )

    # Sort by timestamp descending (newest first) for consistent ordering
    # and prioritize operator-salient drift first
    findings.sort(
        key=lambda f: (
            f.get("timestamp") or "",
            -sum(f.get("driftCounts", {}).values()),
        ),
        reverse=True,
    )

    # Limit to top 5 findings to keep report concise
    return findings[:5] if findings else None


def _build_vmalert_discovery_context(
    context: UIIndexContext,
) -> VmalertDiscoveryContextPayload | None:
    """Build vmalert discovery context for the incident report.

    This is a read-only, non-invasive integration: no live scraping or actions.
    vmalertSources is sourced from the UI context (artifact-backed, not re-discovered).

    Contract invariants:
    - Returns None when no vmalert sources are available (not an error)
    - source_count == 0 means quiet/no-op (not an error)
    - discovered_but_unverified sources are represented but non-fatal
    - No errors are raised for missing/discovery failures

    Args:
        context: UI index context containing vmalert sources from artifact.

    Returns:
        VmalertDiscoveryContextPayload or None if no sources available.
    """
    vmalert_sources = context.vmalert_sources
    if vmalert_sources is None:
        return None

    # Build compact source summaries for diagnostic context
    sources: list[VmalertSourceSummaryPayload] = []
    for source in vmalert_sources.sources:
        sources.append({
            "endpoint": source.endpoint,
            "namespace": source.namespace,
            "name": source.name,
            "origin": source.origin,
            "state": source.state,
            "display_provenance": source.display_provenance,
            "cluster_label": source.cluster_label,
        })

    return {
        "source_count": vmalert_sources.source_count,
        "discovered_count": vmalert_sources.discovered_count,
        "discovered_but_unverified_count": vmalert_sources.discovered_but_unverified_count,
        "sources": sources,
    }


def _build_vmalert_rule_state_context(
    context: UIIndexContext,
) -> VmalertRuleStateContextPayload | None:
    """Build vmalert rule state context for the incident report.

    This is a read-only, non-invasive integration: no live scraping or actions.
    vmalertRuleState is sourced from the UI context (artifact-backed).

    Contract invariants:
    - Returns None when no vmalert rule state is available (not an error)
    - Empty alerts means quiet zero-count state (not an error)
    - Pending alerts are visible but not escalated
    - Fetch failures are visible but non-fatal
    - No errors are raised for missing/malformed artifacts

    Args:
        context: UI index context containing vmalert rule state from artifact.

    Returns:
        VmalertRuleStateContextPayload or None if no rule state available.
    """
    vmalert_rule_state = context.vmalert_rule_state
    if vmalert_rule_state is None:
        return None

    return {
        "source_count": vmalert_rule_state.source_count,
        "fetched_source_count": vmalert_rule_state.fetched_source_count,
        "failed_source_count": vmalert_rule_state.failed_source_count,
        "alert_count": vmalert_rule_state.alert_count,
        "firing_alert_count": vmalert_rule_state.firing_alert_count,
        "pending_alert_count": vmalert_rule_state.pending_alert_count,
        "critical_firing_count": vmalert_rule_state.critical_firing_count,
        "top_alertnames": list(vmalert_rule_state.top_alertnames),
        "severity_counts": list(vmalert_rule_state.severity_counts),
        "affected_namespaces": list(vmalert_rule_state.affected_namespaces),
        "affected_workloads": list(vmalert_rule_state.affected_workloads),
        "fetch_error_count": vmalert_rule_state.fetch_error_count,
    }


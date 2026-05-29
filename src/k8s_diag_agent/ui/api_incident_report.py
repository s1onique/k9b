"""Incident report and operator worklist payload builders.

These functions derive canonical incident-report and worklist projections from
existing UI context artifacts (assessments, drilldowns, next-check queue,
execution history, deterministic next checks). They do not introduce new
immutable artifacts; the output is a read-only API projection.

Truthfulness rules enforced by the builders:
- Facts are deterministic/evidence-backed only.
- Inferences are explicitly labeled as inferences.
- Unknowns/missing evidence are explicit.
- Stale evidence is flagged when freshness data supports it.
- Provider-assisted content is never classified as deterministic fact.
- Source artifact refs are preserved where available; absent provenance is left
  empty/unknown rather than fabricated.

Security note:
    All operator-facing text fields are sanitized at serialization boundary
    to prevent internal context markers like "in-cluster" from leaking to
    the operator UI. This includes cluster labels, context values, hypotheses,
    and worklist target fields.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Literal, cast

from ..security.kubectl_context import (
    display_kube_cluster_label,
    sanitize_operator_text,
)
from .api_incident_report_filtering import (
    filter_artifact_refs_preserving_minimum,
)
from .api_incident_report_ownership import (
    derive_evidence_ownership,
    format_ownership_fields,
)
from .api_incident_report_worklist import (  # noqa: F401 - re-exported for backward compatibility
    _ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED,
    _ADAPTATION_EFFECT_HYPOTHESIS_WEAKENED,
    _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE,
    _ADAPTATION_EFFECT_RECOMMENDATION_DEPRIORITIZED,
    _ADAPTATION_EFFECT_RECOMMENDATION_PROMOTED,
    _ADAPTATION_EFFECT_UNKNOWN_RESOLVED,
    _USE_TO_ADAPTATION_MAP,
    _build_operator_worklist_payload,
    _derive_adaptation_provenance,
    _derive_item_state,
    _derive_temporal_context,
    _derive_worklist_ranking_reason,
    _sanitize_target_cluster,
    _sanitize_target_context,
)
from .api_payloads import (
    ArtifactLink,
    CrossClusterFindingPayload,
    FreshnessPayload,
    IncidentReportDerivedPayload,
    IncidentReportFactPayload,
    IncidentReportInferencePayload,
    IncidentReportPayload,
    IncidentReportRecommendationPayload,
    IncidentReportUnknownPayload,
    VmalertDiscoveryContextPayload,
    VmalertRuleStateContextPayload,
    VmalertSourceSummaryPayload,
)
from .model import UIIndexContext

logger = logging.getLogger(__name__)

# _sanitize_target_cluster and _sanitize_target_context are imported from
# api_incident_report_worklist module for backward compatibility


def _build_incident_report_payload(
    context: UIIndexContext,
    freshness: Mapping[str, object] | None,
) -> IncidentReportPayload | None:
    """Derive an incident report from the existing UI context.

    Returns None when there is no meaningful incident state to report.
    """
    # Gather degraded clusters and top problems from fleet status and clusters
    degraded_labels = list(context.fleet_status.degraded_clusters)
    cluster_count = len(context.clusters)

    if not degraded_labels and cluster_count == 0:
        # Honest empty/unknown state: no clusters, no incident data
        return None

    # Derive title/status from fleet state
    if degraded_labels:
        status = "degraded"
        title = f"Degraded health detected in {len(degraded_labels)} cluster(s)"
    else:
        status = "healthy"
        title = "No degraded clusters detected"

    facts: list[IncidentReportFactPayload] = []
    derived: list[IncidentReportDerivedPayload] = []
    inferences: list[IncidentReportInferencePayload] = []
    recommendations: list[IncidentReportRecommendationPayload] = []
    unknowns: list[IncidentReportUnknownPayload] = []
    stale_warnings: list[str] = []
    recommended_actions: list[str] = []
    source_refs: list[ArtifactLink] = []

    def _assessment_refs() -> list[ArtifactLink]:
        path = assessment.artifact_path if assessment else None
        return [{"label": "Assessment", "path": path}] if path else []

    # Build derived claims from latest assessment when present
    # Health rating is a deterministic conclusion from evidence fields, not raw telemetry
    assessment = context.latest_assessment
    if assessment is not None:
        if assessment.health_rating:
            # Sanitize cluster_label to prevent internal markers like "in-cluster"
            # from appearing in operator-facing prose
            safe_cluster_name = display_kube_cluster_label(assessment.cluster_label)
            # Avoid awkward "Cluster the cluster..." phrasing
            if safe_cluster_name:
                statement = f"Cluster {safe_cluster_name} health rating is {assessment.health_rating}."
            else:
                statement = f"The cluster health rating is {assessment.health_rating}."
            derived.append(
                {
                    "claimType": "derived",
                    "statement": statement,
                    "sourceFields": ["health_rating"],
                    "sourceArtifactRefs": _assessment_refs(),
                    "confidence": "high",
                }
            )
        # Missing evidence is an explicit unknown claim with ownership derivation
        # Derive ownership hints from available signals: method, evidence_needed,
        # probable_layer, existing owner field, and workstream
        for missing in assessment.missing_evidence:
            # Extract signals from assessment for ownership derivation
            # Use the first next_check as a representative signal source
            method: str | None = None
            evidence_needed: tuple[str, ...] = ()
            owner: str | None = None
            workstream: str | None = None
            if assessment.next_checks:
                first_check = assessment.next_checks[0]
                method = first_check.method
                evidence_needed = first_check.evidence_needed
                owner = first_check.owner
                workstream = getattr(first_check, "workstream", None)
            
            # Derive ownership from available signals
            probable_layer = assessment.probable_layer
            evidence_owner, routing_hint, confidence = derive_evidence_ownership(
                method=method,
                evidence_needed=evidence_needed,
                probable_layer=probable_layer,
                owner=owner,
                workstream=workstream,
                is_cross_cluster=cluster_count > 1,
            )
            
            # Format ownership fields for the unknown payload
            ownership_fields = format_ownership_fields(evidence_owner, routing_hint, confidence)
            
            # Build unknown payload with ownership context
            unknown_entry: IncidentReportUnknownPayload = {
                "claimType": "unknown",
                "statement": f"Missing evidence: {missing}",
                "whyMissing": "Not collected in this run",
                "sourceArtifactRefs": _assessment_refs(),
            }
            # Merge ownership fields if derivable (format_ownership_fields returns dict compatible with TypedDict)
            # Each field is explicitly typed to match the TypedDict signature
            if "evidenceOwner" in ownership_fields:
                unknown_entry["evidenceOwner"] = cast("str | None", ownership_fields["evidenceOwner"])
            if "routingHint" in ownership_fields:
                unknown_entry["routingHint"] = cast("str | None", ownership_fields["routingHint"])
            if "ownershipConfidence" in ownership_fields:
                unknown_entry["ownershipConfidence"] = cast("Literal['high', 'medium', 'low', 'unknown'] | None", ownership_fields["ownershipConfidence"])
            unknowns.append(unknown_entry)
        # Hypotheses are inference/hypothesis claims
        # Sanitize description to prevent internal markers from leaking
        for hypothesis in assessment.hypotheses:
            safe_hypothesis_description = sanitize_operator_text(hypothesis.description)
            if safe_hypothesis_description:
                inferences.append(
                    {
                        "claimType": "hypothesis",
                        "statement": safe_hypothesis_description,
                        "basis": [hypothesis.probable_layer],
                        "confidence": hypothesis.confidence,
                        "sourceArtifactRefs": _assessment_refs(),
                    }
                )
        # Recommended action is a separate recommendation claim (not mixed with facts)
        if assessment.recommended_action is not None:
            action = assessment.recommended_action
            # Sanitize action description to prevent internal markers from leaking
            safe_action_description = sanitize_operator_text(action.description)
            if safe_action_description:
                recommendations.append(
                    {
                        "claimType": "recommendation",
                        "statement": safe_action_description,
                        "safetyLevel": action.safety_level or "unknown",
                        "sourceArtifactRefs": _assessment_refs(),
                    }
                )
                recommended_actions.append(safe_action_description)
        if assessment.artifact_path:
            source_refs.append({"label": "Assessment", "path": assessment.artifact_path})
        if assessment.snapshot_path:
            source_refs.append({"label": "Snapshot", "path": assessment.snapshot_path})

    # Build facts from latest findings (drilldown) when present
    findings = context.latest_findings
    if findings is not None:
        def _drilldown_refs() -> list[ArtifactLink]:
            path = findings.artifact_path if findings else None
            return [{"label": "Drilldown", "path": path}] if path else []

        if findings.trigger_reasons:
            facts.append(
                {
                    "claimType": "observed",
                    "statement": f"Trigger reasons: {', '.join(findings.trigger_reasons)}",
                    "sourceArtifactRefs": _drilldown_refs(),
                    "confidence": "high",
                }
            )
        if findings.warning_events > 0:
            facts.append(
                {
                    "claimType": "observed",
                    "statement": f"Warning events observed: {findings.warning_events}",
                    "sourceArtifactRefs": _drilldown_refs(),
                    "confidence": "high",
                }
            )
        if findings.non_running_pods > 0:
            facts.append(
                {
                    "claimType": "observed",
                    "statement": f"Non-running pods observed: {findings.non_running_pods}",
                    "sourceArtifactRefs": _drilldown_refs(),
                    "confidence": "high",
                }
            )
        if findings.artifact_path:
            source_refs.append({"label": "Drilldown", "path": findings.artifact_path})

    # Stale evidence warning when freshness supports it
    if freshness is not None:
        freshness_status = freshness.get("status")
        if freshness_status in ("delayed", "stale"):
            stale_warnings.append(
                f"Run freshness is {freshness_status}; some evidence may be stale."
            )

    # Provider-assisted content: review enrichment is explicitly an inference source
    review_enrichment = context.review_enrichment
    if review_enrichment is not None and review_enrichment.summary:
        def _enrichment_refs() -> list[ArtifactLink]:
            path = review_enrichment.artifact_path if review_enrichment else None
            return [{"label": "Review Enrichment", "path": path}] if path else []

        # Sanitize summary to prevent internal markers from leaking
        safe_summary = sanitize_operator_text(review_enrichment.summary)
        if safe_summary:
            inferences.append(
                {
                    "claimType": "hypothesis",
                    "statement": safe_summary,
                    "basis": ["review-enrichment"],
                    "confidence": "medium",
                    "sourceArtifactRefs": _enrichment_refs(),
                }
            )
        if review_enrichment.artifact_path:
            source_refs.append(
                {"label": "Review Enrichment", "path": review_enrichment.artifact_path}
            )

    # Deduplicate source refs while preserving order
    seen_refs: set[str] = set()
    deduped_refs: list[ArtifactLink] = []
    for ref in source_refs:
        path = ref.get("path")
        if path and path not in seen_refs:
            seen_refs.add(path)
            deduped_refs.append(ref)

    # Apply artifact filtering to improve provenance quality
    # Filter skipped/placeholder artifacts from source refs to avoid noise
    # Use preserving-minimum to ensure claims don't lose all provenance
    filtered_refs = filter_artifact_refs_preserving_minimum(deduped_refs)

    # A healthy run with no evidence should still produce an honest empty report
    if status == "healthy" and not facts and not inferences and not unknowns:
        facts.append(
            {
                "claimType": "observed",
                "statement": "No degraded clusters or incidents detected in this run.",
                "sourceArtifactRefs": filtered_refs or [],
                "confidence": "high",
            }
        )

    # Build cross-cluster findings from comparison triggers
    # These provide fleet-level drift visibility that individual cluster assessments may miss
    cross_cluster_findings = _build_cross_cluster_findings_payload(context)

    # Build vmalert discovery context for diagnostic awareness
    # This is a read-only, non-invasive integration: no live scraping or actions
    # vmalertSources is sourced from the UI context (artifact-backed, not re-discovered)
    vmalert_context = _build_vmalert_discovery_context(context)

    # Build vmalert rule state context for firing/pending alert diagnostics
    # This is a read-only, non-invasive integration: no live scraping or actions
    # vmalertRuleState is sourced from the UI context (artifact-backed)
    vmalert_rule_state_context = _build_vmalert_rule_state_context(context)

    return {
        "title": title,
        "status": status,
        "affectedScope": ", ".join(degraded_labels) if degraded_labels else None,
        "impact": None,
        "evidenceSummary": None,
        "facts": facts,
        "derived": derived,
        "inferences": inferences,
        "recommendations": recommendations,
        "unknowns": unknowns,
        "staleEvidenceWarnings": stale_warnings,
        "confidence": "high" if (facts or derived) else "low",
        "freshness": cast(FreshnessPayload | None, freshness),
        "recommendedActions": recommended_actions,
        "sourceArtifactRefs": filtered_refs,
        "crossClusterFindings": cross_cluster_findings,
        "vmalertDiscoveryContext": vmalert_context,
        "vmalertRuleStateContext": vmalert_rule_state_context,
    }


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
        recommended_next_checks = _derive_fleet_aware_checks(drift_counts, trigger_reasons)

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
                "triggerReasons": trigger_reasons,
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


def _derive_fleet_aware_checks(
    drift_counts: dict[str, int],
    trigger_reasons: list[str],
) -> list[str]:
    """Derive fleet-aware next check recommendations from drift categories.

    Recommendations focus on next useful fleet-aware checks, not just generic
    cluster triage. They are derived from the drift categories present.

    Args:
        drift_counts: Drift category counts (e.g., {"helm_releases": 2, "crds": 1})
        trigger_reasons: Trigger reasons that fired the comparison

    Returns:
        List of recommended next checks for fleet-level investigation.
    """
    recommendations: list[str] = []

    # Helm release drift: recommend inspecting the specific drift
    if drift_counts.get("helm_releases", 0) > 0:
        recommendations.append("Compare Helm release versions across same-role clusters")

    # CRD drift: recommend inspecting CRD versions
    if drift_counts.get("crds", 0) > 0:
        recommendations.append("Inspect CRD storage versions and served APIs across clusters")

    # Metadata drift (control plane version): recommend fleet-wide version check
    if drift_counts.get("metadata", 0) > 0:
        recommendations.append("Check control plane version consistency across fleet")

    # Metrics drift: recommend comparing resource utilization
    if drift_counts.get("metrics", 0) > 0:
        recommendations.append("Compare resource utilization patterns across peer clusters")

    # Add fleet-aware checks based on trigger reasons
    for reason in trigger_reasons:
        reason_lower = reason.lower()
        if "health_regression" in reason_lower:
            if "Investigate health regression across comparable clusters" not in recommendations:
                recommendations.append("Investigate health regression across comparable clusters")
        elif "baseline" in reason_lower:
            if "Review baseline drift across same-cohort clusters" not in recommendations:
                recommendations.append("Review baseline drift across same-cohort clusters")
        elif "helm" in reason_lower:
            if "Compare Helm release versions across same-role clusters" not in recommendations:
                recommendations.append("Compare Helm release versions across same-role clusters")

    # Deduplicate and limit to top 3 recommendations
    seen = set()
    deduped: list[str] = []
    for rec in recommendations:
        if rec not in seen:
            seen.add(rec)
            deduped.append(rec)

    return deduped[:3]




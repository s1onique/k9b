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

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from ..security.kubectl_context import (
    CLUSTER_LOCAL_PRESENTATION_LABEL,
    display_kube_cluster_label,
    is_internal_kube_marker,
    sanitize_kubectl_display_command,
    sanitize_operator_text,
)
from .api_incident_report_filtering import (
    filter_artifact_refs_preserving_minimum,
)
from .api_incident_report_ownership import (
    derive_evidence_ownership,
    format_ownership_fields,
)
from .api_payloads import (
    ArtifactLink,
    CrossClusterFindingPayload,
    FeedbackAdaptationProvenancePayload,
    FreshnessPayload,
    IncidentReportDerivedPayload,
    IncidentReportFactPayload,
    IncidentReportInferencePayload,
    IncidentReportPayload,
    IncidentReportRecommendationPayload,
    IncidentReportUnknownPayload,
    OperatorWorklistItemPayload,
    OperatorWorklistPayload,
    StalenessClass,
    VmalertDiscoveryContextPayload,
    VmalertRuleStateContextPayload,
    VmalertSourceSummaryPayload,
)
from .execution_index_utils import (
    collect_execution_artifacts_for_all_runs,
)
from .model import UIIndexContext

logger = logging.getLogger(__name__)


# =============================================================================
# Execution Artifact Overlay for Worklist
# =============================================================================


@dataclass(frozen=True)
class ExecutionArtifactOverlay:
    """Overlay data from an execution artifact for worklist derivation."""
    candidate_id: str | None
    candidate_index: int | None
    command_family: str | None
    target_cluster: str | None
    artifact_path: str | None
    status: str | None  # success | failed | timed-out
    timestamp: str | None


def _scan_execution_artifacts_for_worklist(
    health_root: Path,
    run_id: str,
) -> tuple[Sequence[ExecutionArtifactOverlay], dict[str, int]]:
    """Scan external-analysis directory for execution artifacts matching this run.
    
    Returns tuple of (overlays, telemetry) where overlays can be used to derive
    execution state for worklist items.
    
    This function uses the shared one-pass collector from execution_index_utils.py
    to ensure consistency with the index-backed path. Both paths now use identical
    artifact discovery logic.
    
    CRITICAL: This function uses collect_execution_artifacts_for_all_runs() which
    finds artifacts by their run_id field first, then falls back to filename matching.
    This ensures worklist path matches index path even when artifact filenames differ
    from the run_id field (e.g., filename="old-run-next-check-execution-0.json" but
    artifact field run_id="current-run").
    
    Matching criteria (all non-None fields must match):
    - candidate_index AND command_family AND target_cluster (primary)
    - OR candidate_id AND target_cluster (fallback)
    
    Telemetry tracks scan performance and match statistics.
    """
    telemetry: dict[str, int] = {
        "execution_artifacts_found": 0,
        "execution_artifacts_matched": 0,
        "execution_artifacts_skipped_mismatch": 0,
        "execution_artifacts_parse_failed": 0,
    }
    
    overlays: list[ExecutionArtifactOverlay] = []
    
    external_analysis_dir = health_root / "external-analysis"
    if not external_analysis_dir.exists():
        return overlays, telemetry
    
    # Use the rich record collector for exact artifact matching
    # This returns ExecutionArtifactRecord with artifact_path, status, timestamp
    # The collector uses run_id field as primary key, ensuring we find artifacts
    # even when their filenames differ from the run_id field
    artifacts_by_run, exec_diagnostics = collect_execution_artifacts_for_all_runs(
        external_analysis_dir,
        health_root=health_root,
    )
    
    # Get execution records for this specific run
    run_artifacts = artifacts_by_run.get(run_id, {})
    telemetry["execution_artifacts_found"] = cast(int, exec_diagnostics.get("total_execution_artifacts_found", 0))
    telemetry["execution_artifacts_matched"] = len(run_artifacts)
    
    # Build overlays from the exact records found by the shared collector
    # Each record has: candidate_index, status, artifact_path, timestamp
    # We need to read the artifact to get additional fields (candidate_id, command_family, target_cluster)
    # This is a targeted read of only the artifacts already matched by the collector
    for candidate_index, record in run_artifacts.items():
        artifact_path = record.get("artifact_path")
        if not artifact_path:
            continue
        
        # Resolve artifact path relative to health_root
        # The artifact_path in the record is relative to health_root
        artifact_file = health_root / artifact_path if not Path(artifact_path).is_absolute() else Path(artifact_path)
        
        if not artifact_file.exists():
            # Try constructing from external_analysis_dir directly
            artifact_file = external_analysis_dir / Path(artifact_path).name
        
        if not artifact_file.exists():
            # Skip if we can't find the artifact file
            telemetry["execution_artifacts_parse_failed"] += 1
            continue
        
        try:
            raw = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                telemetry["execution_artifacts_parse_failed"] += 1
                continue
            
            payload = raw.get("payload", {})
            if not isinstance(payload, dict):
                telemetry["execution_artifacts_parse_failed"] += 1
                continue
            
            # Extract enrichment fields from the artifact
            candidate_id = payload.get("candidateId") or payload.get("candidate_id")
            command_family = payload.get("commandFamily") or payload.get("command_family")
            if not command_family:
                tool_name = payload.get("tool_name") or ""
                if isinstance(tool_name, str) and "-" in tool_name:
                    command_family = tool_name.split("-", 1)[1] if "-" in tool_name else tool_name
            target_cluster = payload.get("clusterLabel") or payload.get("cluster_label") or payload.get("targetCluster")
            
            overlay = ExecutionArtifactOverlay(
                candidate_id=str(candidate_id) if candidate_id else None,
                candidate_index=candidate_index,
                command_family=str(command_family) if command_family else None,
                target_cluster=str(target_cluster) if target_cluster else None,
                artifact_path=artifact_path,
                status=record.get("status"),
                timestamp=record.get("timestamp"),
            )
            overlays.append(overlay)
            
        except (OSError, json.JSONDecodeError):
            telemetry["execution_artifacts_parse_failed"] += 1
            continue
    
    telemetry["execution_artifacts_matched"] = len(overlays)
    return overlays, telemetry


def _match_execution_overlay_to_queue_item(
    overlay: ExecutionArtifactOverlay,
    queue_item_candidate_id: str | None,
    queue_item_candidate_index: int | None,
    queue_item_command_family: str | None,
    queue_item_target_cluster: str | None,
) -> bool:
    """Check if an execution artifact overlay matches a queue item.
    
    Matching rules (all non-None overlay fields must match):
    1. Primary: candidate_index + command_family + target_cluster (all required)
    2. Fallback: candidate_id + target_cluster (all required)
    
    Returns True if overlay should be applied to this queue item.
    """
    # Primary match: candidate_index + command_family + target_cluster
    if overlay.candidate_index is not None and overlay.command_family is not None and overlay.target_cluster is not None:
        index_match = overlay.candidate_index == queue_item_candidate_index
        family_match = overlay.command_family.lower() == queue_item_command_family.lower() if queue_item_command_family else False
        cluster_match = overlay.target_cluster == queue_item_target_cluster
        
        if index_match and family_match and cluster_match:
            return True
    
    # Fallback match: candidate_id + target_cluster
    if overlay.candidate_id and overlay.target_cluster:
        id_match = overlay.candidate_id == queue_item_candidate_id
        cluster_match = overlay.target_cluster == queue_item_target_cluster
        
        if id_match and cluster_match:
            return True
    
    return False


def _derive_execution_state_from_artifact(status: str | None) -> str:
    """Derive execution_state string from artifact status.
    
    Maps artifact status to queue item execution_state:
    - "success" -> "executed-success"
    - "failed" -> "executed-failed"
    - "timed-out" / "timeout" -> "timed-out"
    - other -> "executed-success" (default for any completed artifact)
    """
    if status is None:
        return "executed-success"
    
    status_lower = status.lower()
    if status_lower == "success":
        return "executed-success"
    elif status_lower == "failed":
        return "executed-failed"
    elif status_lower in ("timed-out", "timeout"):
        return "timed-out"
    else:
        # Any other status means execution completed (artifact was created)
        return "executed-success"


def _sanitize_target_cluster(cluster: str | None, context: str | None = None) -> str | None:
    """Sanitize a cluster label for operator-facing display.

    Removes internal context markers like "in-cluster" and "in_cluster" from
    cluster labels, returning "cluster-local" if the label is only an internal marker.

    Args:
        cluster: The cluster label to sanitize.
        context: Optional context for fallback if cluster is internal marker.

    Returns:
        Sanitized cluster label, or "cluster-local" if the label is only an internal marker.
    """
    if cluster is None:
        return None
    # If cluster is an internal marker, try to use context as fallback
    if is_internal_kube_marker(cluster):
        if context and not is_internal_kube_marker(context):
            return context
        return CLUSTER_LOCAL_PRESENTATION_LABEL
    return cluster


def _sanitize_target_context(context: str | None) -> str | None:
    """Sanitize a context value for operator-facing display.

    Removes internal context markers like "in-cluster" and "in_cluster".
    Returns "cluster-local" if the context is only an internal marker.

    Args:
        context: The context value to sanitize.

    Returns:
        Sanitized context, or "cluster-local" if the context is an internal marker.
    """
    if context is None:
        return None
    if is_internal_kube_marker(context):
        return CLUSTER_LOCAL_PRESENTATION_LABEL
    return context


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


# =============================================================================
# Worklist Item State Constants
# =============================================================================


# Canonical item states for the unified worklist projection
# State transition: advisory -> approval-needed -> approved -> queued -> executed -> reviewed
_ITEM_STATE_ADVISORY = "advisory"
_ITEM_STATE_APPROVAL_NEEDED = "approval-needed"
_ITEM_STATE_APPROVED = "approved"
_ITEM_STATE_QUEUED = "queued"
_ITEM_STATE_EXECUTED = "executed"
_ITEM_STATE_REVIEWED = "reviewed"


# Source type constants for provenance tracking
_SOURCE_TYPE_DETERMINISTIC = "deterministic"
_SOURCE_TYPE_PLANNER = "planner"
_SOURCE_TYPE_PROMOTION = "promotion"
_SOURCE_TYPE_EXECUTION = "execution"
_SOURCE_TYPE_VMALERT_ALERT = "vmalert-alert"


# =============================================================================
# Adaptation Effect Taxonomy
# =============================================================================


# Adaptation effect constants for feedback provenance
# These describe what changed in the diagnosis or worklist because of execution feedback
_ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED = "hypothesis_strengthened"
_ADAPTATION_EFFECT_HYPOTHESIS_WEAKENED = "hypothesis_weakened"
_ADAPTATION_EFFECT_UNKNOWN_RESOLVED = "unknown_resolved"
_ADAPTATION_EFFECT_RECOMMENDATION_PROMOTED = "recommendation_promoted"
_ADAPTATION_EFFECT_RECOMMENDATION_DEPRIORITIZED = "recommendation_deprioritized"
_ADAPTATION_EFFECT_NO_MATERIAL_CHANGE = "no_material_change"

# Mapping from usefulness class to default adaptation effect
_USE_TO_ADAPTATION_MAP: dict[str, str] = {
    "useful": _ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED,
    "partial": _ADAPTATION_EFFECT_UNKNOWN_RESOLVED,
    "noisy": _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE,
    "empty": _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE,
}


def _derive_adaptation_provenance(
    usefulness_class: str | None,
    usefulness_summary: str | None,
    execution_result_summary: str | None,
) -> dict[str, object] | None:
    """Derive adaptation provenance from execution feedback.

    Produces a feedbackAdaptationProvenance dict for worklist items when
    execution feedback exists. This is derived-only (stateless) from execution
    history and usefulness feedback; no new persistence is introduced.

    Adaptation effect derivation rules:
    - useful result -> hypothesis_strengthened (confirms leading hypothesis)
    - partial result -> unknown_resolved (fills evidence gap but leaves unknowns)
    - noisy result -> no_material_change (inconclusive, doesn't change diagnosis)
    - empty result -> no_material_change (no signal captured)

    Args:
        usefulness_class: The usefulness class from operator feedback (useful/partial/noisy/empty)
        usefulness_summary: Human-readable summary from operator feedback
        execution_result_summary: Computed result summary from execution classification

    Returns:
        Dict with adaptation provenance fields, or None if no feedback exists
    """
    if not usefulness_class:
        return None

    effect = _USE_TO_ADAPTATION_MAP.get(usefulness_class)
    if not effect:
        return None

    # Generate adaptation summary based on effect
    if effect == _ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED:
        if usefulness_summary:
            summary = f"Strengthened leading hypothesis: {usefulness_summary[:100]}"
        else:
            summary = "Strengthened leading workload hypothesis"
    elif effect == _ADAPTATION_EFFECT_UNKNOWN_RESOLVED:
        if usefulness_summary:
            summary = f"Resolved evidence gap: {usefulness_summary[:100]}"
        else:
            summary = "Resolved missing evidence gap"
    elif effect == _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE:
        if usefulness_summary:
            summary = f"No material change: {usefulness_summary[:100]}"
        else:
            summary = "No material change to diagnosis"
    else:
        summary = None

    return {
        "feedbackAdaptation": True,
        "adaptationReason": f"usefulness:{usefulness_class}",
        "adaptationEffect": effect,
        "adaptationSummary": summary,
        "originalBonus": 0,
        "suppressedBonus": 0,
        "penaltyApplied": 0,
        "explanation": execution_result_summary,
    }


# =============================================================================
# Ranking Rationale Derivation
# =============================================================================


def _derive_worklist_ranking_reason(
    source_type: str | None,
    item_state: str | None,
    execution_state: str | None,
    is_primary_triage: bool | None,
    urgency: str | None,
    priority_label: str | None,
    command: str | None,
    workstream: str | None,
) -> str | None:
    """Derive a concise ranking rationale for a worklist item.

    The rationale explains why this item has its current rank in the worklist.
    It is derived-only (stateless) from available item signals and state.

    Allowed basis for ranking rationale:
    - urgency / primary triage: deterministic items marked as primary triage
    - approval/execution readiness: items ready to execute or pending approval
    - expected information gain: executable items that confirm leading hypothesis
    - drift category severity: fleet-level drift affecting comparable clusters
    - executed/reviewed state: completed items retained for result review

    Priority order for queue items:
    1. Executed/reviewed state
    2. Primary triage deterministic
    3. Approval-needed state (before high-priority executable)
    4. Drift workstream
    5. High priority executable
    6. Generic executable
    7. Advisory deterministic
    8. Fallback

    Args:
        source_type: Origin source (deterministic | planner | promotion | execution)
        item_state: Canonical item state (advisory | approval-needed | approved | queued | executed | reviewed)
        execution_state: Execution state from queue item
        is_primary_triage: Whether deterministic item is primary triage
        urgency: Urgency level from deterministic next check
        priority_label: Priority label from planner candidate
        command: Executable command (None for advisory/deterministic items)
        workstream: Workstream context (incident | drift | network | etc)

    Returns:
        Concise operator-readable ranking rationale, or None if no basis is determinable.
    """
    # 1. Executed/reviewed items: retained for result review
    if item_state in (_ITEM_STATE_EXECUTED, _ITEM_STATE_REVIEWED):
        return "Already executed; retained for result review"

    # 2. Primary triage deterministic items
    if is_primary_triage and source_type == _SOURCE_TYPE_DETERMINISTIC:
        # Include urgency when available
        if urgency and urgency != "unknown":
            return f"Primary triage for current degraded workload ({urgency} urgency)"
        return "Primary triage for current degraded workload"

    # 3. Drift workstream items (cross-cluster) - prioritized before state-based rationale
    if workstream == "drift":
        return "Fleet-level drift affects comparable clusters"

    # 4. Planner items with command - state-based and priority-based rationale
    if source_type in (_SOURCE_TYPE_PLANNER, _SOURCE_TYPE_PROMOTION) and command is not None:
        if item_state == _ITEM_STATE_APPROVAL_NEEDED:
            return "Pending operator approval before execution"
        if item_state == _ITEM_STATE_APPROVED:
            return "Approved and ready for execution"
        if item_state == _ITEM_STATE_QUEUED:
            # Check high priority first
            if priority_label in ("primary", "critical"):
                return "Executable now; likely to confirm the leading hypothesis"
            return "Queued for automated execution"
        # Default executable rationale for planner items with command
        if priority_label in ("primary", "critical"):
            return "Executable now; likely to confirm the leading hypothesis"
        return "Planner-selected check; executable now"

    # 5. Advisory deterministic items without executable command
    if source_type == _SOURCE_TYPE_DETERMINISTIC:
        if urgency and urgency != "unknown":
            return f"Advisory check; {urgency} urgency for evidence collection"
        return "Advisory check; method-based diagnostics"

    # 6. Fallback: no specific ranking basis determinable
    return None


# =============================================================================
# Temporal Context Derivation (Epic: BETA-G4 Temporal Context in Worklist)
# =============================================================================


# Staleness thresholds in seconds
_STALENESS_FRESH_SECONDS = 5 * 60  # < 5 minutes
_STALENESS_AGING_SECONDS = 30 * 60  # 5-30 minutes
# > 30 minutes = stale


def _parse_timestamp(timestamp_str: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to datetime.

    Args:
        timestamp_str: ISO 8601 formatted timestamp or None

    Returns:
        datetime in UTC or None if parsing fails
    """
    if not timestamp_str:
        return None
    try:
        # Try parsing with timezone
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    try:
        # Fallback: try parsing without timezone (assume UTC)
        dt = datetime.fromisoformat(timestamp_str)
        return dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _derive_temporal_context(
    first_recommended_at: str | None,
    last_state_changed_at: str | None,
    current_run_timestamp: str | None,
) -> tuple[str | None, str | None, int | None, StalenessClass | None]:
    """Derive temporal context fields for a worklist item.

    Temporal context is derived-only (stateless) from existing timestamps in
    queue items, execution history, plan artifacts, and run metadata. No new
    timestamps are fabricated.

    Derivation rules:
    - firstRecommendedAt: earliest known timestamp tied to the logical recommendation
      * deterministic items: assessment/drilldown artifact timestamp
      * queue items: plan artifact timestamp or earliest candidate timestamp
      * None when no timing data is available
    - lastStateChangedAt: most recent meaningful state transition timestamp
      * approval, execution, or review timestamp
      * None when no state change timestamp is available
    - recommendationAgeSeconds: age from first recommendation to current run
      * Derived from firstRecommendedAt and current_run_timestamp when both are known
      * None when timing data is insufficient
    - stalenessClass: honest staleness category
      * fresh: < 5 minutes since first recommendation
      * aging: 5-30 minutes since first recommendation
      * stale: > 30 minutes since first recommendation
      * unknown: timing data insufficient

    Args:
        first_recommended_at: Earliest known recommendation timestamp
        last_state_changed_at: Most recent state change timestamp
        current_run_timestamp: Current run timestamp for age calculation

    Returns:
        Tuple of (firstRecommendedAt, lastStateChangedAt, recommendationAgeSeconds, stalenessClass)
    """
    # Determine staleness based on available timestamps
    staleness: StalenessClass = "unknown"
    age_seconds: int | None = None

    if first_recommended_at and current_run_timestamp:
        first_dt = _parse_timestamp(first_recommended_at)
        current_dt = _parse_timestamp(current_run_timestamp)
        if first_dt and current_dt:
            # Calculate age in seconds
            delta = current_dt - first_dt
            age_seconds = int(delta.total_seconds())
            if age_seconds >= 0:
                if age_seconds < _STALENESS_FRESH_SECONDS:
                    staleness = "fresh"
                elif age_seconds < _STALENESS_AGING_SECONDS:
                    staleness = "aging"
                else:
                    staleness = "stale"
            else:
                # Negative age means first recommendation was after current run
                # This is honest - mark as unknown rather than fabricate
                staleness = "unknown"
                age_seconds = None

    return first_recommended_at, last_state_changed_at, age_seconds, staleness


def _derive_item_state(
    queue_item: object,
) -> str | None:
    """Derive canonical itemState from queue item state fields.

    State transition rules:
    - Deterministic items (no queue state): advisory
    - Queue items with requiresOperatorApproval + not approved: approval-needed
    - Queue items with requiresOperatorApproval + approved: approved
    - Queue items safeToAutomate + not executed: queued
    - Queue items executed + not reviewed: executed
    - Queue items with usefulness_class: reviewed

    Returns None for deterministic items that have no queue state.
    """
    if not hasattr(queue_item, "requires_operator_approval"):
        return None

    requires_approval = getattr(queue_item, "requires_operator_approval", False)
    approval_state = getattr(queue_item, "approval_state", None) or ""
    execution_state = getattr(queue_item, "execution_state", None) or ""
    usefulness_class = getattr(queue_item, "usefulness_class", None)

    # Usefulness review indicates reviewed state
    if usefulness_class:
        return _ITEM_STATE_REVIEWED

    # Execution states
    if execution_state in ("executed-success", "executed-failed", "timed-out"):
        return _ITEM_STATE_EXECUTED

    # Approved state (requires approval but is approved)
    if requires_approval and approval_state == "approved":
        return _ITEM_STATE_APPROVED

    # Approval needed (requires approval but not yet approved)
    if requires_approval and approval_state != "approved":
        return _ITEM_STATE_APPROVAL_NEEDED

    # Executable but not yet executed (safe to automate)
    safe_to_automate = getattr(queue_item, "safe_to_automate", False)
    if safe_to_automate and execution_state == "unexecuted":
        return _ITEM_STATE_QUEUED

    # Default to queued for queue items
    if execution_state == "unexecuted":
        return _ITEM_STATE_QUEUED

    return None


def _build_operator_worklist_payload(
    context: UIIndexContext,
    health_root: Path | None = None,
) -> OperatorWorklistPayload | None:
    """Derive a ranked operator worklist from deterministic next checks and queue state.

    Unified projection from deterministic next checks, planner candidates,
    and execution history. This is a read-only projection; there is no new
    persistence layer.

    Execution overlay derivation:
    - If health_root is provided, scans external-analysis/ for execution artifacts
    - Matches artifacts to queue items by candidate_index + command_family + target_cluster
    - Marks matched items as executed with executionState from artifact status
    - This ensures worklist reflects actual execution even when queue data is stale

    Truthfulness rules:
    - command is None for deterministic/advisory items (they have method, not executable cmd)
    - command is a concrete string for executable queue items
    - itemState reflects canonical state: advisory | approval-needed | approved | queued | executed | reviewed
    - sourceType distinguishes origin for provenance: deterministic | planner | promotion | execution
    - mergedSources preserves all contributing origins when multiple sources refer to the same logical action
    """
    items: list[OperatorWorklistItemPayload] = []
    
    # Scan execution artifacts for overlay derivation
    # This enables worklist items to reflect actual execution state from artifacts
    execution_overlays: tuple[ExecutionArtifactOverlay, ...] = ()
    if health_root is not None:
        run_id = context.run.run_id if hasattr(context.run, "run_id") else ""
        if run_id:
            overlays, _ = _scan_execution_artifacts_for_worklist(health_root, run_id)
            execution_overlays = tuple(overlays)

    # Track deterministic IDs for dedupe with queue items
    deterministic_ids: set[str] = set()

    # Prefer deterministic next checks as the primary workstream source
    deterministic = context.run.deterministic_next_checks
    # Get run timestamp for temporal context derivation
    run_timestamp = context.run.timestamp if hasattr(context.run, "timestamp") else None

    if deterministic is not None:
        rank = 1
        for cluster in deterministic.clusters:
            # Sanitize cluster label and context to prevent "in-cluster" leaks
            safe_cluster = _sanitize_target_cluster(cluster.label, cluster.context)
            safe_context = _sanitize_target_context(cluster.context)
            # Only add item if we have a valid cluster identifier
            if safe_cluster is None:
                rank += len(list(cluster.deterministic_next_check_summaries))
                continue
            for summary in cluster.deterministic_next_check_summaries:
                # Deterministic next checks carry a method name, not an executable command.
                # Leave command None so consumers do not misinterpret it as a runnable string.
                # Sanitize all text fields to prevent internal markers from leaking
                # sanitize_operator_text returns str | None but always returns str
                # when input is non-None str (input type is str for summary.description)
                title_str = sanitize_operator_text(summary.description)
                title_str = title_str if title_str is not None else summary.description
                item_id = f"deterministic-{safe_cluster}-{rank}"
                deterministic_ids.add(item_id)
                # Derive item state for ranking rationale
                item_state = _ITEM_STATE_ADVISORY
                # Derive ranking reason for deterministic item
                ranking_reason = _derive_worklist_ranking_reason(
                    source_type=_SOURCE_TYPE_DETERMINISTIC,
                    item_state=item_state,
                    execution_state=None,
                    is_primary_triage=summary.is_primary_triage,
                    urgency=summary.urgency,
                    priority_label=None,
                    command=None,  # Deterministic items have no executable command
                    workstream=summary.workstream,
                )
                # Derive temporal context for deterministic items
                # firstRecommendedAt: assessment artifact timestamp for deterministic items
                assessment_timestamp = None
                if cluster.assessment_artifact_path:
                    # Use the assessment timestamp from the cluster's assessment
                    assessment_timestamp = context.latest_assessment.timestamp if context.latest_assessment else None
                first_recommended_at = assessment_timestamp
                # lastStateChangedAt: None for advisory deterministic items (no state transition yet)
                last_state_changed_at: str | None = None
                first_rec, last_change, age_sec, staleness = _derive_temporal_context(
                    first_recommended_at=first_recommended_at,
                    last_state_changed_at=last_state_changed_at,
                    current_run_timestamp=run_timestamp,
                )
                items.append(
                    {
                        "id": item_id,
                        "rank": rank,
                        "workstream": summary.workstream,
                        "title": title_str,
                        "description": sanitize_operator_text(
                            f"Owner: {summary.owner}; method: {summary.method}; evidence needed: {', '.join(summary.evidence_needed)}"
                        ),
                        "command": None,  # Deterministic items: no executable command
                        "targetCluster": safe_cluster,
                        "targetContext": safe_context,
                        "reason": sanitize_operator_text(summary.why_now),
                        "expectedEvidence": sanitize_operator_text(", ".join(summary.evidence_needed)),
                        "safetyNote": sanitize_operator_text(
                            f"Urgency: {summary.urgency}; primary triage: {summary.is_primary_triage}"
                        ),
                        "itemState": item_state,
                        "approvalState": None,
                        "executionState": None,
                        "feedbackState": None,
                        "sourceType": _SOURCE_TYPE_DETERMINISTIC,
                        "mergedSources": None,
                        "sourceArtifactRefs": [
                            {"label": "Assessment", "path": path}
                            for path in [cluster.assessment_artifact_path, cluster.drilldown_artifact_path]
                            if path
                        ],
                        "rankingReason": ranking_reason,
                        # Temporal context (BETA-G4)
                        "firstRecommendedAt": first_rec,
                        "lastStateChangedAt": last_change,
                        "recommendationAgeSeconds": age_sec,
                        "stalenessClass": staleness,
                    }
                )
                rank += 1

    # Process next-check queue items for execution/approval state enrichment.
    # Queue items are merged when IDs match (deduplication with provenance preservation).
    # For items without matching IDs, we also check by description to catch duplicates
    # where deterministic and planner refer to the same logical action.
    queue_items = context.run.next_check_queue
    for queue_item in queue_items:
        item_id = queue_item.candidate_id or f"queue-{queue_item.description}"
        item_description = queue_item.description

        # Check if this queue item corresponds to an existing deterministic item by ID
        matched_deterministic = False
        if item_id in deterministic_ids:
            # Merge queue state into existing deterministic item
            for existing in items:
                if existing.get("id") == item_id:
                    # Preserve deterministic provenance, add planner provenance
                    existing["approvalState"] = queue_item.approval_state
                    existing["executionState"] = queue_item.execution_state
                    existing["feedbackState"] = queue_item.outcome_status
                    # Update itemState to reflect queue state (not advisory anymore)
                    existing["itemState"] = _derive_item_state(queue_item) or _ITEM_STATE_ADVISORY
                    existing["sourceType"] = _SOURCE_TYPE_PLANNER
                    existing["mergedSources"] = [_SOURCE_TYPE_DETERMINISTIC, _SOURCE_TYPE_PLANNER]
                    if queue_item.plan_artifact_path:
                        refs = list(existing.get("sourceArtifactRefs") or [])
                        refs.append(
                            {
                                "label": "Next-Check Plan",
                                "path": queue_item.plan_artifact_path,
                            }
                        )
                        existing["sourceArtifactRefs"] = refs
                    matched_deterministic = True
                    break
            if matched_deterministic:
                continue

        # Fallback: check for matching deterministic item by description
        # This handles cases where deterministic and planner items describe the same action
        # but have different ID schemes
        if not matched_deterministic and item_description:
            for existing in items:
                if (
                    existing.get("sourceType") == _SOURCE_TYPE_DETERMINISTIC
                    and existing.get("title") == item_description
                ):
                    # Found a deterministic item with same description - merge
                    existing["approvalState"] = queue_item.approval_state
                    existing["executionState"] = queue_item.execution_state
                    existing["feedbackState"] = queue_item.outcome_status
                    existing["itemState"] = _derive_item_state(queue_item) or _ITEM_STATE_ADVISORY
                    existing["sourceType"] = _SOURCE_TYPE_PLANNER
                    existing["mergedSources"] = [_SOURCE_TYPE_DETERMINISTIC, _SOURCE_TYPE_PLANNER]
                    if queue_item.plan_artifact_path:
                        refs = list(existing.get("sourceArtifactRefs") or [])
                        refs.append(
                            {"label": "Next-Check Plan", "path": queue_item.plan_artifact_path}
                        )
                        existing["sourceArtifactRefs"] = refs
                    matched_deterministic = True
                    break
            if matched_deterministic:
                continue

        # Check if this queue item matches an existing queue item (by candidate_id)
        existing_queue_ids = {
            cast(str | None, item.get("id"))
            for item in items
            if cast(str | None, item.get("sourceType")) == _SOURCE_TYPE_PLANNER
        }
        if item_id in existing_queue_ids:
            # Enrich existing queue item with additional provenance
            for existing in items:
                if existing.get("id") == item_id:
                    existing["executionState"] = queue_item.execution_state
                    existing["feedbackState"] = queue_item.outcome_status
                    existing["itemState"] = _derive_item_state(queue_item) or _ITEM_STATE_QUEUED
                    # Add execution provenance
                    if queue_item.latest_artifact_path:
                        refs = list(existing.get("sourceArtifactRefs") or [])
                        refs.append(
                            {
                                "label": "Next-Check Execution",
                                "path": queue_item.latest_artifact_path,
                            }
                        )
                        existing["sourceArtifactRefs"] = refs
            continue

        # New queue item: add as a separate entry
        queue_title = sanitize_operator_text(queue_item.description)
        queue_title = queue_title if queue_title is not None else queue_item.description

        # Determine source type from queue item characteristics
        source_type = _SOURCE_TYPE_PLANNER
        if queue_item.source_type == "deterministic":
            source_type = _SOURCE_TYPE_PROMOTION

        # Build sourceArtifactRefs: include both plan and execution artifacts
        # for complete provenance traceability
        artifact_refs: list[ArtifactLink] = []
        if queue_item.plan_artifact_path:
            artifact_refs.append(
                {"label": "Next-Check Plan", "path": queue_item.plan_artifact_path}
            )
        if queue_item.latest_artifact_path:
            artifact_refs.append(
                {"label": "Next-Check Execution", "path": queue_item.latest_artifact_path}
            )

        # Derive item state and ranking reason for queue item
        queue_item_state = _derive_item_state(queue_item) or _ITEM_STATE_QUEUED
        command = sanitize_kubectl_display_command(queue_item.command_preview) if queue_item.command_preview else None
        ranking_reason = _derive_worklist_ranking_reason(
            source_type=source_type,
            item_state=queue_item_state,
            execution_state=queue_item.execution_state,
            is_primary_triage=None,
            urgency=None,
            priority_label=queue_item.priority_label,
            command=command,
            workstream=queue_item.workstream,
        )

        # Derive adaptation provenance for executed/reviewed items with usefulness feedback
        # Extract usefulness fields from queue item view model
        usefulness_class: str | None = None
        usefulness_summary: str | None = None
        result_summary: str | None = None

        # Access queue item attributes (may be from the view model)
        if hasattr(queue_item, "usefulness_class"):
            usefulness_class = getattr(queue_item, "usefulness_class", None)
        if hasattr(queue_item, "usefulness_summary"):
            usefulness_summary = getattr(queue_item, "usefulness_summary", None)
        if hasattr(queue_item, "result_summary"):
            result_summary = getattr(queue_item, "result_summary", None)

        # Also check for feedback_adaptation_provenance from planner/feedback pipeline
        feedback_adaptation_provenance: dict[str, object] | None = None
        if hasattr(queue_item, "feedback_adaptation_provenance") and queue_item.feedback_adaptation_provenance:
            fp = queue_item.feedback_adaptation_provenance
            if hasattr(fp, "feedback_adaptation") and fp.feedback_adaptation:
                feedback_adaptation_provenance = {
                    "feedbackAdaptation": fp.feedback_adaptation,
                    "adaptationReason": fp.adaptation_reason,
                    "adaptationEffect": getattr(fp, "adaptation_effect", None),
                    "adaptationSummary": getattr(fp, "adaptation_summary", None),
                    "originalBonus": fp.original_bonus,
                    "suppressedBonus": fp.suppressed_bonus,
                    "penaltyApplied": fp.penalty_applied,
                    "explanation": fp.explanation,
                }

        # If no provenance from view model, derive from usefulness class
        if not feedback_adaptation_provenance and usefulness_class:
            feedback_adaptation_provenance = _derive_adaptation_provenance(
                usefulness_class=usefulness_class,
                usefulness_summary=usefulness_summary,
                execution_result_summary=result_summary,
            )

        # Derive temporal context for queue items
        # firstRecommendedAt: plan artifact timestamp or latest execution timestamp
        # Use plan artifact timestamp as first recommendation time
        first_recommended_at = queue_item.plan_artifact_timestamp if hasattr(queue_item, "plan_artifact_timestamp") and queue_item.plan_artifact_timestamp else None
        if not first_recommended_at and queue_item.plan_artifact_path:
            # Fallback: use plan artifact path as a proxy (no exact timestamp)
            first_recommended_at = None
        # lastStateChangedAt: most recent execution or approval timestamp
        last_state_changed_at = queue_item.latest_timestamp if hasattr(queue_item, "latest_timestamp") and queue_item.latest_timestamp else None
        first_rec, last_change, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_recommended_at,
            last_state_changed_at=last_state_changed_at,
            current_run_timestamp=run_timestamp,
        )

        items.append(
            {
                "id": item_id,
                "rank": len(items) + 1,
                "workstream": queue_item.workstream,
                # Sanitize all text fields to prevent internal markers from leaking
                "title": queue_title,
                "description": sanitize_operator_text(queue_item.source_reason),
                # Command semantics: sanitized command for executable queue items
                "command": command,
                # Sanitize targetCluster and targetContext to prevent "in-cluster" leaks
                "targetCluster": _sanitize_target_cluster(queue_item.target_cluster, queue_item.target_context),
                "targetContext": _sanitize_target_context(queue_item.target_context),
                "reason": sanitize_operator_text(queue_item.source_reason),
                "expectedEvidence": sanitize_operator_text(queue_item.expected_signal),
                "safetyNote": sanitize_operator_text(queue_item.safety_reason),
                "itemState": queue_item_state,
                "approvalState": queue_item.approval_state,
                "executionState": queue_item.execution_state,
                "feedbackState": queue_item.outcome_status,
                "sourceType": source_type,
                "mergedSources": None,
                "sourceArtifactRefs": artifact_refs,
                "rankingReason": ranking_reason,
                # Cast to TypedDict-compatible type (derived provenance matches payload shape)
                "feedbackAdaptationProvenance": cast(
                    "FeedbackAdaptationProvenancePayload | None", feedback_adaptation_provenance
                ),
                # Temporal context (BETA-G4)
                "firstRecommendedAt": first_rec,
                "lastStateChangedAt": last_change,
                "recommendationAgeSeconds": age_sec,
                "stalenessClass": staleness,
            }
        )

    # =============================================================================
    # vmalert Alert-Derived Worklist Items
    # =============================================================================

    # Add conservative vmalert alert-derived operator worklist items.
    # Rule: severity=critical AND state=firing => create an advisory worklist item.
    # All other alerts (warning, pending, missing severity) remain context-only.
    # This is a read-only projection; no actions are taken.
    vmalert_rule_state = context.vmalert_rule_state
    if vmalert_rule_state is not None:
        # Track seen items for deduplication: (alertname, namespace, workload, source_endpoint)
        seen_vmalert_keys: set[tuple[str, str | None, str | None, str | None]] = set()

        # Process firing critical alerts as worklist items
        for alert in vmalert_rule_state.alerts:
            # Conservative rule: only severity=critical AND state=firing
            if alert.state != "firing" or alert.severity != "critical":
                continue

            # Deduplication key: same alertname + namespace + workload + source_endpoint
            dedupe_key = (alert.alertname, alert.namespace, alert.workload, alert.source_endpoint)
            if dedupe_key in seen_vmalert_keys:
                continue
            seen_vmalert_keys.add(dedupe_key)

            # Build item ID from alert identity
            ns_suffix = f"-{alert.namespace}" if alert.namespace else ""
            wl_suffix = f"-{alert.workload}" if alert.workload else ""
            ep_suffix = f"-{alert.source_endpoint}" if alert.source_endpoint else ""
            item_id = f"vmalert-critical-{alert.alertname}{ns_suffix}{wl_suffix}{ep_suffix}"

            # Build title and description
            title = f"Critical vmalert alert firing: {alert.alertname}"
            if alert.namespace or alert.workload:
                location_parts = [p for p in [alert.namespace, alert.workload] if p]
                title += f" ({'/'.join(location_parts)})"

            # Build description with available context
            description_parts = []
            if alert.namespace:
                description_parts.append(f"namespace={alert.namespace}")
            if alert.workload:
                description_parts.append(f"workload={alert.workload}")
            if alert.instance:
                description_parts.append(f"instance={alert.instance}")
            description = "; ".join(description_parts) if description_parts else None

            # Build reason explaining why this item was created
            reason = f"vmalert reported alert '{alert.alertname}' as firing with severity=critical"
            if alert.source_endpoint:
                reason += f" (source: {alert.source_endpoint})"

            # Build source artifact ref for provenance
            vmalert_artifact_refs: list[ArtifactLink] = []
            if health_root is not None:
                run_id = context.run.run_id if hasattr(context.run, "run_id") else ""
                if run_id:
                    artifact_path = f"{run_id}-vmalert-rule-state.json"
                    vmalert_artifact_refs.append({
                        "label": "VMAlert Rule State",
                        "path": artifact_path,
                    })

            # Derive ranking reason for critical vmalert item
            ranking_reason = "Critical vmalert alert firing; requires operator attention"

            # Assign rank after existing items (critical alerts rank above informational)
            # Use a high rank to appear near the top
            item_rank = len(items) + 1

            items.append(
                {
                    "id": item_id,
                    "rank": item_rank,
                    "workstream": "incident",  # Critical alerts are incident-class
                    "title": title,
                    "description": description,
                    "command": None,  # Advisory item: no executable command
                    "targetCluster": alert.cluster_label,
                    "targetContext": None,
                    "reason": reason,
                    "expectedEvidence": None,
                    "safetyNote": f"Severity: {alert.severity}; State: {alert.state}",
                    "itemState": _ITEM_STATE_ADVISORY,
                    "approvalState": None,
                    "executionState": None,
                    "feedbackState": None,
                    "sourceType": _SOURCE_TYPE_VMALERT_ALERT,
                    "mergedSources": None,
                    "sourceArtifactRefs": vmalert_artifact_refs,
                    "rankingReason": ranking_reason,
                    "firstRecommendedAt": None,
                    "lastStateChangedAt": None,
                    "recommendationAgeSeconds": None,
                    "stalenessClass": None,
                }
            )

    if not items:
        return None

    # Apply execution artifact overlay to derive actual execution state from artifacts
    # This ensures worklist reflects execution even when queue data is stale
    # Only overlay if the item is not already marked as executed
    for item in items:
        # Get current execution state
        current_execution_state = item.get("executionState") or ""
        
        # Skip if already marked as executed
        if current_execution_state in ("executed-success", "executed-failed", "timed-out", "completed"):
            continue
        
        # Get item fields for matching
        item_candidate_id = item.get("id")  # candidate_id from queue item
        item_candidate_index = None
        item_command_family = None
        item_target_cluster = item.get("targetCluster")
        
        # Extract command_family from source data if available
        # Look in description for command family hints
        description = item.get("description") or ""
        if "kubectl" in description.lower():
            parts = description.lower().split("kubectl")
            if len(parts) > 1:
                cmd_part = parts[1].split()[0] if parts[1].strip() else ""
                if cmd_part:
                    item_command_family = cmd_part
        
        # Try to extract candidate_index from queue items if available
        # Check the queue_item in context if we have matching
        for queue_item in queue_items:
            queue_item_id = queue_item.candidate_id or f"queue-{queue_item.description}"
            if queue_item_id == item_candidate_id:
                item_candidate_index = queue_item.candidate_index if hasattr(queue_item, "candidate_index") else None
                if hasattr(queue_item, "suggested_command_family") and queue_item.suggested_command_family:
                    item_command_family = queue_item.suggested_command_family
                break
        
        # Match against execution overlays
        for overlay in execution_overlays:
            if _match_execution_overlay_to_queue_item(
                overlay=overlay,
                queue_item_candidate_id=str(item_candidate_id) if item_candidate_id else None,
                queue_item_candidate_index=item_candidate_index,
                queue_item_command_family=item_command_family,
                queue_item_target_cluster=item_target_cluster,
            ):
                # Apply overlay - mark as executed
                derived_execution_state = _derive_execution_state_from_artifact(overlay.status)
                item["executionState"] = derived_execution_state
                item["itemState"] = _ITEM_STATE_EXECUTED
                
                # Update lastStateChangedAt from artifact timestamp
                if overlay.timestamp:
                    item["lastStateChangedAt"] = overlay.timestamp
                
                # Add artifact reference if not already present
                if overlay.artifact_path:
                    refs = list(item.get("sourceArtifactRefs") or [])
                    # Check if artifact already in refs
                    artifact_exists = any(
                        ref.get("path") == overlay.artifact_path 
                        for ref in refs
                    )
                    if not artifact_exists:
                        refs.append({
                            "label": "Next-Check Execution",
                            "path": overlay.artifact_path,
                        })
                        item["sourceArtifactRefs"] = refs
                
                # Update ranking reason for executed items
                item["rankingReason"] = _derive_worklist_ranking_reason(
                    source_type=item.get("sourceType"),
                    item_state=_ITEM_STATE_EXECUTED,
                    execution_state=derived_execution_state,
                    is_primary_triage=None,
                    urgency=None,
                    priority_label=cast("str | None", item.get("priorityLabel")),
                    command=item.get("command"),
                    workstream=item.get("workstream"),
                )
                
                # Only match first applicable overlay
                break

    # Apply artifact filtering to worklist item provenance
    # Filter skipped/placeholder artifacts from sourceArtifactRefs to improve quality
    for item in items:
        refs = item.get("sourceArtifactRefs") or []
        filtered_refs = filter_artifact_refs_preserving_minimum(refs)
        item["sourceArtifactRefs"] = filtered_refs

    # Compute counts based on canonical itemState
    completed = sum(
        1
        for item in items
        if item.get("itemState") in (_ITEM_STATE_EXECUTED, _ITEM_STATE_REVIEWED)
        or item.get("executionState") in ("executed-success", "completed")
    )
    blocked = sum(
        1
        for item in items
        if item.get("itemState") == _ITEM_STATE_APPROVAL_NEEDED
        or item.get("approvalState") == "approval-required"
        or item.get("executionState") == "blocked"
    )
    return {
        "items": items,
        "totalItems": len(items),
        "completedItems": completed,
        "pendingItems": len(items) - completed - blocked,
        "blockedItems": blocked,
    }

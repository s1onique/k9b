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

from collections.abc import Mapping
from typing import cast

from ..security.kubectl_context import (
    display_kube_cluster_label,
    is_internal_kube_marker,
    sanitize_kubectl_display_command,
    sanitize_operator_text,
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
    OperatorWorklistItemPayload,
    OperatorWorklistPayload,
)
from .model import UIIndexContext


def _sanitize_target_cluster(cluster: str | None, context: str | None = None) -> str | None:
    """Sanitize a cluster label for operator-facing display.

    Removes internal context markers like "in-cluster" and "in_cluster" from
    cluster labels, returning None if the label is only an internal marker.

    Args:
        cluster: The cluster label to sanitize.
        context: Optional context for fallback if cluster is internal marker.

    Returns:
        Sanitized cluster label, or None if the label is only an internal marker.
    """
    if cluster is None:
        return None
    # If cluster is an internal marker, try to use context as fallback
    if is_internal_kube_marker(cluster):
        if context and not is_internal_kube_marker(context):
            return context
        return None
    return cluster


def _sanitize_target_context(context: str | None) -> str | None:
    """Sanitize a context value for operator-facing display.

    Removes internal context markers like "in-cluster" and "in_cluster".
    Returns None if the context is only an internal marker.

    Args:
        context: The context value to sanitize.

    Returns:
        Sanitized context, or None if the context is an internal marker.
    """
    if context is None:
        return None
    if is_internal_kube_marker(context):
        return None
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
        # Missing evidence is an explicit unknown claim
        for missing in assessment.missing_evidence:
            unknowns.append(
                {
                    "claimType": "unknown",
                    "statement": f"Missing evidence: {missing}",
                    "whyMissing": "Not collected in this run",
                    "sourceArtifactRefs": _assessment_refs(),
                }
            )
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

    # A healthy run with no evidence should still produce an honest empty report
    if status == "healthy" and not facts and not inferences and not unknowns:
        facts.append(
            {
                "claimType": "observed",
                "statement": "No degraded clusters or incidents detected in this run.",
                "sourceArtifactRefs": deduped_refs or [],
                "confidence": "high",
            }
        )

    # Build cross-cluster findings from comparison triggers
    # These provide fleet-level drift visibility that individual cluster assessments may miss
    cross_cluster_findings = _build_cross_cluster_findings_payload(context)

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
        "sourceArtifactRefs": deduped_refs,
        "crossClusterFindings": cross_cluster_findings,
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
) -> OperatorWorklistPayload | None:
    """Derive a ranked operator worklist from deterministic next checks and queue state.

    Unified projection from deterministic next checks, planner candidates,
    and execution history. This is a read-only projection; there is no new
    persistence layer.

    Truthfulness rules:
    - command is None for deterministic/advisory items (they have method, not executable cmd)
    - command is a concrete string for executable queue items
    - itemState reflects canonical state: advisory | approval-needed | approved | queued | executed | reviewed
    - sourceType distinguishes origin for provenance: deterministic | planner | promotion | execution
    - mergedSources preserves all contributing origins when multiple sources refer to the same logical action
    """
    items: list[OperatorWorklistItemPayload] = []

    # Track deterministic IDs for dedupe with queue items
    deterministic_ids: set[str] = set()

    # Prefer deterministic next checks as the primary workstream source
    deterministic = context.run.deterministic_next_checks
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
                        "itemState": _ITEM_STATE_ADVISORY,  # Deterministic = advisory
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
            cast(str | None, item.get("id")) for item in items
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

        items.append(
            {
                "id": item_id,
                "rank": len(items) + 1,
                "workstream": queue_item.workstream,
                # Sanitize all text fields to prevent internal markers from leaking
                "title": queue_title,
                "description": sanitize_operator_text(queue_item.source_reason),
                # Command semantics: sanitized command for executable queue items
                "command": sanitize_kubectl_display_command(queue_item.command_preview) if queue_item.command_preview else None,
                # Sanitize targetCluster and targetContext to prevent "in-cluster" leaks
                "targetCluster": _sanitize_target_cluster(queue_item.target_cluster, queue_item.target_context),
                "targetContext": _sanitize_target_context(queue_item.target_context),
                "reason": sanitize_operator_text(queue_item.source_reason),
                "expectedEvidence": sanitize_operator_text(queue_item.expected_signal),
                "safetyNote": sanitize_operator_text(queue_item.safety_reason),
                "itemState": _derive_item_state(queue_item) or _ITEM_STATE_QUEUED,
                "approvalState": queue_item.approval_state,
                "executionState": queue_item.execution_state,
                "feedbackState": queue_item.outcome_status,
                "sourceType": source_type,
                "mergedSources": None,
                "sourceArtifactRefs": artifact_refs,
            }
        )

    if not items:
        return None

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

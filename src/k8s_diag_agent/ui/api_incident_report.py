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
    }


def _build_operator_worklist_payload(
    context: UIIndexContext,
) -> OperatorWorklistPayload | None:
    """Derive a ranked operator worklist from deterministic next checks and queue state.

    Returns None when there are no actionable items.
    """
    items: list[OperatorWorklistItemPayload] = []

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
                items.append(
                    {
                        "id": f"deterministic-{safe_cluster}-{rank}",
                        "rank": rank,
                        "workstream": summary.workstream,
                        "title": title_str,
                        "description": sanitize_operator_text(
                            f"Owner: {summary.owner}; method: {summary.method}; evidence needed: {', '.join(summary.evidence_needed)}"
                        ),
                        "command": None,
                        "targetCluster": safe_cluster,
                        "targetContext": safe_context,
                        "reason": sanitize_operator_text(summary.why_now),
                        "expectedEvidence": sanitize_operator_text(", ".join(summary.evidence_needed)),
                        "safetyNote": sanitize_operator_text(
                            f"Urgency: {summary.urgency}; primary triage: {summary.is_primary_triage}"
                        ),
                        "approvalState": None,
                        "executionState": None,
                        "feedbackState": None,
                        "sourceArtifactRefs": [
                            {"label": "Assessment", "path": path}
                            for path in [cluster.assessment_artifact_path, cluster.drilldown_artifact_path]
                            if path
                        ],
                    }
                )
                rank += 1

    # Append next-check queue items for execution/approval state enrichment.
    # Queue items are appended rather than merged when there is no shared stable candidate ID,
    # because deterministic checks and planner candidates originate from different artifacts
    # and may describe the same intent with different IDs.
    queue_items = context.run.next_check_queue
    for queue_item in queue_items:
        existing_ids = {cast(str | None, item.get("id")) for item in items}
        item_id = queue_item.candidate_id or f"queue-{queue_item.description}"
        if item_id in existing_ids:
            # Enrich existing item with queue state when IDs match
            for existing in items:
                if existing.get("id") == item_id:
                    existing["approvalState"] = queue_item.approval_state
                    existing["executionState"] = queue_item.execution_state
                    existing["feedbackState"] = queue_item.outcome_status
                    if queue_item.plan_artifact_path:
                        refs = list(existing.get("sourceArtifactRefs") or [])
                        refs.append(
                            {
                                "label": "Next-Check Plan",
                                "path": queue_item.plan_artifact_path,
                            }
                        )
                        existing["sourceArtifactRefs"] = refs
            continue
        # sanitize_operator_text returns str | None but always returns str
        # when input is non-None str
        queue_title = sanitize_operator_text(queue_item.description)
        queue_title = queue_title if queue_title is not None else queue_item.description
        items.append(
            {
                "id": item_id,
                "rank": len(items) + 1,
                "workstream": queue_item.workstream,
                # Sanitize all text fields to prevent internal markers from leaking
                "title": queue_title,
                "description": sanitize_operator_text(queue_item.source_reason),
                "command": sanitize_kubectl_display_command(queue_item.command_preview) if queue_item.command_preview else None,
                # Sanitize targetCluster and targetContext to prevent "in-cluster" leaks
                "targetCluster": _sanitize_target_cluster(queue_item.target_cluster, queue_item.target_context),
                "targetContext": _sanitize_target_context(queue_item.target_context),
                "reason": sanitize_operator_text(queue_item.source_reason),
                "expectedEvidence": sanitize_operator_text(queue_item.expected_signal),
                "safetyNote": sanitize_operator_text(queue_item.safety_reason),
                "approvalState": queue_item.approval_state,
                "executionState": queue_item.execution_state,
                "feedbackState": queue_item.outcome_status,
                "sourceArtifactRefs": [
                    {"label": "Next-Check Plan", "path": path}
                    for path in [queue_item.plan_artifact_path]
                    if path
                ],
            }
        )

    if not items:
        return None

    completed = sum(
        1
        for item in items
        if item.get("executionState") in ("executed-success", "completed")
    )
    blocked = sum(
        1
        for item in items
        if item.get("approvalState") == "approval-required"
        or item.get("executionState") == "blocked"
    )
    return {
        "items": items,
        "totalItems": len(items),
        "completedItems": completed,
        "pendingItems": len(items) - completed - blocked,
        "blockedItems": blocked,
    }

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
"""

from __future__ import annotations

from typing import cast

from .api_payloads import (
    ArtifactLink,
    FreshnessPayload,
    IncidentReportFactPayload,
    IncidentReportInferencePayload,
    IncidentReportPayload,
    IncidentReportUnknownPayload,
    OperatorWorklistItemPayload,
    OperatorWorklistPayload,
)
from .model import UIIndexContext


def _build_incident_report_payload(
    context: UIIndexContext,
    freshness: FreshnessPayload | None,
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
    inferences: list[IncidentReportInferencePayload] = []
    unknowns: list[IncidentReportUnknownPayload] = []
    stale_warnings: list[str] = []
    recommended_actions: list[str] = []
    source_refs: list[ArtifactLink] = []

    def _assessment_refs() -> list[ArtifactLink]:
        path = assessment.artifact_path if assessment else None
        return [{"label": "Assessment", "path": path}] if path else []

    # Build facts from latest assessment when present
    assessment = context.latest_assessment
    if assessment is not None:
        # Health rating is deterministic
        if assessment.health_rating:
            facts.append(
                {
                    "statement": f"Cluster {assessment.cluster_label} health rating is {assessment.health_rating}.",
                    "sourceArtifactRefs": _assessment_refs(),
                    "confidence": "high",
                }
            )
        # Missing evidence is deterministic
        for missing in assessment.missing_evidence:
            unknowns.append(
                {
                    "statement": f"Missing evidence: {missing}",
                    "whyMissing": "Not collected in this run",
                    "sourceArtifactRefs": _assessment_refs(),
                }
            )
        # Hypotheses are inferences
        for hypothesis in assessment.hypotheses:
            inferences.append(
                {
                    "statement": hypothesis.description,
                    "basis": [hypothesis.probable_layer],
                    "confidence": hypothesis.confidence,
                    "sourceArtifactRefs": _assessment_refs(),
                }
            )
        # Recommended action from assessment is deterministic
        if assessment.recommended_action is not None:
            action = assessment.recommended_action
            facts.append(
                {
                    "statement": action.description,
                    "sourceArtifactRefs": _assessment_refs(),
                    "confidence": "high",
                }
            )
            recommended_actions.append(action.description)
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
                    "statement": f"Trigger reasons: {', '.join(findings.trigger_reasons)}",
                    "sourceArtifactRefs": _drilldown_refs(),
                    "confidence": "high",
                }
            )
        if findings.warning_events > 0:
            facts.append(
                {
                    "statement": f"Warning events observed: {findings.warning_events}",
                    "sourceArtifactRefs": _drilldown_refs(),
                    "confidence": "high",
                }
            )
        if findings.non_running_pods > 0:
            facts.append(
                {
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

        inferences.append(
            {
                "statement": review_enrichment.summary,
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
        "inferences": inferences,
        "unknowns": unknowns,
        "staleEvidenceWarnings": stale_warnings,
        "confidence": "high" if facts else "low",
        "freshness": freshness,
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
            for summary in cluster.deterministic_next_check_summaries:
                # Deterministic next checks carry a method name, not an executable command.
                # Leave command None so consumers do not misinterpret it as a runnable string.
                items.append(
                    {
                        "id": f"deterministic-{cluster.label}-{rank}",
                        "rank": rank,
                        "workstream": summary.workstream,
                        "title": summary.description,
                        "description": f"Owner: {summary.owner}; method: {summary.method}; evidence needed: {', '.join(summary.evidence_needed)}",
                        "command": None,
                        "targetCluster": cluster.label,
                        "targetContext": cluster.context,
                        "reason": summary.why_now,
                        "expectedEvidence": ", ".join(summary.evidence_needed),
                        "safetyNote": f"Urgency: {summary.urgency}; primary triage: {summary.is_primary_triage}",
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
        items.append(
            {
                "id": item_id,
                "rank": len(items) + 1,
                "workstream": queue_item.workstream,
                "title": queue_item.description,
                "description": queue_item.source_reason,
                "command": queue_item.command_preview,
                "targetCluster": queue_item.target_cluster,
                "targetContext": queue_item.target_context,
                "reason": queue_item.source_reason,
                "expectedEvidence": queue_item.expected_signal,
                "safetyNote": queue_item.safety_reason,
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

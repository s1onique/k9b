"""Cluster detail serialization functions for the operator UI.

This module contains serializer functions for cluster detail, assessment,
drilldown, and related payloads:

- Findings, hypotheses, next checks, and recommended actions from assessments
- Drilldown availability and coverage summaries
- Assessment summary for cluster detail view
- Auto-interpretation of drilldown data
- Cluster summary and proposal summary for fleet view
- Related proposal/notification filtering

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from .api_payloads import (
    AssessmentSummaryPayload,
    ClusterSummaryPayload,
    DrilldownCoveragePayload,
    DrilldownInterpretationPayload,
    DrilldownSummaryPayload,
    FindingEntry,
    HypothesisEntry,
    NextCheckEntry,
    NotificationEntry,
    ProblemSummary,
    ProposalEntry,
    ProposalSummaryPayload,
    RatingCount,
    RecommendedActionPayload,
    StatusCount,
)
from .model import (
    AssessmentHypothesisView,
    AssessmentNextCheckView,
    AssessmentView,
    AutoDrilldownInterpretationView,
    ClusterView,
    DrilldownAvailabilityView,
    DrilldownCoverageEntry,
    FindingsView,
    NotificationView,
    ProposalView,
    RecommendedActionView,
    UIIndexContext,
)


def _serialize_findings(findings: FindingsView | None) -> FindingEntry:
    """Serialize findings view to payload dict."""
    if findings is None:
        return {
            "label": None,
            "context": None,
            "triggerReasons": [],
            "warningEvents": 0,
            "nonRunningPods": 0,
            "summaryEntries": [],
            "patternDetails": [],
            "rolloutStatus": [],
            "artifactPath": None,
        }
    return {
        "label": findings.label,
        "context": findings.context,
        "triggerReasons": list(findings.trigger_reasons),
        "warningEvents": findings.warning_events,
        "nonRunningPods": findings.non_running_pods,
        "summaryEntries": [{"label": label, "value": value} for label, value in findings.summary],
        "patternDetails": [{"label": label, "value": value} for label, value in findings.pattern_details],
        "rolloutStatus": list(findings.rollout_status),
        "artifactPath": findings.artifact_path,
    }


def _serialize_hypothesis(hypothesis: AssessmentHypothesisView) -> HypothesisEntry:
    """Serialize assessment hypothesis view to payload dict."""
    return {
        "description": hypothesis.description,
        "confidence": hypothesis.confidence,
        "probableLayer": hypothesis.probable_layer,
        "falsifier": hypothesis.what_would_falsify,
    }


def _serialize_next_check(check: AssessmentNextCheckView) -> NextCheckEntry:
    """Serialize assessment next check view to payload dict."""
    return {
        "description": check.description,
        "owner": check.owner,
        "method": check.method,
        "evidenceNeeded": list(check.evidence_needed),
    }


def _serialize_recommended_action(action: RecommendedActionView | None) -> RecommendedActionPayload | None:
    """Serialize recommended action view to payload dict."""
    if not action:
        return None
    return {
        "actionType": action.action_type,
        "description": action.description,
        "references": list(action.references),
        "safetyLevel": action.safety_level,
    }


def _serialize_assessment_summary(assessment: AssessmentView | None) -> AssessmentSummaryPayload | None:
    """Serialize assessment summary view to payload dict."""
    if not assessment:
        return None
    return {
        "healthRating": assessment.health_rating,
        "missingEvidence": list(assessment.missing_evidence),
        "probableLayer": assessment.probable_layer,
        "overallConfidence": assessment.overall_confidence,
        "artifactPath": assessment.artifact_path,
        "snapshotPath": assessment.snapshot_path,
    }


def _serialize_auto_interpretation(interpretation: AutoDrilldownInterpretationView | None) -> DrilldownInterpretationPayload | None:
    """Serialize auto-drilldown interpretation view to payload dict."""
    if not interpretation:
        return None
    payload = dict(interpretation.payload) if interpretation.payload else None
    return {
        "adapter": interpretation.adapter,
        "status": interpretation.status,
        "summary": interpretation.summary,
        "timestamp": interpretation.timestamp,
        "artifactPath": interpretation.artifact_path,
        "provider": interpretation.provider,
        "durationMs": interpretation.duration_ms,
        "payload": payload,
        "errorSummary": interpretation.error_summary,
        "skipReason": interpretation.skip_reason,
    }


def _serialize_drilldown_summary(availability: DrilldownAvailabilityView) -> DrilldownSummaryPayload:
    """Serialize drilldown availability view to payload dict."""
    return {
        "totalClusters": availability.total_clusters,
        "available": availability.available,
        "missing": availability.missing,
        "missingClusters": list(availability.missing_clusters),
    }


def _serialize_drilldown(entry: DrilldownCoverageEntry) -> DrilldownCoveragePayload:
    """Serialize drilldown coverage entry to payload dict."""
    return {
        "label": entry.label,
        "context": entry.context,
        "available": entry.available,
        "timestamp": entry.timestamp,
        "artifactPath": entry.artifact_path,
    }


def _build_problem_summary(context: UIIndexContext) -> ProblemSummary:
    """Build problem summary from UI index context."""
    findings = context.latest_findings
    if findings and findings.trigger_reasons:
        detail = " · ".join(findings.trigger_reasons)
        return {"title": "Trigger reasons", "detail": detail}
    assessment = context.latest_assessment
    if assessment and assessment.findings:
        first = assessment.findings[0]
        return {"title": "Assessment finding", "detail": first.description}
    return {"title": "Fleet status", "detail": "Awaiting fresh evidence"}


def _serialize_cluster(cluster: ClusterView) -> ClusterSummaryPayload:
    """Serialize cluster view to payload dict."""
    return {
        "label": cluster.label,
        "context": cluster.context,
        "clusterClass": cluster.cluster_class,
        "clusterRole": cluster.cluster_role,
        "baselineCohort": cluster.baseline_cohort,
        "controlPlaneVersion": cluster.control_plane_version,
        "healthRating": cluster.health_rating,
        "warnings": cluster.warnings,
        "nonRunningPods": cluster.non_running_pods,
        "latestRunTimestamp": cluster.latest_run_timestamp,
        "topTriggerReason": cluster.top_trigger_reason,
        "drilldownAvailable": cluster.drilldown_available,
        "drilldownTimestamp": cluster.drilldown_timestamp,
        "missingEvidence": list(cluster.missing_evidence),
    }


def _serialize_rating_counts(entries: tuple[tuple[str, int], ...]) -> list[RatingCount]:
    """Serialize rating counts tuple to payload list."""
    return [{"rating": rating, "count": count} for rating, count in entries]


def _serialize_status_counts(entries: tuple[tuple[str, int], ...]) -> list[StatusCount]:
    """Serialize status counts tuple to payload list."""
    return [{"status": status, "count": count} for status, count in entries]


def _build_proposal_summary(context: UIIndexContext) -> ProposalSummaryPayload:
    """Build proposal summary from UI index context."""
    counts = {status.lower(): count for status, count in context.proposal_status_summary.status_counts}
    total = sum(count for count in counts.values())
    return {
        "pending": counts.get("pending", 0),
        "total": total,
        "statusCounts": _serialize_status_counts(context.proposal_status_summary.status_counts),
    }


def _serialize_proposal(proposal: ProposalView) -> ProposalEntry:
    """Serialize proposal view to payload dict."""
    from .api_payloads import ArtifactLink

    artifacts: list[ArtifactLink] = []
    if proposal.artifact_path:
        artifacts.append({"label": "Proposal JSON", "path": proposal.artifact_path})
    if proposal.review_path:
        artifacts.append({"label": "Review JSON", "path": proposal.review_path})
    entry: ProposalEntry = {
        "proposalId": proposal.proposal_id,
        "target": proposal.target,
        "status": proposal.status,
        "confidence": proposal.confidence,
        "rationale": proposal.rationale,
        "expectedBenefit": proposal.expected_benefit,
        "sourceRunId": proposal.source_run_id,
        "latestNote": proposal.latest_note,
        "lifecycle": [{"status": status, "timestamp": timestamp, "note": note} for status, timestamp, note in proposal.lifecycle_history],
        "artifacts": artifacts,
        "artifactId": proposal.artifact_id,
    }
    return entry


def _serialize_notification(entry: NotificationView) -> NotificationEntry:
    """Serialize notification view to payload dict."""
    return {
        "kind": entry.kind,
        "summary": entry.summary,
        "timestamp": entry.timestamp,
        "runId": entry.run_id,
        "clusterLabel": entry.cluster_label,
        "context": entry.context,
        "details": [{"label": label, "value": value} for label, value in entry.details],
        "artifactPath": entry.artifact_path,
        "artifactId": entry.artifact_id,
    }


def _filter_related_proposals(label: str | None, proposals: tuple[ProposalView, ...]) -> list[ProposalEntry]:
    """Filter proposals related to a specific cluster label."""
    if label:
        matching = [p for p in proposals if label in p.target or label in (p.latest_note or "")]
        if matching:
            return [_serialize_proposal(p) for p in matching[:3]]
    return [_serialize_proposal(p) for p in proposals[:3]]


def _filter_related_notifications(label: str | None, notifications: tuple[NotificationView, ...]) -> list[NotificationEntry]:
    """Filter notifications related to a specific cluster label."""
    if label:
        matching = [n for n in notifications if n.cluster_label == label]
        if matching:
            return [_serialize_notification(entry) for entry in matching[:3]]
    return [_serialize_notification(entry) for entry in notifications[:3]]

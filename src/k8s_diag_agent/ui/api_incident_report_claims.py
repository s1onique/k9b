"""Incident report claim builders (facts, derived, unknown, inference, recommendations).

This module contains the claim/fact builder functions for incident report sections
that deal with observations, derivations, unknowns, inferences, and recommendations.

Extracted from api_incident_report_facts.py to keep modules below 500 lines.
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

from typing import cast

from ..security.kubectl_context import sanitize_operator_text
from .api_incident_report_ownership import (
    derive_evidence_ownership,
    format_ownership_fields,
)
from .api_payloads import (
    ArtifactLink,
    IncidentReportDerivedPayload,
    IncidentReportFactPayload,
    IncidentReportInferencePayload,
    IncidentReportRecommendationPayload,
    IncidentReportUnknownPayload,
)


def _build_finding_facts(
    findings: object,
) -> tuple[list[IncidentReportFactPayload], list[ArtifactLink]]:
    """Build fact claims from findings (drilldown) data.

    Args:
        findings: Latest findings artifact with trigger reasons and metrics.

    Returns:
        Tuple of (facts list, source_refs list).
    """
    facts: list[IncidentReportFactPayload] = []
    source_refs: list[ArtifactLink] = []

    if findings is None:
        return facts, source_refs

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

    return facts, source_refs


def _build_assessment_derived_claims(
    assessment: object,
) -> tuple[list[IncidentReportDerivedPayload], list[ArtifactLink]]:
    """Build derived claims from latest assessment.

    Health rating is a deterministic conclusion from evidence fields, not raw telemetry.

    Args:
        assessment: Latest assessment artifact.

    Returns:
        Tuple of (derived claims list, source_refs list).
    """
    from ..security.kubectl_context import display_kube_cluster_label

    derived: list[IncidentReportDerivedPayload] = []
    source_refs: list[ArtifactLink] = []

    if assessment is None:
        return derived, source_refs

    def _assessment_refs() -> list[ArtifactLink]:
        path = assessment.artifact_path if assessment else None
        return [{"label": "Assessment", "path": path}] if path else []

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

    if assessment.artifact_path:
        source_refs.append({"label": "Assessment", "path": assessment.artifact_path})
    if assessment.snapshot_path:
        source_refs.append({"label": "Snapshot", "path": assessment.snapshot_path})

    return derived, source_refs


def _build_unknown_claims(
    assessment: object,
    cluster_count: int,
) -> list[IncidentReportUnknownPayload]:
    """Build unknown/missing-evidence claims from assessment.

    Args:
        assessment: Latest assessment artifact.
        cluster_count: Number of clusters for cross-cluster detection.

    Returns:
        List of unknown claims.
    """
    unknowns: list[IncidentReportUnknownPayload] = []

    if assessment is None:
        return unknowns

    def _assessment_refs() -> list[ArtifactLink]:
        path = assessment.artifact_path if assessment else None
        return [{"label": "Assessment", "path": path}] if path else []

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
            # Copy directly - ownership_fields already contains validated data
            unknown_entry["ownershipConfidence"] = ownership_fields["ownershipConfidence"]
        unknowns.append(unknown_entry)

    return unknowns


def _build_inference_claims(
    assessment: object,
    review_enrichment: object,
) -> tuple[list[IncidentReportInferencePayload], list[ArtifactLink]]:
    """Build inference/hypothesis claims from assessment and review enrichment.

    Sanitizes text to prevent internal markers from leaking to operator UI.

    Args:
        assessment: Latest assessment artifact.
        review_enrichment: Review enrichment artifact (provider-assisted).

    Returns:
        Tuple of (inferences list, source_refs list).
    """
    inferences: list[IncidentReportInferencePayload] = []
    source_refs: list[ArtifactLink] = []

    # Hypotheses are inference/hypothesis claims
    # Sanitize description to prevent internal markers from leaking
    if assessment is not None:
        def _assessment_refs() -> list[ArtifactLink]:
            path = assessment.artifact_path if assessment else None
            return [{"label": "Assessment", "path": path}] if path else []

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

    # Provider-assisted content: review enrichment is explicitly an inference source
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

    return inferences, source_refs


def _build_recommendation_claims(
    assessment: object,
) -> tuple[list[IncidentReportRecommendationPayload], list[str]]:
    """Build recommendation claims from assessment.

    Sanitizes text to prevent internal markers from leaking to operator UI.

    Args:
        assessment: Latest assessment artifact.

    Returns:
        Tuple of (recommendations list, recommended_actions list).
    """
    recommendations: list[IncidentReportRecommendationPayload] = []
    recommended_actions: list[str] = []

    if assessment is None or assessment.recommended_action is None:
        return recommendations, recommended_actions

    action = assessment.recommended_action
    # Sanitize action description to prevent internal markers from leaking
    safe_action_description = sanitize_operator_text(action.description)
    if safe_action_description:
        recommendations.append(
            {
                "claimType": "recommendation",
                "statement": safe_action_description,
                "safetyLevel": action.safety_level or "unknown",
                "sourceArtifactRefs": [],
            }
        )
        recommended_actions.append(safe_action_description)

    return recommendations, recommended_actions


def _deduplicate_refs(source_refs: list[ArtifactLink]) -> list[ArtifactLink]:
    """Deduplicate source refs while preserving order.

    Args:
        source_refs: List of artifact links.

    Returns:
        Deduplicated list preserving original order.
    """
    seen_refs: set[str] = set()
    deduped_refs: list[ArtifactLink] = []
    for ref in source_refs:
        path = ref.get("path")
        if path and path not in seen_refs:
            seen_refs.add(path)
            deduped_refs.append(ref)
    return deduped_refs


def _filter_refs_preserving_minimum(
    deduped_refs: list[ArtifactLink],
) -> list[ArtifactLink]:
    """Apply artifact filtering to improve provenance quality.

    Filter skipped/placeholder artifacts from source refs to avoid noise.
    Use preserving-minimum to ensure claims don't lose all provenance.

    Args:
        deduped_refs: Deduplicated artifact links.

    Returns:
        Filtered artifact links.
    """
    from .api_incident_report_filtering import filter_artifact_refs_preserving_minimum
    return filter_artifact_refs_preserving_minimum(deduped_refs)


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


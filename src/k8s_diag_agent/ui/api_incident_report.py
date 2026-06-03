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
from pathlib import Path
from typing import cast

from .api_incident_report_execution_evidence import _build_diagnostic_execution_evidence
from .api_incident_report_facts import (  # noqa: F401 - re-exported for backward compatibility
    _build_assessment_derived_claims,
    _build_cross_cluster_findings_payload,
    _build_finding_facts,
    _build_inference_claims,
    _build_recommendation_claims,
    _build_unknown_claims,
    _build_vmalert_discovery_context,
    _build_vmalert_rule_state_context,
    _deduplicate_refs,
    _derive_fleet_aware_checks,
    _filter_refs_preserving_minimum,
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
    DiagnosticExecutionEvidencePayload,
    FreshnessPayload,
    IncidentReportPayload,
)
from .model import UIIndexContext

logger = logging.getLogger(__name__)

# _sanitize_target_cluster and _sanitize_target_context are imported from
# api_incident_report_worklist module for backward compatibility


def _build_incident_report_payload(
    context: UIIndexContext,
    freshness: Mapping[str, object] | None,
    health_root: Path | None = None,
) -> IncidentReportPayload | None:
    """Derive an incident report from the existing UI context.

    Returns None when there is no meaningful incident state to report.

    Args:
        context: The UI index context
        freshness: Optional freshness payload for stale evidence warnings
        health_root: Optional path to health root for loading execution artifacts
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

    # Build fact claims from findings (drilldown) data
    findings = context.latest_findings
    facts, finding_refs = _build_finding_facts(findings)

    # Build derived claims from latest assessment
    assessment = context.latest_assessment
    derived, assessment_refs = _build_assessment_derived_claims(assessment)

    # Build unknown/missing-evidence claims
    unknowns = _build_unknown_claims(assessment, cluster_count)

    # Build inference/hypothesis claims from assessment and review enrichment
    review_enrichment = context.review_enrichment
    inferences, inference_refs = _build_inference_claims(assessment, review_enrichment)

    # Build recommendation claims
    recommendations, recommended_actions = _build_recommendation_claims(assessment)

    # Stale evidence warning when freshness supports it
    stale_warnings: list[str] = []
    if freshness is not None:
        freshness_status = freshness.get("status")
        if freshness_status in ("delayed", "stale"):
            stale_warnings.append(
                f"Run freshness is {freshness_status}; some evidence may be stale."
            )

    # Combine source refs from all sections
    source_refs: list[ArtifactLink] = []
    source_refs.extend(assessment_refs)
    source_refs.extend(finding_refs)
    source_refs.extend(inference_refs)

    # Deduplicate and filter source refs
    deduped_refs = _deduplicate_refs(source_refs)
    filtered_refs = _filter_refs_preserving_minimum(deduped_refs)

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
    cross_cluster_findings = _build_cross_cluster_findings_payload(context)

    # Build vmalert discovery context for diagnostic awareness
    vmalert_context = _build_vmalert_discovery_context(context)

    # Build vmalert rule state context for firing/pending alert diagnostics
    vmalert_rule_state_context = _build_vmalert_rule_state_context(context)

    # Build diagnostic execution evidence from execution artifacts
    run_id = context.run.run_id if hasattr(context.run, "run_id") else ""
    diagnostic_execution_evidence: list[DiagnosticExecutionEvidencePayload] | None = None
    if health_root is not None and run_id:
        external_analysis_dir = health_root / "external-analysis"
        evidence_list = _build_diagnostic_execution_evidence(external_analysis_dir, run_id)
        if evidence_list:
            diagnostic_execution_evidence = evidence_list

    payload: IncidentReportPayload = {
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
        "diagnosticExecutionEvidence": diagnostic_execution_evidence,
    }
    return payload


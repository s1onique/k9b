"""Prompt templates for evaluation over snapshot comparisons."""
from __future__ import annotations

import json
import logging
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple

from ..collect.cluster_snapshot import ClusterSnapshot
from ..compare.two_cluster import ClusterComparison, ComparisonIntentMetadata

logger = logging.getLogger(__name__)


def _metadata_summary(snapshot: ClusterSnapshot) -> Dict[str, object]:
    meta = snapshot.metadata
    return {
        "cluster_id": meta.cluster_id,
        "control_plane_version": meta.control_plane_version,
        "node_count": meta.node_count,
        "pod_count": meta.pod_count,
        "region": meta.region,
        "labels": meta.labels,
    }


def _summarize_helm_diffs(helm_diffs: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for release_key in sorted(helm_diffs):
        diff = helm_diffs[release_key]
        primary = diff.get("primary")
        secondary = diff.get("secondary")
        entry: Dict[str, Any] = {"release": release_key}
        if primary and secondary:
            entry["status"] = "version-mismatch"
            entry["primary_chart_version"] = primary.get("chart_version")
            entry["secondary_chart_version"] = secondary.get("chart_version")
            entry["primary_app_version"] = primary.get("app_version")
            entry["secondary_app_version"] = secondary.get("app_version")
        elif primary:
            entry["status"] = "only-in-primary"
            entry["primary_chart_version"] = primary.get("chart_version")
            entry["primary_app_version"] = primary.get("app_version")
        elif secondary:
            entry["status"] = "only-in-secondary"
            entry["secondary_chart_version"] = secondary.get("chart_version")
            entry["secondary_app_version"] = secondary.get("app_version")
        entries.append(entry)
    return entries


def _summarize_crd_diffs(crd_diffs: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for crd_name in sorted(crd_diffs):
        diff = crd_diffs[crd_name]
        primary = diff.get("primary")
        secondary = diff.get("secondary")
        entry: Dict[str, Any] = {"name": crd_name}
        if primary and secondary:
            entry["status"] = "version-mismatch"
            entry["primary_storage_version"] = primary.get("storage_version")
            entry["secondary_storage_version"] = secondary.get("storage_version")
            entry["primary_served_versions"] = primary.get("served_versions")
            entry["secondary_served_versions"] = secondary.get("served_versions")
        elif primary:
            entry["status"] = "only-in-primary"
            entry["primary_storage_version"] = primary.get("storage_version")
        elif secondary:
            entry["status"] = "only-in-secondary"
            entry["secondary_storage_version"] = secondary.get("storage_version")
        entries.append(entry)
    return entries


def _format_categories(label: str, values: Tuple[str, ...]) -> str:
    if not values:
        return f"{label}: none declared"
    return f"{label}: {', '.join(values)}"


def _describe_comparison_context(metadata: Optional[ComparisonIntentMetadata]) -> str:
    if metadata is None:
        return "Comparison intent: unspecified (no metadata provided)\nNotes: none provided\nExpected drift categories: none declared\nSuspicious drift categories: none declared"
    lines: List[str] = []
    intent = metadata.intent or "unspecified"
    lines.append(f"Comparison intent: {intent}")
    notes = metadata.notes or "none provided"
    lines.append(f"Notes: {notes}")
    lines.append(_format_categories("Expected drift categories", metadata.expected_drift_categories))
    lines.append(_format_categories("Suspicious drift categories", metadata.unexpected_drift_categories))
    return "\n".join(lines)


def _build_intent_guidance(metadata: Optional[ComparisonIntentMetadata]) -> str:
    if metadata is None or not metadata.intent:
        return (
            "No comparison intent was declared for this pair, so treat any detected drift as ambiguous and lower overall confidence. "
            "Mention the missing intent when describing hypotheses and next evidence, and avoid assuming the environments share a role."
        )
    guidance_lines: List[str] = [f"Frame your assessment around the declared intent '{metadata.intent}'."]
    if metadata.expected_drift_categories:
        guidance_lines.append(
            "Differences that match the expected drift categories "
            f"({', '.join(metadata.expected_drift_categories)}) should be described as anticipated drift consistent with the intent."
        )
    else:
        guidance_lines.append("No expected drift categories were declared; remain open to new normal patterns for this intent.")
    if metadata.unexpected_drift_categories:
        guidance_lines.append(
            "Treat any difference that falls into the suspicious drift categories "
            f"({', '.join(metadata.unexpected_drift_categories)}) as unexpected for this intent and raise its priority."
        )
    else:
        guidance_lines.append("No suspicious drift categories were declared; rely on the intent description to judge urgency.")
    return " ".join(guidance_lines)


def build_assessment_prompt(
    primary: ClusterSnapshot,
    secondary: ClusterSnapshot,
    comparison: ClusterComparison,
    intent_metadata: Optional[ComparisonIntentMetadata] = None,
) -> str:
    metadata_deltas = comparison.differences.get("metadata", {})
    helm_diffs = comparison.differences.get("helm_releases", {})
    crd_diffs = comparison.differences.get("crds", {})
    helm_summary = _summarize_helm_diffs(helm_diffs)
    crd_summary = _summarize_crd_diffs(crd_diffs)
    statuses = {
        "primary": primary.collection_status.to_dict(),
        "secondary": secondary.collection_status.to_dict(),
    }
    prompt = dedent(
        """
        You are a careful Kubernetes diagnostician.
        The compact context summary for both snapshots follows.

        Primary metadata summary:
        {primary_meta}

        Secondary metadata summary:
        {secondary_meta}

        Metadata deltas:
        {metadata_deltas}

        Helm release changes (count: {helm_diff_count}):
        {helm_changes}

        CRD differences (count: {crd_diff_count}):
        {crd_changes}

        Snapshot collection status:
        {collection_status}

        Comparison context:
        {comparison_context}

        Interpretation guidance:
        {intent_guidance}

        Provide a structured JSON assessment that lists observed signals, findings, hypotheses (with confidence and falsifiable checks), next evidence to collect, recommended actions, safety level, and optional metadata such as probable layer of origin.
        Keep confidence aligned with how much difference exists between the snapshots. If no difference exists, recommend observation-only steps.
        Return JSON only. Do not wrap the object in markdown or add prose outside the single JSON payload, and do not replace the required objects with strings.
        Every key below must match the schema exactly and should not be renamed.

        Schema reminder:
        {{
          "observed_signals": [
            {{
              "id": "signal-1",
              "description": "Description of the detected signal.",
              "layer": "observability|workload|control-plane|network|storage",
              "evidence_id": "unique evidence identifier",
              "severity": "info|warning|critical"
            }}
          ],
          "findings": [
            {{
              "description": "Interpretation of the signal.",
              "supporting_signals": ["signal-1"],
              "layer": "workload|control-plane|network|storage"
            }}
          ],
          "hypotheses": [
            {{
              "description": "Plausible root cause hypothesis.",
              "confidence": "low|medium|high",
              "probable_layer": "node|control-plane|workload|network|storage",
              "what_would_falsify": "How to prove this hypothesis wrong."
            }}
          ],
          "next_evidence_to_collect": [
            {{
              "description": "Actionable diagnostic query.",
              "owner": "platform-engineer|application-owner",
              "method": "kubectl|api|logs|metrics",
              "evidence_needed": ["kubectl get pods"]
            }}
          ],
          "recommended_action": {{
            "type": "observation|mitigation|rollback",
            "description": "Recommended next step.",
            "references": ["signal-1"],
            "safety_level": "low-risk|change-with-caution|potentially-disruptive"
          }},
          "safety_level": "low-risk|change-with-caution|potentially-disruptive",
          "probable_layer_of_origin": "workload|node|control-plane|network|storage",
          "overall_confidence": "low|medium|high"
        }}

        Example list entries and objects to follow the schema exactly:
        observed_signals entry:
        {{
          "id": "signal-diff",
          "description": "Comparison reveals an extra Helm release in the secondary snapshot.",
          "layer": "observability",
          "evidence_id": "comparison.diff",
          "severity": "warning"
        }}
        findings entry:
        {{
          "description": "Helm release count differs between snapshots.",
          "supporting_signals": ["signal-diff"],
          "layer": "workflow"
        }}
        hypotheses entry:
        {{
          "description": "A recent rollout introduced a new Helm release.",
          "confidence": "medium",
          "probable_layer": "workload",
          "what_would_falsify": "Release histories match in both clusters."
        }}
        next_evidence_to_collect entry:
        {{
          "description": "Fetch Helm releases for both snapshots.",
          "owner": "platform-engineer",
          "method": "helm",
          "evidence_needed": ["helm list --all-namespaces --output json"]
        }}
        recommended_action object:
        {{
          "type": "observation",
          "description": "Watch Helm releases until snapshots reconverge.",
          "references": ["signal-diff"],
          "safety_level": "low-risk"
        }}
        "safety_level" value example: "low-risk"
        "probable_layer_of_origin" value example: "workload"
        "overall_confidence" value example: "medium"
        """
    ).format(
        primary_meta=json.dumps(_metadata_summary(primary), indent=2),
        secondary_meta=json.dumps(_metadata_summary(secondary), indent=2),
        metadata_deltas=json.dumps(metadata_deltas, indent=2) if metadata_deltas else "{}",
        helm_diff_count=len(helm_summary),
        helm_changes=json.dumps(helm_summary, indent=2),
        crd_diff_count=len(crd_summary),
        crd_changes=json.dumps(crd_summary, indent=2),
        collection_status=json.dumps(statuses, indent=2),
        comparison_context=_describe_comparison_context(intent_metadata),
        intent_guidance=_build_intent_guidance(intent_metadata),
    )
    logger.info(
        "LLM prompt prepared: helm_diffs=%d, crd_diffs=%d, prompt_chars=%d",
        len(helm_summary),
        len(crd_summary),
        len(prompt),
    )
    return prompt

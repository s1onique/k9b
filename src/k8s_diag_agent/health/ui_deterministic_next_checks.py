"""Deterministic next-check projection logic for UI rendering.

This module extracts the cohesive logic for projecting deterministic next-check
assessments from health snapshots into UI-consumable summaries.

Separated from ui.py to provide a crisp canonical home for:
- Workstream classification (incident / evidence / drift)
- Priority scoring
- Description contextualization
- Evidence entry summarization
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .ui_shared import _relative_path

if TYPE_CHECKING:
    from .loop import DrilldownArtifact, HealthAssessmentArtifact


# Workstream base scores for priority ranking
_WORKSTREAM_BASE_SCORES = {
    "incident": 60,
    "evidence": 40,
    "drift": 20,
}


# Keywords that indicate an incident-related check
_DETERMINISTIC_INCIDENT_KEYWORDS = {
    "pod",
    "pods",
    "container",
    "containers",
    "deployment",
    "deployments",
    "statefulset",
    "statefulsets",
    "daemonset",
    "service",
    "services",
    "restart",
    "crashloop",
    "oom",
    "oomkill",
    "failure",
    "fail",
    "error",
    "timeout",
    "latency",
    "packet",
    "connection",
    "drop",
    "tcpdump",
    "traffic",
    "unhealthy",
    "evict",
    "kubelet",
}


# Keywords that indicate a drift/parity check
_DETERMINISTIC_DRIFT_KEYWORDS = {
    "baseline",
    "drift",
    "parity",
    "version",
    "channel",
    "crd",
    "helm",
    "release",
    "image",
    "policy",
    "configuration",
    "config",
    "upgrade",
    "sync",
}


# Ordered (term, label) pairs for drift reason derivation
_DETERMINISTIC_DRIFT_REASON_LABELS = (
    ("baseline", "Baseline drift"),
    ("parity", "Baseline parity"),
    ("version", "Version parity"),
    ("channel", "Channel parity"),
    ("crd", "CRD parity"),
    ("helm", "Helm release parity"),
    ("release", "Release parity"),
    ("image", "Image parity"),
    ("policy", "Policy parity"),
)


# Methods that indicate immediate incident response
_DETERMINISTIC_INCIDENT_METHODS = ("kubectl exec", "kubectl rollout", "rollout status")


def _tokenize_text(value: str | None) -> set[str]:
    """Tokenize text into lowercase alphanumeric parts for keyword matching."""
    if not value:
        return set()
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if part}


def _collect_evidence_tokens(evidence: Sequence[str] | None) -> set[str]:
    """Collect all tokens from evidence items for classification matching."""
    tokens: set[str] = set()
    if not evidence:
        return tokens
    for item in evidence:
        if item:
            tokens.update(_tokenize_text(str(item)))
    return tokens


def _token_variants(value: str) -> set[str]:
    """Generate singular/plural variants of a token for flexible matching."""
    normalized = {value}
    if value.endswith("s") and len(value) > 1:
        normalized.add(value[:-1])
    elif not value.endswith("s"):
        normalized.add(f"{value}s")
    return normalized


def _mentions_top_problem(description: str | None, top_problem: str | None) -> bool:
    """Check if description mentions tokens from top_problem."""
    if not top_problem or not description:
        return False
    top_tokens = _tokenize_text(top_problem)
    desc_tokens = _tokenize_text(description)
    return bool(top_tokens and any(token in desc_tokens for token in top_tokens))


def _derive_deterministic_context(drilldown: DrilldownArtifact | None) -> dict[str, str | None]:
    """Derive namespace and workload context from drilldown artifact.

    Extracts the most relevant workload and namespace for contextualizing
    deterministic next-check descriptions.
    """
    if drilldown is None:
        return {"namespace": None, "workload": None}
    workload_namespace: str | None = None
    workload_text: str | None = None
    for entry in drilldown.affected_workloads:
        name = str(entry.get("name") or "").strip()
        kind = str(entry.get("kind") or "").strip()
        namespace = str(entry.get("namespace") or "").strip()
        display = ""
        if kind and name:
            display = f"{kind}/{name}"
        elif name:
            display = name
        elif kind:
            display = kind
        if display:
            if namespace:
                display = f"{display} in {namespace}"
            workload_text = display
            workload_namespace = namespace or workload_namespace
            break
        if namespace and not workload_namespace:
            workload_namespace = namespace
    if not workload_text:
        for ns in drilldown.affected_namespaces:
            if ns:
                workload_namespace = workload_namespace or ns
                break
    if not workload_namespace:
        for event in drilldown.warning_events:
            if event.namespace:
                workload_namespace = workload_namespace or event.namespace
                break
    return {"namespace": workload_namespace, "workload": workload_text}


def _derive_deterministic_top_problem(
    cluster: dict[str, object],
    drilldown: DrilldownArtifact | None,
) -> str | None:
    """Derive the top problem/trigger reason for contextualizing next checks."""
    if drilldown and drilldown.trigger_reasons:
        return drilldown.trigger_reasons[0]
    reason = cluster.get("top_trigger_reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return None


def _summarize_next_evidence_entries(
    artifact: HealthAssessmentArtifact,
) -> list[dict[str, object]]:
    """Extract and normalize next_evidence_to_collect entries from assessment payload."""
    payload = artifact.assessment if isinstance(artifact.assessment, Mapping) else {}
    raw_next_checks = payload.get("next_evidence_to_collect")
    if not isinstance(raw_next_checks, Sequence) or isinstance(raw_next_checks, (str, bytes, bytearray)):
        return []
    summaries: list[dict[str, object]] = []
    for entry in raw_next_checks:
        if not isinstance(entry, Mapping):
            continue
        description = str(entry.get("description") or "").strip()
        owner = str(entry.get("owner") or "platform")
        method = str(entry.get("method") or "").strip()
        evidence_raw = entry.get("evidence_needed")
        if isinstance(evidence_raw, Sequence) and not isinstance(evidence_raw, (str, bytes, bytearray)):
            evidence = [str(item) for item in evidence_raw if item is not None]
        else:
            evidence = []
        summaries.append(
            {
                "description": description or "Next evidence",
                "owner": owner,
                "method": method,
                "evidenceNeeded": evidence,
            }
        )
    return summaries


def _rewrite_deterministic_next_check_description(
    summary: dict[str, object],
    cluster_label: str | None,
    cluster_context: str | None,
    top_problem: str | None,
    context: dict[str, str | None],
) -> None:
    """Rewrite generic template descriptions to be more specific.

    Mutates summary in-place, adding _generic_template marker for scoring.
    """
    description = str(summary.get("description") or "").strip()
    normalized = description.lower()
    cluster_name = cluster_label or cluster_context or "the cluster"
    namespace = context.get("namespace")
    workload = context.get("workload")
    if normalized == "review node, pod, and control plane status before taking action." or (
        "node" in normalized and "control plane" in normalized and "review" in normalized
    ):
        prefix = f"Review {cluster_name}'s node, pod, and control plane status"
        if workload:
            prefix += f" around {workload}"
        elif namespace:
            prefix += f" in {namespace}"
        if top_problem:
            prefix += f" for {top_problem}"
        summary["description"] = f"{prefix} before taking action."
        summary["_generic_template"] = "status_review"
        return
    if normalized == "investigate the flagged nodes, pods, jobs, and warning events." or "flagged nodes" in normalized:
        prefix = f"Investigate flagged nodes, pods, jobs, and warning events on {cluster_name}"
        if workload:
            prefix += f" targeting {workload}"
        elif namespace:
            prefix += f" in {namespace}"
        if top_problem:
            prefix += f" tied to {top_problem}"
        summary["description"] = f"{prefix}."
        summary["_generic_template"] = "flagged_investigation"


def _classify_deterministic_next_check(
    summary: Mapping[str, object], top_problem: str | None
) -> dict[str, object]:
    """Classify a deterministic next-check into workstream and urgency.

    Uses keyword matching on description, method, and evidence to determine
    whether this is an incident response, drift follow-up, or evidence gathering.

    Returns a dict with:
    - workstream: "incident", "evidence", or "drift"
    - urgency: "high", "medium", or "low"
    - isPrimaryTriage: bool
    - whyNow: human-readable reason
    """
    description = str(summary.get("description") or "").lower()
    method = str(summary.get("method") or "").lower()
    evidence_raw = summary.get("evidenceNeeded")
    if isinstance(evidence_raw, Sequence) and not isinstance(evidence_raw, (str, bytes, bytearray)):
        evidence = [str(item) for item in evidence_raw if item is not None]
    else:
        evidence = []
    desc_tokens = _tokenize_text(description)
    method_tokens = _tokenize_text(method)
    evidence_tokens = _collect_evidence_tokens(evidence)
    all_tokens = desc_tokens | method_tokens | evidence_tokens
    top_problem_tokens = _tokenize_text(top_problem)

    def _matches_top_problem() -> bool:
        if not top_problem_tokens:
            return False
        for token in top_problem_tokens:
            if token and any(variant in all_tokens for variant in _token_variants(token)):
                return True
        return False

    def _method_immediate() -> bool:
        for command in _DETERMINISTIC_INCIDENT_METHODS:
            if command in method:
                return True
        return False

    def _method_log_or_describe() -> bool:
        return "describe" in method or "log" in method or "logs" in method

    incident_tokens_match = bool(all_tokens & _DETERMINISTIC_INCIDENT_KEYWORDS)
    if _matches_top_problem() or _method_immediate() or (_method_log_or_describe() and incident_tokens_match):
        summary_reason = (
            f"Immediate triage for {top_problem}" if top_problem else "Immediate triage for degraded cluster"
        )
        return {
            "workstream": "incident",
            "urgency": "high",
            "isPrimaryTriage": True,
            "whyNow": summary_reason,
        }

    drift_tokens_match = bool(all_tokens & _DETERMINISTIC_DRIFT_KEYWORDS)
    if drift_tokens_match:
        drift_reason = next(
            (label for term, label in _DETERMINISTIC_DRIFT_REASON_LABELS if term in all_tokens),
            None,
        )
        if drift_reason:
            why_now = f"{drift_reason} follow-up"
        else:
            why_now = "Drift / toil follow-up"
        return {
            "workstream": "drift",
            "urgency": "low",
            "isPrimaryTriage": False,
            "whyNow": why_now,
        }

    evidence_reason = (
        f"Gather additional evidence for {top_problem}" if top_problem else "Gather additional evidence"
    )
    return {
        "workstream": "evidence",
        "urgency": "medium",
        "isPrimaryTriage": False,
        "whyNow": evidence_reason,
    }


def _score_deterministic_next_check(
    summary: dict[str, object],
    top_problem: str | None,
    context: dict[str, str | None],
) -> None:
    """Compute priority score for a deterministic next-check.

    Mutates summary in-place, adding priorityScore field.
    Higher scores indicate higher priority for operator attention.
    """
    generic_template = summary.pop("_generic_template", None)
    workstream = str(summary.get("workstream") or "evidence")
    urgency = str(summary.get("urgency") or "").lower()
    score = _WORKSTREAM_BASE_SCORES.get(workstream, 30)
    if summary.get("isPrimaryTriage"):
        score += 20
    if urgency == "high":
        score += 10
    elif urgency == "medium":
        score += 5
    if _mentions_top_problem(str(summary.get("description")), top_problem):
        score += 8
    workload = context.get("workload")
    namespace = context.get("namespace")
    if workload:
        score += 10
    elif namespace:
        score += 5
    if generic_template == "status_review":
        score -= 15
    elif generic_template == "flagged_investigation":
        score -= 10
    summary["priorityScore"] = max(score, 0)


def _build_deterministic_next_checks_projection(
    clusters: Sequence[dict[str, object]],
    assessment_map: Mapping[str, HealthAssessmentArtifact | None],
    drilldown_map: Mapping[str, DrilldownArtifact],
    root_dir: Path,
) -> dict[str, object]:
    """Build the deterministic next-checks projection for the UI index.

    Iterates over degraded clusters, extracts next_evidence_to_collect from
    assessments, classifies and scores each check, and returns a structured
    projection suitable for UI rendering.
    """
    entries: list[dict[str, object]] = []
    total_next_checks = 0
    degraded_labels = [
        str(cluster.get("label"))
        for cluster in clusters
        if str(cluster.get("health_rating") or "").lower() == "degraded"
    ]
    for cluster in clusters:
        rating = str(cluster.get("health_rating") or "").lower()
        if rating != "degraded":
            continue
        label = str(cluster.get("label") or "")
        if not label:
            continue
        assessment = assessment_map.get(label)
        if not assessment:
            continue
        summaries = _summarize_next_evidence_entries(assessment)
        if not summaries:
            continue
        drilldown = drilldown_map.get(label)
        top_problem = _derive_deterministic_top_problem(cluster, drilldown)
        context = _derive_deterministic_context(drilldown)
        for summary in summaries:
            _rewrite_deterministic_next_check_description(
                summary,
                label,
                str(cluster.get("context") or ""),
                top_problem,
                context,
            )
        # annotate classification metadata for each predicted check
        for s in summaries:
            s.update(_classify_deterministic_next_check(s, top_problem))
            _score_deterministic_next_check(s, top_problem, context)
        def _priority_sort_key(entry: dict[str, object]) -> tuple[int, str]:
            raw_score = entry.get("priorityScore")
            magnitude = 0
            if isinstance(raw_score, (int, float)):
                magnitude = int(raw_score)
            description = str(entry.get("description") or "")
            return (-magnitude, description)

        summaries.sort(key=_priority_sort_key)
        total_next_checks += len(summaries)
        entries.append(
            {
                "label": label,
                "context": str(cluster.get("context") or ""),
                "topProblem": top_problem,
                "triggerReason": top_problem,
                "deterministicNextCheckCount": len(summaries),
                "deterministicNextCheckSummaries": summaries,
                "drilldownAvailable": bool(drilldown),
                "assessmentArtifactPath": _relative_path(
                    root_dir, assessment.artifact_path
                ),
                "drilldownArtifactPath": _relative_path(
                    root_dir, drilldown.artifact_path if drilldown else None
                ),
            }
        )
    return {
        "clusterCount": len(degraded_labels),
        "totalNextCheckCount": total_next_checks,
        "clusters": entries,
    }

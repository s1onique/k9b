"""Prompt builder for LLM assessments that focus on drilldown artifacts."""

from __future__ import annotations

import json
from textwrap import dedent

from ..health.drilldown import DrilldownArtifact
from ..security import sanitize_prompt


def _format_table(items: list[str], header: str) -> str:
    if not items:
        return f"{header}: none"
    return f"{header}:\n" + "\n".join(f"- {line}" for line in items)


def _summarize_descriptions(descriptions: dict[str, str]) -> str:
    if not descriptions:
        return "No pod descriptions were captured."
    lines: list[str] = []
    for index, (key, value) in enumerate(descriptions.items()):
        if index >= 2:
            lines.append("... (additional pod descriptions omitted)")
            break
        lines.append(f"{key}: {value}")
    return "Pod descriptions:\n" + "\n---\n".join(lines)


def _join_lines(items: list[str]) -> str:
    """Join list items with newlines, returning 'none' if empty."""
    return "\n".join(items) if items else "none"


def _truncate_events(event_lines: list[str], max_items: int = 5) -> tuple[list[str], int]:
    """Truncate event lines to max_items, return (lines, total_count)."""
    total = len(event_lines)
    truncated = event_lines[:max_items]
    return truncated, total


def _truncate_pods(pod_lines: list[str], max_items: int = 5) -> tuple[list[str], int]:
    """Truncate pod lines to max_items, return (lines, total_count)."""
    total = len(pod_lines)
    truncated = pod_lines[:max_items]
    return truncated, total


def _truncate_rollouts(rollout_lines: list[str], max_items: int = 3) -> tuple[list[str], int]:
    """Truncate rollout lines to max_items, return (lines, total_count)."""
    total = len(rollout_lines)
    truncated = rollout_lines[:max_items]
    return truncated, total


def build_drilldown_prompt(artifact: DrilldownArtifact) -> str:
    # Truncate bulky input sections to reduce prompt size
    event_lines, event_count = _truncate_events(
        [json.dumps(event.to_dict(), indent=2) for event in artifact.warning_events],
        max_items=5,
    )
    pod_lines, pod_count = _truncate_pods(
        [f"{pod.namespace}/{pod.name} ({pod.phase}) reason={pod.reason}" for pod in artifact.non_running_pods],
        max_items=5,
    )
    rollout_lines, rollout_count = _truncate_rollouts(
        [f"{entry.kind} {entry.namespace}/{entry.name}: desired={entry.desired_replicas}, available={entry.available_replicas}, unavailable={entry.unavailable_replicas}" for entry in artifact.rollout_status],
        max_items=3,
    )

    # Schema reminder matching AssessorAssessment.from_dict() required fields:
    # - observed_signals[].id, description, layer, evidence_id, severity
    # - findings[].description, supporting_signals, layer
    # - hypotheses[].description, confidence, probable_layer, what_would_falsify
    # - next_evidence_to_collect[].description, owner, method, evidence_needed
    # - recommended_action.type, description, references, safety_level
    schema_reminder = (
        '{"observed_signals": [{"id": "sig-1", "description": "Brief signal.", '
        '"layer": "workload|control-plane|network|storage", "evidence_id": "evt-1", '
        '"severity": "info|warning|critical"}], '
        '"findings": [{"description": "Brief finding.", "supporting_signals": ["sig-1"], '
        '"layer": "workload|control-plane|network|storage"}], '
        '"hypotheses": [{"description": "Brief hypothesis.", "confidence": "low|medium|high", '
        '"probable_layer": "node|control-plane|workload|network|storage", '
        '"what_would_falsify": "Brief falsification check."}], '
        '"next_evidence_to_collect": [{"description": "Brief diagnostic query.", "owner": "platform-engineer", '
        '"method": "kubectl|api|logs|metrics", "evidence_needed": ["kubectl top pod"]}], '
        '"recommended_action": {"type": "observation|mitigation|rollback", '
        '"description": "Brief action.", "references": ["sig-1"], '
        '"safety_level": "low-risk|change-with-caution|potentially-disruptive"}, '
        '"safety_level": "low-risk|change-with-caution|potentially-disruptive", '
        '"probable_layer_of_origin": "workload|node|control-plane|network|storage", '
        '"overall_confidence": "low|medium|high"}'
    )

    prompt = dedent(
        f"""
        You are a careful Kubernetes diagnostician.
        The following drilldown artifact collects targeted evidence for a triggered health run.

        Return ONLY JSON. No markdown. No prose. Use short strings.
        Use evidence_id values like evt-1, evt-2 when exact IDs are unavailable.

        Artifact summary:
        run_label: {artifact.run_label}
        run_id: {artifact.run_id}
        context: {artifact.context}
        label: {artifact.label}
        cluster_id: {artifact.cluster_id}
        snapshot_timestamp: {artifact.snapshot_timestamp.isoformat()}
        artifact_timestamp: {artifact.timestamp.isoformat()}
        trigger_reasons: {"; ".join(artifact.trigger_reasons) or "none"}
        missing_evidence: {", ".join(artifact.missing_evidence) or "none"}

        Evidence summary:
        {json.dumps(artifact.evidence_summary, indent=2)}

        Warning events (showing {len(event_lines)} of {event_count} total{", top 5 by timestamp" if event_count > 5 else ""}):
        {_join_lines(event_lines)}

        Non-running pods (showing {len(pod_lines)} of {pod_count} total):
        {_join_lines(pod_lines)}

        Rollout/Deployment snapshots (showing {len(rollout_lines)} of {rollout_count} total):
        {_join_lines(rollout_lines)}

        Affected namespaces: {", ".join(artifact.affected_namespaces) or "none"}
        Evidence collection timestamps: {json.dumps(artifact.collection_timestamps, indent=2)}

        {_summarize_descriptions(artifact.pod_descriptions)}

        Provide a concise structured JSON assessment that follows the schema exactly. Focus on the highest-signal evidence and recommend the next safest diagnostic step.
        Schema reminder (observe limits - produce no more than 2 items per list):
        {schema_reminder}

        Constraint: max 2 items each for observed_signals, findings, hypotheses, next_evidence_to_collect. Keep descriptions under 60 characters. Do not explain every event.
        """
    )
    return sanitize_prompt(prompt)

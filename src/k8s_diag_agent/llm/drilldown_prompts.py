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
        if index >= 3:
            lines.append("... (additional pod descriptions omitted)")
            break
        lines.append(f"{key}: {value}")
    return "Pod descriptions:\n" + "\n---\n".join(lines)


def _join_lines(items: list[str]) -> str:
    """Join list items with newlines, returning 'none' if empty."""
    return "\n".join(items) if items else "none"


def build_drilldown_prompt(artifact: DrilldownArtifact) -> str:
    event_lines = [json.dumps(event.to_dict(), indent=2) for event in artifact.warning_events]
    pod_lines = [f"{pod.namespace}/{pod.name} ({pod.phase}) reason={pod.reason}" for pod in artifact.non_running_pods]
    rollout_lines = [f"{entry.kind} {entry.namespace}/{entry.name}: desired={entry.desired_replicas}, available={entry.available_replicas}, unavailable={entry.unavailable_replicas}" for entry in artifact.rollout_status]

    schema_reminder = (
        '{"observed_signals": [{"id": "signal-1", "description": "Brief signal.", '
        '"layer": "workload|control-plane|network|storage", "severity": "info|warning|critical"}], '
        '"findings": [{"description": "Brief finding.", "layer": "workload|control-plane|network|storage"}], '
        '"hypotheses": [{"description": "Brief hypothesis.", "confidence": "low|medium|high", '
        '"probable_layer": "node|control-plane|workload|network|storage", '
        '"what_would_falsify": "Brief falsification check."}], '
        '"next_evidence_to_collect": [{"description": "Brief diagnostic query.", "method": "kubectl|api|logs|metrics"}], '
        '"recommended_action": {"type": "observation|mitigation|rollback", "description": "Brief action.", '
        '"safety_level": "low-risk|change-with-caution|potentially-disruptive"}, '
        '"safety_level": "low-risk|change-with-caution|potentially-disruptive", '
        '"probable_layer_of_origin": "workload|node|control-plane|network|storage", '
        '"overall_confidence": "low|medium|high"}'
    )

    prompt = dedent(
        f"""
        You are a careful Kubernetes diagnostician.
        The following drilldown artifact collects targeted evidence for a triggered health run.

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

        Warning events (count: {len(artifact.warning_events)}):
        {_join_lines(event_lines)}

        Non-running pods (count: {len(artifact.non_running_pods)}):
        {_join_lines(pod_lines)}

        Rollout/Deployment snapshots:
        {_join_lines(rollout_lines)}

        Affected namespaces: {", ".join(artifact.affected_namespaces) or "none"}
        Evidence collection timestamps: {json.dumps(artifact.collection_timestamps, indent=2)}

        {_summarize_descriptions(artifact.pod_descriptions)}

        Provide a concise structured JSON assessment that follows the schema exactly. Focus on the highest-signal evidence and recommend the next safest diagnostic step.
        Schema reminder (observe limits - produce no more than 3 items per list):
        {schema_reminder}

        Constraint: max 3 items each for observed_signals, findings, hypotheses, next_evidence_to_collect. Keep descriptions under 80 characters. Do not include exhaustive event listings.
        """
    )
    return sanitize_prompt(prompt)

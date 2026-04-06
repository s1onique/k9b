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


def build_drilldown_prompt(artifact: DrilldownArtifact) -> str:
    event_lines = [json.dumps(event.to_dict(), indent=2) for event in artifact.warning_events]
    pod_lines = [f"{pod.namespace}/{pod.name} ({pod.phase}) reason={pod.reason}" for pod in artifact.non_running_pods]
    rollout_lines = [f"{entry.kind} {entry.namespace}/{entry.name}: desired={entry.desired_replicas}, available={entry.available_replicas}, unavailable={entry.unavailable_replicas}" for entry in artifact.rollout_status]
    prompt = dedent(
        """
        You are a careful Kubernetes diagnostician.
        The following drilldown artifact collects targeted evidence for a triggered health run.

        Artifact summary:
        run_label: {run_label}
        run_id: {run_id}
        context: {context}
        label: {label}
        cluster_id: {cluster_id}
        snapshot_timestamp: {snapshot_timestamp}
        artifact_timestamp: {artifact_timestamp}
        trigger_reasons: {trigger_reasons}
        missing_evidence: {missing_evidence}

        Evidence summary:
        {evidence_summary}

        Warning events (count: {warning_count}):
        {warning_events}

        Non-running pods (count: {pod_count}):
        {non_running_pods}

        Rollout/Deployment snapshots:
        {rollout_status}

        Affected namespaces: {namespaces}
        Evidence collection timestamps: {collection_timestamps}

        {pod_descriptions}

        Provide a structured JSON assessment that follows the schema exactly.  Focus on the evidence listed above, explain what additional evidence would falsify your leading hypotheses, and recommend the next safest diagnostic steps.

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
        """
    ).format(
        run_label=artifact.run_label,
        run_id=artifact.run_id,
        context=artifact.context,
        label=artifact.label,
        cluster_id=artifact.cluster_id,
        snapshot_timestamp=artifact.snapshot_timestamp.isoformat(),
        artifact_timestamp=artifact.timestamp.isoformat(),
        trigger_reasons="; ".join(artifact.trigger_reasons) or "none",
        missing_evidence=", ".join(artifact.missing_evidence) or "none",
        evidence_summary=json.dumps(artifact.evidence_summary, indent=2),
        warning_count=len(artifact.warning_events),
        warning_events="\n".join(event for event in event_lines) if event_lines else "none",
        pod_count=len(artifact.non_running_pods),
        non_running_pods="\n".join(pod_lines) if pod_lines else "none",
        rollout_status="\n".join(rollout_lines) if rollout_lines else "none",
        namespaces=", ".join(artifact.affected_namespaces) or "none",
        collection_timestamps=json.dumps(artifact.collection_timestamps, indent=2),
        pod_descriptions=_summarize_descriptions(artifact.pod_descriptions),
    )
    return sanitize_prompt(prompt)

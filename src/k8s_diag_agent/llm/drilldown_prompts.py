"""Prompt builder for LLM assessments that focus on drilldown artifacts."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import TYPE_CHECKING

from ..security import sanitize_prompt
from ..security.anonymizer import MetadataAnonymizer
from .prompt_boundaries import (
    BEGIN_OUTPUT_SCHEMA,
    BEGIN_UNTRUSTED_CLUSTER_DATA,
    END_OUTPUT_SCHEMA,
    END_UNTRUSTED_CLUSTER_DATA,
)
from .semantic_injection_detector import (
    build_security_note,
    detect_semantic_injection,
)

if TYPE_CHECKING:
    from ..health.drilldown import DrilldownArtifact


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
    # Create single anonymizer instance to preserve alias consistency within prompt
    anonymizer = MetadataAnonymizer()

    # Anonymize artifact-level string fields that may contain cluster identifiers
    # Wrap each in a dict to give the anonymizer context for proper anonymization
    anon_cluster_id_data = anonymizer.anonymize({"cluster_id": artifact.cluster_id})
    anon_cluster_id = anon_cluster_id_data.get("cluster_id", artifact.cluster_id)

    anon_context_data = anonymizer.anonymize({"context": artifact.context})
    anon_context = anon_context_data.get("context", artifact.context)

    anon_label_data = anonymizer.anonymize({"label": artifact.label})
    anon_label = anon_label_data.get("label", artifact.label)

    anon_run_label_data = anonymizer.anonymize({"run_label": artifact.run_label})
    anon_run_label = anon_run_label_data.get("run_label", artifact.run_label)

    # Anonymize affected_namespaces - each namespace string needs context for proper anonymization
    # Wrap each namespace in a dict with "namespace" key, then extract the anonymized values
    affected_ns_list = list(artifact.affected_namespaces)
    anon_affected_namespaces_list = []
    for ns in affected_ns_list:
        anon_ns_data = anonymizer.anonymize({"namespace": ns})
        anon_affected_namespaces_list.append(anon_ns_data.get("namespace", ns))
    anon_affected_namespaces = anon_affected_namespaces_list

    # Anonymize evidence summary
    anon_evidence_summary = artifact.evidence_summary
    if artifact.evidence_summary:
        anon_evidence_summary_data = anonymizer.anonymize({"evidence_summary": artifact.evidence_summary})
        anon_evidence_summary = anon_evidence_summary_data.get("evidence_summary", artifact.evidence_summary)

    # Truncate bulky input sections to reduce prompt size
    # Anonymize event data
    event_data_for_anonymization = [event.to_dict() for event in artifact.warning_events]
    anon_event_data = anonymizer.anonymize(event_data_for_anonymization)
    event_lines, event_count = _truncate_events(
        [json.dumps(event, indent=2) for event in anon_event_data],
        max_items=5,
    )

    # Build pod lines with anonymized namespaces/names
    anon_pods = [
        {"namespace": pod.namespace, "name": pod.name, "phase": pod.phase, "reason": pod.reason}
        for pod in artifact.non_running_pods
    ]
    anon_pod_data = anonymizer.anonymize(anon_pods)
    pod_lines, pod_count = _truncate_pods(
        [f"{pod['namespace']}/{pod['name']} ({pod['phase']}) reason={pod['reason']}" for pod in anon_pod_data],
        max_items=5,
    )

    # Build rollout lines with anonymized namespaces/names
    anon_rollouts = [
        entry.to_dict() for entry in artifact.rollout_status
    ]
    anon_rollout_data = anonymizer.anonymize(anon_rollouts)
    rollout_lines, rollout_count = _truncate_rollouts(
        [f"{entry['kind']} {entry['namespace']}/{entry['name']}: desired={entry['desired_replicas']}, available={entry['available_replicas']}, unavailable={entry['unavailable_replicas']}" for entry in anon_rollout_data],
        max_items=3,
    )

    # Anonymize pod descriptions (keys are namespace/name format)
    anon_descriptions: dict[str, str] = {}
    for key, value in artifact.pod_descriptions.items():
        # Key is in format "namespace/name" - anonymize it
        parts = key.split("/", 1)
        if len(parts) == 2:
            ns, name = parts
            anon_key_data = anonymizer.anonymize({"namespace": ns, "name": name})
            anon_key = f"{anon_key_data.get('namespace', ns)}/{anon_key_data.get('name', name)}"
        else:
            anon_key = key
        anon_descriptions[anon_key] = value

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

    # Build untrusted data section with boundary markers
    untrusted_data = dedent(
        f"""
        Artifact summary:
        run_label: {anon_run_label}
        run_id: {artifact.run_id}
        context: {anon_context}
        label: {anon_label}
        cluster_id: {anon_cluster_id}
        snapshot_timestamp: {artifact.snapshot_timestamp.isoformat()}
        artifact_timestamp: {artifact.timestamp.isoformat()}
        trigger_reasons: {"; ".join(artifact.trigger_reasons) or "none"}
        missing_evidence: {", ".join(artifact.missing_evidence) or "none"}

        Evidence summary:
        {json.dumps(anon_evidence_summary, indent=2)}

        Warning events (showing {len(event_lines)} of {event_count} total{", top 5 by timestamp" if event_count > 5 else ""}):
        {_join_lines(event_lines)}

        Non-running pods (showing {len(pod_lines)} of {pod_count} total):
        {_join_lines(pod_lines)}

        Rollout/Deployment snapshots (showing {len(rollout_lines)} of {rollout_count} total):
        {_join_lines(rollout_lines)}

        Affected namespaces: {", ".join(str(ns) for ns in anon_affected_namespaces) or "none"}
        Evidence collection timestamps: {json.dumps(artifact.collection_timestamps, indent=2)}

        {_summarize_descriptions(anon_descriptions)}
        """
    )

    # Build output schema section with boundary markers
    output_schema = dedent(
        """
        Return ONLY JSON. No markdown. No prose. Use short strings.
        Use evidence_id values like evt-1, evt-2 when exact IDs are unavailable.

        Provide a concise structured JSON assessment that follows the schema exactly. Focus on the highest-signal evidence and recommend the next safest diagnostic step.
        Schema reminder (observe limits - produce no more than 2 items per list):
        {schema_reminder}

        Constraint: max 2 items each for observed_signals, findings, hypotheses, next_evidence_to_collect. Keep descriptions under 60 characters. Do not explain every event.
        """
    ).format(schema_reminder=schema_reminder)

    # Detect semantic injection patterns in untrusted data
    # This is deterministic and does NOT make LLM calls
    injection_findings = detect_semantic_injection(untrusted_data)

    # Build security note if suspicious patterns detected
    # The note is placed OUTSIDE the untrusted boundary (in trusted instruction area)
    # to ensure the LLM sees it as a directive, not as untrusted data
    # Security note format: [UNTRUSTED_EVIDENCE_SECURITY_NOTE] ... [/UNTRUSTED_EVIDENCE_SECURITY_NOTE]
    security_note = build_security_note(injection_findings)

    # Compose prompt with explicit boundaries:
    # 1. Trusted instruction header
    # 2. Optional security note (only if injection patterns detected)
    # 3. Untrusted data section (wrapped with boundary markers, preserved verbatim)
    # 4. Trusted output schema section (outside untrusted markers)
    prompt_parts = [
        "You are a careful Kubernetes diagnostician.\n"
        "The following drilldown artifact collects targeted evidence for a triggered health run.\n",
    ]

    # Add security note if injection patterns detected
    # This warns the LLM to treat suspicious evidence as data only
    if security_note:
        prompt_parts.append(f"\n{security_note}\n")

    # Add untrusted data section (suspicious content preserved verbatim)
    prompt_parts.append(f"\n{BEGIN_UNTRUSTED_CLUSTER_DATA}\n{untrusted_data}\n{END_UNTRUSTED_CLUSTER_DATA}\n")

    # Add output schema section
    prompt_parts.append(f"{BEGIN_OUTPUT_SCHEMA}\n{output_schema}\n{END_OUTPUT_SCHEMA}\n")

    prompt = "".join(prompt_parts)
    return sanitize_prompt(prompt)

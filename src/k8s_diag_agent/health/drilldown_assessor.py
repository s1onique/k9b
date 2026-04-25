"""Evaluate a drilldown artifact with the shared LLM seam."""
from __future__ import annotations

import json

from ..llm.assessor_schema import AssessorAssessment
from ..llm.base import LLMAssessmentInput
from ..llm.drilldown_prompts import build_drilldown_prompt
from ..llm.prompt_diagnostics import PromptSection, build_prompt_diagnostics
from ..llm.provider import get_provider
from ..security import sanitize_payload
from .drilldown import DrilldownArtifact


def resolve_drilldown_max_tokens(
    provider_name: str,
    explicit_max_tokens: int | None = None,
) -> int | None:
    """Resolve max_tokens for drilldown artifact assessment.


    This helper avoids importing get_provider or LlamaCppProvider in health/loop.py
    by encapsulating provider resolution logic here.


    Args:
        provider_name: The LLM provider name (e.g., "llamacpp").
        explicit_max_tokens: Explicit max_tokens value if provided by caller.


    Returns:
        The explicit_max_tokens if provided, otherwise the provider-specific
        default from LlamaCppProvider.max_tokens_for_operation("auto-drilldown"),
        or None if provider doesn't support auto-drilldown max_tokens.
    """
    if explicit_max_tokens is not None:
        return explicit_max_tokens
    if provider_name != "llamacpp":
        return None
    from ..llm.llamacpp_provider import LlamaCppProvider
    from ..llm.provider import get_provider
    prov = get_provider(provider_name)
    if isinstance(prov, LlamaCppProvider):
        return prov.max_tokens_for_operation("auto-drilldown")
    return None





def assess_drilldown_artifact(
    artifact: DrilldownArtifact,
    provider_name: str = "default",
    *,
    max_tokens: int | None = None,
) -> AssessorAssessment:
    """Run the named provider against a drilldown artifact."""
    prompt = build_drilldown_prompt(artifact)
    provider = get_provider(provider_name)

    differences: dict[str, object] = {
        reason: artifact.evidence_summary for reason in artifact.trigger_reasons
    }
    if not differences:
        differences = {"drilldown": artifact.evidence_summary}
    sanitized_differences = sanitize_payload({"differences": differences})["differences"]
    payload = LLMAssessmentInput(
        primary_snapshot=sanitize_payload({
            "context": artifact.context,
            "cluster_id": artifact.cluster_id,
            "trigger_reasons": list(artifact.trigger_reasons),
            "missing_evidence": list(artifact.missing_evidence),
        }),
        secondary_snapshot={},
        comparison={"differences": sanitized_differences},
        comparison_metadata=None,
        collection_statuses=sanitize_payload({"drilldown": artifact.collection_timestamps}),
    )
    # Use provider-specific max_tokens if not explicitly provided
    effective_max_tokens = max_tokens
    if effective_max_tokens is None and provider_name == "llamacpp":
        from ..llm.llamacpp_provider import LlamaCppProvider
        if isinstance(provider, LlamaCppProvider):
            effective_max_tokens = provider.max_tokens_for_operation("auto-drilldown")
    raw_assessment = provider.assess(
        prompt, payload, max_tokens=effective_max_tokens, response_format_json=True
    )
    return AssessorAssessment.from_dict(raw_assessment)


def extract_drilldown_prompt_sections(artifact: DrilldownArtifact) -> list[PromptSection]:
    """Extract named sections from a drilldown artifact for prompt diagnostics.

    Named sections:
    - artifact_metadata: run_id, context, label, cluster_id, timestamps
    - trigger_reasons: Why this drilldown was triggered
    - evidence_summary: JSON summary of collected evidence
    - warning_events: Warning event data
    - non_running_pods: Pod status information
    - rollout_status: Deployment/ReplicaSet status
    - pod_descriptions: Captured pod descriptions
    - output_schema: JSON output schema reminder
    """
    sections: list[PromptSection] = []

    # Section 1: Artifact metadata
    sections.append(PromptSection(
        name="artifact_metadata",
        text=f"run_label={artifact.run_label}\nrun_id={artifact.run_id}\n"
             f"context={artifact.context}\nlabel={artifact.label}\n"
             f"cluster_id={artifact.cluster_id}\n"
             f"snapshot_timestamp={artifact.snapshot_timestamp.isoformat()}\n"
             f"artifact_timestamp={artifact.timestamp.isoformat()}",
    ))

    # Section 2: Trigger reasons
    sections.append(PromptSection(
        name="trigger_reasons",
        text="; ".join(artifact.trigger_reasons) or "none",
    ))

    # Section 3: Evidence summary
    sections.append(PromptSection(
        name="evidence_summary",
        text=json.dumps(artifact.evidence_summary, indent=2),
    ))

    # Section 4: Warning events
    event_lines = [json.dumps(event.to_dict(), indent=2) for event in artifact.warning_events]
    sections.append(PromptSection(
        name="warning_events",
        text="\n".join(event for event in event_lines) if event_lines else "none",
    ))

    # Section 5: Non-running pods
    pod_lines = [f"{pod.namespace}/{pod.name} ({pod.phase}) reason={pod.reason}"
                 for pod in artifact.non_running_pods]
    sections.append(PromptSection(
        name="non_running_pods",
        text="\n".join(pod_lines) if pod_lines else "none",
    ))

    # Section 6: Rollout status
    rollout_lines = [
        f"{entry.kind} {entry.namespace}/{entry.name}: "
        f"desired={entry.desired_replicas}, available={entry.available_replicas}, "
        f"unavailable={entry.unavailable_replicas}"
        for entry in artifact.rollout_status
    ]
    sections.append(PromptSection(
        name="rollout_status",
        text="\n".join(rollout_lines) if rollout_lines else "none",
    ))

    # Section 7: Affected namespaces
    sections.append(PromptSection(
        name="affected_namespaces",
        text=", ".join(artifact.affected_namespaces) or "none",
    ))

    # Section 8: Collection timestamps
    sections.append(PromptSection(
        name="collection_timestamps",
        text=json.dumps(artifact.collection_timestamps, indent=2),
    ))

    # Section 9: Pod descriptions (exact measurement, no summarization)
    pod_desc_lines: list[str] = []
    for key, value in artifact.pod_descriptions.items():
        pod_desc_lines.append(f"{key}: {value}")
    sections.append(PromptSection(
        name="pod_descriptions",
        text="\n---\n".join(pod_desc_lines) if pod_desc_lines else "No pod descriptions were captured.",
    ))

    # Section 10: Output schema (fixed text)
    sections.append(PromptSection(
        name="output_schema",
        text=(
            'Provide a structured JSON assessment that follows the schema exactly. '
            'Schema reminder: observed_signals, findings, hypotheses, next_evidence_to_collect, '
            'recommended_action, safety_level, probable_layer_of_origin, overall_confidence'
        ),
    ))

    return sections


def build_drilldown_prompt_diagnostics(
    artifact: DrilldownArtifact,
    provider_name: str = "llamacpp",
    *,
    actual_prompt_chars: int | None = None,
    max_tokens: int | None = None,
    timeout_seconds: int | None = None,
    elapsed_ms: int | None = None,
    failure_class: str | None = None,
    exception_type: str | None = None,
) -> dict[str, object]:
    """Build prompt diagnostics for a drilldown artifact assessment.

    This function extracts named sections from the drilldown artifact prompt
    and computes diagnostics. If actual_prompt_chars is provided, uses exact
    measurement from the actual prompt sent to the LLM.


    Args:
        artifact: The drilldown artifact
        provider_name: The LLM provider name
        actual_prompt_chars: Exact character count of the actual prompt sent to LLM.
                           If None, uses section-based measurement.
        max_tokens: The max_tokens completion budget if any
        timeout_seconds: The timeout configured for the call
        elapsed_ms: Time taken for the call
        failure_class: Failure classification if call failed
        exception_type: Exception type name if call failed

    Returns:
        Dict representation of PromptDiagnostics suitable for JSON serialization
    """
    sections = extract_drilldown_prompt_sections(artifact)
    diags = build_prompt_diagnostics(
        provider=provider_name,
        operation="auto-drilldown",
        sections=sections,
        actual_prompt_chars=actual_prompt_chars,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        elapsed_ms=elapsed_ms,
        failure_class=failure_class,
        exception_type=exception_type,
    )
    return diags.to_dict()

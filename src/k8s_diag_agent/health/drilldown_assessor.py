"""Evaluate a drilldown artifact with the shared LLM seam."""
from __future__ import annotations

from typing import Dict

from ..llm.assessor_schema import AssessorAssessment
from ..llm.base import LLMAssessmentInput
from ..llm.drilldown_prompts import build_drilldown_prompt
from ..llm.provider import get_provider
from ..security import sanitize_payload
from .drilldown import DrilldownArtifact


def assess_drilldown_artifact(artifact: DrilldownArtifact, provider_name: str = "default") -> AssessorAssessment:
    """Run the named provider against a drilldown artifact."""

    prompt = build_drilldown_prompt(artifact)
    provider = get_provider(provider_name)
    differences: Dict[str, object] = {
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
    raw_assessment = provider.assess(prompt, payload)
    return AssessorAssessment.from_dict(raw_assessment)

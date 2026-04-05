"""Render assessments to structured JSON or CLI-friendly text."""
from __future__ import annotations

import json
from typing import Dict

from ..models import Assessment, ConfidenceLevel


def assessment_to_dict(assessment: Assessment) -> Dict[str, object]:
    serialized = {
        "observed_signals": [
            {
                "id": signal.id,
                "description": signal.description,
                "layer": signal.layer.value,
                "evidence_id": signal.evidence_id,
                "severity": signal.severity,
            }
            for signal in assessment.observed_signals
        ],
        "findings": [
            {
                "id": finding.id,
                "description": finding.description,
                "supporting_signals": finding.supporting_signals,
                "layer": finding.layer.value,
            }
            for finding in assessment.findings
        ],
        "hypotheses": [
            {
                "id": hypothesis.id,
                "description": hypothesis.description,
                "confidence": hypothesis.confidence.value,
                "probable_layer": hypothesis.probable_layer.value,
                "what_would_falsify": hypothesis.what_would_falsify,
            }
            for hypothesis in assessment.hypotheses
        ],
        "next_evidence_to_collect": [
            {
                "description": check.description,
                "owner": check.owner,
                "method": check.method,
                "evidence_needed": check.evidence_needed,
            }
            for check in assessment.next_evidence_to_collect
        ],
        "recommended_action": {
            "type": assessment.recommended_action.type,
            "description": assessment.recommended_action.description,
            "references": assessment.recommended_action.references,
            "safety_level": assessment.recommended_action.safety_level.value,
        },
        "safety_level": assessment.safety_level.value,
    }
    if assessment.probable_layer_of_origin:
        serialized["probable_layer_of_origin"] = assessment.probable_layer_of_origin.value
    if assessment.impact_estimate:
        serialized["impact_estimate"] = assessment.impact_estimate
    overall_confidence = assessment.overall_confidence
    if not overall_confidence and assessment.hypotheses:
        overall_confidence = assessment.hypotheses[0].confidence
    if overall_confidence:
        serialized["overall_confidence"] = overall_confidence.value
    return serialized


def format_summary(assessment: Assessment) -> str:
    hypotheses = assessment.hypotheses
    description = hypotheses[0].description if hypotheses else "No hypotheses generated."
    return f"Assessment ready. First hypothesis: {description}"


def dump_json(assessment: Assessment, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(assessment_to_dict(assessment), fh, indent=2)

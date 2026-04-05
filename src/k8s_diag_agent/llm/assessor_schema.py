"""Structured schema for LLM assessments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from ..models import ConfidenceLevel, SafetyLevel


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _ensure_list(raw: Any, name: str) -> List[Any]:
    if isinstance(raw, list):
        return raw
    raise ValueError(f"{name} must be a list")


def _list_of_strings(raw: Iterable[Any], name: str) -> List[str]:
    result: List[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        else:
            raise ValueError(f"{name} contains invalid string entries")
    return result


@dataclass(frozen=True)
class AssessorSignal:
    id: str
    description: str
    layer: str
    evidence_id: str
    severity: str

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssessorSignal":
        return cls(
            id=_require_str(raw.get("id"), "signal.id"),
            description=_require_str(raw.get("description"), "signal.description"),
            layer=_require_str(raw.get("layer"), "signal.layer"),
            evidence_id=_require_str(raw.get("evidence_id"), "signal.evidence_id"),
            severity=_require_str(raw.get("severity"), "signal.severity"),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "description": self.description,
            "layer": self.layer,
            "evidence_id": self.evidence_id,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class AssessorFinding:
    description: str
    supporting_signals: List[str]
    layer: str

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssessorFinding":
        return cls(
            description=_require_str(raw.get("description"), "finding.description"),
            supporting_signals=_list_of_strings(raw.get("supporting_signals", []), "finding.supporting_signals"),
            layer=_require_str(raw.get("layer"), "finding.layer"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "supporting_signals": self.supporting_signals,
            "layer": self.layer,
        }


@dataclass(frozen=True)
class AssessorHypothesis:
    description: str
    confidence: ConfidenceLevel
    probable_layer: str
    what_would_falsify: str

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssessorHypothesis":
        confidence_value = _require_str(raw.get("confidence"), "hypothesis.confidence")
        return cls(
            description=_require_str(raw.get("description"), "hypothesis.description"),
            confidence=ConfidenceLevel(confidence_value.lower()),
            probable_layer=_require_str(raw.get("probable_layer"), "hypothesis.probable_layer"),
            what_would_falsify=_require_str(raw.get("what_would_falsify"), "hypothesis.what_would_falsify"),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "description": self.description,
            "confidence": self.confidence.value,
            "probable_layer": self.probable_layer,
            "what_would_falsify": self.what_would_falsify,
        }


@dataclass(frozen=True)
class AssessorNextCheck:
    description: str
    owner: str
    method: str
    evidence_needed: List[str]

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssessorNextCheck":
        return cls(
            description=_require_str(raw.get("description"), "next_check.description"),
            owner=_require_str(raw.get("owner"), "next_check.owner"),
            method=_require_str(raw.get("method"), "next_check.method"),
            evidence_needed=_list_of_strings(raw.get("evidence_needed", []), "next_check.evidence_needed"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "owner": self.owner,
            "method": self.method,
            "evidence_needed": self.evidence_needed,
        }


@dataclass(frozen=True)
class AssessorRecommendedAction:
    type: str
    description: str
    references: List[str]
    safety_level: SafetyLevel

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssessorRecommendedAction":
        references = _list_of_strings(raw.get("references", []), "recommended_action.references")
        safety_value = _require_str(raw.get("safety_level"), "recommended_action.safety_level")
        return cls(
            type=_require_str(raw.get("type"), "recommended_action.type"),
            description=_require_str(raw.get("description"), "recommended_action.description"),
            references=references,
            safety_level=SafetyLevel(safety_value.lower()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "description": self.description,
            "references": self.references,
            "safety_level": self.safety_level.value,
        }


@dataclass(frozen=True)
class AssessorAssessment:
    observed_signals: List[AssessorSignal]
    findings: List[AssessorFinding]
    hypotheses: List[AssessorHypothesis]
    next_evidence_to_collect: List[AssessorNextCheck]
    recommended_action: AssessorRecommendedAction
    safety_level: SafetyLevel
    probable_layer_of_origin: Optional[str] = None
    overall_confidence: Optional[ConfidenceLevel] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssessorAssessment":
        observed_signals = [
            AssessorSignal.from_dict(entry) for entry in _ensure_list(raw.get("observed_signals"), "observed_signals")
        ]
        findings = [
            AssessorFinding.from_dict(entry) for entry in _ensure_list(raw.get("findings"), "findings")
        ]
        hypotheses = [
            AssessorHypothesis.from_dict(entry) for entry in _ensure_list(raw.get("hypotheses"), "hypotheses")
        ]
        next_checks = [
            AssessorNextCheck.from_dict(entry)
            for entry in _ensure_list(raw.get("next_evidence_to_collect"), "next_evidence_to_collect")
        ]
        recommended = AssessorRecommendedAction.from_dict(raw.get("recommended_action", {}))
        safety_value = _require_str(raw.get("safety_level"), "safety_level")
        overall_raw = raw.get("overall_confidence")
        overall = None
        if overall_raw is not None:
            overall = ConfidenceLevel(_require_str(overall_raw, "overall_confidence").lower())
        return cls(
            observed_signals=observed_signals,
            findings=findings,
            hypotheses=hypotheses,
            next_evidence_to_collect=next_checks,
            recommended_action=recommended,
            safety_level=SafetyLevel(safety_value.lower()),
            probable_layer_of_origin=_require_str(raw.get("probable_layer_of_origin"), "probable_layer_of_origin")
            if raw.get("probable_layer_of_origin")
            else None,
            overall_confidence=overall,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "observed_signals": [signal.to_dict() for signal in self.observed_signals],
            "findings": [finding.to_dict() for finding in self.findings],
            "hypotheses": [hypothesis.to_dict() for hypothesis in self.hypotheses],
            "next_evidence_to_collect": [check.to_dict() for check in self.next_evidence_to_collect],
            "recommended_action": self.recommended_action.to_dict(),
            "safety_level": self.safety_level.value,
        }
        if self.probable_layer_of_origin:
            result["probable_layer_of_origin"] = self.probable_layer_of_origin
        if self.overall_confidence:
            result["overall_confidence"] = self.overall_confidence.value
        return result

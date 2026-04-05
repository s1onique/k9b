"""Structured schema for LLM assessments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from ..models import ConfidenceLevel, SafetyLevel


def _type_name(value: Any) -> str:
    if value is None:
        return "NoneType"
    return type(value).__name__


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} expected a string but got {_type_name(value)}")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must be a non-empty string")
    return stripped


def _ensure_mapping(raw: Any, path: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{path} expected an object but got {_type_name(raw)}")
    return raw


def _ensure_list(raw: Any, path: str) -> List[Any]:
    if isinstance(raw, list):
        return raw
    raise ValueError(f"{path} expected a list but got {_type_name(raw)}")


def _list_of_strings(raw: Iterable[Any], path: str) -> List[str]:
    result: List[str] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            trimmed = item.strip()
            if trimmed:
                result.append(trimmed)
                continue
        raise ValueError(
            f"{path}[{index}] expected a non-empty string but got {_type_name(item)}"
        )
    return result


@dataclass(frozen=True)
class AssessorSignal:
    id: str
    description: str
    layer: str
    evidence_id: str
    severity: str

    @classmethod
    def from_dict(cls, raw: Any, path: str) -> "AssessorSignal":
        payload = _ensure_mapping(raw, path)
        return cls(
            id=_require_str(payload.get("id"), f"{path}.id"),
            description=_require_str(payload.get("description"), f"{path}.description"),
            layer=_require_str(payload.get("layer"), f"{path}.layer"),
            evidence_id=_require_str(payload.get("evidence_id"), f"{path}.evidence_id"),
            severity=_require_str(payload.get("severity"), f"{path}.severity"),
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
    def from_dict(cls, raw: Any, path: str) -> "AssessorFinding":
        payload = _ensure_mapping(raw, path)
        supporting_signals_raw = payload.get("supporting_signals", [])
        return cls(
            description=_require_str(payload.get("description"), f"{path}.description"),
            supporting_signals=_list_of_strings(
                _ensure_list(supporting_signals_raw, f"{path}.supporting_signals"),
                f"{path}.supporting_signals",
            ),
            layer=_require_str(payload.get("layer"), f"{path}.layer"),
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
    def from_dict(cls, raw: Any, path: str) -> "AssessorHypothesis":
        payload = _ensure_mapping(raw, path)
        confidence_value = _require_str(payload.get("confidence"), f"{path}.confidence")
        return cls(
            description=_require_str(payload.get("description"), f"{path}.description"),
            confidence=ConfidenceLevel(confidence_value.lower()),
            probable_layer=_require_str(payload.get("probable_layer"), f"{path}.probable_layer"),
            what_would_falsify=_require_str(
                payload.get("what_would_falsify"),
                f"{path}.what_would_falsify",
            ),
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
    def from_dict(cls, raw: Any, path: str) -> "AssessorNextCheck":
        payload = _ensure_mapping(raw, path)
        evidence_needed_raw = payload.get("evidence_needed", [])
        return cls(
            description=_require_str(payload.get("description"), f"{path}.description"),
            owner=_require_str(payload.get("owner"), f"{path}.owner"),
            method=_require_str(payload.get("method"), f"{path}.method"),
            evidence_needed=_list_of_strings(
                _ensure_list(evidence_needed_raw, f"{path}.evidence_needed"),
                f"{path}.evidence_needed",
            ),
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
    def from_dict(cls, raw: Any, path: str) -> "AssessorRecommendedAction":
        payload = _ensure_mapping(raw, path)
        references_raw = payload.get("references", [])
        references = _list_of_strings(
            _ensure_list(references_raw, f"{path}.references"),
            f"{path}.references",
        )
        safety_value = _require_str(payload.get("safety_level"), f"{path}.safety_level")
        return cls(
            type=_require_str(payload.get("type"), f"{path}.type"),
            description=_require_str(payload.get("description"), f"{path}.description"),
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
    def from_dict(cls, raw: Any, path: str = "assessment") -> "AssessorAssessment":
        payload = _ensure_mapping(raw, path)
        observed_signals_raw = _ensure_list(payload.get("observed_signals"), f"{path}.observed_signals")
        observed_signals = [
            AssessorSignal.from_dict(entry, f"{path}.observed_signals[{index}]")
            for index, entry in enumerate(observed_signals_raw)
        ]
        findings_raw = _ensure_list(payload.get("findings"), f"{path}.findings")
        findings = [
            AssessorFinding.from_dict(entry, f"{path}.findings[{index}]")
            for index, entry in enumerate(findings_raw)
        ]
        hypotheses_raw = _ensure_list(payload.get("hypotheses"), f"{path}.hypotheses")
        hypotheses = [
            AssessorHypothesis.from_dict(entry, f"{path}.hypotheses[{index}]")
            for index, entry in enumerate(hypotheses_raw)
        ]
        next_checks_raw = _ensure_list(
            payload.get("next_evidence_to_collect"),
            f"{path}.next_evidence_to_collect",
        )
        next_checks = [
            AssessorNextCheck.from_dict(entry, f"{path}.next_evidence_to_collect[{index}]")
            for index, entry in enumerate(next_checks_raw)
        ]
        recommended_raw = payload.get("recommended_action")
        recommended = AssessorRecommendedAction.from_dict(
            recommended_raw, f"{path}.recommended_action"
        )
        safety_value = _require_str(payload.get("safety_level"), f"{path}.safety_level")
        overall_raw = payload.get("overall_confidence")
        overall = None
        if overall_raw is not None:
            overall = ConfidenceLevel(_require_str(overall_raw, f"{path}.overall_confidence").lower())
        probable_layer_value = payload.get("probable_layer_of_origin")
        probable_layer = (
            _require_str(probable_layer_value, f"{path}.probable_layer_of_origin")
            if probable_layer_value
            else None
        )
        return cls(
            observed_signals=observed_signals,
            findings=findings,
            hypotheses=hypotheses,
            next_evidence_to_collect=next_checks,
            recommended_action=recommended,
            safety_level=SafetyLevel(safety_value.lower()),
            probable_layer_of_origin=probable_layer,
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

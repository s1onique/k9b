from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SafetyLevel(str, Enum):
    OBSERVE_ONLY = "observe-only"
    LOW_RISK = "low-risk"
    CHANGE_WITH_CAUTION = "change-with-caution"
    POTENTIALLY_DISRUPTIVE = "potentially-disruptive"


class Layer(str, Enum):
    WORKLOAD = "workload"
    NODE = "node"
    STORAGE = "storage"
    NETWORK = "network"
    OBSERVABILITY = "observability"
    ROLLOUT = "rollout"


@dataclass
class EvidenceRecord:
    id: str
    kind: str
    layer: Layer
    timestamp: datetime
    payload: dict[str, Any]


@dataclass
class Signal:
    id: str
    description: str
    layer: Layer
    evidence_id: str
    severity: str


@dataclass
class Finding:
    id: str
    description: str
    supporting_signals: list[str]
    layer: Layer


@dataclass
class Hypothesis:
    id: str
    description: str
    confidence: ConfidenceLevel
    probable_layer: Layer
    what_would_falsify: str


@dataclass
class NextCheck:
    description: str
    owner: str
    method: str
    evidence_needed: list[str] = field(default_factory=list)


@dataclass
class RecommendedAction:
    type: str
    description: str
    references: list[str]
    safety_level: SafetyLevel


@dataclass
class Assessment:
    observed_signals: list[Signal]
    findings: list[Finding]
    hypotheses: list[Hypothesis]
    next_evidence_to_collect: list[NextCheck]
    recommended_action: RecommendedAction
    safety_level: SafetyLevel
    probable_layer_of_origin: Layer | None = None
    impact_estimate: dict[str, Any] | None = None
    overall_confidence: ConfidenceLevel | None = None

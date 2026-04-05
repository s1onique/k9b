"""Typed feedback artifacts for runs, assessments, and proposals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from ..models import ConfidenceLevel


class FailureMode(str, Enum):
    MISSING_EVIDENCE = "missing_evidence"
    FALSE_CERTAINTY = "false_certainty"
    VALIDATION_FAILURE = "validation_failure"
    COLLECTION_ERROR = "collection_error"
    INVALID_ARTIFACT = "invalid_artifact"
    OTHER = "other"
    LLM_ERROR = "llm_error"


@dataclass
class SnapshotPairArtifact:
    primary_snapshot_id: str
    primary_snapshot_path: str
    comparison_summary: Dict[str, int] = field(default_factory=dict)
    secondary_snapshot_id: Optional[str] = None
    secondary_snapshot_path: Optional[str] = None
    status: str = "complete"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    missing_evidence: List[str] = field(default_factory=list)


@dataclass
class AssessmentArtifact:
    assessment_id: str
    schema_version: str
    assessment: Dict[str, Any]
    overall_confidence: Optional[str] = None


@dataclass
class ValidationResult:
    name: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    failure_mode: Optional[FailureMode] = None


@dataclass
class ProposedImprovement:
    id: str
    description: str
    target: str
    owner: Optional[str] = None
    confidence: Optional[ConfidenceLevel] = None
    rationale: Optional[str] = None
    related_failure_modes: List[FailureMode] = field(default_factory=list)


@dataclass
class RunArtifact:
    run_id: str
    timestamp: datetime
    context_name: Optional[str]
    collector_version: str
    collection_status: str
    snapshot_pair: SnapshotPairArtifact
    comparison_summary: Dict[str, int] = field(default_factory=dict)
    missing_evidence: List[str] = field(default_factory=list)
    assessment: Optional[AssessmentArtifact] = None
    validation_results: List[ValidationResult] = field(default_factory=list)
    failure_modes: List[FailureMode] = field(default_factory=list)
    proposed_improvements: List[ProposedImprovement] = field(default_factory=list)
    notes: Optional[str] = None

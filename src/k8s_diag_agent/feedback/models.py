"""Typed feedback artifacts for runs, assessments, and proposals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

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
    comparison_summary: dict[str, int] = field(default_factory=dict)
    secondary_snapshot_id: str | None = None
    secondary_snapshot_path: str | None = None
    status: str = "complete"
    start_time: datetime | None = None
    end_time: datetime | None = None
    missing_evidence: list[str] = field(default_factory=list)


@dataclass
class AssessmentArtifact:
    assessment_id: str
    schema_version: str
    assessment: dict[str, Any]
    overall_confidence: str | None = None


@dataclass
class ValidationResult:
    name: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    failure_mode: FailureMode | None = None


@dataclass
class ProposedImprovement:
    id: str
    description: str
    target: str
    owner: str | None = None
    confidence: ConfidenceLevel | None = None
    rationale: str | None = None
    related_failure_modes: list[FailureMode] = field(default_factory=list)


@dataclass
class RunArtifact:
    run_id: str
    timestamp: datetime
    context_name: str | None
    collector_version: str
    collection_status: str
    snapshot_pair: SnapshotPairArtifact
    comparison_intent: str | None = None
    comparison_notes: str | None = None
    expected_drift_categories: tuple[str, ...] = field(default_factory=tuple)
    unexpected_drift_categories: tuple[str, ...] = field(default_factory=tuple)
    comparison_summary: dict[str, int] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)
    assessment: AssessmentArtifact | None = None
    validation_results: list[ValidationResult] = field(default_factory=list)
    failure_modes: list[FailureMode] = field(default_factory=list)
    proposed_improvements: list[ProposedImprovement] = field(default_factory=list)
    notes: str | None = None

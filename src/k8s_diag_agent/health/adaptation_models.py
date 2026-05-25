"""Data models and serialization for health adaptation proposals."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ..models import ConfidenceLevel

if TYPE_CHECKING:
    from ..external_analysis.alertmanager_durable_learning import DurableProposalCandidate
    from ..identity.artifact import new_artifact_id


class ProposalLifecycleStatus(StrEnum):
    PENDING = "pending"
    CHECKED = "checked"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"
    PROPOSED = "proposed"
    REPLAYED = "replayed"
    PROMOTED = "promoted"


@dataclass(frozen=True)
class ProposalLifecycleEntry:
    status: ProposalLifecycleStatus
    timestamp: str
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status.value,
            "timestamp": self.timestamp,
        }
        if self.note:
            data["note"] = self.note
        return data


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _freeze_payload(value: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    base = dict(value or {})
    return MappingProxyType(base)


def _empty_payload() -> Mapping[str, Any]:
    return MappingProxyType({})


def _default_lifecycle_history() -> tuple[ProposalLifecycleEntry, ...]:
    return (ProposalLifecycleEntry(status=ProposalLifecycleStatus.PENDING, timestamp=_now_iso()),)


@dataclass(frozen=True)
class HealthProposal:
    proposal_id: str
    source_run_id: str
    source_artifact_path: str
    target: str
    proposed_change: str
    rationale: str
    confidence: ConfidenceLevel
    expected_benefit: str
    rollback_note: str
    promotion_payload: Mapping[str, Any] = field(default_factory=_empty_payload)
    lifecycle_history: tuple[ProposalLifecycleEntry, ...] = field(default_factory=_default_lifecycle_history)
    promotion_evaluation: ProposalEvaluation | None = None
    artifact_path: str | None = None
    artifact_id: str | None = None  # None for legacy, auto-generated for new proposals via factory functions
    # Tag for durable-learning proposals to distinguish from regular proposals
    durable_learning_source: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "promotion_payload", _freeze_payload(self.promotion_payload))
        history = tuple(self.lifecycle_history) if self.lifecycle_history else _default_lifecycle_history()
        if not history:
            history = _default_lifecycle_history()
        object.__setattr__(self, "lifecycle_history", history)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "proposal_id": self.proposal_id,
            "source_run_id": self.source_run_id,
            "source_artifact_path": self.source_artifact_path,
            "target": self.target,
            "proposed_change": self.proposed_change,
            "rationale": self.rationale,
            "confidence": self.confidence.value,
            "expected_benefit": self.expected_benefit,
            "rollback_note": self.rollback_note,
            "promotion_payload": dict(self.promotion_payload),
            "lifecycle_history": [entry.to_dict() for entry in self.lifecycle_history],
            "promotion_evaluation": self.promotion_evaluation.to_dict() if self.promotion_evaluation else None,
            "artifact_path": self.artifact_path,
        }
        # Include artifact_id when present (backward compat: legacy artifacts without it)
        if self.artifact_id is not None:
            data["artifact_id"] = self.artifact_id
        # Thread durable_learning_source for UI surfacing (optional)
        if self.durable_learning_source is not None:
            data["durable_learning_source"] = self.durable_learning_source
        return data

    def __hash__(self) -> int:
        return hash((self.proposal_id, self.source_run_id, self.target, self.proposed_change))

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> HealthProposal:
        if not isinstance(raw, Mapping):
            raise ValueError("Proposal must be a mapping")
        confidence_value = raw.get("confidence")
        if not confidence_value:
            raise ValueError("Proposal missing confidence level")
        try:
            confidence = ConfidenceLevel(str(confidence_value))
        except ValueError as exc:
            raise ValueError(f"Invalid confidence value: {confidence_value}") from exc
        payload_raw = raw.get("promotion_payload") or {}
        payload = _freeze_payload(payload_raw if isinstance(payload_raw, Mapping) else {})
        history_entries: list[ProposalLifecycleEntry] = []
        history_raw = raw.get("lifecycle_history")
        if isinstance(history_raw, Sequence):
            for entry_raw in history_raw:
                if not isinstance(entry_raw, Mapping):
                    continue
                status_value = entry_raw.get("status")
                timestamp_value = entry_raw.get("timestamp")
                note_value = entry_raw.get("note")
                timestamp = str(timestamp_value) if timestamp_value else _now_iso()
                try:
                    status = ProposalLifecycleStatus(str(status_value)) if status_value else ProposalLifecycleStatus.PENDING
                except ValueError:
                    status = ProposalLifecycleStatus.PENDING
                history_entries.append(
                    ProposalLifecycleEntry(status=status, timestamp=timestamp, note=str(note_value) if note_value else None)
                )
        history = tuple(history_entries) if history_entries else _default_lifecycle_history()
        evaluation_raw = raw.get("promotion_evaluation")
        evaluation: ProposalEvaluation | None = None
        if isinstance(evaluation_raw, Mapping):
            try:
                evaluation = ProposalEvaluation.from_dict(evaluation_raw)
            except ValueError:
                evaluation = None
        # Parse artifact_id for backward compatibility (legacy artifacts without it)
        artifact_id_value = raw.get("artifact_id")
        parsed_artifact_id: str | None = None
        if artifact_id_value is not None and isinstance(artifact_id_value, str) and artifact_id_value:
            parsed_artifact_id = artifact_id_value
        # Parse durable_learning_source for durable-learning proposals
        durable_source = raw.get("durable_learning_source")
        parsed_durable_source: str | None = None
        if durable_source is not None and isinstance(durable_source, str) and durable_source:
            parsed_durable_source = durable_source
        return cls(
            proposal_id=str(raw.get("proposal_id") or ""),
            source_run_id=str(raw.get("source_run_id") or ""),
            source_artifact_path=str(raw.get("source_artifact_path") or ""),
            target=str(raw.get("target") or ""),
            proposed_change=str(raw.get("proposed_change") or ""),
            rationale=str(raw.get("rationale") or ""),
            confidence=confidence,
            expected_benefit=str(raw.get("expected_benefit") or ""),
            rollback_note=str(raw.get("rollback_note") or ""),
            promotion_payload=payload,
            lifecycle_history=history,
            promotion_evaluation=evaluation,
            artifact_path=str(raw.get("artifact_path")) if raw.get("artifact_path") else None,
            artifact_id=parsed_artifact_id,
            durable_learning_source=parsed_durable_source,
        )

    @classmethod
    def from_durable_proposal_candidate(
        cls,
        candidate: DurableProposalCandidate,
        source_run_id: str,
        source_artifact_path: str,
    ) -> HealthProposal:
        """Convert a DurableProposalCandidate to a HealthProposal for UI integration.

        This enables durable Alertmanager proposals to appear in the existing
        proposal pipeline without creating a parallel proposal system.
        """
        pattern = candidate.pattern
        # Map confidence string to ConfidenceLevel
        confidence_map = {
            "high": ConfidenceLevel.HIGH,
            "medium": ConfidenceLevel.MEDIUM,
            "low": ConfidenceLevel.LOW,
        }
        confidence = confidence_map.get(candidate._compute_confidence(), ConfidenceLevel.MEDIUM)
        values_str = ", ".join(sorted(pattern.values))

        return cls(
            proposal_id=candidate.proposal_id,
            source_run_id=source_run_id,
            source_artifact_path=source_artifact_path,
            target=f"health.durable_learning.{pattern.dimension}",
            proposed_change=f"Suppress {pattern.dimension} '{values_str}' "
                           f"from Alertmanager scoring (signal: {pattern.signal}).",
            rationale=pattern.proposal_rationale,
            confidence=confidence,
            expected_benefit=candidate.to_dict().get("expected_benefit", ""),
            rollback_note=f"Remove suppression for {pattern.dimension} '{values_str}' if signal re-emerges.",
            promotion_payload=dict(candidate._build_promotion_payload()),
            lifecycle_history=_default_lifecycle_history(),
            promotion_evaluation=None,
            artifact_path=None,
            artifact_id=new_artifact_id(),
            durable_learning_source="alertmanager_durable_learning",
        )


@dataclass(frozen=True)
class ProposalEvaluation:
    proposal_id: str
    noise_reduction: str
    signal_loss: str
    test_outcome: str

    def to_dict(self) -> dict[str, str]:
        return {
            "proposal_id": self.proposal_id,
            "noise_reduction": self.noise_reduction,
            "signal_loss": self.signal_loss,
            "test_outcome": self.test_outcome,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ProposalEvaluation:
        if not isinstance(raw, Mapping):
            raise ValueError("promotion_evaluation must be a mapping")
        return cls(
            proposal_id=str(raw.get("proposal_id") or ""),
            noise_reduction=str(raw.get("noise_reduction") or ""),
            signal_loss=str(raw.get("signal_loss") or ""),
            test_outcome=str(raw.get("test_outcome") or ""),
        )


# Re-export for backward compatibility
__all__ = [
    "HealthProposal",
    "ProposalEvaluation",
    "ProposalLifecycleEntry",
    "ProposalLifecycleStatus",
    "_default_lifecycle_history",
    "_empty_payload",
    "_freeze_payload",
    "_now_iso",
]

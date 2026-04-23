"""Immutable proposal lifecycle event artifacts.

These artifacts record each targeted lifecycle transition for proposals,
keeping the base proposal artifact immutable once written.

Storage layout:
  runs/health/proposals/transitions/{proposal_id}-{transition}-{artifact_id}.json

Lifecycle event artifacts contain:
- artifact_id: immutable identity (UUIDv7)
- proposal_id: back-reference to the base proposal
- proposal_artifact_id: optional reference to the base proposal's artifact_id
- status: the lifecycle status this event records
- transition: the type of transition (check, promote)
- created_at: ISO timestamp when the event was created
- note: optional operator note or context
- provenance: optional metadata about the command source
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..identity.artifact import new_artifact_id, write_append_only_json_artifact
from .adaptation import ProposalLifecycleStatus

if TYPE_CHECKING:
    from .adaptation import ProposalEvaluation


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ProposalLifecycleEvent:
    """Immutable proposal lifecycle event artifact.

    Each event records a targeted lifecycle transition for a proposal.
    The base proposal artifact remains unchanged; all transitions are
    captured in separate event artifacts.
    """

    artifact_id: str = field(default_factory=new_artifact_id)
    proposal_id: str = ""
    proposal_artifact_id: str | None = None
    status: ProposalLifecycleStatus = ProposalLifecycleStatus.PENDING
    transition: str = ""  # e.g., "check", "promote"
    created_at: str = field(default_factory=_now_iso)
    note: str | None = None
    provenance: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "proposal_id": self.proposal_id,
            "status": self.status.value,
            "transition": self.transition,
            "created_at": self.created_at,
        }
        if self.proposal_artifact_id is not None:
            data["proposal_artifact_id"] = self.proposal_artifact_id
        if self.note is not None:
            data["note"] = self.note
        if self.provenance is not None:
            data["provenance"] = dict(self.provenance)
        return data

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ProposalLifecycleEvent:
        if not isinstance(raw, Mapping):
            raise ValueError("Lifecycle event must be a mapping")

        status_value = raw.get("status")
        try:
            status = ProposalLifecycleStatus(str(status_value)) if status_value else ProposalLifecycleStatus.PENDING
        except ValueError:
            status = ProposalLifecycleStatus.PENDING

        proposal_artifact_id = raw.get("proposal_artifact_id")
        provenance = raw.get("provenance")
        if provenance is not None and not isinstance(provenance, Mapping):
            provenance = None

        return cls(
            artifact_id=str(raw.get("artifact_id")) if raw.get("artifact_id") else new_artifact_id(),
            proposal_id=str(raw.get("proposal_id") or ""),
            proposal_artifact_id=str(proposal_artifact_id) if proposal_artifact_id else None,
            status=status,
            transition=str(raw.get("transition") or ""),
            created_at=str(raw.get("created_at")) if raw.get("created_at") else _now_iso(),
            note=str(raw.get("note")) if raw.get("note") else None,
            provenance=dict(provenance) if provenance else None,
        )


def write_proposal_lifecycle_event(
    event: ProposalLifecycleEvent,
    transitions_dir: Path,
) -> Path:
    """Write an immutable proposal lifecycle event artifact.

    Proposal lifecycle event artifacts are immutable: once written, they must
    not be overwritten. This function rejects writes to an existing path to
    enforce the immutability contract.

    The immutability contract means that the same path (proposal_id + transition
    + artifact_id combination) should never be written twice. Each event is
    uniquely identified by its artifact_id, so duplicate writes are a bug.

    Mutable exceptions (NOT covered by this guard):
    - history.json
    - alertmanager-source-registry.json
    - ui-index.json
    - diagnostic-packs/latest/
    - other explicitly documented mutable/derived artifacts

    Args:
        event: The lifecycle event to write.
        transitions_dir: Directory where transition artifacts are stored.

    Returns:
        Path to the written artifact.

    Raises:
        FileExistsError: If the artifact path already exists (immutability guarantee)
    """
    filename = f"{event.proposal_id}-{event.transition}-{event.artifact_id}.json"
    path = transitions_dir / filename

    context = (
        f"proposal_id={event.proposal_id}, transition={event.transition}, "
        f"artifact_id={event.artifact_id}"
    )
    return write_append_only_json_artifact(path, event.to_dict(), context=context)


def derive_current_proposal_status(
    base_proposal_dict: Mapping[str, Any],
    transitions_dir: Path | None,
) -> ProposalLifecycleStatus:
    """Derive the current lifecycle status for a proposal.

    Uses event artifacts if present, falling back to the base proposal's
    lifecycle_history for backward compatibility.

    Args:
        base_proposal_dict: The parsed base proposal dictionary.
        transitions_dir: Directory containing transition artifacts.

    Returns:
        The current lifecycle status.
    """
    proposal_id = str(base_proposal_dict.get("proposal_id", ""))

    # Try event artifacts first
    if transitions_dir and transitions_dir.is_dir():
        pattern = f"{proposal_id}-*-*.json"
        candidates: list[tuple[datetime, ProposalLifecycleStatus]] = []

        for path in sorted(transitions_dir.glob(pattern)):
            try:
                import json

                raw = json.loads(path.read_text(encoding="utf-8"))
                event = ProposalLifecycleEvent.from_dict(raw)
                created = datetime.fromisoformat(event.created_at)
                candidates.append((created, event.status))
            except (OSError, json.JSONDecodeError, ValueError):
                continue

        if candidates:
            # Sort by timestamp descending, pick latest
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]

    # Fall back to embedded lifecycle_history
    history = base_proposal_dict.get("lifecycle_history")
    if history and isinstance(history, list) and len(history) > 0:
        last_entry = history[-1]
        if isinstance(last_entry, Mapping):
            status_value = last_entry.get("status")
            if status_value:
                try:
                    return ProposalLifecycleStatus(str(status_value))
                except ValueError:
                    pass

    return ProposalLifecycleStatus.PENDING


def derive_proposal_evaluation_from_events(
    proposal_id: str,
    transitions_dir: Path | None,
) -> ProposalEvaluation | None:
    """Derive the latest usable proposal evaluation from lifecycle event artifacts.

    When proposals are checked, the evaluation data is stored in the check event's
    provenance. This helper retrieves the latest evaluation from check-related events.

    Args:
        proposal_id: The proposal identifier to look up.
        transitions_dir: Directory containing transition artifacts.

    Returns:
        A ProposalEvaluation parsed from the latest check event's provenance,
        or None if no evaluation data is found.
    """
    # Import here to avoid circular dependency at runtime
    from .adaptation import ProposalEvaluation

    if not transitions_dir or not transitions_dir.is_dir():
        return None

    # Look for check transition events (they contain evaluation data)
    pattern = f"{proposal_id}-check-*.json"
    candidates: list[tuple[datetime, ProposalEvaluation]] = []

    for path in sorted(transitions_dir.glob(pattern)):
        try:
            import json

            raw = json.loads(path.read_text(encoding="utf-8"))
            event = ProposalLifecycleEvent.from_dict(raw)

            # Extract evaluation from provenance
            provenance = event.provenance
            if provenance and isinstance(provenance, Mapping):
                eval_raw = provenance.get("evaluation")
                if eval_raw and isinstance(eval_raw, Mapping):
                    evaluation = ProposalEvaluation.from_dict(eval_raw)
                    created = datetime.fromisoformat(event.created_at)
                    candidates.append((created, evaluation))
        except (OSError, json.JSONDecodeError, ValueError):
            continue

    if not candidates:
        return None

    # Sort by timestamp descending, return the latest evaluation
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]

"""Missing-evidence assessment helpers for health assessment building.

Extracts missing-evidence derivation logic from build_health_assessment() into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module handles:
1. Creating signals for each missing evidence item
2. Recording findings for missing telemetry
3. Detecting and recording new missing evidence since previous run

The module does not modify issues_detected - the caller owns that state.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..models import Layer, Signal
from .loop_history import HealthHistoryEntry

__all__ = [
    "MissingEvidenceAssessment",
    "assess_missing_evidence",
]


@dataclass
class MissingEvidenceAssessment:
    """Result of missing evidence assessment."""

    __slots__ = ("signal_ids", "signal_map", "new_signal_ids", "new_missing_items")

    signal_ids: list[str]
    """All signal IDs created for missing evidence items."""

    signal_map: dict[str, str]
    """Mapping from missing evidence item to its signal ID."""

    new_signal_ids: list[str]
    """Signal IDs for newly missing evidence items (since previous run)."""

    new_missing_items: list[str]
    """List of newly missing evidence items (since previous run)."""


def assess_missing_evidence(
    *,
    missing: Sequence[str],
    previous: HealthHistoryEntry | None,
    signal_adder: Callable[[str, str, Layer], Signal],
    finding_recorder: Callable[[str, Layer, Sequence[str]], None],
) -> MissingEvidenceAssessment:
    """Assess missing evidence and create signals, findings, and detection results.

    This function extracts missing-evidence derivation logic from build_health_assessment().
    It processes missing telemetry items, creates signals, records findings, and detects
    new missing evidence compared to the previous run.

    Args:
        missing: Sequence of missing evidence item names.
        previous: Previous health history entry, or None if no history.
        signal_adder: Callable that adds a signal and returns it.
                      Signature: (description, severity, layer) -> Signal
        finding_recorder: Callable that records a finding.
                         Signature: (description, layer, signal_ids) -> None

    Returns:
        MissingEvidenceAssessment with signal IDs, mappings, and new-missing detection.
    """
    signal_ids: list[str] = []
    signal_map: dict[str, str] = {}
    new_signal_ids: list[str] = []
    new_missing_items: list[str] = []

    # Create signals for each missing evidence item
    for missing_item in missing:
        signal = signal_adder(
            f"Missing evidence: {missing_item}.",
            "medium",
            Layer.OBSERVABILITY,
        )
        signal_ids.append(signal.id)
        signal_map[missing_item] = signal.id

    # Record finding for all missing telemetry
    if signal_ids:
        finding_recorder(
            f"Snapshot is missing telemetry: {', '.join(sorted(missing))}.",
            Layer.OBSERVABILITY,
            signal_ids,
        )

        # Detect new missing evidence compared to previous run
        if previous:
            prev_missing = set(previous.missing_evidence)
            new_missing = sorted(set(missing) - prev_missing)
            new_signal_ids = [signal_map[item] for item in new_missing if item in signal_map]
            new_missing_items = list(new_missing)

            if new_missing and new_signal_ids:
                finding_recorder(
                    f"New missing telemetry since last run: {', '.join(new_missing)}.",
                    Layer.OBSERVABILITY,
                    new_signal_ids,
                )

    return MissingEvidenceAssessment(
        signal_ids=signal_ids,
        signal_map=signal_map,
        new_signal_ids=new_signal_ids,
        new_missing_items=new_missing_items,
    )
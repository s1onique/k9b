"""Config/CLI parsing helpers for the health loop.

Extracts config-owned parsing functions from loop.py into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides the pure parsing logic for:
1. Manual trigger strings from CLI
2. Manual external analysis requests from CLI
3. Threshold values from config
4. Comparison intent values from config

These are independent helpers with no runner logic or comparison-policy dependencies.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .utils import normalize_ref

if TYPE_CHECKING:
    from .loop import ComparisonIntent, ManualComparison, ManualExternalAnalysisRequest


def _parse_manual_triggers(values: Sequence[str]) -> list[ManualComparison]:
    """Parse CLI/manual trigger strings into ManualComparison objects.

    Format: "primary:secondary" where each reference is normalized.
    Skips entries without a colon separator.
    """
    manual: list[ManualComparison] = []
    for raw_value in values:
        if ":" not in raw_value:
            continue
        primary, secondary = raw_value.split(":", 1)
        manual.append(
            ManualComparison(primary=normalize_ref(primary), secondary=normalize_ref(secondary))
        )
    return manual


def _parse_manual_external_analysis_requests(
    values: Sequence[str],
) -> list[ManualExternalAnalysisRequest]:
    """Parse CLI/manual external analysis request strings into objects.

    Format: "tool:target" where target is normalized and tool is lowercased.
    Skips entries without a colon or with empty tool/target.
    """
    manual: list[ManualExternalAnalysisRequest] = []
    for raw_value in values:
        if ":" not in raw_value:
            continue
        tool_raw, target_raw = raw_value.split(":", 1)
        tool = tool_raw.strip().lower()
        target = normalize_ref(target_raw)
        if not tool or not target:
            continue
        manual.append(ManualExternalAnalysisRequest(tool=tool, target=target))
    return manual


def _parse_threshold(value: Any | None) -> int:
    """Parse a threshold value from config, returning 0 for invalid inputs."""
    if value is None:
        return 0
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, threshold)


def _parse_comparison_intent(value: Any | None) -> ComparisonIntent:
    """Parse a comparison intent from config, defaulting to SUSPICIOUS_DRIFT."""
    # Import at runtime to avoid circular imports - ComparisonIntent is a StrEnum defined in loop.py
    from .loop import ComparisonIntent

    if value is None:
        return ComparisonIntent.SUSPICIOUS_DRIFT
    try:
        return ComparisonIntent(str(value))
    except ValueError:
        return ComparisonIntent.SUSPICIOUS_DRIFT

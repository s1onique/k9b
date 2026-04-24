"""View models for auto-drilldown interpretation UI layer (UI model module).

This module contains auto-drilldown-interpretation-related view model dataclasses
and builders extracted from model.py. It exists to enable incremental modularization
without changing behavior.

Dependency direction:
- model_auto_drilldown.py -> model_primitives.py
- model.py imports from model_auto_drilldown.py for re-export compatibility.

Note: Auto-drilldown interpretations represent provider-assisted drilldown results
that provide automated cluster analysis and diagnostic insights.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class AutoDrilldownInterpretationView:
    """View model for a single auto-drilldown interpretation result in the UI."""
    adapter: str
    status: str
    summary: str | None
    timestamp: str
    artifact_path: str | None
    provider: str | None
    duration_ms: int | None
    payload: Mapping[str, object] | None
    error_summary: str | None
    skip_reason: str | None


def _build_auto_drilldown_interpretations(
    raw: object | None,
) -> Mapping[str, AutoDrilldownInterpretationView]:
    """Build auto-drilldown interpretations mapping from raw JSON data.

    Returns an empty dict for non-Mapping input.
    Skips entries where label is not a str or entry is not a Mapping.
    Preserves iteration order from raw mapping.
    """
    if not isinstance(raw, Mapping):
        return {}
    interpretations: dict[str, AutoDrilldownInterpretationView] = {}
    for label, entry in raw.items():
        if not isinstance(label, str) or not isinstance(entry, Mapping):
            continue
        interpretations[label] = AutoDrilldownInterpretationView(
            adapter=_coerce_str(entry.get("adapter")),
            status=_coerce_str(entry.get("status")),
            summary=_coerce_optional_str(entry.get("summary")),
            timestamp=_coerce_str(entry.get("timestamp")),
            artifact_path=_coerce_optional_str(entry.get("artifact_path")),
            provider=_coerce_optional_str(entry.get("provider")),
            duration_ms=_coerce_optional_int(entry.get("duration_ms")),
            payload=entry.get("payload") if isinstance(entry.get("payload"), Mapping) else None,
            error_summary=_coerce_optional_str(entry.get("error_summary")),
            skip_reason=_coerce_optional_str(entry.get("skip_reason")),
        )
    return interpretations

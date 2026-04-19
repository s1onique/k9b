"""Build review-enrichment inputs for provider requests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .alertmanager_artifact import alertmanager_artifacts_exist, read_alertmanager_compact


@dataclass(frozen=True)
class AlertmanagerContext:
    """Structured Alertmanager compact context for LLM prompts."""
    available: bool
    source: str  # "run_artifact" or "unavailable"
    compact: dict[str, Any] | None
    status: str | None  # Original Alertmanager status when available

    @classmethod
    def from_run_artifacts(cls, root_dir: Path, run_id: str) -> AlertmanagerContext:
        """Load Alertmanager compact from run-scoped artifact path.
        
        Returns unavailable context if artifact does not exist or cannot be parsed.
        No live Alertmanager fetch is performed.
        """
        snap_exists, compact_exists = alertmanager_artifacts_exist(root_dir, run_id)
        if not compact_exists:
            return cls(
                available=False,
                source="unavailable",
                compact=None,
                status=None,
            )
        compact_path = root_dir / f"{run_id}-alertmanager-compact.json"
        compact = read_alertmanager_compact(compact_path)
        if compact is None:
            return cls(
                available=False,
                source="unavailable",
                compact=None,
                status=None,
            )
        return cls(
            available=True,
            source="run_artifact",
            compact=compact.to_dict(),
            status=compact.status,
        )


@dataclass(frozen=True)
class ReviewSelectionContext:
    label: str
    context: str
    entry: Mapping[str, Any]
    drilldown_path: str | None
    drilldown: dict[str, Any] | None
    assessment_path: str | None
    assessment: dict[str, Any] | None
    snapshot_path: str | None
    snapshot: dict[str, Any] | None


@dataclass(frozen=True)
class ReviewEnrichmentInput:
    run_id: str
    review_path: Path
    review: dict[str, Any]
    selections: tuple[ReviewSelectionContext, ...]
    missing_drilldowns: tuple[str, ...]
    missing_assessments: tuple[str, ...]
    missing_snapshots: tuple[str, ...]
    alertmanager_context: AlertmanagerContext = field(default_factory=lambda: AlertmanagerContext(
        available=False,
        source="unavailable",
        compact=None,
        status=None,
    ))


def build_review_enrichment_input(
    review_path: Path, run_id: str, selection_limit: int = 3
) -> ReviewEnrichmentInput:
    if selection_limit < 0:
        raise ValueError("selection_limit must be non-negative")
    if not review_path or not review_path.exists():
        raise FileNotFoundError(f"Review artifact missing: {review_path}")
    review = _load_json(review_path)
    if not isinstance(review, Mapping):
        raise ValueError("Review artifact must be a mapping")
    root_dir = _determine_root_dir(review_path)
    selections: list[ReviewSelectionContext] = []
    missing_drilldowns: list[str] = []
    missing_assessments: list[str] = []
    missing_snapshots: list[str] = []
    for entry in _selected_drilldowns(review)[:selection_limit]:
        label = str(entry.get("label") or "")
        context_value = str(entry.get("context") or "")
        drilldown_path = root_dir / "drilldowns" / f"{run_id}-{label}-drilldown.json"
        drilldown_data = _load_json(drilldown_path)
        if drilldown_data is None:
            missing_drilldowns.append(label)
        assessment_path = root_dir / "assessments" / f"{run_id}-{label}-assessment.json"
        assessment_data = _load_json(assessment_path)
        if assessment_data is None:
            missing_assessments.append(label)
        snapshot_path, snapshot_data = _snapshot_from_assessment(assessment_data, root_dir)
        if assessment_data and snapshot_path and snapshot_data is None:
            missing_snapshots.append(label)
        selections.append(
            ReviewSelectionContext(
                label=label,
                context=context_value,
                entry=dict(entry),
                drilldown_path=str(drilldown_path),
                drilldown=drilldown_data,
                assessment_path=str(assessment_path),
                assessment=assessment_data,
                snapshot_path=str(snapshot_path) if snapshot_path else None,
                snapshot=snapshot_data,
            )
        )
    alertmanager_ctx = AlertmanagerContext.from_run_artifacts(root_dir, run_id)
    return ReviewEnrichmentInput(
        run_id=run_id,
        review_path=review_path,
        review=dict(review),
        selections=tuple(selections),
        missing_drilldowns=tuple(missing_drilldowns),
        missing_assessments=tuple(missing_assessments),
        missing_snapshots=tuple(missing_snapshots),
        alertmanager_context=alertmanager_ctx,
    )


def _selected_drilldowns(review: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    raw = review.get("selected_drilldowns") or []
    if not isinstance(raw, Sequence):
        return ()
    return tuple(entry for entry in raw if isinstance(entry, Mapping))


def _determine_root_dir(review_path: Path) -> Path:
    # Use path parts to determine depth (includes the file itself)
    # For /a/b/c.json -> parts = ['/', 'a', 'b', 'c.json'] (4 parts)
    # For /a/b.json -> parts = ['/', 'a', 'b.json'] (3 parts)
    # For /a.json -> parts = ['/', 'a.json'] (2 parts)
    if len(review_path.parts) >= 3:
        return review_path.parents[1]
    return review_path.parent


def _snapshot_from_assessment(
    assessment: Mapping[str, Any] | None, base_dir: Path
) -> tuple[Path | None, dict[str, Any] | None]:
    if not assessment:
        return None, None
    snapshot_path_raw = assessment.get("snapshot_path")
    if not isinstance(snapshot_path_raw, str):
        return None, None
    candidate = Path(snapshot_path_raw)
    if not candidate.is_absolute():
        candidate = base_dir / snapshot_path_raw
    snapshot_data = _load_json(candidate)
    return candidate, snapshot_data


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, Mapping):
        return None
    return dict(data)

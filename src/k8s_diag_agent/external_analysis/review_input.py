"""Build review-enrichment inputs for provider requests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    return ReviewEnrichmentInput(
        run_id=run_id,
        review_path=review_path,
        review=dict(review),
        selections=tuple(selections),
        missing_drilldowns=tuple(missing_drilldowns),
        missing_assessments=tuple(missing_assessments),
        missing_snapshots=tuple(missing_snapshots),
    )


def _selected_drilldowns(review: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    raw = review.get("selected_drilldowns") or []
    if not isinstance(raw, Sequence):
        return ()
    return tuple(entry for entry in raw if isinstance(entry, Mapping))


def _determine_root_dir(review_path: Path) -> Path:
    if len(review_path.parents) >= 2:
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

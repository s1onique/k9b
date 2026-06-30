"""Shared helpers for next_check_planner tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)


def _write_review(root: Path, run_id: str, selections: list[dict[str, object]]) -> Path:
    review_dir = root / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / f"{run_id}-review.json"
    path.write_text(
        json.dumps({"run_id": run_id, "selected_drilldowns": selections}), encoding="utf-8"
    )
    return path


def _write_assessment(
    root: Path, run_id: str, label: str, next_checks: list[dict[str, str]]
) -> None:
    assessments_dir = root / "assessments"
    assessments_dir.mkdir(parents=True, exist_ok=True)
    path = assessments_dir / f"{run_id}-{label}-assessment.json"
    path.write_text(json.dumps({"next_evidence_to_collect": next_checks}), encoding="utf-8")


def _build_enrichment_artifact(run_id: str, hints: tuple[str, ...]) -> ExternalAnalysisArtifact:
    return ExternalAnalysisArtifact(
        tool_name="llamacpp",
        run_id=run_id,
        cluster_label="status-run",
        summary="enrichment",
        suggested_next_checks=hints,
        status=ExternalAnalysisStatus.SUCCESS,
        artifact_path="external-analysis/plan.json",
        provider="llamacpp",
    )


def _copy_fixture_set(tmp_path: Path) -> Path:
    # fixtures/next_check_planner is at tests/fixtures/next_check_planner
    fixture_root = Path(__file__).parent.parent / "fixtures" / "next_check_planner"
    destination = tmp_path / "runs" / "health"
    shutil.copytree(fixture_root, destination)
    return destination

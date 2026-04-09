#!/usr/bin/env python3
"""CLI to review diagnostic packs with a stronger external analysis adapter."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, cast

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.artifact import write_external_analysis_artifact
from k8s_diag_agent.ui.model import UIIndexContext, build_ui_context


@dataclass(frozen=True)
class DiagnosticPackReviewResult:
    artifact: ExternalAnalysisArtifact
    artifact_path: Path


def extract_diagnostic_pack(pack_path: Path, destination: Path) -> Path:
    with zipfile.ZipFile(pack_path, "r") as archive:
        archive.extractall(destination)
    run_health_dir = destination / "runs" / "health"
    if not run_health_dir.exists():
        raise FileNotFoundError("Compressed pack missing runs/health directory")
    return run_health_dir


def load_manifest(run_health_dir: Path) -> Mapping[str, object]:
    manifest_path = run_health_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("Diagnostic pack missing manifest.json")
    return cast(Mapping[str, object], json.loads(manifest_path.read_text(encoding="utf-8")))


def load_summary(run_health_dir: Path) -> str | None:
    summary_path = run_health_dir / "summary.md"
    if not summary_path.exists():
        return None
    return summary_path.read_text(encoding="utf-8").strip()


def load_ui_index(run_health_dir: Path) -> Mapping[str, object]:
    index_path = run_health_dir / "ui-index.json"
    if not index_path.exists():
        raise FileNotFoundError("Diagnostic pack missing ui-index.json")
    return cast(Mapping[str, object], json.loads(index_path.read_text(encoding="utf-8")))


def build_review_payload(context: "UIIndexContext", summary_text: str | None) -> dict[str, object]:
    review_plan = context.run.next_check_plan
    deterministic = context.run.deterministic_next_checks
    queue_explanation = context.run.next_check_queue_explanation
    major_disagreements: list[str] = []
    missing_checks: list[str] = []
    generic_checks: list[str] = []
    ranking_issues: list[str] = []
    recommended: list[str] = []

    if review_plan:
        generic_checks = [candidate.description for candidate in review_plan.candidates if candidate.priority_label == "fallback"]
        ranking_issues = [
            f"Planner fell back to {candidate.description} without deterministic primacy"
            for candidate in review_plan.candidates
            if candidate.priority_label == "fallback"
        ]
        if review_plan.candidates:
            recommended.append(review_plan.candidates[0].description)
    if deterministic:
        if deterministic.cluster_count > (queue_explanation.cluster_state.deterministic_cluster_count if queue_explanation else 0):
            major_disagreements.append("Deterministic cluster coverage exceeds queue explanation.")
        total_checks = deterministic.total_next_check_count
        queue_checks = queue_explanation.candidate_accounting.generated if queue_explanation else 0
        if queue_checks < total_checks:
            missing_checks.append("Planner queue lacks some deterministic next checks.")
    if queue_explanation:
        if queue_explanation.status.endswith("mismatch"):
            major_disagreements.append("Queue explanation status signals inconsistency.")

    drift_flag = bool(queue_explanation and queue_explanation.cluster_state.degraded_cluster_count < (deterministic.cluster_count if deterministic else 0))
    return {
        "summary": summary_text or "Diagnostic pack review",
        "major_disagreements": major_disagreements,
        "generic_checks": generic_checks,
        "missing_checks": missing_checks,
        "ranking_issues": ranking_issues,
        "drift_misprioritized": drift_flag,
        "recommended_next_actions": recommended,
        "confidence": "medium",
    }


def build_review_artifact(
    run_health_dir: Path,
    manifest: Mapping[str, object],
    context: "UIIndexContext",
    summary_text: str | None,
    provider: str,
    purpose: ExternalAnalysisPurpose,
) -> DiagnosticPackReviewResult:
    run_id = context.run.run_id
    artifact_path = run_health_dir / "external-analysis" / f"{run_id}-diagnostic-pack-review-{provider}.json"
    payload = build_review_payload(context, summary_text)
    artifact = ExternalAnalysisArtifact(
        tool_name=provider,
        run_id=run_id,
        cluster_label=context.run.run_label,
        run_label=context.run.run_label,
        summary=summary_text or "Diagnostic pack review",
        status=ExternalAnalysisStatus.SUCCESS,
        provider=provider,
        purpose=purpose,
        payload=payload,
        source_artifact="ui-index.json",
        findings=tuple(str(item) for item in payload.get("major_disagreements", []) if isinstance(item, str)),
    )
    written = write_external_analysis_artifact(artifact_path, artifact)
    return DiagnosticPackReviewResult(artifact=artifact, artifact_path=written)


def create_diagnostic_pack_review(
    pack_path: Path,
    *,
    provider: str = "diagnostic-pack-review",
    temporarily_extract_to: Path | None = None,
) -> DiagnosticPackReviewResult:
    base_dir = Path(tempfile.mkdtemp(prefix="diagnostic-pack-review-") if temporarily_extract_to is None else temporarily_extract_to)
    try:
        run_health_dir = extract_diagnostic_pack(pack_path, base_dir)
        manifest = load_manifest(run_health_dir)
        summary_text = load_summary(run_health_dir)
        ui_index = load_ui_index(run_health_dir)
        context = build_ui_context(ui_index)
        result = build_review_artifact(
            run_health_dir,
            manifest,
            context,
            summary_text,
            provider,
            ExternalAnalysisPurpose.DIAGNOSTIC_PACK_REVIEW,
        )
        return result
    finally:
        if temporarily_extract_to is None:
            shutil.rmtree(base_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Review a diagnostic pack with a stronger model.")
    parser.add_argument("--pack", required=True, type=Path, help="Path to diagnostic pack ZIP")
    parser.add_argument("--provider", default="diagnostic-pack-review", help="Provider label for the review")
    args = parser.parse_args()
    result = create_diagnostic_pack_review(args.pack, provider=args.provider)
    print(f"Review artifact written to {result.artifact_path}")


if __name__ == "__main__":
    main()
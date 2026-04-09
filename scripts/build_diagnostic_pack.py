#!/usr/bin/env python3
"""Build a run-scoped diagnostic pack for operator review."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, cast

PACK_METADATA_CATEGORY = "pack_metadata"


def create_diagnostic_pack(
    run_id: str, runs_dir: Path, *, output_dir: Path | None = None
) -> Path:
    runs_dir = runs_dir.expanduser().resolve()
    run_health_dir = runs_dir / "health"
    if not run_health_dir.exists():
        raise FileNotFoundError(f"Runs directory missing health artifacts: {run_health_dir}")
    index_path = run_health_dir / "ui-index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"UI index missing for run {run_id}: {index_path}")
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    run_entry = cast(dict[str, object], index_data.get("run") or {})
    run_label = str(run_entry.get("run_label") or run_id)
    print(f"Preparing diagnostic pack for run {run_id} ({run_label})")

    artifacts = _collect_run_artifacts(run_id, run_health_dir)
    for category, paths in artifacts.items():
        print(f"  Collected {len(paths)} {category.replace('_', ' ')} artifact(s)")

    temp_dir = Path(tempfile.mkdtemp(prefix=f"diagnostic-pack-{run_id}-"))
    try:
        manifest_entries = _copy_artifacts(temp_dir, run_health_dir, artifacts)
        deterministic_raw = run_entry.get("deterministic_next_checks")
        queue_explanation_raw = run_entry.get("next_check_queue_explanation")
        deterministic = (
            cast(dict[str, object], deterministic_raw)
            if isinstance(deterministic_raw, Mapping)
            else None
        )
        queue_explanation = (
            cast(dict[str, object], queue_explanation_raw)
            if isinstance(queue_explanation_raw, Mapping)
            else None
        )
        summary_text = _build_summary_text(
            run_entry, deterministic, queue_explanation
        )
        (temp_dir / "summary.md").write_text(summary_text, encoding="utf-8")
        manifest_entries.append({"category": PACK_METADATA_CATEGORY, "path": "summary.md"})
        prompt_text = _build_analyst_prompt(run_id, run_label)
        (temp_dir / "analyst_prompt.md").write_text(prompt_text, encoding="utf-8")
        manifest_entries.append({"category": PACK_METADATA_CATEGORY, "path": "analyst_prompt.md"})
        manifest_entries.append({"category": PACK_METADATA_CATEGORY, "path": "manifest.json"})
        manifest = _build_manifest(run_id, run_label, manifest_entries)
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        final_output_dir = output_dir or run_health_dir / "diagnostic-packs"
        pack_path = _zip_pack(temp_dir, final_output_dir, run_id)
        print(f"Diagnostic pack ready: {pack_path}")
        return pack_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _collect_run_artifacts(run_id: str, run_health_dir: Path) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {
        "ui_index": [],
        "review": [],
        "assessments": [],
        "drilldowns": [],
        "triggers": [],
        "comparisons": [],
        "external_analysis": [],
    }
    index_path = run_health_dir / "ui-index.json"
    if index_path.exists():
        result["ui_index"].append(index_path)
    review_path = run_health_dir / "reviews" / f"{run_id}-review.json"
    if review_path.exists():
        result["review"].append(review_path)
    for folder in ("assessments", "drilldowns", "triggers", "comparisons"):
        directory = run_health_dir / folder
        if not directory.exists():
            continue
        pattern = f"{run_id}-*.json"
        for candidate in directory.glob(pattern):
            result[folder].append(candidate)
    external_dir = run_health_dir / "external-analysis"
    if external_dir.exists():
        for artifact in external_dir.glob("*.json"):
            if run_id in artifact.name:
                result["external_analysis"].append(artifact)
    return result


def _copy_artifacts(pack_root: Path, run_health_dir: Path, artifacts: dict[str, list[Path]]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for category, paths in artifacts.items():
        for source in paths:
            rel = source.relative_to(run_health_dir)
            destination = pack_root / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            entries.append({"category": category, "path": rel.as_posix()})
    return entries


def _build_manifest(run_id: str, run_label: str, files: Iterable[dict[str, str]]) -> dict[str, object]:
    files_list = list(files)
    return {
        "run_id": run_id,
        "run_label": run_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files_list),
        "files": files_list,
    }


def _build_summary_text(
    run_entry: dict[str, object],
    deterministic: dict[str, object] | None,
    queue_explanation: dict[str, object] | None,
) -> str:
    queue_state_raw = (queue_explanation or {}).get("clusterState")
    queue_state = (
        cast(dict[str, object], queue_state_raw)
        if isinstance(queue_state_raw, Mapping)
        else {}
    )
    degraded_labels = cast(list[str], queue_state.get("degradedClusterLabels") or [])
    raw_degraded_count = queue_state.get("degradedClusterCount")
    degraded_count = (
        _coerce_int_from_dict(queue_state, "degradedClusterCount")
        if raw_degraded_count is not None
        else len(degraded_labels)
    )
    clusters = deterministic.get("clusters") if isinstance(deterministic, dict) else []
    deterministic_map: dict[str, dict[str, object]] = {}
    if isinstance(clusters, list):
        for entry in clusters:
            if isinstance(entry, dict):
                deterministic_map[str(entry.get("label") or "")] = entry
    lines = [
        f"# Diagnostic summary for run {run_entry.get('run_label') or 'unknown'}",
        "",
        f"## Degraded clusters ({degraded_count})",
    ]
    if degraded_labels:
        for label in degraded_labels:
            lines.append(f"- {label}")
    else:
        lines.append("- None detected during this run")
    lines.extend(["", "## Deterministic next-check counts per cluster"])
    if degraded_labels:
        for label in degraded_labels:
            entry = deterministic_map.get(label)
            count = _coerce_int_from_dict(entry or {}, "deterministicNextCheckCount")
            lines.append(f"- {label}: {count} deterministic check{'s' if count != 1 else ''}")
    else:
        lines.append("- No degraded clusters recorded, so no deterministic next checks.")
    review_status = run_entry.get("review_enrichment_status")
    review_summary = "not attempted"
    if isinstance(review_status, dict):
        review_summary = str(review_status.get("status") or review_summary)
        reason = review_status.get("reason")
        if reason:
            review_summary = f"{review_summary} (reason: {reason})"
    elif isinstance(run_entry.get("review_enrichment"), dict):
        enrichment_entry = cast(dict[str, object], run_entry["review_enrichment"])
        review_summary = str(enrichment_entry.get("status") or "completed")
    planner_raw = run_entry.get("next_check_plan")
    planner = (
        cast(dict[str, object], planner_raw)
        if isinstance(planner_raw, Mapping)
        else {}
    )
    candidate_count = _coerce_int_from_dict(planner, "candidateCount")
    queue_status_raw = (queue_explanation or {}).get("status")
    queue_status = str(queue_status_raw or "unknown")
    lines.extend(
        [
            "",
            "## Review enrichment status",
            f"- {review_summary}",
            "",
            "## Planner / queue",
            f"- Planner candidate count: {candidate_count}",
            f"- Queue explanation status: {queue_status}",
        ]
    )
    total_checks = _coerce_int_from_dict(deterministic or {}, "totalNextCheckCount")
    queue_checks = _coerce_int_from_dict(queue_state, "deterministicNextCheckCount")
    cluster_checks = _coerce_int_from_dict(deterministic or {}, "clusterCount")
    queue_clusters = _coerce_int_from_dict(queue_state, "deterministicClusterCount")
    if total_checks == queue_checks and cluster_checks == queue_clusters:
        consistency_line = "Counts align between deterministic projection and queue explanation."
    else:
        consistency_line = (
            f"Mismatch detected (projection count {total_checks}/{cluster_checks} vs queue "
            f"{queue_checks}/{queue_clusters})."
        )
    lines.extend(["", "## Projection consistency", f"- {consistency_line}"])
    return "\n".join(lines) + "\n"


def _coerce_int_from_dict(source: dict[str, object], key: str) -> int:
    value = source.get(key) if source else None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _build_analyst_prompt(run_id: str, run_label: str) -> str:
    return """# Analyst prompt
Run: {run_label} ({run_id})

Please review the attached artifacts in the diagnostic pack and respond with concrete findings:

1. Validate the deterministic assessments and signal/finding structure to confirm the agent's interpretation reflects real evidence.
2. Review the deterministic next-check list, the queue explanation, and the queue candidate plan to ensure the proposed follow-ups align with the observed signals.
3. Explain why the planner produced (or did not produce) candidates by looking at review enrichment status, planner availability, and deterministic signal gaps.
4. Highlight duplicates, vague/generic commands, or automated suggestions that lack actionable signal so operators can prioritize accurate checks.
5. Identify any artifact-to-UI inconsistencies (missing drilldowns, mismatched cluster counts, etc.) that would erode trust in future runs.
6. Recommend the smallest safe next fixes or operator actions needed to close the remaining gaps.
""".format(run_id=run_id, run_label=run_label)


def _zip_pack(pack_root: Path, output_dir: Path, run_id: str) -> Path:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pack_name = f"diagnostic-pack-{run_id}-{timestamp}.zip"
    pack_path = output_dir / pack_name
    if pack_path.exists():
        pack_path.unlink()
    with zipfile.ZipFile(pack_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in pack_root.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(pack_root))
    return pack_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a diagnostic pack for a health run.")
    parser.add_argument("--run-id", required=True, help="Target run_id to package")
    parser.add_argument(
        "--runs-dir", required=True, help="Path to the runs directory (contains health/)",
    )
    parser.add_argument("--output-dir", help="Optional output directory for the pack")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs_dir = Path(args.runs_dir)
    output = Path(args.output_dir) if args.output_dir else None
    create_diagnostic_pack(args.run_id, runs_dir, output_dir=output)


if __name__ == "__main__":
    main()

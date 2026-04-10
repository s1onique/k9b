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
import sys
from typing import Iterable, Mapping, Sequence, cast

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from k8s_diag_agent.structured_logging import emit_structured_log

COMPONENT_NAME = "diagnostic-pack-builder"

PACK_METADATA_CATEGORY = "pack_metadata"
REVIEW_BUNDLE_SCHEMA = "diagnostic-pack-review-bundle/v1"
REVIEW_INPUT_SCHEMA = "diagnostic-pack-review-input-14b/v1"


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
    _log_structured_event(
        event="diagnostic-pack-start",
        message=f"Preparing diagnostic pack for run {run_id} ({run_label})",
        run_label=run_label,
        run_id=run_id,
        metadata={
            "runs_dir": str(runs_dir),
            "run_health_dir": str(run_health_dir),
        },
    )

    artifacts = _collect_run_artifacts(run_id, run_health_dir)
    for category, paths in artifacts.items():
        _log_structured_event(
            event="diagnostic-pack-collection-summary",
            message=f"Collected {len(paths)} {category.replace('_', ' ')} artifact(s)",
            run_label=run_label,
            run_id=run_id,
            metadata={
                "artifact_kind": category,
                "artifact_count": len(paths),
                "runs_dir": str(runs_dir),
                "run_health_dir": str(run_health_dir),
            },
        )

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
        digest_text = _build_digest_text(index_data, run_entry)
        (temp_dir / "digest.md").write_text(digest_text, encoding="utf-8")
        manifest_entries.append({"category": PACK_METADATA_CATEGORY, "path": "digest.md"})
        prompt_text = _build_analyst_prompt(run_id, run_label)
        (temp_dir / "analyst_prompt.md").write_text(prompt_text, encoding="utf-8")
        manifest_entries.append({"category": PACK_METADATA_CATEGORY, "path": "analyst_prompt.md"})
        final_manifest_entries = list(manifest_entries)
        final_manifest_entries.extend([
            {"category": PACK_METADATA_CATEGORY, "path": "review_bundle.json"},
            {"category": PACK_METADATA_CATEGORY, "path": "review_input_14b.json"},
            {"category": PACK_METADATA_CATEGORY, "path": "manifest.json"},
        ])
        review_bundle = _build_review_bundle(
            run_id=run_id,
            run_health_dir=run_health_dir,
            artifacts=artifacts,
            index_data=index_data,
            run_entry=run_entry,
            included_paths=[entry["path"] for entry in final_manifest_entries],
        )
        (temp_dir / "review_bundle.json").write_text(
            json.dumps(review_bundle, indent=2), encoding="utf-8"
        )
        review_input = _build_review_input_14b(index_data, run_entry, review_bundle)
        (temp_dir / "review_input_14b.json").write_text(
            json.dumps(review_input, indent=2), encoding="utf-8"
        )
        manifest = _build_manifest(run_id, run_label, final_manifest_entries)
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        final_output_dir = output_dir or run_health_dir / "diagnostic-packs"
        pack_path = _zip_pack(temp_dir, final_output_dir, run_id)
        _log_structured_event(
            event="diagnostic-pack-ready",
            message=f"Diagnostic pack ready: {pack_path}",
            run_label=run_label,
            run_id=run_id,
            metadata={
                "pack_path": str(pack_path),
                "output_dir": str(final_output_dir),
                "runs_dir": str(runs_dir),
                "run_health_dir": str(run_health_dir),
            },
        )
        return pack_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _log_structured_event(
    *,
    event: str,
    message: str,
    run_label: str,
    run_id: str | None,
    severity: str = "INFO",
    metadata: Mapping[str, object] | None = None,
) -> None:
    metadata_dict = dict(metadata or {})
    emit_structured_log(
        component=COMPONENT_NAME,
        message=message,
        severity=severity,
        run_label=run_label,
        run_id=run_id,
        metadata=metadata_dict,
        event=event,
    )


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


def _build_review_bundle(
    run_id: str,
    run_health_dir: Path,
    artifacts: dict[str, list[Path]],
    index_data: dict[str, object],
    run_entry: dict[str, object],
    included_paths: Iterable[str],
) -> dict[str, object]:
    run_label = run_entry.get("run_label")
    run_id_value = str(run_entry.get("run_id") or run_id)
    timestamp = run_entry.get("timestamp")
    review_paths = artifacts.get("review", [])
    return {
        "schema_version": REVIEW_BUNDLE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run": {
            "run_label": str(run_label) if isinstance(run_label, str) else None,
            "run_id": run_id_value,
            "timestamp": str(timestamp) if timestamp else None,
        },
        "fleet_summary": _build_fleet_summary(index_data, run_entry),
        "review": _build_review_entry(run_health_dir, run_id, review_paths),
        "assessments": _build_cluster_entries(artifacts.get("assessments", []), run_health_dir, run_id),
        "drilldowns": _build_cluster_entries(artifacts.get("drilldowns", []), run_health_dir, run_id),
        "triggers": _build_cluster_entries(artifacts.get("triggers", []), run_health_dir, run_id),
        "comparisons": _build_comparison_entries(artifacts.get("comparisons", []), run_health_dir),
        "external_analysis": _build_external_analysis_entries(artifacts.get("external_analysis", []), run_health_dir),
        "proposals": _build_proposal_entries(index_data),
        "deterministic_next_checks": _first_mapping(index_data, run_entry, "deterministic_next_checks"),
        "review_enrichment": _extract_mapping(run_entry, "review_enrichment"),
        "provider_execution": _extract_mapping(run_entry, "provider_execution"),
        "diagnostic_pack_review": _extract_mapping(run_entry, "diagnostic_pack_review"),
        "artifact_manifest": {
            "summary_path": "summary.md",
            "digest_path": "digest.md",
            "ui_index_path": "ui-index.json",
            "review_bundle_path": "review_bundle.json",
            "included_paths": _normalize_included_paths(included_paths),
        },
    }


def _build_review_input_14b(
    index_data: dict[str, object],
    run_entry: dict[str, object],
    review_bundle: dict[str, object],
) -> dict[str, object]:
    run_obj = review_bundle.get("run") or {}
    run_id_value = str(run_entry.get("run_id") or run_obj.get("run_id") or "")
    run_label = str(run_entry.get("run_label") or run_obj.get("run_label") or "")
    review_entry = cast(dict[str, object], review_bundle.get("review") or {})
    review_content = cast(dict[str, object], review_entry.get("content") or {})
    cluster_entries = cast(list[dict[str, object]], review_bundle.get("assessments") or [])
    drilldown_entries = cast(list[dict[str, object]], review_bundle.get("drilldowns") or [])
    external_entries = cast(list[dict[str, object]], review_bundle.get("external_analysis") or [])
    comparison_entries = cast(list[dict[str, object]], review_bundle.get("comparisons") or [])
    proposal_entries = cast(list[dict[str, object]], review_bundle.get("proposals") or [])
    bundle_manifest = cast(dict[str, object], review_bundle.get("artifact_manifest") or {})
    included_paths = cast(list[str], bundle_manifest.get("included_paths") or [])
    return {
        "schema_version": REVIEW_INPUT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": run_id_value,
        "source_review_bundle_path": "review_bundle.json",
        "run": {
            "run_label": run_label or None,
            "run_id": run_id_value or None,
            "timestamp": run_obj.get("timestamp"),
        },
        "fleet_summary": _build_fleet_summary(index_data, run_entry),
        "review_summary": _build_review_summary(review_entry, review_content),
        "cluster_summaries": _build_cluster_summaries(
            cluster_entries, drilldown_entries, external_entries
        ),
        "comparison_summary": _build_comparison_summary(comparison_entries),
        "external_analysis_summary": _build_external_analysis_summary(external_entries),
        "proposal_summary": _build_proposal_summary(proposal_entries),
        "review_enrichment": _extract_mapping(review_bundle, "review_enrichment"),
        "provider_execution": _extract_mapping(review_bundle, "provider_execution"),
        "artifact_manifest": {
            "review_input_14b_path": "review_input_14b.json",
            "review_bundle_path": "review_bundle.json",
            "digest_path": "digest.md",
            "included_paths": _normalize_included_paths(included_paths + ["review_input_14b.json"]),
        },
    }


def _build_review_summary(
    review_entry: dict[str, object], review_content: dict[str, object]
) -> dict[str, object] | None:
    if not review_entry or not review_content:
        return None
    selected_drilldowns = []
    for selection in cast(list[dict[str, object]], review_content.get("selected_drilldowns") or []):
        selected_drilldowns.append(
            {
                "cluster_label": selection.get("cluster_label"),
                "reasons": _ensure_strings(selection.get("reasons")),
            }
        )
    return {
        "path": review_entry.get("path"),
        "quality_summary": _trim_quality_summary(review_content.get("quality_summary")),
        "failure_modes": _ensure_strings(review_content.get("failure_modes")),
        "selected_drilldowns": selected_drilldowns,
    }


def _build_cluster_summaries(
    cluster_entries: list[dict[str, object]],
    drilldown_entries: list[dict[str, object]],
    external_entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    drilldown_map: dict[str, dict[str, object]] = {}
    for entry in drilldown_entries:
        label = entry.get("cluster_label")
        if isinstance(label, str):
            drilldown_map[label] = entry
    external_map: dict[str, list[str]] = {}
    for entry in external_entries:
        label = entry.get("cluster_label")
        if not isinstance(label, str):
            continue
        path_value = entry.get("path")
        if isinstance(path_value, str):
            external_map.setdefault(label, []).append(path_value)
    summaries: list[dict[str, object]] = []
    for assessment in cluster_entries:
        label = assessment.get("cluster_label")
        if not isinstance(label, str):
            continue
        content = cast(dict[str, object], assessment.get("content") or {})
        drilldown_entry = drilldown_map.get(label)
        summaries.append(
            {
                "cluster_label": label,
                "health_rating": content.get("health_rating"),
                "top_findings": _extract_descriptions(content.get("findings"), ("description", "summary")),
                "top_hypotheses": _extract_descriptions(content.get("hypotheses"), ("description", "summary")),
                "top_next_checks": _build_top_next_checks(content),
                "drilldown_summary": _build_drilldown_summary(
                    cast(dict[str, object], drilldown_entry.get("content") if drilldown_entry else {})
                    if drilldown_entry
                    else {},
                ),
                "artifact_paths": {
                    "assessment": assessment.get("path"),
                    "drilldown": (drilldown_entry or {}).get("path"),
                    "external_analysis": _ensure_strings(external_map.get(label)),
                },
            }
        )
    return summaries


def _build_top_next_checks(content: Mapping[str, object]) -> list[str]:
    candidates: list[str] = []
    for section in ("next_evidence_to_collect", "next_checks", "recommended_next_checks"):
        for entry in cast(list[object], content.get(section) or []):
            text = _extract_first_string(entry, ("description", "summary"))
            if text:
                candidates.append(text)
            if len(candidates) >= 3:
                return candidates
    recommended_action = content.get("recommended_action")
    if isinstance(recommended_action, Mapping):
        description = _extract_first_string(recommended_action, ("description",))
        if description:
            candidates.append(description)
    return candidates[:3]


def _build_drilldown_summary(content: dict[str, object]) -> dict[str, object] | None:
    if not content:
        return None
    return {
        "trigger_reasons": _ensure_strings(content.get("trigger_reasons")),
        "non_running_pods": len(cast(list[object], content.get("non_running_pods") or [])),
        "summary": _flatten_summary(content.get("summary")),
    }


def _build_comparison_summary(comparisons: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for entry in comparisons:
        content = cast(dict[str, object], entry.get("content") or {})
        result.append(
            {
                "path": entry.get("path"),
                "summary": {
                    "summary": str(content.get("summary") or "comparison"),
                    "primary_cluster": content.get("primary_cluster_label"),
                    "secondary_cluster": content.get("secondary_cluster_label"),
                },
                "top_drifts": _extract_top_drifts(content),
            }
        )
    return result


def _build_external_analysis_summary(external: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for entry in external:
        content = cast(dict[str, object], entry.get("content") or {})
        result.append(
            {
                "purpose": content.get("purpose"),
                "cluster_label": entry.get("cluster_label"),
                "provider": content.get("provider"),
                "status": content.get("status"),
                "summary": {
                    "text": str(content.get("summary") or ""),
                    "findings": _extract_descriptions(content.get("findings"), ("description",)),
                    "suggested_next_checks": _ensure_strings(content.get("suggested_next_checks")),
                },
                "path": entry.get("path"),
            }
        )
    return result


def _build_proposal_summary(proposals: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for proposal in proposals:
        content = cast(dict[str, object], proposal.get("content") or {})
        summary_text = _extract_first_string(content, ("rationale", "summary", "expected_benefit"))
        result.append(
            {
                "proposal_id": proposal.get("proposal_id"),
                "summary": summary_text or "proposal",
                "path": proposal.get("path"),
            }
        )
    return result


def _trim_quality_summary(metrics: object | None) -> list[dict[str, object]]:
    metric_list = cast(list[dict[str, object]], metrics or [])
    trimmed: list[dict[str, object]] = []
    for metric in metric_list[:3]:
        trimmed.append({
            "dimension": metric.get("dimension"),
            "level": metric.get("level"),
            "score": metric.get("score"),
        })
    return trimmed


def _extract_descriptions(
    items: object | None, keys: Sequence[str]
) -> list[str]:
    results: list[str] = []
    for entry in cast(list[object], items or []):
        text = _extract_first_string(entry, keys)
        if text:
            results.append(text)
        if len(results) >= 3:
            break
    return results


def _extract_top_drifts(content: Mapping[str, object]) -> list[str]:
    drifts = content.get("top_drifts") or content.get("drift_reasons") or []
    return _ensure_strings(drifts)[:3]


def _ensure_strings(value: object | None) -> list[str]:
    results: list[str] = []
    for entry in cast(list[object], value or []):
        if isinstance(entry, str):
            results.append(entry)
    return results


def _extract_first_string(entry: object, keys: Sequence[str]) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, Mapping):
        for key in keys:
            candidate = entry.get(key)
            if isinstance(candidate, str):
                return candidate
    return None


def _flatten_summary(value: object | None) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        parts: list[str] = []
        for key, val in value.items():
            parts.append(f"{key}: {val}")
        return "; ".join(parts)
    return ""

def _build_fleet_summary(index_data: dict[str, object], run_entry: dict[str, object]) -> dict[str, object]:
    cluster_count = _coerce_int_from_dict(run_entry, "cluster_count")
    fleet_status = cast(dict[str, object], index_data.get("fleet_status") or {})
    degraded_clusters = cast(list[str], fleet_status.get("degraded_clusters") or [])
    degraded_count = len(degraded_clusters)
    healthy_count = None
    if cluster_count or degraded_count:
        healthy_count = max(cluster_count - degraded_count, 0)
    return {
        "cluster_count": cluster_count,
        "healthy_count": healthy_count,
        "degraded_count": degraded_count,
        "proposal_count": _coerce_optional_int(run_entry, "proposal_count"),
        "drilldown_count": _coerce_optional_int(run_entry, "drilldown_count"),
        "external_analysis_count": _coerce_optional_int(run_entry, "external_analysis_count"),
    }


def _build_review_entry(run_health_dir: Path, run_id: str, review_paths: list[Path]) -> dict[str, object | None]:
    if not review_paths:
        return {"path": None, "content": None}
    selected = min(review_paths, key=lambda path: path.as_posix())
    return {
        "path": selected.relative_to(run_health_dir).as_posix(),
        "content": _load_json_object(selected),
    }


def _build_cluster_entries(paths: list[Path], run_health_dir: Path, run_id: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(paths, key=lambda candidate: candidate.as_posix()):
        entries.append(
            {
                "cluster_label": _extract_cluster_label(path, run_id),
                "path": path.relative_to(run_health_dir).as_posix(),
                "content": _load_json_object(path),
            }
        )
    return entries


def _build_comparison_entries(paths: list[Path], run_health_dir: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(paths, key=lambda candidate: candidate.as_posix()):
        entries.append(
            {
                "cluster_label": None,
                "path": path.relative_to(run_health_dir).as_posix(),
                "content": _load_json_object(path),
            }
        )
    return entries


def _build_external_analysis_entries(paths: list[Path], run_health_dir: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(paths, key=lambda candidate: candidate.as_posix()):
        content = _load_json_object(path)
        cluster_label = None
        if isinstance(content, Mapping):
            raw_label = content.get("cluster_label")
            if isinstance(raw_label, str):
                cluster_label = raw_label
        entries.append(
            {
                "cluster_label": cluster_label,
                "path": path.relative_to(run_health_dir).as_posix(),
                "content": content,
            }
        )
    return entries


def _build_proposal_entries(index_data: dict[str, object]) -> list[dict[str, object]]:
    proposals = cast(list[dict[str, object]], index_data.get("proposals") or [])
    entries: list[dict[str, object]] = []
    for proposal in proposals:
        proposal_id = proposal.get("proposal_id")
        artifact_path = proposal.get("artifact_path")
        path_value = str(artifact_path) if artifact_path else f"proposals/{proposal_id or 'unknown'}.json"
        entries.append(
            {
                "proposal_id": str(proposal_id) if proposal_id is not None else None,
                "path": path_value,
                "content": dict(proposal),
            }
        )
    return entries


def _coerce_optional_int(source: dict[str, object], key: str) -> int | None:
    if key not in source:
        return None
    value = source.get(key)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _extract_mapping(source: dict[str, object], key: str) -> dict[str, object] | None:
    value = source.get(key)
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _first_mapping(
    primary: dict[str, object], secondary: dict[str, object], key: str
) -> dict[str, object] | None:
    mapping = _extract_mapping(primary, key)
    if mapping is not None:
        return mapping
    return _extract_mapping(secondary, key)


def _normalize_included_paths(paths: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for path in paths:
        if path not in seen:
            seen.append(path)
    return seen


def _load_json_object(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _extract_cluster_label(path: Path, run_id: str) -> str | None:
    stem = path.stem
    prefix = f"{run_id}-"
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    return None


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


def _build_digest_text(index_data: dict[str, object], run_entry: dict[str, object]) -> str:
    lines: list[str] = ["# Diagnostic pack digest", ""]
    run_label = str(run_entry.get("run_label") or "unknown")
    run_id = str(run_entry.get("run_id") or "unknown")
    timestamp = run_entry.get("timestamp")
    lines.extend(
        [
            "## Run identity",
            f"- Run label: {run_label}",
            f"- Run id: {run_id}",
        ]
    )
    if timestamp:
        lines.append(f"- Run timestamp: {timestamp}")

    fleet_status = cast(dict[str, object], index_data.get("fleet_status") or {})
    degraded_clusters = cast(list[str], fleet_status.get("degraded_clusters") or [])
    cluster_count = _coerce_int_from_dict(run_entry, "cluster_count")
    proposal_count = _coerce_int_from_dict(run_entry, "proposal_count")
    drilldown_count = _coerce_int_from_dict(run_entry, "drilldown_count")
    external_analysis_count = _coerce_int_from_dict(run_entry, "external_analysis_count")
    healthy_count = None
    if cluster_count and degraded_clusters:
        healthy_count = max(cluster_count - len(degraded_clusters), 0)
    lines.extend(["", "## Fleet summary"])
    lines.append(f"- Monitored clusters: {cluster_count}")
    if healthy_count is not None:
        lines.append(f"- Healthy clusters: {healthy_count}")
    lines.append(f"- Degraded clusters ({len(degraded_clusters)}): {', '.join(sorted(degraded_clusters)) or 'none'}")
    if proposal_count:
        lines.append(f"- Proposal count: {proposal_count}")
    if drilldown_count:
        lines.append(f"- Drilldown count: {drilldown_count}")
    if external_analysis_count:
        lines.append(f"- External analysis count: {external_analysis_count}")

    cluster_entries = cast(list[dict[str, object]], index_data.get("clusters") or [])
    if cluster_entries:
        lines.extend(["", "## Top problems by cluster"])
        for cluster in sorted(cluster_entries, key=lambda entry: str(entry.get("label") or "")):
            label = str(cluster.get("label") or "unknown")
            rating = str(cluster.get("health_rating") or "unknown")
            reason = (
                str(cluster.get("top_problem") or cluster.get("top_trigger_reason") or "not reported")
            )
            lines.extend(
                [
                    f"### {label}",
                    f"- Health rating: {rating}",
                    f"- Top problem: {reason}",
                ]
            )

    notifications = cast(list[dict[str, object]], index_data.get("notification_history") or [])
    comparisons = []
    for note in notifications:
        kind = str(note.get("kind") or "").lower()
        if "comparison" not in kind:
            continue
        summary = str(note.get("summary") or "comparison")
        reasons = []
        for detail in cast(list[dict[str, object]], note.get("details") or []):
            label = str(detail.get("label") or "").lower()
            if label in {"reasons", "intent"}:
                value = detail.get("value")
                if value:
                    reasons.append(str(value))
        reason_text = "; ".join(sorted(set(reasons))) if reasons else "details in artifact"
        comparisons.append((summary, reason_text))
    lines.extend(["", "## Triggered comparison summary"])
    if comparisons:
        for summary, reason_text in comparisons:
            lines.append(f"- {summary} — reason: {reason_text}")
    else:
        lines.append("- None recorded for this run.")

    drilldowns = cast(list[dict[str, object]], index_data.get("drilldowns") or [])
    if drilldowns:
        lines.extend(["", "## Drilldown summary"])
        for drilldown in sorted(drilldowns, key=lambda entry: str(entry.get("label") or "")):
            label = str(drilldown.get("label") or "unknown")
            triggers = cast(list[str], drilldown.get("trigger_reasons") or [])
            warnings = drilldown.get("warning_events")
            non_running = len(cast(list[object], drilldown.get("non_running_pods") or []))
            summary_counts = cast(dict[str, object], drilldown.get("summary") or {})
            summary_frag = ", ".join(
                f"{key}: {summary_counts.get(key)}"
                for key in sorted(summary_counts)
                if summary_counts.get(key) is not None
            )
            lines.append(
                f"- {label}: triggers {', '.join(triggers) or 'none'}, warnings {warnings or 0}, "
                f"non-running pods {non_running}{', ' + summary_frag if summary_frag else ''}"
            )

    deterministic = cast(dict[str, object], index_data.get("deterministic_next_checks") or {})
    deterministic_clusters = cast(list[dict[str, object]], deterministic.get("clusters") or [])
    if deterministic_clusters:
        lines.extend(["", "## Deterministic next checks summary"])
        for cluster in sorted(deterministic_clusters, key=lambda entry: str(entry.get("label") or "")):
            label = str(cluster.get("label") or "unknown")
            problem = str(cluster.get("top_problem") or cluster.get("triggerReason") or "not reported")
            count = _coerce_int_from_dict(cluster, "deterministicNextCheckCount")
            summaries = cast(list[dict[str, object]], cluster.get("deterministicNextCheckSummaries") or [])
            sample = ""
            if summaries:
                first = summaries[0]
                sample = str(first.get("description") or "")
            lines.append(f"- {label}: {count} checks for {problem}")
            if sample:
                lines.append(f"  - Sample: {sample}")

    lines.extend(["", "## Provider-assisted review/enrichment"])
    enrichment = run_entry.get("review_enrichment")
    if isinstance(enrichment, Mapping):
        status = str(enrichment.get("status") or "unknown")
        summary = str(enrichment.get("summary") or "no summary")
        lines.append(f"- Review enrichment ({status}): {summary}")
    else:
        lines.append("- Review enrichment: not present")
    pack_review = run_entry.get("diagnostic_pack_review")
    if isinstance(pack_review, Mapping):
        provider_status = str(pack_review.get("providerStatus") or pack_review.get("provider_status") or "unknown")
        summary = str(pack_review.get("providerSummary") or pack_review.get("summary") or "no summary")
        lines.append(f"- Pack review ({provider_status}): {summary}")

    proposals = cast(list[dict[str, object]], index_data.get("proposals") or [])
    lines.extend(["", "## Proposal summary", f"- Total proposals: {len(proposals)}"])
    if proposals:
        status_counts: dict[str, int] = {}
        example_ids: list[str] = []
        for proposal in proposals:
            status = str(proposal.get("status") or "unknown").lower()
            status_counts[status] = status_counts.get(status, 0) + 1
            if len(example_ids) < 3 and proposal.get("proposal_id"):
                example_ids.append(str(proposal.get("proposal_id")))
        for status in sorted(status_counts):
            lines.append(f"- {status}: {status_counts[status]}")
        if example_ids:
            lines.append(f"- Examples: {', '.join(example_ids)}")

    lines.extend(["", "## Artifact map"])
    lines.extend(
        [
            "- ui-index.json",
            f"- reviews/{run_id}-review.json",
            f"- assessments/{run_id}-<cluster>.json",
            f"- drilldowns/{run_id}-<cluster>.json",
            f"- triggers/{run_id}-*.json",
            f"- comparisons/{run_id}-*.json",
            f"- external-analysis/{run_id}-*.json",
            "- summary.md",
            "- digest.md",
            "- analyst_prompt.md",
            "- manifest.json",
        ]
    )
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

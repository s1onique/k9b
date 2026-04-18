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
from k8s_diag_agent.health.utils import normalize_ref
from k8s_diag_agent.external_analysis.alertmanager_artifact import (
    read_alertmanager_snapshot,
    read_alertmanager_compact,
)

COMPONENT_NAME = "diagnostic-pack-builder"
PACK_METADATA_CATEGORY = "pack_metadata"
REVIEW_BUNDLE_SCHEMA = "diagnostic-pack-review-bundle/v1"
REVIEW_INPUT_SCHEMA = "diagnostic-pack-review-input-14b/v1"
MAX_TOP_FINDINGS = 7
MAX_TOP_HYPOTHESES = 5
MAX_TOP_NEXT_CHECKS = 6
MAX_TOP_DRIFTS = 7
MAX_PATTERN_KEYS = 5


# Directory name for the stable "latest" unpacked pack mirror
LATEST_PACK_DIR_NAME = "latest"


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

        # Write stable uncompressed "latest" mirror for operator/reviewer convenience
        _write_latest_pack_mirror(
            final_output_dir,
            review_bundle=review_bundle,
            review_input=review_input,
            run_id=run_id,
        )

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
                "latest_pack_dir": str(final_output_dir / LATEST_PACK_DIR_NAME),
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
        "alertmanager": [],  # Alertmanager snapshot and compact artifacts
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
    # Collect Alertmanager artifacts (snapshot and compact)
    # Alertmanager artifacts are stored alongside other run artifacts in run_health_dir
    am_snapshot = run_health_dir / f"{run_id}-alertmanager-snapshot.json"
    if am_snapshot.exists():
        result["alertmanager"].append(am_snapshot)
    am_compact = run_health_dir / f"{run_id}-alertmanager-compact.json"
    if am_compact.exists():
        result["alertmanager"].append(am_compact)
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
    # Build Alertmanager context for prompt-facing provenance
    alertmanager_context = _build_alertmanager_context(run_health_dir, run_id)
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
        "alertmanager_context": alertmanager_context,
        "artifact_manifest": {
            "summary_path": "summary.md",
            "digest_path": "digest.md",
            "ui_index_path": "ui-index.json",
            "review_bundle_path": "review_bundle.json",
            "included_paths": _normalize_included_paths(included_paths),
        },
    }


def _build_alertmanager_context(run_health_dir: Path, run_id: str) -> dict[str, object]:
    """Build Alertmanager context for review bundle.
    
    Reads snapshot and compact artifacts and builds prompt-facing context.
    Returns unavailable context if artifacts are missing.
    No live Alertmanager fetch is performed.
    """
    snapshot_path = run_health_dir / f"{run_id}-alertmanager-snapshot.json"
    compact_path = run_health_dir / f"{run_id}-alertmanager-compact.json"
    
    snapshot_exists = snapshot_path.exists()
    compact_exists = compact_path.exists()
    
    if not compact_exists:
        return {
            "available": False,
            "source": "unavailable",
            "status": None,
            "compact": None,
            "snapshot_available": snapshot_exists,
        }
    
    compact = read_alertmanager_compact(compact_path)
    if compact is None:
        return {
            "available": False,
            "source": "unavailable",
            "status": None,
            "compact": None,
            "snapshot_available": snapshot_exists,
        }
    
    # Build prompt-facing compact context
    return {
        "available": True,
        "source": "run_artifact",
        "status": compact.status,
        "compact": compact.to_dict(),
        "snapshot_available": snapshot_exists,
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
    label_map, _ = _build_cluster_label_map(cluster_entries)
    # Extract Alertmanager context from review bundle for replayability
    alertmanager_context = cast(dict[str, object], review_bundle.get("alertmanager_context") or {
        "available": False,
        "source": "not_present",
        "status": None,
        "compact": None,
        "snapshot_available": False,
    })
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
        "review_summary": _build_review_summary(review_entry, review_content, label_map),
        "cluster_summaries": _build_cluster_summaries(
            cluster_entries,
            drilldown_entries,
            external_entries,
            label_map,
        ),
        "comparison_summary": _build_comparison_summary(
            comparison_entries, label_map, run_id_value
        ),
        "external_analysis_summary": _build_external_analysis_summary(external_entries),
        "next_check_execution_summary": _build_next_check_execution_summary(external_entries),
        "next_check_lifecycle_summary": _build_next_check_lifecycle_summary(external_entries),
        "proposal_summary": _build_proposal_summary(proposal_entries),
        "review_enrichment": _extract_mapping(review_bundle, "review_enrichment"),
        "provider_execution": _extract_mapping(review_bundle, "provider_execution"),
        "alertmanager_context": alertmanager_context,
        "artifact_manifest": {
            "review_input_14b_path": "review_input_14b.json",
            "review_bundle_path": "review_bundle.json",
            "digest_path": "digest.md",
            "included_paths": _normalize_included_paths(included_paths + ["review_input_14b.json"]),
        },
    }


def _build_cluster_label_map(cluster_entries: list[dict[str, object]]) -> tuple[dict[str, str], dict[str, str]]:
    mapping: dict[str, str] = {}
    lookup: dict[str, str] = {}
    for entry in cluster_entries:
        label = entry.get("cluster_label")
        if not isinstance(label, str):
            continue
        normalized = normalize_ref(label)
        if not normalized:
            continue
        mapping[label] = normalized
        lookup[normalized] = label
    return mapping, lookup


def _build_review_summary(
    review_entry: dict[str, object], review_content: dict[str, object],
    label_map: dict[str, str],
) -> dict[str, object] | None:
    if not review_entry or not review_content:
        return None
    selected_drilldowns = []
    for selection in cast(list[dict[str, object]], review_content.get("selected_drilldowns") or []):
        selected_drilldowns.append(
            {
                "cluster_label": _normalize_reference_label(
                    selection.get("cluster_label") or selection.get("label"), label_map
                ),
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
    label_map: dict[str, str],
) -> list[dict[str, object]]:
    drilldown_map: dict[str, dict[str, object]] = {}
    for entry in drilldown_entries:
        normalized = _normalize_reference_label(entry.get("cluster_label"), label_map)
        if not normalized:
            normalized = _normalize_reference_label(entry.get("label"), label_map)
        if normalized:
            drilldown_map[normalized] = entry
    external_paths_map: dict[str, list[str]] = {}
    external_check_map: dict[str, list[str]] = {}
    for entry in external_entries:
        normalized = _normalize_reference_label(entry.get("cluster_label"), label_map)
        if not normalized:
            normalized = _normalize_reference_label(entry.get("label"), label_map)
        if not normalized:
            continue
        path_value = entry.get("path")
        if _is_auto_drilldown_entry(entry) and isinstance(path_value, str):
            external_paths_map.setdefault(normalized, []).append(path_value)
        content = cast(dict[str, object], entry.get("content") or {})
        suggestions = _ensure_strings(content.get("suggested_next_checks"))
        summary_text = _extract_first_string(content, ("summary",))
        extras = _ensure_strings(content.get("findings"))
        external_candidates: list[str] = []
        external_candidates.extend(suggestions)
        if summary_text:
            external_candidates.append(summary_text)
        external_candidates.extend(extras)
        if external_candidates:
            external_check_map.setdefault(normalized, []).extend(external_candidates)
    summaries: list[dict[str, object]] = []
    for assessment in cluster_entries:
        normalized_label = _normalize_reference_label(assessment.get("cluster_label"), label_map)
        if not normalized_label:
            normalized_label = _normalize_reference_label(assessment.get("label"), label_map)
        if not normalized_label:
            continue
        content = cast(dict[str, object], assessment.get("content") or {})
        assessment_section = cast(dict[str, object], content.get("assessment") or content)
        drilldown_entry = drilldown_map.get(normalized_label)
        drilldown_content = (
            cast(dict[str, object], drilldown_entry.get("content") or {})
            if drilldown_entry
            else {}
        )
        summaries.append({
            "cluster_label": normalized_label,
            "health_rating": assessment_section.get("health_rating") or content.get("health_rating"),
            "top_findings": _extract_descriptions(
                assessment_section.get("findings"), ("description", "summary")
            ),
            "top_hypotheses": _extract_descriptions(
                assessment_section.get("hypotheses"), ("description", "summary")
            ),
            "top_next_checks": _build_top_next_checks(
                assessment_section,
                drilldown_content,
                external_check_map.get(normalized_label, []),
            ),
            "drilldown_summary": _build_drilldown_summary(drilldown_content),
            "artifact_paths": {
                "assessment": assessment.get("path"),
                "drilldown": (drilldown_entry or {}).get("path"),
                "external_analysis": external_paths_map.get(normalized_label) or [],
            },
        })
    return summaries


def _build_top_next_checks(
    assessment: Mapping[str, object],
    drilldown: Mapping[str, object],
    external_next_checks: Sequence[str],
) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(text: str | None) -> None:
        if not text:
            return
        text = text.strip()
        if not text or text in seen:
            return
        seen.add(text)
        candidates.append(text)

    for section in ("next_evidence_to_collect", "next_checks", "recommended_next_checks"):
        for entry in cast(list[object], assessment.get(section) or []):
            text = _extract_first_string(entry, ("description", "summary"))
            add_candidate(text)
            if len(candidates) >= MAX_TOP_NEXT_CHECKS:
                return candidates
    recommended_action = cast(Mapping[str, object], assessment.get("recommended_action") or {})
    add_candidate(_extract_first_string(recommended_action, ("description",)))
    add_candidate(_flatten_summary(drilldown.get("summary")))
    for extra in external_next_checks:
        add_candidate(extra)
        if len(candidates) >= MAX_TOP_NEXT_CHECKS:
            return candidates
    return candidates[:MAX_TOP_NEXT_CHECKS]


def _build_drilldown_summary(content: dict[str, object]) -> dict[str, object] | None:
    if not content:
        return None
    return {
        "trigger_reasons": _ensure_strings(content.get("trigger_reasons")),
        "warning_event_count": len(cast(list[object], content.get("warning_events") or [])),
        "non_running_pod_count": len(cast(list[object], content.get("non_running_pods") or [])),
        "affected_namespaces": _ensure_strings(content.get("affected_namespaces")),
        "pattern_keys": _extract_pattern_keys(content.get("pattern_details")),
    }


def _build_comparison_summary(
    comparisons: list[dict[str, object]],
    label_map: dict[str, str],
    run_id: str,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for entry in comparisons:
        content = cast(dict[str, object], entry.get("content") or {})
        primary_label = _normalize_reference_label(content.get("primary_cluster_label"), label_map)
        secondary_label = _normalize_reference_label(content.get("secondary_cluster_label"), label_map)
        if not primary_label or not secondary_label:
            derived_primary, derived_secondary = _extract_comparison_clusters(entry.get("path"), run_id, label_map)
            primary_label = primary_label or derived_primary
            secondary_label = secondary_label or derived_secondary
        result.append(
            {
                "path": entry.get("path"),
                "summary": {
                    "summary": str(content.get("summary") or "comparison"),
                    "primary_cluster": primary_label,
                    "secondary_cluster": secondary_label,
                },
                "top_drifts": _extract_top_drifts(content),
            }
        )
    return result


def _is_next_check_planning_entry(entry: dict[str, object]) -> bool:
    """Check if an external analysis entry is a next-check-planning artifact."""
    content = cast(dict[str, object], entry.get("content") or {})
    purpose = content.get("purpose")
    return isinstance(purpose, str) and purpose == "next-check-planning"


def _is_next_check_approval_entry(entry: dict[str, object]) -> bool:
    """Check if an external analysis entry is a next-check-approval artifact."""
    content = cast(dict[str, object], entry.get("content") or {})
    purpose = content.get("purpose")
    return isinstance(purpose, str) and purpose == "next-check-approval"


def _is_next_check_promotion_entry(entry: dict[str, object]) -> bool:
    """Check if an external analysis entry is a next-check-promotion artifact."""
    content = cast(dict[str, object], entry.get("content") or {})
    purpose = content.get("purpose")
    return isinstance(purpose, str) and purpose == "next-check-promotion"


def _is_next_check_execution_entry(entry: dict[str, object]) -> bool:
    """Check if an external analysis entry is a next-check-execution artifact."""
    content = cast(dict[str, object], entry.get("content") or {})
    purpose = content.get("purpose")
    return isinstance(purpose, str) and purpose == "next-check-execution"


def _build_next_check_execution_summary(external: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build a reviewer-friendly summary of next-check execution outcomes.
    
    Extracts the key fields that a reviewer model needs without requiring it to
    scan all external-analysis artifacts manually. This includes:
    - executed check description
    - target cluster
    - command family / preview
    - execution status (success/failed/timed-out)
    - duration
    - summary
    - artifact path pointer
    """
    result: list[dict[str, object]] = []
    for entry in external:
        if not _is_next_check_execution_entry(entry):
            continue
        content = cast(dict[str, object], entry.get("content") or {})
        payload = cast(dict[str, object], content.get("payload") or {})
        
        # Extract description from payload
        description = (
            payload.get("candidate_description")
            or payload.get("description")
            or content.get("summary")
            or "Next check execution"
        )
        
        # Extract target cluster - prefer payload target, fall back to entry cluster_label
        target_cluster = (
            payload.get("target_cluster")
            or entry.get("cluster_label")
        )
        
        # Extract command family and preview
        command_family = payload.get("command_family") or payload.get("suggested_command_family")
        command_preview = payload.get("command_preview")
        
        # Extract status - handle outcome_status, timed_out, and generic status
        status = content.get("status")
        timed_out = content.get("timed_out")
        outcome_status = content.get("outcome_status")
        
        # Build execution status string
        execution_status = None
        if outcome_status:
            execution_status = str(outcome_status)
        elif timed_out is True:
            execution_status = "timed-out"
        elif status:
            execution_status = str(status)
        
        # Extract duration
        duration_ms = content.get("duration_ms")
        
        # Extract summary
        summary = content.get("summary")
        
        # Extract usefulness fields if present
        usefulness_class = content.get("usefulness_class")
        usefulness_summary = content.get("usefulness_summary")
        
        # Get artifact path
        artifact_path = entry.get("path")
        
        result.append({
            "description": description,
            "target_cluster": target_cluster,
            "command_family": command_family,
            "command_preview": command_preview,
            "execution_status": execution_status,
            "timed_out": timed_out if timed_out is not None else False,
            "duration_ms": duration_ms,
            "summary": summary,
            "path": artifact_path,
            "usefulness_class": usefulness_class,
            "usefulness_summary": usefulness_summary,
        })
    return result


def _build_next_check_lifecycle_summary(external: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build a compact, reviewer-friendly summary of next-check candidates with lifecycle state.
    
    This function extracts lifecycle information from next-check planning, approval, promotion,
    and execution artifacts to provide a consolidated view of all candidates in the current run.
    
    For each candidate, it includes:
    - candidate_id: unique identifier
    - source_type: 'planner' or 'deterministic'
    - description: human-readable description
    - cluster_label: target cluster
    - source_reason: why this candidate was generated
    - approval_status: current approval state
    - execution_status: current execution state  
    - outcome_status: final outcome
    - timed_out: whether execution timed out
    - result_summary: summary of execution result
    - suggested_next_operator_move: suggested next action
    - artifact pointers: plan_artifact_path, approval_artifact_path, execution_artifact_path
    
    Only includes planner-originated and deterministic-promoted candidates from the current run.
    """
    # Collect artifacts by type for efficient lookup
    planning_entries: list[dict[str, object]] = []
    approval_entries: list[dict[str, object]] = []
    promotion_entries: list[dict[str, object]] = []
    execution_entries: list[dict[str, object]] = []
    
    for entry in external:
        content = cast(dict[str, object], entry.get("content") or {})
        if _is_next_check_planning_entry(entry):
            planning_entries.append(entry)
        elif _is_next_check_approval_entry(entry):
            approval_entries.append(entry)
        elif _is_next_check_promotion_entry(entry):
            promotion_entries.append(entry)
        elif _is_next_check_execution_entry(entry):
            execution_entries.append(entry)
    
    # Build lookup maps for approvals and executions by candidate_id and candidate_index
    approval_by_candidate_id: dict[str, dict[str, object]] = {}
    approval_by_candidate_index: dict[int, dict[str, object]] = {}
    
    for entry in approval_entries:
        content = cast(dict[str, object], entry.get("content") or {})
        payload = cast(dict[str, object], content.get("payload") or {})
        candidate_id = payload.get("candidateId") or content.get("candidate_id")
        candidate_index = payload.get("candidateIndex") or content.get("candidate_index")
        
        if isinstance(candidate_id, str) and candidate_id:
            approval_by_candidate_id[candidate_id] = entry
        if isinstance(candidate_index, int):
            approval_by_candidate_index[candidate_index] = entry
    
    execution_by_candidate_id: dict[str, dict[str, object]] = {}
    execution_by_candidate_index: dict[int, dict[str, object]] = {}
    
    for entry in execution_entries:
        content = cast(dict[str, object], entry.get("content") or {})
        payload = cast(dict[str, object], content.get("payload") or {})
        candidate_id = payload.get("candidateId") or payload.get("candidate_id")
        candidate_index = payload.get("candidateIndex") or payload.get("candidate_index")
        
        if isinstance(candidate_id, str) and candidate_id:
            execution_by_candidate_id[candidate_id] = entry
        if isinstance(candidate_index, int):
            execution_by_candidate_index[candidate_index] = entry
    
    # Process planner-originated candidates
    result: list[dict[str, object]] = []
    
    for entry in planning_entries:
        content = cast(dict[str, object], entry.get("content") or {})
        payload = cast(dict[str, object], content.get("payload") or {})
        candidates = payload.get("candidates") if isinstance(payload, dict) else []
        
        if not isinstance(candidates, list):
            continue
            
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
                
            candidate_id = candidate.get("candidateId")
            candidate_index = candidate.get("candidateIndex")
            
            # Find approval if exists
            approval_entry: dict[str, object] | None = None
            if isinstance(candidate_id, str) and candidate_id in approval_by_candidate_id:
                approval_entry = approval_by_candidate_id[candidate_id]
            elif isinstance(candidate_index, int) and candidate_index in approval_by_candidate_index:
                approval_entry = approval_by_candidate_index[candidate_index]
            
            # Find execution if exists
            execution_entry: dict[str, object] | None = None
            if isinstance(candidate_id, str) and candidate_id in execution_by_candidate_id:
                execution_entry = execution_by_candidate_id[candidate_id]
            elif isinstance(candidate_index, int) and candidate_index in execution_by_candidate_index:
                execution_entry = execution_by_candidate_index[candidate_index]
            
            # Build lifecycle entry
            lifecycle_entry = _build_lifecycle_entry(
                source_type="planner",
                candidate=candidate,
                plan_entry=entry,
                approval_entry=approval_entry,
                execution_entry=execution_entry,
            )
            if lifecycle_entry:
                result.append(lifecycle_entry)
    
    # Process deterministic promoted candidates
    for entry in promotion_entries:
        content = cast(dict[str, object], entry.get("content") or {})
        payload = cast(dict[str, object], content.get("payload") or {})
        
        candidate_id = payload.get("candidateId")
        candidate_index = payload.get("promotionIndex")
        
        # Find approval if exists (approvals can reference promoted candidates)
        approval_entry = None
        if isinstance(candidate_id, str) and candidate_id in approval_by_candidate_id:
            approval_entry = approval_by_candidate_id[candidate_id]
        elif isinstance(candidate_index, int) and candidate_index in approval_by_candidate_index:
            approval_entry = approval_by_candidate_index[candidate_index]
        
        # Find execution if exists
        execution_entry = None
        if isinstance(candidate_id, str) and candidate_id in execution_by_candidate_id:
            execution_entry = execution_by_candidate_id[candidate_id]
        elif isinstance(candidate_index, int) and candidate_index in execution_by_candidate_index:
            execution_entry = execution_by_candidate_index[candidate_index]
        
        # Build lifecycle entry for deterministic candidate
        lifecycle_entry = _build_lifecycle_entry(
            source_type="deterministic",
            candidate=payload,
            plan_entry=entry,
            approval_entry=approval_entry,
            execution_entry=execution_entry,
        )
        if lifecycle_entry:
            result.append(lifecycle_entry)
    
    return result


def _build_lifecycle_entry(
    source_type: str,
    candidate: dict[str, object],
    plan_entry: dict[str, object],
    approval_entry: dict[str, object] | None,
    execution_entry: dict[str, object] | None,
) -> dict[str, object] | None:
    """Build a single lifecycle entry from a candidate and its related artifacts."""
    
    # Extract basic candidate info
    candidate_id = candidate.get("candidateId") or candidate.get("candidate_id")
    description = candidate.get("description") or "Next check"
    cluster_label = candidate.get("targetCluster") or candidate.get("target_cluster")
    source_reason = candidate.get("sourceReason") or candidate.get("source_reason")
    
    # Determine approval status
    approval_status: str | None = None
    approval_artifact_path: str | None = None
    if approval_entry:
        approval_content = cast(dict[str, object], approval_entry.get("content") or {})
        approval_payload = cast(dict[str, object], approval_content.get("payload") or {})
        raw_approval_status = approval_payload.get("status") or approval_content.get("status")
        approval_status = str(raw_approval_status) if raw_approval_status else None
        raw_path = approval_entry.get("path")
        approval_artifact_path = str(raw_path) if raw_path else None
    
    # Determine execution status
    execution_status: str | None = None
    execution_artifact_path: str | None = None
    outcome_status: str | None = None
    timed_out: bool = False
    result_summary: str | None = None
    suggested_next_operator_move: str | None = None
    usefulness_class: str | None = None
    usefulness_summary: str | None = None
    
    if execution_entry:
        exec_content = cast(dict[str, object], execution_entry.get("content") or {})
        exec_payload = cast(dict[str, object], exec_content.get("payload") or {})
        
        raw_exec_status = exec_content.get("status")
        execution_status = str(raw_exec_status) if raw_exec_status else None
        raw_exec_path = execution_entry.get("path")
        execution_artifact_path = str(raw_exec_path) if raw_exec_path else None
        
        # Get outcome status from payload
        raw_outcome = exec_payload.get("outcomeStatus") or exec_content.get("outcome_status")
        outcome_status = str(raw_outcome) if raw_outcome else None
        
        # Check for timeout
        timed_out = bool(exec_content.get("timed_out") or exec_payload.get("timedOut"))
        
        # Get result summary and suggested move
        raw_summary = exec_content.get("summary") or exec_payload.get("resultSummary")
        result_summary = str(raw_summary) if raw_summary else None
        raw_move = exec_payload.get("suggestedNextOperatorMove")
        suggested_next_operator_move = str(raw_move) if raw_move else None
        
        # Get usefulness fields if present
        raw_usefulness_class = exec_content.get("usefulness_class")
        usefulness_class = str(raw_usefulness_class) if raw_usefulness_class else None
        raw_usefulness_summary = exec_content.get("usefulness_summary")
        usefulness_summary = str(raw_usefulness_summary) if raw_usefulness_summary else None
    
    # Get plan artifact path
    plan_artifact_path = plan_entry.get("path")
    
    return {
        "candidate_id": candidate_id,
        "source_type": source_type,
        "description": description,
        "cluster_label": cluster_label,
        "source_reason": source_reason,
        "approval_status": approval_status,
        "execution_status": execution_status,
        "outcome_status": outcome_status,
        "timed_out": timed_out,
        "result_summary": result_summary,
        "suggested_next_operator_move": suggested_next_operator_move,
        "plan_artifact_path": plan_artifact_path,
        "approval_artifact_path": approval_artifact_path,
        "execution_artifact_path": execution_artifact_path,
        "usefulness_class": usefulness_class,
        "usefulness_summary": usefulness_summary,
    }


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
    candidates: list[str] = []
    def add_candidate(text: str | None) -> None:
        if not text:
            return
        text = text.strip()
        if not text or text in candidates:
            return
        candidates.append(text)
    drifts_raw = content.get("top_drifts") or content.get("drift_reasons") or []
    for entry in cast(list[object], drifts_raw):
        if isinstance(entry, str):
            add_candidate(entry)
        elif isinstance(entry, Mapping):
            text = entry.get("reason") or entry.get("summary") or entry.get("label")
            if isinstance(text, str):
                add_candidate(text)
        if len(candidates) >= MAX_TOP_DRIFTS:
            return candidates[:MAX_TOP_DRIFTS]
    for entry in cast(list[dict[str, object]], content.get("trigger_details") or []):
        reason = entry.get("reason")
        classification = entry.get("classification")
        if isinstance(reason, str):
            label = f"{reason} ({classification})" if isinstance(classification, str) else reason
            add_candidate(label)
        if len(candidates) >= MAX_TOP_DRIFTS:
            break
    if not candidates:
        for reason in cast(list[str], content.get("trigger_reasons") or []):
            add_candidate(reason)
            if len(candidates) >= MAX_TOP_DRIFTS:
                break
    return candidates[:MAX_TOP_DRIFTS]


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


def _extract_pattern_keys(value: object | None) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    keys: list[str] = []
    for raw_key in value.keys():
        if isinstance(raw_key, str):
            keys.append(raw_key)
        elif raw_key is not None:
            keys.append(str(raw_key))
        if len(keys) >= MAX_PATTERN_KEYS:
            break
    return keys

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
        content = _load_json_object(path)
        label_value = _extract_content_label(content) or _extract_cluster_label(path, run_id)
        entries.append(
            {
                "cluster_label": label_value,
                "path": path.relative_to(run_health_dir).as_posix(),
                "content": content,
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
    trimmed = stem[len(prefix) :] if stem.startswith(prefix) else stem
    for suffix in ("-assessment", "-drilldown", "-trigger", "-comparison"):
        if trimmed.endswith(suffix):
            trimmed = trimmed[: -len(suffix)]
            break
    return trimmed or None


def _extract_content_label(content: object | None) -> str | None:
    if not isinstance(content, Mapping):
        return None
    for key in ("label", "cluster_label"):
        candidate = content.get(key)
        if isinstance(candidate, str):
            return candidate
    return None


def _normalize_reference_label(value: object | None, label_map: dict[str, str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = normalize_ref(value)
    if not normalized:
        return None
    if normalized in label_map.values():
        return normalized
    if value in label_map:
        return label_map[value]
    # fallback to normalized string even if not previously recorded
    return normalized


def _extract_auto_drilldown_purpose(content: dict[str, object]) -> bool:
    purpose = content.get("purpose")
    if isinstance(purpose, str) and purpose == "auto-drilldown":
        return True
    metadata = content.get("payload")
    if isinstance(metadata, Mapping):
        if metadata.get("purpose") == "auto-drilldown":
            return True
    return False


def _is_auto_drilldown_entry(entry: dict[str, object]) -> bool:
    content = cast(dict[str, object], entry.get("content") or {})
    return _extract_auto_drilldown_purpose(content)


def _extract_comparison_clusters(path: object | None, run_id: str, label_map: dict[str, str]) -> tuple[str | None, str | None]:
    if not isinstance(path, str):
        return None, None
    name = Path(path).stem
    if name.startswith(f"{run_id}-"):
        name = name[len(run_id) + 1 :]
    for suffix in ("-comparison", "-diff"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if "-vs-" not in name:
        return None, None
    primary_part, secondary_part = name.split("-vs-", 1)
    primary = _normalize_reference_label(primary_part, label_map)
    secondary = _normalize_reference_label(secondary_part, label_map)
    return primary, secondary


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


def _write_latest_pack_mirror(
    output_dir: Path,
    review_bundle: dict[str, object],
    review_input: dict[str, object],
    run_id: str,
) -> None:
    """Write stable uncompressed copies of the review files to a 'latest' directory.
    
    This provides operator/reviewer convenience by making the pack outputs available
    as plain JSON files without requiring ZIP extraction.
    
    The files are written to: {output_dir}/latest/
    - review_bundle.json
    - review_input_14b.json
    
    Each pack build overwrites these files to maintain the "latest" invariant.
    """
    latest_dir = output_dir / LATEST_PACK_DIR_NAME
    latest_dir.mkdir(parents=True, exist_ok=True)
    
    # Write review_bundle.json
    bundle_path = latest_dir / "review_bundle.json"
    bundle_path.write_text(json.dumps(review_bundle, indent=2), encoding="utf-8")
    
    # Write review_input_14b.json
    input_path = latest_dir / "review_input_14b.json"
    input_path.write_text(json.dumps(review_input, indent=2), encoding="utf-8")


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

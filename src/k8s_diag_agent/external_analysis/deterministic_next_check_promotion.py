"""Helpers to persist operator promotions of deterministic next checks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import SupportsIndex, TypedDict, cast

from .artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from .next_check_planner import CommandFamily, detect_command_family, detect_expected_signal
from .utils import artifact_matches_run


class DeterministicNextCheckPromotionPayload(TypedDict, total=False):
    description: str
    method: str | None
    evidenceNeeded: list[str]
    workstream: str | None
    urgency: str | None
    whyNow: str | None
    topProblem: str | None
    priorityScore: int | None
    clusterLabel: str
    targetContext: str | None
    runId: str
    candidateId: str
    promotionIndex: int


def build_promoted_candidate_id(description: str, cluster_label: str, run_id: str) -> str:
    normalized = f"{description.strip()}|{cluster_label}|{run_id}".encode()
    return sha256(normalized).hexdigest()


def _coerce_str(value: object | None) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _coerce_optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    if isinstance(value, SupportsIndex):
        return int(value)
    return None


def _normalize_command_hint(payload: Mapping[str, object]) -> str:
    method = str(payload.get("method") or "").strip()
    description = str(payload.get("description") or "").strip()
    return method if method else description


def _priority_label(score: int | None) -> str:
    if score is None:
        return "secondary"
    if score >= 80:
        return "primary"
    if score >= 50:
        return "secondary"
    return "fallback"


def _build_queue_entry(
    payload: DeterministicNextCheckPromotionPayload, artifact_path: str
) -> dict[str, object]:
    command_hint = _normalize_command_hint(payload)
    family = detect_command_family(command_hint)
    expected_signal = detect_expected_signal(command_hint)
    description = str(payload.get("description") or "Deterministic next check").strip()
    cluster_label = payload.get("clusterLabel") or ""
    entry: dict[str, object] = {
        "candidateId": payload.get("candidateId"),
        "candidateIndex": payload.get("promotionIndex"),
        "description": description,
        "targetCluster": cluster_label,
        "targetContext": payload.get("targetContext"),
        "sourceReason": payload.get("whyNow")
        or payload.get("topProblem")
        or "Deterministic next check",
        "expectedSignal": expected_signal,
        "suggestedCommandFamily": family.value if family != CommandFamily.UNKNOWN else None,
        "safeToAutomate": False,
        "requiresOperatorApproval": True,
        "approvalState": "approval-required",
        "executionState": "unexecuted",
        "outcomeStatus": "approval-required",
        "latestArtifactPath": artifact_path,
        "queueStatus": "approval-needed",
        "planArtifactPath": artifact_path,
        "sourceType": "deterministic",
        "priorityLabel": _priority_label(payload.get("priorityScore")),
        "normalizationReason": "deterministic-promoted",
        "safetyReason": "deterministic-promoted",
        "approvalReason": "deterministic-promoted",
        "blockingReason": "awaiting-review",
    }
    # Preserve workstream from promotion payload for drift/parity visibility
    workstream = payload.get("workstream")
    if isinstance(workstream, str) and workstream:
        entry["workstream"] = workstream
    return entry


def write_deterministic_next_check_promotion(
    *,
    runs_dir: Path,
    run_id: str,
    run_label: str,
    cluster_label: str,
    target_context: str | None,
    summary: Mapping[str, object],
) -> tuple[ExternalAnalysisArtifact, DeterministicNextCheckPromotionPayload]:
    promotions = collect_promoted_next_check_payloads(runs_dir, run_id)
    promotion_index = len(promotions)
    description = str(summary.get("description") or "").strip()
    payload: DeterministicNextCheckPromotionPayload = {
        "description": description,
        "method": _coerce_optional_str(summary.get("method")),
        "evidenceNeeded": [str(item) for item in summary.get("evidenceNeeded") or [] if isinstance(item, str)],
        "workstream": _coerce_optional_str(summary.get("workstream")),
        "urgency": _coerce_optional_str(summary.get("urgency")),
        "whyNow": _coerce_optional_str(summary.get("whyNow")),
        "topProblem": _coerce_optional_str(summary.get("topProblem")),
        "priorityScore": _coerce_optional_int(summary.get("priorityScore")),
        "clusterLabel": cluster_label,
        "targetContext": target_context,
        "runId": run_id,
        "candidateId": build_promoted_candidate_id(description, cluster_label, run_id),
        "promotionIndex": promotion_index,
    }
    artifact_dir = runs_dir / "external-analysis"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{run_id}-next-check-promotion-{promotion_index}.json"
    artifact = ExternalAnalysisArtifact(
        tool_name="deterministic-promoter",
        run_id=run_id,
        run_label=run_label,
        cluster_label=cluster_label,
        summary="Operator promoted deterministic next check",
        status=ExternalAnalysisStatus.SUCCESS,
        artifact_path=str(artifact_path.relative_to(runs_dir)),
        provider="platform",
        duration_ms=0,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
        payload=cast(dict[str, object], dict(payload)),
    )
    write_external_analysis_artifact(artifact_path, artifact)
    return artifact, payload


def collect_promoted_next_check_payloads(
    runs_dir: Path,
    run_id: str,
) -> list[tuple[DeterministicNextCheckPromotionPayload, str]]:
    """Collect promotion payloads for a specific run.
    
    This optimized version uses glob pattern to filter promotion files first,
    then checks run_id before loading the full artifact. This significantly
    reduces I/O for cold requests by avoiding scanning unrelated files.
    """
    collected: list[tuple[DeterministicNextCheckPromotionPayload, str]] = []
    directory = runs_dir / "external-analysis"
    if not directory.exists():
        return collected
    
    # OPTIMIZATION: Use glob pattern to filter to only promotion files first
    # This avoids iterating over all files in the directory
    # Pattern matches: *-next-check-promotion-*.json
    promotion_files = list(directory.glob("*-next-check-promotion-*.json"))
    
    for candidate in sorted(promotion_files, key=lambda item: item.name):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # REVIEWED: Non-fatal artifact read fallback in promotion scan.
            # Silently skip unreadable files - not all files are valid promotion artifacts.
            continue
        
        # OPTIMIZATION: Check run_id in raw data before parsing full artifact
        # This avoids the overhead of creating ExternalAnalysisArtifact for non-matching runs
        payload = data.get("payload")
        if not isinstance(payload, Mapping):
            continue
        payload_run_id = payload.get("runId")
        if payload_run_id != run_id:
            continue
            
        try:
            artifact = ExternalAnalysisArtifact.from_dict(data)
        except (ValueError, TypeError, KeyError):
            # REVIEWED: Non-fatal artifact deserialization fallback.
            # Silently skip malformed artifacts - run_id check handles mismatches.
            continue
            
        if artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION:
            continue
            
        # Already verified run_id matches above, double-check for safety
        if not artifact_matches_run(artifact, run_id):
            continue
            
        if not isinstance(payload, Mapping):
            continue
        entry: DeterministicNextCheckPromotionPayload = {
            "description": _coerce_str(payload.get("description")),
            "method": _coerce_optional_str(payload.get("method")),
            "evidenceNeeded": [
                str(item) for item in payload.get("evidenceNeeded") or [] if isinstance(item, str)
            ],
            "workstream": _coerce_optional_str(payload.get("workstream")),
            "urgency": _coerce_optional_str(payload.get("urgency")),
            "whyNow": _coerce_optional_str(payload.get("whyNow")),
            "topProblem": _coerce_optional_str(payload.get("topProblem")),
            "priorityScore": _coerce_optional_int(payload.get("priorityScore")),
            "clusterLabel": _coerce_str(payload.get("clusterLabel")),
            "targetContext": _coerce_optional_str(payload.get("targetContext")),
            "runId": _coerce_str(payload.get("runId")),
            "candidateId": _coerce_str(payload.get("candidateId")),
            "promotionIndex": _coerce_optional_int(payload.get("promotionIndex")) or 0,
        }
        rel_path = artifact.artifact_path or str(candidate.relative_to(runs_dir))
        collected.append((entry, rel_path))
    return collected


def collect_promoted_queue_entries(runs_dir: Path, run_id: str) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    for payload, artifact_rel_path in collect_promoted_next_check_payloads(runs_dir, run_id):
        entry = _build_queue_entry(payload, artifact_rel_path)
        collected.append(entry)
    return collected

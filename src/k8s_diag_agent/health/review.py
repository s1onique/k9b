"""Helper logic for choosing the highest-signal health drilldown."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence, Tuple

from ..llm.assessor_schema import AssessorAssessment
from .drilldown import DrilldownArtifact, DrilldownPod


@dataclass(frozen=True)
class DrilldownCandidate:
    path: Path
    artifact: DrilldownArtifact


@dataclass(frozen=True)
class LatestRunSelection:
    run_id: str
    run_timestamp: datetime
    candidates: Tuple[DrilldownCandidate, ...]


def collect_drilldown_candidates(drilldown_dir: Path) -> Tuple[DrilldownCandidate, ...]:
    if not drilldown_dir.exists():
        return ()
    candidates: list[DrilldownCandidate] = []
    for path in sorted(drilldown_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifact = DrilldownArtifact.from_dict(raw)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        candidates.append(DrilldownCandidate(path=path, artifact=artifact))
    return tuple(candidates)


def select_latest_run(drilldown_dir: Path) -> LatestRunSelection:
    candidates = collect_drilldown_candidates(drilldown_dir)
    if not candidates:
        raise RuntimeError(f"no drilldown artifacts found in {drilldown_dir}")
    latest = max(candidates, key=lambda candidate: candidate.artifact.timestamp)
    run_id = latest.artifact.run_id
    run_candidates = tuple(candidate for candidate in candidates if candidate.artifact.run_id == run_id)
    ranked = rank_drilldown_candidates(run_candidates)
    return LatestRunSelection(run_id=run_id, run_timestamp=latest.artifact.timestamp, candidates=ranked)


def rank_drilldown_candidates(candidates: Iterable[DrilldownCandidate]) -> Tuple[DrilldownCandidate, ...]:
    return tuple(sorted(candidates, key=_ranking_key))


def assessment_path_for_drilldown(drilldown_path: Path, assessments_dir: Path) -> Path:
    stem = drilldown_path.name
    if stem.endswith("-drilldown.json"):
        stem = f"{stem[: -len('-drilldown.json')]}-assessment.json"
    else:
        stem = f"{stem}-assessment.json"
    return assessments_dir / stem


def load_assessment(path: Path) -> AssessorAssessment | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return AssessorAssessment.from_dict(raw)
    except ValueError:
        return None


def _ranking_key(candidate: DrilldownCandidate) -> Tuple[int, float, str]:
    severity = _priority_bucket(candidate.artifact)
    timestamp = candidate.artifact.timestamp.timestamp()
    label = candidate.artifact.label or candidate.path.name
    return (severity, -timestamp, label)


def _priority_bucket(artifact: DrilldownArtifact) -> int:
    if _has_image_pull_backoff(artifact):
        return 0
    if _has_crash_loop_backoff(artifact):
        return 1
    if _has_failed_job(artifact):
        return 2
    if _has_pending_pod(artifact):
        return 3
    return 4


def _has_image_pull_backoff(artifact: DrilldownArtifact) -> bool:
    return _trigger_present(artifact, "imagepullbackoff") or _pod_reason_contains(artifact, "imagepullbackoff")


def _has_crash_loop_backoff(artifact: DrilldownArtifact) -> bool:
    return _trigger_present(artifact, "crashloopbackoff") or _pod_reason_contains(artifact, "crashloopbackoff")


def _has_failed_job(artifact: DrilldownArtifact) -> bool:
    if _trigger_present(artifact, "job_failures"):
        return True
    return any(_matches_phase(pod, "failed") for pod in artifact.non_running_pods)


def _has_pending_pod(artifact: DrilldownArtifact) -> bool:
    return any(_matches_phase(pod, "pending") for pod in artifact.non_running_pods)


def _trigger_present(artifact: DrilldownArtifact, needle: str) -> bool:
    lowered = needle.lower()
    return any(reason.lower() == lowered for reason in artifact.trigger_reasons)


def _pod_reason_contains(artifact: DrilldownArtifact, needle: str) -> bool:
    lowered = needle.lower()
    for pod in artifact.non_running_pods:
        if pod.reason.lower() == lowered:
            return True
    return False


def _matches_phase(pod: DrilldownPod, phase: str) -> bool:
    return pod.phase.lower() == phase.lower()

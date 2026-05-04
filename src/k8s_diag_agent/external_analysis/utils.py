"""Shared helpers for external analysis artifacts."""

from __future__ import annotations

from pathlib import Path

from .artifact import ExternalAnalysisArtifact


def artifact_matches_run(artifact: ExternalAnalysisArtifact, run_id: str) -> bool:
    if artifact.run_id == run_id:
        return True
    artifact_path = artifact.artifact_path
    if not artifact_path:
        return False
    try:
        candidate = Path(str(artifact_path)).name
    except (ValueError, TypeError):
        # REVIEWED: Non-fatal path extraction fallback.
        # Silently skip artifacts with invalid path strings.
        return False
    return candidate.startswith(f"{run_id}-")

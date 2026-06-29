#!/usr/bin/env python3
"""Artifact I/O helpers for K8s multi-pass diagnosis phase.

This module contains functions for reading and writing diagnosis
artifacts. It knows only about paths, JSON, and contract objects,
not about Kubernetes/provider execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.k9b_lab_common_helpers import write_json_artifact
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    ARTIFACT_DIR,
    ARTIFACT_FILENAME,
    PHASE_DIAGNOSIS,
)


def get_diagnosis_dir(artifact_dir: Path) -> Path:
    """Get the diagnosis phase directory.

    Args:
        artifact_dir: Root artifact directory

    Returns:
        Path to diagnosis phase directory
    """
    phase_dir = artifact_dir / PHASE_DIAGNOSIS
    phase_dir.mkdir(parents=True, exist_ok=True)
    return phase_dir / ARTIFACT_DIR


def get_diagnosis_evidence_path(artifact_dir: Path) -> Path:
    """Get the diagnosis evidence artifact path.

    Args:
        artifact_dir: Root artifact directory

    Returns:
        Path to diagnosis evidence JSON file
    """
    diagnosis_dir = get_diagnosis_dir(artifact_dir)
    return diagnosis_dir / ARTIFACT_FILENAME


def write_diagnosis_evidence(diagnosis_dir: Path, evidence: dict[str, Any]) -> Path:
    """Write diagnosis evidence artifact.

    Args:
        diagnosis_dir: Directory to write artifact
        evidence: Evidence dict to write

    Returns:
        Path to the written artifact
    """
    artifact_path = diagnosis_dir / ARTIFACT_FILENAME
    write_json_artifact(diagnosis_dir, ARTIFACT_FILENAME, evidence)
    return artifact_path


def read_diagnosis_evidence(artifact_dir: Path) -> dict[str, Any] | None:
    """Read diagnosis evidence artifact if it exists.

    Args:
        artifact_dir: Root artifact directory

    Returns:
        Evidence dict or None if not found
    """
    import json

    evidence_path = get_diagnosis_evidence_path(artifact_dir)
    if evidence_path.exists():
        result: dict[str, Any] = json.loads(evidence_path.read_text())
        return result
    return None


def get_p3c_evidence_path(artifact_dir: Path) -> Path:
    """Get the P3c detection evidence path.

    Args:
        artifact_dir: Root artifact directory

    Returns:
        Path to P3c detection evidence JSON file
    """
    return artifact_dir / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"

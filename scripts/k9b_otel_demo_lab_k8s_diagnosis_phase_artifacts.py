"""Kubernetes diagnosis phase: artifact helpers.

This module provides path construction and artifact I/O helpers for the diagnosis phase.
Extracted to support LLM-friendly file sizes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def get_diagnosis_dir(artifact_dir: Path) -> Path:
    """Get the diagnosis artifact directory.

    Args:
        artifact_dir: Root artifact directory

    Returns:
        Path to diagnosis directory
    """
    diagnosis_dir = artifact_dir / "phase4-diagnosis"
    diagnosis_dir.mkdir(parents=True, exist_ok=True)
    return diagnosis_dir


def get_p3c_evidence_path(artifact_dir: Path) -> Path:
    """Get the path to P3c detection evidence.

    Args:
        artifact_dir: Root artifact directory

    Returns:
        Path to P3c evidence file
    """
    return artifact_dir / "phase3c-discovery" / "detection-evidence.json"


def write_diagnosis_evidence(diagnosis_dir: Path, evidence: dict[str, Any]) -> None:
    """Write diagnosis evidence to file.

    Args:
        diagnosis_dir: Diagnosis directory
        evidence: Evidence dict to write
    """
    output_path = diagnosis_dir / "diagnosis-evidence.json"
    with open(output_path, "w") as f:
        json.dump(evidence, f, indent=2, default=str)

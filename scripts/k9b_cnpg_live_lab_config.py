#!/usr/bin/env python3
"""Configuration and data structures for CNPG Live Lab bootstrap.

This module contains the core data classes used to store and serialize
preflight checks and diagnosis results.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .k9b_cnpg_live_lab_helpers import write_json_atomically

# =============================================================================
# Preflight data structure
# =============================================================================

class PreflightData:
    """Container for preflight diagnostic data."""

    def __init__(self, artifact_dir: Path, namespace: str = ""):
        self.artifact_dir = artifact_dir
        self.namespace = namespace
        self.timestamp = datetime.now(UTC).isoformat()
        self.failure_class: str | None = None
        self.failure_reason: str | None = None
        self.failure_stage: str | None = None  # "bootstrap" or "helm_deploy"
        self.active_identity: str | None = None
        self.credential_source: str | None = None
        self.current_context: str | None = None
        self.api_reachable: bool | None = None
        self.namespace_exists: bool | None = None
        self.namespace_status: str | None = None
        self.rbac_checks_complete: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "bootstrap_timestamp": self.timestamp,
            "namespace": self.namespace,
            "failure_class": self.failure_class,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "active_identity": self.active_identity,
            "credential_source": self.credential_source,
            "current_context": self.current_context,
            "api_reachable": self.api_reachable,
            "namespace_exists": self.namespace_exists,
            "namespace_status": self.namespace_status,
            "rbac_checks_complete": self.rbac_checks_complete,
        }

    def save(self) -> None:
        """Save preflight data to JSON file."""
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.artifact_dir / "lab-preflight.json"
        write_json_atomically(path, self.to_dict())


# =============================================================================
# Diagnosis markdown generator
# =============================================================================

class DiagnosisGenerator:
    """Generates lab-diagnosis.md markdown file."""

    def __init__(self, artifact_dir: Path, namespace: str = ""):
        self.artifact_dir = artifact_dir
        self.namespace = namespace
        self.lines: list[str] = []

    def heading(self, level: int, text: str) -> None:
        """Add a heading."""
        self.lines.append(f"{'#' * level} {text}\n")

    def text(self, text: str) -> None:
        """Add plain text."""
        self.lines.append(f"{text}\n")

    def code(self, code: str, lang: str = "") -> None:
        """Add code block."""
        self.lines.append(f"```{lang}\n{code}\n```\n")

    def bold(self, text: str) -> str:
        """Wrap text in bold markdown."""
        return f"**{text}**"

    def inline_code(self, text: str) -> str:
        """Wrap text in inline code markdown."""
        return f"`{text}`"

    def bullet(self, text: str) -> None:
        """Add bullet point."""
        self.lines.append(f"- {text}\n")

    def save(self) -> None:
        """Save diagnosis to markdown file."""
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.artifact_dir / "lab-diagnosis.md"
        path.write_text("".join(self.lines))

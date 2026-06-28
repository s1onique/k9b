#!/usr/bin/env python3
"""Common helper functions for k9b live labs.

This module contains reusable utility functions for:
- Logging (log, warn, error)
- JSON file operations (write_json_atomically, read_json)
- Environment secret handling
- kubectl command execution helpers
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# =============================================================================
# Logging functions
# =============================================================================

def log(msg: str) -> None:
    """Log info message."""
    print(f"[lab-common] {msg}", flush=True)


def warn(msg: str) -> None:
    """Log warning message."""
    print(f"[lab-common] WARNING: {msg}", file=sys.stderr, flush=True)


def error(msg: str) -> None:
    """Log error message."""
    print(f"[lab-common] ERROR: {msg}", file=sys.stderr, flush=True)


# =============================================================================
# JSON file operations
# =============================================================================

def write_json_atomically(path: Path, data: dict) -> None:
    """Write JSON file atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(path)


def read_json(path: Path) -> dict:
    """Read JSON file, returning empty dict if not found."""
    if path.exists():
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    return {}


def write_text_artifact(artifact_dir: Path, filename: str, content: str) -> Path:
    """Write a text artifact file atomically.
    
    Args:
        artifact_dir: Directory to write artifact
        filename: Name of the artifact file
        content: Content to write
        
    Returns:
        Path to the written artifact file
    """
    path = artifact_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def write_json_artifact(artifact_dir: Path, filename: str, data: dict) -> Path:
    """Write a JSON artifact file atomically.
    
    Args:
        artifact_dir: Directory to write artifact
        filename: Name of the artifact file
        data: Dictionary data to serialize as JSON
        
    Returns:
        Path to the written artifact file
    """
    path = artifact_dir / filename
    write_json_atomically(path, data)
    return path


# =============================================================================
# Environment secret handling
# =============================================================================

def get_env_secret(secret_name: str) -> str | None:
    """Get environment secret value, returning None if not set."""
    # Handle GitHub Actions secrets format
    value = os.environ.get(secret_name)
    if value is None:
        # Try lowercase
        value = os.environ.get(secret_name.lower())
    return value


# =============================================================================
# Kubectl result dataclass
# =============================================================================

@dataclass
class KubectlResult:
    """Structured result from kubectl command.
    
    Supports both old field names (json_data, text_data, error_message) and
    new field names (stdout, stderr, returncode, data) for backward compatibility.
    """

    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    success: bool = False
    data: dict[str, Any] | None = None
    parsed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Backward-compatible aliases for old field names
    json_data: str = ""  # Alias for stdout (JSON format)
    text_data: str = ""  # Alias for stdout (text format)
    error_message: str = ""  # Alias for stderr

    def __post_init__(self) -> None:
        """Initialize backward-compatible aliases if not provided."""
        if not self.stdout and self.json_data:
            self.stdout = self.json_data
            self.data = None
            try:
                self.data = json.loads(self.json_data)
            except (json.JSONDecodeError, TypeError):
                pass
        if not self.stdout and self.text_data:
            self.stdout = self.text_data
        if not self.stderr and self.error_message:
            self.stderr = self.error_message
        if not self.json_data and self.stdout:
            try:
                json.loads(self.stdout)
                self.json_data = self.stdout
            except (json.JSONDecodeError, TypeError):
                self.json_data = "{}"
        if not self.text_data:
            self.text_data = self.stdout
        if not self.error_message:
            self.error_message = self.stderr

    @classmethod
    def from_subprocess(
        cls,
        result: subprocess.CompletedProcess[str],
        parse_json: bool = False,
    ) -> KubectlResult:
        """Create KubectlResult from subprocess result."""
        data = None
        json_data = ""
        if parse_json and result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                json_data = result.stdout
            except json.JSONDecodeError:
                pass

        return cls(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            success=result.returncode == 0,
            data=data,
            json_data=json_data,
            text_data=result.stdout,
            error_message=result.stderr,
        )


# =============================================================================
# kubectl execution wrappers
# =============================================================================

def kubectl_json(
    kubeconfig: str,
    resource: str,
    namespace: str | None = None,
    extra_args: list[str] | None = None,
) -> KubectlResult:
    """Execute kubectl get with JSON output."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", resource, "-o", "json"]
    if namespace:
        cmd.extend(["-n", namespace])
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result, parse_json=True)


def kubectl_text(
    kubeconfig: str,
    resource: str,
    namespace: str | None = None,
    extra_args: list[str] | None = None,
) -> KubectlResult:
    """Execute kubectl get with default text output."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", resource]
    if namespace:
        cmd.extend(["-n", namespace])
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)


def kubectl_events(
    kubeconfig: str,
    namespace: str,
    sort_by: str = ".lastTimestamp",
    extra_args: list[str] | None = None,
) -> KubectlResult:
    """Get events with sorting."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", "events", "-n", namespace]
    if sort_by:
        cmd.extend(["--sort-by=" + sort_by])
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)


def kubectl_logs(
    kubeconfig: str,
    pod: str,
    namespace: str,
    container: str | None = None,
    previous: bool = False,
    tail: int | None = None,
) -> KubectlResult:
    """Get pod logs."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "logs", pod, "-n", namespace]
    if container:
        cmd.extend(["-c", container])
    if previous:
        cmd.append("--previous")
    if tail:
        cmd.extend(["--tail", str(tail)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)


def kubectl_describe(
    kubeconfig: str,
    resource_type: str,
    name: str,
    namespace: str | None = None,
) -> KubectlResult:
    """Get kubectl describe output."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "describe", resource_type, name]
    if namespace:
        cmd.extend(["-n", namespace])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)


def kubectl_apply(
    kubeconfig: str,
    manifest: str,
    namespace: str | None = None,
    dry_run: str | None = None,
) -> KubectlResult:
    """Apply a manifest."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"]
    if namespace:
        cmd.extend(["--namespace", namespace])
    if dry_run:
        cmd.extend(["--dry-run=" + dry_run])

    result = subprocess.run(cmd, input=manifest, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)


# =============================================================================
# Re-exports for backward compatibility
# =============================================================================

__all__ = [
    "log",
    "warn",
    "error",
    "write_json_atomically",
    "read_json",
    "write_text_artifact",
    "write_json_artifact",
    "get_env_secret",
    "KubectlResult",
    "kubectl_json",
    "kubectl_text",
    "kubectl_events",
    "kubectl_logs",
    "kubectl_describe",
    "kubectl_apply",
]

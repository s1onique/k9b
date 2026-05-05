"""Typed artifact readers for external analysis artifacts.

This module provides a typed boundary for reading ExternalAnalysisArtifact files
from disk, replacing scattered ad-hoc json.loads() + from_dict() patterns.

Pilot scope: ExternalAnalysisArtifact family only.
Do not extend without validation against this pattern.

Error handling model:
- Strict reader (read_external_analysis_artifact) raises specific exceptions:
  - OSError, json.JSONDecodeError, ValueError, TypeError, KeyError
- Optional reader (try_read_external_analysis_artifact) returns None on failure
  and logs safe metadata only.

Logging policy:
- Only safe metadata is logged: filename, artifact kind, run_id (if safe), error type
- Never log raw artifact payloads, prompts, responses, kubeconfig, tokens, or secrets
- Avoid full absolute paths - use basename or safe relative path
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path

from .artifact import ExternalAnalysisArtifact

logger = logging.getLogger(__name__)


class ExternalAnalysisArtifactReadError(Exception):
    """Base exception for artifact read failures.

    Carries safe metadata for logging without exposing sensitive content.
    """

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.path = path
        self.cause = cause
        safe_path = path.name if path else None
        super().__init__(f"{message} (path={safe_path})")


def read_external_analysis_artifact(path: Path) -> ExternalAnalysisArtifact:
    """Read and parse an ExternalAnalysisArtifact from disk.

    This is a strict reader that raises on any parse failure.
    Use try_read_external_analysis_artifact() if you need graceful fallback.

    Args:
        path: Path to the artifact JSON file

    Returns:
        Parsed ExternalAnalysisArtifact

    Raises:
        OSError: If the file cannot be read
        json.JSONDecodeError: If the file content is not valid JSON
        ValueError: If the JSON is valid but not a mapping, or from_dict validation fails
        TypeError: If from_dict receives unexpected type
        KeyError: If required fields are missing in from_dict
    """
    raw: Mapping[str, object] = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"Artifact is not a mapping: {path.name}")
    return ExternalAnalysisArtifact.from_dict(raw)


def try_read_external_analysis_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "external-analysis",
    log_failures: bool = True,
) -> ExternalAnalysisArtifact | None:
    """Try to read an ExternalAnalysisArtifact, returning None on failure.

    This optional reader preserves existing fallback behavior where malformed
    artifacts are skipped rather than causing errors.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.

    Args:
        path: Path to the artifact JSON file
        run_id: Run ID for safe logging context
        artifact_kind: Descriptive kind for log messages (e.g., "next-check-execution")
        log_failures: If True (default), log warning on parse failure.
                     If False, return None silently (for broad scan paths).

    Returns:
        Parsed ExternalAnalysisArtifact, or None if parsing fails
    """
    try:
        return read_external_analysis_artifact(path)
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        if log_failures:
            # Log safe metadata only - never log content
            logger.warning(
                "Skipped malformed %s artifact: %s",
                artifact_kind,
                path.name,
                extra={
                    "run_id": run_id,
                    "artifact_kind": artifact_kind,
                    "scan_name": "try_read_external_analysis_artifact",
                    "error": type(exc).__name__,
                },
            )
        return None

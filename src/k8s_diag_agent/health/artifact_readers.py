"""Typed artifact readers for health artifacts.

This module provides a typed boundary for reading ClusterSnapshot, HealthProposal,
DrilldownArtifact, NotificationArtifact, and HealthAssessmentArtifact files from disk,
replacing scattered ad-hoc json.loads() + from_dict() patterns.

Supported artifact families: ClusterSnapshot, HealthProposal, DrilldownArtifact,
NotificationArtifact, HealthAssessmentArtifact. Do not extend without validation against this pattern.

Error handling model:
- Strict readers (read_*_artifact) raise specific exceptions:
  - OSError, json.JSONDecodeError, ValueError, TypeError, KeyError
- Optional readers (try_read_*_artifact) return None on failure
  and log safe metadata only.

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

from ..collect.cluster_snapshot import ClusterSnapshot
from .adaptation import HealthProposal
from .drilldown import DrilldownArtifact
from .loop import HealthAssessmentArtifact
from .notifications import NotificationArtifact

logger = logging.getLogger(__name__)


class DrilldownArtifactReadError(Exception):
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


class HealthAssessmentArtifactReadError(Exception):
    """Base exception for HealthAssessmentArtifact read failures.

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


def read_drilldown_artifact(path: Path) -> DrilldownArtifact:
    """Read and parse a DrilldownArtifact from disk.

    This is a strict reader that raises on any parse failure.
    Use try_read_drilldown_artifact() if you need graceful fallback.

    Args:
        path: Path to the artifact JSON file

    Returns:
        Parsed DrilldownArtifact

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
    return DrilldownArtifact.from_dict(raw)


def try_read_drilldown_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "drilldown",
    log_failures: bool = True,
) -> DrilldownArtifact | None:
    """Try to read a DrilldownArtifact, returning None on failure.

    This optional reader preserves existing fallback behavior where malformed
    artifacts are skipped rather than causing errors.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.

    Args:
        path: Path to the artifact JSON file
        run_id: Run ID for safe logging context
        artifact_kind: Descriptive kind for log messages (e.g., "drilldown")
        log_failures: If True (default), log warning on parse failure.
                     If False, return None silently (for broad scan paths).

    Returns:
        Parsed DrilldownArtifact, or None if parsing fails
    """
    try:
        return read_drilldown_artifact(path)
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
                    "scan_name": "try_read_drilldown_artifact",
                    "error": type(exc).__name__,
                },
            )
        return None


class HealthProposalArtifactReadError(Exception):
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


def read_health_proposal_artifact(path: Path) -> HealthProposal:
    """Read and parse a HealthProposal from disk.

    This is a strict reader that raises on any parse failure.
    Use try_read_health_proposal_artifact() if you need graceful fallback.

    Args:
        path: Path to the artifact JSON file

    Returns:
        Parsed HealthProposal

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
    return HealthProposal.from_dict(raw)


def try_read_health_proposal_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "health-proposal",
    log_failures: bool = True,
) -> HealthProposal | None:
    """Try to read a HealthProposal, returning None on failure.

    This optional reader preserves existing fallback behavior where malformed
    artifacts are skipped rather than causing errors.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.

    Args:
        path: Path to the artifact JSON file
        run_id: Run ID for safe logging context
        artifact_kind: Descriptive kind for log messages (e.g., "health-proposal")
        log_failures: If True (default), log warning on parse failure.
                     If False, return None silently (for broad scan paths).

    Returns:
        Parsed HealthProposal, or None if parsing fails
    """
    try:
        return read_health_proposal_artifact(path)
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
                    "scan_name": "try_read_health_proposal_artifact",
                    "error": type(exc).__name__,
                },
            )
        return None


class ClusterSnapshotArtifactReadError(Exception):
    """Base exception for ClusterSnapshot artifact read failures.

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


def read_cluster_snapshot_artifact(path: Path) -> ClusterSnapshot:
    """Read and parse a ClusterSnapshot from disk.

    This is a strict reader that raises on any parse failure.
    Use try_read_cluster_snapshot_artifact() if you need graceful fallback.

    Args:
        path: Path to the ClusterSnapshot JSON file

    Returns:
        Parsed ClusterSnapshot

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
    return ClusterSnapshot.from_dict(raw)


def try_read_cluster_snapshot_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "cluster-snapshot",
    log_failures: bool = True,
) -> ClusterSnapshot | None:
    """Try to read a ClusterSnapshot, returning None on failure.

    This optional reader preserves existing fallback behavior where malformed
    snapshots are skipped rather than causing errors.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.

    Args:
        path: Path to the ClusterSnapshot JSON file
        run_id: Run ID for safe logging context
        artifact_kind: Descriptive kind for log messages (e.g., "cluster-snapshot")
        log_failures: If True (default), log warning on parse failure.
                     If False, return None silently (for broad scan paths).

    Returns:
        Parsed ClusterSnapshot, or None if parsing fails
    """
    try:
        return read_cluster_snapshot_artifact(path)
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
                    "scan_name": "try_read_cluster_snapshot_artifact",
                    "error": type(exc).__name__,
                },
            )
        return None


class NotificationArtifactReadError(Exception):
    """Base exception for NotificationArtifact read failures.

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


def read_notification_artifact(path: Path) -> NotificationArtifact:
    """Read and parse a NotificationArtifact from disk.

    This is a strict reader that raises on any parse failure.
    Use try_read_notification_artifact() if you need graceful fallback.

    Args:
        path: Path to the notification artifact JSON file

    Returns:
        Parsed NotificationArtifact

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
    return NotificationArtifact.from_dict(raw)


def try_read_notification_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "notification",
    log_failures: bool = True,
) -> NotificationArtifact | None:
    """Try to read a NotificationArtifact, returning None on failure.

    This optional reader preserves existing fallback behavior where malformed
    notifications are skipped rather than causing errors.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.

    Args:
        path: Path to the notification artifact JSON file
        run_id: Run ID for safe logging context
        artifact_kind: Descriptive kind for log messages (e.g., "notification")
        log_failures: If True (default), log warning on parse failure.
                     If False, return None silently (for broad scan paths).

    Returns:
        Parsed NotificationArtifact, or None if parsing fails
    """
    try:
        return read_notification_artifact(path)
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
                    "scan_name": "try_read_notification_artifact",
                    "error": type(exc).__name__,
                },
            )
        return None


def read_health_assessment_artifact(path: Path) -> HealthAssessmentArtifact:
    """Read and parse a HealthAssessmentArtifact from disk.

    This is a strict reader that raises on any parse failure.
    Use try_read_health_assessment_artifact() if you need graceful fallback.

    Args:
        path: Path to the health assessment artifact JSON file

    Returns:
        Parsed HealthAssessmentArtifact

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
    return HealthAssessmentArtifact.from_dict(raw)


def try_read_health_assessment_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "health-assessment",
    log_failures: bool = True,
) -> HealthAssessmentArtifact | None:
    """Try to read a HealthAssessmentArtifact, returning None on failure.

    This optional reader preserves existing fallback behavior where malformed
    artifacts are skipped rather than causing errors.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.

    Args:
        path: Path to the health assessment artifact JSON file
        run_id: Run ID for safe logging context
        artifact_kind: Descriptive kind for log messages (e.g., "health-assessment")
        log_failures: If True (default), log warning on parse failure.
                     If False, return None silently (for broad scan paths).

    Returns:
        Parsed HealthAssessmentArtifact, or None if parsing fails
    """
    try:
        return read_health_assessment_artifact(path)
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
                    "scan_name": "try_read_health_assessment_artifact",
                    "error": type(exc).__name__,
                },
            )
        return None

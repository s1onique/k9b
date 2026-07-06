"""Alert signal artifact reader for incident promotion.

This module reads persisted alert signal artifacts from:
    runs_dir/external-analysis/alert-signals/

The reader:
- Reads alert-signal-*.json artifacts
- Ignores alertmanager-raw-*.json artifacts
- Requires schema_version == "k9b.alert_signal.v1"
- Deserializes AlertSignal and correlation_hints
- Skips malformed artifacts safely
- Returns bounded deterministic results

Suggested by: ACT-K9B-ALERT-INCIDENT-PROMOTION01
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .incident_alert_signal_store import (
    ALERT_SIGNAL_SCHEMA_VERSION,
    ALERT_SIGNALS_SUBDIR,
    EXTERNAL_ANALYSIS_SUBDIR,
    AlertSignalArtifact,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertSignalScanDiagnostics:
    """Diagnostics from scanning alert signal artifacts."""
    total_files_found: int = 0
    malformed_files_skipped: int = 0
    schema_version_skipped: int = 0
    valid_artifacts_returned: int = 0


# Maximum number of artifacts to process in a single scan
MAX_ARTIFACTS_PER_SCAN = 1000


def get_alert_signals_dir(runs_dir: Path) -> Path:
    """Get the alert signals directory path.

    Args:
        runs_dir: The runs directory root

    Returns:
        Path to the alert signals directory
    """
    return runs_dir / EXTERNAL_ANALYSIS_SUBDIR / ALERT_SIGNALS_SUBDIR


def scan_alert_signal_artifacts(
    runs_dir: Path,
    max_count: int = MAX_ARTIFACTS_PER_SCAN,
) -> tuple[AlertSignalArtifact, ...]:
    """Scan alert signal artifacts from the runs directory.

    Reads alert-signal-*.json artifacts only, ignoring alertmanager-raw-*.json
    and any malformed artifacts.

    Args:
        runs_dir: The runs directory root
        max_count: Maximum number of artifacts to return (default 1000)

    Returns:
        Tuple of AlertSignalArtifact objects, sorted by identity
    """
    signals_dir = get_alert_signals_dir(runs_dir)

    if not signals_dir.exists():
        return ()

    artifacts: list[AlertSignalArtifact] = []
    malformed_count = 0

    # Read only alert-signal-*.json files
    for artifact_path in sorted(signals_dir.glob("alert-signal-*.json")):
        if len(artifacts) >= max_count:
            break

        try:
            result = _read_single_artifact(artifact_path)
            if result is None:
                # Check why it was None - schema version or malformed?
                # For now, count as malformed if read failed
                malformed_count += 1
            else:
                artifacts.append(result)
        except Exception as e:
            malformed_count += 1
            logger.debug(
                "Skipping malformed artifact %s: %s",
                artifact_path.name,
                e,
            )

    if malformed_count > 0:
        logger.info(
            "Scanned %d alert signal artifacts, skipped %d malformed",
            len(artifacts),
            malformed_count,
        )

    # Sort by identity for deterministic output
    return tuple(sorted(artifacts, key=lambda a: a.identity))


def _read_single_artifact(artifact_path: Path) -> AlertSignalArtifact | None:
    """Read a single alert signal artifact.

    Args:
        artifact_path: Path to the artifact file

    Returns:
        AlertSignalArtifact if valid, None if skipped
    """
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Failed to read artifact %s: %s", artifact_path.name, e)
        return None

    # Check schema version
    schema_version = data.get("schema_version", "")
    if schema_version != ALERT_SIGNAL_SCHEMA_VERSION:
        logger.debug(
            "Skipping artifact with unexpected schema version %s (expected %s)",
            schema_version,
            ALERT_SIGNAL_SCHEMA_VERSION,
        )
        return None

    try:
        return AlertSignalArtifact.from_dict(data)
    except Exception as e:
        logger.debug("Failed to deserialize artifact %s: %s", artifact_path.name, e)
        return None


def read_alert_signal_by_identity(
    runs_dir: Path,
    identity: str,
) -> AlertSignalArtifact | None:
    """Read a specific alert signal artifact by identity.

    Args:
        runs_dir: The runs directory root
        identity: The alert signal identity

    Returns:
        AlertSignalArtifact if found, None otherwise
    """
    signals_dir = get_alert_signals_dir(runs_dir)
    artifact_path = signals_dir / f"alert-signal-{identity}.json"

    if not artifact_path.exists():
        return None

    return _read_single_artifact(artifact_path)


__all__ = [
    "get_alert_signals_dir",
    "scan_alert_signal_artifacts",
    "read_alert_signal_by_identity",
]

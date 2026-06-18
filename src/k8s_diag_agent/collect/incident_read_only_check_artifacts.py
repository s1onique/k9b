"""Pure helper module for persisting and loading read-only check result artifacts.

This module provides read/write logic for persisting fake runner results
as bounded JSON artifacts and loading them for incident case-file packets.

Design constraints:
- Bounded file IO only in explicit load/write functions
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic ordering
- Failure-tolerant loading (missing/malformed artifacts produce empty results)
- Explicit safety metadata

Artifact naming convention:
- {run_id}-read-only-check-results.json

SAFE extraction rules:
- Only artifacts linked by matching run_id from incident signals
- Only artifacts where schema version is present
- Only artifacts where incident_id matches current incident (if present)
- Unsafe run_ids are skipped without path construction

Path safety:
- run_id values are validated against strict character constraints
- Unsafe run_ids are skipped without path construction
- Only exact expected filenames are read (no glob/recursive patterns)
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_lifecycle import Incident

__all__ = [
    "write_read_only_check_result_artifact",
    "load_read_only_check_result_artifacts_for_incident",
    "is_safe_run_id",
    "ARTIFACT_SCHEMA_VERSION",
    "DEFAULT_MAX_READ_ONLY_CHECK_ARTIFACTS",
    "DEFAULT_MAX_CHECK_RESULTS_PER_ARTIFACT",
    "DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS",
    "DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS",
]


# =============================================================================
# Constants and Patterns
# =============================================================================

# Artifact schema version
ARTIFACT_SCHEMA_VERSION = "1.0"

# Artifact filename pattern
ARTIFACT_FILENAME_PATTERN = "{run_id}-read-only-check-results.json"

# Maximum bounds for safety
DEFAULT_MAX_READ_ONLY_CHECK_ARTIFACTS = 10
DEFAULT_MAX_CHECK_RESULTS_PER_ARTIFACT = 20
DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS = 500
DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS = 2000

# Strict regex for allowed run_id characters: A-Z a-z 0-9 _ . -
# Excludes: / \ .. and other special characters
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# Fields that must NOT appear in loaded check results (action-control fields)
_FORBIDDEN_ACTION_FIELDS: frozenset[str] = frozenset({
    "run",
    "execute",
    "promote",
    "apply",
    "remediate",
    "action",
    "approve",
    "reject",
    "run_command",
    "execute_command",
    "mutate",
    "delete",
    "scale",
    "restart",
    "rollout",
})


# =============================================================================
# Safety Helpers
# =============================================================================


def is_safe_run_id(run_id: str | None) -> bool:
    """Validate that a run_id is safe for path construction.

    run_id values come from incident signals and are used to construct
    artifact paths. This function enforces strict character constraints
    to prevent path traversal attacks.

    Rules:
    - Must be non-empty
    - Must match pattern: A-Z a-z 0-9 _ . -
    - Must not contain / or \\ (path separators)
    - Must not contain .. (path traversal)
    - Must not be an absolute path

    Args:
        run_id: The run_id to validate (may be None)

    Returns:
        True if run_id is safe, False otherwise
    """
    if not run_id:
        return False
    if _SAFE_RUN_ID_RE.fullmatch(run_id) is None:
        return False
    if ".." in run_id:
        return False
    # Check for path separators (defensive)
    if "/" in run_id or "\\" in run_id:
        return False
    return True


# =============================================================================
# Artifact Path Construction
# =============================================================================


def _artifact_path_for_run(
    external_analysis_dir: Path,
    run_id: str,
) -> Path | None:
    """Construct the expected path for a read-only check result artifact.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The run ID to construct path for

    Returns:
        Path to the expected artifact, or None if run_id is unsafe.
    """
    if not is_safe_run_id(run_id):
        return None

    filename = ARTIFACT_FILENAME_PATTERN.format(run_id=run_id)
    return external_analysis_dir / filename


# =============================================================================
# Safe Field Extraction
# =============================================================================


def _strip_action_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Remove action-control fields from a dict.

    This ensures check result entries do not contain fields that could
    be misinterpreted as executable actions.

    Args:
        data: Input dict that may contain action fields

    Returns:
        Filtered dict without action-control fields
    """
    return {k: v for k, v in data.items() if k not in _FORBIDDEN_ACTION_FIELDS}


def _truncate_string(value: str | None, max_chars: int) -> str | None:
    """Truncate a string to maximum length.

    Args:
        value: String to truncate
        max_chars: Maximum allowed characters

    Returns:
        Truncated string with marker, or None if input was None
    """
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + " [...]"


def _truncate_evidence(evidence: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Truncate evidence dict fields to stay within bounds.

    Args:
        evidence: Evidence dict to truncate
        max_chars: Maximum characters for string fields

    Returns:
        Truncated evidence dict
    """
    result: dict[str, Any] = {}

    for key, value in evidence.items():
        if isinstance(value, str):
            result[key] = _truncate_string(value, max_chars)
        elif isinstance(value, list):
            # Truncate list items that are strings
            truncated_items = []
            for item in value:
                if isinstance(item, str):
                    truncated_items.append(_truncate_string(item, max_chars))
                else:
                    truncated_items.append(item)
            # Also truncate total list representation
            result[key] = truncated_items
        elif isinstance(value, dict):
            result[key] = _truncate_evidence(value, max_chars)
        else:
            result[key] = value

    return result


# =============================================================================
# Write-Side Bounding
# =============================================================================


def _bound_runner_result_for_write(runner_result: Mapping[str, object]) -> dict[str, object]:
    """Bound a runner_result dict for safe write to artifact.

    This ensures the persisted artifact is bounded even before reading:
    - Caps results count
    - Caps skipped_checks count
    - Caps rejected_checks count
    - Truncates summary strings
    - Truncates evidence strings
    - Strips action-control fields

    Args:
        runner_result: Raw runner result from check execution

    Returns:
        Bounded runner_result dict safe for persistence
    """
    result: dict[str, object] = {}

    # Copy and bound top-level counts
    result["checks_requested"] = runner_result.get("checks_requested", 0)
    result["checks_run"] = runner_result.get("checks_run", 0)
    result["checks_skipped"] = runner_result.get("checks_skipped", 0)
    result["checks_rejected"] = runner_result.get("checks_rejected", 0)

    # Bound and sanitize results
    results: list[dict[str, object]] = []
    raw_results = runner_result.get("results", [])
    if isinstance(raw_results, list):
        for item in raw_results[:DEFAULT_MAX_CHECK_RESULTS_PER_ARTIFACT]:
            if not isinstance(item, dict):
                continue
            safe_item = _strip_action_fields(dict(item))
            # Truncate summary
            summary = safe_item.get("summary", "")
            if isinstance(summary, str):
                safe_item["summary"] = _truncate_string(summary, DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS)
            # Truncate evidence
            evidence = safe_item.get("evidence", {})
            if isinstance(evidence, dict):
                safe_item["evidence"] = _truncate_evidence(evidence, DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS)
            results.append(safe_item)
    result["results"] = results

    # Bound and sanitize skipped_checks
    skipped: list[dict[str, object]] = []
    raw_skipped = runner_result.get("skipped_checks", [])
    if isinstance(raw_skipped, list):
        for item in raw_skipped[:10]:  # Cap at 10
            if isinstance(item, dict):
                skipped.append(_strip_action_fields(dict(item)))
    result["skipped_checks"] = skipped

    # Bound and sanitize rejected_checks
    rejected: list[dict[str, object]] = []
    raw_rejected = runner_result.get("rejected_checks", [])
    if isinstance(raw_rejected, list):
        for item in raw_rejected[:10]:  # Cap at 10
            if isinstance(item, dict):
                rejected.append(_strip_action_fields(dict(item)))
    result["rejected_checks"] = rejected

    return result


# =============================================================================
# Artifact Writing
# =============================================================================


def write_read_only_check_result_artifact(
    *,
    external_analysis_dir: Path,
    run_id: str,
    incident_id: str,
    runner_result: Mapping[str, object],
    now: datetime | None = None,
) -> dict[str, object]:
    """Write a read-only check result artifact to disk.

    This function persists fake runner output as a bounded JSON artifact.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: Unique identifier for this run (must be safe)
        incident_id: The incident ID this artifact belongs to
        runner_result: The runner result from run_read_only_checks()
        now: Optional datetime for deterministic timestamps

    Returns:
        Dict with artifact metadata including path and status

    Raises:
        ValueError: If run_id is unsafe

    Safety:
        - Validates run_id against strict character constraints
        - Does not write outside external_analysis_dir
        - Does not create parent directories outside artifact root
        - Does not follow symlinks outside artifact directory
    """
    # Safety check: reject unsafe run_ids
    if not is_safe_run_id(run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")

    # Resolve timestamp
    resolved_now = now if now is not None else datetime.now(UTC)

    # Construct artifact path
    artifact_path = _artifact_path_for_run(external_analysis_dir, run_id)
    if artifact_path is None:
        raise ValueError(f"Could not construct artifact path for run_id: {run_id!r}")

    # Ensure parent directory exists
    external_analysis_dir.mkdir(parents=True, exist_ok=True)

    # Build artifact envelope
    artifact: dict[str, object] = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "read-only-check-results",
        "run_id": run_id,
        "incident_id": incident_id,
        "generated_at": resolved_now.isoformat(),
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": [
            "execute",
            "promote",
            "apply",
            "remediate",
            "delete",
            "mutate_cluster",
            "mutate",
            "scale",
            "restart",
            "rollout",
        ],
        "source": "fake-read-only-check-runner",
        "bounded": True,
        "runner_result": _bound_runner_result_for_write(runner_result),
        "safety_metadata": {
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": [
                "execute",
                "promote",
                "apply",
                "remediate",
                "delete",
                "mutate_cluster",
            ],
            "no_kubernetes_client": True,
            "no_shell": True,
            "no_subprocess": True,
            "no_kubectl": True,
            "no_mutation": True,
            "fake_runner": True,
            "bounded": True,
        },
    }

    # Write artifact as deterministic JSON
    artifact_json = json.dumps(artifact, default=str, indent=2)
    artifact_path.write_text(artifact_json, encoding="utf-8")

    return {
        "artifact_path": str(artifact_path),
        "run_id": run_id,
        "incident_id": incident_id,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "written": True,
    }


# =============================================================================
# Artifact Loading
# =============================================================================


def _load_artifact_payload(path: Path) -> dict[str, Any] | None:
    """Load and validate an artifact payload.

    Args:
        path: Path to the artifact file

    Returns:
        Validated artifact dict if file exists and is valid JSON dict,
        None otherwise (file missing, malformed JSON, or non-dict root)
    """
    try:
        if not path.exists():
            return None

        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        # Must be a dict/mapping
        if not isinstance(raw, dict):
            return None

        return raw
    except (json.JSONDecodeError, OSError):
        return None


def _extract_bounded_check_result_entry(
    run_id: str,
    payload: Mapping[str, object],
    current_incident_id: str,
    max_summary_chars: int,
    max_evidence_chars: int,
) -> dict[str, object] | None:
    """Extract a bounded check result entry from an artifact payload.

    Args:
        run_id: Run ID from the filename
        payload: Loaded artifact payload
        current_incident_id: Incident ID to validate linkage
        max_summary_chars: Maximum characters for summary field
        max_evidence_chars: Maximum characters for evidence fields

    Returns:
        Bounded check result entry dict, or None if linkage is invalid
    """
    # Validate schema version exists (required for trusted linkage)
    schema_version = payload.get("schema_version")
    if schema_version is None:
        return None

    # Check incident_id linkage if present in artifact
    artifact_incident_id = payload.get("incident_id")
    if artifact_incident_id is not None and artifact_incident_id != current_incident_id:
        # Wrong incident - do not include
        return None

    # Extract runner result
    runner_result = payload.get("runner_result", {})
    if not isinstance(runner_result, dict):
        runner_result = {}

    # Extract bounded metadata
    generated_at = payload.get("generated_at") or ""

    # Extract check counts
    checks_requested = runner_result.get("checks_requested", 0)
    checks_run = runner_result.get("checks_run", 0)
    checks_skipped = runner_result.get("checks_skipped", 0)
    checks_rejected = runner_result.get("checks_rejected", 0)

    # Extract and bound results
    results: list[dict[str, Any]] = []
    raw_results = runner_result.get("results", [])
    if isinstance(raw_results, list):
        for result in raw_results[:DEFAULT_MAX_CHECK_RESULTS_PER_ARTIFACT]:
            if not isinstance(result, dict):
                continue

            # Strip action fields
            safe_result = _strip_action_fields(dict(result))

            # Truncate summary
            summary = safe_result.get("summary", "")
            if isinstance(summary, str):
                safe_result["summary"] = _truncate_string(summary, max_summary_chars)

            # Truncate evidence
            evidence = safe_result.get("evidence", {})
            if isinstance(evidence, dict):
                safe_result["evidence"] = _truncate_evidence(evidence, max_evidence_chars)

            # Mark as bounded
            safe_result["bounded"] = True

            results.append(safe_result)

    # Extract and bound skipped checks
    skipped_checks: list[dict[str, Any]] = []
    raw_skipped = runner_result.get("skipped_checks", [])
    if isinstance(raw_skipped, list):
        for skipped in raw_skipped[:10]:  # Limit to 10
            if isinstance(skipped, dict):
                safe_skipped = _strip_action_fields(dict(skipped))
                skipped_checks.append(safe_skipped)

    # Extract and bound rejected checks
    rejected_checks: list[dict[str, Any]] = []
    raw_rejected = runner_result.get("rejected_checks", [])
    if isinstance(raw_rejected, list):
        for rejected in raw_rejected[:10]:  # Limit to 10
            if isinstance(rejected, dict):
                safe_rejected = _strip_action_fields(dict(rejected))
                rejected_checks.append(safe_rejected)

    # Extract safety metadata if present
    safety_metadata = payload.get("safety_metadata", {})
    if not isinstance(safety_metadata, dict):
        safety_metadata = {}

    # Build safe artifact reference
    artifact_ref: dict[str, object] = {
        "kind": "external-analysis",
        "type": "read-only-check-results",
        "name": f"{run_id}-read-only-check-results.json",
        "safe": True,
    }

    # Build the entry
    entry: dict[str, object] = {
        "artifact_type": "read-only-check-results",
        "run_id": run_id,
        "generated_at": str(generated_at) if generated_at else None,
        "checks_requested": checks_requested,
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
        "checks_rejected": checks_rejected,
        "results": results,
        "bounded": True,
        "fake_runner_artifact": True,
        "artifact_ref": artifact_ref,
    }

    # Add optional fields if present
    if artifact_incident_id:
        entry["incident_id"] = artifact_incident_id

    # Add source label
    entry["source"] = payload.get("source", "unknown")

    # Add safety metadata
    if safety_metadata:
        entry["safety_metadata"] = _strip_action_fields(dict(safety_metadata))

    return entry


def load_read_only_check_result_artifacts_for_incident(
    incident: Incident,
    external_analysis_dir: Path,
    *,
    max_artifacts: int = DEFAULT_MAX_READ_ONLY_CHECK_ARTIFACTS,
    max_summary_chars: int = DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS,
    max_evidence_chars: int = DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS,
) -> list[dict[str, object]]:
    """Load read-only check result artifacts for an incident.

    Extracts run_ids from incident signals, locates corresponding
    check result artifacts, loads and validates them, and returns
    in deterministic order.

    Args:
        incident: The incident to load check result artifacts for
        external_analysis_dir: Path to the external-analysis directory
        max_artifacts: Maximum number of artifacts to load (default 10)
        max_summary_chars: Maximum characters for summary fields (default 500)
        max_evidence_chars: Maximum characters for evidence fields (default 2000)

    Returns:
        List of bounded check result entries

    Failure-tolerant behavior:
    - Missing directory: returns empty list
    - Missing artifact: skipped
    - Malformed artifact: skipped
    - Wrong incident linkage: skipped
    - Run_ids beyond max_artifacts: truncated (deterministic)
    - Unsafe run_ids: skipped

    Note:
        Does not mutate incident or artifacts.
        Does not raise for normal missing/malformed artifact cases.
    """
    # Extract run_ids from signals
    seen: set[str] = set()
    run_ids: list[str] = []
    for signal in incident.signals:
        run_id = signal.run_id
        if run_id is not None and run_id not in seen:
            seen.add(run_id)
            run_ids.append(run_id)

    # Bound the number of run_ids to check
    if len(run_ids) > max_artifacts * 2:  # Allow checking more than returning
        run_ids = run_ids[: max_artifacts * 2]

    # Early exit if no run_ids or directory doesn't exist
    if not run_ids:
        return []

    if not external_analysis_dir.is_dir():
        return []

    # Load artifacts
    entries: list[dict[str, object]] = []
    current_incident_id = incident.incident_id

    for run_id in run_ids:
        if len(entries) >= max_artifacts:
            break

        # Safety check: skip unsafe run_ids
        if not is_safe_run_id(run_id):
            continue

        # Construct path
        artifact_path = _artifact_path_for_run(external_analysis_dir, run_id)
        if artifact_path is None:
            continue

        # Load payload
        payload = _load_artifact_payload(artifact_path)
        if payload is None:
            continue

        # Extract bounded entry
        entry = _extract_bounded_check_result_entry(
            run_id=run_id,
            payload=payload,
            current_incident_id=current_incident_id,
            max_summary_chars=max_summary_chars,
            max_evidence_chars=max_evidence_chars,
        )

        if entry is not None:
            entries.append(entry)

    # Deterministic ordering: sort by run_id
    entries.sort(key=lambda e: str(e.get("run_id", "")))

    return entries[:max_artifacts]

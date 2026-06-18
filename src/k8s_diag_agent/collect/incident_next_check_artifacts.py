"""Pure helper module for loading next-check plan artifacts for incident detail.

This module provides read-only extraction logic for populating
IncidentDetailPayload.suggested_checks from next-check plan artifacts.

Design constraints:
- Pure functions only
- Bounded file IO only in explicit load function
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic ordering
- Failure-tolerant (missing/malformed artifacts produce empty results)

SAFE extraction rule:
Only candidates where linkage_status="linked" AND incident_id matches current incident.

Path safety:
- run_id values are validated against strict character constraints
- Unsafe run_ids are skipped without path construction
- Only exact expected filenames are read (no glob/recursive patterns)
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_lifecycle import Incident

__all__ = [
    "incident_signal_run_ids",
    "next_check_plan_path_for_run",
    "load_next_check_plan_payload",
    "load_next_check_plan_payloads_for_incident",
    "is_safe_next_check_run_id",
]

# Expected filename pattern for next-check plan artifacts
_NEXT_CHECK_PLAN_FILENAME_PATTERN = "{run_id}-next-check-plan.json"

# Maximum number of artifacts to load (bounded for safety)
_MAX_ARTIFACTS = 16

# Strict regex for allowed run_id characters: A-Z a-z 0-9 _ . -
# Excludes: / \ .. and other special characters
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


# =============================================================================
# Pure Extraction Helpers
# =============================================================================


def is_safe_next_check_run_id(run_id: str | None) -> bool:
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


def incident_signal_run_ids(incident: Incident) -> tuple[str, ...]:
    """Extract unique run_id values from incident signals.

    Extracts run_id from each signal that has one, deduplicates while
    preserving first-occurrence order for deterministic behavior.

    Args:
        incident: The incident to extract run_ids from

    Returns:
        Tuple of unique run_ids in first-occurrence order
    """
    seen: set[str] = set()
    result: list[str] = []

    for signal in incident.signals:
        run_id = signal.run_id
        if run_id is not None and run_id not in seen:
            seen.add(run_id)
            result.append(run_id)

    return tuple(result)


def next_check_plan_path_for_run(
    external_analysis_dir: Path,
    run_id: str,
) -> Path | None:
    """Construct the expected path for a next-check plan artifact.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The run ID to construct path for

    Returns:
        Path to the expected next-check plan artifact, or None if run_id is unsafe.

    Note:
        Does not check if the file exists - caller is responsible for
        existence check before loading.
    """
    # Safety check: reject unsafe run_ids
    if not is_safe_next_check_run_id(run_id):
        return None

    filename = _NEXT_CHECK_PLAN_FILENAME_PATTERN.format(run_id=run_id)
    return external_analysis_dir / filename


def load_next_check_plan_payload(path: Path) -> Mapping[str, object] | None:
    """Load and validate a next-check plan artifact payload.

    This function is NOT pure - it performs file IO.

    Args:
        path: Path to the artifact file

    Returns:
        Validated plan payload dict if file exists and is valid JSON dict,
        None otherwise (file missing, malformed JSON, or non-dict root)

    Failure-tolerant behavior:
    - Missing file: returns None
    - Malformed JSON: returns None
    - Root is not a dict/mapping: returns None
    - Other IO errors: returns None
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


def load_next_check_plan_payloads_for_incident(
    incident: Incident,
    external_analysis_dir: Path,
    *,
    max_artifacts: int = _MAX_ARTIFACTS,
) -> tuple[Mapping[str, object], ...]:
    """Load next-check plan payloads for an incident.

    Extracts run_ids from incident signals, locates corresponding plan
    artifacts, loads and validates them, and returns in deterministic order.

    Args:
        incident: The incident to load plan artifacts for
        external_analysis_dir: Path to the external-analysis directory
        max_artifacts: Maximum number of artifacts to load (default 16)

    Returns:
        Tuple of valid plan payloads in run_id order

    Failure-tolerant behavior:
    - Missing directory: returns empty tuple
    - Missing artifact: skipped
    - Malformed artifact: skipped
    - Run_ids beyond max_artifacts: truncated (deterministic)

    Note:
        Does not mutate incident or artifacts.
        Does not raise for normal missing/malformed artifact cases.
    """
    # Extract run_ids from signals
    run_ids = incident_signal_run_ids(incident)

    # Bound the number of artifacts to load
    if len(run_ids) > max_artifacts:
        run_ids = run_ids[:max_artifacts]

    # Early exit if no run_ids or directory doesn't exist
    if not run_ids:
        return ()

    if not external_analysis_dir.is_dir():
        return ()

    # Load each artifact in run_id order
    payloads: list[Mapping[str, object]] = []
    for run_id in run_ids:
        if len(payloads) >= max_artifacts:
            break

        # Safety check: skip unsafe run_ids to prevent path traversal
        if not is_safe_next_check_run_id(run_id):
            continue

        plan_path = next_check_plan_path_for_run(external_analysis_dir, run_id)
        if plan_path is None:
            continue
        payload = load_next_check_plan_payload(plan_path)

        if payload is not None:
            payloads.append(payload)

    return tuple(payloads)

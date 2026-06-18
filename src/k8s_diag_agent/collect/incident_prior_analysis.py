"""Pure helper module for loading prior analysis artifacts for incident case files.

This module provides read-only extraction logic for populating
incident case-file packets with bounded prior analysis context.

Design constraints:
- Pure functions only
- Bounded file IO only in explicit load function
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic ordering
- Failure-tolerant (missing/malformed artifacts produce empty results)

SAFE extraction rules:
- Only artifacts linked by matching run_id from incident signals
- Only artifacts where linkage schema version is present
- Only artifacts where incident_id matches current incident (if present in artifact)
- Unsafe run_ids are skipped without path construction

Artifact naming conventions:
- {run_id}-next-check-review.json: review of next-check results

Note: Only next-check-review is implemented. Other patterns are documented
for future extensibility.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_lifecycle import Incident

__all__ = [
    "load_prior_analysis_for_incident",
    "is_safe_run_id",
]

# =============================================================================
# Constants and Patterns
# =============================================================================

# Maximum number of prior analysis artifacts to load (bounded for safety)
DEFAULT_MAX_PRIOR_ANALYSIS = 10

# Maximum characters for summary fields
DEFAULT_MAX_SUMMARY_CHARS = 1000

# Maximum characters for raw output fields
DEFAULT_MAX_RAW_CHARS = 2000

# Artifact filename patterns by type
_ARTIFACT_PATTERNS: dict[str, str] = {
    "next-check-review": "{run_id}-next-check-review.json",
}

# Strict regex for allowed run_id characters: A-Z a-z 0-9 _ . -
# Excludes: / \ .. and other special characters
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# Fields that must NOT appear in prior_analysis entries (action-control fields)
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
})

# Source types for prior analysis
PRIOR_ANALYSIS_SOURCE_TYPES: frozenset[str] = frozenset({
    "next-check-review",
    "llm-summary",
    "llm-diagnosis",
    "review-enrichment",
    "unknown",
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
    artifact_type: str,
) -> Path | None:
    """Construct the expected path for a prior analysis artifact.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The run ID to construct path for
        artifact_type: Type of artifact (e.g., "next-check-review")

    Returns:
        Path to the expected artifact, or None if run_id is unsafe.
    """
    if not is_safe_run_id(run_id):
        return None

    pattern = _ARTIFACT_PATTERNS.get(artifact_type)
    if not pattern:
        return None

    filename = pattern.format(run_id=run_id)
    return external_analysis_dir / filename


# =============================================================================
# Safe Field Extraction
# =============================================================================


def _strip_action_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Remove action-control fields from a dict.

    This ensures prior analysis entries do not contain fields that could
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


def _detect_source_type(artifact_type: str, payload: Mapping[str, object]) -> str:
    """Detect the source type from artifact type and payload content.

    Args:
        artifact_type: The filename-based artifact type
        payload: The loaded artifact payload

    Returns:
        Detected source type string
    """
    if artifact_type == "next-check-review":
        # Check for review-enrichment signature
        if payload.get("purpose") == "review-enrichment":
            return "review-enrichment"
        return "next-check-review"

    # Check for llm-summary signature
    if payload.get("kind") == "llm-summary":
        return "llm-summary"

    # Check for llm-diagnosis signature
    if payload.get("kind") == "llm-diagnosis":
        return "llm-diagnosis"

    return "unknown"


def _extract_prior_analysis_entry(
    artifact_type: str,
    run_id: str,
    payload: Mapping[str, object],
    current_incident_id: str,
    max_summary_chars: int,
    max_raw_chars: int,
) -> dict[str, object] | None:
    """Extract a bounded prior analysis entry from an artifact payload.

    Args:
        artifact_type: Type of artifact (e.g., "next-check-review")
        run_id: Run ID from the filename
        payload: Loaded artifact payload
        current_incident_id: Incident ID to validate linkage
        max_summary_chars: Maximum characters for summary field
        max_raw_chars: Maximum characters for raw output fields

    Returns:
        Bounded prior analysis entry dict, or None if linkage is invalid
    """
    # Validate linkage schema version exists (required for trusted linkage)
    linkage_schema_version = payload.get("linkage_schema_version")
    if linkage_schema_version is None:
        return None

    # Check incident_id linkage if present in artifact
    artifact_incident_id = payload.get("incident_id")
    if artifact_incident_id is not None and artifact_incident_id != current_incident_id:
        # Wrong incident - do not include
        return None

    # Detect source type
    source = _detect_source_type(artifact_type, payload)

    # Extract bounded summary
    raw_summary = payload.get("summary") or payload.get("message") or ""
    summary = _truncate_string(str(raw_summary) if raw_summary else None, max_summary_chars)

    # Extract bounded raw output if present
    raw_output = payload.get("raw_output") or payload.get("raw_model_output")
    bounded_raw = _truncate_string(str(raw_output) if raw_output else None, max_raw_chars)

    # Extract confidence if present
    confidence = str(payload.get("confidence", "unknown"))

    # Extract supporting evidence if present (bounded)
    supporting_evidence: list[str] = []
    evidence_list = payload.get("supporting_evidence") or payload.get("evidence") or []
    if isinstance(evidence_list, list):
        for item in evidence_list[:5]:  # Limit to 5 evidence items
            if isinstance(item, str):
                supporting_evidence.append(_truncate_string(item, 200) or "")

    # Extract uncertainties if present (bounded)
    uncertainties: list[str] = []
    uncertainty_list = payload.get("uncertainties") or []
    if isinstance(uncertainty_list, list):
        for item in uncertainty_list[:3]:  # Limit to 3 uncertainty items
            if isinstance(item, str):
                uncertainties.append(_truncate_string(item, 200) or "")

    # Extract generated_at timestamp if present
    generated_at = payload.get("generated_at") or payload.get("timestamp") or payload.get("created_at")
    if generated_at:
        generated_at = str(generated_at)

    # Build safe artifact reference
    artifact_ref: dict[str, object] = {
        "kind": "external-analysis",
        "type": artifact_type,
        "name": f"{run_id}-{artifact_type}.json",
        "safe": True,
    }

    # Build the entry (strip action fields from any nested data)
    entry: dict[str, object] = {
        "source": source,
        "run_id": run_id,
        "summary": summary,
        "confidence": confidence,
        "bounded": True,
        "artifact_ref": artifact_ref,
    }

    # Add optional fields if present
    if artifact_incident_id:
        entry["incident_id"] = artifact_incident_id

    if generated_at:
        entry["generated_at"] = generated_at

    if supporting_evidence:
        entry["supporting_evidence"] = supporting_evidence

    if uncertainties:
        entry["uncertainties"] = uncertainties

    if bounded_raw:
        entry["raw_output"] = bounded_raw

    # Note: This is model-generated context, not ground truth
    entry["_model_generated"] = True
    entry["_bounded"] = True

    return entry


# =============================================================================
# Main Loading Function
# =============================================================================


def load_prior_analysis_for_incident(
    incident: Incident,
    external_analysis_dir: Path,
    *,
    max_items: int = DEFAULT_MAX_PRIOR_ANALYSIS,
    max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
    max_raw_chars: int = DEFAULT_MAX_RAW_CHARS,
) -> list[dict[str, object]]:
    """Load prior analysis artifacts for an incident.

    Extracts run_ids from incident signals, locates corresponding prior
    analysis artifacts, loads and validates them, and returns in
    deterministic order.

    Args:
        incident: The incident to load prior analysis for
        external_analysis_dir: Path to the external-analysis directory
        max_items: Maximum number of prior analysis entries to return (default 10)
        max_summary_chars: Maximum characters for summary fields (default 1000)
        max_raw_chars: Maximum characters for raw output fields (default 2000)

    Returns:
        List of bounded prior analysis entries

    Failure-tolerant behavior:
    - Missing directory: returns empty list
    - Missing artifact: skipped
    - Malformed artifact: skipped
    - Wrong incident linkage: skipped
    - Run_ids beyond max_items: truncated (deterministic)
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
    if len(run_ids) > max_items * 2:  # Allow checking more than returning
        run_ids = run_ids[: max_items * 2]

    # Early exit if no run_ids or directory doesn't exist
    if not run_ids:
        return []

    if not external_analysis_dir.is_dir():
        return []

    # Load artifacts for each type
    entries: list[dict[str, object]] = []
    current_incident_id = incident.incident_id

    for run_id in run_ids:
        if len(entries) >= max_items:
            break

        # Safety check: skip unsafe run_ids
        if not is_safe_run_id(run_id):
            continue

        # Try each artifact type
        for artifact_type in _ARTIFACT_PATTERNS:
            if len(entries) >= max_items:
                break

            artifact_path = _artifact_path_for_run(external_analysis_dir, run_id, artifact_type)
            if artifact_path is None:
                continue

            payload = _load_artifact_payload(artifact_path)
            if payload is None:
                continue

            entry = _extract_prior_analysis_entry(
                artifact_type=artifact_type,
                run_id=run_id,
                payload=payload,
                current_incident_id=current_incident_id,
                max_summary_chars=max_summary_chars,
                max_raw_chars=max_raw_chars,
            )

            if entry is not None:
                entries.append(entry)

    # Deterministic ordering: sort by run_id then source type
    entries.sort(key=lambda e: (e.get("run_id", ""), e.get("source", "")))

    return entries[:max_items]

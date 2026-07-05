"""Bounded diagnosis loop review packet artifact writer.

Provides a deterministic evidence packet for operator/ChatGPT review after
automatic diagnosis loop evidence collection.

Design constraints:
- Bounded JSON output only
- No raw artifact contents, absolute paths, secrets, or action-control fields
- Deterministic and JSON-serializable

Artifact naming: {run_id}-diagnosis-review-packet.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..observability import (
    trace_artifact_scan,
    trace_review_packet_load,
)
from .incident_diagnosis_review_packet_exceptions import (
    AutomaticDiagnosisReviewPacketUnavailable,
)
from .incident_read_only_check_artifacts import is_safe_run_id

if TYPE_CHECKING:
    from .incident_diagnosis_auto_loop import AutomaticDiagnosisLoopConfig


__all__ = [
    "write_diagnosis_review_packet",
    "load_review_packet_summary",
    "load_review_packet_for_handoff",
    "find_latest_review_packet",
    "REVIEW_PACKET_SCHEMA_VERSION",
    "REVIEW_PACKET_ARTIFACT_TYPE",
    "AutomaticDiagnosisReviewPacketUnavailable",
]


# =============================================================================
# Constants
# =============================================================================

# Schema version for tracking structure evolution
REVIEW_PACKET_SCHEMA_VERSION = "1.0"

# Artifact type identifier
REVIEW_PACKET_ARTIFACT_TYPE = "diagnosis-loop-review-packet"

# Review packet filename suffix
REVIEW_PACKET_SUFFIX = "diagnosis-review-packet.json"

# Bounds for safety
MAX_SELECTED_CHECKS = 5
MAX_ARTIFACT_REFS = 10


# =============================================================================
# Forbidden Fields
# =============================================================================

# Action-control fields that must not appear in review packets
_FORBIDDEN_ACTION_FIELDS: frozenset[str] = frozenset([
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
    "patch",
    "kubectl",
    "helm",
])

# Forbidden metadata fields
_FORBIDDEN_METADATA_FIELDS: frozenset[str] = frozenset([
    "kubeconfig",
    "token",
    "secret",
    "password",
    "api_key",
    "authorization",
])


# =============================================================================
# Public API
# =============================================================================


def write_diagnosis_review_packet(
    *,
    external_analysis_dir: Path,
    incident_id: str,
    collector_run_id: str,
    run_id: str,
    decision: str,
    checks_requested: int,
    checks_run: int,
    checks_skipped: int,
    checks_rejected: int,
    eligible: bool,
    eligibility_reason: str,
    config: AutomaticDiagnosisLoopConfig | None = None,
    now: datetime | None = None,
    case_file: dict[str, Any] | None = None,
    orchestrator_result: dict[str, Any] | None = None,
    provider_configured: bool = False,
    provider_invocation_attempted: bool = False,
    provider_name: str | None = None,
) -> dict[str, object]:
    """Write a bounded diagnosis loop review packet artifact.

    This function creates a deterministic JSON artifact intended for
    operator/ChatGPT review after automatic diagnosis loop evidence collection.

    The packet contains:
    - Bounded metadata (no absolute paths, no secrets)
    - Selected checks (bounded, from case file only)
    - Loop result counts
    - Artifact references (filenames only)
    - Safety metadata
    - Review guidance

    The packet does NOT contain:
    - Raw case file contents
    - Raw runner results
    - Absolute filesystem paths
    - Stack traces
    - Secret values
    - Action-control fields

    Args:
        external_analysis_dir: Path to external-analysis directory
        incident_id: The incident ID this packet belongs to
        collector_run_id: The collector batch run ID
        run_id: The run ID for this specific incident's automatic pass
        decision: The loop decision string
        checks_requested: Number of checks requested
        checks_run: Number of checks actually run
        checks_skipped: Number of checks skipped
        checks_rejected: Number of checks rejected
        eligible: Whether the incident was eligible
        eligibility_reason: Reason for eligibility determination
        config: Optional collector configuration
        now: Optional datetime for deterministic timestamps
        case_file: Optional case file for extracting selected checks
        orchestrator_result: Optional orchestrator result for artifact references

    Returns:
        Dict with artifact metadata including path and status

    Raises:
        ValueError: If run_id is unsafe

    Safety:
        - Validates run_id against strict character constraints
        - Does not write absolute paths or raw artifacts
        - Does not include forbidden action-control fields
        - Does not include secrets or stack traces
    """
    # Validate run_id for safety
    if not is_safe_run_id(run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")

    # Resolve timestamp
    resolved_now = now if now is not None else datetime.now(UTC)

    # Build configuration dict
    config_dict: dict[str, Any] = {
        "max_passes_per_incident": 1,
        "max_checks_per_pass": 5,
        "max_incidents_per_run": 10,
    }
    if config is not None:
        config_dict = config.to_dict()

    # Extract selected checks from case file (bounded)
    selected_checks = _extract_selected_checks(case_file, MAX_SELECTED_CHECKS)

    # Extract artifact references (bounded, filenames only)
    artifact_refs = _extract_artifact_refs(orchestrator_result, MAX_ARTIFACT_REFS)

    # Build the review packet
    packet: dict[str, Any] = {
        # Schema and type identification
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "artifact_type": REVIEW_PACKET_ARTIFACT_TYPE,

        # Identity
        "incident_id": incident_id,
        "automatic": True,
        "read_only": True,
        "allowed_actions": [],
        "run_id": run_id,
        "collector_run_id": collector_run_id,
        "generated_at": resolved_now.isoformat(),

        # Eligibility
        "eligibility": {
            "eligible": eligible,
            "reason": eligibility_reason,
        },

        # Budget
        "budget": {
            "max_passes_per_incident": config_dict.get("max_passes_per_incident", 1),
            "max_checks_per_pass": config_dict.get("max_checks_per_pass", 5),
            "pass_index": 1,
            "passes_completed": 1,
        },

        # Selected checks (bounded source)
        "selected_checks": selected_checks,

        # Loop result
        "loop_result": {
            "decision": decision,
            "checks_requested": checks_requested,
            "checks_run": checks_run,
            "checks_skipped": checks_skipped,
            "checks_rejected": checks_rejected,
        },

        # Artifact references (filenames only)
        "artifacts": artifact_refs,

        # Review guidance
        "review_guidance": {
            "intended_reviewer": "operator_or_chatgpt",
            "review_required_before_any_action": True,
            "summary": "Bounded evidence packet. No remediation was attempted.",
            "packet_purpose": "Automatic diagnosis loop evidence collection for operator review",
        },

        # Safety metadata
        "safety_metadata": {
            "read_only": True,
            "allowed_actions": [],
            "no_kubernetes_mutation": True,
            "no_shell": True,
            "no_subprocess": True,
            "no_kubectl": True,
            "no_remediation": True,
            "automatic_evidence_collection_only": True,
            "no_llm_calls": True,
            "no_execution": True,
            "bounded": True,
        },

        # Provider status - persisted for Phase 4 contract verification
        # These fields expose LLM provider configuration/invocation state
        "provider_status": {
            "provider_enabled": provider_configured,
            "provider_configured": provider_configured,
            "provider_invocation_attempted": provider_invocation_attempted,
            "provider_name": provider_name,
        },
    }

    # Write artifact as deterministic JSON
    packet_path = _review_packet_path(external_analysis_dir, run_id)
    packet_json = json.dumps(packet, default=str, indent=2)
    packet_path.write_text(packet_json, encoding="utf-8")

    return {
        "artifact_path": str(packet_path),
        "run_id": run_id,
        "incident_id": incident_id,
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "artifact_type": REVIEW_PACKET_ARTIFACT_TYPE,
        "written": True,
        "name": packet_path.name,
    }


# =============================================================================
# Internal Helpers
# =============================================================================


def _review_packet_path(external_analysis_dir: Path, run_id: str) -> Path:
    """Construct the review packet artifact path.

    Args:
        external_analysis_dir: Path to external-analysis directory
        run_id: The run ID for this pass

    Returns:
        Path to the review packet artifact
    """
    return external_analysis_dir / f"{run_id}-{REVIEW_PACKET_SUFFIX}"


def _extract_selected_checks(
    case_file: dict[str, Any] | None,
    max_checks: int,
) -> list[dict[str, Any]]:
    """Extract bounded selected checks from case file.

    Args:
        case_file: The incident case file
        max_checks: Maximum number of checks to include

    Returns:
        Bounded list of selected checks with safe metadata
    """
    if case_file is None:
        return []

    suggested_checks = case_file.get("suggested_checks", [])
    if not isinstance(suggested_checks, list):
        return []

    selected = []
    for check in suggested_checks[:max_checks]:
        if not isinstance(check, dict):
            continue

        # Extract safe fields only
        check_id = check.get("check_id") or check.get("id")
        title = check.get("title") or check.get("name") or check_id

        if not check_id:
            continue

        # Build safe check entry (no action-control fields)
        safe_entry: dict[str, Any] = {
            "check_id": check_id,
            "title": str(title)[:200],  # Bound title length
            "source": "automatic_suggested_check",
        }

        # Add optional safe fields
        if check.get("read_only") is not None:
            safe_entry["read_only"] = bool(check.get("read_only"))

        selected.append(safe_entry)

    return selected


def _extract_artifact_refs(
    orchestrator_result: dict[str, Any] | None,
    max_refs: int,
) -> dict[str, Any]:
    """Extract bounded artifact references from orchestrator result.

    Args:
        orchestrator_result: The orchestrator result dict
        max_refs: Maximum number of artifact refs to include

    Returns:
        Bounded dict with artifact references (filenames only)
    """
    refs: dict[str, Any] = {
        "read_only_check_results": {
            "written": False,
            "name": None,
        },
        "diagnosis_loop_pass": {
            "written": False,
            "name": None,
        },
    }

    if orchestrator_result is None:
        return refs

    # Extract read-only check artifact reference
    artifact = orchestrator_result.get("artifact")
    if artifact and isinstance(artifact, dict):
        if artifact.get("written"):
            path = artifact.get("artifact_path") or artifact.get("path")
            if path:
                refs["read_only_check_results"] = {
                    "written": True,
                    "name": Path(str(path)).name,
                }

    # Extract loop-pass artifact reference
    loop_pass_artifact = orchestrator_result.get("loop_pass_artifact")
    if loop_pass_artifact and isinstance(loop_pass_artifact, dict):
        if loop_pass_artifact.get("written"):
            path = loop_pass_artifact.get("artifact_path") or loop_pass_artifact.get("path")
            if path:
                refs["diagnosis_loop_pass"] = {
                    "written": True,
                    "name": Path(str(path)).name,
                }

    return refs


# =============================================================================
# Review Packet Lookup
# =============================================================================


def find_latest_review_packet(
    external_analysis_dir: Path,
    incident_id: str,
) -> dict[str, Any] | None:
    """Find the latest review packet for an incident.

    Args:
        external_analysis_dir: Path to external-analysis directory
        incident_id: The incident ID to search for

    Returns:
        Dict with packet metadata or None if not found
    """
    if not external_analysis_dir.exists():
        return None

    def _scan_directory() -> dict[str, Any] | None:
        # Search for packets matching this incident
        # Pattern: auto-{incident_id}-*-diagnosis-review-packet.json
        prefix = f"auto-{incident_id}-"
        suffix = f"-{REVIEW_PACKET_SUFFIX}"

        candidates: list[tuple[datetime, Path]] = []

        try:
            for path in external_analysis_dir.iterdir():
                if not path.is_file():
                    continue
                name = path.name
                if name.startswith(prefix) and name.endswith(suffix):
                    # Extract timestamp from filename for ordering
                    # Format: auto-{incident_id}-{timestamp}-{uuid}-diagnosis-review-packet.json
                    try:
                        parts = name[len(prefix):-len(suffix)].rsplit("-", 1)
                        if parts:
                            timestamp_str = parts[0]
                            # Try to parse timestamp
                            dt = datetime.strptime(timestamp_str[:14], "%Y%m%d%H%M%S")
                            candidates.append((dt, path))
                    except (ValueError, IndexError):
                        # Fallback: use file modification time
                        candidates.append((datetime.fromtimestamp(path.stat().st_mtime), path))
        except OSError:
            return None

        if not candidates:
            return None

        # Return the most recent
        candidates.sort(key=lambda x: x[0], reverse=True)
        latest_path = candidates[0][1]

        return {
            "path": str(latest_path),
            "name": latest_path.name,
            "incident_id": incident_id,
            "file_count": len(candidates),
        }

    return trace_artifact_scan(  # type: ignore[no-any-return]
        _scan_directory,
        attributes={
            "k9b.path.kind": "artifact_dir",
            "k9b.artifact_kind": "review_packet",
        },
    )


def load_review_packet_summary(
    external_analysis_dir: Path,
    incident_id: str,
) -> dict[str, Any] | None:
    """Load a bounded summary of the latest review packet.

    This loads only the top-level metadata, not raw contents.

    Args:
        external_analysis_dir: Path to external-analysis directory
        incident_id: The incident ID to search for

    Returns:
        Bounded summary dict, or None if no packet exists for this incident
    """
    def _load() -> dict[str, Any] | None:
        packet_info = find_latest_review_packet(external_analysis_dir, incident_id)
        if packet_info is None:
            # No packet found for this incident - not an error, just unavailable
            return None

        try:
            content = Path(packet_info["path"]).read_text(encoding="utf-8")
            data = json.loads(content)

            # Return only bounded summary fields
            return {
                "incident_id": data.get("incident_id"),
                "run_id": data.get("run_id"),
                "collector_run_id": data.get("collector_run_id"),
                "decision": data.get("loop_result", {}).get("decision"),
                "checks_requested": data.get("loop_result", {}).get("checks_requested", 0),
                "checks_run": data.get("loop_result", {}).get("checks_run", 0),
                "checks_rejected": data.get("loop_result", {}).get("checks_rejected", 0),
                "generated_at": data.get("generated_at"),
                "artifact_name": data.get("run_id") + "-diagnosis-review-packet.json",
                "eligible": data.get("eligibility", {}).get("eligible"),
                "eligibility_reason": data.get("eligibility", {}).get("reason"),
                # Provider status - for Phase 4 contract verification
                "provider_status": data.get("provider_status", {}),
            }
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise AutomaticDiagnosisReviewPacketUnavailable(
                f"Failed to load review packet for incident {incident_id!r}: {exc}"
            ) from exc

    return trace_review_packet_load(  # type: ignore[no-any-return]
        _load,
        attributes={
            "k9b.artifact_kind": "review_packet",
        },
    )


def load_review_packet_for_handoff(
    external_analysis_dir: Path,
    incident_id: str,
) -> dict[str, Any] | None:
    """Load data from the latest review packet suitable for handoff generation.

    This loads the packet and extracts fields needed for the handoff payload.
    Unlike load_review_packet_summary, this returns additional fields needed
    for the markdown handoff content.

    Args:
        external_analysis_dir: Path to external-analysis directory
        incident_id: The incident ID to search for

    Returns:
        Dict with packet fields needed for handoff, or None if no packet exists
    """
    def _load() -> dict[str, Any] | None:
        packet_info = find_latest_review_packet(external_analysis_dir, incident_id)
        if packet_info is None:
            return None

        try:
            content = Path(packet_info["path"]).read_text(encoding="utf-8")
            data = json.loads(content)

            # Return fields needed for handoff generation
            return {
                "run_id": data.get("run_id"),
                "collector_run_id": data.get("collector_run_id"),
                "decision": data.get("loop_result", {}).get("decision"),
                "checks_requested": data.get("loop_result", {}).get("checks_requested", 0),
                "checks_run": data.get("loop_result", {}).get("checks_run", 0),
                "checks_rejected": data.get("loop_result", {}).get("checks_rejected", 0),
                "generated_at": data.get("generated_at"),
                "eligible": data.get("eligibility", {}).get("eligible"),
                "eligibility_reason": data.get("eligibility", {}).get("reason"),
            }
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise AutomaticDiagnosisReviewPacketUnavailable(
                f"Failed to load review packet for incident {incident_id!r}: {exc}"
            ) from exc

    return trace_review_packet_load(  # type: ignore[no-any-return]
        _load,
        attributes={
            "k9b.artifact_kind": "review_packet",
        },
    )

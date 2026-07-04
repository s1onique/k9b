"""P4c forensic dump: dump writer functions.

This module provides forensic dump writers:
- dump_backend_incident_detail_before_loop: Dump 3
- dump_diagnosis_loop_pass: Dump 4
- write_forensic_summary: Composite report

These are separated from provenance capture to support LLM-friendly line-count gate.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Re-export from evidence module for internal use
from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (
    _get_forensic_dump_dir,
    _mapping_summary,
    is_forensic_dump_enabled,
)

# =============================================================================
# Dump 3: Backend Incident Detail Before Diagnosis-Loop
# =============================================================================


def dump_backend_incident_detail_before_loop(
    artifact_dir: Path,
    incident_detail: dict[str, Any] | None,
    incident_id: str,
) -> dict[str, Any] | None:
    """Dump the full backend incident detail JSON before diagnosis-loop pass 1.

    Captures:
    - incident detail
    - review packet status
    - evidence links
    - signals
    - any scheduling_evidence fields

    Args:
        artifact_dir: Root artifact directory
        incident_detail: The incident detail dict from backend
        incident_id: The incident ID

    Returns:
        The provenance dict or None if dump disabled
    """
    if not is_forensic_dump_enabled():
        return None

    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    # Stable schema: wrap incident_detail in a summary dict for non-Mapping inputs
    # This ensures forensic artifacts have stable JSON schemas even when
    # the source value is malformed/non-mapping (None, list, str, etc.)
    incident_detail_summary = _mapping_summary(incident_detail)

    provenance: dict[str, Any] = {
        "timestamp": timestamp,
        "incident_id": incident_id,
        "phase": "before_diagnosis_loop_pass_1",
        "incident_detail": incident_detail_summary,
        "fields_present": incident_detail_summary["fields_present"],
    }

    # Extract scheduling_evidence if the input was a valid mapping
    if isinstance(incident_detail, Mapping):
        provenance["scheduling_evidence"] = incident_detail.get("scheduling_evidence")
        provenance["signals_count"] = len(incident_detail.get("signals", []))
        provenance["events_count"] = len(incident_detail.get("events", []))
        provenance["evidence_links_count"] = len(incident_detail.get("evidence_links", []))

    # Write to file
    output_path = dump_dir / f"incident-detail-before-loop-{incident_id[:8]}-{timestamp}.json"
    with open(output_path, "w") as f:
        import json
        json.dump(provenance, f, indent=2, default=str)

    return provenance


# =============================================================================
# Dump 4: Backend Diagnosis-Loop Request/Response for Each Pass
# =============================================================================


def dump_diagnosis_loop_pass(
    artifact_dir: Path,
    incident_id: str,
    pass_num: int,
    request_body: dict[str, Any] | None,
    http_status: int | None,
    response_body: dict[str, Any] | None,
    loop_summary: dict[str, Any] | None,
    review_packet_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Dump diagnosis-loop request/response JSON for a single pass.

    Captures:
    - request body
    - HTTP status
    - full response body
    - loop summary
    - generated review packet metadata

    Args:
        artifact_dir: Root artifact directory
        incident_id: The incident ID
        pass_num: Pass number (1, 2, ...)
        request_body: Request body sent to backend
        http_status: HTTP status code
        response_body: Full response from backend
        loop_summary: Diagnosis loop summary
        review_packet_metadata: Metadata about generated review packet

    Returns:
        Dict with pass provenance data
    """
    if not is_forensic_dump_enabled():
        return {}

    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    # Stable schema: get response summary using _mapping_summary
    # This ensures forensic artifacts have stable JSON schemas even when
    # the source value is malformed/non-mapping (None, list, str, etc.)
    response_summary = _mapping_summary(response_body, fields_key="response_fields_present")

    provenance: dict[str, Any] = {
        "timestamp": timestamp,
        "incident_id": incident_id,
        "pass_num": pass_num,
        "phase": "diagnosis_loop_pass",
        "http_status": http_status,
        "request_body": request_body,
        "response_summary": response_summary,
        "response_fields_present": response_summary["response_fields_present"],
        "loop_summary": loop_summary,
        "review_packet_metadata": review_packet_metadata,
    }

    # Extract key fields from response if it was a valid mapping
    if isinstance(response_body, Mapping):
        provenance["scheduling_evidence"] = response_body.get("scheduling_evidence")
        provenance["root_cause_summary"] = response_body.get("root_cause_summary")
        provenance["terminal_decision"] = response_body.get("terminal_decision")
        provenance["review_packet_path"] = response_body.get("review_packet_path")
        provenance["review_packet_artifact_name"] = response_body.get("review_packet_artifact_name")

    # Write to file
    output_path = dump_dir / f"diagnosis-loop-pass{pass_num}-{incident_id[:8]}-{timestamp}.json"
    with open(output_path, "w") as f:
        import json
        json.dump(provenance, f, indent=2, default=str)

    return provenance


# =============================================================================
# Composite Forensics Report
# =============================================================================


def write_forensic_summary(
    artifact_dir: Path,
    incident_id: str,
    classification: str | None,
    dumps: list[str],
    provenance: dict[str, Any],
) -> Path:
    """Write a forensic summary report.

    Args:
        artifact_dir: Root artifact directory
        incident_id: The incident ID
        classification: Classification bucket (A-F) if determined
        dumps: List of dump files created (concrete file paths)
        provenance: Summary provenance data

    Returns:
        Path to the summary file
    """
    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    # Nil-safe extraction of scheduling_evidence
    raw_scheduling_evidence = provenance.get("scheduling_evidence")
    
    # Guard against malformed scheduling_evidence (string, list, None, etc.)
    if isinstance(raw_scheduling_evidence, dict) and raw_scheduling_evidence:
        scheduling_evidence: dict[str, Any] = raw_scheduling_evidence
        scheduling_evidence_keys: list[str] = list(scheduling_evidence.keys())
        scheduling_evidence_type: str = "dict"
    else:
        scheduling_evidence = {}
        scheduling_evidence_keys = []
        scheduling_evidence_type = type(raw_scheduling_evidence).__name__ if raw_scheduling_evidence is not None else "NoneType"

    summary: dict[str, Any] = {
        "timestamp": timestamp,
        "incident_id": incident_id,
        "classification": classification,
        "dumps_created": dumps,
        "provenance_summary": {
            "has_backend_provenance": "backend" in provenance,
            "has_p4c_script_provenance": "p4c_script" in provenance,
            "has_p4c_input": "p4c_input" in provenance,
            "scheduling_evidence_keys": scheduling_evidence_keys,
            "scheduling_evidence_type": scheduling_evidence_type,
        },
        "failure_symptoms": {
            "matching_signals_count": scheduling_evidence.get("matching_signals_count", "N/A"),
            "selector_key": scheduling_evidence.get("selector_key"),
            "selector_value": scheduling_evidence.get("selector_value"),
            "failed_scheduling": scheduling_evidence.get("failed_scheduling"),
            "unschedulable": scheduling_evidence.get("unschedulable"),
            "completeness": scheduling_evidence.get("root_cause_summary") is not None,
        },
        "classification_buckets": {
            "A": "Backend image is stale",
            "B": "Backend artifact is stale",
            "C": "Backend case file lacks scheduling evidence",
            "D": "Backend has scheduling evidence, host verifier reads wrong artifact",
            "E": "Live input shape mismatch",
            "F": "Event-message marker guard too strict",
        },
    }

    output_path = dump_dir / f"forensic-summary-{incident_id[:8]}-{timestamp}.json"
    with open(output_path, "w") as f:
        import json
        json.dump(summary, f, indent=2, default=str)

    return output_path

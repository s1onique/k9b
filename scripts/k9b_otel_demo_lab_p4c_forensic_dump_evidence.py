#!/usr/bin/env python3
"""P4c forensic dump: evidence and summary helpers.

This module provides forensic dumps 5-6 and summary/integration helpers for
diagnosing P4c scheduling evidence gaps.
Dumps are written to lab-artifacts/otel-demo/phase4-diagnosis/p4c-debug/.

Required forensic dumps:
5. Backend review artifact files after each pass
6. Raw P4c outcome input (exact dict passed to compute_p4c_outcome)

This is committed as test/lab instrumentation, NOT ad-hoc manual debugging.

Enable with: K9B_P4C_FORENSIC_DUMP=1

The provenance/loop dumps (1-4) are in k9b_otel_demo_lab_p4c_forensic_dump.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# =============================================================================
# Environment and Configuration
# =============================================================================

FORENSIC_DUMP_ENABLED = os.environ.get("K9B_P4C_FORENSIC_DUMP", "0") == "1"
FORENSIC_DUMP_DIR_ENV = os.environ.get("K9B_FORENSIC_DUMP_DIR", "")


# =============================================================================
# Mapping Summary Helpers (shared between forensic dump modules)
# =============================================================================


def _mapping_fields_present(value: object) -> list[str]:
    """Return sorted list of field names for Mapping values, [] otherwise.

    Args:
        value: Any Python object

    Returns:
        Sorted list of string keys if value is a Mapping, empty list otherwise
    """
    if not isinstance(value, Mapping):
        return []
    return sorted(str(key) for key in value.keys())


def _mapping_summary(
    value: object,
    *,
    fields_key: str = "fields_present",
) -> dict[str, Any]:
    """Create a stable summary dict for any value, mapping or not.

    This ensures forensic artifacts have stable JSON schemas even when
    the source value is malformed/non-mapping.

    Args:
        value: Any Python object (dict, None, list, str, int, etc.)
        fields_key: Key name for the fields_present list (default "fields_present")

    Returns:
        Dict with is_mapping, value_type, and fields_present keys
    """
    return {
        "is_mapping": isinstance(value, Mapping),
        "value_type": type(value).__name__,
        fields_key: _mapping_fields_present(value),
    }


def _get_forensic_dump_dir(artifact_dir: Path) -> Path:
    """Get the forensic dump directory path.

    Args:
        artifact_dir: Root artifact directory

    Returns:
        Path to forensic dump directory
    """
    if FORENSIC_DUMP_DIR_ENV:
        dump_dir = Path(FORENSIC_DUMP_DIR_ENV)
    else:
        dump_dir = artifact_dir / "phase4-diagnosis" / "p4c-debug"
    dump_dir.mkdir(parents=True, exist_ok=True)
    return dump_dir


# =============================================================================
# Dump 5: Backend Review Artifact Files After Each Pass
# =============================================================================


def dump_review_artifact_files(
    artifact_dir: Path,
    incident_id: str,
    pass_num: int,
    backend_review_paths: list[str],
    host_review_paths: list[str],
    kubeconfig: str | None = None,
    backend_namespace: str = "k9b",
    backend_deployment: str = "k9b-backend",
    backend_container: str = "backend",
) -> dict[str, Any]:
    """Dump review artifact files content comparison.

    Compares:
    - Files from backend container (using kubectl exec)
    - Host-side copy if one exists

    Args:
        artifact_dir: Root artifact directory
        incident_id: The incident ID
        pass_num: Pass number
        backend_review_paths: Paths from backend container (inside container filesystem)
        host_review_paths: Paths from host side
        kubeconfig: Path to kubeconfig for kubectl exec
        backend_namespace: Namespace where k9b-backend runs
        backend_deployment: Deployment name for kubectl exec
        backend_container: Container name in the deployment

    Returns:
        Dict with artifact comparison data including backend_file_path field
    """
    if not FORENSIC_DUMP_ENABLED:
        return {}

    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    provenance: dict[str, Any] = {
        "timestamp": timestamp,
        "incident_id": incident_id,
        "pass_num": pass_num,
        "phase": "review_artifact_files",
        "backend_review_paths": backend_review_paths,
        "host_review_paths": host_review_paths,
        "backend_files": {},
        "host_files": {},
        "comparison": {},
        "backend_read_method": "kubectl_exec",
        "kubectl_config": {
            "kubeconfig": kubeconfig,
            "namespace": backend_namespace,
            "deployment": backend_deployment,
            "container": backend_container,
        },
    }

    # Build kubectl exec base
    kubectl_base = ["kubectl"]
    if kubeconfig:
        kubectl_base.extend(["--kubeconfig", kubeconfig])

    # Read backend review files using kubectl exec
    for path in backend_review_paths:
        backend_result: dict[str, Any] = {
            "path_in_container": path,
            "backend_read_not_configured": False,
        }

        try:
            # Use kubectl exec to read file from backend container
            # This is the correct approach for files inside the container
            result = subprocess.run(
                kubectl_base
                + [
                    "-n", backend_namespace,
                    "exec",
                    f"deploy/{backend_deployment}",
                    "-c", backend_container,
                    "--",
                    "cat", path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                content = result.stdout
                backend_result["exists"] = True
                backend_result["size"] = len(content)
                backend_result["content_preview"] = content[:500] if content else ""
                backend_result["read_method"] = "kubectl_exec"

                # Parse as JSON if possible
                try:
                    data = json.loads(content)
                    backend_result["scheduling_evidence"] = data.get("scheduling_evidence")
                    backend_result["root_cause_summary"] = data.get("root_cause_summary")
                except json.JSONDecodeError:
                    backend_result["parse_error"] = "not valid JSON"
            else:
                backend_result["exists"] = False
                backend_result["error"] = result.stderr.strip()
                backend_result["kubectl_rc"] = result.returncode

        except subprocess.TimeoutExpired:
            backend_result["exists"] = False
            backend_result["error"] = "kubectl exec timeout"
        except Exception as e:
            backend_result["exists"] = False
            backend_result["error"] = str(e)
            backend_result["backend_read_not_configured"] = True

        provenance["backend_files"][path] = backend_result

    # Read host review files
    for path in host_review_paths:
        try:
            file_path = Path(path)
            if file_path.exists():
                content = file_path.read_text()
                provenance["host_files"][path] = {
                    "exists": True,
                    "size": len(content),
                    "content_preview": content[:500] if content else "",
                }
            else:
                provenance["host_files"][path] = {"exists": False}
        except Exception as e:
            provenance["host_files"][path] = {"error": str(e)}

    # Compare backend and host
    provenance["comparison"] = {
        "backend_count": len(backend_review_paths),
        "host_count": len(host_review_paths),
        "paths_match": set(backend_review_paths) == set(host_review_paths),
    }

    # Write to file
    output_path = dump_dir / f"review-artifact-files-pass{pass_num}-{incident_id[:8]}-{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(provenance, f, indent=2, default=str)

    return provenance


# =============================================================================
# Dump 6: Raw P4c Outcome Input
# =============================================================================


def dump_p4c_outcome_input(
    artifact_dir: Path,
    evidence: dict[str, Any],
    incident_id: str,
) -> dict[str, Any]:
    """Dump the exact dict passed to compute_p4c_outcome().

    This is captured immediately before calling compute_p4c_outcome().

    Args:
        artifact_dir: Root artifact directory
        evidence: The evidence dict passed to compute_p4c_outcome
        incident_id: The incident ID

    Returns:
        Dict with the captured input
    """
    if not FORENSIC_DUMP_ENABLED:
        return {}

    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    # Stable schema: get evidence summary using _mapping_summary
    # This ensures forensic artifacts have stable JSON schemas even when
    # the source value is malformed/non-mapping (None, list, str, etc.)
    evidence_summary = _mapping_summary(evidence)

    provenance: dict[str, Any] = {
        "timestamp": timestamp,
        "incident_id": incident_id,
        "phase": "before_compute_p4c_outcome",
        "evidence_summary": evidence_summary,
        "fields_present": evidence_summary["fields_present"],
        "scheduling_evidence": None,
        "p4c_verdict": None,
        "root_cause_summary": None,
        "pass_count": None,
        "pass_run_ids": None,
        "evidence_size": 0,
    }

    # Extract key fields if evidence was a valid mapping
    if isinstance(evidence, Mapping):
        provenance["scheduling_evidence"] = evidence.get("scheduling_evidence")
        provenance["p4c_verdict"] = evidence.get("p4c_verdict")
        provenance["root_cause_summary"] = evidence.get("root_cause_summary")
        provenance["pass_count"] = evidence.get("pass_count")
        provenance["pass_run_ids"] = evidence.get("pass_run_ids")
        provenance["evidence_size"] = len(json.dumps(dict(evidence), default=str))

    # Write full evidence to separate file
    output_path = dump_dir / f"p4c-outcome-input-{incident_id[:8]}-{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(evidence, f, indent=2, default=str)

    # Write provenance summary
    provenance_path = dump_dir / f"p4c-outcome-input-provenance-{incident_id[:8]}-{timestamp}.json"
    with open(provenance_path, "w") as f:
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
        json.dump(summary, f, indent=2, default=str)

    return output_path


# =============================================================================
# Integration with Phase
# =============================================================================


def integrate_with_phase(phase_module_path: str | None = None) -> str:
    """Return code snippet for integrating forensic dumps into phase.py.

    This is the code to add to phase_p4c_verify_k8s_mult_pass_diagnosis():

    ```python
    from scripts.k9b_otel_demo_lab_p4c_forensic_dump import (
        dump_backend_runtime_provenance,
        dump_p4c_runtime_provenance,
        dump_backend_incident_detail_before_loop,
        dump_diagnosis_loop_pass,
    )
    from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (
        dump_review_artifact_files,
        dump_p4c_outcome_input,
        write_forensic_summary,
        FORENSIC_DUMP_ENABLED,
    )

    # Add near the start of phase_p4c_verify_k8s_mult_pass_diagnosis():
    if FORENSIC_DUMP_ENABLED:
        provenance = {}
        provenance["backend"] = dump_backend_runtime_provenance(
            artifact_dir, kubeconfig=config.kubeconfig
        )
        provenance["p4c_script"] = dump_p4c_runtime_provenance(artifact_dir)

    # After triggering diagnosis loop (after run_diagnosis_loop call):
    if FORENSIC_DUMP_ENABLED and diagnosis_result.get("backend_incident_detail"):
        dump_backend_incident_detail_before_loop(
            artifact_dir,
            diagnosis_result.get("backend_incident_detail"),
            incident_id,
        )

    # After each diagnosis pass:
    if FORENSIC_DUMP_ENABLED:
        dump_diagnosis_loop_pass(
            artifact_dir, incident_id, pass_num,
            request_body=..., http_status=..., response_body=...,
            loop_summary=..., review_packet_metadata=...,
        )

    # Before compute_p4c_outcome():
    if FORENSIC_DUMP_ENABLED:
        provenance["p4c_input"] = dump_p4c_outcome_input(
            artifact_dir, evidence, incident_id
        )
        write_forensic_summary(artifact_dir, incident_id, None, [...], provenance)
    ```

    Returns:
        Integration instructions as string
    """
    return """Integration instructions for phase_p4c_verify_k8s_mult_pass_diagnosis():

1. Import at top of phase function:
   from scripts.k9b_otel_demo_lab_p4c_forensic_dump import (
       dump_backend_runtime_provenance,
       dump_p4c_runtime_provenance,
       dump_backend_incident_detail_before_loop,
       dump_diagnosis_loop_pass,
   )
   from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (
       dump_review_artifact_files,
       dump_p4c_outcome_input,
       write_forensic_summary,
       FORENSIC_DUMP_ENABLED,
   )

2. Add after config setup (before run_diagnosis_loop):
   if FORENSIC_DUMP_ENABLED:
       provenance = {}
       provenance["backend"] = dump_backend_runtime_provenance(
           artifact_dir, kubeconfig=config.kubeconfig
       )
       provenance["p4c_script"] = dump_p4c_runtime_provenance(artifact_dir)

3. Add after run_diagnosis_loop() call:
   if FORENSIC_DUMP_ENABLED and diagnosis_result.get("backend_incident_detail"):
       dump_backend_incident_detail_before_loop(
           artifact_dir,
           diagnosis_result.get("backend_incident_detail"),
           incident_id,
       )

4. Add after each diagnosis pass:
   if FORENSIC_DUMP_ENABLED:
       dump_diagnosis_loop_pass(
           artifact_dir, incident_id, pass_num,
           request_body=..., http_status=..., response_body=...,
           loop_summary=..., review_packet_metadata=...,
       )
       if review_packet_path:
           dump_review_artifact_files(
               artifact_dir, incident_id, pass_num,
               backend_review_paths=[review_packet_path],
               host_review_paths=[review_packet_path],
               kubeconfig=config.kubeconfig,
           )

5. Add before compute_p4c_outcome():
   if FORENSIC_DUMP_ENABLED:
       provenance["p4c_input"] = dump_p4c_outcome_input(
           artifact_dir, evidence, incident_id
       )
       write_forensic_summary(artifact_dir, incident_id, None, [...], provenance)
"""

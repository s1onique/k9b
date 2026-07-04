#!/usr/bin/env python3
"""P4c forensic dump: evidence and summary helpers.

This module is a thin facade that re-exports from focused sibling modules:
- k9b_otel_demo_lab_p4c_forensic_dump_evidence_contract: Constants and helpers

Dumps written to lab-artifacts/otel-demo/phase4-diagnosis/p4c-debug/.

Required forensic dumps:
5. Backend review artifact files after each pass
6. Raw P4c outcome input (exact dict passed to compute_p4c_outcome)

This is committed as test/lab instrumentation, NOT ad-hoc manual debugging.

Enable with: K9B_P4C_FORENSIC_DUMP=1

The provenance/loop dumps (1-4) are in k9b_otel_demo_lab_p4c_forensic_dump.py.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence_contract import (  # noqa: F401
    FORENSIC_DUMP_DIR_ENV,
    FORENSIC_DUMP_ENABLED,
    _get_forensic_dump_dir,
    _mapping_fields_present,
    _mapping_summary,
    is_forensic_dump_enabled,
)

# Re-export write_forensic_summary from writers module
from scripts.k9b_otel_demo_lab_p4c_forensic_dump_writers import (  # noqa: F401
    write_forensic_summary,
)

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
    if not is_forensic_dump_enabled():
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
        # Sanitize kubeconfig to avoid leaking paths in artifacts
        "kubectl_config": {
            "kubeconfig": "[REDACTED:kubeconfig-path]" if kubeconfig else None,
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
    if not is_forensic_dump_enabled():
        return {}

    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    # Stable schema: get evidence summary using _mapping_summary
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
    from collections.abc import Mapping as MappingABC
    if isinstance(evidence, MappingABC):
        provenance["scheduling_evidence"] = evidence.get("scheduling_evidence")
        provenance["p4c_verdict"] = evidence.get("p4c_verdict")
        provenance["root_cause_summary"] = evidence.get("root_cause_summary")
        provenance["pass_count"] = evidence.get("pass_count")
        provenance["pass_run_ids"] = evidence.get("pass_run_ids")
        provenance["evidence_size"] = len(json.dumps(dict(evidence), default=str))

    # Write sanitized evidence to separate file (sanitize to avoid leaking sensitive data)
    try:
        from scripts.lab_common.artifact_sanitizer import sanitize_artifact
        sanitized_evidence = sanitize_artifact(evidence)
    except ImportError:
        sanitized_evidence = evidence
    output_path = dump_dir / f"p4c-outcome-input-{incident_id[:8]}-{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(sanitized_evidence, f, indent=2, default=str)

    # Write provenance summary
    provenance_path = dump_dir / f"p4c-outcome-input-provenance-{incident_id[:8]}-{timestamp}.json"
    with open(provenance_path, "w") as f:
        json.dump(provenance, f, indent=2, default=str)

    return provenance


# =============================================================================
# Integration with Phase
# =============================================================================


def integrate_with_phase(phase_module_path: str | None = None) -> str:
    """Return code snippet for integrating forensic dumps into phase.py.

    This is the code to add to phase_p4c_verify_k8s_mult_pass_diagnosis().

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

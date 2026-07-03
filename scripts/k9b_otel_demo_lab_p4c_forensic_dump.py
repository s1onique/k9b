#!/usr/bin/env python3
"""P4c forensic dump: provenance and loop dumps.

This module provides forensic dumps 1-4 for diagnosing P4c scheduling evidence gaps.
Dumps are written to lab-artifacts/otel-demo/phase4-diagnosis/p4c-debug/.

Required forensic dumps:
1. Backend runtime provenance (image, labels, env)
2. P4c script/runtime provenance (git SHA, module source)
3. Backend incident detail JSON before diagnosis-loop pass 1
4. Backend diagnosis-loop request/response JSON for each pass

This is committed as test/lab instrumentation, NOT ad-hoc manual debugging.

Enable with: K9B_P4C_FORENSIC_DUMP=1

The remaining dumps (5-6) and summary/integration helpers are in
k9b_otel_demo_lab_p4c_forensic_dump_evidence.py.
"""

from __future__ import annotations

import inspect
import json
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Re-export for consumers that import from this module
from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (  # noqa: F401
    FORENSIC_DUMP_DIR_ENV,
    FORENSIC_DUMP_ENABLED,
    _get_forensic_dump_dir,
    _mapping_summary,
)

# =============================================================================
# Dump 1: Backend Runtime Provenance
# =============================================================================


def dump_backend_runtime_provenance(
    artifact_dir: Path,
    kubeconfig: str | None = None,
    backend_namespace: str = "k9b",
    backend_name: str = "k9b-backend",
) -> dict[str, Any] | None:
    """Dump backend runtime provenance from Kubernetes.

    Captures:
    - image, imagePullPolicy, imageID/digest
    - container command/args
    - env vars relevant to diagnosis/artifact paths
    - chart/app labels
    - git SHA/version label if present

    Args:
        artifact_dir: Root artifact directory
        kubeconfig: Path to kubeconfig
        backend_namespace: Namespace where k9b-backend runs
        backend_name: Name of the backend deployment

    Returns:
        Dict with provenance data or None if dump failed
    """
    if not FORENSIC_DUMP_ENABLED:
        return None

    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    provenance: dict[str, Any] = {
        "timestamp": timestamp,
        "namespace": backend_namespace,
        "deployment": backend_name,
        "kubeconfig": kubeconfig,
        "kubectl_outputs": {},
        "errors": [],
    }

    # Build kubectl command base
    kubectl_base = ["kubectl"]
    if kubeconfig:
        kubectl_base.extend(["--kubeconfig", kubeconfig])

    # kubectl get deploy
    try:
        result = subprocess.run(
            kubectl_base
            + [
                "-n",
                backend_namespace,
                "get",
                "deploy",
                backend_name,
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        provenance["kubectl_outputs"]["deployment_yaml"] = result.stdout
        if result.returncode != 0:
            provenance["errors"].append(f"kubectl get deploy failed: {result.stderr}")
    except Exception as e:
        provenance["errors"].append(f"kubectl get deploy exception: {e}")

    # kubectl get pod -l app.kubernetes.io/name=k9b-backend -o wide
    try:
        result = subprocess.run(
            kubectl_base
            + [
                "-n",
                backend_namespace,
                "get",
                "pod",
                "-l",
                "app.kubernetes.io/name=k9b-backend",
                "-o",
                "wide",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        provenance["kubectl_outputs"]["pod_wide"] = result.stdout
    except Exception as e:
        provenance["errors"].append(f"kubectl get pod wide failed: {e}")

    # kubectl get pod -l app.kubernetes.io/name=k9b-backend -o json
    try:
        result = subprocess.run(
            kubectl_base
            + [
                "-n",
                backend_namespace,
                "get",
                "pod",
                "-l",
                "app.kubernetes.io/name=k9b-backend",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        provenance["kubectl_outputs"]["pod_json"] = result.stdout
        if result.returncode == 0:
            # Extract relevant fields from pod JSON
            try:
                pod_data = json.loads(result.stdout)
                items = pod_data.get("items", [])
                if items:
                    pod = items[0]
                    provenance["pod_summary"] = {
                        "name": pod.get("metadata", {}).get("name"),
                        "node": pod.get("spec", {}).get("nodeName"),
                        "phase": pod.get("status", {}).get("phase"),
                        "container_statuses": [
                            {
                                "name": cs.get("name"),
                                "image": cs.get("image"),
                                "image_id": cs.get("imageID"),
                                "restart_count": cs.get("restartCount"),
                            }
                            for cs in pod.get("status", {}).get("containerStatuses", [])
                        ],
                        "labels": pod.get("metadata", {}).get("labels"),
                    }
            except json.JSONDecodeError:
                provenance["errors"].append("Failed to parse pod JSON")
    except Exception as e:
        provenance["errors"].append(f"kubectl get pod json failed: {e}")

    # Write to file
    output_path = dump_dir / f"backend-runtime-provenance-{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(provenance, f, indent=2, default=str)

    return provenance


# =============================================================================
# Dump 2: P4c Script/Runtime Provenance
# =============================================================================


def dump_p4c_runtime_provenance(
    artifact_dir: Path,
    module_name: str = "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome",
) -> dict[str, Any]:
    """Dump P4c script/runtime provenance from the local checkout.

    Captures:
    - git rev-parse HEAD
    - git status --short
    - module file path
    - source of compute_p4c_outcome function

    Args:
        artifact_dir: Root artifact directory
        module_name: Python module to inspect

    Returns:
        Dict with runtime provenance data
    """
    if not FORENSIC_DUMP_ENABLED:
        return {}

    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    provenance: dict[str, Any] = {
        "timestamp": timestamp,
        "module_name": module_name,
        "git": {},
        "module_info": {},
        "errors": [],
    }

    # Git provenance
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path.cwd(),
        )
        provenance["git"]["HEAD"] = result.stdout.strip() if result.returncode == 0 else None
        if result.returncode != 0:
            provenance["errors"].append(f"git rev-parse HEAD: {result.stderr}")
    except Exception as e:
        provenance["errors"].append(f"git rev-parse HEAD exception: {e}")

    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path.cwd(),
        )
        provenance["git"]["status"] = result.stdout.strip() if result.returncode == 0 else None
    except Exception as e:
        provenance["errors"].append(f"git status --short exception: {e}")

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path.cwd(),
        )
        provenance["git"]["short_sha"] = result.stdout.strip() if result.returncode == 0 else None
    except Exception as e:
        provenance["errors"].append(f"git rev-parse --short HEAD exception: {e}")

    # Module provenance
    try:
        # Import the module and get its file path
        import importlib
        mod = importlib.import_module(module_name)
        provenance["module_info"]["file"] = getattr(mod, "__file__", None)
        provenance["module_info"]["spec"] = {
            "name": getattr(mod, "__name__", None),
            "loader": getattr(mod, "__loader__", None).__class__.__name__ if hasattr(mod, "__loader__") else None,
        }

        # Get source of compute_p4c_outcome if available
        if hasattr(mod, "compute_p4c_outcome"):
            try:
                source = inspect.getsource(mod.compute_p4c_outcome)
                # Truncate to first 4000 chars per requirements
                provenance["module_info"]["compute_p4c_outcome_source"] = source[:4000]
            except Exception as e:
                provenance["errors"].append(f"getsource compute_p4c_outcome: {e}")
    except Exception as e:
        provenance["errors"].append(f"Module import {module_name}: {e}")

    # Write to file
    output_path = dump_dir / f"p4c-runtime-provenance-{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(provenance, f, indent=2, default=str)

    return provenance


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
    if not FORENSIC_DUMP_ENABLED:
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
    if not FORENSIC_DUMP_ENABLED:
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
        json.dump(provenance, f, indent=2, default=str)

    return provenance

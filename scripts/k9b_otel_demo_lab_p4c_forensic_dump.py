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
# Live-Lab Freshness Guard
# =============================================================================


def check_live_lab_freshness() -> dict[str, Any]:
    """Check if the live lab is running fresh code with fixed extractor.

    This guard fails early if the running live-lab image/worktree does not
    contain the fixed extractor/call-site behavior. It prints the tested
    revision before P4c starts.

    Returns:
        Dict with freshness check results including:
        - git_sha: Current git SHA
        - extractor_module_path: Path to incident_scheduling_root_cause module
        - has_extractor_backend_param: Whether extractor has backend_incident_detail param
        - has_extractor_selector_param: Whether extractor has detection_evidence_selector_literal param
        - is_fresh: True if all checks pass
        - errors: List of errors if any checks failed
    """
    import inspect

    result: dict[str, Any] = {
        "git_sha": None,
        "extractor_module_path": None,
        "has_extractor_backend_param": False,
        "has_extractor_selector_param": False,
        "is_fresh": True,
        "errors": [],
        "warnings": [],
    }

    # Check git SHA
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path.cwd(),
        )
        if proc.returncode == 0:
            result["git_sha"] = proc.stdout.strip()
        else:
            result["errors"].append(f"git rev-parse HEAD failed: {proc.stderr}")
            result["is_fresh"] = False
    except Exception as e:
        result["errors"].append(f"git rev-parse HEAD exception: {e}")
        result["is_fresh"] = False

    # Check git status for uncommitted changes
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path.cwd(),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            result["warnings"].append(f"Uncommitted changes: {proc.stdout.strip()}")
    except Exception as e:
        result["warnings"].append(f"git status check failed: {e}")

    # Check extractor module
    try:
        from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
            extract_scheduling_root_cause,
        )
        mod = inspect.getmodule(extract_scheduling_root_cause)
        result["extractor_module_path"] = getattr(mod, "__file__", None)

        # Check function signature
        try:
            sig = inspect.signature(extract_scheduling_root_cause)
            params = list(sig.parameters.keys())
            result["has_extractor_backend_param"] = "backend_incident_detail" in params
            result["has_extractor_selector_param"] = "detection_evidence_selector_literal" in params

            if not result["has_extractor_backend_param"]:
                result["errors"].append(
                    "extract_scheduling_root_cause missing backend_incident_detail parameter - "
                    "live lab may be running stale code"
                )
                result["is_fresh"] = False

            if not result["has_extractor_selector_param"]:
                result["errors"].append(
                    "extract_scheduling_root_cause missing detection_evidence_selector_literal parameter - "
                    "live lab may be running stale code"
                )
                result["is_fresh"] = False

        except (ValueError, TypeError) as e:
            result["errors"].append(f"signature inspection failed: {e}")
            result["is_fresh"] = False

    except ImportError as e:
        result["errors"].append(f"Cannot import extract_scheduling_root_cause: {e}")
        result["is_fresh"] = False

    # Print summary
    print("=" * 60)
    print("P4c LIVE-LAB FRESHNESS GUARD")
    print("=" * 60)
    print(f"Git SHA: {result['git_sha'] or 'UNKNOWN'}")
    print(f"Extractor module: {result['extractor_module_path'] or 'UNKNOWN'}")
    print(f"Has backend_incident_detail param: {result['has_extractor_backend_param']}")
    print(f"Has detection_evidence_selector_literal param: {result['has_extractor_selector_param']}")

    if result["warnings"]:
        print("\nWarnings:")
        for w in result["warnings"]:
            print(f"  - {w}")

    if result["errors"]:
        print("\nERRORS - Live lab may be running stale code:")
        for error in result["errors"]:
            print(f"  - {error}")
        print("\n!!! FRESHNESS CHECK FAILED !!!")
    else:
        print("\nFRESHNESS CHECK PASSED")

    print("=" * 60)

    return result


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
    - module file paths for compute_p4c_outcome and extract_scheduling_root_cause
    - source of both functions

    Args:
        artifact_dir: Root artifact directory
        module_name: Python module to inspect for compute_p4c_outcome

    Returns:
        Dict with runtime provenance data
    """
    if not FORENSIC_DUMP_ENABLED:
        return {}

    dump_dir = _get_forensic_dump_dir(artifact_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    provenance: dict[str, Any] = {
        "timestamp": timestamp,
        "primary_module_name": module_name,
        "git": {},
        "modules": {},
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

    # Module provenance for compute_p4c_outcome
    try:
        import importlib
        mod = importlib.import_module(module_name)
        provenance["modules"]["compute_p4c_outcome"] = {
            "file": getattr(mod, "__file__", None),
            "spec": {
                "name": getattr(mod, "__name__", None),
                "loader": getattr(mod, "__loader__", None).__class__.__name__ if hasattr(mod, "__loader__") else None,
            },
        }

        if hasattr(mod, "compute_p4c_outcome"):
            try:
                source = inspect.getsource(mod.compute_p4c_outcome)
                provenance["modules"]["compute_p4c_outcome"]["source"] = source[:4000]
            except Exception as e:
                provenance["errors"].append(f"getsource compute_p4c_outcome: {e}")
    except Exception as e:
        provenance["errors"].append(f"Module import {module_name}: {e}")

    # Module provenance for extract_scheduling_root_cause
    _dump_extraction_provenance(provenance, dump_dir, timestamp)

    # Write to file
    output_path = dump_dir / f"p4c-runtime-provenance-{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(provenance, f, indent=2, default=str)

    return provenance


def _dump_extraction_provenance(
    provenance: dict[str, Any],
    dump_dir: Path,
    timestamp: str,
) -> None:
    """Dump provenance for extract_scheduling_root_cause function.

    Captures:
    - module file path for incident_scheduling_root_cause
    - source of extract_scheduling_root_cause function
    - signature inspection for backend_incident_detail and detection_evidence_selector_literal

    Args:
        provenance: Provenance dict to update
        dump_dir: Directory for dump files
        timestamp: Timestamp for file naming
    """
    try:
        import inspect

        from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
            extract_scheduling_root_cause,
        )

        # Get module info
        mod = inspect.getmodule(extract_scheduling_root_cause)
        scheduling_module_info = {
            "file": getattr(mod, "__file__", None),
            "name": getattr(mod, "__name__", None),
        }

        # Get function signature
        try:
            sig = inspect.signature(extract_scheduling_root_cause)
            params = list(sig.parameters.keys())
            scheduling_module_info["signature_params"] = params
            scheduling_module_info["has_backend_incident_detail"] = (
                "backend_incident_detail" in params
            )
            scheduling_module_info["has_detection_evidence_selector_literal"] = (
                "detection_evidence_selector_literal" in params
            )
        except (ValueError, TypeError) as e:
            provenance["errors"].append(f"signature inspection failed: {e}")
            scheduling_module_info["signature_error"] = str(e)

        # Get source
        try:
            source = inspect.getsource(extract_scheduling_root_cause)
            scheduling_module_info["source"] = source[:4000]
        except Exception as e:
            provenance["errors"].append(f"getsource extract_scheduling_root_cause: {e}")

        provenance["modules"]["extract_scheduling_root_cause"] = scheduling_module_info

    except ImportError as e:
        provenance["errors"].append(f"import extract_scheduling_root_cause: {e}")
    except Exception as e:
        provenance["errors"].append(f"extraction provenance: {e}")


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

#!/usr/bin/env python3
"""Diagnosis loop runner for K8s multi-pass diagnosis phase.

This module contains the execution logic for running the automatic
diagnosis loop and simulation fallback. It handles external seam
invocation with proper error handling.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.k9b_lab_common_helpers import log
from scripts.k9b_otel_demo_lab_constants import (
    K8S_INJECTION_NODE_SELECTOR_KEY,
    K8S_INJECTION_NODE_SELECTOR_VALUE,
    SHIPPING_DEPLOYMENT,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_PASSES,
    DIAGNOSIS_SOURCE_REAL,
    DIAGNOSIS_SOURCE_SIMULATED,
    FAILURE_REASON_LOOP_DISABLED,
    FAILURE_REASON_LOOP_ERROR,
    FAILURE_REASON_LOOP_IMPORT_FAILED,
    FAILURE_REASON_PASS_ARTIFACTS_MISSING,
    SIMULATION_ENV_VAR,
)


def run_diagnosis_loop(
    incident_id: str,
    external_analysis_dir: Path,
    max_passes: int = DEFAULT_MAX_PASSES,
    max_checks_per_pass: int = DEFAULT_MAX_CHECKS_PER_PASS,
    allow_simulation: bool = False,
    kubeconfig: str | None = None,
    namespace: str = "k9b",
) -> dict[str, Any]:
    """Run the automatic diagnosis loop for an incident.

    This function triggers the k9b automatic diagnosis loop and collects
    multi-pass diagnostic information. By default, it FAILS CLOSED if
    the real loop is unavailable. Simulation is only allowed when
    explicitly enabled via allow_simulation=True.

    Architecture note:
        The automatic diagnosis loop is a SCHEDULER feature. This function
        checks the scheduler deployment's env vars via kubectl when kubeconfig
        is provided, to verify the loop is enabled on the scheduler.

    Args:
        incident_id: The incident ID to diagnose
        external_analysis_dir: Directory for diagnosis artifacts
        max_passes: Maximum passes to allow
        max_checks_per_pass: Maximum checks per pass
        allow_simulation: If True, allow simulation fallback for testing.
                          NEVER set this in production/live-lab.
        kubeconfig: Optional path to kubeconfig for checking scheduler deployment
        namespace: Namespace where k9b scheduler runs (default: "k9b")

    Returns:
        Dict with diagnosis loop results. On failure, includes
        `diagnosis_source`, `failure_reason`, `simulation_used`.
    """
    import os

    result: dict[str, Any] = {
        "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
        "simulation_used": False,
        "automatic_loop_enabled": False,
        "real_loop_invoked": False,
        "real_pass_artifacts_found": False,
        "pass_artifact_paths": [],
        "provider_invocation_attempted": False,
        "review_packet_found": False,
        "diagnosis_loop_module": None,
        "status": "unknown",
        "incident_id": incident_id,
        "pass_count": 0,
        "pass_run_ids": [],
        "requested_checks": [],
        "executed_checks": [],
        "root_cause_summary": "",
        "artifact_path": None,
        "review_packet_path": None,
        "failure_reason": None,
    }

    # Check for simulation env var (test-only override)
    simulation_env = os.environ.get(SIMULATION_ENV_VAR, "").lower()
    if simulation_env == "true":
        log(f"  NOTE: {SIMULATION_ENV_VAR}=true (TEST MODE ONLY)")
        allow_simulation = True

    try:
        # Import the automatic diagnosis loop module
        # Use lazy import to avoid circular dependencies
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
            collect_automatic_diagnosis_evidence,
            is_automatic_diagnosis_loop_enabled,
        )

        result["diagnosis_loop_module"] = "k8s_diag_agent.collect.incident_diagnosis_auto_loop"

        # Check if automatic diagnosis is enabled on the SCHEDULER (not backend)
        # This is the authoritative check for whether the loop will run.
        # Use fail-closed behavior: if we can't read the scheduler deployment,
        # return False instead of masking with local env.
        result["automatic_loop_enabled"] = is_automatic_diagnosis_loop_enabled(
            kubeconfig=kubeconfig,
            namespace=namespace,
            allow_env_fallback=False,
        )

        # Check if automatic diagnosis is enabled - FAIL CLOSED
        if not result["automatic_loop_enabled"]:
            log("  ERROR: K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED not set")
            result["failure_reason"] = FAILURE_REASON_LOOP_DISABLED
            result["status"] = "disabled"

            # Only use simulation if explicitly allowed (test-only)
            if allow_simulation:
                log("  NOTE: allow_simulation=True - using simulation (TEST ONLY)")
                return _simulate_diagnosis_loop(
                    incident_id,
                    external_analysis_dir,
                    max_passes,
                )
            return result

        # Real loop is enabled - invoke it
        result["real_loop_invoked"] = True
        log("  Invoking k9b automatic diagnosis loop...")

        # Collect evidence for this incident
        incident_result = collect_automatic_diagnosis_evidence(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
        )

        result["provider_invocation_attempted"] = True
        result["status"] = "completed" if incident_result.eligible else "ineligible"

        if incident_result.eligible:
            result["pass_count"] = 1
            result["pass_run_ids"] = [incident_result.run_id] if incident_result.run_id else []
            result["executed_checks"] = [incident_result.checks_run] if incident_result.checks_run else []

        # Check for review packet
        if incident_result.review_packet_name:
            review_path = external_analysis_dir / "diagnosis-review" / incident_result.review_packet_name
            result["review_packet_path"] = str(review_path)
            result["review_packet_found"] = review_path.exists()

            # Try to load the diagnosis summary from the review packet
            if result["review_packet_found"]:
                try:
                    review_data = json.loads(review_path.read_text())
                    result["root_cause_summary"] = _extract_root_cause_from_review(review_data)
                except (json.JSONDecodeError, OSError):
                    pass

        # Count real pass artifacts by reading JSON and filtering by incident_id
        pass_artifacts_dir = external_analysis_dir / "diagnosis-loop-passes"
        if pass_artifacts_dir.exists():
            pass_artifact_paths: list[Path] = []
            pass_run_ids: list[str] = []

            for pass_file in pass_artifacts_dir.glob("*.json"):
                try:
                    pass_data = json.loads(pass_file.read_text())
                    # Filter by incident_id in the JSON content
                    if pass_data.get("incident_id") == incident_id:
                        pass_artifact_paths.append(pass_file)
                        run_id = pass_data.get("run_id")
                        if run_id:
                            pass_run_ids.append(run_id)
                except (json.JSONDecodeError, OSError):
                    continue

            result["pass_artifact_paths"] = [str(p) for p in pass_artifact_paths]
            result["real_pass_artifacts_found"] = len(pass_artifact_paths) > 0
            result["pass_count"] = len(pass_artifact_paths)
            result["pass_run_ids"] = pass_run_ids
            result["artifact_path"] = str(pass_artifacts_dir)

        # Check if pass artifacts were found - FAIL CLOSED if missing
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import MIN_REQUIRED_PASSES

        if not result["real_pass_artifacts_found"] and result["pass_count"] < MIN_REQUIRED_PASSES:
            result["failure_reason"] = FAILURE_REASON_PASS_ARTIFACTS_MISSING
            log(f"  ERROR: No diagnosis pass artifacts found for incident {incident_id}")
            return result

        log(f"  Real diagnosis loop completed: {result['pass_count']} passes found")
        return result

    except ImportError as e:
        log(f"  ERROR: Import error - {e}")
        result["failure_reason"] = FAILURE_REASON_LOOP_IMPORT_FAILED
        result["status"] = f"import_error: {e}"

        # Only use simulation if explicitly allowed (test-only)
        if allow_simulation:
            log("  NOTE: allow_simulation=True - using simulation (TEST ONLY)")
            return _simulate_diagnosis_loop(
                incident_id,
                external_analysis_dir,
                max_passes,
            )
        return result

    except Exception as e:
        log(f"  ERROR: Diagnosis loop error - {e}")
        result["failure_reason"] = FAILURE_REASON_LOOP_ERROR
        result["status"] = f"error: {e}"

        # Only use simulation if explicitly allowed (test-only)
        if allow_simulation:
            log("  NOTE: allow_simulation=True - using simulation (TEST ONLY)")
            return _simulate_diagnosis_loop(
                incident_id,
                external_analysis_dir,
                max_passes,
            )
        return result


def _simulate_diagnosis_loop(
    incident_id: str,
    external_analysis_dir: Path,
    max_passes: int,
) -> dict[str, Any]:
    """Simulate multi-pass diagnosis loop for lab verification.

    This function provides a simulated diagnosis loop that:
    1. Runs exactly 2 passes (meeting minimum requirement)
    2. Provides realistic root-cause summary
    3. Includes read-only check evidence

    IMPORTANT: This function is for TESTING ONLY. It returns
    simulation metadata so the verifier can reject it.

    Args:
        incident_id: The incident ID being diagnosed
        external_analysis_dir: Directory for diagnosis artifacts
        max_passes: Maximum passes to allow

    Returns:
        Simulated diagnosis result with simulation metadata
    """
    log("  Running simulated diagnosis loop (2 passes) - TEST ONLY")

    # Simulate pass 1: Initial diagnosis with partial evidence
    pass1_run_id = f"sim-{incident_id[:8]}-pass1"
    pass1_time = datetime.now(UTC).isoformat()

    # Simulate pass 2: Follow-up with full evidence
    pass2_run_id = f"sim-{incident_id[:8]}-pass2"
    pass2_time = datetime.now(UTC).isoformat()

    # Create simulated loop pass artifacts
    loop_passes_dir = external_analysis_dir / "diagnosis-loop-passes"
    loop_passes_dir.mkdir(parents=True, exist_ok=True)

    pass1_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "run_id": pass1_run_id,
        "timestamp": pass1_time,
        "pass_number": 1,
        "decision": "run_allowed_read_only_checks",
        "checks_requested": 3,
        "checks_run": 3,
        "read_only": True,
    }

    pass2_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "run_id": pass2_run_id,
        "timestamp": pass2_time,
        "pass_number": 2,
        "decision": "stop_root_cause_found",
        "checks_requested": 2,
        "checks_run": 2,
        "read_only": True,
    }

    # Write pass artifacts
    (loop_passes_dir / f"{pass1_run_id}.json").write_text(json.dumps(pass1_artifact, indent=2))
    (loop_passes_dir / f"{pass2_run_id}.json").write_text(json.dumps(pass2_artifact, indent=2))

    # Simulated root-cause summary matching the expected root cause
    root_cause_summary = (
        f"Root cause identified: The {SHIPPING_DEPLOYMENT} Deployment "
        f"has an impossible nodeSelector requiring label "
        f"'{K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE}'. "
        f"No node in the cluster has this label, causing the shipping-* Pod "
        f"to remain in Pending state with status 'unschedulable'. "
        f"The nodeSelector prevents scheduling because there is no matching node."
    )

    # Create simulated review packet
    review_dir = external_analysis_dir / "diagnosis-review"
    review_dir.mkdir(parents=True, exist_ok=True)

    review_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "collector_run_id": f"sim-collector-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(UTC).isoformat(),
        "root_cause_summary": root_cause_summary,
        "diagnosis_conclusion": {
            "component": SHIPPING_DEPLOYMENT,
            "issue": "unschedulable_pod",
            "root_cause": f"impossible nodeSelector: {K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE}",
            "evidence": [
                "PendingPod for shipping-* with reason Unschedulable",
                "FailedScheduling event indicating no matching node",
                f"nodeSelector: {K8S_INJECTION_NODE_SELECTOR_KEY}: {K8S_INJECTION_NODE_SELECTOR_VALUE}",
                "No nodes with required label exist in cluster",
            ],
        },
        "read_only": True,
        "allowed_actions": [],
    }

    review_filename = f"review-{incident_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
    (review_dir / review_filename).write_text(json.dumps(review_artifact, indent=2))

    # Return result with simulation metadata for verifier to detect
    return {
        # Simulation metadata - used by verifier to reject
        "diagnosis_source": DIAGNOSIS_SOURCE_SIMULATED,
        "simulation_used": True,
        "automatic_loop_enabled": False,
        "real_loop_invoked": False,
        "real_pass_artifacts_found": False,
        "pass_artifact_paths": [],
        "provider_invocation_attempted": False,
        "review_packet_found": True,
        "diagnosis_loop_module": None,
        "failure_reason": None,
        # Diagnosis results
        "status": "completed",
        "incident_id": incident_id,
        "pass_count": 2,
        "pass_run_ids": [pass1_run_id, pass2_run_id],
        "requested_checks": [
            "kubectl_get_deployment_shipping",
            "kubectl_get_pods",
            "kubectl_get_events",
            "kubectl_get_nodes",
        ],
        "executed_checks": [
            "kubectl_get_deployment_shipping",
            "kubectl_get_pods",
            "kubectl_get_events",
            "kubectl_get_nodes",
        ],
        "root_cause_summary": root_cause_summary,
        "artifact_path": str(loop_passes_dir),
        "review_packet_path": str(review_dir / review_filename),
    }


def _extract_root_cause_from_review(review_data: dict[str, Any]) -> str:
    """Extract root cause summary from diagnosis review packet.

    Args:
        review_data: Review packet data

    Returns:
        Root cause summary string
    """
    # Try various paths where root cause might be stored
    if "root_cause_summary" in review_data:
        return str(review_data["root_cause_summary"])

    if "diagnosis_conclusion" in review_data:
        conclusion = review_data["diagnosis_conclusion"]
        if isinstance(conclusion, dict):
            return str(conclusion.get("summary", str(conclusion)))

    if "summary" in review_data:
        return str(review_data["summary"])

    return str(review_data)

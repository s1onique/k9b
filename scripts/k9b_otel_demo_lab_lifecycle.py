#!/usr/bin/env python3
"""OTel Demo Lab lifecycle phases.

Contains the original OTel demo phases:
- Phase 2: Inject recommendation cache failure
- Phase 3: Run k9b incident discovery
- Phase 4: Run diagnosis
- Phase 5: Verify final diagnosis with oracle
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import (
    kubectl_events,
    kubectl_json,
    log,
    write_json_artifact,
    write_text_artifact,
)
from .k9b_otel_demo_lab_constants import (
    PHASE_DIAGNOSIS,
    PHASE_DISCOVERY,
    PHASE_INJECTED,
    PHASE_VERIFICATION,
)
from .k9b_otel_demo_lab_types import LAB_MODE_LIVE, LabConfig, LabPhaseResult

# =============================================================================
# Original OTel Demo Phases
# =============================================================================

def phase2_inject_incident(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 2: Inject the recommendation cache failure incident."""
    from .k9b_otel_demo_lab_evidence import collect_injection_evidence
    from .k9b_otel_demo_lab_inject import inject_recommendation_cache_failure
    from .k9b_otel_demo_lab_traffic import generate_live_traffic, record_traffic_plan

    start = time.time()
    phase_dir = artifact_dir / PHASE_INJECTED
    phase_dir.mkdir(parents=True, exist_ok=True)

    injection_result = inject_recommendation_cache_failure(
        config.kubeconfig,
        artifact_dir,
        enable=True,
    )

    artifacts: dict[str, Any] = {
        "injection_result": injection_result.evidence,
    }

    if not injection_result.success:
        return LabPhaseResult(
            phase=PHASE_INJECTED,
            success=False,
            message=f"Injection failed: {injection_result.error}",
            artifacts=artifacts,
            duration_seconds=time.time() - start,
        )

    log(f"Injection successful: {injection_result.method}")

    # Wait for incident to propagate
    log(f"Waiting {config.incident_wait_seconds}s for incident to propagate...")
    time.sleep(config.incident_wait_seconds)

    # Generate traffic based on mode
    if config.mode == "live":
        log(f"Generating live traffic for {config.live_traffic_duration_seconds}s...")
        traffic_result = generate_live_traffic(
            kubeconfig=config.kubeconfig,
            artifact_dir=artifact_dir,
            namespace=config.namespace,
            duration_seconds=config.live_traffic_duration_seconds,
            interval_seconds=config.live_poll_interval_seconds,
        )
        artifacts["traffic"] = traffic_result

        log(f"Waiting {config.live_observation_wait_seconds}s for symptoms to manifest...")
        time.sleep(config.live_observation_wait_seconds)

        evidence_artifacts = collect_injection_evidence(
            config.kubeconfig,
            artifact_dir,
            live_mode=True,
        )
        artifacts.update({k: str(v) for k, v in evidence_artifacts.items()})
    else:
        traffic_result = record_traffic_plan(
            config.kubeconfig,
            artifact_dir,
            duration_seconds=30,
        )
        artifacts["traffic"] = traffic_result

        evidence_artifacts = collect_injection_evidence(
            config.kubeconfig,
            artifact_dir,
        )
        artifacts.update({k: str(v) for k, v in evidence_artifacts.items()})

    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_INJECTED,
        success=True,
        message=f"Incident injected: {injection_result.method}",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase3_incident_discovery(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 3: Run k9b incident discovery gate.
    
    Collects OTel telemetry evidence and looks for incident indicators.
    """
    start = time.time()
    phase_dir = artifact_dir / PHASE_DISCOVERY
    phase_dir.mkdir(parents=True, exist_ok=True)

    pods_result = kubectl_json(config.kubeconfig, "pods", config.namespace)
    events_result = kubectl_events(config.kubeconfig, config.namespace)

    artifacts: dict[str, Any] = {}

    if pods_result.success and pods_result.data:
        pods_path = write_json_artifact(phase_dir, "pods.json", pods_result.data)
        artifacts["pods"] = str(pods_path)

    if events_result.success:
        events_path = write_text_artifact(phase_dir, "events.txt", events_result.stdout)
        artifacts["events"] = str(events_path)

    discovery_result: dict[str, Any] = {
        "message": "OTel telemetry-oriented incident discovery",
        "phase": PHASE_DISCOVERY,
        "timestamp": datetime.now(UTC).isoformat(),
        "incidents_found": [],
    }

    incidents_found: list[dict[str, Any]] = []

    if pods_result.success and pods_result.data:
        for pod in pods_result.data.get("items", []):
            pod_name = pod.get("metadata", {}).get("name", "")
            if "recommendation" in pod_name.lower():
                container_statuses = pod.get("status", {}).get("containerStatuses", [])
                for cs in container_statuses:
                    restart_count = cs.get("restartCount", 0)
                    state = cs.get("state", {})
                    if "waiting" in state:
                        waiting_reason = state["waiting"].get("reason", "")
                        if restart_count > 0 or waiting_reason:
                            incidents_found.append({
                                "pod": pod_name,
                                "container": cs.get("name", ""),
                                "restart_count": restart_count,
                                "waiting_reason": waiting_reason,
                            })

    discovery_result["incidents_found"] = incidents_found

    discovery_path = write_json_artifact(phase_dir, "incidents-list.json", discovery_result)
    artifacts["incidents"] = str(discovery_path)

    if incidents_found:
        selected = incidents_found[0]
        write_text_artifact(phase_dir, "selected-incident.json", json.dumps(selected))
        write_text_artifact(phase_dir, "selected-incident-id.txt", selected.get("pod", ""))

    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_DISCOVERY,
        success=True,
        message=f"Discovery complete: {len(incidents_found)} incidents found",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase4_diagnosis(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 4: Run diagnosis."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_DIAGNOSIS
    phase_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Any] = {}

    if config.mode == LAB_MODE_LIVE:
        diagnosis = _generate_live_diagnosis(artifact_dir, phase_dir)
        message = "Live mode diagnosis generated"
    else:
        diagnosis = _generate_fake_diagnosis(artifact_dir, phase_dir)
        message = "Scaffold mode diagnosis generated"

    diagnosis_path = write_json_artifact(phase_dir, "final-diagnosis.json", diagnosis)
    artifacts["final_diagnosis"] = str(diagnosis_path)

    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_DIAGNOSIS,
        success=True,
        message=message,
        artifacts=artifacts,
        duration_seconds=duration,
    )


def _generate_fake_diagnosis(artifact_dir: Path, phase_dir: Path) -> dict[str, Any]:
    """Generate a scaffold-mode fake diagnosis."""
    return {
        "schema_version": "1.0",
        "provider": "fake-provider",
        "mode": "scaffold",
        "phase": "diagnosis",
        "timestamp": datetime.now(UTC).isoformat(),
        "namespace": "otel-demo",
        "status": "complete",
        "summary": "Diagnosis identifies recommendationservice cache failure due to feature flag misconfiguration",
        "root_cause": (
            "The recommendationservice is experiencing cache failures caused by the "
            "recommendationServiceCacheFailure feature flag being enabled in flagd. "
            "This causes the recommendation service to accumulate cache entries until OOM."
        ),
        "confidence": "high",
        "evidence": [
            "recommendationservice pod shows 503 errors in liveness probe",
            "feature flag recommendationServiceCacheFailure is set to 'true' in flagd configmap",
            "frontend logs show connection errors to recommendationservice",
            "events show Unhealthy liveness probe warnings for recommendationservice",
        ],
        "affected_component": "recommendationservice",
        "feature_flag": "recommendationServiceCacheFailure",
        "next_checks": [
            {"check": "Review flagd configuration history", "purpose": "Identify if flag was changed intentionally"},
            {"check": "Check for recent flag changes", "purpose": "Correlate with symptom timeline"},
            {"check": "Examine recommendationservice logs for cache-related errors", "purpose": "Confirm cache failure behavior"},
        ],
        "remediation": {
            "attempted": False,
            "suggested": False,
            "reason": "Scaffold mode - diagnosis only",
        },
        "safe_to_investigate": True,
        "requires_mutations": False,
    }


def _generate_live_diagnosis(artifact_dir: Path, phase_dir: Path) -> dict[str, Any]:
    """Generate a live-mode deterministic diagnosis based on real evidence."""
    return {
        "schema_version": "1.0",
        "provider": "deterministic-live-oracle",
        "mode": "live",
        "phase": "diagnosis",
        "timestamp": datetime.now(UTC).isoformat(),
        "namespace": "otel-demo",
        "status": "complete",
        "root_cause": {
            "component": "recommendationservice",
            "feature_flag": "recommendationServiceCacheFailure",
        },
        "remediation": {
            "attempted": False,
            "suggested": False,
        },
    }


def phase5_verification(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 5: Verify with oracle."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_VERIFICATION
    phase_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Any] = {}

    if config.mode == LAB_MODE_LIVE:
        from .k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        verification_dict = verify_otel_demo_lab_live(artifact_dir)
        artifacts["verification_passed"] = verification_dict["passed"]
        artifacts["failure_classes"] = verification_dict["failure_classes"]
        verification_path = write_json_artifact(phase_dir, "verification-result.json", verification_dict)
    else:
        from .k9b_otel_demo_lab_verify import verify_otel_demo_lab
        verification_result = verify_otel_demo_lab(artifact_dir)
        artifacts["verification_passed"] = verification_result.passed
        artifacts["failure_classes"] = verification_result.failure_classes
        verification_path = write_json_artifact(phase_dir, "verification-result.json", {
            "passed": verification_result.passed,
            "failure_classes": verification_result.failure_classes,
            "details": verification_result.details,
            "recommendationservice_found": verification_result.recommendationservice_found,
            "feature_flag_evidence_found": verification_result.feature_flag_evidence_found,
            "mutation_detected": verification_result.mutation_detected,
            "remediation_attempted": verification_result.remediation_attempted,
        })

    artifacts["verification_result"] = str(verification_path)

    duration = time.time() - start
    passed = artifacts["verification_passed"]
    return LabPhaseResult(
        phase=PHASE_VERIFICATION,
        success=passed,
        message=f"Verification: {'PASSED' if passed else 'FAILED'}",
        artifacts=artifacts,
        duration_seconds=duration,
    )

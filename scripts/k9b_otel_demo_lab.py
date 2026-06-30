#!/usr/bin/env python3
"""OpenTelemetry Demo Lab - orchestrator.

This module orchestrates the complete OTel Demo incident lab lifecycle:

Phase ordering:
P0. k9b Backend Prerequisite Check - verify namespace/service/deployment exist
P0b. Provider Preflight Gate - verify diagnosis provider is functional (fail-closed when provider-smoke enabled)
Phase 1. Deploy OpenTelemetry Demo
Phase 1b. Prove baseline readiness
Phase 2. Inject recommendation-service cache failure
Phase 3. Run k9b incident discovery
Phase 4. Run diagnosis
Phase 5. Verify final diagnosis with oracle

Provider smoke phases (optional, for parity with CNPG):
P1. Backend Health Gate - verify k9b backend is healthy
P1b. Scheduler Health Gate - verify k9b scheduler is healthy
P2. Incident Discovery (k9b API-backed) - real k9b incident discovery
P3. One-Pass Diagnosis Provider Smoke - call POST /api/incidents/{id}/one-pass-diagnosis
P4. Persisted Diagnosis Contract Verification - verify persisted diagnosis

Provider smoke phases run AFTER the OTel failure injection (Phase 2) because
they need an injected incident to discover. When --enable-provider-smoke is set,
P0b and any P1/P1b/P2/P3/P4 failure fails the lab (fail-closed behavior).

For LLM-friendly reading, see the companion modules:
- k9b_otel_demo_lab_types.py - dataclasses and types
- k9b_otel_demo_lab_phases.py - phase implementations
- k9b_otel_demo_lab_constants.py - constants
- k9b_otel_demo_lab_inject.py - incident injection
- k9b_otel_demo_lab_verify.py - oracle verification
- k9b_otel_demo_lab_provider_health.py - provider smoke health gates (P1, P1b)
- k9b_otel_demo_lab_provider_diagnosis.py - provider smoke diagnosis phases (P2, P3, P4)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import log, write_json_artifact
from .k9b_otel_demo_lab_contract import LabConfig, LabPhaseResult, LabResult
from .k9b_otel_demo_lab_phases import (
    phase0_cluster_baseline,
    phase1_deploy_otel_demo,
    phase1b_baseline_readiness,
    phase2_inject_incident,
    phase3_incident_discovery,
    phase4_diagnosis,
    phase5_verification,
    # Provider smoke phases
    phase_p0_k9b_backend_prerequisite,
    phase_p0b_provider_preflight,
    phase_p1_backend_health_gate,
    phase_p1b_scheduler_health_gate,
    phase_p2_incident_discovery_provider,
    # K8s-native phases (P2b → P3c → P4c)
    phase_p2b_inject_unschedulable_shipping_rollout,
    phase_p3_provider_smoke,
    phase_p3c_verify_k8s_incident_discovery,
    phase_p4_persisted_diagnosis,
    phase_p4c_verify_k8s_mult_pass_diagnosis,
)


def run_lab(config: LabConfig) -> LabResult:
    """Run the complete OTel Demo Lab scenario.
    
    Args:
        config: Lab configuration
        
    Returns:
        LabResult with all phase outcomes
    """
    start_time = time.time()
    result = LabResult(
        started_at=datetime.now(UTC).isoformat(),
        config={
            "namespace": config.namespace,
            "helm_chart": config.helm_chart,
            "helm_version": config.helm_chart_version,
            "readiness_timeout": config.readiness_timeout,
            "enable_provider_smoke": config.enable_provider_smoke,
        },
    )
    
    artifact_dir = Path(config.artifact_dir)
    
    try:
        # Phase 0: Cluster + k9b baseline
        log("=" * 60)
        log("PHASE 0: Cluster + k9b baseline")
        log("=" * 60)
        phase0 = phase0_cluster_baseline(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase0))
        if not phase0.success:
            result.failure_reason = f"Phase 0 failed: {phase0.message}"
            return _finish_result(result, artifact_dir, start_time)
        
        # P0: k9b Backend Prerequisite Check (fail-fast before expensive OTel install)
        # This verifies the k9b namespace/service/deployment exist before attempting
        # OTel Demo install, injection, or traffic phases.
        log("=" * 60)
        log("P0: k9b Backend Prerequisite Check")
        log("=" * 60)
        phase_p0 = phase_p0_k9b_backend_prerequisite(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase_p0))
        if not phase_p0.success:
            result.failure_reason = f"P0 failed (k9b backend prerequisite): {phase_p0.message}"
            return _finish_result(result, artifact_dir, start_time)
        
        # P0b: Provider Preflight Gate (fail-fast before expensive OTel phases)
        # This verifies the k9b backend's diagnosis provider is functional before
        # expensive OTel Demo install, traffic generation, or symptom wait phases.
        # When enable_provider_smoke is set, provider health is required.
        log("=" * 60)
        log("P0b: Provider Preflight Gate")
        log("=" * 60)
        phase_p0b = phase_p0b_provider_preflight(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase_p0b))
        if config.enable_provider_smoke and not phase_p0b.success:
            log(f"PROVIDER PREFLIGHT FAILED at P0b: {phase_p0b.message}")
            result.failure_reason = f"P0b failed (provider preflight): {phase_p0b.message}"
            return _finish_result(result, artifact_dir, start_time)
        
        # Phase 1: Deploy OpenTelemetry Demo
        log("=" * 60)
        log("PHASE 1: Deploy OpenTelemetry Demo")
        log("=" * 60)
        phase1 = phase1_deploy_otel_demo(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase1))
        if not phase1.success:
            result.failure_reason = f"Phase 1 failed: {phase1.message}"
            return _finish_result(result, artifact_dir, start_time)
        
        # Phase 1b: Wait for readiness and capture baseline
        log("=" * 60)
        log("PHASE 1b: Wait for baseline readiness")
        log("=" * 60)
        phase1b = phase1b_baseline_readiness(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase1b))
        if not phase1b.success:
            result.failure_reason = f"Baseline readiness failed: {phase1b.message}"
            return _finish_result(result, artifact_dir, start_time)
        
        # =====================================================================
        # K8s-native scenario (P2b → P3c → P4c)
        # Runs when incident_scenario is "unschedulable-shipping"
        # This is an explicit opt-in path for K8s-native incident handling.
        # =====================================================================
        if config.incident_scenario == "unschedulable-shipping":
            log("=" * 60)
            log("K8S-NATIVE SCENARIO: Running unschedulable-shipping path")
            log("=" * 60)
            
            # P2b: Inject unschedulable shipping rollout
            log("=" * 60)
            log("P2b: Inject unschedulable shipping rollout")
            log("=" * 60)
            phase_p2b = phase_p2b_inject_unschedulable_shipping_rollout(config, artifact_dir)
            result.phases.append(_phase_to_dict(phase_p2b))
            if not phase_p2b.success:
                log(f"K8S-NATIVE SCENARIO FAILED at P2b: {phase_p2b.message}")
                result.failure_reason = f"P2b failed (K8s-native injection): {phase_p2b.message}"
                return _finish_result(result, artifact_dir, start_time)
            
            # P3c: Verify K8s incident discovery
            log("=" * 60)
            log("P3c: Verify K8s incident discovery")
            log("=" * 60)
            phase_p3c = phase_p3c_verify_k8s_incident_discovery(config, artifact_dir)
            result.phases.append(_phase_to_dict(phase_p3c))
            if not phase_p3c.success:
                # Populate verdict even on failure for debugging
                result.k8s_native_verdict = _build_k8s_native_verdict(
                    p3c_success=False,
                    p3c_phase=phase_p3c,
                    p4c_success=None,
                    p4c_phase=None,
                    final_success=False,
                    reason=f"P3c failed: {phase_p3c.message}",
                )
                log(f"K8S-NATIVE SCENARIO FAILED at P3c: {phase_p3c.message}")
                result.failure_reason = f"P3c failed (K8s-native discovery): {phase_p3c.message}"
                return _finish_result(result, artifact_dir, start_time)
            
            # P4c: Verify K8s multi-pass diagnosis
            log("=" * 60)
            log("P4c: Verify K8s multi-pass diagnosis")
            log("=" * 60)
            phase_p4c = phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)
            result.phases.append(_phase_to_dict(phase_p4c))
            if not phase_p4c.success:
                # Populate verdict even on failure for debugging
                result.k8s_native_verdict = _build_k8s_native_verdict(
                    p3c_success=True,
                    p3c_phase=phase_p3c,
                    p4c_success=False,
                    p4c_phase=phase_p4c,
                    final_success=False,
                    reason=f"P4c failed: {phase_p4c.message}",
                )
                log(f"K8S-NATIVE SCENARIO FAILED at P4c: {phase_p4c.message}")
                result.failure_reason = f"P4c failed (K8s-native diagnosis): {phase_p4c.message}"
                return _finish_result(result, artifact_dir, start_time)
            
            # K8s-native scenario succeeds
            result.success = True
            result.verification_passed = True
            
            # Build verdict summary that distinguishes discovery from root-cause
            result.verification_details = {
                "scenario": "unschedulable-shipping",
                "p2b_success": phase_p2b.success,
                "p3c_success": phase_p3c.success,
                "p4c_success": phase_p4c.success,
            }
            
            # Add K8s-native verdict with phase distinction
            result.k8s_native_verdict = _build_k8s_native_verdict(
                p3c_success=True,
                p3c_phase=phase_p3c,
                p4c_success=True,
                p4c_phase=phase_p4c,
                final_success=True,
                reason="all_phases_passed",
            )
            
            return _finish_result(result, artifact_dir, start_time)
        
        # =====================================================================
        # Original OTel Demo Phases (default path)
        # =====================================================================
        
        # Phase 2: Inject incident
        log("=" * 60)
        log("PHASE 2: Inject recommendation cache failure")
        log("=" * 60)
        phase2 = phase2_inject_incident(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase2))
        if not phase2.success:
            result.failure_reason = f"Incident injection failed: {phase2.message}"
            return _finish_result(result, artifact_dir, start_time)
        
        # Phase 3: Incident discovery (placeholder - OTel telemetry-oriented)
        log("=" * 60)
        log("PHASE 3: Run k9b incident discovery")
        log("=" * 60)
        phase3 = phase3_incident_discovery(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase3))
        
        # Phase 4: Diagnosis
        log("=" * 60)
        log("PHASE 4: Run diagnosis")
        log("=" * 60)
        phase4 = phase4_diagnosis(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase4))
        
        # =====================================================================
        # Provider Smoke Phases (run AFTER incident injection, fail-closed)
        # These phases run AFTER the OTel failure injection because they need
        # an injected incident to discover. They are fail-closed when enabled.
        # =====================================================================
        provider_smoke_passed = False
        
        if config.enable_provider_smoke:
            log("=" * 60)
            log("PROVIDER SMOKE: Starting provider smoke phases (fail-closed)")
            log("=" * 60)
            
            # Phase P1: Backend Health Gate
            log("=" * 60)
            log("PHASE P1: Backend Health Gate")
            log("=" * 60)
            phase_p1 = phase_p1_backend_health_gate(config, artifact_dir)
            result.phases.append(_phase_to_dict(phase_p1))
            if not phase_p1.success:
                log(f"PROVIDER SMOKE FAILED at P1 (backend health): {phase_p1.message}")
                result.failure_reason = f"Provider smoke failed at backend health gate: {phase_p1.message}"
                result.provider_smoke_passed = False
                return _finish_result(result, artifact_dir, start_time)
            
            # Phase P1b: Scheduler Health Gate
            log("=" * 60)
            log("PHASE P1b: Scheduler Health Gate")
            log("=" * 60)
            phase_p1b = phase_p1b_scheduler_health_gate(config, artifact_dir)
            result.phases.append(_phase_to_dict(phase_p1b))
            if not phase_p1b.success:
                log(f"PROVIDER SMOKE FAILED at P1b (scheduler health): {phase_p1b.message}")
                result.failure_reason = f"Provider smoke failed at scheduler health gate: {phase_p1b.message}"
                result.provider_smoke_passed = False
                return _finish_result(result, artifact_dir, start_time)
            
            # Phase P2: Incident Discovery (k9b API-backed)
            log("=" * 60)
            log("PHASE P2: Incident Discovery (k9b API)")
            log("=" * 60)
            phase_p2, discovered_incident_id = phase_p2_incident_discovery_provider(config, artifact_dir)
            result.phases.append(_phase_to_dict(phase_p2))
            
            if not phase_p2.success or not discovered_incident_id:
                log(f"PROVIDER SMOKE FAILED at P2 (incident discovery): {phase_p2.message}")
                result.failure_reason = f"Provider smoke failed at incident discovery: {phase_p2.message}"
                result.provider_smoke_passed = False
                return _finish_result(result, artifact_dir, start_time)
            
            # Phase P3: One-Pass Diagnosis Provider Smoke
            log("=" * 60)
            log("PHASE P3: One-Pass Diagnosis Provider Smoke")
            log("=" * 60)
            phase_p3 = phase_p3_provider_smoke(config, artifact_dir, discovered_incident_id)
            result.phases.append(_phase_to_dict(phase_p3))
            
            if not phase_p3.success:
                log(f"PROVIDER SMOKE FAILED at P3 (one-pass diagnosis): {phase_p3.message}")
                result.failure_reason = f"Provider smoke failed at one-pass diagnosis: {phase_p3.message}"
                result.provider_smoke_passed = False
                return _finish_result(result, artifact_dir, start_time)
            
            # Phase P4: Persisted Diagnosis Contract Verification
            log("=" * 60)
            log("PHASE P4: Persisted Diagnosis Contract Verification")
            log("=" * 60)
            phase_p4 = phase_p4_persisted_diagnosis(config, artifact_dir, discovered_incident_id)
            result.phases.append(_phase_to_dict(phase_p4))
            
            if not phase_p4.success:
                log(f"PROVIDER SMOKE FAILED at P4 (persisted diagnosis): {phase_p4.message}")
                result.failure_reason = f"Provider smoke failed at persisted diagnosis: {phase_p4.message}"
                result.provider_smoke_passed = False
                return _finish_result(result, artifact_dir, start_time)
            
            provider_smoke_passed = True
            log("PROVIDER SMOKE: All phases passed")
        else:
            log("=" * 60)
            log("PROVIDER SMOKE: Disabled (enable_provider_smoke=false)")
            log("=" * 60)
        
        # =====================================================================
        # Phase 5: Verification (original OTel oracle)
        # =====================================================================
        
        log("=" * 60)
        log("PHASE 5: Verify with oracle")
        log("=" * 60)
        phase5 = phase5_verification(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase5))
        result.verification_passed = phase5.success
        result.verification_details = phase5.artifacts
        
        # When provider smoke is enabled, lab success requires BOTH verification AND provider smoke
        # When provider smoke is disabled, lab success is based on verification alone
        if config.enable_provider_smoke:
            result.success = phase5.success and provider_smoke_passed
            if not provider_smoke_passed:
                result.failure_reason = result.failure_reason or "Provider smoke phases failed"
        else:
            result.success = phase5.success
        
        result.provider_smoke_passed = provider_smoke_passed
        
    except Exception as e:
        log(f"Lab execution error: {e}")
        result.failure_reason = str(e)
    
    return _finish_result(result, artifact_dir, start_time)


def _phase_to_dict(phase: LabPhaseResult) -> dict[str, Any]:
    """Convert phase result to dict."""
    data = {
        "phase": phase.phase,
        "success": phase.success,
        "message": phase.message,
        "artifacts": phase.artifacts,
        "duration_seconds": phase.duration_seconds,
    }
    # Include verdict fields for K8s-native phases
    if phase.p3c_verdict is not None:
        data["p3c_verdict"] = phase.p3c_verdict
    if phase.p4c_verdict is not None:
        data["p4c_verdict"] = phase.p4c_verdict
    return data


def _build_k8s_native_verdict(
    p3c_success: bool,
    p3c_phase: LabPhaseResult | None,
    p4c_success: bool | None,
    p4c_phase: LabPhaseResult | None,
    final_success: bool,
    reason: str,
) -> dict[str, Any]:
    """Build K8s-native verdict dict for lab-result.json.
    
    This function is used in both success and failure paths to ensure
    the verdict is always populated with phase distinction.
    """
    verdict: dict[str, Any] = {
        "final": {
            "success": final_success,
            "reason": reason,
        },
    }
    
    # P3c verdict
    p3c_data: dict[str, Any] = {
        "success": p3c_success,
        "phase": "incident_discovery",
    }
    if p3c_phase is not None:
        p3c_data["incident_id"] = p3c_phase.artifacts.get("incident_id")
        p3c_data["candidate_class"] = p3c_phase.artifacts.get("candidate_class")
        p3c_data["root_cause_final"] = False  # P3c is symptom-level only
    verdict["p3c"] = p3c_data
    
    # P4c verdict
    p4c_data: dict[str, Any] = {
        "phase": "root_cause_validation",
    }
    if p4c_success is not None:
        p4c_data["success"] = p4c_success
    if p4c_phase is not None:
        p4c_data["failure_reason"] = p4c_phase.artifacts.get("failure_reason")
    verdict["p4c"] = p4c_data
    
    return verdict


def _finish_result(result: LabResult, artifact_dir: Path, start_time: float) -> LabResult:
    """Finalize and save the lab result."""
    result.finished_at = datetime.now(UTC).isoformat()
    elapsed = time.time() - start_time
    result.elapsed_seconds = elapsed
    
    # Write result to artifact dir
    result_path = write_json_artifact(artifact_dir, "lab-result.json", _result_to_dict(result))
    log(f"Lab result saved to {result_path}")
    
    return result


def _result_to_dict(result: LabResult) -> dict[str, Any]:
    """Convert LabResult to dict for JSON serialization."""
    data = {
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "elapsed_seconds": result.elapsed_seconds,
        "success": result.success,
        "failure_reason": result.failure_reason,
        "verification_passed": result.verification_passed,
        "verification_details": result.verification_details,
        "provider_smoke_passed": result.provider_smoke_passed,
        "config": result.config,
        "phases": result.phases,
    }
    # Include K8s-native verdict if present (for unschedulable-shipping scenario)
    if result.k8s_native_verdict is not None:
        data["k8s_native_verdict"] = result.k8s_native_verdict
    return data


# Backward-compatible CLI entry point
def main() -> int:
    """Backward-compatible CLI entry point.

    Delegates to k9b_otel_demo_lab_cli.run_cli() for the actual CLI logic.
    Use module invocation for reliable execution:
        python -m scripts.k9b_otel_demo_lab --kubeconfig /path/to/kubeconfig [options]
        python -m scripts.k9b_otel_demo_lab_cli --kubeconfig /path/to/kubeconfig [options]
    """
    from .k9b_otel_demo_lab_cli import run_cli

    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())



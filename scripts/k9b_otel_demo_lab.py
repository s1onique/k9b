#!/usr/bin/env python3
"""OpenTelemetry Demo Lab - orchestrator.

This module orchestrates the complete OTel Demo incident lab lifecycle:
1. Cluster + k9b baseline (Phase 0)
2. Deploy OpenTelemetry Demo (Phase 1)
3. Prove baseline readiness (Phase 1b)
4. Inject recommendation-service cache failure (Phase 2)
5. Run k9b incident discovery (Phase 3)
6. Run diagnosis (Phase 4)
7. Verify final diagnosis with oracle (Phase 5)

For LLM-friendly reading, see the companion modules:
- k9b_otel_demo_lab_types.py - dataclasses and types
- k9b_otel_demo_lab_phases.py - phase implementations
- k9b_otel_demo_lab_constants.py - constants
- k9b_otel_demo_lab_inject.py - incident injection
- k9b_otel_demo_lab_verify.py - oracle verification
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import log, write_json_artifact
from .k9b_otel_demo_lab_phases import (
    phase0_cluster_baseline,
    phase1_deploy_otel_demo,
    phase1b_baseline_readiness,
    phase2_inject_incident,
    phase3_incident_discovery,
    phase4_diagnosis,
    phase5_verification,
)
from .k9b_otel_demo_lab_types import LabConfig, LabPhaseResult, LabResult


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
        
        # Phase 2: Inject incident
        log("=" * 60)
        log("PHASE 2: Inject recommendation cache failure")
        log("=" * 60)
        phase2 = phase2_inject_incident(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase2))
        if not phase2.success:
            result.failure_reason = f"Incident injection failed: {phase2.message}"
            return _finish_result(result, artifact_dir, start_time)
        
        # Phase 3: Incident discovery
        log("=" * 60)
        log("PHASE 3: Run k9b incident discovery")
        log("=" * 60)
        phase3 = phase3_incident_discovery(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase3))
        # Non-fatal - incident discovery might not find anything
        
        # Phase 4: Diagnosis
        log("=" * 60)
        log("PHASE 4: Run diagnosis")
        log("=" * 60)
        phase4 = phase4_diagnosis(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase4))
        
        # Phase 5: Verification
        log("=" * 60)
        log("PHASE 5: Verify with oracle")
        log("=" * 60)
        phase5 = phase5_verification(config, artifact_dir)
        result.phases.append(_phase_to_dict(phase5))
        result.verification_passed = phase5.success
        result.verification_details = phase5.artifacts
        
        result.success = phase5.success
        
    except Exception as e:
        log(f"Lab execution error: {e}")
        result.failure_reason = str(e)
    
    return _finish_result(result, artifact_dir, start_time)


def _phase_to_dict(phase: LabPhaseResult) -> dict[str, Any]:
    """Convert phase result to dict."""
    return {
        "phase": phase.phase,
        "success": phase.success,
        "message": phase.message,
        "artifacts": phase.artifacts,
        "duration_seconds": phase.duration_seconds,
    }


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
    return {
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "elapsed_seconds": result.elapsed_seconds,
        "success": result.success,
        "failure_reason": result.failure_reason,
        "verification_passed": result.verification_passed,
        "verification_details": result.verification_details,
        "config": result.config,
        "phases": result.phases,
    }


# CLI entry point
def main() -> int:
    """CLI entry point for OTel Demo Lab."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run OTel Demo incident lab")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument(
        "--artifact-dir",
        default="./lab-artifacts/otel-demo",
        help="Artifact directory",
    )
    parser.add_argument(
        "--mode",
        choices=["scaffold", "live"],
        default="scaffold",
        help="Lab mode: scaffold (fixture-based) or live (real cluster traffic)",
    )
    # Live mode timing overrides
    parser.add_argument(
        "--live-traffic-duration",
        type=int,
        default=600,
        help="Duration of live traffic generation in seconds (default: 600)",
    )
    parser.add_argument(
        "--live-observation-wait",
        type=int,
        default=600,
        help="Wait time for symptoms to manifest in seconds (default: 600)",
    )
    parser.add_argument(
        "--live-poll-interval",
        type=int,
        default=30,
        help="Poll interval for observation in seconds (default: 30)",
    )
    
    args = parser.parse_args()
    
    from .k9b_otel_demo_lab_types import LabConfig
    
    config = LabConfig(
        kubeconfig=args.kubeconfig,
        artifact_dir=args.artifact_dir,
        mode=args.mode,
        live_traffic_duration_seconds=args.live_traffic_duration,
        live_observation_wait_seconds=args.live_observation_wait,
        live_poll_interval_seconds=args.live_poll_interval,
    )
    
    result = run_lab(config)
    
    if result.success:
        print(f"LAB RESULT: SUCCESS (mode={args.mode})")
        print(f"Elapsed: {result.elapsed_seconds:.1f}s")
        return 0
    else:
        print(f"LAB RESULT: FAILED - {result.failure_reason} (mode={args.mode})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

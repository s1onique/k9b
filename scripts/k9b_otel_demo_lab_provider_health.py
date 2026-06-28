#!/usr/bin/env python3
"""Provider smoke health gates (P1, P1b).

These phases verify k9b backend and scheduler health before incident discovery.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .k9b_otel_demo_lab_constants import (
    K9B_BACKEND_CONTAINER,
    K9B_BACKEND_DEPLOYMENT,
    K9B_BACKEND_PORT,
    K9B_NAMESPACE,
    PHASE_BACKEND_HEALTH,
    PHASE_SCHEDULER_HEALTH,
)
from .k9b_otel_demo_lab_types import LabConfig, LabPhaseResult


def phase_p1_backend_health_gate(
    config: LabConfig, artifact_dir: Path
) -> LabPhaseResult:
    """Phase P1: Backend Health Gate - verify k9b backend is healthy.
    
    This is a fail-fast gate that checks if the k9b backend /api/health returns HTTP 200.
    """
    from .backend_health_gate import run_health_gate

    start = time.time()
    phase_dir = artifact_dir / PHASE_BACKEND_HEALTH
    phase_dir.mkdir(parents=True, exist_ok=True)

    from .k9b_lab_common_helpers import log
    log("=== Phase P1: Backend Health Gate ===")
    log(f"Checking k9b backend health at k9b-backend:{K9B_BACKEND_PORT}")

    try:
        result = run_health_gate(
            kubeconfig=config.kubeconfig,
            namespace=K9B_NAMESPACE,
            deployment=K9B_BACKEND_DEPLOYMENT,
            container=K9B_BACKEND_CONTAINER,
            port=K9B_BACKEND_PORT,
            max_retries=30,
            retry_interval=5,
            artifact_dir=phase_dir,
        )

        result_data = result.to_dict()
        result_path = phase_dir / "health-check-result.json"
        result_path.write_text(json.dumps(result_data, indent=2))

        duration = time.time() - start

        if result.passed:
            log(f"Backend health gate PASSED: HTTP 200 after {result.poll_count} polls")
            return LabPhaseResult(
                phase="p1-backend-health",
                success=True,
                message=f"Backend healthy: HTTP 200 after {result.poll_count} polls ({result.total_elapsed_seconds:.1f}s)",
                artifacts={"health_check_result": str(result_path)},
                duration_seconds=duration,
            )
        else:
            log(f"Backend health gate FAILED: {result.failure_class}")
            return LabPhaseResult(
                phase="p1-backend-health",
                success=False,
                message=f"Backend unhealthy: {result.failure_class}",
                artifacts={"health_check_result": str(result_path)},
                duration_seconds=duration,
            )
    except Exception as e:
        duration = time.time() - start
        log(f"Backend health gate error: {e}")
        return LabPhaseResult(
            phase="p1-backend-health",
            success=False,
            message=f"Backend health check error: {e}",
            artifacts={},
            duration_seconds=duration,
        )


def phase_p1b_scheduler_health_gate(
    config: LabConfig, artifact_dir: Path
) -> LabPhaseResult:
    """Phase P1b: Scheduler Health Gate - verify k9b scheduler is healthy.
    
    This is a fail-fast gate that checks if the k9b scheduler deployment is Ready.
    """
    from .scheduler_health_gate import run_scheduler_health_gate

    start = time.time()
    phase_dir = artifact_dir / PHASE_SCHEDULER_HEALTH
    phase_dir.mkdir(parents=True, exist_ok=True)

    from .k9b_lab_common_helpers import log
    log("=== Phase P1b: Scheduler Health Gate ===")
    log(f"Checking k9b scheduler health in namespace {K9B_NAMESPACE}")

    try:
        result = run_scheduler_health_gate(
            kubeconfig=config.kubeconfig,
            namespace=K9B_NAMESPACE,
            artifact_dir=phase_dir,
        )

        result_data = result.to_dict()
        result_path = phase_dir / "scheduler-health-result.json"
        result_path.write_text(json.dumps(result_data, indent=2))

        duration = time.time() - start

        if result.passed:
            log(f"Scheduler health gate PASSED: {result.ready_replicas} ready replicas")
            return LabPhaseResult(
                phase="p1b-scheduler-health",
                success=True,
                message=f"Scheduler healthy: {result.ready_replicas} ready replicas",
                artifacts={"scheduler_health_result": str(result_path)},
                duration_seconds=duration,
            )
        else:
            log(f"Scheduler health gate FAILED: {result.failure_class}")
            return LabPhaseResult(
                phase="p1b-scheduler-health",
                success=False,
                message=f"Scheduler unhealthy: {result.failure_class}",
                artifacts={"scheduler_health_result": str(result_path)},
                duration_seconds=duration,
            )
    except Exception as e:
        duration = time.time() - start
        log(f"Scheduler health gate error: {e}")
        return LabPhaseResult(
            phase="p1b-scheduler-health",
            success=False,
            message=f"Scheduler health check error: {e}",
            artifacts={},
            duration_seconds=duration,
        )

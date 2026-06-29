#!/usr/bin/env python3
"""K8s-native multi-pass diagnosis verification for OTel Demo Lab.

This module is a facade that re-exports symbols from the split modules:
- k9b_otel_demo_lab_k8s_diagnosis_phase: Main phase function
- k9b_otel_demo_lab_k8s_diagnosis_verify: Standalone verifier
- k9b_otel_demo_lab_k8s_diagnosis_constants: Configuration constants

For new code, import directly from the split modules for better
LLM-friendly organization.
"""

from __future__ import annotations

# Re-export from split modules for backward compatibility
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    ARTIFACT_DIR,
    ARTIFACT_FILENAME,
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_PASSES,
    DIAGNOSIS_SOURCE_REAL,
    DIAGNOSIS_SOURCE_SIMULATED,
    FAILURE_REASON_LOOP_DISABLED,
    FAILURE_REASON_LOOP_ERROR,
    FAILURE_REASON_LOOP_IMPORT_FAILED,
    FAILURE_REASON_PASS_ARTIFACTS_MISSING,
    FORBIDDEN_MUTATING_PATTERNS,
    MIN_REQUIRED_PASSES,
    PHASE_DIAGNOSIS,
    PHASE_NAME,
    REQUIRED_ROOT_CAUSE_TERMS,
    SCHEDULING_PATTERNS,
    SELECTOR_KEY_PATTERNS,
    SELECTOR_VALUE_PATTERNS,
    SIMULATION_ENV_VAR,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import (
    _check_pass_count,
    _check_read_only_contract,
    _check_root_cause_terms,
    _extract_pass_run_ids,
    _validate_diagnosis_evidence,
    _validate_discovery_evidence,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
    phase_p4c_verify_k8s_mult_pass_diagnosis,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
    verify_unschedulable_shipping_mult_pass_diagnosis,
)

__all__ = [
    # Constants
    "PHASE_NAME",
    "PHASE_DIAGNOSIS",
    "ARTIFACT_DIR",
    "ARTIFACT_FILENAME",
    "MIN_REQUIRED_PASSES",
    "DEFAULT_MAX_PASSES",
    "DEFAULT_MAX_CHECKS_PER_PASS",
    "REQUIRED_ROOT_CAUSE_TERMS",
    "SCHEDULING_PATTERNS",
    "SELECTOR_KEY_PATTERNS",
    "SELECTOR_VALUE_PATTERNS",
    "FORBIDDEN_MUTATING_PATTERNS",
    # Simulation control
    "DIAGNOSIS_SOURCE_REAL",
    "DIAGNOSIS_SOURCE_SIMULATED",
    "SIMULATION_ENV_VAR",
    "FAILURE_REASON_LOOP_DISABLED",
    "FAILURE_REASON_LOOP_IMPORT_FAILED",
    "FAILURE_REASON_LOOP_ERROR",
    "FAILURE_REASON_PASS_ARTIFACTS_MISSING",
    # Phase function
    "phase_p4c_verify_k8s_mult_pass_diagnosis",
    # Verifier function
    "verify_unschedulable_shipping_mult_pass_diagnosis",
    # Helper functions (for testing)
    "_validate_diagnosis_evidence",
    "_validate_discovery_evidence",
    "_check_read_only_contract",
    "_check_root_cause_terms",
    "_check_pass_count",
    "_extract_pass_run_ids",
]


def main() -> int:
    """CLI entry point for K8s multi-pass diagnosis verification."""
    import argparse
    from pathlib import Path

    from scripts.k9b_otel_demo_lab_constants import OTEL_DEMO_NAMESPACE
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
        phase_p4c_verify_k8s_mult_pass_diagnosis,
    )
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
        verify_unschedulable_shipping_mult_pass_diagnosis,
    )
    from scripts.k9b_otel_demo_lab_types import LabConfig

    parser = argparse.ArgumentParser(description="Verify k9b multi-pass diagnosis")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument("--namespace", default=OTEL_DEMO_NAMESPACE, help="Namespace")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing artifacts")

    args = parser.parse_args()
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if args.verify_only:
        # Just verify existing diagnosis artifacts
        verify_result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
        print(f"Verification: {'PASS' if verify_result['verified'] else 'FAIL'}")
        print(f"Reason: {verify_result.get('reason', 'N/A')}")
        if verify_result.get('verified'):
            print(f"Incident ID: {verify_result.get('incident_id', 'N/A')}")
            print(f"Pass count: {verify_result.get('pass_count', 0)}")
        return 0 if verify_result["verified"] else 1

    # Run diagnosis phase
    config = LabConfig(
        kubeconfig=args.kubeconfig,
        artifact_dir=str(artifact_dir),
        namespace=args.namespace,
    )

    phase_result = phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)

    print(f"Phase result: {'SUCCESS' if phase_result.success else 'FAILED'}")
    print(f"Message: {phase_result.message}")
    print(f"Duration: {phase_result.duration_seconds:.1f}s")

    return 0 if phase_result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

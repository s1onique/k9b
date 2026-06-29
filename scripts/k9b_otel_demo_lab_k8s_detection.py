#!/usr/bin/env python3
"""K8s-native incident discovery verification for OTel Demo Lab.

This module is a facade that re-exports symbols from the split modules:
- k9b_otel_demo_lab_k8s_detection_phase: Main phase function
- k9b_otel_demo_lab_k8s_detection_verify: Standalone verifier
- k9b_otel_demo_lab_k8s_detection_constants: Configuration constants

For new code, import directly from the split modules for better
LLM-friendly organization.
"""

from __future__ import annotations

# Re-export from split modules for backward compatibility
from scripts.k9b_otel_demo_lab_k8s_detection_constants import (
    ACCEPTED_CANDIDATE_CLASSES,
    DEFAULT_BACKEND_PORT,
    DEFAULT_DETECTION_POLL_INTERVAL_SECONDS,
    DEFAULT_DETECTION_TIMEOUT_SECONDS,
    DEFAULT_MAX_DETECTION_ATTEMPTS,
    FAILED_SCHEDULING_PATTERNS,
    SHIPPING_MATCH_PATTERNS,
)
from scripts.k9b_otel_demo_lab_k8s_detection_match import (
    _extract_matching_signals,
    _match_shipping_incident,
    _validate_discovery_evidence,
    _validate_namespace,
    _validate_shipping_reference,
)
from scripts.k9b_otel_demo_lab_k8s_detection_phase import (
    phase_p3c_verify_k8s_incident_discovery,
)
from scripts.k9b_otel_demo_lab_k8s_detection_verify import (
    verify_unschedulable_shipping_incident_discovered,
)

__all__ = [
    # Constants
    "ACCEPTED_CANDIDATE_CLASSES",
    "DEFAULT_BACKEND_PORT",
    "DEFAULT_DETECTION_POLL_INTERVAL_SECONDS",
    "DEFAULT_DETECTION_TIMEOUT_SECONDS",
    "DEFAULT_MAX_DETECTION_ATTEMPTS",
    "FAILED_SCHEDULING_PATTERNS",
    "SHIPPING_MATCH_PATTERNS",
    # Phase function
    "phase_p3c_verify_k8s_incident_discovery",
    # Verifier function
    "verify_unschedulable_shipping_incident_discovered",
    # Helper functions (for testing)
    "_match_shipping_incident",
    "_validate_namespace",
    "_validate_shipping_reference",
    "_validate_discovery_evidence",
    "_extract_matching_signals",
]


def main() -> int:
    """CLI entry point for K8s incident discovery verification."""
    import argparse
    from pathlib import Path

    from scripts.k9b_otel_demo_lab_constants import OTEL_DEMO_NAMESPACE
    from scripts.k9b_otel_demo_lab_k8s_detection_phase import (
        phase_p3c_verify_k8s_incident_discovery,
    )
    from scripts.k9b_otel_demo_lab_k8s_detection_verify import (
        verify_unschedulable_shipping_incident_discovered,
    )
    from scripts.k9b_otel_demo_lab_types import LabConfig

    parser = argparse.ArgumentParser(description="Verify k9b incident discovery")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument("--namespace", default=OTEL_DEMO_NAMESPACE, help="Namespace")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing artifacts")

    args = parser.parse_args()
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if args.verify_only:
        # Just verify existing detection artifacts
        verify_result = verify_unschedulable_shipping_incident_discovered(artifact_dir)
        print(f"Verification: {'PASS' if verify_result['verified'] else 'FAIL'}")
        print(f"Reason: {verify_result.get('reason', 'N/A')}")
        return 0 if verify_result["verified"] else 1

    # Run detection
    config = LabConfig(
        kubeconfig=args.kubeconfig,
        artifact_dir=str(artifact_dir),
        namespace=args.namespace,
    )

    phase_result = phase_p3c_verify_k8s_incident_discovery(config, artifact_dir)

    print(f"Phase result: {'SUCCESS' if phase_result.success else 'FAILED'}")
    print(f"Message: {phase_result.message}")
    print(f"Duration: {phase_result.duration_seconds:.1f}s")

    return 0 if phase_result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

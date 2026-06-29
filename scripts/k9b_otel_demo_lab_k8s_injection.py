#!/usr/bin/env python3
"""Kubernetes-native incident injection for OTel Demo Lab.

This module is a facade that re-exports symbols from the split modules:
- k9b_otel_demo_lab_k8s_injection_phase: Main phase function
- k9b_otel_demo_lab_k8s_injection_cleanup: Cleanup and rollback functions
- k9b_otel_demo_lab_k8s_injection_types: Types and constants

For new code, import directly from the split modules for better
LLM-friendly organization.
"""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_constants import (
    K8S_INJECTION_NODE_SELECTOR_KEY,
    K8S_INJECTION_NODE_SELECTOR_VALUE,
    SHIPPING_DEPLOYMENT,
)

# Re-export from split modules for backward compatibility
from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import (
    _restore_node_selector,
    cleanup_unschedulable_shipping_rollout,
)
from scripts.k9b_otel_demo_lab_k8s_injection_helpers import (
    _extract_node_selector,
    _extract_pod_template,
)
from scripts.k9b_otel_demo_lab_k8s_injection_phase import (
    phase_p2b_inject_unschedulable_shipping_rollout,
)
from scripts.k9b_otel_demo_lab_k8s_injection_polling import (
    _filter_pods_by_ownership,
    _poll_for_symptoms,
)
from scripts.k9b_otel_demo_lab_k8s_injection_types import (
    DEFAULT_MAX_POLL_ATTEMPTS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    K8sInjectionResult,
)

__all__ = [
    # Types
    "K8sInjectionResult",
    # Constants
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_MAX_POLL_ATTEMPTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "K8S_INJECTION_NODE_SELECTOR_KEY",
    "K8S_INJECTION_NODE_SELECTOR_VALUE",
    "SHIPPING_DEPLOYMENT",
    # Phase function
    "phase_p2b_inject_unschedulable_shipping_rollout",
    # Cleanup function
    "cleanup_unschedulable_shipping_rollout",
    # Helper functions (for testing)
    "_restore_node_selector",
    "_extract_node_selector",
    "_extract_pod_template",
    "_filter_pods_by_ownership",
    "_poll_for_symptoms",
]


def main() -> int:
    """CLI entry point for K8s-native incident injection."""
    import argparse
    import json
    from pathlib import Path

    from scripts.k9b_otel_demo_lab_constants import OTEL_DEMO_NAMESPACE
    from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import (
        cleanup_unschedulable_shipping_rollout,
    )
    from scripts.k9b_otel_demo_lab_k8s_injection_phase import (
        phase_p2b_inject_unschedulable_shipping_rollout,
    )
    from scripts.k9b_otel_demo_lab_types import LabConfig

    parser = argparse.ArgumentParser(description="Inject K8s-native OTel Demo incident")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument("--namespace", default=OTEL_DEMO_NAMESPACE, help="Namespace")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory")
    parser.add_argument("--cleanup", action="store_true", help="Run cleanup instead of injection")
    parser.add_argument("--previous-node-selector", help="Path to previous nodeSelector JSON for cleanup")
    parser.add_argument("--replicas", type=int, default=1, help="Original replica count for cleanup")

    args = parser.parse_args()
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if args.cleanup:
        if not args.previous_node_selector:
            print("Error: --previous-node-selector required for cleanup")
            return 1

        node_selector_data = json.loads(Path(args.previous_node_selector).read_text())
        previous_node_selector = node_selector_data.get("node_selector")
        success = cleanup_unschedulable_shipping_rollout(
            args.kubeconfig,
            args.namespace,
            previous_node_selector,
            args.replicas,
        )
        print(f"Cleanup: {'SUCCESS' if success else 'FAILED'}")
        return 0 if success else 1

    # Run injection
    config = LabConfig(
        kubeconfig=args.kubeconfig,
        artifact_dir=str(artifact_dir),
        namespace=args.namespace,
    )

    result = phase_p2b_inject_unschedulable_shipping_rollout(config, artifact_dir)

    print(f"Phase result: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Message: {result.message}")
    print(f"Duration: {result.duration_seconds:.1f}s")

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

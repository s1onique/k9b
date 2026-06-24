"""Golden-case fake handlers.

This module provides fake handlers that return context-aware evidence
from golden-case bundles instead of generic placeholder output.

.. note::
    These handlers are NOT currently wired into the adapter. They exist as a
    future seam for wiring into the read-only check runner.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .golden_case_evidence_provider import GoldenCaseEvidenceProvider

__all__ = ["create_golden_case_fake_handlers", "GoldenCaseFakeHandlers"]


# Type alias for the handlers dict
GoldenCaseFakeHandlers = dict[str, Any]


def create_golden_case_fake_handlers(
    evidence_provider: GoldenCaseEvidenceProvider,
) -> dict[str, Any]:
    """Create fake handlers that use golden-case evidence.

    .. note::
        This function is NOT currently wired into the adapter. It exists as a
        future seam for wiring into the read-only check runner. The adapter
        currently uses DeterministicDiagnosisProvider directly.

    Args:
        evidence_provider: Provider for golden-case evidence

    Returns:
        Dict mapping check_id to handler function
    """
    def _fake_pod_describe_handler(
        check: Mapping[str, object], *, now: datetime
    ) -> Mapping[str, object]:
        """Fake handler that returns golden-case pod describe evidence."""
        params = check.get("parameters", {})
        namespace = params.get("namespace", "unknown")
        object_name = params.get("object_name", "unknown")

        pod_content = evidence_provider.get_evidence("incident/pods.txt") or ""
        events_content = evidence_provider.get_evidence("incident/events.txt") or ""

        relevant_pod = ""
        if object_name in pod_content:
            lines = pod_content.split("\n")
            in_section = False
            for line in lines:
                if object_name in line:
                    in_section = True
                if in_section:
                    relevant_pod += line + "\n"
                    if line.strip() == "" and len(relevant_pod) > 500:
                        break

        summary = (
            f"Golden-case evidence for pod {namespace}/{object_name}. "
            f"Pod is Running but NotReady due to readiness probe failure."
        )

        observations = [
            f"namespace: {namespace}",
            f"pod: {object_name}",
            "golden_case_evidence: true",
            f"timestamp: {now.isoformat()}",
        ]

        if relevant_pod:
            observations.append("pod_state: Running, Ready: 0/1")
            observations.append("readiness_probe: failing (exit code 1)")

        if "Unhealthy" in events_content:
            observations.append("events: Warning events detected")

        return {
            "summary": summary[:500],
            "observations": observations[:10],
            "evidence": {"pod_content": relevant_pod[:2000] if relevant_pod else ""},
            "golden_case_handler": True,
            "no_kubernetes_call": True,
        }

    def _fake_pod_events_handler(
        check: Mapping[str, object], *, now: datetime
    ) -> Mapping[str, object]:
        """Fake handler that returns golden-case events evidence."""
        params = check.get("parameters", {})
        namespace = params.get("namespace", "unknown")
        object_name = params.get("object_name", "unknown")

        events_content = evidence_provider.get_evidence("incident/events.txt") or ""

        summary = (
            f"Golden-case events for {namespace}/{object_name}. "
            f"Warning: Unhealthy readiness probe."
        )

        observations = [
            f"namespace: {namespace}",
            f"object: {object_name}",
            "golden_case_evidence: true",
            f"timestamp: {now.isoformat()}",
        ]

        if "Unhealthy" in events_content:
            observations.append("Warning: Readiness probe failed (Unhealthy)")

        if "/bin/false" in events_content:
            observations.append("Probe command: /bin/false (always fails)")

        return {
            "summary": summary[:500],
            "observations": observations[:10],
            "evidence": {"events_content": events_content[:2000]},
            "golden_case_handler": True,
            "no_kubernetes_call": True,
        }

    def _fake_pod_logs_handler(
        check: Mapping[str, object], *, now: datetime
    ) -> Mapping[str, object]:
        """Fake handler for pod logs check."""
        params = check.get("parameters", {})
        namespace = params.get("namespace", "unknown")
        object_name = params.get("object_name", "unknown")
        container = params.get("container", "default")

        return {
            "summary": f"Golden-case logs for {namespace}/{object_name}",
            "observations": [
                f"namespace: {namespace}",
                f"pod: {object_name}",
                f"container: {container}",
                "golden_case_evidence: true",
                f"timestamp: {now.isoformat()}",
                "Note: Readiness probe failure detected at application layer",
            ],
            "golden_case_handler": True,
            "no_kubernetes_call": True,
        }

    def _fake_deployment_status_handler(
        check: Mapping[str, object], *, now: datetime
    ) -> Mapping[str, object]:
        """Fake handler for deployment status check."""
        params = check.get("parameters", {})
        namespace = params.get("namespace", "unknown")
        object_name = params.get("object_name", "unknown")

        return {
            "summary": f"Golden-case deployment status for {namespace}/{object_name}",
            "observations": [
                f"namespace: {namespace}",
                f"deployment: {object_name}",
                "golden_case_evidence: true",
                f"timestamp: {now.isoformat()}",
                "Replicas: 0/1 ready (readiness probe failing)",
            ],
            "golden_case_handler": True,
            "no_kubernetes_call": True,
        }

    def _fake_node_status_handler(
        check: Mapping[str, object], *, now: datetime
    ) -> Mapping[str, object]:
        """Fake handler for node status check."""
        params = check.get("parameters", {})
        node_name = params.get("node_name", "unknown")

        return {
            "summary": f"Golden-case node status for {node_name}",
            "observations": [
                f"node: {node_name}",
                "golden_case_evidence: true",
                f"timestamp: {now.isoformat()}",
                "Note: Node is healthy; issue is at pod level",
            ],
            "golden_case_handler": True,
            "no_kubernetes_call": True,
        }

    def _fake_service_endpoints_handler(
        check: Mapping[str, object], *, now: datetime
    ) -> Mapping[str, object]:
        """Fake handler for service endpoints check."""
        params = check.get("parameters", {})
        namespace = params.get("namespace", "unknown")
        object_name = params.get("object_name", "unknown")

        return {
            "summary": f"Golden-case service endpoints for {namespace}/{object_name}",
            "observations": [
                f"namespace: {namespace}",
                f"service: {object_name}",
                "golden_case_evidence: true",
                f"timestamp: {now.isoformat()}",
                "Endpoints: 0 (no ready pods)",
            ],
            "golden_case_handler": True,
            "no_kubernetes_call": True,
        }

    return {
        "pod_describe": _fake_pod_describe_handler,
        "pod_events": _fake_pod_events_handler,
        "pod_logs": _fake_pod_logs_handler,
        "deployment_status": _fake_deployment_status_handler,
        "node_status": _fake_node_status_handler,
        "service_endpoints": _fake_service_endpoints_handler,
    }

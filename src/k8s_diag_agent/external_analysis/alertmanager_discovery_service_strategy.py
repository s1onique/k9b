"""Alertmanager service-based discovery strategy.

This module provides the service/pod heuristic discovery strategy:
- ServiceHeuristicDiscoveryStrategy: Discover via service/pod name heuristics

The module answers: "Given cluster context, find Alertmanager instances via service/pod patterns."

It does NOT include:
- CRD-based discovery (see alertmanager_discovery_crd_strategy)
- Source/endpoint construction (see alertmanager_discovery_sources)
- HTTP verification of endpoints
- High-level orchestration of discovery runs
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .alertmanager_discovery_crd_strategy import DiscoveryStrategy, _kubectl_context_args
from .alertmanager_discovery_models import (
    AlertmanagerSource,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    DiscoveryResult,
)

# Module logger for debug output
_logger = logging.getLogger(__name__)


# --- Service Heuristic Discovery Strategy ---


class ServiceHeuristicDiscoveryStrategy(DiscoveryStrategy):
    """Discover Alertmanagers via service/pod heuristics.

    Lowest confidence method - looks for conventional service patterns
    and port configurations. Only used as fallback when CRD and Prometheus
    discovery methods fail or return empty results. Uses -A flag to search all namespaces.
    """

    name = "service-heuristic"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Search for Alertmanager-like services by name pattern."""
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        try:
            cmd = ["kubectl", "get", "svc", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "Service heuristic discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                errors.append(f"kubectl get svc failed: {result.stderr[:200]}")
                _logger.warning("Service heuristic discovery failed: %s", errors[-1])
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "Service heuristic discovery: found %d services across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_service_item(item, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "Service heuristic discovery: found service %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

            # Search for pods with app=alertmanager label
            pod_cmd = ["kubectl", "get", "pods", "-A", "-o", "json", "-l", "app=alertmanager"]
            pod_cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "Service heuristic discovery: searching all namespaces for pods",
            )

            pod_result = subprocess.run(pod_cmd, capture_output=True, text=True, timeout=30)

            if pod_result.returncode == 0:
                pod_data = json.loads(pod_result.stdout)
                pod_items = pod_data.get("items", [])

                _logger.debug(
                    "Service heuristic discovery: found %d pods with app=alertmanager label",
                    len(pod_items),
                )

                for pod in pod_items:
                    source = self._parse_pod_item(pod, context, cluster_uid)
                    if source:
                        if not any(s.source_id == source.source_id for s in sources):
                            sources.append(source)
                            _logger.debug(
                                "Service heuristic discovery: found pod %s in namespace %s",
                                source.name,
                                source.namespace,
                            )

        except subprocess.TimeoutExpired:
            errors.append("Service/pod discovery timed out")
            _logger.warning("Service heuristic discovery timed out")
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            _logger.warning("kubectl not found in PATH for service heuristic discovery")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse service heuristic output: {exc}")
            _logger.warning("Failed to parse service heuristic discovery output: %s", exc)

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_service_item(
        self,
        item: dict[str, Any],
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse a service to check if it's an Alertmanager service."""
        metadata = item.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")

        name_lower = name.lower()
        if "alertmanager" not in name_lower:
            return None

        ports = item.get("spec", {}).get("ports", [])
        has_am_port = any(p.get("port") == 9093 for p in ports)

        source_id = f"service:{namespace}/{name}"
        endpoint = f"http://{name}.{namespace}:9093"

        return AlertmanagerSource(
            source_id=source_id,
            endpoint=endpoint,
            namespace=namespace,
            name=name,
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            state=AlertmanagerSourceState.DISCOVERED,
            confidence_hints=(
                "from-service",
                "port=9093" if has_am_port else "port=unknown",
            ),
            cluster_uid=cluster_uid,
        )

    def _parse_pod_item(
        self,
        item: dict[str, Any],
        context: str | None,
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse a pod to extract Alertmanager info."""
        metadata = item.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")

        pod_ip = item.get("status", {}).get("podIP")
        if not pod_ip:
            return None

        object_uid: str | None = metadata.get("uid")
        source_id = f"pod:{namespace}/{name}"

        return AlertmanagerSource(
            source_id=source_id,
            endpoint=f"http://{pod_ip}:9093",
            namespace=namespace,
            name=name,
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            state=AlertmanagerSourceState.DISCOVERED,
            confidence_hints=("from-pod-label",),
            cluster_uid=cluster_uid,
            object_uid=object_uid,
        )


__all__ = [
    "ServiceHeuristicDiscoveryStrategy",
]

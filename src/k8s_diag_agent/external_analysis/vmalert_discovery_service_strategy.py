"""vmalert service-based discovery strategy.

This module provides the service heuristic discovery strategy:
- ServiceHeuristicDiscoveryStrategy: Discover via service name/labels/ports heuristics

The module answers: "Given cluster context, find vmalert instances via service patterns."

It does NOT include:
- CRD-based discovery (see vmalert_discovery_crd_strategy)
- Source/endpoint construction (see vmalert_discovery_sources)
- HTTP verification of endpoints
- High-level orchestration of discovery runs
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .vmalert_discovery_crd_strategy import DiscoveryStrategy, _kubectl_context_args
from .vmalert_discovery_models import (
    DiscoveryResult,
    VmalertSource,
    VmalertSourceOrigin,
    VmalertSourceState,
)

# Module logger for debug output
_logger = logging.getLogger(__name__)


# --- Service Heuristic Discovery Strategy ---


class ServiceHeuristicDiscoveryStrategy(DiscoveryStrategy):
    """Discover vmalert via service heuristics.

    Lowest confidence method - looks for conventional service patterns
    and port configurations. Primary fallback when CRD is not available.
    """

    name = "service-heuristic"

    # Likely namespace patterns for VictoriaMetrics stack
    LIKELY_NAMESPACES = frozenset({
        'victoria-metrics-k8s-stack',
        'monitoring',
        'victoria-metrics',
        'vm',
    })

    # Likely port names for vmalert HTTP endpoints
    LIKELY_PORT_NAMES = frozenset({
        'http',
        'web',
        'metrics',
        'api',
        'vmalert',
    })

    # Likely port numbers
    LIKELY_PORTS = frozenset({8080, 8880})

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Search for vmalert services by name pattern and labels."""
        import subprocess

        sources: list[VmalertSource] = []
        errors: list[str] = []

        try:
            # Search all namespaces for services
            cmd = ["kubectl", "get", "svc", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "vmalert service heuristic discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    _logger.debug("vmalert service discovery: no services found")
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl get svc failed: {result.stderr[:200]}")
                # Do NOT emit unstructured warning - orchestrator handles structured event
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "vmalert service heuristic discovery: found %d services across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_service_item(item, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "vmalert service heuristic discovery: found service %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

        except subprocess.TimeoutExpired:
            errors.append("vmalert service discovery timed out")
            # Do NOT emit unstructured warning - orchestrator handles structured event
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            # Do NOT emit unstructured warning - orchestrator handles structured event
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse kubectl output: {exc}")
            # Do NOT emit unstructured warning - orchestrator handles structured event

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_service_item(
        self,
        item: dict[str, Any],
        cluster_uid: str | None,
    ) -> VmalertSource | None:
        """Parse a service to check if it's a vmalert service."""
        metadata = item.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")
        labels = metadata.get("labels", {})

        # Check name patterns for vmalert - name match is primary
        name_lower = name.lower()
        if not self._matches_vmalert_name(name_lower):
            return None

        # Check labels - optional if name match is strong, but raises confidence
        has_labels = self._matches_vmalert_labels(labels)
        # Require label match only if name doesn't clearly indicate vmalert
        if not has_labels and not name_lower.startswith("vmalert-"):
            return None

        # Extract port information
        spec = item.get("spec", {})
        ports = spec.get("ports", [])
        target_port = self._extract_vmalert_port(ports)

        if target_port is None:
            return None

        # Capture object UID
        object_uid: str | None = metadata.get("uid")

        source_id = f"service:{namespace}/{name}"

        # Construct canonical in-cluster DNS URL
        endpoint = f"http://{name}.{namespace}.svc:{target_port}"

        # Build confidence hints
        confidence_hints: list[str] = ["from-service"]
        if self._matches_likely_namespace(namespace):
            confidence_hints.append("likely-namespace")
        if self._matches_likely_port(ports):
            confidence_hints.append("likely-port")

        return VmalertSource(
            source_id=source_id,
            endpoint=endpoint,
            namespace=namespace,
            name=name,
            origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
            state=VmalertSourceState.DISCOVERED,
            confidence_hints=tuple(confidence_hints),
            cluster_uid=cluster_uid,
            object_uid=object_uid,
        )

    def _matches_vmalert_name(self, name_lower: str) -> bool:
        """Check if service name matches vmalert patterns."""
        # Exact or prefix match
        if name_lower.startswith("vmalert-"):
            return True
        # Contains match
        if "vmalert" in name_lower:
            return True
        return False

    def _matches_vmalert_labels(self, labels: dict[str, str]) -> bool:
        """Check if service labels indicate vmalert/VM operator ownership."""
        # Check for app.kubernetes.io labels
        app_name = labels.get("app.kubernetes.io/name", "")
        if "vmalert" in app_name.lower():
            return True

        component = labels.get("app.kubernetes.io/component", "")
        if "vmalert" in component.lower():
            return True

        # Check for VM operator labels
        if labels.get("operator.victoriametrics.com/name"):
            return True
        if labels.get("app") and "vmalert" in labels["app"].lower():
            return True

        return False

    def _extract_vmalert_port(self, ports: list[dict[str, Any]]) -> int | None:
        """Extract the most likely vmalert HTTP port from service ports."""
        # First, look for ports by likely names
        for port_spec in ports:
            port_name = port_spec.get("name", "").lower()
            port_num = port_spec.get("port")
            if port_num and port_name in self.LIKELY_PORT_NAMES:
                return int(port_num)

        # Second, look for likely port numbers
        for port_spec in ports:
            port_num = port_spec.get("port")
            if port_num and int(port_num) in self.LIKELY_PORTS:
                return int(port_num)

        # Fallback: return first TCP port if available
        for port_spec in ports:
            if port_spec.get("protocol") == "TCP":
                return int(port_spec.get("port", 0))

        return None

    def _matches_likely_namespace(self, namespace: str) -> bool:
        """Check if namespace matches likely VM stack namespaces."""
        return namespace in self.LIKELY_NAMESPACES

    def _matches_likely_port(self, ports: list[dict[str, Any]]) -> bool:
        """Check if any port matches likely vmalert ports."""
        for port_spec in ports:
            if int(port_spec.get("port", 0)) in self.LIKELY_PORTS:
                return True
        return False


__all__ = [
    "ServiceHeuristicDiscoveryStrategy",
]

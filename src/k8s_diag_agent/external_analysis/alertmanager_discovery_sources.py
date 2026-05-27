"""Alertmanager source construction and discovery strategies.

This module provides the source construction logic for Alertmanager discovery:
- DiscoveryStrategy base class and concrete strategy implementations
- Context helper functions for kubectl commands
- Source construction helpers for manual endpoints
- Prometheus Operator alias resolution

The module answers: "Given config/Kubernetes objects/manual endpoint data,
construct AlertmanagerSource or DiscoveryResult objects."

It does NOT include:
- HTTP verification of Alertmanager endpoints
- High-level orchestration of discovery runs
- Inventory persistence/loading/writing
- Final inventory merge/dedup orchestration
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .alertmanager_discovery_models import (
    AlertmanagerSource,
    AlertmanagerSourceMode,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    DiscoveryResult,
)

# Module logger for debug output
_logger = logging.getLogger(__name__)


# --- Context Helpers for kubectl commands ---


# In-cluster context sentinel (matches live_snapshot.py behavior)
_IN_CLUSTER_CONTEXT = "in-cluster"


def _should_add_context_flag(context: str | None) -> bool:
    """Determine if kubectl should use --context flag.
    
    In-cluster mode (context == "in-cluster") must NOT pass --context because:
    - kubectl uses service account token automatically in-cluster
    - Passing "--context in-cluster" fails with "context was not found for specified context"
    
    Kubeconfig contexts (any other non-None value) should use --context.
    """
    if context is None:
        return False
    # In-cluster mode: rely on service account auth without --context
    # Kubeconfig mode: pass --context to select the named context
    return context != _IN_CLUSTER_CONTEXT


def _kubectl_context_args(context: str | None) -> list[str]:
    """Return kubectl --context args based on context value.

    - None -> []
    - "in-cluster" -> []
    - "real-context" -> ["--context", "real-context"]

    This helper avoids mypy list-item errors when adding context to kubectl commands.
    """
    if context is None or context == _IN_CLUSTER_CONTEXT:
        return []
    return ["--context", context]


# --- Discovery Strategy Interfaces ---


class DiscoveryStrategy:
    """Base class for Alertmanager discovery strategies."""

    name: str = "base"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Discover Alertmanager sources.

        Args:
            context: Kubernetes context to use for discovery
            cluster_uid: Canonical cluster identity for cross-cluster disambiguation

        Returns:
            DiscoveryResult with found sources and any errors
        """
        raise NotImplementedError


# --- CRD Discovery Strategy ---


class CRDDiscoveryStrategy(DiscoveryStrategy):
    """Discover Alertmanagers via monitoring.coreos.com/v1 Alertmanager CRDs.

    This is the highest-confidence discovery method as it uses the official
    Kubernetes API for Alertmanager resources. Uses -A flag to search all namespaces.
    """

    name = "alertmanager-crd"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Query Alertmanager CRDs using kubectl.

        Uses `kubectl get alertmanagers -A` to find all Alertmanager resources
        in all namespaces, then resolves their service endpoints.

        The -A flag is required because kube contexts may default to namespace
        'default' while Alertmanager resources typically live in 'monitoring'.
        
        Note: When context is "in-cluster", --context is NOT passed to kubectl
        because in-cluster mode uses service account authentication automatically.
        """
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        try:
            # Use -A to search ALL namespaces (required for cross-namespace discovery)
            cmd = ["kubectl", "get", "alertmanagers", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "Alertmanager CRD discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # CRD may not be installed or kubectl may not be available
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    # CRD not present, return empty
                    _logger.debug(
                        "Alertmanager CRD discovery: no Alertmanager CRDs found in any namespace",
                    )
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl failed: {result.stderr[:200]}")
                _logger.warning(
                    "Alertmanager CRD discovery failed: %s",
                    errors[-1],
                )
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "Alertmanager CRD discovery: found %d Alertmanager CRDs across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_crd_item(item, context, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "Alertmanager CRD discovery: found source %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

        except subprocess.TimeoutExpired:
            errors.append("kubectl get alertmanagers timed out")
            _logger.warning("Alertmanager CRD discovery timed out")
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            _logger.warning("kubectl not found in PATH for Alertmanager CRD discovery")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse kubectl output: {exc}")
            _logger.warning("Failed to parse Alertmanager CRD discovery output: %s", exc)

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_crd_item(
        self,
        item: dict[str, Any],
        context: str | None,
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse an Alertmanager CRD item into a source."""
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", "default")

        if not name:
            return None

        # Capture native Kubernetes object UID (highest confidence identity anchor)
        object_uid: str | None = metadata.get("uid")

        # Build the service URL - Alertmanager is typically on port 9093
        # For in-cluster access, we construct the service DNS name
        endpoint = f"http://alertmanager-operated.{namespace}:9093"  # conventional for Prometheus Operator

        source_id = f"crd:{namespace}/{name}"

        return AlertmanagerSource(
            source_id=source_id,
            endpoint=endpoint,
            namespace=namespace,
            name=name,
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
            confidence_hints=("from-crd", f"namespace={namespace}"),
            cluster_uid=cluster_uid,
            object_uid=object_uid,
        )


# --- Prometheus CRD Config Discovery Strategy ---


class PrometheusCRDConfigDiscoveryStrategy(DiscoveryStrategy):
    """Discover Alertmanagers via Prometheus CRD alertmanagers configuration.

    This method looks for Prometheus instances that reference Alertmanagers
    in their alerting.alertmanagers spec. Lower confidence than direct CRD
    as it relies on Prometheus configuration rather than direct inspection.
    Uses -A flag to search all namespaces.
    """

    name = "prometheus-crd-config"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Look for Prometheus resources and their Alertmanager configurations.

        Uses `kubectl get prometheuses -A` to search all namespaces.
        
        Note: When context is "in-cluster", --context is NOT passed to kubectl
        because in-cluster mode uses service account authentication automatically.
        """
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        try:
            # Use -A to search ALL namespaces
            cmd = ["kubectl", "get", "prometheuses", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "Prometheus CRD config discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Prometheus CRD may not be installed
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    _logger.debug(
                        "Prometheus CRD config discovery: no Prometheus CRDs found",
                    )
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl prometheuses failed: {result.stderr[:200]}")
                _logger.warning(
                    "Prometheus CRD config discovery failed: %s",
                    errors[-1],
                )
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "Prometheus CRD config discovery: found %d Prometheus CRDs across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_prometheus_item(item, context, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "Prometheus CRD config discovery: found Alertmanager reference %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

        except subprocess.TimeoutExpired:
            errors.append("kubectl get prometheuses timed out")
            _logger.warning("Prometheus CRD config discovery timed out")
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            _logger.warning("kubectl not found in PATH for Prometheus CRD config discovery")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse kubectl output: {exc}")
            _logger.warning("Failed to parse Prometheus CRD config discovery output: %s", exc)

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_prometheus_item(
        self,
        item: dict[str, Any],
        context: str | None,
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse a Prometheus CRD item to extract Alertmanager info."""
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", "default")

        spec = item.get("spec", {})

        # Look for alerting configuration
        alerting = spec.get("alerting", {})
        alertmanagers = alerting.get("alertmanagers", [])

        for am in alertmanagers:
            # Prometheus Operator alertmanagers typically point to the operated service
            namespace = am.get("namespace", namespace)
            name = am.get("name", "alertmanager-main")

            source_id = f"prom-crd-config:{namespace}/{name}"
            endpoint = f"http://alertmanager-operated.{namespace}:9093"

            return AlertmanagerSource(
                source_id=source_id,
                endpoint=endpoint,
                namespace=namespace,
                name=name,
                origin=AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
                state=AlertmanagerSourceState.DISCOVERED,
                confidence_hints=("from-prometheus-crd-config",),
                cluster_uid=cluster_uid,
            )

        return None


# --- Service Heuristic Discovery Strategy ---


class ServiceHeuristicDiscoveryStrategy(DiscoveryStrategy):
    """Discover Alertmanagers via service/pod heuristics.

    Lowest confidence method - looks for conventional service patterns
    and port configurations. Only used as fallback when CRD and Prometheus
    discovery methods fail or return empty results. Uses -A flag to search all namespaces.
    """

    name = "service-heuristic"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Search for Alertmanager-like services by name pattern.

        Uses `kubectl get svc -A` and `kubectl get pods -A -l app=alertmanager`
        to search all namespaces. This is required because kube contexts may
        default to namespace 'default' while Alertmanager resources typically
        live in 'monitoring'.
        
        Note: When context is "in-cluster", --context is NOT passed to kubectl
        because in-cluster mode uses service account authentication automatically.
        """
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        # Search for services with alertmanager-related names

        try:
            # Use -A to search ALL namespaces for services
            cmd = ["kubectl", "get", "svc", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "Service heuristic discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                errors.append(f"kubectl get svc failed: {result.stderr[:200]}")
                _logger.warning(
                    "Service heuristic discovery failed: %s",
                    errors[-1],
                )
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

            # Use -A to search ALL namespaces for pods with app=alertmanager label
            pod_cmd = ["kubectl", "get", "pods", "-A", "-o", "json", "-l", "app=alertmanager"]
            pod_cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "Service heuristic discovery: searching all namespaces for pods with command: %s",
                " ".join(pod_cmd),
            )

            pod_result = subprocess.run(
                pod_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

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
                        # Avoid duplicates from service discovery
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

        # Check if name matches alertmanager patterns
        name_lower = name.lower()
        if "alertmanager" not in name_lower:
            return None

        # Check for port 9093 (standard Alertmanager port)
        ports = item.get("spec", {}).get("ports", [])
        has_am_port = any(p.get("port") == 9093 for p in ports)

        if not has_am_port:
            # Still might be Alertmanager, just different port
            pass

        source_id = f"service:{namespace}/{name}"

        # Construct cluster-internal URL
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

        # Extract pod IP
        pod_ip = item.get("status", {}).get("podIP")
        if not pod_ip:
            return None

        # Capture native Kubernetes object UID (optional identity anchor)
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


# --- Manual Source Construction ---


def build_endpoint_for_manual(
    endpoint: str,
    namespace: str | None = None,
    name: str | None = None,
) -> AlertmanagerSource:
    """Build a manual Alertmanager source from user-provided endpoint.
    
    The source is marked as operator-configured to distinguish it from
    promoted sources (which preserve their discovery origin).
    """
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"

    source_id = f"manual:{endpoint}"
    if namespace and name:
        source_id = f"manual:{namespace}/{name}"

    return AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=AlertmanagerSourceOrigin.MANUAL,
        state=AlertmanagerSourceState.MANUAL,
        manual_source_mode=AlertmanagerSourceMode.OPERATOR_CONFIGURED,
    )


# --- Prometheus Operator Alias Resolution ---


def _resolve_prometheus_operator_alias(
    source: AlertmanagerSource,
    all_sources: dict[str, AlertmanagerSource],
) -> AlertmanagerSource:
    """Resolve Prometheus Operator alias: alertmanager-operated -> CRD-backed AM.
    
    In Prometheus Operator deployments:
    - CRD is named 'alertmanager-main' (or similar)
    - The actual service is 'alertmanager-operated' (conventional suffix)
    
    When a service heuristic finds 'alertmanager-operated', it should share the
    same canonical identity as the CRD-backed Alertmanager in the same namespace
    IF there's an unambiguous mapping (only one CRD Alertmanager in that namespace).
    
    This ensures that:
    - CRD source: monitoring/alertmanager-main (points to alertmanager-operated.monitoring:9093)
    - Service source: monitoring/alertmanager-operated (same endpoint)
    
    Both resolve to canonical identity 'monitoring/alertmanager-main' (the CRD's name).
    """
    # Only apply alias resolution for service heuristic sources
    if source.origin != AlertmanagerSourceOrigin.SERVICE_HEURISTIC:
        return source
    
    # Check if this is the alertmanager-operated pattern
    name = source.name or ''
    if not name.endswith('-operated'):
        return source
    
    # Find CRD sources in the same namespace
    crd_in_namespace = [
        s for s in all_sources.values()
        if s.namespace == source.namespace
        and s.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
    ]
    
    # Only apply when there's exactly one CRD Alertmanager in this namespace
    # (unambiguous mapping)
    if len(crd_in_namespace) != 1:
        return source
    
    crd_source = crd_in_namespace[0]
    
    # Create aliased source with CRD's namespace/name but keep service's endpoint
    # (since they both point to the same endpoint: alertmanager-operated.svc:9093)
    # Preserve identity anchors from the source (cluster_uid/object_uid)
    aliased_source = AlertmanagerSource(
        source_id=f'service:{source.namespace}/{crd_source.name}',  # Use CRD name
        endpoint=source.endpoint,  # Keep the actual endpoint
        namespace=source.namespace,
        name=crd_source.name,  # Use CRD name for canonical identity
        origin=source.origin,
        state=source.state,
        discovered_at=source.discovered_at,
        verified_at=source.verified_at,
        last_check=source.last_check,
        last_error=source.last_error,
        verified_version=source.verified_version,
        confidence_hints=source.confidence_hints + ('prometheus-operator-alias',),
        merged_provenances=source.merged_provenances,
        cluster_label=source.cluster_label,
        cluster_context=source.cluster_context,
        cluster_uid=source.cluster_uid,
        object_uid=source.object_uid,
    )
    
    _logger.debug(
        'Resolved Prometheus Operator alias: %s/%s -> %s/%s (endpoint %s)',
        source.namespace,
        source.name,
        source.namespace,
        crd_source.name,
        source.endpoint,
    )
    
    return aliased_source


# --- Re-exports for backward compatibility ---

__all__ = [
    # Sentinel constant
    "_IN_CLUSTER_CONTEXT",
    # Context helpers
    "_should_add_context_flag",
    "_kubectl_context_args",
    # Strategy classes
    "DiscoveryStrategy",
    "CRDDiscoveryStrategy",
    "PrometheusCRDConfigDiscoveryStrategy",
    "ServiceHeuristicDiscoveryStrategy",
    # Source construction
    "build_endpoint_for_manual",
    "_resolve_prometheus_operator_alias",
]
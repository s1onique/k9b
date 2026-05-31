"""Alertmanager CRD-based discovery strategies.

This module provides the CRD-based discovery strategy classes:
- DiscoveryStrategy: Base class interface
- CRDDiscoveryStrategy: Discover via monitoring.coreos.com/v1 Alertmanager CRDs
- PrometheusCRDConfigDiscoveryStrategy: Discover via Prometheus CRD alerting config

The module answers: "Given cluster context, find Alertmanager instances via CRD APIs."

It does NOT include:
- Service/pod heuristics (see alertmanager_discovery_service_strategy)
- Source/endpoint construction (see alertmanager_discovery_sources)
- HTTP verification of endpoints
- High-level orchestration of discovery runs
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .alertmanager_discovery_models import (
    AlertmanagerSource,
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
    return context != _IN_CLUSTER_CONTEXT


def _kubectl_context_args(context: str | None) -> list[str]:
    """Return kubectl --context args based on context value."""
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
        """Query Alertmanager CRDs using kubectl."""
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        try:
            cmd = ["kubectl", "get", "alertmanagers", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "Alertmanager CRD discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    _logger.debug(
                        "Alertmanager CRD discovery: no Alertmanager CRDs found in any namespace",
                    )
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl failed: {result.stderr[:200]}")
                _logger.warning("Alertmanager CRD discovery failed: %s", errors[-1])
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "Alertmanager CRD discovery: found %d Alertmanager CRDs across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_crd_item(item, cluster_uid)
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
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse an Alertmanager CRD item into a source."""
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", "default")

        if not name:
            return None

        object_uid: str | None = metadata.get("uid")
        endpoint = f"http://alertmanager-operated.{namespace}:9093"
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
    in their alerting.alertmanagers spec. Uses -A flag to search all namespaces.
    """

    name = "prometheus-crd-config"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Look for Prometheus resources and their Alertmanager configurations."""
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        try:
            cmd = ["kubectl", "get", "prometheuses", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "Prometheus CRD config discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    _logger.debug(
                        "Prometheus CRD config discovery: no Prometheus CRDs found",
                    )
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl prometheuses failed: {result.stderr[:200]}")
                _logger.warning("Prometheus CRD config discovery failed: %s", errors[-1])
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "Prometheus CRD config discovery: found %d Prometheus CRDs across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_prometheus_item(item, cluster_uid)
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
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse a Prometheus CRD item to extract Alertmanager info."""
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", "default")

        spec = item.get("spec", {})
        alerting = spec.get("alerting", {})
        alertmanagers = alerting.get("alertmanagers", [])

        for am in alertmanagers:
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


# --- Re-exports for backward compatibility ---

__all__ = [
    "_IN_CLUSTER_CONTEXT",
    "_should_add_context_flag",
    "_kubectl_context_args",
    "DiscoveryStrategy",
    "CRDDiscoveryStrategy",
    "PrometheusCRDConfigDiscoveryStrategy",
]

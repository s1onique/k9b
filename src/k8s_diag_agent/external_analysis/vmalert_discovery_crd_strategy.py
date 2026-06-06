"""vmalert CRD-based discovery strategy.

This module provides the CRD-based discovery strategy class:
- DiscoveryStrategy: Base class interface
- VMAlertCRDDiscoveryStrategy: Discover via VMAlert CRDs (VictoriaMetrics Operator)

The module answers: "Given cluster context, find vmalert instances via CRD APIs."

It does NOT include:
- Service heuristics (see vmalert_discovery_service_strategy)
- Source/endpoint construction (see vmalert_discovery_sources)
- HTTP verification of endpoints
- High-level orchestration of discovery runs
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .vmalert_discovery_models import (
    DiscoveryResult,
    VmalertSource,
    VmalertSourceOrigin,
    VmalertSourceState,
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
    """Base class for vmalert discovery strategies."""

    name: str = "base"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Discover vmalert sources.

        Args:
            context: Kubernetes context to use for discovery
            cluster_uid: Canonical cluster identity for cross-cluster disambiguation

        Returns:
            DiscoveryResult with found sources and any errors
        """
        raise NotImplementedError


# --- CRD Discovery Strategy ---


class VMAlertCRDDiscoveryStrategy(DiscoveryStrategy):
    """Discover vmalert via VMAlert CRDs (VictoriaMetrics Operator).

    This is the highest-confidence discovery method as it uses the official
    VictoriaMetrics Operator CRD API for vmalert resources.
    """

    name = "vmalert-crd"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Query VMAlert CRDs using kubectl."""
        import subprocess

        sources: list[VmalertSource] = []
        errors: list[str] = []

        try:
            # Try VictoriaMetrics Operator CRDs
            cmd = ["kubectl", "get", "vmalerts", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "vmalert CRD discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if "not found" in stderr_lower or "no resources" in stderr_lower:
                    _logger.debug(
                        "vmalert CRD discovery: VMAlert CRD not installed",
                    )
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                # Detect Forbidden errors for structured logging - errors returned in DiscoveryResult
                if "forbidden" in stderr_lower:
                    errors.append(f"kubectl failed: Forbidden - {result.stderr[:200]}")
                else:
                    errors.append(f"kubectl failed: {result.stderr[:200]}")
                # Do NOT emit unstructured warning - orchestrator handles structured event
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "vmalert CRD discovery: found %d VMAlert CRDs across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_crd_item(item, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "vmalert CRD discovery: found source %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

        except subprocess.TimeoutExpired:
            errors.append("kubectl get vmalerts timed out")
            # Do NOT emit unstructured warning - orchestrator handles structured event
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            # Do NOT emit unstructured warning - orchestrator handles structured event
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse kubectl output: {exc}")
            # Do NOT emit unstructured warning - orchestrator handles structured event

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_crd_item(
        self,
        item: dict[str, Any],
        cluster_uid: str | None,
    ) -> VmalertSource | None:
        """Parse a VMAlert CRD item into a source."""
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", "default")

        if not name:
            return None

        object_uid: str | None = metadata.get("uid")

        # Extract port from spec (VMAlert CRD typically specifies port)
        spec = item.get("spec", {})
        port = spec.get("port", 8080)  # Default to 8080

        source_id = f"crd:{namespace}/{name}"
        endpoint = f"http://{name}.{namespace}.svc:{port}"

        return VmalertSource(
            source_id=source_id,
            endpoint=endpoint,
            namespace=namespace,
            name=name,
            origin=VmalertSourceOrigin.VMALERT_CRD,
            state=VmalertSourceState.DISCOVERED,
            confidence_hints=("from-crd", f"namespace={namespace}"),
            cluster_uid=cluster_uid,
            object_uid=object_uid,
        )


# --- Re-exports for backward compatibility ---

__all__ = [
    "_IN_CLUSTER_CONTEXT",
    "_should_add_context_flag",
    "_kubectl_context_args",
    "DiscoveryStrategy",
    "VMAlertCRDDiscoveryStrategy",
]

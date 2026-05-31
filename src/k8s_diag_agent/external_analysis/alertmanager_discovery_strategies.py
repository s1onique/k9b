"""Alertmanager discovery strategy implementations.

This module re-exports all discovery strategy classes from sub-modules:
- alertmanager_discovery_crd_strategy: CRD-based strategies
- alertmanager_discovery_service_strategy: Service/pod heuristic strategy

The module provides a single import point for all strategies while keeping
each implementation below the 500-line LLM-friendly threshold.

It does NOT include:
- Source/endpoint construction (see alertmanager_discovery_sources)
- HTTP verification of endpoints
- High-level orchestration of discovery runs
"""

from __future__ import annotations

from .alertmanager_discovery_crd_strategy import (
    _IN_CLUSTER_CONTEXT,
    CRDDiscoveryStrategy,
    DiscoveryStrategy,
    PrometheusCRDConfigDiscoveryStrategy,
    _kubectl_context_args,
    _should_add_context_flag,
)
from .alertmanager_discovery_service_strategy import (
    ServiceHeuristicDiscoveryStrategy,
)

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
]

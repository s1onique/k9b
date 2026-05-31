"""vmalert source construction helpers.

This module provides the source construction logic for vmalert discovery:
- Source construction helpers for manual endpoints
- Endpoint/source-id construction helpers

The module answers: "Given config/manual endpoint data, construct VmalertSource objects."

It does NOT include:
- HTTP verification of vmalert endpoints
- High-level orchestration of discovery runs
- Inventory persistence/loading/writing
- Discovery strategies (see vmalert_discovery_strategies)
"""

from __future__ import annotations

import logging

from .vmalert_discovery_crd_strategy import (
    _IN_CLUSTER_CONTEXT,
    _kubectl_context_args,
    _should_add_context_flag,
)
from .vmalert_discovery_models import (
    VmalertSource,
    VmalertSourceMode,
    VmalertSourceOrigin,
    VmalertSourceState,
)

# Module logger for debug output
_logger = logging.getLogger(__name__)


# --- Manual Source Construction ---


def build_endpoint_for_manual(
    endpoint: str,
    namespace: str | None = None,
    name: str | None = None,
) -> VmalertSource:
    """Build a manual vmalert source from user-provided endpoint.

    The source is marked as operator-configured to distinguish it from
    promoted sources (which preserve their discovery origin).
    """
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"

    source_id = f"manual:{endpoint}"
    if namespace and name:
        source_id = f"manual:{namespace}/{name}"

    return VmalertSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=VmalertSourceOrigin.MANUAL,
        state=VmalertSourceState.MANUAL,
        manual_source_mode=VmalertSourceMode.OPERATOR_CONFIGURED,
    )


# --- Re-exports for backward compatibility ---

__all__ = [
    # Sentinel constant
    "_IN_CLUSTER_CONTEXT",
    # Context helpers
    "_should_add_context_flag",
    "_kubectl_context_args",
    # Source construction
    "build_endpoint_for_manual",
]

"""Alertmanager snapshot collection runner for health loop.

Extracts the Alertmanager snapshot collection flow from HealthLoopRunner into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides the snapshot collection logic that:
1. Selects eligible sources (MANUAL > AUTO_TRACKED) from verified inventory
2. Handles port-forward for cluster-internal endpoints
3. Fetches alerts from selected source via HTTP /api/v2/alerts
4. Writes snapshot and compact artifacts

Port-forward infrastructure (port selection, TCP polling, kubectl process management) remains
in loop.py and is injected as callable parameters to this module.

This module is a facade that re-exports from the implementation module.
Internal details are in loop_alertmanager_snapshot_impl.py, loop_alertmanager_snapshot_collection.py,
and loop_alertmanager_snapshot_signals.py.
"""

from __future__ import annotations

from .loop_alertmanager_snapshot_impl import (
    AlertSignalPromotionDispatchResult,
    run_alertmanager_snapshot_collection,
)

__all__ = [
    "AlertSignalPromotionDispatchResult",
    "run_alertmanager_snapshot_collection",
]

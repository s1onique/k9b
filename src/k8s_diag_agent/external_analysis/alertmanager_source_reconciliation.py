"""Alertmanager source reconciliation.

This module provides reconciliation logic that collapses previously detected duplicate
Alertmanager sources into one logical source while preserving all raw discovery
evidence as aliases/provenance.

The reconciliation handles the Prometheus Operator pattern where:
- alertmanager-operated (headless) - operator governing service
- kube-prometheus-stack-alertmanager (chart service) - user-facing service

Both point to the same Alertmanager backing pods and should be collapsed into one
logical source.

See also:
- alertmanager_source_reconciliation_keys: core identity types
- alertmanager_source_reconciliation_grouping: grouping helpers
- alertmanager_source_reconciliation_merge: merge logic
- alertmanager_source_registry_reconciliation: registry persistence
"""

# Re-export all public types and functions from split modules
from .alertmanager_source_reconciliation_grouping import (
    ReconciliationGroup,
    build_backing_identity_cache,
    group_sources_by_backing_identity,
)
from .alertmanager_source_reconciliation_keys import (
    LogicalSourceKey,
    compute_logical_source_key,
    normalize_endpoint,
)
from .alertmanager_source_reconciliation_merge import (
    reconcile_alertmanager_sources,
)
from .alertmanager_source_registry_reconciliation import (
    detect_duplicate_registry_entries,
)

__all__ = [
    # Keys module
    "LogicalSourceKey",
    "compute_logical_source_key",
    "normalize_endpoint",
    # Grouping module
    "ReconciliationGroup",
    "build_backing_identity_cache",
    "group_sources_by_backing_identity",
    # Merge module
    "reconcile_alertmanager_sources",
    # Registry module
    "detect_duplicate_registry_entries",
]

"""Monitoring discovery and collection helpers for health loop runner.

This module contains helper methods for Alertmanager and vmalert discovery
and collection that are delegated from HealthLoopRunner.

Extracted from loop_runner.py for LLM-friendly file sizes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .loop_alertmanager_discovery import run_alertmanager_discovery as _run_alertmanager_discovery_impl
from .loop_alertmanager_port_forward import (
    start_alertmanager_port_forward,
    stop_alertmanager_port_forward,
)
from .loop_alertmanager_snapshot import run_alertmanager_snapshot_collection as _run_alertmanager_snapshot_collection_impl
from .loop_port_forward_helpers import _choose_free_local_port, _wait_for_port_ready
from .loop_vmalert_discovery import run_vmalert_discovery as _run_vmalert_discovery_impl
from .loop_vmalert_rule_state import run_vmalert_rule_state_collection as _run_vmalert_rule_state_collection_impl

if TYPE_CHECKING:
    import subprocess

    from ..external_analysis.alertmanager_discovery import AlertmanagerSourceInventory
    from ..external_analysis.vmalert_discovery import VmalertSourceInventory


class LogEvent(Protocol):
    """Protocol for logging event callbacks with keyword-only metadata."""

    def __call__(
        self,
        component: str,
        severity: str,
        message: str,
        **metadata: Any,
    ) -> None: ...


def run_monitoring_discovery_and_collection(
    records: list[Any],
    directories: dict[str, Path],
    run_id: str,
    run_label: str,
    log_event_fn: LogEvent,
    start_port_forward_fn: Callable[..., tuple[subprocess.Popen[str], int]],
    stop_port_forward_fn: Callable[..., None],
    choose_free_local_port_fn: Callable[[], int],
    wait_for_port_ready_fn: Callable[..., bool],
) -> tuple[AlertmanagerSourceInventory | None, VmalertSourceInventory | None]:
    """Run Alertmanager and vmalert discovery and collection.

    This is a convenience function that runs both Alertmanager and vmalert
    discovery, followed by snapshot/rule state collection.

    Args:
        records: List of health snapshot records.
        directories: Output directories.
        run_id: Run identifier.
        run_label: Run label.
        log_event_fn: Logging function.
        start_port_forward_fn: Function to start port-forward.
        stop_port_forward_fn: Function to stop port-forward.
        choose_free_local_port_fn: Function to choose a free port.
        wait_for_port_ready_fn: Function to wait for port readiness.

    Returns:
        Tuple of (alertmanager_inventory, vmalert_inventory).
    """
    # Run Alertmanager discovery
    alertmanager_inventory = run_alertmanager_discovery(
        records=records,
        directories=directories,
        log_event=log_event_fn,
        run_id=run_id,
    )

    # Run Alertmanager snapshot collection
    run_alertmanager_snapshot_collection(
        inventory=alertmanager_inventory,
        run_id=run_id,
        run_label=run_label,
        log_event=log_event_fn,
        directories=directories,
        start_port_forward=start_port_forward_fn,
        stop_port_forward=stop_port_forward_fn,
    )

    # Run vmalert discovery
    vmalert_inventory = run_vmalert_discovery(
        records=records,
        directories=directories,
        log_event=log_event_fn,
        run_id=run_id,
    )

    # Collect vmalert rule state
    run_vmalert_rule_state_collection(
        inventory=vmalert_inventory,
        directories=directories,
        run_id=run_id,
        cluster_label=run_label,
    )

    return alertmanager_inventory, vmalert_inventory


def run_alertmanager_discovery(
    records: list[Any],
    directories: dict[str, Path],
    log_event: LogEvent,
    run_id: str,
) -> AlertmanagerSourceInventory | None:
    """Run Alertmanager discovery for each cluster target.

    Delegates to loop_alertmanager_discovery module.
    """
    return _run_alertmanager_discovery_impl(
        records=records,
        directories=directories,
        log_event=log_event,
        run_id=run_id,
    )


def run_alertmanager_snapshot_collection(
    inventory: AlertmanagerSourceInventory | None,
    run_id: str,
    run_label: str,
    log_event: LogEvent,
    directories: dict[str, Path],
    start_port_forward: Callable[..., tuple[subprocess.Popen[str], int]],
    stop_port_forward: Callable[..., None],
) -> None:
    """Collect Alertmanager snapshot and compact artifacts for tracked sources.

    Delegates to loop_alertmanager_snapshot module.
    """
    _run_alertmanager_snapshot_collection_impl(
        inventory=inventory,
        run_id=run_id,
        run_label=run_label,
        log_event=log_event,
        directories=directories,
        start_port_forward=start_port_forward,
        stop_port_forward=stop_port_forward,
    )


def run_vmalert_discovery(
    records: list[Any],
    directories: dict[str, Path],
    log_event: LogEvent,
    run_id: str,
) -> VmalertSourceInventory | None:
    """Run vmalert discovery for each cluster target.

    Delegates to loop_vmalert_discovery module.
    """
    return _run_vmalert_discovery_impl(
        records=records,
        directories=directories,
        log_event=log_event,
        run_id=run_id,
    )


def run_vmalert_rule_state_collection(
    inventory: VmalertSourceInventory | None,
    directories: dict[str, Path],
    run_id: str,
    cluster_label: str,
) -> None:
    """Collect vmalert rule state from discovered sources.

    Delegates to loop_vmalert_rule_state module.
    """
    _run_vmalert_rule_state_collection_impl(
        inventory=inventory,
        directories=directories,
        run_id=run_id,
        cluster_label=cluster_label,
    )


# Port-forward helpers for delegation
start_alertmanager_port_forward_fn = start_alertmanager_port_forward
stop_alertmanager_port_forward_fn = stop_alertmanager_port_forward
choose_free_local_port_fn = _choose_free_local_port
wait_for_port_ready_fn = _wait_for_port_ready

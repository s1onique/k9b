"""Compatibility delegator methods extracted from HealthLoopRunner.

This module provides the instance-based interface expected by existing tests
and production call sites. Each method delegates to a pure helper function.

These methods preserve the HealthLoopRunner contract by wrapping pure
extracted helpers from loop_runner_*.py modules.

These helpers do NOT import HealthLoopRunner.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..external_analysis.alertmanager_discovery import AlertmanagerSourceInventory
    from ..external_analysis.vmalert_discovery import VmalertSourceInventory


class LogEventFn:
    """Protocol for logging event callbacks."""

    def __call__(
        self,
        component: str,
        severity: str,
        message: str,
        **metadata: Any,
    ) -> None: ...


def run_auto_drilldown_analysis_compat(
    runner: Any,
    drilldowns: list[Any],
    directories: dict[str, Path],
) -> list[Any]:
    """Compatibility wrapper for auto-drilldown analysis.

    This is a delegator that wraps run_auto_drilldown_analysis
    from loop_runner_drilldown_analysis, providing the instance-based interface
    expected by existing tests and production call sites.
    """
    from .loop_runner_drilldown_analysis import run_auto_drilldown_analysis as impl

    provider_name = runner.config.external_analysis.auto_drilldown.provider
    # No default fallback - let the impl decide if provider is not configured
    return impl(
        drilldowns=drilldowns,
        directories=directories,
        run_id=runner.run_id,
        run_label=runner.run_label,
        auto_drilldown_policy=runner.config.external_analysis.auto_drilldown,
        provider_name=provider_name,
        log_event_fn=runner._log_event,
    )


def run_alertmanager_discovery_compat(
    runner: Any,
    records: list[Any],
    directories: dict[str, Path],
) -> AlertmanagerSourceInventory | None:
    """Compatibility wrapper for Alertmanager discovery.

    This is a delegator that wraps run_alertmanager_discovery
    from loop_runner_monitoring.
    """
    from .loop_runner_monitoring import run_alertmanager_discovery as impl

    runner._alertmanager_inventory = impl(
        records=records,
        directories=directories,
        log_event=runner._log_event,
        run_id=runner.run_id,
    )
    return runner._alertmanager_inventory  # type: ignore[no-any-return]


def run_alertmanager_snapshot_collection_compat(
    runner: Any,
    directories: dict[str, Path],
) -> None:
    """Compatibility wrapper for Alertmanager snapshot collection.

    This is a delegator that wraps run_alertmanager_snapshot_collection
    from loop_runner_monitoring.
    """
    from .loop_runner_monitoring import run_alertmanager_snapshot_collection as impl

    impl(
        inventory=runner._alertmanager_inventory,
        run_id=runner.run_id,
        run_label=runner.run_label,
        log_event=runner._log_event,
        directories=directories,
        start_port_forward=runner._start_alertmanager_port_forward,
        stop_port_forward=runner._stop_alertmanager_port_forward,
    )


def run_vmalert_discovery_compat(
    runner: Any,
    records: list[Any],
    directories: dict[str, Path],
) -> VmalertSourceInventory | None:
    """Compatibility wrapper for vmalert discovery.

    This is a delegator that wraps run_vmalert_discovery
    from loop_runner_monitoring.
    """
    from .loop_runner_monitoring import run_vmalert_discovery as impl

    runner._vmalert_inventory = impl(
        records=records,
        directories=directories,
        log_event=runner._log_event,
        run_id=runner.run_id,
    )
    return runner._vmalert_inventory  # type: ignore[no-any-return]


def run_automatic_diagnosis_loop_compat(
    runner: Any,
    external_analysis_dir: Path,
) -> dict[str, Any]:
    """Compatibility wrapper for automatic diagnosis loop.

    This is a delegator that wraps run_automatic_diagnosis_loop
    from loop_automatic_diagnosis, providing the instance-based interface
    expected by existing tests and production call sites.

    Args:
        runner: HealthLoopRunner instance
        external_analysis_dir: Path to the external-analysis directory

    Returns:
        Bounded result summary dict with:
        - automatic_diagnosis_enabled: bool
        - collector_run_id: str | None
        - incidents_processed: int
        - incidents_eligible: int
        - incidents_skipped: int
        - incidents_with_errors: int
        - total_review_packets_written: int
    """
    # Import from loop_runner module namespace to respect patches in tests
    from . import loop_runner

    return loop_runner.run_automatic_diagnosis_loop(
        external_analysis_dir=external_analysis_dir,
        log_event_fn=runner._log_event,
    )


def failure_metadata_field_compat(
    metadata: dict[str, object] | None,
    field_name: str,
) -> str | bool | None:
    """Extract a field from failure metadata, checking top-level and nested prompt_diagnostics.

    This static helper provides backward compatibility for code that references
    HealthLoopRunner._failure_metadata_field. The actual implementation is in
    loop_failure_metadata.extract_failure_metadata_field.
    """
    from .loop_failure_metadata import extract_failure_metadata_field as impl

    return impl(metadata, field_name)


def start_alertmanager_port_forward_compat(
    runner: Any,
    namespace: str,
    service_name: str,
    context: str | None,
) -> tuple:
    """Compatibility wrapper for starting Alertmanager port-forward.

    This is a delegator that wraps start_alertmanager_port_forward
    from loop_alertmanager_port_forward.
    """
    from .loop_alertmanager_port_forward import start_alertmanager_port_forward as impl

    return impl(
        namespace=namespace,
        service_name=service_name,
        context=context,
        run_id=runner.run_id,
        run_label=runner.run_label,
        log_event=runner._log_event,
        choose_free_local_port=runner._choose_free_local_port,
        wait_for_port_ready=runner._wait_for_port_ready,
    )


def stop_alertmanager_port_forward_compat(
    runner: Any,
    process: Any,
    local_port: int | None,
) -> None:
    """Compatibility wrapper for stopping Alertmanager port-forward.

    This is a delegator that wraps stop_alertmanager_port_forward
    from loop_alertmanager_port_forward.
    """
    from .loop_alertmanager_port_forward import stop_alertmanager_port_forward as impl

    impl(
        process=process,
        local_port=local_port,
        run_id=runner.run_id,
        run_label=runner.run_label,
        log_event=runner._log_event,
    )


# Re-export for backward compatibility
__all__ = [
    "run_auto_drilldown_analysis_compat",
    "run_alertmanager_discovery_compat",
    "run_alertmanager_snapshot_collection_compat",
    "run_vmalert_discovery_compat",
    "run_automatic_diagnosis_loop_compat",
    "failure_metadata_field_compat",
    "start_alertmanager_port_forward_compat",
    "stop_alertmanager_port_forward_compat",
]

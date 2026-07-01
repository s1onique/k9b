"""Budget reset helpers - operates on backend artifact root (runs/health/external-analysis/)."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts._k9b_budget_backend_scripts import _BACKEND_RESET_SCRIPT
from scripts._k9b_budget_status import (
    get_budget_status_in_backend as _get_budget_status_in_backend,
)
from scripts._k9b_budget_status import (
    get_budget_status_local as _get_budget_status_local,
)
from scripts.k9b_lab_common_helpers import log

_logger = logging.getLogger(__name__)

BUDGET_RESETTABLE_SUFFIXES = (
    "-diagnosis-review-packet.json",
    "-diagnosis-loop-pass.json",
    "-read-only-check-result.json",
    "-next-check-budget.json",
)

DIAGNOSIS_REVIEW_PACKET_SUFFIX = "-diagnosis-review-packet.json"
LOOP_PASS_SUFFIX = "-diagnosis-loop-pass.json"


@dataclass(frozen=True)
class BudgetResetResult:
    """Result of budget reset operation."""

    incident_id: str
    reset_file_count: int
    reset_paths: tuple[str, ...]
    execution_context: str
    error: str | None = None


def _matches_diagnosis_artifact(name: str, incident_id: str) -> bool:
    """Check if a filename matches any budget-affecting artifact pattern."""
    if not name.startswith(f"auto-{incident_id}-"):
        return False
    return name.endswith(BUDGET_RESETTABLE_SUFFIXES)


def _resolve_health_root(runs_dir: Path) -> Path:
    """Resolve the health root directory from a runs directory."""
    if runs_dir.name == "health":
        return runs_dir
    return runs_dir / "health"


def reset_diagnosis_loop_budget_local(
    runs_dir: Path,
    incident_id: str,
) -> BudgetResetResult:
    """Reset the automatic diagnosis loop budget for a specific incident (local mode)."""
    health_root = _resolve_health_root(runs_dir)
    external_analysis_dir = health_root / "external-analysis"

    if not external_analysis_dir.exists():
        _logger.debug(
            "External analysis dir does not exist, nothing to reset for incident_id=%s",
            incident_id,
        )
        return BudgetResetResult(
            incident_id=incident_id,
            reset_file_count=0,
            reset_paths=(),
            execution_context="local_filesystem",
        )

    removed_files: list[str] = []
    removed_types: dict[str, int] = {
        "review_packets": 0,
        "loop_passes": 0,
        "other_budget_artifacts": 0,
    }

    try:
        for path in external_analysis_dir.rglob("*"):
            if not path.is_file():
                continue

            name = path.name

            if not _matches_diagnosis_artifact(name, incident_id):
                continue

            if name.endswith(DIAGNOSIS_REVIEW_PACKET_SUFFIX):
                removed_types["review_packets"] += 1
            elif name.endswith(LOOP_PASS_SUFFIX):
                removed_types["loop_passes"] += 1
            else:
                removed_types["other_budget_artifacts"] += 1

            try:
                path.unlink()
                removed_files.append(str(path.relative_to(external_analysis_dir)))
                _logger.debug("Removed diagnosis artifact: %s", path)
            except OSError as e:
                _logger.warning(
                    "Failed to remove diagnosis artifact %s: %s",
                    path,
                    e,
                )
    except OSError as e:
        _logger.warning(
            "Failed to scan external-analysis dir for budget reset: %s",
            e,
        )
        return BudgetResetResult(
            incident_id=incident_id,
            reset_file_count=0,
            reset_paths=(),
            execution_context="local_filesystem",
            error=str(e),
        )

    if removed_files:
        _logger.info(
            "Reset diagnosis loop budget for incident_id=%s: removed %d files (%s)",
            incident_id,
            len(removed_files),
            removed_types,
        )
        log(
            f"  Budget reset: removed {len(removed_files)} diagnosis artifact(s) for {incident_id}: "
            f"{removed_types['review_packets']} review packets, "
            f"{removed_types['loop_passes']} loop passes, "
            f"{removed_types['other_budget_artifacts']} other budget artifacts"
        )
    else:
        _logger.debug(
            "No diagnosis artifacts found for incident_id=%s (budget is clean)",
            incident_id,
        )
        log(f"  Budget reset: no diagnosis artifacts found for {incident_id} (already clean)")

    return BudgetResetResult(
        incident_id=incident_id,
        reset_file_count=len(removed_files),
        reset_paths=tuple(removed_files),
        execution_context="local_filesystem",
    )


def reset_diagnosis_loop_budget_in_backend(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    deployment: str = "k9b-backend",
    container: str = "backend",
    backend_runs_dir: str = "/app/runs",
) -> BudgetResetResult:
    """Reset the automatic diagnosis loop budget in the backend container (k8s mode)."""
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "exec",
        "-n", namespace,
        f"deploy/{deployment}",
        "-c", container,
        "--",
        "python", "-c", _BACKEND_RESET_SCRIPT,
        incident_id,
        backend_runs_dir,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        _logger.error("Budget reset timed out in backend container")
        return BudgetResetResult(
            incident_id=incident_id,
            reset_file_count=0,
            reset_paths=(),
            execution_context="k8s_backend_container",
            error="timeout",
        )

    if result.returncode != 0:
        _logger.error("kubectl exec failed: %s", result.stderr[:500])
        return BudgetResetResult(
            incident_id=incident_id,
            reset_file_count=0,
            reset_paths=(),
            execution_context="k8s_backend_container",
            error=f"kubectl_exec_failed:{result.stderr[:500]}",
        )

    try:
        data = json.loads(result.stdout.strip())
        removed_count = data.get("removed_count", 0)
        removed_paths = data.get("removed_paths", [])
        external_dir_exists = data.get("external_dir_exists", False)

        if not external_dir_exists:
            _logger.debug(
                "Backend external-analysis dir does not exist, nothing to reset for incident_id=%s",
                incident_id,
            )
            log(f"  Budget reset: backend external-analysis dir not found for {incident_id} (already clean)")
        elif removed_count > 0:
            _logger.info(
                "Reset diagnosis loop budget in backend for incident_id=%s: removed %d files",
                incident_id,
                removed_count,
            )
            log(
                f"  Budget reset (backend container): removed {removed_count} diagnosis artifact(s) for {incident_id}"
            )
        else:
            _logger.debug(
                "No diagnosis artifacts found in backend for incident_id=%s (budget is clean)",
                incident_id,
            )
            log(f"  Budget reset: no diagnosis artifacts found in backend for {incident_id} (already clean)")

        return BudgetResetResult(
            incident_id=incident_id,
            reset_file_count=removed_count,
            reset_paths=tuple(removed_paths),
            execution_context="k8s_backend_container",
        )
    except (json.JSONDecodeError, ValueError) as e:
        _logger.error("Failed to parse budget reset output: %s", result.stdout[:500])
        return BudgetResetResult(
            incident_id=incident_id,
            reset_file_count=0,
            reset_paths=(),
            execution_context="k8s_backend_container",
            error=f"parse_error: {e}",
        )


# Re-export status functions
get_budget_status_local = _get_budget_status_local
get_budget_status_in_backend = _get_budget_status_in_backend


# Legacy function names - deprecated
def reset_diagnosis_loop_budget(
    external_analysis_dir: Path,
    incident_id: str,
) -> int:
    """DEPRECATED: Use reset_diagnosis_loop_budget_local or reset_diagnosis_loop_budget_in_backend."""
    raise RuntimeError(
        "Legacy reset_diagnosis_loop_budget() is deprecated. "
        "Use reset_diagnosis_loop_budget_local() or reset_diagnosis_loop_budget_in_backend() instead."
    )


def get_budget_status(
    external_analysis_dir: Path,
    incident_id: str,
) -> dict:
    """DEPRECATED: Use get_budget_status_local or get_budget_status_in_backend."""
    raise RuntimeError(
        "Legacy get_budget_status() is deprecated. "
        "Use get_budget_status_local() or get_budget_status_in_backend() instead."
    )


__all__ = [
    "BudgetResetResult",
    "reset_diagnosis_loop_budget",
    "reset_diagnosis_loop_budget_local",
    "reset_diagnosis_loop_budget_in_backend",
    "get_budget_status",
    "get_budget_status_local",
    "get_budget_status_in_backend",
]

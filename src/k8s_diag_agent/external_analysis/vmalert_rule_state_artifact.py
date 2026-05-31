"""Run artifact persistence for vmalert rule state.

This module provides artifact persistence for vmalert alert/rule state results,
parallel to the alertmanager_snapshot module.

Key invariants:
- Artifacts are immutable: once written, they must not be overwritten
- Failures are non-fatal to health loop
- Artifacts include source tracking and error context
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..identity.artifact import write_append_only_json_artifact
from .vmalert_client import VmalertFetchResult
from .vmalert_rule_state import VmalertAlertSignal, VmalertRuleGroup, normalize_vmalert_response

if TYPE_CHECKING:
    from .vmalert_discovery import VmalertSourceInventory


@dataclass(frozen=True)
class VmalertRuleStateArtifact:
    """Complete vmalert rule state artifact for a run.

    Aggregates results from all vmalert sources into a single run-scoped artifact.
    """

    source_count: int
    fetched_source_count: int
    failed_source_count: int
    alerts: tuple[VmalertAlertSignal, ...]
    rule_groups: tuple[VmalertRuleGroup, ...]
    fetch_errors: tuple[dict[str, Any], ...]
    captured_at: str

    # Property accessors for backward compatibility
    @property
    def firing_alert_count(self) -> int:
        return sum(1 for a in self.alerts if a.is_firing)

    @property
    def pending_alert_count(self) -> int:
        return sum(1 for a in self.alerts if a.is_pending)

    @property
    def critical_firing_count(self) -> int:
        return sum(1 for a in self.alerts if a.is_firing and a.is_critical)

    @property
    def firing_alerts(self) -> tuple[VmalertAlertSignal, ...]:
        return tuple(a for a in self.alerts if a.is_firing)

    @property
    def pending_alerts(self) -> tuple[VmalertAlertSignal, ...]:
        return tuple(a for a in self.alerts if a.is_pending)

    @property
    def critical_firing_alerts(self) -> tuple[VmalertAlertSignal, ...]:
        return tuple(a for a in self.alerts if a.is_firing and a.is_critical)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_count": self.source_count,
            "fetched_source_count": self.fetched_source_count,
            "failed_source_count": self.failed_source_count,
            "alert_count": len(self.alerts),
            "firing_alert_count": self.firing_alert_count,
            "pending_alert_count": self.pending_alert_count,
            "critical_firing_count": self.critical_firing_count,
            "alerts": [a.to_dict() for a in self.alerts],
            "rule_groups": [g.to_dict() for g in self.rule_groups],
            "fetch_errors": list(self.fetch_errors),
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> VmalertRuleStateArtifact:
        # Parse alerts
        alerts: list[VmalertAlertSignal] = []
        for raw_alert in raw.get("alerts", []):
            if isinstance(raw_alert, dict):
                alerts.append(VmalertAlertSignal.from_dict(raw_alert))

        # Parse rule groups
        rule_groups: list[VmalertRuleGroup] = []
        for raw_group in raw.get("rule_groups", []):
            if isinstance(raw_group, dict):
                rule_groups.append(VmalertRuleGroup.from_dict(raw_group))

        # Parse fetch errors
        fetch_errors: list[dict[str, Any]] = []
        for raw_error in raw.get("fetch_errors", []):
            if isinstance(raw_error, dict):
                fetch_errors.append(dict(raw_error))

        return cls(
            source_count=int(raw.get("source_count", 0)),
            fetched_source_count=int(raw.get("fetched_source_count", 0)),
            failed_source_count=int(raw.get("failed_source_count", 0)),
            alerts=tuple(alerts),
            rule_groups=tuple(rule_groups),
            fetch_errors=tuple(fetch_errors),
            captured_at=str(raw.get("captured_at", "")),
        )


@dataclass(frozen=True)
class FetchError:
    """A sanitized fetch error for artifact storage."""

    source_endpoint: str
    source_id: str | None
    status: str
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_endpoint": self.source_endpoint,
            "source_id": self.source_id,
            "status": self.status,
            "error": self.error,
        }


def write_vmalert_rule_state(
    directory: Path,
    artifact: VmalertRuleStateArtifact,
    run_id: str,
) -> Path:
    """Write vmalert rule state artifact to run artifact directory.

    vmalert rule state artifacts are immutable: once written, they must not be overwritten.
    This function rejects writes to an existing path to enforce the immutability contract.

    Returns the path to the written file.

    Raises:
        FileExistsError: If the artifact path already exists (immutability guarantee)
    """
    path = directory / f"{run_id}-vmalert-rule-state.json"
    context = f"run_id={run_id}"
    return write_append_only_json_artifact(path, artifact.to_dict(), context=context)


def read_vmalert_rule_state(path: Path) -> VmalertRuleStateArtifact | None:
    """Read vmalert rule state from artifact file.

    Returns None if file does not exist or cannot be parsed.
    """
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return VmalertRuleStateArtifact.from_dict(raw)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def vmalert_rule_state_exists(root: Path, run_id: str) -> bool:
    """Check if vmalert rule state artifact exists for a run."""
    path = root / f"{run_id}-vmalert-rule-state.json"
    return path.exists()


def build_rule_state_from_fetch_results(
    fetch_results: tuple[VmalertFetchResult, ...],
    max_string_length: int = 200,
) -> VmalertRuleStateArtifact:
    """Build a VmalertRuleStateArtifact from a collection of fetch results.

    Args:
        fetch_results: Tuple of fetch results from vmalert endpoints
        max_string_length: Maximum string length for normalization

    Returns:
        Aggregated VmalertRuleStateArtifact
    """
    all_alerts: list[VmalertAlertSignal] = []
    all_rule_groups: list[VmalertRuleGroup] = []
    fetch_errors: list[dict[str, Any]] = []

    source_count = len(fetch_results)
    fetched_count = 0
    failed_count = 0

    for result in fetch_results:
        if result.is_ok:
            fetched_count += 1
            if result.raw_response:
                alerts, rule_groups = normalize_vmalert_response(
                    result.raw_response,
                    result.source_endpoint,
                    max_string_length,
                )
                all_alerts.extend(alerts)
                all_rule_groups.extend(rule_groups)
        else:
            failed_count += 1
            # Sanitize error for storage
            fetch_errors.append({
                "source_endpoint": result.source_endpoint,
                "status": result.status.value,
                "error": result.error or "Unknown error",
            })

    return VmalertRuleStateArtifact(
        source_count=source_count,
        fetched_source_count=fetched_count,
        failed_source_count=failed_count,
        alerts=tuple(all_alerts),
        rule_groups=tuple(all_rule_groups),
        fetch_errors=tuple(fetch_errors),
        captured_at=fetch_results[0].captured_at if fetch_results else datetime.now(UTC).isoformat(),
    )


def collect_vmalert_rule_state(
    inventory: VmalertSourceInventory,
    timeout_seconds: float = 5.0,
) -> VmalertRuleStateArtifact:
    """Collect vmalert rule state from all eligible sources.

    Args:
        inventory: The vmalert source inventory
        timeout_seconds: Timeout for each fetch request

    Returns:
        VmalertRuleStateArtifact with aggregated results
    """
    from datetime import UTC, datetime

    from .vmalert_client import fetch_vmalert_alerts, fetch_vmalert_rules
    from .vmalert_discovery import VmalertSource

    # Determine eligible sources
    eligible_sources: list[VmalertSource] = []
    for source in inventory.sources.values():
        # Include sources in useful states
        if source.state.value in (
            "discovered",
            "auto-tracked",
            "manual",
            "discovered-but-unverified",  # Still attempt fetch even if unverified
        ):
            eligible_sources.append(source)

    if not eligible_sources:
        return VmalertRuleStateArtifact(
            source_count=0,
            fetched_source_count=0,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at=datetime.now(UTC).isoformat(),
        )

    # Fetch from each eligible source
    fetch_results: list[VmalertFetchResult] = []
    for source in eligible_sources:
        # Try /api/v1/alerts first (more directly useful for operators)
        alerts_result = fetch_vmalert_alerts(source.endpoint, timeout_seconds)
        if alerts_result.is_ok and alerts_result.raw_response:
            fetch_results.append(alerts_result)
        else:
            # Fall back to /api/v1/rules which includes alerts too
            rules_result = fetch_vmalert_rules(source.endpoint, timeout_seconds)
            fetch_results.append(rules_result)

    # Build artifact from results
    return build_rule_state_from_fetch_results(tuple(fetch_results))

"""Utility to preview health config and cohort expectations before a run."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.health.loop import (
    ComparisonIntent,
    HealthRunConfig,
    HealthSnapshotRecord,
    HealthTarget,
    _policy_eligible_pair,
)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect health config files for required metadata and cohort compatibility."
    )
    parser.add_argument("config", type=Path, help="Path to the health config JSON file.")
    return parser.parse_args()


def _dummy_snapshot(target: HealthTarget) -> ClusterSnapshot:
    metadata = {
        "cluster_id": target.context,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "control_plane_version": "unknown",
        "node_count": 0,
        "pod_count": 0,
    }
    return ClusterSnapshot.from_dict({"metadata": metadata})


def _build_records(config: HealthRunConfig) -> dict[str, HealthSnapshotRecord]:
    records: dict[str, HealthSnapshotRecord] = {}
    for target in config.targets:
        snapshot = _dummy_snapshot(target)
        record = HealthSnapshotRecord(target=target, snapshot=snapshot, path=Path(target.label))
        for reference in record.refs():
            records[reference] = record
    return records


def _print_targets(config: HealthRunConfig) -> None:
    print("Declared targets:")
    for target in config.targets:
        print(
            f"- {target.label} ({target.context}): class={target.cluster_class}, "
            f"role={target.cluster_role}, cohort={target.baseline_cohort}"
        )


def _format_meta(value: str | None) -> str:
    return value or "missing"


def _format_categories(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _check_peers(config: HealthRunConfig, records: dict[str, HealthSnapshotRecord]) -> int:
    status_counts = {"eligible": 0, "skipped": 0, "unsafe": 0}
    eligible_suspicious = 0
    total_suspicious = 0
    issues_found = False
    print("Peer comparison sanity:")
    if not config.peers:
        print("- No peer mappings configured (health-only mode).")
        return eligible_suspicious
    for peer in config.peers:
        primary = records.get(peer.primary)
        secondary = records.get(peer.secondary)
        if not primary or not secondary:
            print(
                f"- Unable to resolve peer {peer.primary} vs {peer.secondary}: missing target metadata."
            )
            issues_found = True
            continue
        if peer.intent == ComparisonIntent.SUSPICIOUS_DRIFT:
            total_suspicious += 1
        (
            policy_eligible,
            policy_reason,
            primary_class,
            secondary_class,
            primary_role,
            secondary_role,
            primary_cohort,
            secondary_cohort,
        ) = _policy_eligible_pair(
            primary, secondary, peer.intent, config.baseline_policy
        )
        if policy_eligible:
            status = "eligible"
        elif peer.intent == ComparisonIntent.SUSPICIOUS_DRIFT:
            status = "unsafe"
            issues_found = True
        else:
            status = "skipped"
        status_counts[status] += 1
        if policy_eligible and peer.intent == ComparisonIntent.SUSPICIOUS_DRIFT:
            eligible_suspicious += 1
        print(
            f"- {primary.target.label} ({primary.target.context}) vs "
            f"{secondary.target.label} ({secondary.target.context}) ({peer.intent.label()}): "
            f"{status}; reason: {policy_reason}"
        )
        print(
            f"  class: {_format_meta(primary_class)} vs {_format_meta(secondary_class)}"
        )
        print(
            f"  roles: {_format_meta(primary_role)} vs {_format_meta(secondary_role)}"
        )
        print(
            f"  cohorts: {_format_meta(primary_cohort)} vs {_format_meta(secondary_cohort)}"
        )
        print(
            f"  expected drift categories: {_format_categories(peer.expected_drift_categories)}"
        )
        if peer.notes:
            print(f"  notes: {peer.notes}")
        print("")
    print("Comparison status summary:")
    for label in ("eligible", "skipped", "unsafe"):
        print(f"- {label}: {status_counts[label]}")
    if total_suspicious:
        print(
            f"  Suspicious drift pairs eligible: {eligible_suspicious}/{total_suspicious}"
        )
        if eligible_suspicious == 0:
            print("  (No eligible suspicious-drift comparisons configured yet.)")
    if issues_found:
        print("Unsafe suspicious-drift mappings detected; fix the configuration before running the loop.")
    return int(issues_found)


def main() -> None:
    args = _parse_arguments()
    try:
        config = HealthRunConfig.load(args.config)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load config: {exc}")
        sys.exit(1)
    records = _build_records(config)
    _print_targets(config)
    issues = _check_peers(config, records)
    sys.exit(issues)


if __name__ == "__main__":
    main()

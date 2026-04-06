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


def _check_peers(config: HealthRunConfig, records: dict[str, HealthSnapshotRecord]) -> int:
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
            *_ignored,
            primary_cohort,
            secondary_cohort,
        ) = _policy_eligible_pair(
            primary, secondary, peer.intent, config.baseline_policy
        )
        status = "eligible" if policy_eligible else "skipped"
        print(
            f"- {primary.target.label} vs {secondary.target.label} ({peer.intent.value}): "
            f"{status}; reason: {policy_reason}"
        )
        if peer.intent == ComparisonIntent.SUSPICIOUS_DRIFT:
            if policy_eligible:
                eligible_suspicious += 1
            if not policy_eligible and "baseline cohort" in policy_reason.lower():
                issues_found = True
        if not policy_eligible and "baseline cohort" in policy_reason.lower():
            print(
                f"  Cohort breakdown: primary={primary_cohort}, secondary={secondary_cohort}"
            )
    if total_suspicious:
        print(
            f"  Suspicious drift pairs eligible: {eligible_suspicious}/{total_suspicious}"
        )
        if eligible_suspicious == 0:
            print("  (No eligible suspicious-drift comparisons configured yet.)")
    if issues_found:
        print("Cohort metadata issues detected; please fix before running the loop.")
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

"""Utility to preview health config and cohort expectations before a run."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import (
    BaselineRegistry,
    ComparisonIntent,
    HealthRunConfig,
    HealthSnapshotRecord,
    HealthTarget,
    _policy_eligible_pair,
)

BASELINE_GUIDE_DOC = Path("docs/baseline_watch_practices.md")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect health config files for required metadata and cohort compatibility."
    )
    parser.add_argument("config", type=Path, help="Path to the health config JSON file.")
    return parser.parse_args()


def _dummy_snapshot(target: HealthTarget) -> ClusterSnapshot:
    metadata = {
        "cluster_id": target.context,
        "captured_at": datetime.now(UTC).isoformat(),
        "control_plane_version": "unknown",
        "node_count": 0,
        "pod_count": 0,
    }
    return ClusterSnapshot.from_dict({"metadata": metadata})


def _build_records(config: HealthRunConfig) -> dict[str, HealthSnapshotRecord]:
    records: dict[str, HealthSnapshotRecord] = {}
    for target in config.targets:
        snapshot = _dummy_snapshot(target)
        record = HealthSnapshotRecord(
            target=target,
            snapshot=snapshot,
            path=Path(target.label),
            baseline_policy=BaselinePolicy.empty(),
        )
        for reference in record.refs():
            records[reference] = record
    return records


def resolve_runs_dir(config_path: Path) -> str:
    path = config_path
    output_dir = "runs"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        output_dir = raw.get("output_dir") or output_dir
    except (OSError, json.JSONDecodeError):
        pass
    return str(Path(output_dir) / "health")


def _print_targets(config: HealthRunConfig, baseline_map: dict[str, tuple[BaselinePolicy, Path | None]]) -> None:
    print("Declared targets:")
    for target in config.targets:
        _, target_baseline_path = baseline_map.get(target.label, (None, None))
        print(
            f"- {target.label} ({target.context}): class={target.cluster_class}, "
            f"role={target.cluster_role}, cohort={target.baseline_cohort}, "
            f"policy={target_baseline_path or 'default'}"
        )


def _print_baseline_map(config: HealthRunConfig) -> None:
    if not config.cohort_baselines:
        return
    print("Cohort baseline policies:")
    for cohort, (_policy, path) in sorted(config.cohort_baselines.items()):
        print(f"  - {cohort}: {path}")


def _collect_missing_metadata(config: HealthRunConfig) -> list[tuple[str, tuple[str, ...]]]:
    missing_list: list[tuple[str, tuple[str, ...]]] = []
    for target in config.targets:
        missing_fields: list[str] = []
        if not target.cluster_class:
            missing_fields.append("cluster_class")
        if not target.cluster_role:
            missing_fields.append("cluster_role")
        if not target.baseline_cohort:
            missing_fields.append("baseline_cohort")
        if missing_fields:
            missing_list.append((target.label, tuple(missing_fields)))
    return missing_list


def _format_meta(value: str | None) -> str:
    return value or "missing"


def _format_categories(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


@dataclass(frozen=True)
class PeerComparisonReport:
    primary_label: str
    secondary_label: str
    intent: ComparisonIntent
    status: str
    policy_eligible: bool
    reason: str
    expected_drift_categories: tuple[str, ...]
    notes: str | None
    primary_class: str | None
    secondary_class: str | None
    primary_role: str | None
    secondary_role: str | None
    primary_cohort: str | None
    secondary_cohort: str | None


def _collect_peer_reports(
    config: HealthRunConfig,
    records: dict[str, HealthSnapshotRecord],
    registry: BaselineRegistry,
) -> tuple[list[PeerComparisonReport], dict[str, int]]:
    status_counts = {"eligible": 0, "skipped": 0, "unsafe": 0}
    reports: list[PeerComparisonReport] = []
    for peer in config.peers:
        primary = records.get(peer.primary)
        secondary = records.get(peer.secondary)
        if not primary or not secondary:
            status = (
                "unsafe"
                if peer.intent == ComparisonIntent.SUSPICIOUS_DRIFT
                else "skipped"
            )
            status_counts[status] += 1
            reports.append(
                PeerComparisonReport(
                    primary_label=primary.target.label if primary else peer.primary,
                    secondary_label=secondary.target.label
                    if secondary
                    else peer.secondary,
                    intent=peer.intent,
                    status=status,
                    policy_eligible=False,
                    reason="missing target metadata",
                    expected_drift_categories=peer.expected_drift_categories,
                    notes=peer.notes,
                    primary_class=None,
                    secondary_class=None,
                    primary_role=None,
                    secondary_role=None,
                    primary_cohort=None,
                    secondary_cohort=None,
                )
            )
            continue
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
            primary, secondary, peer.intent, registry
        )
        if policy_eligible:
            status = "eligible"
        elif peer.intent == ComparisonIntent.SUSPICIOUS_DRIFT:
            status = "unsafe"
        else:
            status = "skipped"
        status_counts[status] += 1
        reports.append(
            PeerComparisonReport(
                primary_label=primary.target.label,
                secondary_label=secondary.target.label,
                intent=peer.intent,
                status=status,
                policy_eligible=policy_eligible,
                reason=policy_reason,
                expected_drift_categories=peer.expected_drift_categories,
                notes=peer.notes,
                primary_class=primary_class,
                secondary_class=secondary_class,
                primary_role=primary_role,
                secondary_role=secondary_role,
                primary_cohort=primary_cohort,
                secondary_cohort=secondary_cohort,
            )
        )
    return reports, status_counts


def _check_release_coverage(config: HealthRunConfig) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for target in config.targets:
        for release_key in target.watched_helm_releases:
            if config.baseline_policy.release_policy(release_key):
                continue
            missing.append((target.label, release_key))
    return missing


def _print_peer_summary(reports: list[PeerComparisonReport], status_counts: dict[str, int]) -> None:
    suspicious_reports = [
        report
        for report in reports
        if report.intent == ComparisonIntent.SUSPICIOUS_DRIFT
    ]
    suspicious_total = len(suspicious_reports)
    unsafe = status_counts.get("unsafe", 0)
    eligible = sum(1 for report in suspicious_reports if report.policy_eligible)
    skipped = status_counts.get("skipped", 0)
    state = "PASS" if unsafe == 0 else "FAIL"
    print(f"Suspicious drift compatibility: {state}")
    print(f"  - suspicious pairs total: {suspicious_total}")
    print(f"  - eligible: {eligible}")
    print(f"  - unsafe: {unsafe}")
    print(f"  - skipped: {skipped}")
    if unsafe:
        print("  Issues:")
        for report in suspicious_reports:
            if report.policy_eligible:
                continue
            primary_class_label = report.primary_class or "missing"
            secondary_class_label = report.secondary_class or "missing"
            class_meta = f"class {primary_class_label} vs {secondary_class_label}"
            primary_role_label = report.primary_role or "missing"
            secondary_role_label = report.secondary_role or "missing"
            role_meta = f"role {primary_role_label} vs {secondary_role_label}"
            primary_cohort_label = report.primary_cohort or "missing"
            secondary_cohort_label = report.secondary_cohort or "missing"
            cohort_meta = f"cohort {primary_cohort_label} vs {secondary_cohort_label}"
            print(
                f"    - {report.primary_label} vs {report.secondary_label}: {report.reason}"
            )
            print(f"      {class_meta}; {role_meta}; {cohort_meta}")
            if report.expected_drift_categories:
                categories = ", ".join(report.expected_drift_categories)
                print(f"      expected drift categories: {categories}")
            if report.notes:
                print(f"      notes: {report.notes}")


def _print_release_summary(
    config: HealthRunConfig, release_issues: list[tuple[str, str]]
) -> None:
    watched_total = sum(len(target.watched_helm_releases) for target in config.targets)
    state = "FAIL" if release_issues else "PASS"
    print(f"Watched release coverage: {state}")
    print(f"  - releases tracked: {watched_total}")
    if release_issues:
        print("  Missing baseline policies:")
        for label, release_key in release_issues:
            print(f"    - {label}: {release_key}")


def _print_release_guidance(release_issues: list[tuple[str, str]]) -> None:
    if not release_issues:
        return
    print("Release guidance:")
    print("  - Keep tracked releases aligned with the platform-level baseline definition so retention is predictable.")
    print("  - Remove a release from a target’s WATCHED list before deleting it from the baseline, or add a matching baseline entry that describes the supported release family.")
    guide = BASELINE_GUIDE_DOC
    print(f"  - See {guide} for pruning tips and how to reason about platform-level parity when you pick watched releases.")


def _print_metadata_guidance(metadata_issues: list[tuple[str, tuple[str, ...]]]) -> None:
    if not metadata_issues:
        return
    guide = BASELINE_GUIDE_DOC
    print("Metadata guidance:")
    print("  - Every target must declare cluster_class, cluster_role, and baseline_cohort so comparisons stay deterministic and auditable.")
    print("  - Update the listed fields in your health config or use the example policy as a template, then rerun inspect to confirm eligibility.")
    print(f"  - See {guide} for naming guidance and platform-level cohort modeling.")


def _print_peer_guidance(reports: list[PeerComparisonReport]) -> None:
    unsafe_reports = [
        report
        for report in reports
        if report.intent == ComparisonIntent.SUSPICIOUS_DRIFT and report.status == "unsafe"
    ]
    if not unsafe_reports:
        return
    guide = BASELINE_GUIDE_DOC
    print("Suspicious drift guidance:")
    print("  - Ensure primary/secondary pairs share compatible class/role/cohort metadata before allowing a drift comparison.")
    print("  - If the pairing should still be compared, mark the intent as expected drift or add matching drift categories in the baseline policy.")
    print(f"  - See {guide} for cohort-aware policy structure and how to keep suspicious-drift pairs safe.")


def _print_preflight_summary(
    config_path: Path,
    baseline_path: Path | None,
    runs_dir: str,
    reports: list[PeerComparisonReport],
    status_counts: dict[str, int],
    release_issues: list[tuple[str, str]],
    config: HealthRunConfig,
    metadata_issues: list[tuple[str, tuple[str, ...]]],
) -> None:
    unsafe = status_counts.get("unsafe", 0)
    overall_state = "FAIL" if release_issues or unsafe else "PASS"
    print("Policy preflight summary")
    print("========================")
    baseline_label = str(baseline_path or "<unknown>")
    print(f"- config: {config_path}")
    print(f"- baseline: {baseline_label}")
    print(f"- expected runs_dir: {runs_dir}")
    print(f"- overall status: {overall_state}")
    print("")
    _print_peer_summary(reports, status_counts)
    print("")
    _print_release_summary(config, release_issues)
    if metadata_issues:
        print("")
        print("Metadata coverage: FAIL")
        for label, fields in metadata_issues:
            fields_list = ", ".join(fields)
            print(f"  - {label}: missing {fields_list}")
    elif not release_issues and not unsafe:
        print("")
        print("Metadata coverage: PASS")
    _print_release_guidance(release_issues)
    _print_metadata_guidance(metadata_issues)
    _print_peer_guidance(reports)


def main() -> None:
    args = _parse_arguments()
    try:
        config = HealthRunConfig.load(args.config)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load config: {exc}")
        sys.exit(1)
    registry = BaselineRegistry([config.baseline_policy])
    for policy, _ in config.target_baselines.values():
        registry.add(policy)
    records = _build_records(config)
    runs_dir = resolve_runs_dir(args.config)
    _print_targets(config, config.target_baselines)
    _print_baseline_map(config)
    reports, status_counts = _collect_peer_reports(config, records, registry)
    release_issues = _check_release_coverage(config)
    metadata_issues = _collect_missing_metadata(config)
    _print_preflight_summary(
        args.config,
        config.baseline_policy_path,
        runs_dir,
        reports,
        status_counts,
        release_issues,
        config,
        metadata_issues,
    )
    suspicious_issues = any(
        report.intent == ComparisonIntent.SUSPICIOUS_DRIFT and not report.policy_eligible
        for report in reports
    )
    issues = bool(release_issues or suspicious_issues or metadata_issues)
    sys.exit(int(issues))


if __name__ == "__main__":
    main()

"""Snapshot CLI handlers extracted from cli_handlers.py.

This module contains handlers for fixture, snapshot, and batch snapshot operations.
Extracted to reduce cli_handlers.py size and improve LLM-friendly traversal.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .cli_logging import CLI_LOG_PATH, _cli_run_label, _log_cli_event  # noqa: F401

# Import assessment handler from sibling module
from .cli_snapshot_assess_handlers import handle_assess_snapshots  # noqa: F401
from .collect.cluster_snapshot import ClusterSnapshot, CollectionStatus
from .collect.fixture_loader import load_fixture
from .collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from .compare.two_cluster import compare_snapshots
from .correlate.linkers import correlate_signals
from .health.artifact_readers import read_cluster_snapshot_artifact
from .models import Assessment
from .normalize.evidence import normalize_signals
from .reason.diagnoser import build_findings_and_hypotheses
from .recommend.next_steps import build_recommended_action, propose_next_steps
from .render.formatter import assessment_to_dict, dump_json, format_summary

# =============================================================================
# Snapshot Configuration
# =============================================================================


DEFAULT_BATCH_CONFIG = Path("snapshots/targets.local.json")
BATCH_CONFIG_FALLBACK = Path("snapshots/targets.local.example.json")


@dataclass(frozen=True)
class SnapshotTarget:
    context: str
    label: str | None = None
    output: str | None = None


@dataclass(frozen=True)
class BatchSnapshotConfig:
    targets: tuple[SnapshotTarget, ...]
    output_dir: Path


# =============================================================================
# Fixture Handler
# =============================================================================


def handle_fixture(args: argparse.Namespace) -> int:
    fixture_data = load_fixture(args.fixture)
    evidence, signals = normalize_signals(fixture_data)
    correlated = correlate_signals(signals)
    findings, hypotheses = build_findings_and_hypotheses(signals, correlated)
    next_checks = propose_next_steps(hypotheses)
    action = build_recommended_action()

    assessment = Assessment(
        observed_signals=signals,
        findings=findings,
        hypotheses=hypotheses,
        next_evidence_to_collect=next_checks,
        recommended_action=action,
        safety_level=action.safety_level,
        probable_layer_of_origin=findings[0].layer if findings and findings[0].layer else None,
    )

    serialized = assessment_to_dict(assessment)
    if args.output:
        dump_json(assessment, str(args.output))
    else:
        sys.stdout.write(json.dumps(serialized, indent=2))
        sys.stdout.write("\n")
    if not args.quiet:
        print(format_summary(assessment))
    return 0


# =============================================================================
# Single Snapshot Handler
# =============================================================================


def handle_snapshot(args: argparse.Namespace) -> int:
    component = "cli-snapshot"
    run_label = _cli_run_label(component, args.context)
    _log_cli_event(
        component,
        run_label,
        "snapshot command started",
        metadata={"context": args.context},
    )
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        _log_cli_event(
            component,
            run_label,
            "unable to discover kube contexts",
            severity="ERROR",
            metadata={"error": str(exc)},
        )
        print(f"Unable to discover kube contexts: {exc}", file=sys.stderr)
        return 1
    if contexts and args.context not in contexts:
        _log_cli_event(
            component,
            run_label,
            "requested context unavailable",
            severity="ERROR",
            metadata={"context": args.context, "available": contexts},
        )
        print(
            f"Context '{args.context}' not found. Available contexts: {', '.join(contexts)}",
            file=sys.stderr,
        )
        return 1
    try:
        snapshot = collect_cluster_snapshot(args.context)
    except RuntimeError as exc:
        _log_cli_event(
            component,
            run_label,
            "snapshot collection failed",
            severity="ERROR",
            metadata={"error": str(exc)},
        )
        print(f"Snapshot collection failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
    print(f"Snapshot for '{args.context}' written to {args.output}")
    _log_cli_event(
        component,
        run_label,
        "snapshot command completed",
        metadata={"output": str(args.output)},
    )
    return 0


# =============================================================================
# Batch Snapshot Handler
# =============================================================================


def handle_batch_snapshot(
    args: argparse.Namespace, default_config: Path = DEFAULT_BATCH_CONFIG
) -> int:
    try:
        config_path = _resolve_config_path(
            args.config,
            BATCH_CONFIG_FALLBACK,
            args.config == default_config,
        )
    except RuntimeError as exc:
        run_label = _cli_run_label("cli-batch-snapshot", args.config.name)
        _log_cli_event(
            "cli-batch-snapshot",
            run_label,
            "batch snapshot config resolution failed",
            severity="ERROR",
            metadata={"error": str(exc), "config": str(args.config)},
        )
        print(f"Unable to resolve batch config: {exc}", file=sys.stderr)
        return 1
    component = "cli-batch-snapshot"
    run_label = _cli_run_label(component, config_path.name)
    _log_cli_event(
        component,
        run_label,
        "batch snapshot command started",
        metadata={"config": str(config_path)},
    )
    try:
        config = _load_batch_config(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _log_cli_event(
            component,
            run_label,
            "unable to load batch config",
            severity="ERROR",
            metadata={"error": str(exc), "config": str(config_path)},
        )
        print(f"Unable to load batch config {config_path}: {exc}", file=sys.stderr)
        return 1
    if not config.targets:
        _log_cli_event(
            component,
            run_label,
            "batch config contains no targets",
            severity="ERROR",
            metadata={"config": str(config_path)},
        )
        print(f"Batch config {config_path} contains no targets.", file=sys.stderr)
        return 1
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        print(f"Unable to discover kube contexts: {exc}", file=sys.stderr)
        return 1
    available = set(contexts)
    successes = 0
    issues: list[str] = []
    config.output_dir.mkdir(parents=True, exist_ok=True)
    for target in config.targets:
        label = target.label or target.context
        if target.context not in available:
            msg = f"Context '{target.context}' not found; skipping {label}."
            print(msg, file=sys.stderr)
            issues.append(msg)
            continue
        output_path = Path(target.output) if target.output else config.output_dir / f"{target.context}.json"
        try:
            snapshot = collect_cluster_snapshot(target.context)
        except RuntimeError as exc:
            msg = f"Snapshot for '{target.context}' failed: {exc}"
            print(msg, file=sys.stderr)
            issues.append(msg)
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
        print(f"Collected snapshot for '{target.context}' -> {output_path}")
        partial = _format_partial_status(snapshot.collection_status)
        if partial:
            print(f"  partial issues: {partial}", file=sys.stderr)
        successes += 1
    print(f"Batch snapshot processed {successes} target(s).")
    if issues:
        print(f"Issues encountered for {len(issues)} target(s).", file=sys.stderr)
        _log_cli_event(
            component,
            run_label,
            "batch snapshot completed with issues",
            severity="WARNING",
            metadata={"successes": successes, "issues": issues},
        )
    else:
        _log_cli_event(
            component,
            run_label,
            "batch snapshot completed",
            metadata={"successes": successes},
        )
    return 0


# =============================================================================
# Compare Handler
# =============================================================================


def handle_compare(args: argparse.Namespace) -> int:
    component = "cli-compare"
    run_label = _cli_run_label(component, f"{args.snapshot_a.name}-{args.snapshot_b.name}")
    _log_cli_event(
        component,
        run_label,
        "compare command started",
        metadata={"snapshot_a": str(args.snapshot_a), "snapshot_b": str(args.snapshot_b)},
    )
    try:
        primary = _load_snapshot(args.snapshot_a)
        secondary = _load_snapshot(args.snapshot_b)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        _log_cli_event(
            component,
            run_label,
            "unable to load snapshots",
            severity="ERROR",
            metadata={"error": str(exc)},
        )
        print(f"Unable to load snapshots: {exc}", file=sys.stderr)
        return 1
    comparison = compare_snapshots(primary, secondary)
    if not comparison.differences:
        print("Snapshots match across tracked dimensions.")
        _log_cli_event(
            component,
            run_label,
            "compare command completed with no differences",
            metadata={"differences": 0},
        )
        return 0
    print(json.dumps(comparison.differences, indent=2))
    _log_cli_event(
        component,
        run_label,
        "compare command completed with differences",
        metadata={"differences": len(comparison.differences)},
    )
    return 0


# =============================================================================
# Helper Functions
# =============================================================================


def _load_batch_config(path: Path) -> BatchSnapshotConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    output_dir = Path(str(raw.get("output_dir") or "snapshots"))
    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, list):
        raise ValueError("`targets` must be a list")
    targets: list[SnapshotTarget] = []
    for raw_target in targets_raw:
        if not isinstance(raw_target, dict):
            continue
        context = raw_target.get("context")
        if not context:
            continue
        targets.append(
            SnapshotTarget(
                context=str(context),
                label=_str_or_none(raw_target.get("label")),
                output=_str_or_none(raw_target.get("output")),
            )
        )
    return BatchSnapshotConfig(tuple(targets), output_dir)


def _resolve_config_path(preferred: Path, fallback: Path, allow_fallback: bool) -> Path:
    if preferred.exists():
        return preferred
    if allow_fallback and fallback.exists():
        raise RuntimeError(
            f"Local config {preferred} is missing; copy {fallback} → {preferred} and replace the placeholder contexts with your real kube contexts before running."
        )
    raise RuntimeError(f"Config {preferred} not found; create it from {fallback} before running.")


def _format_partial_status(status: CollectionStatus) -> str | None:
    issues: list[str] = []
    if status.helm_error:
        issues.append(f"helm_error={status.helm_error}")
    if status.missing_evidence:
        issues.append(f"missing_evidence={','.join(status.missing_evidence)}")
    if not issues:
        return None
    return "; ".join(issues)


def _str_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _load_snapshot(path: Path) -> ClusterSnapshot:
    """Load a ClusterSnapshot from disk using the typed artifact reader."""
    return read_cluster_snapshot_artifact(path)


# Re-export for backward compatibility
__all__ = [
    "CLI_LOG_PATH",
    "SnapshotTarget",
    "BatchSnapshotConfig",
    "DEFAULT_BATCH_CONFIG",
    "BATCH_CONFIG_FALLBACK",
    "handle_fixture",
    "handle_snapshot",
    "handle_batch_snapshot",
    "handle_compare",
    "handle_assess_snapshots",
    "_cli_run_label",
    "_log_cli_event",
]

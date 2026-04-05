"""CLI entry point for fixture and snapshot flows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from .collect.cluster_snapshot import ClusterSnapshot, CollectionStatus
from .collect.fixture_loader import load_fixture
from .collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from .compare.two_cluster import compare_snapshots
from .correlate.linkers import correlate_signals
from .llm.assessor_schema import AssessorAssessment
from .llm.prompts import build_assessment_prompt
from .llm.provider import AVAILABLE_PROVIDERS, build_assessment_input, get_provider
from .models import Assessment
from .normalize.evidence import normalize_signals
from .recommend.next_steps import build_recommended_action, propose_next_steps
from .reason.diagnoser import build_findings_and_hypotheses
from .render.formatter import assessment_to_dict, dump_json, format_summary
from .feedback.runner import run_feedback_loop


_SUBCOMMANDS = {"fixture", "snapshot", "compare", "batch-snapshot", "assess-snapshots", "run-feedback"}

_DEFAULT_BATCH_CONFIG = Path("snapshots/targets.local.json")
_BATCH_CONFIG_FALLBACK = Path("snapshots/targets.local.example.json")
_RUN_CONFIG_DEFAULT = Path("runs/run-config.local.json")
_RUN_CONFIG_FALLBACK = Path("runs/run-config.local.example.json")


@dataclass(frozen=True)
class SnapshotTarget:
    context: str
    label: Optional[str] = None
    output: Optional[str] = None


@dataclass(frozen=True)
class BatchSnapshotConfig:
    targets: Tuple[SnapshotTarget, ...]
    output_dir: Path


def main(argv: Iterable[str] | None = None) -> int:
    source_args = list(argv) if argv is not None else sys.argv[1:]
    normalized = _normalize_args(source_args)
    parser = argparse.ArgumentParser(description="Run diagnostics or snapshot tools.")
    subparsers = parser.add_subparsers(dest="command")

    fixture_parser = subparsers.add_parser("fixture", help="Diagnose a fixture.")
    fixture_parser.add_argument("fixture", type=Path, help="Path to scenario fixture JSON file.")
    fixture_parser.add_argument(
        "--output", "-o", type=Path, default=None, help="Optional path for assessment JSON."
    )
    fixture_parser.add_argument("--quiet", action="store_true", help="Suppress summary output.")

    snapshot_parser = subparsers.add_parser("snapshot", help="Collect a typed cluster snapshot.")
    snapshot_parser.add_argument("--context", required=True, help="Kubernetes context name to collect.")
    snapshot_parser.add_argument("--output", "-o", type=Path, required=True, help="Path for snapshot JSON.")

    compare_parser = subparsers.add_parser("compare", help="Compare two snapshots.")
    compare_parser.add_argument("snapshot_a", type=Path, help="First snapshot JSON file.")
    compare_parser.add_argument("snapshot_b", type=Path, help="Second snapshot JSON file.")

    batch_parser = subparsers.add_parser("batch-snapshot", help="Collect snapshots for configured contexts.")
    batch_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=_DEFAULT_BATCH_CONFIG,
        help="Path to JSON config listing batch targets (defaults to snapshots/targets.local.json, which must point at your real contexts).",
    )

    assess_parser = subparsers.add_parser(
        "assess-snapshots",
        help="Run the optional LLM assessment over two snapshot files.",
    )
    assess_parser.add_argument("snapshot_a", type=Path, help="First snapshot JSON file.")
    assess_parser.add_argument("snapshot_b", type=Path, help="Second snapshot JSON file.")
    assess_parser.add_argument(
        "--provider",
        choices=AVAILABLE_PROVIDERS,
        default="default",
        help="LLM provider name to use for assessment.",
    )
    assess_parser.add_argument("--output", "-o", type=Path, help="Optional path for assessment JSON output.")
    assess_parser.add_argument("--quiet", action="store_true", help="Suppress summary output.")

    run_parser = subparsers.add_parser("run-feedback", help="Run the operational feedback loop.")
    run_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=_RUN_CONFIG_DEFAULT,
        help="Feedback run configuration file (defaults to runs/run-config.local.json; template files require explicit --config).",
    )
    run_parser.add_argument(
        "--provider",
        "-p",
        choices=AVAILABLE_PROVIDERS,
        help="Optional provider override for assessments.",
    )
    run_parser.add_argument("--quiet", action="store_true", help="Suppress summary output.")

    args = parser.parse_args(normalized)
    command = args.command or "fixture"

    if command == "snapshot":
        return _handle_snapshot(args)
    if command == "compare":
        return _handle_compare(args)
    if command == "batch-snapshot":
        return _handle_batch_snapshot(args)
    if command == "assess-snapshots":
        return _handle_assess_snapshots(args)
    if command == "run-feedback":
        return _handle_run_feedback(args)
    return _handle_fixture(args)


def _normalize_args(argv: Iterable[str]) -> List[str]:
    normalized = list(argv)
    if not normalized:
        return ["fixture"]
    if normalized[0] in _SUBCOMMANDS:
        return normalized
    return ["fixture", *normalized]


def _handle_fixture(args: argparse.Namespace) -> int:
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


def _handle_snapshot(args: argparse.Namespace) -> int:
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        print(f"Unable to discover kube contexts: {exc}", file=sys.stderr)
        return 1
    if contexts and args.context not in contexts:
        print(
            f"Context '{args.context}' not found. Available contexts: {', '.join(contexts)}",
            file=sys.stderr,
        )
        return 1
    try:
        snapshot = collect_cluster_snapshot(args.context)
    except RuntimeError as exc:
        print(f"Snapshot collection failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
    print(f"Snapshot for '{args.context}' written to {args.output}")
    return 0


def _handle_batch_snapshot(args: argparse.Namespace) -> int:
    try:
        config_path = _resolve_config_path(
            args.config,
            _BATCH_CONFIG_FALLBACK,
            args.config == _DEFAULT_BATCH_CONFIG,
        )
    except RuntimeError as exc:
        print(f"Unable to resolve batch config: {exc}", file=sys.stderr)
        return 1
    try:
        config = _load_batch_config(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load batch config {config_path}: {exc}", file=sys.stderr)
        return 1
    if not config.targets:
        print(f"Batch config {config_path} contains no targets.", file=sys.stderr)
        return 1
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        print(f"Unable to discover kube contexts: {exc}", file=sys.stderr)
        return 1
    available = set(contexts)
    successes = 0
    issues: List[str] = []
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
    return 0


def _load_batch_config(path: Path) -> BatchSnapshotConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    output_dir = Path(str(raw.get("output_dir") or "snapshots"))
    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, list):
        raise ValueError("`targets` must be a list")
    targets: List[SnapshotTarget] = []
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


def _format_partial_status(status: CollectionStatus) -> Optional[str]:
    issues: List[str] = []
    if status.helm_error:
        issues.append(f"helm_error={status.helm_error}")
    if status.missing_evidence:
        issues.append(f"missing_evidence={','.join(status.missing_evidence)}")
    if not issues:
        return None
    return "; ".join(issues)


def _str_or_none(value: object | None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _handle_compare(args: argparse.Namespace) -> int:
    try:
        primary = _load_snapshot(args.snapshot_a)
        secondary = _load_snapshot(args.snapshot_b)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Unable to load snapshots: {exc}", file=sys.stderr)
        return 1
    comparison = compare_snapshots(primary, secondary)
    if not comparison.differences:
        print("Snapshots match across tracked dimensions.")
        return 0
    print(json.dumps(comparison.differences, indent=2))
    return 0


def _handle_assess_snapshots(args: argparse.Namespace) -> int:
    try:
        primary = _load_snapshot(args.snapshot_a)
        secondary = _load_snapshot(args.snapshot_b)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Unable to load snapshots: {exc}", file=sys.stderr)
        return 1
    comparison = compare_snapshots(primary, secondary)
    prompt = build_assessment_prompt(primary, secondary, comparison)
    provider = get_provider(args.provider)
    payload = build_assessment_input(primary, secondary, comparison)
    try:
        raw_assessment = provider.assess(prompt, payload)
    except Exception as exc:
        print(f"LLM assessment failed: {exc}", file=sys.stderr)
        return 1
    try:
        validated = AssessorAssessment.from_dict(raw_assessment)
    except ValueError as exc:
        print(f"LLM assessment returned invalid schema: {exc}", file=sys.stderr)
        return 1
    serialized = validated.to_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    else:
        sys.stdout.write(json.dumps(serialized, indent=2))
        sys.stdout.write("\n")
    if not args.quiet and validated.hypotheses:
        print(
            f"LLM assessment ready. Hypothesis: {validated.hypotheses[0].description}",
            file=sys.stderr,
        )
    return 0


def _handle_run_feedback(args: argparse.Namespace) -> int:
    try:
        config_path = _resolve_config_path(
            args.config,
            _RUN_CONFIG_FALLBACK,
            args.config == _RUN_CONFIG_DEFAULT,
        )
    except RuntimeError as exc:
        print(f"Unable to resolve run config: {exc}", file=sys.stderr)
        return 1
    exit_code, _ = run_feedback_loop(config_path, provider_override=args.provider, quiet=args.quiet)
    return exit_code


def _load_snapshot(path: Path) -> ClusterSnapshot:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ClusterSnapshot.from_dict(raw)


if __name__ == "__main__":
    raise SystemExit(main())

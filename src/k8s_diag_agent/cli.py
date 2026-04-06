"""CLI entry point for fixture and snapshot flows."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from .cli_handlers import (
    DEFAULT_BATCH_CONFIG,
    HEALTH_CONFIG_DEFAULT,
    RUN_CONFIG_DEFAULT,
    handle_assess_drilldown,
    handle_assess_snapshots,
    handle_batch_snapshot,
    handle_check_proposal,
    handle_compare,
    handle_fixture,
    handle_health_loop,
    handle_health_summary,
    handle_run_feedback,
    handle_promote_proposal,
    handle_snapshot,
)
from .llm.provider import AVAILABLE_PROVIDERS

_SUBCOMMANDS = {
    "fixture",
    "snapshot",
    "compare",
    "batch-snapshot",
    "assess-snapshots",
    "assess-drilldown",
    "run-feedback",
    "run-health-loop",
    "check-proposal",
    "promote-proposal",
    "health-summary",
}

_DEFAULT_BATCH_CONFIG = DEFAULT_BATCH_CONFIG
_RUN_CONFIG_DEFAULT = RUN_CONFIG_DEFAULT
_HEALTH_CONFIG_DEFAULT = HEALTH_CONFIG_DEFAULT


def main(argv: Iterable[str] | None = None) -> int:
    source_args = list(argv) if argv is not None else sys.argv[1:]
    normalized = _normalize_args(source_args)
    parser = build_parser()
    args = parser.parse_args(normalized)
    command = args.command or "fixture"

    if command == "snapshot":
        return handle_snapshot(args)
    if command == "compare":
        return handle_compare(args)
    if command == "batch-snapshot":
        return handle_batch_snapshot(args, default_config=_DEFAULT_BATCH_CONFIG)
    if command == "assess-snapshots":
        return handle_assess_snapshots(args)
    if command == "assess-drilldown":
        return handle_assess_drilldown(args)
    if command == "run-feedback":
        return handle_run_feedback(args, default_config=_RUN_CONFIG_DEFAULT)
    if command == "run-health-loop":
        return handle_health_loop(args, default_config=_HEALTH_CONFIG_DEFAULT)
    if command == "health-summary":
        return handle_health_summary(args)
    if command == "check-proposal":
        return handle_check_proposal(args)
    if command == "promote-proposal":
        return handle_promote_proposal(args)
    return handle_fixture(args)


def _normalize_args(argv: Iterable[str]) -> list[str]:
    normalized = list(argv)
    if not normalized:
        return ["fixture"]
    if normalized[0] in _SUBCOMMANDS:
        return normalized
    return ["fixture", *normalized]


def _positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return ivalue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run diagnostics or snapshot tools.")
    subparsers = parser.add_subparsers(dest="command")

    fixture_parser = subparsers.add_parser("fixture", help="Diagnose a fixture.")
    fixture_parser.add_argument("fixture", type=Path, help="Path to scenario fixture JSON file.")
    fixture_parser.add_argument(
        "--output", "-o", type=Path, default=None, help="Optional path for assessment JSON."
    )
    fixture_parser.add_argument("--quiet", action="store_true", help="Suppress summary output.")

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Collect a typed cluster snapshot.",
    )
    snapshot_parser.add_argument(
        "--context",
        required=True,
        help="Kubernetes context name to collect.",
    )
    snapshot_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Path for snapshot JSON.",
    )

    compare_parser = subparsers.add_parser("compare", help="Compare two snapshots.")
    compare_parser.add_argument("snapshot_a", type=Path, help="First snapshot JSON file.")
    compare_parser.add_argument("snapshot_b", type=Path, help="Second snapshot JSON file.")

    batch_parser = subparsers.add_parser("batch-snapshot", help="Collect snapshots for configured contexts.")
    batch_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=_DEFAULT_BATCH_CONFIG,
        help=(
            "Path to JSON config listing batch targets "
            "(defaults to snapshots/targets.local.json, which must point at your real contexts)."
        ),
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
    assess_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional path for assessment JSON output.",
    )
    assess_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress summary output.",
    )

    drilldown_parser = subparsers.add_parser(
        "assess-drilldown",
        help="Run the optional LLM assessment over a targeted drilldown artifact.",
    )
    drilldown_parser.add_argument("artifact", type=Path, help="Drilldown artifact JSON generated by the health loop.")
    drilldown_parser.add_argument(
        "--provider",
        choices=AVAILABLE_PROVIDERS,
        default="default",
        help="LLM provider name to use for assessment.",
    )
    drilldown_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional path for assessment JSON output.",
    )
    drilldown_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress summary output.",
    )

    run_parser = subparsers.add_parser("run-feedback", help="Run the operational feedback loop.")
    run_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=_RUN_CONFIG_DEFAULT,
        help=(
            "Feedback run configuration file (defaults to runs/run-config.local.json; "
            "template files require explicit --config)."
        ),
    )
    run_parser.add_argument(
        "--provider",
        "-p",
        choices=AVAILABLE_PROVIDERS,
        help="Optional provider override for assessments.",
    )
    run_parser.add_argument("--quiet", action="store_true", help="Suppress summary output.")

    health_parser = subparsers.add_parser("run-health-loop", help="Run per-cluster health assessments.")
    health_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=_HEALTH_CONFIG_DEFAULT,
        help=(
            "Health run configuration file (defaults to runs/health-config.local.json; "
            "template files require explicit --config)."
        ),
    )
    health_parser.add_argument(
        "--trigger",
        "-t",
        action="append",
        help="Manual comparison trigger in the format primary:secondary.",
    )
    health_parser.add_argument(
        "--drilldown",
        "-d",
        action="append",
        help="Request a drilldown artifact for the given context even without automated triggers.",
    )
    health_parser.add_argument("--quiet", action="store_true", help="Suppress summary output.")
    health_parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single health iteration and exit even if scheduling options are provided.",
    )
    health_parser.add_argument(
        "--every-seconds",
        type=_positive_int,
        help="Repeat the health run every N seconds until interrupted or --max-runs is reached.",
    )
    health_parser.add_argument(
        "--max-runs",
        type=_positive_int,
        help="Optional cap on repeated runs (requires --every-seconds).",
    )

    summary_parser = subparsers.add_parser(
        "health-summary",
        help="Show a compact overview of the latest health run artifacts.",
    )
    summary_parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs/health"),
        help="Base directory of health artifacts (default: runs/health).",
    )
    summary_parser.add_argument(
        "--run-id",
        help="Optionally target a specific run_id instead of the latest.",
    )

    check_parser = subparsers.add_parser(
        "check-proposal",
        help="Evaluate a health proposal against a replay fixture.",
    )
    check_parser.add_argument("proposal", type=Path, help="Path to a proposal JSON artifact.")
    check_parser.add_argument(
        "--fixture",
        "-f",
        type=Path,
        default=Path("tests/fixtures/snapshots/sanitized-alpha.json"),
        help="Fixture to replay when evaluating the proposal.",
    )

    promote_parser = subparsers.add_parser(
        "promote-proposal",
        help="Render candidate health config or baseline patches from a proposal.",
    )
    promote_parser.add_argument("proposal", type=Path, help="Path to a proposal JSON artifact.")
    promote_parser.add_argument(
        "--health-config",
        type=Path,
        default=Path("runs/health-config.local.json"),
        help=(
            "Health config file that drives the proposal generation "
            "(used for defaults and baseline paths)."
        ),
    )
    promote_parser.add_argument(
        "--baseline",
        type=Path,
        help="Optional baseline policy file override (otherwise resolved from the health config).",
    )
    promote_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/health/promotions"),
        help="Directory where promotion patches are written.",
    )
    promote_parser.add_argument(
        "--note",
        help="Optional operator rationale or note to store with the promotion lifecycle entry.",
    )

    return parser


if __name__ == "__main__":
    raise SystemExit(main())

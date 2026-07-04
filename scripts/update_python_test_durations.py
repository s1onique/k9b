#!/usr/bin/env python3
"""Update Python test duration manifest from JUnit XML timing artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

from _duration_utils import (
    aggregate_durations,
    check_balance_threshold,
    compute_shard_balance,
    find_junit_xml_files,
    is_bootstrap_manifest,
    load_existing_durations,
    parse_junit_xml,
)

# Schema expected by shard_tests.py:
# {"durations": [{"nodeid": "tests/...", "duration_s": 0.5}, ...]}


def write_manifest(
    output_file: Path,
    source_files: list[Path],
    aggregated: list[dict[str, str | float]],
    aggregate_method: str = "max",
    overwrite: bool = False,
) -> None:
    """Write the updated duration manifest."""
    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Output file exists: {output_file}. Use --overwrite to replace.")
    manifest = {
        "version": 1,
        "description": "Python unit test duration manifest for duration-weighted sharding",
        "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        "source": [str(f) for f in source_files],
        "test_count": len(aggregated),
        "aggregate_method": aggregate_method,
        "durations": aggregated,
    }
    with open(output_file, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def print_balance_report(
    metrics: dict,
    before_metrics: dict | None = None,
    file: TextIO = sys.stdout,
) -> None:
    """Print a formatted shard balance report."""
    print("=== Shard Balance Report ===", file=file)
    print(f"Total tests: {metrics['total_tests']}", file=file)
    print(f"Total weight: {metrics['total_weight']:.2f}s", file=file)
    print(f"Number of shards: {metrics['num_shards']}", file=file)
    print(file=file)
    print("Shard distribution:", file=file)
    for i in range(metrics["num_shards"]):
        print(f"  Shard {i}: {metrics['shard_weights'][i]:.2f}s ({metrics['shard_counts'][i]} tests)", file=file)
    print(file=file)
    skew = metrics["skew_ratio"]
    status = "✓" if skew <= 2.0 else "✗"
    print(f"{status} Skew ratio: {skew:.4f}", file=file)
    if before_metrics is not None:
        print(file=file)
        delta = skew - before_metrics["skew_ratio"]
        print(f"  Previous skew: {before_metrics['skew_ratio']:.4f}", file=file)
        print(f"  Current skew:  {skew:.4f} {'↓' if delta < 0 else '↑'}", file=file)
        print(f"  Change: {delta:+.4f}", file=file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update Python test duration manifest from JUnit XML artifacts")
    parser.add_argument("inputs", nargs="+", type=Path, help="JUnit XML files or directories")
    parser.add_argument("--output", "-o", type=Path, default=Path("scripts/python_test_durations.json"), help="Output path")
    parser.add_argument("--aggregate", choices=["max", "avg"], default="max", help="Aggregation method (default: max)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output file")
    parser.add_argument("--allow-empty", action="store_true", help="Exit successfully even if no test cases found")
    parser.add_argument("--check-balance", action="store_true", help="Show balance report instead of writing manifest")
    parser.add_argument("--shards", type=int, default=2, help="Number of shards for balance check (default: 2)")
    parser.add_argument("--max-skew", type=float, default=2.0, help="Maximum acceptable skew ratio (default: 2.0)")
    parser.add_argument("--bootstrap-guard", action="store_true", help="Warn if input is a bootstrap placeholder")
    parser.add_argument("--manifest", type=Path, help="Manifest to check with --bootstrap-guard")

    args = parser.parse_args()

    xml_files = find_junit_xml_files(args.inputs)
    if not xml_files:
        print("ERROR: No JUnit XML files found." if not args.allow_empty else "No XML files found, --allow-empty specified.", file=sys.stderr)
        return 0 if args.allow_empty else 1

    print(f"Found {len(xml_files)} JUnit XML file(s)", file=sys.stderr)

    all_durations: list[tuple[str, float]] = []
    parse_errors: list[str] = []
    for xml_file in xml_files:
        try:
            durations = parse_junit_xml(xml_file)
            if durations:
                all_durations.extend(durations)
                print(f"  Parsed: {xml_file} ({len(durations)} test cases)", file=sys.stderr)
            else:
                print(f"  Empty: {xml_file}", file=sys.stderr)
        except Exception as e:
            parse_errors.append(str(e))
            print(f"  ERROR: {xml_file}: {e}", file=sys.stderr)

    if parse_errors and not args.allow_empty:
        print(f"\nERROR: {len(parse_errors)} file(s) failed to parse.", file=sys.stderr)
        return 1

    if not all_durations:
        print("ERROR: No test cases found." if not args.allow_empty else "No test cases found, --allow-empty specified.", file=sys.stderr)
        return 0 if args.allow_empty else 1

    aggregated = aggregate_durations(all_durations, args.aggregate)
    print(f"Aggregated to {len(aggregated)} unique test durations", file=sys.stderr)

    durations_dict: dict[str, float] = {str(e["nodeid"]): float(e["duration_s"]) for e in aggregated}

    if args.bootstrap_guard and args.manifest and is_bootstrap_manifest(args.manifest):
        print(f"WARNING: Current manifest appears to be a bootstrap placeholder: {args.manifest}", file=sys.stderr)

    current_metrics = compute_shard_balance(durations_dict, args.shards)

    before_metrics = None
    if args.manifest and args.manifest.exists():
        try:
            before_durations = load_existing_durations(args.manifest)
            if before_durations:
                before_metrics = compute_shard_balance(before_durations, args.shards)
        except Exception:
            pass

    if args.check_balance:
        print_balance_report(current_metrics, before_metrics)
        passes, message = check_balance_threshold(current_metrics, args.max_skew)
        print(file=sys.stderr)
        print(message, file=sys.stderr)
        return 0 if passes else 1

    try:
        write_manifest(args.output, xml_files, aggregated, args.aggregate, args.overwrite)
        print(f"Wrote manifest to: {args.output}", file=sys.stderr)
    except FileExistsError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Use --overwrite to replace existing file.", file=sys.stderr)
        return 1

    print_balance_report(current_metrics, before_metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())

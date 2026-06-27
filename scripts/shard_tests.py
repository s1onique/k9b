#!/usr/bin/env python3
"""
Deterministic duration-weighted test sharding.

This script implements greedy longest-processing-time (LPT) balancing
to distribute tests across shards based on historical duration data.

Usage:
    python scripts/shard_tests.py --shard N --total K [--durations FILE] [--collect-only]
    python scripts/shard_tests.py --verify --total K [--durations FILE]

Algorithm:
    1. Collect all test nodeids deterministically (sorted)
    2. Load historical duration weights from JSON manifest
    3. Sort tests by weight descending (heaviest first)
    4. Greedily assign each test to the currently lightest shard
    5. Output nodeids for requested shard or verification report

The output is stable for unchanged inputs: same nodeids + same durations
produces identical shard assignments.

Collection Policy:
    - Test collection uses the shared helper from test_collection.py
    - No raw ignore flags for test files (enforced by regression guard)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from test_collection import collect_test_nodeids as _collect_tests

REPO_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_DURATIONS_FILE = REPO_ROOT / "scripts" / "python_test_durations.json"
FALLBACK_WEIGHT = 1.0


@dataclass
class ShardStats:
    """Track cumulative weight and assigned nodeids for a shard."""
    weight: float = 0.0
    nodeids: list[str] = field(default_factory=list)


def load_duration_weights(durations_file: Path | None) -> dict[str, float]:
    """Load duration weights from JSON manifest.
    
    The manifest maps nodeids to their historical duration in seconds.
    Unknown tests use FALLBACK_WEIGHT.
    Removed entries are silently ignored.
    
    Raises:
        SystemExit: If manifest has duplicate nodeids.
    """
    if durations_file is None or not durations_file.exists():
        return {}
    
    try:
        with open(durations_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: Could not load {durations_file}: {e}", file=sys.stderr)
        return {}
    
    weights: dict[str, float] = {}
    for entry in data.get("durations", []):
        nodeid = entry.get("nodeid", "")
        duration = entry.get("duration_s", FALLBACK_WEIGHT)
        
        if not nodeid:
            continue
        
        if nodeid in weights:
            print(f"ERROR: Duplicate nodeid in durations manifest: {nodeid}", file=sys.stderr)
            sys.exit(1)
        
        weights[nodeid] = duration
    
    return weights


def collect_test_nodeids() -> list[str]:
    """Collect all test nodeids deterministically using pytest --collect-only.
    
    This function delegates to the shared helper in test_collection.py
    to ensure the same collection method is used by both shard_tests.py
    and verify_test_exclusions.py.
    """
    result = _collect_tests()
    
    if result.returncode != 0:
        print(f"ERROR: pytest collection failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    
    return list(result.nodeids)


def assign_shards_lpt(
    nodeids: list[str],
    weights: dict[str, float],
    num_shards: int,
) -> list[ShardStats]:
    """Assign nodeids to shards using greedy longest-processing-time balancing.
    
    Algorithm:
    1. Sort nodeids by weight descending (heaviest first)
    2. For each nodeid, assign to the currently lightest shard
    
    This is a 4/3-approximation algorithm for the optimal makespan.
    """
    if num_shards < 1:
        print("ERROR: Number of shards must be >= 1", file=sys.stderr)
        sys.exit(1)
    
    # Initialize shards
    shards = [ShardStats() for _ in range(num_shards)]
    
    # Sort nodeids by weight descending for LPT assignment
    # Use stable sort to maintain relative order for equal weights
    sorted_nodeids = sorted(
        nodeids,
        key=lambda n: (weights.get(n, FALLBACK_WEIGHT), n),
        reverse=True,
    )
    
    # Greedily assign each test to the lightest shard
    for nodeid in sorted_nodeids:
        weight = weights.get(nodeid, FALLBACK_WEIGHT)
        
        # Find shard with minimum current weight
        min_shard_idx = min(range(num_shards), key=lambda i: shards[i].weight)
        
        shards[min_shard_idx].weight += weight
        shards[min_shard_idx].nodeids.append(nodeid)
    
    return shards


def print_shard_assignments(shards: list[ShardStats], weights: dict[str, float]) -> None:
    """Print summary of shard assignments."""
    print("Shard assignments (sorted by nodeid for verification):", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    
    for i, shard in enumerate(shards):
        # Sort nodeids for deterministic output
        sorted_nodeids = sorted(shard.nodeids)
        total_weight = sum(weights.get(n, FALLBACK_WEIGHT) for n in shard.nodeids)
        
        print(f"\nShard {i}: {len(shard.nodeids)} tests, weight={total_weight:.2f}s", file=sys.stderr)
        for nodeid in sorted_nodeids:
            w = weights.get(nodeid, FALLBACK_WEIGHT)
            print(f"  {w:6.2f}s  {nodeid}", file=sys.stderr)


def verify_shard_completeness(
    all_nodeids: list[str],
    shards: list[ShardStats],
) -> bool:
    """Verify that all nodeids are assigned exactly once.
    
    Returns True if verification passes, False otherwise.
    """
    # Collect all assigned nodeids
    assigned: dict[str, int] = defaultdict(int)
    for shard in shards:
        for nodeid in shard.nodeids:
            assigned[nodeid] += 1
    
    errors = 0
    
    # Check for missing nodeids
    all_sorted = sorted(all_nodeids)
    assigned_sorted = sorted(assigned.keys())
    
    if all_sorted != assigned_sorted:
        print("\nERROR: Nodeid set mismatch!", file=sys.stderr)
        print(f"  Total collected: {len(all_nodeids)}", file=sys.stderr)
        print(f"  Total assigned:  {len(assigned)}", file=sys.stderr)
        
        # Find missing
        assigned_set = set(assigned_sorted)
        for nodeid in all_sorted:
            if nodeid not in assigned_set:
                print(f"  MISSING: {nodeid}", file=sys.stderr)
                errors += 1
        
        # Find extra
        all_set = set(all_sorted)
        for nodeid in assigned_sorted:
            if nodeid not in all_set:
                print(f"  EXTRA:   {nodeid}", file=sys.stderr)
                errors += 1
    
    # Check for duplicates
    for nodeid, count in assigned.items():
        if count > 1:
            print(f"\nERROR: Duplicate nodeid: {nodeid} (appears {count} times)", file=sys.stderr)
            errors += 1
    
    # Check for empty shards
    for i, shard in enumerate(shards):
        if not shard.nodeids:
            print(f"\nWARNING: Shard {i} is empty", file=sys.stderr)
    
    if errors == 0:
        print("\nVERIFICATION PASSED: All nodeids assigned exactly once.", file=sys.stderr)
        return True
    else:
        print(f"\nVERIFICATION FAILED: {errors} error(s) found.", file=sys.stderr)
        return False


def output_nodeids_for_shard(shards: list[ShardStats], shard_index: int, output: TextIO) -> None:
    """Output nodeids for a specific shard (one per line for shell expansion)."""
    if shard_index < 0 or shard_index >= len(shards):
        print(f"ERROR: Invalid shard index {shard_index}, expected 0-{len(shards)-1}", file=sys.stderr)
        sys.exit(1)
    
    # Sort for deterministic output
    for nodeid in sorted(shards[shard_index].nodeids):
        print(nodeid, file=output)


def compute_shard_metrics(shards: list[ShardStats]) -> dict:
    """Compute metrics about shard distribution."""
    weights = [s.weight for s in shards]
    counts = [len(s.nodeids) for s in shards]
    
    return {
        "num_shards": len(shards),
        "total_tests": sum(counts),
        "shard_weights": weights,
        "shard_counts": counts,
        "min_weight": min(weights),
        "max_weight": max(weights),
        "skew_ratio": max(weights) / min(weights) if min(weights) > 0 else float('inf'),
        "min_count": min(counts),
        "max_count": max(counts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic duration-weighted test sharding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--shard", type=int, metavar="N",
        help="Output nodeids for shard N (0-indexed)",
    )
    parser.add_argument(
        "--total", type=int, metavar="K", required=True,
        help="Total number of shards",
    )
    parser.add_argument(
        "--durations", type=Path, metavar="FILE",
        help=f"Path to duration manifest JSON (default: {DEFAULT_DURATIONS_FILE})",
    )
    parser.add_argument(
        "--collect-only", action="store_true",
        help="Only collect nodeids, do not shard",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify shard completeness without running tests",
    )
    parser.add_argument(
        "--metrics", action="store_true",
        help="Output shard metrics as JSON",
    )
    
    args = parser.parse_args()
    
    # Validate shard index
    if args.shard is not None and (args.shard < 0 or args.shard >= args.total):
        print(f"ERROR: --shard {args.shard} invalid for --total {args.total}", file=sys.stderr)
        print("       Must satisfy: 0 <= shard < total", file=sys.stderr)
        return 1
    
    # Determine durations file
    durations_file = args.durations
    if durations_file is None:
        durations_file = DEFAULT_DURATIONS_FILE
    
    # Load duration weights
    weights = load_duration_weights(durations_file)
    if weights:
        print(f"Loaded {len(weights)} duration weights from {durations_file}", file=sys.stderr)
    else:
        print("No duration manifest found, using fallback weight=1.0 for all tests", file=sys.stderr)
    
    # Collect test nodeids
    print("Collecting test nodeids...", file=sys.stderr)
    nodeids = collect_test_nodeids()
    print(f"Collected {len(nodeids)} test nodeids", file=sys.stderr)
    
    if args.collect_only:
        for nodeid in sorted(nodeids):
            print(nodeid)
        return 0
    
    # Assign to shards
    shards = assign_shards_lpt(nodeids, weights, args.total)
    
    # Compute and output metrics if requested
    if args.metrics:
        metrics = compute_shard_metrics(shards)
        print(json.dumps(metrics, indent=2))
        return 0
    
    # Verify completeness
    if args.verify:
        print_shard_assignments(shards, weights)
        success = verify_shard_completeness(nodeids, shards)
        return 0 if success else 1
    
    # Output nodeids for requested shard
    if args.shard is not None:
        output_nodeids_for_shard(shards, args.shard, sys.stdout)
        return 0
    
    # Default: show all assignments
    print_shard_assignments(shards, weights)
    metrics = compute_shard_metrics(shards)
    print("\nShard metrics:", file=sys.stderr)
    print(json.dumps(metrics, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

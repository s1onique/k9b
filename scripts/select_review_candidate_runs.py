#!/usr/bin/env python3
"""Select review-worthy runs from usefulness review exports.

This script scans exported run-scoped usefulness review files and ranks/selects
the most review-worthy runs based on deterministic heuristics.

Scoring factors:
- Entry count (more checks = more informative)
- Success/failure mix (mixed outcomes are more interesting for review)
- Command family diversity (variety of check types)
- Cross-cluster comparison (same command family across multiple clusters)
- Digest richness (non-generic digests with signal markers)

Usage:
    scripts/select_review_candidate_runs.py --runs-dir runs/ --top 10
    scripts/select_review_candidate_runs.py --runs-dir runs/ --top 5 --json
    scripts/select_review_candidate_runs.py --runs-dir runs/ --min-entry-count 10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


# Schema version for the review exports we consume
EXPECTED_SCHEMA_VERSION = "next-check-usefulness-review/v1"

# Review exports directory name
REVIEW_EXPORTS_DIR_NAME = "review-exports"

# Diagnostic packs directory name (canonical path alternative)
DIAGNOSTIC_PACKS_DIR_NAME = "diagnostic-packs"


@dataclass
class RunMetrics:
    """Computed metrics for a single run."""
    run_id: str
    entry_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    timed_out_count: int = 0
    skipped_count: int = 0
    command_family_counts: dict[str, int] = field(default_factory=dict)
    cluster_labels: set[str] = field(default_factory=set)
    family_to_clusters: dict[str, set[str]] = field(default_factory=dict)
    signal_marker_counts: Counter = field(default_factory=Counter)
    non_generic_digest_count: int = 0
    generic_digest_count: int = 0
    why_selected: list[str] = field(default_factory=list)


@dataclass
class RankedRun:
    """A run with computed score and metrics."""
    run_id: str
    entry_count: int
    success_count: int
    failed_count: int
    timed_out_count: int
    command_family_counts: dict[str, int]
    cluster_count: int
    repeated_family_cross_cluster_count: int
    digest_richness_score: float
    overall_review_priority_score: float
    why_selected: list[str]


def is_generic_digest(digest: str | None) -> bool:
    """Check if a result digest is generic/non-informative."""
    if not digest:
        return True
    digest_lower = digest.lower()
    # Generic patterns that don't provide useful signal
    # Note: "OK (XXXXB)" format should be considered generic
    if digest_lower.startswith("ok"):
        return True
    if digest_lower in ("success", "skipped", "no output", "empty"):
        return True
    return False


def compute_run_metrics(run_data: dict[str, Any]) -> RunMetrics:
    """Compute metrics from a run's review export data."""
    metrics = RunMetrics(run_id=run_data.get("run_id", "unknown"))

    entries = run_data.get("entries", [])
    metrics.entry_count = len(entries)

    for entry in entries:
        # Count execution statuses
        status = entry.get("execution_status", "")
        timed_out = entry.get("timed_out", False)

        if status == "success" or status == "completed":
            metrics.success_count += 1
        elif status == "failed":
            metrics.failed_count += 1
        elif status == "timed-out" or timed_out:
            metrics.timed_out_count += 1
        elif status == "skipped":
            metrics.skipped_count += 1

        # Track command families
        family = entry.get("command_family") or "unknown"
        metrics.command_family_counts[family] = metrics.command_family_counts.get(family, 0) + 1

        # Track cluster labels
        cluster = entry.get("cluster_label") or "unknown"
        metrics.cluster_labels.add(cluster)

        # Track family -> cluster mapping for cross-cluster analysis
        if family not in metrics.family_to_clusters:
            metrics.family_to_clusters[family] = set()
        metrics.family_to_clusters[family].add(cluster)

        # Track signal markers
        markers = entry.get("signal_markers") or []
        for marker in markers:
            metrics.signal_marker_counts[marker] += 1

        # Check digest richness
        result_digest = entry.get("result_digest")
        if is_generic_digest(result_digest):
            metrics.generic_digest_count += 1
        else:
            metrics.non_generic_digest_count += 1

    return metrics


def compute_review_priority_score(metrics: RunMetrics) -> tuple[float, list[str]]:
    """Compute overall review priority score based on heuristics.

    Returns:
        Tuple of (score, list of reasons why selected)
    """
    score = 0.0
    reasons: list[str] = []

    # 1. Entry count scoring (base score for having enough checks)
    # Prefer runs with 5-20 checks for review
    entry_count = metrics.entry_count
    if entry_count >= 5:
        entry_score = min(entry_count * 2, 40)  # Cap at 40 points
        reasons.append(f"entry_count={entry_count}")
    else:
        entry_score = 0

    # 2. Mixed outcomes scoring (success/failure diversity)
    total_outcomes = metrics.success_count + metrics.failed_count + metrics.timed_out_count
    if total_outcomes > 0:
        failure_rate = (metrics.failed_count + metrics.timed_out_count) / total_outcomes
        # Favor runs with some failures but not all failures
        # 20-70% failure rate is ideal (some signal, not all bad)
        if 0.2 <= failure_rate <= 0.7:
            outcome_score = 25
            reasons.append(f"mixed_outcomes(failure_rate={failure_rate:.1%})")
        elif failure_rate > 0:
            outcome_score = 10
            reasons.append(f"has_failures(failure_rate={failure_rate:.1%})")
        else:
            outcome_score = 0  # All successful - less interesting
    else:
        outcome_score = 0

    # 3. Command family diversity scoring
    unique_families = len(metrics.command_family_counts)
    if unique_families >= 3:
        family_score = 15
        reasons.append(f"family_diversity={unique_families}")
    elif unique_families >= 2:
        family_score = 8
        reasons.append(f"family_diversity={unique_families}")
    else:
        family_score = 0

    # 4. Cross-cluster comparison scoring
    # Count families that appear in multiple clusters
    cross_cluster_families = 0
    for family, clusters in metrics.family_to_clusters.items():
        if len(clusters) > 1:
            cross_cluster_families += 1

    if cross_cluster_families > 0:
        cluster_score = min(cross_cluster_families * 10, 30)
        reasons.append(f"cross_cluster_families={cross_cluster_families}")
    else:
        cluster_score = 0

    # 5. Digest richness scoring
    total_digests = metrics.generic_digest_count + metrics.non_generic_digest_count
    if total_digests > 0:
        richness_ratio = metrics.non_generic_digest_count / total_digests
        richness_score = richness_ratio * 20
        if metrics.non_generic_digest_count > 0:
            reasons.append(f"digest_richness={richness_ratio:.1%}")
    else:
        richness_score = 0

    # 6. Signal markers bonus (interesting diagnostic findings)
    total_markers = sum(metrics.signal_marker_counts.values())
    if total_markers > 0:
        marker_score = min(total_markers * 3, 15)
        reasons.append(f"signal_markers={total_markers}")
    else:
        marker_score = 0

    # Calculate total score
    score = entry_score + outcome_score + family_score + cluster_score + richness_score + marker_score

    return score, reasons


def rank_runs(
    runs_data: list[dict[str, Any]],
    min_entry_count: int = 1,
    require_mixed_outcomes: bool = False,
) -> list[RankedRun]:
    """Rank runs by review priority score.

    Args:
        runs_data: List of run review export data
        min_entry_count: Minimum number of entries required
        require_mixed_outcomes: If True, only include runs with both successes and failures

    Returns:
        List of RankedRun objects sorted by score descending
    """
    ranked_runs: list[RankedRun] = []

    for run_data in runs_data:
        # Skip runs that don't match schema
        schema_version = run_data.get("schema_version", "")
        if schema_version != EXPECTED_SCHEMA_VERSION:
            continue

        # Compute metrics
        metrics = compute_run_metrics(run_data)

        # Apply filters
        if metrics.entry_count < min_entry_count:
            continue

        if require_mixed_outcomes:
            has_success = metrics.success_count > 0
            has_failure = metrics.failed_count > 0 or metrics.timed_out_count > 0
            if not (has_success and has_failure):
                continue

        # Count cross-cluster families
        cross_cluster_count = 0
        for family, clusters in metrics.family_to_clusters.items():
            if len(clusters) > 1:
                cross_cluster_count += 1

        # Compute digest richness score (0-1)
        total_digests = metrics.generic_digest_count + metrics.non_generic_digest_count
        digest_richness = metrics.non_generic_digest_count / total_digests if total_digests > 0 else 0.0

        # Compute overall priority score and reasons
        priority_score, reasons = compute_review_priority_score(metrics)

        ranked_run = RankedRun(
            run_id=metrics.run_id,
            entry_count=metrics.entry_count,
            success_count=metrics.success_count,
            failed_count=metrics.failed_count,
            timed_out_count=metrics.timed_out_count,
            command_family_counts=dict(metrics.command_family_counts),
            cluster_count=len(metrics.cluster_labels),
            repeated_family_cross_cluster_count=cross_cluster_count,
            digest_richness_score=round(digest_richness, 3),
            overall_review_priority_score=round(priority_score, 1),
            why_selected=reasons,
        )
        ranked_runs.append(ranked_run)

    # Sort by score descending, then by entry count descending (tiebreaker)
    ranked_runs.sort(key=lambda r: (r.overall_review_priority_score, r.entry_count), reverse=True)

    return ranked_runs


def load_review_exports(runs_dir: Path) -> list[dict[str, Any]]:
    """Load all review export files from the runs directory.

    Searches in both:
    - runs/health/review-exports/*.json
    - runs/health/diagnostic-packs/*/next_check_usefulness_review.json

    Args:
        runs_dir: Path to the runs directory

    Returns:
        List of loaded review export data dictionaries
    """
    runs_dir = runs_dir.expanduser().resolve()
    run_data_list: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()

    # Search pattern 1: review-exports directory (flat exports)
    review_exports_dir = runs_dir / "health" / REVIEW_EXPORTS_DIR_NAME
    if review_exports_dir.exists():
        for export_file in review_exports_dir.glob("*-next_check_usefulness_review.json"):
            run_id = export_file.stem.replace("-next_check_usefulness_review", "")
            if run_id in seen_run_ids:
                continue
            try:
                data = json.loads(export_file.read_text(encoding="utf-8"))
                run_data_list.append(data)
                seen_run_ids.add(run_id)
            except (OSError, json.JSONDecodeError):
                continue

    # Search pattern 2: diagnostic-packs directory (canonical run-scoped exports)
    diagnostic_packs_dir = runs_dir / "health" / DIAGNOSTIC_PACKS_DIR_NAME
    if diagnostic_packs_dir.exists():
        for run_dir in diagnostic_packs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            review_file = run_dir / "next_check_usefulness_review.json"
            if not review_file.exists():
                continue
            run_id = run_dir.name
            if run_id in seen_run_ids:
                continue
            try:
                data = json.loads(review_file.read_text(encoding="utf-8"))
                run_data_list.append(data)
                seen_run_ids.add(run_id)
            except (OSError, json.JSONDecodeError):
                continue

    return run_data_list


def format_ranked_table(ranked_runs: list[RankedRun], top_n: int | None = None) -> str:
    """Format ranked runs as a human-readable table.

    Args:
        ranked_runs: List of ranked runs
        top_n: Optional limit on number of runs to include

    Returns:
        Formatted table string
    """
    if top_n is not None:
        runs_to_show = ranked_runs[:top_n]
    else:
        runs_to_show = ranked_runs

    if not runs_to_show:
        return "No runs found matching criteria."

    # Calculate column widths
    run_id_width = max(len("run_id"), max(len(r.run_id) for r in runs_to_show))
    score_width = max(len("score"), 8)
    entries_width = max(len("entries"), max(len(str(r.entry_count)) for r in runs_to_show))
    success_width = max(len("success"), max(len(str(r.success_count)) for r in runs_to_show))
    failed_width = max(len("failed"), max(len(str(r.failed_count)) for r in runs_to_show))
    clusters_width = max(len("clusters"), max(len(str(r.cluster_count)) for r in runs_to_show))
    cross_width = max(len("x-cluster"), max(len(str(r.repeated_family_cross_cluster_count)) for r in runs_to_show))
    rich_width = max(len("rich"), max(len(str(r.digest_richness_score)) for r in runs_to_show))

    lines: list[str] = []

    # Header
    header = (
        f"{'#':>3} "
        f"{'run_id':<{run_id_width}} "
        f"{'score':>{score_width}} "
        f"{'entries':>{entries_width}} "
        f"{'success':>{success_width}} "
        f"{'failed':>{failed_width}} "
        f"{'clusters':>{clusters_width}} "
        f"{'x-cluster':>{cross_width}} "
        f"{'rich':>{rich_width}} "
        f"why"
    )
    lines.append(header)

    # Separator
    lines.append("-" * len(header))

    # Rows
    for i, run in enumerate(runs_to_show, 1):
        why_short = "; ".join(run.why_selected[:3])
        if len(run.why_selected) > 3:
            why_short += f" +{len(run.why_selected) - 3}"

        row = (
            f"{i:>3} "
            f"{run.run_id:<{run_id_width}} "
            f"{run.overall_review_priority_score:>{score_width}.1f} "
            f"{run.entry_count:>{entries_width}} "
            f"{run.success_count:>{success_width}} "
            f"{run.failed_count:>{failed_width}} "
            f"{run.cluster_count:>{clusters_width}} "
            f"{run.repeated_family_cross_cluster_count:>{cross_width}} "
            f"{run.digest_richness_score:>{rich_width}} "
            f"{why_short}"
        )
        lines.append(row)

    # Summary
    lines.append("")
    lines.append(f"Total runs: {len(ranked_runs)}")
    if top_n is not None and len(ranked_runs) > top_n:
        lines.append(f"Showing top {top_n} of {len(ranked_runs)} runs")

    return "\n".join(lines)


def format_json_output(ranked_runs: list[RankedRun], top_n: int | None = None) -> str:
    """Format ranked runs as machine-readable JSON.

    Args:
        ranked_runs: List of ranked runs
        top_n: Optional limit on number of runs to include

    Returns:
        JSON string
    """
    if top_n is not None:
        runs_to_show = ranked_runs[:top_n]
    else:
        runs_to_show = ranked_runs

    output = {
        "schema_version": "review-candidate-selection/v1",
        "total_runs_scanned": len(ranked_runs),
        "runs": [
            {
                "run_id": r.run_id,
                "entry_count": r.entry_count,
                "success_count": r.success_count,
                "failed_count": r.failed_count,
                "timed_out_count": r.timed_out_count,
                "command_family_counts": r.command_family_counts,
                "cluster_count": r.cluster_count,
                "repeated_family_cross_cluster_count": r.repeated_family_cross_cluster_count,
                "digest_richness_score": r.digest_richness_score,
                "overall_review_priority_score": r.overall_review_priority_score,
                "why_selected": r.why_selected,
            }
            for r in runs_to_show
        ],
    }
    return json.dumps(output, indent=2)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select review-worthy runs from usefulness review exports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Show top 10 runs by review priority
    scripts/select_review_candidate_runs.py --runs-dir runs/ --top 10

    # Output as JSON for scripting
    scripts/select_review_candidate_runs.py --runs-dir runs/ --top 5 --json

    # Require minimum 10 entries and mixed outcomes
    scripts/select_review_candidate_runs.py --runs-dir runs/ --min-entry-count 10 --require-mixed-outcomes
        """,
    )
    parser.add_argument(
        "--runs-dir",
        required=True,
        help="Path to the runs directory (contains health/)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Number of top runs to show (default: show all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as machine-readable JSON",
    )
    parser.add_argument(
        "--min-entry-count",
        type=int,
        default=5,
        help="Minimum number of entries required for a run to be considered (default: 5)",
    )
    parser.add_argument(
        "--require-mixed-outcomes",
        action="store_true",
        help="Only include runs with both successes and failures",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs_dir = Path(args.runs_dir)

    # Load review exports
    try:
        runs_data = load_review_exports(runs_dir)
    except Exception as e:
        print(f"Error loading review exports: {e}", file=sys.stderr)
        sys.exit(1)

    if not runs_data:
        print("No review export files found.", file=sys.stderr)
        sys.exit(1)

    # Rank runs
    ranked_runs = rank_runs(
        runs_data,
        min_entry_count=args.min_entry_count,
        require_mixed_outcomes=args.require_mixed_outcomes,
    )

    if not ranked_runs:
        print("No runs matched the criteria.", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.json:
        print(format_json_output(ranked_runs, top_n=args.top))
    else:
        print(format_ranked_table(ranked_runs, top_n=args.top))


if __name__ == "__main__":
    main()

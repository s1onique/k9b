"""CLI entry point for documentation claim candidate backlog reporter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .loader import read_candidates, read_dispositions, read_inventory
from .model import ALL_REVIEW_CLASSES
from .planning import compute_planning_summary, print_planning_summary
from .report import (
    build_backlog,
    compute_summary,
    filter_entries,
    print_recommended,
    print_summary,
    write_json,
    write_tsv,
)
from .selftest import run_self_test

# Valid priority bands
ALL_PRIORITY_BANDS = ["P0", "P1", "P2", "P3", "P4"]


def _validate_review_classes(values: list[str]) -> set[str]:
    """Validate review class values and return as set."""
    invalid = [v for v in values if v not in ALL_REVIEW_CLASSES]
    if invalid:
        valid = ", ".join(sorted(ALL_REVIEW_CLASSES))
        raise argparse.ArgumentTypeError(
            f"Invalid review class(es): {', '.join(invalid)!r}. Valid values: {valid}"
        )
    return set(values)


def _validate_priority_bands(values: list[str]) -> set[str]:
    """Validate priority band values and return as set."""
    invalid = [v for v in values if v not in ALL_PRIORITY_BANDS]
    if invalid:
        valid = ", ".join(ALL_PRIORITY_BANDS)
        raise argparse.ArgumentTypeError(
            f"Invalid priority band(s): {', '.join(invalid)!r}. Valid values: {valid}"
        )
    return set(values)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report documentation claim candidate backlog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        metavar="N",
        help="Number of top candidates to show in summary (default: 50)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="PATH",
        help="Write JSON output to path",
    )
    parser.add_argument(
        "--tsv",
        type=Path,
        metavar="PATH",
        help="Write TSV output to path (unreviewed candidates only)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode",
    )
    parser.add_argument(
        "--include-reviewed",
        action="store_true",
        help="Include already-reviewed candidates in output",
    )
    parser.add_argument(
        "--disposition",
        type=str,
        metavar="DISPOSITION",
        help="Filter by disposition (e.g., ignored_by_policy)",
    )
    parser.add_argument(
        "--doc",
        type=str,
        metavar="PATH",
        help="Filter by doc path (substring match)",
    )
    parser.add_argument(
        "--review-class",
        type=str,
        action="append",
        default=None,
        metavar="CLASS",
        help=f"Filter by review class. Repeatable. Valid values: {', '.join(ALL_REVIEW_CLASSES)}",
    )
    parser.add_argument(
        "--priority-band",
        type=str,
        action="append",
        default=None,
        metavar="BAND",
        help=f"Filter by priority band. Repeatable. Valid values: {', '.join(ALL_PRIORITY_BANDS)}",
    )
    parser.add_argument(
        "--planning",
        action="store_true",
        help="Print planning/stop-continue assessment",
    )

    args = parser.parse_args()

    # Validate --review-class values
    review_classes: set[str] | None = None
    if args.review_class is not None:
        try:
            review_classes = _validate_review_classes(args.review_class)
        except argparse.ArgumentTypeError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1

    # Validate --priority-band values
    priority_bands: set[str] | None = None
    if args.priority_band is not None:
        try:
            priority_bands = _validate_priority_bands(args.priority_band)
        except argparse.ArgumentTypeError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1

    if args.self_test:
        success = run_self_test()
        return 0 if success else 1

    # Load data
    candidates, c_error = read_candidates()
    if c_error:
        print(f"[ERROR] {c_error}", file=sys.stderr)
        return 1

    dispositions, d_error = read_dispositions()
    if d_error:
        print(f"[ERROR] {d_error}", file=sys.stderr)
        return 1

    inventory, i_error = read_inventory()
    if i_error:
        print(f"[WARNING] {i_error}", file=sys.stderr)

    # Build backlog
    entries = build_backlog(
        candidates=candidates,
        dispositions=dispositions,
        inventory=inventory,
        include_reviewed=args.include_reviewed,
        disposition_filter=args.disposition,
        doc_filter=args.doc,
    )

    # Apply review_class and priority_band filters AFTER building backlog
    # (filters need calibrated_score which is computed during build_backlog)
    if review_classes is not None or priority_bands is not None:
        entries = filter_entries(
            entries,
            review_classes=review_classes,
            priority_bands=priority_bands,
        )

    # Compute summary
    summary = compute_summary(entries)

    # Output
    print_summary(entries, summary)
    print_recommended(entries, args.top)

    # Planning output
    if args.planning:
        planning = compute_planning_summary(entries)
        print_planning_summary(planning)

    # Build filters block for JSON output
    filters: dict | None = None
    if review_classes is not None or priority_bands is not None or args.disposition or args.doc or args.include_reviewed:
        filters = {
            "disposition": args.disposition,
            "doc": args.doc,
            "include_reviewed": args.include_reviewed,
            "review_class": sorted(review_classes) if review_classes else None,
            "priority_band": sorted(priority_bands) if priority_bands else None,
        }

    # Write JSON if requested
    if args.json:
        write_json(
            entries,
            summary,
            args.json,
            include_planning=args.planning,
            planning=compute_planning_summary(entries) if args.planning else None,
            filters=filters,
        )
        print(f"\n[INFO] JSON output written to {args.json}")

    # Write TSV if requested (already respects filters via entries)
    if args.tsv:
        write_tsv(entries, args.tsv, include_priority_band=True)
        print(f"\n[INFO] TSV output written to {args.tsv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
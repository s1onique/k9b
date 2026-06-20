"""CLI entry point for documentation claim candidate backlog reporter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .loader import read_candidates, read_dispositions, read_inventory
from .planning import compute_planning_summary, print_planning_summary
from .report import (
    build_backlog,
    compute_summary,
    print_recommended,
    print_summary,
    write_json,
    write_tsv,
)
from .selftest import run_self_test


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
        "--planning",
        action="store_true",
        help="Print planning/stop-continue assessment",
    )

    args = parser.parse_args()

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

    # Compute summary
    summary = compute_summary(entries)

    # Output
    print_summary(entries, summary)
    print_recommended(entries, args.top)

    # Planning output
    if args.planning:
        planning = compute_planning_summary(entries)
        print_planning_summary(planning)

    # Write JSON if requested
    if args.json:
        write_json(entries, summary, args.json, include_planning=args.planning, planning=compute_planning_summary(entries) if args.planning else None)
        print(f"\n[INFO] JSON output written to {args.json}")

    # Write TSV if requested
    if args.tsv:
        write_tsv(entries, args.tsv, include_priority_band=True)
        print(f"\n[INFO] TSV output written to {args.tsv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
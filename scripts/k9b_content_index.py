#!/usr/bin/env python3
"""Content index CLI.

Command-line interface for content index operations:
- rebuild: Full rebuild from source artifacts
- update: Incremental update
- validate: Validate index integrity

Usage:
    python scripts/k9b_content_index.py rebuild --index-db <path> --roots...
    python scripts/k9b_content_index.py update --index-db <path> --roots...
    python scripts/k9b_content_index.py validate --index-db <path>

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from k8s_diag_agent.content_index.indexer import (
    ContentIndexRoots,
    IndexerConfig,
    IndexerSummary,
    rebuild_index,
    update_index,
    validate_index,
)

# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


# =============================================================================
# Argument Parsing
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="k9b_content_index",
        description="Content index CLI for k9b",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Rebuild index:
    %(prog)s rebuild --index-db .k9b/content-index.sqlite \\
      --lab-root fixtures/lab \\
      --trace-capture-root trace-capture \\
      --perf-baseline-root trace-capture/perf-baseline

  Update index:
    %(prog)s update --index-db .k9b/content-index.sqlite \\
      --lab-root fixtures/lab

  Validate index:
    %(prog)s validate --index-db .k9b/content-index.sqlite
        """,
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Rebuild command
    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Full rebuild of content index",
    )
    _add_common_args(rebuild_parser)
    _add_output_args(rebuild_parser)

    # Update command
    update_parser = subparsers.add_parser(
        "update",
        help="Incrementally update content index",
    )
    _add_common_args(update_parser)
    _add_output_args(update_parser)

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate content index integrity",
    )
    validate_parser.add_argument(
        "--index-db",
        type=Path,
        required=True,
        help="Path to the SQLite database",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments to a parser."""
    parser.add_argument(
        "--index-db",
        type=Path,
        required=True,
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--incident-store",
        type=Path,
        help="Path to incident store directory",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="Path to artifact root directory",
    )
    parser.add_argument(
        "--lab-root",
        type=Path,
        help="Path to lab output directory",
    )
    parser.add_argument(
        "--trace-capture-root",
        type=Path,
        help="Path to trace capture directory",
    )
    parser.add_argument(
        "--perf-baseline-root",
        type=Path,
        help="Path to performance baseline directory",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any indexing error",
    )
    parser.add_argument(
        "--include-detail",
        action="store_true",
        help="Include detail projections",
    )


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    """Add output arguments to a parser."""
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )


# =============================================================================
# Command Handlers
# =============================================================================


def handle_rebuild(args: argparse.Namespace) -> int:
    """Handle the rebuild command."""
    roots = ContentIndexRoots(
        incident_store=args.incident_store,
        artifact_root=args.artifact_root,
        lab_root=args.lab_root,
        trace_capture_root=args.trace_capture_root,
        perf_baseline_root=args.perf_baseline_root,
    )

    config = IndexerConfig(
        strict_mode=args.strict,
        include_detail_projections=args.include_detail,
    )

    # Check if any roots are specified
    if not roots.get_active_roots():
        print("Error: At least one root path must be specified", file=sys.stderr)
        return 1

    logging.info("Starting content index rebuild...")
    summary = rebuild_index(args.index_db, roots, config)

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        _print_summary(summary)

    if summary.status == "failed" or summary.errors:
        return 1

    return 0


def handle_update(args: argparse.Namespace) -> int:
    """Handle the update command."""
    roots = ContentIndexRoots(
        incident_store=args.incident_store,
        artifact_root=args.artifact_root,
        lab_root=args.lab_root,
        trace_capture_root=args.trace_capture_root,
        perf_baseline_root=args.perf_baseline_root,
    )

    config = IndexerConfig(
        strict_mode=args.strict,
        include_detail_projections=args.include_detail,
    )

    # Check if any roots are specified
    if not roots.get_active_roots():
        print("Error: At least one root path must be specified", file=sys.stderr)
        return 1

    logging.info("Starting content index update...")
    summary = update_index(args.index_db, roots, config)

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        _print_summary(summary)

    if summary.status == "failed" or summary.errors:
        return 1

    return 0


def handle_validate(args: argparse.Namespace) -> int:
    """Handle the validate command."""
    logging.info(f"Validating content index: {args.index_db}")
    result = validate_index(args.index_db)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_validation_result(result)

    return 0 if result.get("valid", False) else 1


# =============================================================================
# Output Formatting
# =============================================================================


def _print_summary(summary: IndexerSummary) -> None:
    """Print an IndexerSummary in human-readable format."""
    print("\nContent Index Operation Summary")
    print("=" * 50)
    print(f"Schema Version: {summary.index_schema_version}")
    print(f"Command: {summary.command}")
    print(f"Status: {summary.status}")
    print(f"Started: {summary.started_at}")
    print(f"Finished: {summary.finished_at}")
    print()
    print("Item Counts:")
    print(f"  Discovered:  {summary.items_discovered}")
    print(f"  Indexed:     {summary.items_indexed}")
    print(f"  Updated:     {summary.items_updated}")
    print(f"  Unchanged:   {summary.items_unchanged}")
    print(f"  Tombstoned:  {summary.items_tombstoned}")
    print(f"  Skipped:     {summary.items_skipped}")
    print(f"  Projections: {summary.projections_written}")

    if summary.warnings:
        print()
        print("Warnings:")
        for warning in summary.warnings[:5]:
            print(f"  - {warning}")
        if len(summary.warnings) > 5:
            print(f"  ... and {len(summary.warnings) - 5} more")

    if summary.errors:
        print()
        print("Errors:")
        for error in summary.errors:
            print(f"  - {error}")

    print()
    print(f"VERIFICATION GATE: {'PASSED' if summary.status == 'ok' else 'FAILED'}")


def _print_validation_result(result: dict) -> None:
    """Print a validation result in human-readable format."""
    print("\nContent Index Validation Result")
    print("=" * 50)
    print(f"Valid: {result.get('valid', False)}")

    if "schema_version" in result:
        print(f"Schema Version: {result['schema_version']}")

    if "counts" in result:
        counts = result["counts"]
        print()
        print("Counts:")
        print(f"  Total Items:      {counts.get('total_items', 0)}")
        print(f"  Active Items:     {counts.get('active_items', 0)}")
        print(f"  Deleted Items:    {counts.get('deleted_items', 0)}")
        print(f"  Projections:      {counts.get('projections', 0)}")

    if "errors" in result and result["errors"]:
        print()
        print("Errors:")
        for error in result["errors"]:
            print(f"  - {error}")

    if "warnings" in result and result["warnings"]:
        print()
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    print()
    print(f"VERIFICATION GATE: {'PASSED' if result.get('valid', False) else 'FAILED'}")


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    try:
        if args.command == "rebuild":
            return handle_rebuild(args)
        elif args.command == "update":
            return handle_update(args)
        elif args.command == "validate":
            return handle_validate(args)
        else:
            parser.print_help()
            return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130

    except Exception as e:
        logging.exception("Unexpected error")
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

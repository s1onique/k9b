#!/usr/bin/env python3
"""Batch execution of eligible next-check candidates.

This script executes all currently eligible next-check candidates that are:
- safe (safeToAutomate=true)
- runnable (valid command family, has description, has context)
- not yet executed in this run

The flow:
1. Loads the next_check_plan from the latest health run
2. Collects already-executed candidate indices from existing execution artifacts
3. Filters candidates to find eligible ones
4. Executes each eligible candidate using the existing manual_next_check flow
5. Refreshes the diagnostic pack mirror

Usage:
    python scripts/run_batch_next_checks.py --run-id <run_id> [--runs-dir <path>]
    python scripts/run_batch_next_checks.py --latest [--runs-dir <path>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from k8s_diag_agent.batch import run_batch_next_checks  # noqa: E402
from k8s_diag_agent.structured_logging import emit_structured_log

COMPONENT_NAME = "batch-next-check-runner"


def _refresh_diagnostic_pack(runs_dir: Path, run_id: str, run_label: str) -> bool:
    """Refresh the diagnostic pack mirror and export usefulness review artifact."""
    try:
        # Import here to avoid circular imports
        from scripts.build_diagnostic_pack import create_diagnostic_pack  # noqa: E402

        emit_structured_log(
            component=COMPONENT_NAME,
            message="Refreshing diagnostic pack",
            run_label=run_label,
            run_id=run_id,
        )

        pack_path = create_diagnostic_pack(run_id, runs_dir)
        emit_structured_log(
            component=COMPONENT_NAME,
            message=f"Diagnostic pack refreshed: {pack_path}",
            run_label=run_label,
            run_id=run_id,
            metadata={"pack_path": str(pack_path)},
        )

        # Export run-scoped usefulness review artifact for recent runs
        _export_usefulness_review(runs_dir, run_id, run_label)

        return True
    except Exception as exc:
        emit_structured_log(
            component=COMPONENT_NAME,
            message=f"Failed to refresh diagnostic pack: {exc}",
            severity="ERROR",
            run_label=run_label,
            run_id=run_id,
            metadata={"error": str(exc)},
        )
        return False


def _export_usefulness_review(runs_dir: Path, run_id: str, run_label: str) -> bool:
    """Export run-scoped usefulness review artifact for the run.

    Produces:
    - Run-scoped file: runs/health/diagnostic-packs/<run_id>/next_check_usefulness_review.json
    - Mirror at latest: runs/health/diagnostic-packs/latest/next_check_usefulness_review.json
    """
    try:
        from scripts.export_next_check_usefulness_review import (  # noqa: E402
            export_next_check_usefulness_review,
        )

        emit_structured_log(
            component=COMPONENT_NAME,
            message="Exporting run-scoped usefulness review artifact",
            run_label=run_label,
            run_id=run_id,
        )

        # First, export to run-scoped path
        run_scoped_path = export_next_check_usefulness_review(
            runs_dir,
            run_id=run_id,
            use_run_scoped_path=True,
        )
        emit_structured_log(
            component=COMPONENT_NAME,
            message=f"Exported run-scoped usefulness review: {run_scoped_path}",
            run_label=run_label,
            run_id=run_id,
            metadata={
                "artifact_path": str(run_scoped_path),
                "path_type": "run_scoped",
            },
        )

        # Also export to /latest/ as a mirror for convenience
        latest_path = export_next_check_usefulness_review(
            runs_dir,
            run_id=run_id,
            use_run_scoped_path=False,
        )
        emit_structured_log(
            component=COMPONENT_NAME,
            message=f"Exported latest mirror usefulness review: {latest_path}",
            run_label=run_label,
            run_id=run_id,
            metadata={
                "artifact_path": str(latest_path),
                "path_type": "latest_mirror",
            },
        )

        return True
    except Exception as exc:
        emit_structured_log(
            component=COMPONENT_NAME,
            message=f"Failed to export usefulness review: {exc}",
            severity="WARNING",
            run_label=run_label,
            run_id=run_id,
            metadata={"error": str(exc)},
        )
        return False


def _find_latest_run_id(runs_dir: Path) -> str:
    """Find the most recent run ID from the health directory."""
    run_health_dir = runs_dir / "health"
    ui_index_path = run_health_dir / "ui-index.json"
    if not ui_index_path.exists():
        raise FileNotFoundError(f"UI index not found: {ui_index_path}")
    index_data = json.loads(ui_index_path.read_text(encoding="utf-8"))
    run_entry = cast(dict[str, Any], index_data.get("run") or {})
    run_id = run_entry.get("run_id")
    if not isinstance(run_id, str):
        raise ValueError("Could not find run_id in UI index")
    return run_id


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch execute eligible next-check candidates."
    )
    parser.add_argument(
        "--run-id",
        help="Specific run ID to operate on",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Use the latest run",
    )
    parser.add_argument(
        "--runs-dir",
        default="runs",
        help="Path to runs directory (default: runs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be executed, don't actually run",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    runs_dir = Path(args.runs_dir)

    # Determine run_id
    if args.run_id:
        run_id = args.run_id
    elif args.latest:
        run_id = _find_latest_run_id(runs_dir)
        print(f"Using latest run: {run_id}")
    else:
        print("Error: Must specify either --run-id or --latest", file=sys.stderr)
        sys.exit(1)

    # Get run_label for logging
    run_label = run_id
    try:
        run_health_dir = runs_dir / "health"
        ui_index_path = run_health_dir / "ui-index.json"
        if ui_index_path.exists():
            index_data = json.loads(ui_index_path.read_text(encoding="utf-8"))
            run_entry = cast(dict[str, Any], index_data.get("run") or {})
            run_label = str(run_entry.get("run_label") or run_id)
    except Exception:
        pass

    try:
        result = run_batch_next_checks(
            runs_dir=runs_dir,
            run_id=run_id,
            dry_run=args.dry_run,
        )

        print("\nBatch Execution Summary:")
        print(f"  Total candidates: {result.total_candidates}")
        print(f"  Eligible candidates: {result.eligible_candidates}")
        print(f"  Executed: {result.executed_count}")
        print(f"  Skipped (already executed): {result.skipped_already_executed}")
        print(f"  Skipped (ineligible): {result.skipped_ineligible}")
        print(f"  Failed: {result.failed_count}")
        print(f"  Succeeded: {result.success_count}")

        # Refresh diagnostic pack after execution (if not dry run and we executed something)
        if result.executed_count > 0 and not args.dry_run:
            _refresh_diagnostic_pack(runs_dir, run_id, run_label)

        if result.failed_count > 0:
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
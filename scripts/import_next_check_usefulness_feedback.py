#!/usr/bin/env python3
"""Import batch usefulness feedback for executed next checks.

This script reads a JSON file containing batch usefulness judgments and applies
them to existing next-check-execution artifacts.

Input: JSON file with usefulness feedback (schema: next-check-usefulness-feedback/v2)

The import is idempotent: re-importing the same feedback entry updates the artifact
in place without duplication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from k8s_diag_agent.external_analysis.artifact import (  # noqa: E402
    ExternalAnalysisPurpose,
    UsefulnessClass,
)

# Schema version for the import file
IMPORT_SCHEMA_VERSION = "next-check-usefulness-feedback/v2"

# Supported usefulness classes (must match the contract)
SUPPORTED_USEFULNESS_CLASSES = frozenset({
    UsefulnessClass.USEFUL.value,
    UsefulnessClass.PARTIAL.value,
    UsefulnessClass.NOISY.value,
    UsefulnessClass.EMPTY.value,
})


class ImportResult:
    """Result of a feedback import operation."""

    def __init__(
        self,
        success_count: int = 0,
        error_count: int = 0,
        skipped_count: int = 0,
        updated_count: int = 0,
        errors: list[str] | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        self.success_count = success_count
        self.error_count = error_count
        self.skipped_count = skipped_count
        self.updated_count = updated_count
        self.errors = errors or []
        self.summary = summary or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_count": self.success_count,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "updated_count": self.updated_count,
            "errors": self.errors,
            "summary": self.summary,
        }


def import_next_check_usefulness_feedback(
    runs_dir: Path,
    input_file: Path,
    *,
    dry_run: bool = False,
) -> ImportResult:
    """Import batch usefulness feedback for next-check executions.

    Args:
        runs_dir: Path to the runs directory (contains health/)
        input_file: Path to the JSON file containing usefulness feedback
        dry_run: If True, validate but don't write changes

    Returns:
        ImportResult with counts and summary statistics
    """
    runs_dir = runs_dir.expanduser().resolve()
    run_health_dir = runs_dir / "health"

    # Read and validate input file
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    input_data = json.loads(input_file.read_text(encoding="utf-8"))

    # Validate schema version
    schema_version = input_data.get("schema_version")
    if schema_version != IMPORT_SCHEMA_VERSION:
        raise ValueError(
            f"Invalid schema version: {schema_version!r}. "
            f"Expected: {IMPORT_SCHEMA_VERSION!r}"
        )

    # Validate entries exist
    entries = input_data.get("entries")
    if not entries or not isinstance(entries, list):
        raise ValueError("Input file must contain a non-empty 'entries' list")

    result = ImportResult()
    run_id = input_data.get("run_id", "unknown")

    # Track dedupe keys to detect re-imports
    seen_keys: set[str] = set()

    # Aggregate statistics for summary
    usefulness_class_counts: dict[str, int] = defaultdict(int)
    command_family_counts: dict[str, int] = defaultdict(int)
    duplicate_groups: dict[str, int] = defaultdict(int)

    # Process each entry
    for idx, entry in enumerate(entries):
        try:
            process_result = _process_entry(entry, run_health_dir, dry_run=dry_run)
            if process_result.updated:
                result.updated_count += 1
            if process_result.skipped:
                result.skipped_count += 1
            else:
                result.success_count += 1

            # Generate dedupe key for this entry
            dedupe_key = _generate_dedupe_key(entry)
            if dedupe_key in seen_keys:
                duplicate_groups["reimport"] += 1
            seen_keys.add(dedupe_key)

            # Aggregate statistics
            usefulness_class = entry.get("usefulness_class")
            if usefulness_class:
                usefulness_class_counts[usefulness_class] += 1

            command_family = entry.get("command_family")
            if command_family:
                command_family_counts[command_family] += 1

        except ValueError as e:
            result.error_count += 1
            result.errors.append(f"Entry {idx}: {e}")

    # Build summary artifact data
    result.summary = _build_summary(
        run_id=run_id,
        usefulness_class_counts=dict(usefulness_class_counts),
        command_family_counts=dict(command_family_counts),
        duplicate_groups=dict(duplicate_groups),
        total_entries=len(entries),
        success_count=result.success_count,
        error_count=result.error_count,
    )

    # Write summary artifact (unless dry_run)
    if not dry_run and result.success_count > 0:
        _write_summary_artifact(run_health_dir, run_id, result.summary)

    return result


from typing import NamedTuple


class ProcessResult(NamedTuple):
    """Result of processing a single feedback entry."""
    updated: bool
    skipped: bool


def _process_entry(
    entry: dict[str, object],
    run_health_dir: Path,
    *,
    dry_run: bool = False,
) -> ProcessResult:
    """Process a single feedback entry.

    Args:
        entry: The feedback entry from the input file
        run_health_dir: Path to the health directory
        dry_run: If True, validate but don't write changes

    Returns:
        ProcessResult with updated and skipped flags
    """
    # Validate required fields
    artifact_path_raw = entry.get("artifact_path")
    if not artifact_path_raw or not isinstance(artifact_path_raw, str):
        raise ValueError("Missing or invalid field: artifact_path")
    artifact_path: str = artifact_path_raw

    usefulness_class_raw = entry.get("usefulness_class")
    if not usefulness_class_raw or not isinstance(usefulness_class_raw, str):
        raise ValueError("Missing or invalid field: usefulness_class")
    usefulness_class: str = usefulness_class_raw

    # Validate usefulness_class is supported
    if usefulness_class not in SUPPORTED_USEFULNESS_CLASSES:
        raise ValueError(
            f"Invalid usefulness_class: {usefulness_class!r}. "
            f"Must be one of: {sorted(SUPPORTED_USEFULNESS_CLASSES)}"
        )

    # Resolve the artifact path
    full_artifact_path = run_health_dir / artifact_path

    # Validate artifact exists
    if not full_artifact_path.exists():
        raise ValueError(f"Artifact not found: {artifact_path}")

    # Load the artifact
    try:
        artifact_data = json.loads(full_artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in artifact: {artifact_path}") from e

    # Validate purpose is next-check-execution
    purpose = artifact_data.get("purpose")
    if purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION.value:
        raise ValueError(
            f"Artifact purpose is {purpose!r}, not {ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION.value}: {artifact_path}"
        )

    # Idempotency check: if usefulness_class is already set to the same value, skip
    existing_class = artifact_data.get("usefulness_class")
    usefulness_summary = entry.get("usefulness_summary")
    existing_summary = artifact_data.get("usefulness_summary")

    if existing_class == usefulness_class:
        # Check if summary also matches (complete idempotency)
        if existing_summary == usefulness_summary:
            return ProcessResult(updated=False, skipped=True)  # no changes needed
        # Summary differs but class matches - this is an update
        needs_update = True
    else:
        needs_update = True

    # Update usefulness fields
    if not dry_run and needs_update:
        artifact_data["usefulness_class"] = usefulness_class
        if usefulness_summary:
            artifact_data["usefulness_summary"] = usefulness_summary
        else:
            # Remove if empty
            artifact_data.pop("usefulness_summary", None)

        # Write the updated artifact back
        full_artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

    return ProcessResult(updated=True, skipped=False)


def _generate_dedupe_key(entry: dict[str, object]) -> str:
    """Generate a deterministic dedupe key for an entry.

    The dedupe key is based on the combination of run_id + candidate_index + artifact_path.
    """
    run_id = str(entry.get("run_id", ""))
    candidate_index = str(entry.get("candidate_index", ""))
    artifact_path = str(entry.get("artifact_path", ""))

    key_parts: list[str] = [run_id, candidate_index, artifact_path]
    key_str = "|".join(key_parts)
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def _build_summary(
    run_id: str,
    usefulness_class_counts: dict[str, int],
    command_family_counts: dict[str, int],
    duplicate_groups: dict[str, int],
    total_entries: int,
    success_count: int,
    error_count: int,
) -> dict[str, Any]:
    """Build the summary data structure."""
    from datetime import UTC, datetime

    # Identify top candidates for planner improvement
    # "noisy" and "empty" are candidates for improvement
    improvement_candidates: list[dict[str, Any]] = []
    noisy_count = usefulness_class_counts.get("noisy", 0)
    empty_count = usefulness_class_counts.get("empty", 0)
    partial_count = usefulness_class_counts.get("partial", 0)

    if noisy_count > 0:
        improvement_candidates.append({
            "usefulness_class": "noisy",
            "count": noisy_count,
            "recommendation": "Review command selection criteria to reduce false positives",
        })
    if empty_count > 0:
        improvement_candidates.append({
            "usefulness_class": "empty",
            "count": empty_count,
            "recommendation": "Verify command availability and cluster connectivity",
        })
    if partial_count > 0:
        improvement_candidates.append({
            "usefulness_class": "partial",
            "count": partial_count,
            "recommendation": "Consider adding filters or context checks to improve signal quality",
        })

    return {
        "schema_version": "usefulness-summary/v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "statistics": {
            "total_entries": total_entries,
            "successfully_imported": success_count,
            "errors": error_count,
        },
        "usefulness_class_counts": usefulness_class_counts,
        "command_family_counts": command_family_counts,
        "duplicate_group_stats": duplicate_groups,
        "planner_improvement": {
            "candidate_count": noisy_count + empty_count + partial_count,
            "candidates": improvement_candidates,
        },
    }


def _write_summary_artifact(
    run_health_dir: Path,
    run_id: str,
    summary: dict[str, Any],
) -> Path:
    """Write the derived summary artifact."""
    summary_dir = run_health_dir / "diagnostic-packs" / run_id
    summary_dir.mkdir(parents=True, exist_ok=True)

    summary_path = summary_dir / "usefulness_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import batch usefulness feedback for next-check executions."
    )
    parser.add_argument(
        "--runs-dir",
        required=True,
        help="Path to the runs directory (contains health/)",
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to the JSON file containing usefulness feedback",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate input but don't write changes",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs_dir = Path(args.runs_dir)
    input_file = Path(args.input_file)

    try:
        result = import_next_check_usefulness_feedback(
            runs_dir,
            input_file,
            dry_run=args.dry_run,
        )

        print(f"Import complete:")
        print(f"  - Successfully imported: {result.success_count}")
        print(f"  - Updated (changed): {result.updated_count}")
        print(f"  - Skipped (idempotent): {result.skipped_count}")
        print(f"  - Errors: {result.error_count}")

        if result.success_count > 0 and not args.dry_run:
            # Show summary statistics
            summary = result.summary
            print(f"\nUsefulness class distribution:")
            for cls, count in summary.get("usefulness_class_counts", {}).items():
                print(f"  - {cls}: {count}")

            if summary.get("command_family_counts"):
                print(f"\nCommand family distribution:")
                for family, count in summary.get("command_family_counts", {}).items():
                    print(f"  - {family}: {count}")

            improvement = summary.get("planner_improvement", {})
            if improvement.get("candidate_count", 0) > 0:
                print(f"\nPlanners flagged for improvement: {improvement['candidate_count']}")
                for candidate in improvement.get("candidates", []):
                    print(f"  - {candidate['usefulness_class']} ({candidate['count']}): {candidate['recommendation']}")

        if result.errors:
            print(f"\nErrors encountered:")
            for error in result.errors[:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(result.errors) > 10:
                print(f"  ... and {len(result.errors) - 10} more")

        if result.error_count > 0:
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

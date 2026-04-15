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
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from k8s_diag_agent.external_analysis.artifact import (  # noqa: E402
    ExternalAnalysisPurpose,
    JudgmentScope,
    ProblemClass,
    ReviewStage,
    ReviewerConfidence,
    UsefulnessClass,
    Workstream,
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

# Supported context field enums
SUPPORTED_REVIEW_STAGES = frozenset({e.value for e in ReviewStage})
SUPPORTED_WORKSTREAMS = frozenset({e.value for e in Workstream})
SUPPORTED_PROBLEM_CLASSES = frozenset({e.value for e in ProblemClass})
SUPPORTED_JUDGMENT_SCOPES = frozenset({e.value for e in JudgmentScope})
SUPPORTED_REVIEWER_CONFIDENCES = frozenset({e.value for e in ReviewerConfidence})

# Allowed roots for absolute path resolution (security: prevent path traversal)
ALLOWED_ROOTS: list[Path] = []


def _configure_logging(verbose: bool = False) -> None:
    """Configure structured logging for import diagnostics."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def _set_allowed_roots(runs_dir: Path) -> None:
    """Set allowed roots for absolute path resolution."""
    global ALLOWED_ROOTS
    runs_dir = runs_dir.resolve()
    ALLOWED_ROOTS = [runs_dir, ROOT.resolve()]


class ArtifactResolutionResult(NamedTuple):
    """Result of artifact path resolution."""
    resolved_path: Path
    resolution_mode: str  # "absolute", "modern", "legacy", "unresolved"
    exists: bool


def _resolve_artifact_path(
    artifact_path: str,
    runs_dir: Path,
    run_health_dir: Path,
) -> ArtifactResolutionResult:
    """Resolve artifact path with backward compatibility for modern and legacy layouts.

    Resolution order:
    1. If absolute and inside allowed repo root, use it
    2. Try modern health-root layout: runs/health/<artifact_path>
    3. Try legacy runs-root layout: runs/<artifact_path>
    4. If unresolved, report clear structured error

    Args:
        artifact_path: The artifact path from feedback entry
        runs_dir: Path to runs directory
        run_health_dir: Path to health directory

    Returns:
        ArtifactResolutionResult with resolved path and resolution mode
    """
    logger = logging.getLogger(__name__)

    # Case 1: Absolute path - check if inside allowed roots
    if Path(artifact_path).is_absolute():
        abs_path = Path(artifact_path).resolve()
        allowed = False
        for root in ALLOWED_ROOTS:
            try:
                abs_path.relative_to(root)
                allowed = True
                break
            except ValueError:
                continue

        if allowed:
            logger.debug(
                f"Artifact resolution: original=%s resolved=%s mode=absolute exists=%s",
                artifact_path,
                abs_path,
                abs_path.exists(),
            )
            return ArtifactResolutionResult(
                resolved_path=abs_path,
                resolution_mode="absolute",
                exists=abs_path.exists(),
            )
        else:
            # Absolute path outside allowed roots - report as unresolved
            logger.debug(
                f"Artifact resolution: original=%s resolved=%s mode=unresolved exists=False (outside allowed roots)",
                artifact_path,
                abs_path,
            )
            return ArtifactResolutionResult(
                resolved_path=abs_path,
                resolution_mode="unresolved",
                exists=False,
            )

    # Case 2: Try modern health-root layout: runs/health/<artifact_path>
    modern_path = run_health_dir / artifact_path
    if modern_path.exists():
        logger.debug(
            f"Artifact resolution: original=%s resolved=%s mode=modern exists=True",
            artifact_path,
            modern_path,
        )
        return ArtifactResolutionResult(
            resolved_path=modern_path,
            resolution_mode="modern",
            exists=True,
        )

    # Case 3: Try legacy runs-root layout: runs/<artifact_path>
    legacy_path = runs_dir / artifact_path
    if legacy_path.exists():
        logger.debug(
            f"Artifact resolution: original=%s resolved=%s mode=legacy exists=True",
            artifact_path,
            legacy_path,
        )
        return ArtifactResolutionResult(
            resolved_path=legacy_path,
            resolution_mode="legacy",
            exists=True,
        )

    # Case 4: Unresolved - report clear error
    logger.debug(
        f"Artifact resolution: original=%s mode=unresolved exists=False (not found in modern or legacy locations)",
        artifact_path,
    )
    return ArtifactResolutionResult(
        resolved_path=modern_path,  # Use modern path as default for error reporting
        resolution_mode="unresolved",
        exists=False,
    )


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
    logger = logging.getLogger(__name__)
    runs_dir = runs_dir.expanduser().resolve()
    run_health_dir = runs_dir / "health"

    # Set allowed roots for absolute path resolution
    _set_allowed_roots(runs_dir)

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

    # Group entries by their individual run_id for per-run summary generation
    entries_by_run: dict[str, list[dict[str, object]]] = defaultdict(list)

    # Track dedupe keys to detect re-imports (global scope)
    seen_keys: set[str] = set()

    # Aggregate statistics for summary (global, for backwards compatibility)
    usefulness_class_counts: dict[str, int] = defaultdict(int)
    command_family_counts: dict[str, int] = defaultdict(int)
    duplicate_groups: dict[str, int] = defaultdict(int)

    # Process each entry
    for idx, entry in enumerate(entries):
        # Extract run_id from each individual entry (not from file top-level)
        entry_run_id = str(entry.get("run_id", "unknown"))
        if entry_run_id == "unknown":
            # Fallback to file-level run_id if entry doesn't have one
            entry_run_id = input_data.get("run_id", "unknown")

        # Group entry by its run_id for per-run summary
        entries_by_run[entry_run_id].append(entry)

        try:
            process_result = _process_entry(entry, runs_dir, run_health_dir, dry_run=dry_run)
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

    # Build and write per-run summary artifacts (unless dry_run)
    # Summary is a derived artifact - rebuild on every import including idempotent re-imports
    # Check if there are any entries to process (imported OR skipped)
    has_entries_to_process = result.success_count > 0 or result.skipped_count > 0

    if not dry_run and has_entries_to_process and entries_by_run:
        # Write a summary for each unique run_id that had entries
        for run_id, run_entries in entries_by_run.items():
            # Skip "unknown" if there are valid run_ids - this prevents writing to wrong bucket
            if run_id == "unknown" and len(entries_by_run) > 1:
                logger.warning(
                    "Skipping summary write for 'unknown' run_id bucket when other valid run_ids exist. "
                    "Valid run_ids: %s",
                    list(entries_by_run.keys()),
                )
                continue

            # Determine rebuild reason for logging
            if result.success_count > 0 and result.skipped_count > 0:
                rebuild_reason = "mixed_import_and_idempotent"
            elif result.success_count > 0:
                rebuild_reason = "new_import"
            else:
                rebuild_reason = "idempotent_reimport"

            # Build per-run statistics
            run_usefulness_counts: dict[str, int] = defaultdict(int)
            run_command_counts: dict[str, int] = defaultdict(int)

            for entry in run_entries:
                usefulness_class = entry.get("usefulness_class")
                if usefulness_class:
                    run_usefulness_counts[str(usefulness_class)] += 1

                command_family = entry.get("command_family")
                if command_family:
                    run_command_counts[str(command_family)] += 1

            # Build summary for this specific run
            run_summary = _build_summary(
                run_id=run_id,
                usefulness_class_counts=dict(run_usefulness_counts),
                command_family_counts=dict(run_command_counts),
                duplicate_groups={},  # Per-run duplicates not tracked separately
                total_entries=len(run_entries),
                success_count=len(run_entries),
                error_count=0,  # Errors already counted in global result
            )

            # Write per-run summary artifact with structured logging
            intended_path = run_health_dir / "diagnostic-packs" / run_id / "usefulness_summary.json"
            logger.info(
                "usefulness_summary: run_id=%s path=%s entry_count=%d rebuild_attempted=true rebuild_reason=%s",
                run_id,
                intended_path,
                len(run_entries),
                rebuild_reason,
            )

            try:
                written_path = _write_summary_artifact(run_health_dir, run_id, run_summary)
                write_succeeded = written_path.exists()
                logger.info(
                    "usefulness_summary: run_id=%s path=%s write_succeeded=%s file_exists_after_write=%s",
                    run_id,
                    written_path,
                    write_succeeded,
                    write_succeeded,
                )
            except Exception as e:
                logger.error(
                    "usefulness_summary: run_id=%s path=%s write_succeeded=false error=%s",
                    run_id,
                    intended_path,
                    str(e),
                )
                raise

        # Also build the global summary for backwards compatibility (single run case)
        if len(entries_by_run) == 1:
            # Only one run_id - use the global summary
            result.summary = _build_summary(
                run_id=list(entries_by_run.keys())[0],
                usefulness_class_counts=dict(usefulness_class_counts),
                command_family_counts=dict(command_family_counts),
                duplicate_groups=dict(duplicate_groups),
                total_entries=len(entries),
                success_count=result.success_count,
                error_count=result.error_count,
            )
        else:
            # Multiple run_ids - summary is the collection of per-run summaries
            result.summary = _build_summary(
                run_id="multi-run-import",
                usefulness_class_counts=dict(usefulness_class_counts),
                command_family_counts=dict(command_family_counts),
                duplicate_groups=dict(duplicate_groups),
                total_entries=len(entries),
                success_count=result.success_count,
                error_count=result.error_count,
            )

    return result


def _validate_context_fields(entry: dict[str, object]) -> None:
    """Validate optional context fields in feedback entry.

    Args:
        entry: The feedback entry to validate

    Raises:
        ValueError: If any context field has an invalid value
    """
    # Validate review_stage
    review_stage = entry.get("review_stage")
    if review_stage is not None and review_stage not in SUPPORTED_REVIEW_STAGES:
        raise ValueError(
            f"Invalid review_stage: {review_stage!r}. "
            f"Must be one of: {sorted(SUPPORTED_REVIEW_STAGES)}"
        )

    # Validate workstream
    workstream = entry.get("workstream")
    if workstream is not None and workstream not in SUPPORTED_WORKSTREAMS:
        raise ValueError(
            f"Invalid workstream: {workstream!r}. "
            f"Must be one of: {sorted(SUPPORTED_WORKSTREAMS)}"
        )

    # Validate problem_class
    problem_class = entry.get("problem_class")
    if problem_class is not None and problem_class not in SUPPORTED_PROBLEM_CLASSES:
        raise ValueError(
            f"Invalid problem_class: {problem_class!r}. "
            f"Must be one of: {sorted(SUPPORTED_PROBLEM_CLASSES)}"
        )

    # Validate judgment_scope
    judgment_scope = entry.get("judgment_scope")
    if judgment_scope is not None and judgment_scope not in SUPPORTED_JUDGMENT_SCOPES:
        raise ValueError(
            f"Invalid judgment_scope: {judgment_scope!r}. "
            f"Must be one of: {sorted(SUPPORTED_JUDGMENT_SCOPES)}"
        )

    # Validate reviewer_confidence
    reviewer_confidence = entry.get("reviewer_confidence")
    if reviewer_confidence is not None and reviewer_confidence not in SUPPORTED_REVIEWER_CONFIDENCES:
        raise ValueError(
            f"Invalid reviewer_confidence: {reviewer_confidence!r}. "
            f"Must be one of: {sorted(SUPPORTED_REVIEWER_CONFIDENCES)}"
        )


def _extract_context_fields(entry: dict[str, object]) -> dict[str, str | None]:
    """Extract context fields from feedback entry for persistence.

    Args:
        entry: The feedback entry

    Returns:
        Dict with context field names and values (None for missing)
    """
    return {
        "review_stage": str(entry["review_stage"]) if entry.get("review_stage") else None,
        "workstream": str(entry["workstream"]) if entry.get("workstream") else None,
        "problem_class": str(entry["problem_class"]) if entry.get("problem_class") else None,
        "judgment_scope": str(entry["judgment_scope"]) if entry.get("judgment_scope") else None,
        "reviewer_confidence": str(entry["reviewer_confidence"]) if entry.get("reviewer_confidence") else None,
    }


class ProcessResult(NamedTuple):
    """Result of processing a single feedback entry."""
    updated: bool
    skipped: bool


def _process_entry(
    entry: dict[str, object],
    runs_dir: Path,
    run_health_dir: Path,
    *,
    dry_run: bool = False,
) -> ProcessResult:
    """Process a single feedback entry.

    Args:
        entry: The feedback entry from the input file
        runs_dir: Path to runs directory
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

    # Validate optional context fields (if present)
    _validate_context_fields(entry)

    # Resolve the artifact path with backward compatibility
    resolution_result = _resolve_artifact_path(artifact_path, runs_dir, run_health_dir)

    # Validate artifact exists
    if not resolution_result.exists:
        raise ValueError(
            f"Artifact not found: {artifact_path} "
            f"(resolution_mode={resolution_result.resolution_mode})"
        )

    full_artifact_path = resolution_result.resolved_path

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

    # Update usefulness fields and context fields
    if not dry_run and needs_update:
        artifact_data["usefulness_class"] = usefulness_class
        if usefulness_summary:
            artifact_data["usefulness_summary"] = usefulness_summary
        else:
            # Remove if empty
            artifact_data.pop("usefulness_summary", None)

        # Update context fields for stage-aware feedback
        context_fields = _extract_context_fields(entry)
        for field_name, field_value in context_fields.items():
            if field_value is not None:
                artifact_data[field_name] = field_value
            else:
                # Remove if None to keep artifact clean
                artifact_data.pop(field_name, None)

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
    # New parameters for conditional rollups
    context_aggregates: dict[str, dict[str, dict[str, int]]] | None = None,
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

    result = {
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

    # Add context-aware conditional rollups if available
    if context_aggregates:
        result["context_aggregates"] = context_aggregates

    return result


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

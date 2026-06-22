"""Allowlist verification logic.

This module contains the core comparison logic for verifying that:
1. Current allowlist entries are subset of baseline
2. Baseline doesn't grow in a transaction
3. Allowlisted files that are modified are removed from the active allowlist
4. .llm-friendly-ignore entries don't escape the repo
"""

from __future__ import annotations

from pathlib import Path

from .baseline import (
    check_baseline_duplicates,
    normalize_path,
    parse_baseline_csv,
)
from .changed_files import (
    GIT_STATUS_RENAMED,
    ChangedFile,
    get_baseline_from_git,
    get_changed_files,
)
from .sources import get_current_allowlist_entries


def extract_actual_path(current_path: str) -> str:
    """Extract the actual file path from a current path entry.

    For .llm-friendly-ignore entries (format: "actual_file:ignore_file"),
    returns the actual_file portion.
    For direct paths, returns the path as-is.
    """
    if ":" in current_path and not current_path.startswith("/"):
        actual_file, _ignore_file = current_path.rsplit(":", 1)
        return normalize_path(actual_file)
    return normalize_path(current_path)


def compare_against_baseline(
    current_paths: set[str],
    baseline_entries: list[dict],
) -> tuple[list[str], list[str]]:
    """Compare current allowlist against baseline.

    Returns:
        (new_entries, warnings) where new_entries are paths not in baseline
    """
    baseline_by_path: dict[str, str] = {}
    for entry in baseline_entries:
        path = normalize_path(entry.get("path", "").strip())
        source = entry.get("source", "").strip()
        baseline_by_path[path] = source

    baseline_paths: set[str] = set(baseline_by_path.keys())

    new_entries: list[str] = []

    for path in sorted(current_paths):
        actual_file = extract_actual_path(path)
        if actual_file not in baseline_paths:
            new_entries.append(path)

    return new_entries, []


def check_baseline_growth(
    current_baseline_entries: list[dict],
    old_baseline_paths: set[str],
) -> tuple[list[str], list[str]]:
    """Check if baseline has grown (new entries added).

    Returns:
        (errors, warnings)
        - errors: baseline has new paths not in old baseline
        - warnings: baseline entries removed (encouraged!)
    """
    errors: list[str] = []
    warnings: list[str] = []

    current_paths: set[str] = set()
    for entry in current_baseline_entries:
        path = normalize_path(entry.get("path", "").strip())
        current_paths.add(path)

    # Find new baseline entries
    new_baseline = current_paths - old_baseline_paths
    removed_baseline = old_baseline_paths - current_paths

    if new_baseline:
        errors.append(
            f"BASELINE GROWTH ({len(new_baseline)} new entries): "
            "Adding baseline entries requires a separate policy change."
        )
        for path in sorted(new_baseline)[:10]:
            errors.append(f"  NEW BASELINE: {path}")
        if len(new_baseline) > 10:
            errors.append(f"  ... and {len(new_baseline) - 10} more")

    if removed_baseline:
        warnings.append(
            f"BASELINE ENTRIES REMOVED ({len(removed_baseline)}): "
            "This is encouraged! Cleanup is good."
        )

    return errors, warnings


def check_modified_allowlisted_files(
    current_paths: set[str],
    baseline_entries: list[dict],
    changed_files: list[ChangedFile],
) -> tuple[list[str], list[str]]:
    """Check if modified files are still allowlisted.

    Returns:
        (failures, warnings)
        - failures: files that were modified AND remain in active allowlist
        - warnings: baseline entries that were modified and removed from active allowlist (good!)
    """
    failures: list[str] = []
    warnings: list[str] = []

    baseline_paths: set[str] = set()
    for entry in baseline_entries:
        path = normalize_path(entry.get("path", "").strip())
        baseline_paths.add(path)

    # Current allowlisted files
    current_allowlisted: set[str] = set()
    for current_path in current_paths:
        actual_file = extract_actual_path(current_path)
        current_allowlisted.add(actual_file)

    # Check each changed file
    for changed in changed_files:
        # Check new path (for renames, this is the destination)
        check_path = changed.path

        # For renames, also check old path
        if changed.status == GIT_STATUS_RENAMED and changed.old_path:
            # Old path was allowlisted? New path is also allowlisted?
            if changed.old_path in baseline_paths and check_path in current_allowlisted:
                failures.append(
                    f"Renamed allowlisted file still allowlisted: "
                    f"{changed.old_path} -> {check_path}"
                )
            elif changed.old_path in baseline_paths:
                # Old was allowlisted, new is not - good!
                warnings.append(
                    f"Renamed allowlisted file removed: {changed.old_path} -> {check_path}"
                )
        elif check_path in baseline_paths:
            # File was in baseline (was allowlisted)
            if check_path in current_allowlisted:
                # Still in active allowlist - this is a failure
                failures.append(check_path)
            else:
                # Removed from active allowlist - good!
                warnings.append(check_path)

    return failures, warnings


def check_ignore_repo_escape(
    repo_root: Path,
) -> tuple[list[str], list[str]]:
    """Check if .llm-friendly-ignore files have entries that escape the repo.

    Returns:
        (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    from .sources import find_llm_friendly_ignore_files

    _, parse_errors = find_llm_friendly_ignore_files(repo_root)
    for err in parse_errors:
        if "Cannot read" not in err:
            errors.append(f".llm-friendly-ignore error: {err}")

    return errors, warnings


def run_verification(
    repo_root: Path,
    changed_files: list[ChangedFile] | None = None,
    old_baseline_paths: set[str] | None = None,
    verbose: bool = False,
    skip_baseline_growth_check: bool = False,
) -> tuple[bool, list[str], list[str]]:
    """Run the full verification.

    Args:
        repo_root: Repository root path
        changed_files: List of changed files (None for default/local detection)
        old_baseline_paths: Old baseline paths for growth check (None for local/HEAD)
        verbose: Print verbose output
        skip_baseline_growth_check: Skip baseline growth check (for bootstrap mode)

    Returns:
        (success, errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    baseline_csv = repo_root / "docs" / "tooling" / "llm_large_file_allowlist_baseline.csv"

    if verbose:
        print(f"Using baseline: {baseline_csv}")

    # Check for .llm-friendly-ignore repo escapes
    escape_errors, escape_warnings = check_ignore_repo_escape(repo_root)
    errors.extend(escape_errors)
    warnings.extend(escape_warnings)

    # Parse current baseline
    baseline_entries, parse_errors = parse_baseline_csv(baseline_csv)
    errors.extend(parse_errors)

    if parse_errors and verbose:
        for err in parse_errors:
            print(f"  ERROR: {err}")

    if not baseline_entries and not errors:
        errors.append("No valid baseline entries found")
        return False, errors, warnings

    dup_errors = check_baseline_duplicates(baseline_entries)
    errors.extend(dup_errors)

    if verbose:
        print(f"Baseline entries: {len(baseline_entries)}")

    # Get current allowlist entries
    current_paths, current_errors = get_current_allowlist_entries(repo_root)
    errors.extend(current_errors)

    if verbose:
        print(f"Current allowlist entries: {len(current_paths)}")

    # Get changed files if not provided
    if changed_files is None:
        changed_files, changed_errors = get_changed_files(repo_root, mode="local")
        # CRITICAL: Fail closed on changed-file discovery errors
        errors.extend(changed_errors)
        if verbose:
            print(f"Changed files (local): {len(changed_files)}")

    # Get old baseline for growth check
    if old_baseline_paths is None:
        old_baseline_paths, baseline_git_errors = get_baseline_from_git(repo_root, ref="HEAD")
        # CRITICAL: Fail closed on baseline git errors
        errors.extend(baseline_git_errors)
        if verbose:
            print(f"Old baseline entries (from HEAD): {len(old_baseline_paths)}")

    if not errors:
        # Check for new allowlist entries
        new_entries, _ = compare_against_baseline(current_paths, baseline_entries)

        if new_entries:
            errors.append(
                f"NEW allowlist entries not in baseline ({len(new_entries)}): "
                "Adding allowlist entries is a GATE FAILURE. Split files instead."
            )
            for path in new_entries:
                errors.append(f"  NEW ENTRY: {path}")
                if ":" in path:
                    errors.append(
                        "    HINT: Remove from .llm-friendly-ignore file or split the file"
                    )
                else:
                    errors.append(
                        "    HINT: Remove from ALLOWLIST in scripts/llm_friendly_allowlist.py, or split the file"
                    )

        # Check for baseline growth (skip in bootstrap mode)
        if skip_baseline_growth_check:
            if verbose:
                print("Baseline growth check skipped (bootstrap mode)")
        else:
            baseline_errors, baseline_warnings = check_baseline_growth(
                baseline_entries, old_baseline_paths
            )
            errors.extend(baseline_errors)
            warnings.extend(baseline_warnings)

        # Check modified allowlisted files
        if changed_files:
            modified_failures, modified_warnings = check_modified_allowlisted_files(
                current_paths, baseline_entries, changed_files
            )

            if modified_warnings:
                warnings.append(
                    f"Modified allowlisted files removed from allowlist ({len(modified_warnings)}): "
                    "Good! These were split/shrunk/deleted."
                )
                if verbose:
                    for path in modified_warnings[:10]:
                        print(f"  GOOD: {path}")

            if modified_failures:
                errors.append(
                    f"Modified allowlisted files remain in allowlist ({len(modified_failures)}): "
                    "These must be removed from allowlist in the same transaction."
                )
                for path in modified_failures:
                    errors.append(f"  FAILURE: {path}")
                    errors.append(
                        "    HINT: Split, shrink, delete, or remove from allowlist"
                    )

    if verbose and not errors:
        print("No new entries - verification passed")

    success = len(errors) == 0
    return success, errors, warnings

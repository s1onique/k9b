"""Changed files detection.

This module handles detecting which files have changed in a transaction:
- Local mode: uses git diff against HEAD
- CI mode: uses environment variables or explicit refs
- Fixture mode: reads from a fixture file

Uses status-aware git diff to detect renames and track old/new paths.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .baseline import normalize_path

# Status codes from git diff --name-status
GIT_STATUS_ADDED = "A"
GIT_STATUS_MODIFIED = "M"
GIT_STATUS_DELETED = "D"
GIT_STATUS_RENAMED = "R"
GIT_STATUS_COPIED = "C"
GIT_STATUS_UNMERGED = "U"


@dataclass
class ChangedFile:
    """A file that has changed with its status."""
    path: str
    old_path: str | None  # For renames, the original path
    status: str


def parse_git_diff_status_line(line: str) -> ChangedFile | None:
    """Parse a single line from git diff --name-status -M.

    Format: <status>\t<path>\t[<old_path>]

    Returns:
        ChangedFile or None if line is invalid
    """
    parts = line.split("\t")
    if len(parts) < 2:
        return None

    status = parts[0].strip()
    path = parts[1].strip()

    # Handle renames (R) which have a third field
    old_path = None
    if status.startswith(GIT_STATUS_RENAMED) and len(parts) >= 3:
        old_path = parts[2].strip()

    return ChangedFile(
        path=normalize_path(path),
        old_path=normalize_path(old_path) if old_path else None,
        status=status,
    )


def get_changed_files_local(
    repo_root: Path,
) -> tuple[list[ChangedFile], list[str]]:
    """Get changed files using git diff against HEAD (index).

    Uses --name-status -M to detect renames and track old/new paths.

    Returns:
        (changed_files, errors)
    """
    errors: list[str] = []
    changed: list[ChangedFile] = []

    try:
        # Use --name-status -M for rename detection
        result = subprocess.run(
            ["git", "diff", "--name-status", "-M", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    entry = parse_git_diff_status_line(line)
                    if entry:
                        changed.append(entry)
                    else:
                        errors.append(f"Invalid git diff line: {line}")
        else:
            errors.append(f"git diff failed: {result.stderr}")

        # Also check for staged changes
        result2 = subprocess.run(
            ["git", "diff", "--name-status", "-M", "--cached"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result2.returncode == 0:
            for line in result2.stdout.strip().split("\n"):
                if line.strip():
                    entry = parse_git_diff_status_line(line)
                    if entry:
                        changed.append(entry)

    except subprocess.TimeoutExpired:
        errors.append("git diff timed out")
    except FileNotFoundError:
        errors.append("git not found")
    except Exception as e:
        errors.append(f"git diff error: {e}")

    return changed, errors


def get_changed_files_ci(
    repo_root: Path,
    base_ref: str | None = None,
    head_ref: str | None = None,
) -> tuple[list[ChangedFile], list[str]]:
    """Get changed files using CI refs or environment variables.

    Uses --name-status -M for rename detection.

    Returns:
        (changed_files, errors)
    """
    errors: list[str] = []
    changed: list[ChangedFile] = []

    # Check environment variables first
    base_ref = base_ref or os.environ.get("CI_BASE_REF") or os.environ.get("BASE_REF")
    head_ref = head_ref or os.environ.get("CI_HEAD_REF") or os.environ.get("HEAD_REF")

    if not base_ref or not head_ref:
        base_ref = base_ref or os.environ.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME")
        head_ref = head_ref or os.environ.get("CI_COMMIT_SHA")

    if not base_ref or not head_ref:
        errors.append("No CI refs available. Use --base-ref and --head-ref or set CI env vars.")
        return changed, errors

    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "-M", base_ref, head_ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    entry = parse_git_diff_status_line(line)
                    if entry:
                        changed.append(entry)
                    else:
                        errors.append(f"Invalid git diff line: {line}")
        else:
            errors.append(f"git diff failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        errors.append("git diff timed out")
    except FileNotFoundError:
        errors.append("git not found")
    except Exception as e:
        errors.append(f"git diff error: {e}")

    return changed, errors


def get_changed_files_from_fixture(
    fixture_path: Path,
) -> tuple[list[ChangedFile], list[str]]:
    """Read changed files from a JSON fixture.

    Expected format:
        {
            "changed": [
                {"path": "file1.py", "status": "M"},
                {"path": "file2.py", "old_path": "old.py", "status": "R"}
            ]
        }

    Returns:
        (changed_files, errors)
    """
    errors: list[str] = []
    changed: list[ChangedFile] = []

    if not fixture_path.exists():
        errors.append(f"Fixture file not found: {fixture_path}")
        return changed, errors

    try:
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            errors.append(f"Fixture must be a JSON object, got {type(data).__name__}")
            return changed, errors

        changed_list = data.get("changed", [])
        if not isinstance(changed_list, list):
            errors.append(f"Fixture 'changed' must be a list, got {type(changed_list).__name__}")
            return changed, errors

        for item in changed_list:
            if isinstance(item, str):
                # Simple format: just a path string
                changed.append(ChangedFile(
                    path=normalize_path(item),
                    old_path=None,
                    status=GIT_STATUS_MODIFIED,
                ))
            elif isinstance(item, dict):
                path = item.get("path")
                if not isinstance(path, str):
                    errors.append(f"Fixture changed items must have 'path' string, got {type(path).__name__}")
                    continue
                changed.append(ChangedFile(
                    path=normalize_path(path),
                    old_path=normalize_path(str(item.get("old_path"))) if item.get("old_path") else None,
                    status=item.get("status", GIT_STATUS_MODIFIED),
                ))
            else:
                errors.append(f"Fixture changed items must be strings or objects, got {type(item).__name__}")

    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in fixture: {e}")
    except Exception as e:
        errors.append(f"Error reading fixture: {e}")

    return changed, errors


def get_changed_files(
    repo_root: Path,
    mode: str = "local",
    base_ref: str | None = None,
    head_ref: str | None = None,
    fixture_path: Path | None = None,
) -> tuple[list[ChangedFile], list[str]]:
    """Get changed files based on mode.

    Args:
        repo_root: Repository root path
        mode: "local", "ci", or "fixture"
        base_ref: Base git ref (for ci mode)
        head_ref: Head git ref (for ci mode)
        fixture_path: Path to fixture file (for fixture mode)

    Returns:
        (changed_files, errors)
    """
    if mode == "local":
        return get_changed_files_local(repo_root)
    elif mode == "ci":
        return get_changed_files_ci(repo_root, base_ref, head_ref)
    elif mode == "fixture":
        if not fixture_path:
            return [], ["Fixture mode requires --fixture-path"]
        return get_changed_files_from_fixture(fixture_path)
    else:
        return [], [f"Unknown mode: {mode}"]


def get_all_paths_from_changed(
    changed: list[ChangedFile],
) -> set[str]:
    """Get all paths (including old paths for renames) from changed files.

    For renames, includes both old and new paths so we can track
    allowlisted files that are renamed.
    """
    paths: set[str] = set()
    for entry in changed:
        paths.add(entry.path)
        if entry.old_path:
            paths.add(entry.old_path)
    return paths


def get_baseline_from_git(
    repo_root: Path,
    ref: str = "HEAD",
) -> tuple[set[str], list[str]]:
    """Get baseline CSV entries from a git ref.

    Returns:
        (baseline_paths, errors)
    """
    errors: list[str] = []
    paths: set[str] = set()

    baseline_path = "docs/tooling/llm_large_file_allowlist_baseline.csv"

    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{baseline_path}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            import csv
            import io
            reader = csv.DictReader(io.StringIO(result.stdout))
            for row in reader:
                path = row.get("path", "").strip()
                if path:
                    paths.add(normalize_path(path))
        elif "not in" in result.stderr or "does not exist" in result.stderr or "not found" in result.stderr:
            # Baseline doesn't exist in ref - this is OK (new file)
            pass
        else:
            errors.append(f"git show failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        errors.append("git show timed out")
    except FileNotFoundError:
        errors.append("git not found")
    except Exception as e:
        errors.append(f"git show error: {e}")

    return paths, errors

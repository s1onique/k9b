#!/usr/bin/env python3
"""Check files for LLM-friendly size limits.

This script enforces file size limits to keep code reviewable for humans and
LLM agents. Large monolithic files are design debt.

Usage:
    python scripts/check_llm_friendly_files.py              # full repo check
    python scripts/check_llm_friendly_files.py --changed-only  # git-changed files only
    python scripts/check_llm_friendly_files.py --warn-lines 300 --max-lines 500

Thresholds:
    - Warn: > 300 lines (configurable)
    - Fail: > 500 lines (configurable)

Exclude patterns (always ignored):
    - .git/, node_modules/, .venv/, coverage_html/, runs/
    - build/, dist/, __pycache__/, .pytest_cache/
    - Generated data: *.json (large), *.log

Allowlist categories:
    - [EXTRACTION] - temporary, pending staged extraction
    - [CONTRACT]   - typeddict/payload contracts, need review
    - [TEST]       - test fixtures, need split by behavior
    - [SCRIPT]     - standalone utility scripts
    - [DOC]        - documentation files (not code)
    - [GENERATED]  - generated or data files
    - [CONFIG]     - configuration/ledger files
    - [FRONTEND]   - frontend React components
    - [FRONTEND TEST] - frontend test files
    - [STYLES]     - CSS style files
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Import allowlist from separate module
from llm_friendly_allowlist import ALLOWLIST

# Default thresholds
DEFAULT_WARN_LINES = 300
DEFAULT_MAX_LINES = 500

# Directories to always exclude (generated/data only)
EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "coverage_html",
    "runs",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
}

# File patterns to always exclude (generated/data)
EXCLUDED_PATTERNS = {
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "requirements.txt",
    ".DS_Store",
}

# Allowed file extensions (empty means all)
ALLOWED_EXTENSIONS: set[str] = set()


# ============================================================================
# Helpers
# ============================================================================


def get_git_root() -> Path:
    """Return the git repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def get_git_tracked_files() -> list[Path]:
    """Return list of git-tracked files."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
        cwd=get_git_root(),
    )
    files = [Path(get_git_root() / f) for f in result.stdout.split("\0") if f]
    return files


def get_changed_files() -> list[Path]:
    """Return list of files changed in working tree (staged + unstaged + untracked)."""
    root = get_git_root()

    # Staged files
    result = subprocess.run(
        ["git", "diff", "--name-only", "--cached"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    staged = set(f for f in result.stdout.strip().split("\n") if f)

    # Unstaged modifications
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    unstaged = set(f for f in result.stdout.strip().split("\n") if f)

    # Untracked files
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    untracked = set(f for f in result.stdout.strip().split("\n") if f)

    combined = staged | unstaged | untracked
    return [Path(root / f) for f in combined if f]


def is_excluded(path: Path, root: Path) -> bool:
    """Check if path should be excluded based on directory/pattern rules."""
    rel = path.relative_to(root)

    # Check path components
    for part in rel.parts:
        if part in EXCLUDED_DIRS:
            return True

    # Check filename patterns
    if rel.name in EXCLUDED_PATTERNS:
        return True

    # Check extensions
    if ALLOWED_EXTENSIONS and path.suffix not in ALLOWED_EXTENSIONS:
        return True

    return False


def is_allowlisted(path: Path, root: Path, allowlist: list[tuple[str, str]]) -> tuple[bool, str | None]:
    """Check if path is in allowlist. Returns (is_allowed, reason).
    
    Supports both exact file matching and directory prefix matching.
    If the allowlist entry ends with '/', it's treated as a directory prefix
    and any file under that directory will match.
    """
    for allowed_path, reason in allowlist:
        # Check for trailing slash to enable directory prefix matching
        # Note: Path() normalizes paths and removes trailing slashes, so we check the original string
        is_directory_pattern = allowed_path.endswith("/") or allowed_path.endswith("\\")
        
        allowed = Path(allowed_path)
        
        # Normalize to absolute path for comparison
        if allowed.resolve() == path.resolve():
            return True, reason

        # Check relative to root
        try:
            rel_path = str(path.relative_to(root))
            rel_allowed = str(allowed.relative_to(root))
            
            # Exact match
            if allowed == path or Path(rel_allowed) == path or Path(rel_allowed) == Path(rel_path):
                return True, reason
            
            # Directory prefix match (if original path_str had trailing slash)
            if is_directory_pattern:
                # Check if the relative path starts with the allowlist directory path
                # Ensure we match the full directory name (with trailing separator check)
                if rel_path.startswith(rel_allowed + "/") or rel_path.startswith(rel_allowed + "\\"):
                    return True, reason
                # Also check absolute path prefix
                allowed_abs = allowed.resolve()
                if str(path).startswith(str(allowed_abs) + "/"):
                    return True, reason
        except ValueError:
            pass

    return False, None


def count_physical_lines(path: Path) -> int:
    """Count physical lines in a file. Returns 0 for binary files."""
    try:
        with open(path, "rb") as f:
            # Read first 8KB to check for binary content
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return 0  # Binary file

        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def validate_allowlist(root: Path, allowlist: list[tuple[str, str]]) -> list[str]:
    """Validate allowlist entries. Returns list of error messages."""
    errors = []
    for path_str, reason in allowlist:
        # Check reason is sufficient
        if not reason or len(reason.strip()) < 10:
            errors.append(f"Allowlist entry '{path_str}' has insufficient reason")

        # Check file exists (file or directory)
        file_path = Path(path_str)
        if not file_path.is_absolute():
            file_path = root / path_str

        # Allow directories in allowlist (for prefix matching)
        if file_path.exists() and file_path.is_dir():
            continue  # Valid directory entry
        
        if not file_path.exists():
            errors.append(f"Allowlist entry '{path_str}' - file does not exist (stale)")
            continue

        # Check if file is excluded by global exclusion rules
        if is_excluded(file_path, root):
            errors.append(f"Allowlist entry '{path_str}' - file is globally excluded (redundant)")

    return errors


def check_file(
    path: Path,
    root: Path,
    warn_lines: int,
    max_lines: int,
    allowlist: list[tuple[str, str]],
) -> tuple[bool, str]:
    """Check a single file. Returns (passed, message)."""
    # Check allowlist first
    is_allowed, reason = is_allowlisted(path, root, allowlist)
    if is_allowed:
        return True, f"{path} is allowlisted: {reason}"

    # Check for binary
    line_count = count_physical_lines(path)
    if line_count == 0 and path.suffix not in {".py", ".ts", ".tsx", ".sh", ".md", ".yml", ".yaml"}:
        return True, f"{path} appears to be binary, skipped"

    # If line_count is 0 but extension suggests text, count non-empty as fallback
    if line_count == 0:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                line_count = sum(1 for _ in f)
        except OSError:
            return True, f"{path} could not be read, skipped"

    if line_count > max_lines:
        return False, (
            f"{path}: {line_count} lines (exceeds {max_lines})\n"
            f"  Action: Split this file by responsibility. Consider:\n"
            f"    - Extract related functions/classes into focused modules\n"
            f"    - Move type definitions to contract module\n"
            f"    - Separate UI rendering from business logic"
        )

    if line_count > warn_lines:
        return False, (
            f"{path}: {line_count} lines (warn > {warn_lines})\n"
            f"  Action: Consider splitting if related code can be extracted"
        )

    return True, f"{path}: {line_count} lines (OK)"


# ============================================================================
# Main
# ============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check files for LLM-friendly size limits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Check only git-changed files (staged + unstaged + untracked)",
    )
    parser.add_argument(
        "--warn-lines",
        type=int,
        default=DEFAULT_WARN_LINES,
        help=f"Warning threshold for file size (default: {DEFAULT_WARN_LINES})",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Maximum allowed lines (default: {DEFAULT_MAX_LINES})",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress OK messages and warnings, but always show failures",
    )

    args = parser.parse_args()

    root = get_git_root()

    # Validate allowlist
    errors = validate_allowlist(root, ALLOWLIST)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    # Get files to check
    if args.changed_only:
        files = get_changed_files()
    else:
        files = get_git_tracked_files()

    # Filter to checkable files
    checkable = [f for f in files if not is_excluded(f, root) and f.is_file()]

    failures = []
    warnings = []

    for path in sorted(checkable):
        passed, msg = check_file(path, root, args.warn_lines, args.max_lines, ALLOWLIST)
        if not passed:
            if "exceeds" in msg:
                failures.append(msg)
                print(msg)  # Always print hard failures, even in quiet mode
            else:
                warnings.append(msg)
                if not args.quiet:
                    print(msg)
        elif not args.quiet:
            print(msg)

    # Summary
    print()
    print(f"Checked {len(checkable)} files")
    print(f"  Failures: {len(failures)}")
    print(f"  Warnings: {len(warnings)}")

    if failures:
        print("\nFAILURE: Files exceed maximum threshold")
        return 1

    if warnings:
        print("\nWARNING: Files exceed warning threshold (non-blocking)")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

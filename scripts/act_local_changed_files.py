#!/usr/bin/env python3
"""ACT-Local changed file detection.

Provides functions to detect and filter changed files from git.

CORRECTION16: the script supports an explicit F16..S16
range via ``--base`` / ``--subject`` arguments (or the
``K9B_ACT_LOCAL_BASE`` / ``K9B_ACT_LOCAL_SUBJECT``
environment variables).  When the range is supplied the
script uses ``git diff --name-only -z --diff-filter=ACMRT
<base>..<subject>`` as the authoritative source; the
working-tree / staged / untracked-file discovery is the
fallback when the range is absent.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def get_deleted_files() -> set[str]:
    """Get set of deleted file paths (both staged and unstaged deletions).
    
    Returns set of relative paths from repo root.
    """
    deleted: set[str] = set()
    
    # Get staged deletions
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=D"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                deleted.add(line.strip())
    
    # Get unstaged deletions
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=D"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                deleted.add(line.strip())
    
    return deleted


def get_changed_files(
    *,
    base: str | None = None,
    subject: str | None = None,
) -> list[str]:
    """Get list of changed files from git (staged + unstaged + untracked).
    
    Returns list of relative paths from repo root.
    Includes:
    - unstaged modifications
    - staged changes (additions and modifications, NOT deletions)
    - untracked files
    
    CORRECTION16: when ``base`` and ``subject`` are supplied
    the function uses ``git diff --name-only -z
    --diff-filter=ACMRT <base>..<subject>`` as the
    authoritative source.  The returned paths are filtered
    to those that exist on disk (deletions are excluded).
    
    Note: Deleted files are NOT included because they cannot be passed to
    file-based tools (ruff, mypy, etc.) that require existing files.
    Deleted files are still tracked separately via get_deleted_files() for
    reporting purposes.
    """
    changed: set[str] = set()
    
    if base and subject:
        # CORRECTION16: explicit range mode.  Use the
        # exact same arguments as the orchestrator's
        # diff query so the script's output is
        # byte-for-byte comparable with the bundle.
        result = subprocess.run(
            [
                "git", "diff", "--name-only", "-z",
                "--diff-filter=ACMRT",
                f"{base}..{subject}",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
        )
        if result.returncode == 0:
            # NUL-delimited output - split on NUL.
            for entry in result.stdout.split(b"\0"):
                if entry:
                    try:
                        text = entry.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    if text.strip():
                        changed.add(text.strip())
        # Untracked files are NOT in the diff range; the
        # orchestrator's diff excludes them.  The
        # C15 fallback kept them; preserve the legacy
        # behaviour for callers that still need it.
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    changed.add(line.strip())
    else:
        # Get unstaged changes (modifications only, excluding deletions)
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    changed.add(line.strip())
        
        # Get staged changes (additions and modifications, excluding deletions)
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    changed.add(line.strip())
        
        # Get untracked files (new files not yet staged)
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    changed.add(line.strip())
    
    # Filter to only paths that exist on disk.
    # This excludes deleted files since they no longer exist and cannot be
    # passed to file-based tools (ruff, mypy, etc.).
    existing_changed: list[str] = []
    for path in sorted(changed):
        full_path = REPO_ROOT / path
        if full_path.exists():
            existing_changed.append(path)

    return existing_changed


def filter_python_files(files: list[str]) -> list[str]:
    """Filter to only Python files."""
    return [f for f in files if f.endswith('.py')]


def filter_shell_files(files: list[str]) -> list[str]:
    """Filter to only shell files."""
    return [f for f in files if f.endswith('.sh')]


def filter_docs_prompts_rules(files: list[str]) -> list[str]:
    """Filter to docs, prompts, and rules files."""
    patterns = ['docs/', '.kilocode/rules/', 'AGENTS.md', '.clinerules/']
    return [f for f in files if any(f.startswith(p) or f == p for p in patterns)]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=str, default=None)
    parser.add_argument("--subject", type=str, default=None)
    parser.add_argument("--print", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    base = args.base or os.environ.get("K9B_ACT_LOCAL_BASE")
    subject = args.subject or os.environ.get("K9B_ACT_LOCAL_SUBJECT")
    files = get_changed_files(base=base, subject=subject)
    if args.print:
        for entry in files:
            print(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())

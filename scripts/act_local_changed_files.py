#!/usr/bin/env python3
"""ACT-Local changed file detection.

Provides functions to detect and filter changed files from git.
"""

from __future__ import annotations

import subprocess
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


def get_changed_files() -> list[str]:
    """Get list of changed files from git (staged + unstaged + untracked).
    
    Returns list of relative paths from repo root.
    Includes:
    - unstaged modifications
    - staged changes (additions and modifications, NOT deletions)
    - untracked files
    
    Note: Deleted files are NOT included because they cannot be passed to
    file-based tools (ruff, mypy, etc.) that require existing files.
    Deleted files are still tracked separately via get_deleted_files() for
    reporting purposes.
    """
    changed: set[str] = set()
    
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

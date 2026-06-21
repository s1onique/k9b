#!/usr/bin/env python3
"""ACT-Local changed file detection.

Provides functions to detect and filter changed files from git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def get_changed_files() -> list[str]:
    """Get list of changed files from git (staged + unstaged + untracked).
    
    Returns list of relative paths from repo root.
    Includes:
    - unstaged modifications
    - staged changes
    - untracked files
    """
    changed: set[str] = set()
    
    # Get unstaged changes
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
    
    # Get staged changes
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
    
    return sorted(changed)


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

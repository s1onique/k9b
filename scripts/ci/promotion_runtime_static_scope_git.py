"""Git primitives for the dual-range static-scope model.

Owner: Git subprocess operations, commit resolution, changed-path acquisition.
All scope computation and policy classification live elsewhere.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when a Git subprocess fails."""


def _run_git(
    *args: str,
    repo_root: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    """Run a git subprocess and return the CompletedProcess."""
    cmd = ["git", *args]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git {' '.join(args)!r} failed: {stderr}")
    return proc


# ---------------------------------------------------------------------------
# Commit resolution (P0-4).
# ---------------------------------------------------------------------------


def resolve_revision(repo_root: Path, revision: str) -> str:
    """Resolve a revision to its full 40-char SHA. Fails on unresolved refs."""
    proc = _run_git("rev-parse", "--verify", f"{revision}^{{commit}}", repo_root=repo_root)
    if proc.returncode != 0:
        raise GitError(f"failed to resolve revision {revision!r}")
    return proc.stdout.decode("utf-8").strip()


def get_subject_tree(repo_root: Path, subject_sha: str) -> str:
    """Return the full SHA of SUBJECT's commit tree using git rev-parse."""
    proc = _run_git("rev-parse", "--verify", f"{subject_sha}^{{tree}}", repo_root=repo_root)
    if proc.returncode != 0:
        raise GitError(f"failed to resolve {subject_sha}^{{tree}}")
    return proc.stdout.decode("utf-8").strip()


def get_head_sha(repo_root: Path) -> str:
    """Return the full SHA of the current checked-out HEAD."""
    proc = _run_git("rev-parse", "--verify", "HEAD", repo_root=repo_root)
    if proc.returncode != 0:
        raise GitError(f"git rev-parse HEAD failed")
    return proc.stdout.decode("utf-8").strip()


def is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    """Return True if ancestor is a commit ancestor of descendant."""
    proc = _run_git(
        "merge-base", "--is-ancestor", ancestor, descendant,
        repo_root=repo_root,
        check=False,
    )
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Changed-path acquisition (P0-2, P0-5, P0-7).
# ---------------------------------------------------------------------------


def changed_python(
    repo_root: Path,
    base_sha: str,
    subject_sha: str,
) -> bytes:
    """Return raw NUL-delimited changed-.py paths from ``git diff -z --diff-filter``.

    Scope authority is always a commit-range diff.
    The only permitted command forms:
      git diff --name-only -z --diff-filter=ACMRT BASE..SUBJECT -- '*.py'

    Forbidden:
      - git ls-tree (tree enumeration is not scope authority)
      - git index/working-tree enumeration (not commit objects)
      - tr '\\0' '\\n' or any newline-based splitting
      - dirty-worktree diff fallback
      - implicit HEAD~1 range

    Returns raw bytes split on NUL; caller must decode each record.
    """
    proc = _run_git(
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACMRT",
        f"{base_sha}..{subject_sha}",
        "--",
        "*.py",
        repo_root=repo_root,
    )
    # git diff returns 0 for both changed and unchanged ranges
    return proc.stdout


def changed_all(
    repo_root: Path,
    base_sha: str,
    subject_sha: str,
) -> bytes:
    """Return raw NUL-delimited all-changed paths from ``git diff -z --diff-filter``.

    Used for git-diff-check in workflows. Same scope authority as changed_python.
    """
    proc = _run_git(
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACMRT",
        f"{base_sha}..{subject_sha}",
        repo_root=repo_root,
    )
    return proc.stdout


# ---------------------------------------------------------------------------
# Git command log (P0-17).
# ---------------------------------------------------------------------------

def git_version(repo_root: Path) -> str:
    """Return the git version string."""
    proc = _run_git("--version", repo_root=repo_root)
    return proc.stdout.decode("utf-8").strip()

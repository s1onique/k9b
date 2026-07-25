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

CORRECTION17: in explicit range mode the script is
**strictly range-bound**.  When ``--base`` AND ``--subject``
are supplied (or both environment variables are set):

* the script does NOT call ``git diff``, ``git status`` or
  ``git ls-files``; the orchestrator-supplied manifest
  (passed via ``--manifest <path>`` or
  ``K9B_ACT_LOCAL_MANIFEST``) is the SOLE source;
* working-tree discovery, staged discovery, untracked
  discovery and internal Git rediscovery are all disabled;
* if no manifest is supplied the script raises a fatal
  error rather than silently falling back to internal Git
  discovery.

This guarantees the explicit range mode never produces
``child_git_commands`` and the transcript records zero
hidden shell git invocations from this script.
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


def _read_manifest_paths(manifest_path: Path) -> list[str]:
    """Read the orchestrator-supplied NUL-delimited path manifest.

    CORRECTION17: the manifest is the SOLE authoritative
    source of changed paths in explicit range mode.  The
    file is NUL-delimited with a single trailing NUL.  Any
    decoding error raises a fatal ``RuntimeError`` rather
    than silently dropping the path.
    """
    if not manifest_path.exists():
        raise RuntimeError(
            f"manifest not found: {manifest_path} (CORRECTION17 explicit range mode)"
        )
    raw = manifest_path.read_bytes()
    paths: list[str] = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            text = entry.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"manifest entry not utf-8 decodable: {entry!r}: {exc}"
            ) from exc
        text = text.strip()
        if text:
            paths.append(text)
    return paths


def get_changed_files(
    *,
    base: str | None = None,
    subject: str | None = None,
    manifest_path: Path | str | None = None,
) -> list[str]:
    """Get list of changed files from the orchestrator manifest.

    Returns list of relative paths from repo root.

    CORRECTION16: when ``base`` and ``subject`` are supplied
    the function uses ``git diff --name-only -z
    --diff-filter=ACMRT <base>..<subject>`` as the
    authoritative source.

    CORRECTION17: in explicit range mode (``base`` AND
    ``subject`` are supplied) the script MUST consume the
    orchestrator-supplied manifest via ``manifest_path``
    and MUST NOT perform internal Git discovery
    (``working_tree_discovery``, ``staged_discovery``,
    ``untracked_discovery`` and
    ``internal_git_rediscovery`` are all ``False``).
    Returns the path tuple filtered to those that exist
    on disk (deletions are excluded).

    Note: Deleted files are NOT included because they cannot be passed to
    file-based tools (ruff, mypy, etc.) that require existing files.
    Deleted files are still tracked separately via get_deleted_files() for
    reporting purposes.
    """
    if base and subject:
        # CORRECTION17: explicit range mode is strictly
        # manifest-bound.  Resolve the manifest path from
        # the argument or environment variable.
        if manifest_path is None:
            manifest_env = os.environ.get("K9B_ACT_LOCAL_MANIFEST")
            if manifest_env:
                manifest_path = Path(manifest_env)
        if manifest_path is None:
            raise RuntimeError(
                "CORRECTION17: explicit range mode requires --manifest or "
                "K9B_ACT_LOCAL_MANIFEST; internal Git discovery is disabled."
            )
        manifest_path = Path(manifest_path)
        changed = set(_read_manifest_paths(manifest_path))
    else:
        changed = _discover_changed_files_legacy()

    # Filter to only paths that exist on disk.
    # This excludes deleted files since they no longer exist and cannot be
    # passed to file-based tools (ruff, mypy, etc.).
    existing_changed: list[str] = []
    for path in sorted(changed):
        full_path = REPO_ROOT / path
        if full_path.exists():
            existing_changed.append(path)

    return existing_changed


def _discover_changed_files_legacy() -> set[str]:
    """Legacy C15/C16 fallback: discover changed files via working tree.

    CORRECTION17: this function is ONLY invoked when
    ``--base``/``--subject`` are NOT supplied.  In explicit
    range mode the orchestrator-supplied manifest is used
    instead.  Any invocation in production range mode
    violates the C17 contract.
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

    return changed


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
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="CORRECTION17: path to NUL-delimited changed-paths manifest. "
             "Required when --base and --subject are supplied.",
    )
    parser.add_argument("--print", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    base = args.base or os.environ.get("K9B_ACT_LOCAL_BASE")
    subject = args.subject or os.environ.get("K9B_ACT_LOCAL_SUBJECT")
    manifest = args.manifest or os.environ.get("K9B_ACT_LOCAL_MANIFEST")
    files = get_changed_files(
        base=base,
        subject=subject,
        manifest_path=manifest,
    )
    if args.print:
        for entry in files:
            print(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
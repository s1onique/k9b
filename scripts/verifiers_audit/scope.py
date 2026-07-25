"""Authoritative scope rules for the audit.

The audit scope is determined mechanically from
``git ls-files 'scripts/verifiers/*.py' 'scripts/verifiers/**/*.py'``
plus the explicit exclusion rules below. Every excluded path
must match at least one rule; the audit ``--check`` mode refuses
to admit any path that does not.

Public surface:

* :data:`EXCLUDED_DIRS` — directory globs that are entirely
  excluded from migration consideration
* :data:`EXCLUDED_BASENAMES` — exact basenames that are excluded
* :data:`EXCLUDED_GLOBS` — wildcard globs (matched with
  :func:`fnmatch.fnmatchcase`)
* :func:`is_excluded` — return True when a tracked path matches any
  rule
* :func:`classify_path` — return the matching rule id (or ``None``)
* :func:`changed_paths` — return the changed paths in a
  ``base..subject`` revision range (CORRECTION11)
* :func:`changed_python_paths` — return the subset of ``changed_paths``
  that end in ``.py`` (CORRECTION11)
* :func:`build_ruff_argv` — return the ``ruff check`` argv that
  exactly matches ``changed_python_paths`` (CORRECTION11)
* :func:`argv_after_command_prefix` — return the path-portion of a
  ``ruff check`` argv, stripping the ``(ruff, check)`` prefix
  (CORRECTION11)
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import fnmatch
import subprocess
from collections.abc import Iterable, Sequence

from scripts.verifiers_audit.discovery import REPO_ROOT

# ---------------------------------------------------------------------------
# Exclusion rules (frozen, deterministic)
# ---------------------------------------------------------------------------

EXCLUDED_DIRS: tuple[str, ...] = (
    # The verifier_core package itself is the comparison baseline.
    # Migration candidates that *import* from it are allowed; the
    # package itself is not a migration target.
    "scripts/verifiers/verifier_core",
)

EXCLUDED_BASENAMES: tuple[str, ...] = (
    # Empty package marker.
    "scripts/verifiers/__init__.py",
)

EXCLUDED_GLOBS: tuple[str, ...] = (
    # Per ACT scope: ``automatic_diagnosis_*.py`` files are excluded
    # as migration candidates.
    "scripts/verifiers/automatic_diagnosis_*.py",
)


def _matches_dir_rule(path: str) -> str | None:
    """Return rule id when ``path`` lives under any excluded dir."""
    for d in EXCLUDED_DIRS:
        if path == d or path.startswith(d + "/"):
            return f"EX-DIR:{d}"
    return None


def _matches_basename_rule(path: str) -> str | None:
    """Return rule id when ``path`` matches an excluded basename."""
    for b in EXCLUDED_BASENAMES:
        if path == b:
            return f"EX-BASE:{b}"
    return None


def _matches_glob_rule(path: str) -> str | None:
    """Return rule id when ``path`` matches an excluded wildcard."""
    for g in EXCLUDED_GLOBS:
        if fnmatch.fnmatchcase(path, g):
            return f"EX-GLOB:{g}"
    return None


def classify_path(path: str) -> str | None:
    """Return the rule id that excludes ``path``, or ``None``."""
    for matcher in (_matches_dir_rule, _matches_basename_rule, _matches_glob_rule):
        rule_id = matcher(path)
        if rule_id is not None:
            return rule_id
    return None


def is_excluded(path: str) -> bool:
    """Return True when ``path`` matches at least one exclusion rule."""
    return classify_path(path) is not None


def split_tracked(tracked: Iterable[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Split tracked paths into (included, excluded_with_rule).

    ``excluded_with_rule`` is a list of ``(path, rule_id)`` tuples
    sorted by path. ``included`` is sorted by path.
    """
    included: list[str] = []
    excluded: list[tuple[str, str]] = []
    for p in tracked:
        rule = classify_path(p)
        if rule is None:
            included.append(p)
        else:
            excluded.append((p, rule))
    included.sort()
    excluded.sort()
    return included, excluded


# ---------------------------------------------------------------------------
# CORRECTION11: change-range derived paths for the closure manifest
# ---------------------------------------------------------------------------


def _run_git_diff_names(base: str, subject: str) -> tuple[str, ...]:
    """Return ``git diff --name-only --diff-filter=ACMRT base..subject``.

    Both ``base`` and ``subject`` are interpreted as commit-ish
    references.  The output is the raw newline-split list of paths
    emitted by git; trailing whitespace is stripped and empty
    lines are removed.  The order matches git's output exactly
    (path-status order) so the closure manifest can be reproduced
    by a third party.
    """
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT",
         f"{base}..{subject}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return tuple(
        line.strip() for line in proc.stdout.splitlines() if line.strip()
    )


def changed_paths(base: str, subject: str) -> tuple[str, ...]:
    """Return the paths changed between ``base`` and ``subject``.

    The function is the SOLE production source for the closure
    range's changed-path set.  ``base`` and ``subject`` are
    commit-ish references; the returned tuple mirrors the exact
    git output (no sorting, no dedup).  Tests must call this
    function instead of hard-coding paths.
    """
    return _run_git_diff_names(base, subject)


def changed_python_paths(base: str, subject: str) -> tuple[str, ...]:
    """Return the subset of :func:`changed_paths` that ends in ``.py``.

    Deleted Python files (``D`` status) are excluded from the
    Ruff input by virtue of the ``--diff-filter=ACMRT`` filter
    in :func:`_run_git_diff_names` (only Added, Copied, Modified,
    Renamed, Type-changed files are kept).  The returned tuple
    preserves the order of :func:`changed_paths`.
    """
    return tuple(p for p in changed_paths(base, subject) if p.endswith(".py"))


def build_ruff_argv(paths: Sequence[str]) -> tuple[str, ...]:
    """Return the ``ruff check`` argv that visits exactly ``paths``.

    The function is the SOLE production source for the closure
    range's Ruff input.  The returned tuple is deterministic
    (preserves the order of ``paths``) and is reproducible by
    a third party from the same ``changed_python_paths`` set.
    """
    return ("ruff", "check", *paths)


def argv_after_command_prefix(argv: Sequence[str]) -> tuple[str, ...]:
    """Return the path-portion of a ``ruff check`` argv.

    The function strips the ``(ruff, check)`` prefix from ``argv``
    so a test can compare the path list against
    :func:`changed_python_paths`.  The empty argv is rejected
    so the test cannot accidentally bypass the comparison.
    """
    if not argv:
        raise ValueError("argv is empty; cannot strip prefix")
    if argv[0] != "ruff":
        raise ValueError(
            f"argv does not start with 'ruff': argv[0]={argv[0]!r}"
        )
    if len(argv) < 2 or argv[1] != "check":
        raise ValueError(
            f"argv does not have 'check' as second arg: argv[1]={argv[1]!r}"
        )
    return tuple(argv[2:])


# Detection invariant: existence of the canonical baseline file is
# not required for any of the public functions above; the helpers
# operate entirely on the repository's git history and a Path
# argument.  Tests that need a fixture use
# :func:`changed_paths` / :func:`changed_python_paths` against
# two real commits (typically F vs S) that they have created in
# the test repository.

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
  ``base..subject`` revision range (CORRECTION12 NUL-parser;
  fail-closed on any Git error; ``repo_root`` is injectable)
* :func:`changed_python_paths` — return the subset of ``changed_paths``
  that end in ``.py`` (CORRECTION12)
* :func:`build_ruff_argv` — return the ``ruff check`` argv that
  exactly matches ``changed_python_paths`` (CORRECTION12)
* :func:`argv_after_command_prefix` — return the path-portion of a
  ``ruff check`` argv, stripping the ``(ruff, check)`` prefix
  (CORRECTION12)
* :class:`RangeResolutionError` — typed failure for invalid
  ``git diff`` ranges (CORRECTION12)
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import fnmatch
import os
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

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
# CORRECTION12: fail-closed range API for the closure manifest
# ---------------------------------------------------------------------------


class RangeResolutionError(RuntimeError):
    """CORRECTION12: typed failure for invalid ``git diff`` ranges.

    Raised by :func:`_run_git_diff_names` when ``git diff`` exits
    with a non-zero status.  The exception captures the
    ``base`` / ``subject`` revision pair, the ``returncode``,
    and the (decoded) stderr text so the caller can fail closed
    without ever confusing a Git failure with a valid empty
    range.

    A valid equal-commit range MAY legitimately return an empty
    tuple.  An invalid range MUST raise this exception.
    """

    def __init__(
        self,
        *,
        base: str,
        subject: str,
        returncode: int,
        stderr: str,
    ) -> None:
        super().__init__(
            f"git diff failed for range {base!r}..{subject!r}: "
            f"returncode={returncode}: {stderr}"
        )
        self.base = base
        self.subject = subject
        self.returncode = returncode
        self.stderr = stderr


def _run_git_diff_names(
    base: str,
    subject: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[str, ...]:
    """Return ``git diff --name-only -z --diff-filter=ACMRT base subject``.

    CORRECTION12: NUL-delimited, byte-safe, pathname-safe,
    injectable ``repo_root``.  The function NEVER:

    * uses ``text=True`` (output is binary bytes),
    * uses ``splitlines()`` (pathnames may contain any bytes),
    * calls ``strip()`` on pathnames (whitespace is preserved),
    * returns an empty tuple after a Git failure (it raises),
    * suppresses stderr (it is captured and forwarded),
    * silently substitutes ``HEAD``, the index, or the working
      tree (the supplied revisions are used verbatim).

    On non-zero exit the function raises :class:`RangeResolutionError`.
    On zero exit the trailing NUL is preserved by ``split`` and
    dropped by the ``if raw`` filter; an empty trailing entry is
    NEVER emitted as a path.  A valid equal-commit range MAY
    return ``()``.
    """
    proc = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACMRT",
            base,
            subject,
        ],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )

    if proc.returncode != 0:
        raise RangeResolutionError(
            base=base,
            subject=subject,
            returncode=proc.returncode,
            stderr=os.fsdecode(proc.stderr) if proc.stderr else "",
        )

    return tuple(
        os.fsdecode(raw)
        for raw in proc.stdout.split(b"\0")
        if raw
    )


def changed_paths(
    base: str,
    subject: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[str, ...]:
    """Return the paths changed between ``base`` and ``subject``.

    CORRECTION12: the function is the SOLE production source
    for the closure range's changed-path set.  ``base`` and
    ``subject`` are commit-ish references; ``repo_root`` is
    injectable so tests can use a hermetic temporary Git
    repository.  The returned tuple mirrors the exact git
    output (no sorting, no dedup, no whitespace stripping);
    Git failure is raised as :class:`RangeResolutionError`.
    """
    return _run_git_diff_names(base, subject, repo_root=repo_root)


def changed_python_paths(
    base: str,
    subject: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[str, ...]:
    """Return the subset of :func:`changed_paths` that ends in ``.py``.

    Deleted Python files (``D`` status) are excluded from the
    Ruff input by virtue of the ``--diff-filter=ACMRT`` filter
    in :func:`_run_git_diff_names` (only Added, Copied, Modified,
    Renamed, Type-changed files are kept).  The returned tuple
    preserves the order of :func:`changed_paths`.
    """
    return tuple(
        p for p in changed_paths(base, subject, repo_root=repo_root)
        if p.endswith(".py")
    )


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

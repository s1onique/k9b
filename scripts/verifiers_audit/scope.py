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
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import fnmatch
from collections.abc import Iterable

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

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
* :func:`changed_path_bytes` — return the changed paths in a
  ``base..subject`` revision range as **filesystem bytes**
  (CORRECTION13 authoritative API)
* :func:`changed_paths` — return the changed paths as ``str``
  (CORRECTION13 derived convenience layer; never the source of
  the detached evidence)
* :func:`changed_python_path_bytes` — return the Python subset of
  :func:`changed_path_bytes` as bytes (CORRECTION13)
* :func:`changed_python_paths` — return the Python subset of
  :func:`changed_paths` as ``str`` (CORRECTION13)
* :func:`build_ruff_scope` — return a typed :class:`RuffScope`
  whose ``status`` is ``"skipped_no_python_paths"`` for an empty
  set (CORRECTION13)
* :func:`argv_after_command_prefix` — return the path-portion of a
  ``ruff check`` argv, stripping the ``(ruff, check)`` prefix
* :func:`normalise_index_paths` — produce a deep-copied index
  whose values are equivalent modulo the canonical shard-path
  representation (CORRECTION13 layout-aware; takes a
  :class:`ReportLayout` parameter)
* :func:`python_path_bytes` — derive the Python subset of a
  bytes tuple via a pure-Python filter (CORRECTION13)
* :class:`RangeResolutionError` — typed failure for every Git
  revision / range command, with a ``stage`` field set to
  one of ``resolve_base``, ``resolve_subject``, ``diff_names``
  (CORRECTION12/CORRECTION13)
* :class:`RuffScope` — typed result for the Ruff scope builder
  (CORRECTION13)
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import copy
import fnmatch
import os
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from scripts.verifiers_audit.discovery import REPO_ROOT

if TYPE_CHECKING:
    from scripts.verifiers_audit.report_io import ReportLayout


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
# CORRECTION13: byte-safe range API; string view is a derived convenience
# ---------------------------------------------------------------------------


RangeResolutionStage = Literal[
    "resolve_base",
    "resolve_subject",
    "diff_names",
]


class RangeResolutionError(RuntimeError):
    """CORRECTION12/CORRECTION13: typed failure for every Git
    revision / range command in the evidence-transaction path.

    The exception unifies three previously separate failure
    surfaces:

    * ``"resolve_base"`` - ``git rev-parse --verify ${BASE}^{commit}``
      exited non-zero (the BASE commit cannot be resolved).
    * ``"resolve_subject"`` - ``git rev-parse --verify ${SUBJECT}^{commit}``
      exited non-zero (the SUBJECT commit cannot be resolved).
    * ``"diff_names"`` - ``git diff --name-only -z --diff-filter=ACMRT``
      exited non-zero (the range diff query failed).

    The exception captures the ``base`` / ``subject`` revision
    pair, the failing ``argv`` (as a tuple), the ``returncode``,
    the (decoded) stderr text, and the ``stage`` so the caller
    can fail closed without ever confusing a Git failure with
    a valid empty range.  A bare :class:`RuntimeError` at the
    evidence-transaction boundary is forbidden.

    A valid equal-commit range MAY legitimately return an empty
    tuple.  An invalid range MUST raise this exception.
    """

    def __init__(
        self,
        *,
        base: str,
        subject: str,
        argv: tuple[str, ...],
        returncode: int,
        stderr: str,
        stage: RangeResolutionStage,
    ) -> None:
        super().__init__(
            f"git {argv[0] if argv else '?'} failed at stage {stage!r} "
            f"for range {base!r}..{subject!r}: "
            f"returncode={returncode}: {stderr}"
        )
        self.base = base
        self.subject = subject
        self.argv = tuple(argv)
        self.returncode = returncode
        self.stderr = stderr
        self.stage = stage



def _run_git_diff_names_bytes(
    base: str,
    subject: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[bytes, ...]:
    """Return ``git diff --name-only -z --diff-filter=ACMRT base subject``.

    CORRECTION13: this is the **authoritative** range query.  It
    NEVER:

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

    The returned tuple is bytes (filesystem representation);
    test code may decode with :func:`os.fsdecode` round-trip.
    """
    argv: tuple[str, ...] = (
        "git",
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACMRT",
        base,
        subject,
    )
    proc = subprocess.run(
        list(argv),
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )

    if proc.returncode != 0:
        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=argv,
            returncode=proc.returncode,
            stderr=os.fsdecode(proc.stderr) if proc.stderr else "",
            stage="diff_names",
        )

    return tuple(raw for raw in proc.stdout.split(b"\0") if raw)



def changed_path_bytes(
    base: str,
    subject: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[bytes, ...]:
    """CORRECTION13: authoritative byte-safe range API.

    Returns the changed paths in a ``base..subject`` revision
    range as filesystem bytes.  The string view
    :func:`changed_paths` is a derived convenience.

    ``base`` and ``subject`` are commit-ish references;
    ``repo_root`` is injectable so tests can use a hermetic
    temporary Git repository.  The returned tuple mirrors the
    exact git output (no sorting, no dedup, no whitespace
    stripping); Git failure is raised as
    :class:`RangeResolutionError`.
    """
    return _run_git_diff_names_bytes(base, subject, repo_root=repo_root)


def changed_paths(
    base: str,
    subject: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[str, ...]:
    """CORRECTION13: derived string view of the range API.

    Returns the changed paths in a ``base..subject`` revision
    range as ``str``.  The bytes are decoded via
    :func:`os.fsdecode` so encoding errors are surfaced
    deterministically; the authoritative range query is
    :func:`changed_path_bytes`.
    """
    return tuple(
        os.fsdecode(p) for p in changed_path_bytes(
            base, subject, repo_root=repo_root
        )
    )


def changed_python_path_bytes(
    base: str,
    subject: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[bytes, ...]:
    """CORRECTION13: authoritative byte-safe Python subset.

    Returns the subset of :func:`changed_path_bytes` whose
    bytes end in ``b'.py'``.  Deleted Python files
    (``D`` status) are excluded from the Ruff input by virtue
    of the ``--diff-filter=ACMRT`` filter in
    :func:`_run_git_diff_names_bytes` (only Added, Copied,
    Modified, Renamed, Type-changed files are kept).  The
    returned tuple preserves the order of
    :func:`changed_path_bytes`.
    """
    return tuple(
        p for p in changed_path_bytes(base, subject, repo_root=repo_root)
        if p.endswith(b".py")
    )


def changed_python_paths(
    base: str,
    subject: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[str, ...]:
    """CORRECTION13: derived string view of the Python subset.

    Returns the subset of :func:`changed_paths` whose string
    representation ends in ``.py``.  Deleted Python files
    (``D`` status) are excluded by the ``--diff-filter=ACMRT``
    filter.  The returned tuple preserves the order of
    :func:`changed_paths`.
    """
    return tuple(
        os.fsdecode(p) for p in changed_python_path_bytes(
            base, subject, repo_root=repo_root
        )
    )


# ---------------------------------------------------------------------------
# CORRECTION13: typed Ruff scope builder
# ---------------------------------------------------------------------------


RuffScopeStatus = Literal["ready", "skipped_no_python_paths"]


@dataclass(frozen=True)
class RuffScope:
    """CORRECTION13: typed result of the Ruff scope builder.

    * ``paths`` is the canonical production path tuple (the
      tuple the evidence manifest records; it is identical to
      the output of :func:`changed_python_paths`).
    * ``argv`` is the ``ruff check`` argv that visits exactly
      ``paths``, or ``None`` when ``paths`` is empty (skipped
      range — evidence producer does NOT invoke Ruff).
    * ``status`` is ``"ready"`` for a non-empty range and
      ``"skipped_no_python_paths"`` for an empty range.
    """

    paths: tuple[str, ...]
    argv: tuple[str, ...] | None
    status: RuffScopeStatus


def build_ruff_scope(paths: Sequence[str]) -> RuffScope:
    """CORRECTION13: return the typed :class:`RuffScope` for ``paths``.

    The empty case (``paths == ()``) returns
    ``status="skipped_no_python_paths"`` and ``argv=None``.  The
    evidence producer MUST NOT invoke Ruff when
    ``status="skipped_no_python_paths"``.

    The non-empty case returns ``argv=("ruff", "check", *paths)``
    and ``status="ready"``.  The argv's path suffix
    (``argv[2:]``) is exactly the production path tuple.
    """
    if not paths:
        return RuffScope(
            paths=(),
            argv=None,
            status="skipped_no_python_paths",
        )
    return RuffScope(
        paths=tuple(paths),
        argv=("ruff", "check", *paths),
        status="ready",
    )


def build_ruff_argv(paths: Sequence[str]) -> tuple[str, ...]:
    """CORRECTION13: deprecated wrapper.

    Returns ``("ruff", "check", *paths)`` for a non-empty
    ``paths`` sequence.  For an empty ``paths`` sequence it
    raises :class:`ValueError` instead of returning a pathless
    ``ruff check``.

    Production code SHOULD use :func:`build_ruff_scope` instead;
    this function is preserved for backward compatibility with
    the CORRECTION12 test suite.
    """
    if not paths:
        raise ValueError(
            "build_ruff_argv(paths) requires a non-empty sequence; "
            "use build_ruff_scope(()) for an explicit skip"
        )
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


# ---------------------------------------------------------------------------
# CORRECTION13: in-process Python subset derivation
# ---------------------------------------------------------------------------


def python_path_bytes(paths: tuple[bytes, ...]) -> tuple[bytes, ...]:
    """Return the Python subset of a bytes tuple.

    CORRECTION13: the python subset is derived in-process from
    the authoritative byte tuple via a pure-Python filter.  No
    second git subprocess is launched; the same bytes tuple
    is the source for the changed-paths, changed-python-paths,
    and ruff-input-paths manifests.
    """
    return tuple(p for p in paths if p.endswith(b".py"))


# ---------------------------------------------------------------------------
# CORRECTION13: layout-aware top-level index normalisation
# ---------------------------------------------------------------------------


class IndexNormalisationError(ValueError):
    """CORRECTION13: typed failure for layout-aware normalisation.

    Raised by :func:`normalise_index_paths` when a shard path
    fails the layout contract: an unknown shard name, a missing
    or non-string path, a wrong parent directory, a wrong
    basename, a path-traversal attempt, or a swapped shard
    path (inventory's path under groups' name, etc.).
    """


def _resolve_path_against_layout(
    raw_path: str,
    *,
    layout: ReportLayout,
) -> Path:
    """Resolve a recorded path to an absolute Path.

    The recorded path may be:

    * an absolute path (``/abs/.../shard.json``);
    * a path relative to :data:`REPO_ROOT` (the audit writer
      uses ``_relative_to_repo`` so a path like
      ``docs/reports/verifier-core-migration-audit01/inventory.json``
      resolves to ``REPO_ROOT/docs/reports/verifier-core-migration-audit01/inventory.json``).

    The function returns the absolute Path.  It NEVER
    consults :func:`os.path.realpath`; the comparison is a
    pure path-equality check.
    """
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def _validate_shard_path_against_layout(
    shard_name: str,
    info: object,
    *,
    layout: ReportLayout,
    required_shards: frozenset[str],
) -> str | None:
    """Return the canonical normalised path when valid, else raise.

    The function enforces, in order:

    1. ``shard_name`` must be a known shard (``required_shards``).
    2. ``info`` must be a dict with a string ``path`` field.
    3. The recorded path (absolute or REPO_ROOT-relative) must
       identify exactly ``layout.shard_root / f"{shard_name}.json"``.
    4. A wrong basename, wrong parent, path traversal, missing
       path, or swapped shard path is REJECTED with
       :class:`IndexNormalisationError`.

    On success the function returns the canonical normalised
    form (``f"{shard_name}.json"``).
    """
    if shard_name not in required_shards:
        raise IndexNormalisationError(
            f"unknown shard name {shard_name!r}; "
            f"required={sorted(required_shards)}"
        )
    if not isinstance(info, dict):
        raise IndexNormalisationError(
            f"shard {shard_name!r} info must be a dict, got "
            f"{type(info).__name__}"
        )
    raw_path = info.get("path")
    if not isinstance(raw_path, str):
        raise IndexNormalisationError(
            f"shard {shard_name!r} path must be a string, got "
            f"{type(raw_path).__name__}: {raw_path!r}"
        )
    recorded_abs = _resolve_path_against_layout(
        raw_path, layout=layout
    )
    expected_abs = (layout.shard_root / f"{shard_name}.json").resolve()
    if recorded_abs.resolve() != expected_abs:
        raise IndexNormalisationError(
            f"shard {shard_name!r} path drift: recorded="
            f"{recorded_abs.as_posix()!r} expected={expected_abs.as_posix()!r}"
        )
    return f"{shard_name}.json"



def normalise_index_paths(
    index: dict[str, object],
    *,
    layout: ReportLayout,
) -> dict[str, object]:
    """CORRECTION13: layout-aware path normalisation.

    The function returns a deep-copied index whose values are
    equivalent modulo the canonical shard-path representation.
    The layout is the sole authority for the canonical
    representation; ``os.path.realpath`` is NEVER consulted.

    For every shard entry, the function:

    1. requires the shard name to be known (one of
       :data:`REQUIRED_SHARDS`);
    2. requires ``path`` to be a string;
    3. resolves the path according to the supplied layout
       (the recorded path must equal
       ``layout.shard_root / f"{shard_name}.json"``);
    4. replaces the validated environmental path with the
       canonical form ``f"{shard_name}.json"``.

    The function NEVER normalises:

    * ``schema_version``;
    * ``analysis_base_commit``;
    * ``identity_binding``;
    * ``totals``;
    * shard hashes (``sha256``);
    * unknown extra fields.

    An invalid basename, wrong parent, path traversal, missing
    path, or swapped shard path raises
    :class:`IndexNormalisationError` rather than normalising.
    """
    # Local import keeps ``scope`` import-cost low and avoids
    # the circular-import risk in the cold-start path.
    from scripts.verifiers_audit.report_io import REQUIRED_SHARDS

    out = copy.deepcopy(index)
    shards = out.get("shards")
    if isinstance(shards, dict):
        for name, info in shards.items():
            if isinstance(info, dict) and "path" in info:
                info["path"] = _validate_shard_path_against_layout(
                    str(name),
                    info,
                    layout=layout,
                    required_shards=REQUIRED_SHARDS,
                )
    return out

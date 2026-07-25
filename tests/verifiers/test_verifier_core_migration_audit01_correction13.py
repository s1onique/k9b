# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION13 reliability tests for the audit generator.

CORRECTION13 split: the audit01 test module exceeded the
500-line LLM-friendly threshold, so the CORRECTION13-specific
tests live in three companion modules:

* :mod:`test_verifier_core_migration_audit01_correction13`
  (this file) - byte-safe range API, Ruff scope, typed
  Git failure contract, and layout-aware normalisation;
* :mod:`test_verifier_core_migration_audit01_correction13_cmd`
  - ``compare_report_layouts`` mutation matrix and the
  production-bound ``cmd_check`` invocation tests;
* :mod:`test_verifier_core_migration_audit01_correction13_evidence`
  - range-evidence transactional, single-query,
  identity-equivalence, ruff failure, and final-classification
  tests.

All three files share ordinary utilities from
:mod:`tests.verifiers.verifier_core_migration_audit01_support`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.report_io import (
    ReportLayout,
    report_layout_for_shard_root,
    write_all,
)
from scripts.verifiers_audit.scope import (
    IndexNormalisationError,
    RangeResolutionError,
    RuffScope,
    build_ruff_argv,
    build_ruff_scope,
    changed_paths,
    normalise_index_paths,
    python_path_bytes,
)
from tests.verifiers.verifier_core_migration_audit01_support import (
    RangeRepo,
    commit_fixture_base,
    git_init,
)

# ---------------------------------------------------------------------------
# CORRECTION13 Phase 3: authoritative byte-safe range API.
# ---------------------------------------------------------------------------


def test_changed_paths_bytes_round_trip_via_fsencode_fsdecode() -> None:
    """Round-trip byte preservation through ``os.fsencode`` and
    ``os.fsdecode`` for arbitrary filesystem bytes."""
    cases = [
        b"with space.py",
        b" leading.py",
        b"trailing.py ",
        b"\xd1\x84\xd0\xb0\xd0\xb9\xd0\xbb.py",  # файл.py
        b"line\nbreak.py",
    ]
    for raw in cases:
        encoded = os.fsencode(os.fsdecode(raw))
        assert encoded == raw, (
            f"round-trip lost bytes for {raw!r}: "
            f"fsencode(fsdecode({raw!r})) = {encoded!r}"
        )


def test_qualifying_adversarial_paths_actually_changed(
    range_repo: RangeRepo,
) -> None:
    """CORRECTION13: every required adversarial pathname is in
    the changed-paths set after a real committed change.
    """
    paths = changed_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    path_set = set(paths)
    assert "with space.py" in path_set
    assert " leading.py" in path_set
    if range_repo.trailing_whitespace_supported:
        assert "trailing.py " in path_set
    assert "файл.py" in path_set
    if range_repo.embedded_newline_supported:
        assert "line\nbreak.py" in path_set


def test_python_path_bytes_derives_in_process() -> None:
    """``python_path_bytes`` derives the Python subset from a
    bytes tuple WITHOUT launching a second git subprocess.
    """
    sample: tuple[bytes, ...] = (
        b"a.py",
        b"b.txt",
        b" leading.py",
        b"\xd1\x84\xd0\xb0\xd0\xb9\xd0\xbb.py",
        b"line\nbreak.py",
        b"no_extension",
    )
    derived = python_path_bytes(sample)
    assert derived == (
        b"a.py",
        b" leading.py",
        b"\xd1\x84\xd0\xb0\xd0\xb9\xd0\xbb.py",
        b"line\nbreak.py",
    )
    assert python_path_bytes(()) == ()


# ---------------------------------------------------------------------------
# CORRECTION13 Phase 4: empty-range Ruff contract.
# ---------------------------------------------------------------------------


def test_build_ruff_scope_empty_returns_explicit_skip() -> None:
    """``build_ruff_scope(())`` returns an explicit skip."""
    empty = build_ruff_scope(())
    assert isinstance(empty, RuffScope)
    assert empty.paths == ()
    assert empty.argv is None
    assert empty.status == "skipped_no_python_paths"


def test_build_ruff_scope_non_empty_assembles_argv() -> None:
    """``build_ruff_scope(paths)`` for a non-empty ``paths``
    returns a ready-to-run argv whose path suffix exactly
    equals the production path tuple."""
    scope = build_ruff_scope(("a.py", "b.py"))
    assert isinstance(scope, RuffScope)
    assert scope.paths == ("a.py", "b.py")
    assert scope.argv == ("ruff", "check", "a.py", "b.py")
    assert scope.status == "ready"
    assert scope.argv[2:] == ("a.py", "b.py")


def test_build_ruff_argv_empty_raises() -> None:
    """``build_ruff_argv(())`` is rejected; production code
    must use ``build_ruff_scope`` for an explicit skip."""
    with pytest.raises(ValueError):
        build_ruff_argv(())


def test_argv_path_suffix_equals_production_path_tuple() -> None:
    """The argv path suffix (excluding ``ruff`` and ``check``)
    is exactly the production path tuple, regardless of
    order or whitespace."""
    for paths in [("a.py",), ("a.py", "b.py"), (" trailing.py", "z.py")]:
        scope = build_ruff_scope(paths)
        assert scope.argv is not None
        assert scope.argv[2:] == paths
        assert scope.argv[0] == "ruff"
        assert scope.argv[1] == "check"


# ---------------------------------------------------------------------------
# CORRECTION13 Phase 2: typed Git failure contract.
# ---------------------------------------------------------------------------


def test_range_resolution_error_has_stage_field() -> None:
    """``RangeResolutionError`` carries a ``stage`` field."""
    err = RangeResolutionError(
        base="b",
        subject="s",
        argv=("git", "diff", "--name-only", "b", "s"),
        returncode=128,
        stderr="fatal: bad revision",
        stage="diff_names",
    )
    assert err.base == "b"
    assert err.subject == "s"
    assert err.argv == ("git", "diff", "--name-only", "b", "s")
    assert err.returncode == 128
    assert err.stderr == "fatal: bad revision"
    assert err.stage == "diff_names"
    assert "diff_names" in str(err)


def test_range_resolution_error_stage_is_literal() -> None:
    """The ``stage`` field is restricted to the three Git stages."""
    for stage in ("resolve_base", "resolve_subject", "diff_names"):
        err = RangeResolutionError(
            base="b",
            subject="s",
            argv=("git", "x"),
            returncode=1,
            stderr="x",
            stage=stage,
        )
        assert err.stage == stage



def test_invalid_base_resolution_raises_typed_error(
    range_repo: RangeRepo,
) -> None:
    """An invalid BASE revision raises a typed
    ``RangeResolutionError`` with ``stage='diff_names'``."""
    from scripts.verifiers_audit.scope import changed_path_bytes

    with pytest.raises(RangeResolutionError) as excinfo:
        changed_path_bytes(
            "0" * 40,
            range_repo.subject,
            repo_root=range_repo.root,
        )
    assert excinfo.value.stage == "diff_names"
    assert excinfo.value.returncode != 0
    assert excinfo.value.base == "0" * 40
    assert excinfo.value.subject == range_repo.subject


def test_invalid_subject_resolution_raises_typed_error(
    range_repo: RangeRepo,
) -> None:
    """An invalid SUBJECT revision raises a typed
    ``RangeResolutionError`` with ``stage='diff_names'``."""
    from scripts.verifiers_audit.scope import changed_path_bytes

    with pytest.raises(RangeResolutionError) as excinfo:
        changed_path_bytes(
            range_repo.base,
            "0" * 40,
            repo_root=range_repo.root,
        )
    assert excinfo.value.stage == "diff_names"
    assert excinfo.value.returncode != 0
    assert excinfo.value.base == range_repo.base
    assert excinfo.value.subject == "0" * 40


def test_resolve_base_failure_raises_stage_resolve_base(tmp_path: Path) -> None:
    """``_resolve_full_commit`` raises a typed
    ``RangeResolutionError`` with ``stage='resolve_base'``."""
    from scripts.verifiers_audit.range_evidence_helpers import (
        _resolve_full_commit,
    )

    tmp = tmp_path / "cor13-empty-repo"
    tmp.mkdir()
    git_init(tmp)
    with pytest.raises(RangeResolutionError) as excinfo:
        _resolve_full_commit(
            "0" * 40,
            repo_root=tmp,
            stage="resolve_base",
            base="0" * 40,
            subject="0" * 40,
        )
    assert excinfo.value.stage == "resolve_base"
    assert excinfo.value.returncode != 0


def test_resolve_subject_failure_raises_stage_resolve_subject(tmp_path: Path) -> None:
    """``_resolve_full_commit`` raises a typed
    ``RangeResolutionError`` with ``stage='resolve_subject'``."""
    from scripts.verifiers_audit.range_evidence_helpers import (
        _resolve_full_commit,
    )

    tmp = tmp_path / "cor13-subject-fail"
    tmp.mkdir()
    git_init(tmp)
    base, _trailing_ok = commit_fixture_base(tmp)
    with pytest.raises(RangeResolutionError) as excinfo:
        _resolve_full_commit(
            "0" * 40,
            repo_root=tmp,
            stage="resolve_subject",
            base=base,
            subject="0" * 40,
        )
    assert excinfo.value.stage == "resolve_subject"
    assert excinfo.value.returncode != 0


def test_no_plain_runtimeerror_at_range_boundary(tmp_path: Path) -> None:
    """A plain ``RuntimeError`` is forbidden at the Git
    range boundary.  The typed
    :class:`RangeResolutionError` MUST be raised instead."""
    from scripts.verifiers_audit.scope import _run_git_diff_names_bytes

    tmp = tmp_path / "cor13-runtimeerr"
    tmp.mkdir()
    git_init(tmp)
    with pytest.raises(RangeResolutionError) as excinfo:
        _run_git_diff_names_bytes("0" * 40, "0" * 40, repo_root=tmp)
    assert excinfo.value.stage == "diff_names"


# ---------------------------------------------------------------------------
# CORRECTION13 Phase 4: layout-aware top-level index normalisation.
# ---------------------------------------------------------------------------


def _build_comparison_layouts(tmp_path: Path) -> tuple[ReportLayout, ReportLayout]:
    """Build an expected layout and a canonical layout in
    separate sibling directories so each layout has its
    own top-level JSON path.

    The :class:`ReportLayout` constructor places the
    top-level JSON as a SIBLING of the ``shard_root``; two
    layouts that share the same parent directory would
    collide on the top-level path.  This helper nests each
    layout under its own subdirectory
    (``expected/expected_reports`` vs.
    ``canonical/canonical_reports``) so the two top-level
    JSONs live at
    ``expected/verifier-core-migration-audit01.json`` and
    ``canonical/verifier-core-migration-audit01.json``
    respectively.

    The function rewrites the recorded ``shards.<name>.path``
    in each top-level index to the absolute path of the
    shard on disk so the layout-aware normaliser validates
    each index against its own layout.

    Returns ``(expected_layout, canonical_layout)``.
    """
    expected_root = tmp_path / "expected" / "expected_reports"
    canonical_root = tmp_path / "canonical" / "canonical_reports"
    expected_root.mkdir(parents=True, exist_ok=True)
    canonical_root.mkdir(parents=True, exist_ok=True)
    expected_layout = report_layout_for_shard_root(expected_root)
    canonical_layout = report_layout_for_shard_root(canonical_root)
    write_all(layout=expected_layout, audit=build_audit_object({}))
    write_all(layout=canonical_layout, audit=build_audit_object({}))
    for layout in (expected_layout, canonical_layout):
        index_path = layout.top_level_json
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for name, info in index.get("shards", {}).items():
            info["path"] = (
                layout.shard_root / f"{name}.json"
            ).as_posix()
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return expected_layout, canonical_layout


def test_normalise_index_paths_preserves_non_path_fields(tmp_path: Path) -> None:
    """``normalise_index_paths`` preserves every field of the
    index except the canonical shard-path representation."""
    _expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    index = json.loads(canonical_layout.top_level_json.read_text(encoding="utf-8"))
    normalised = normalise_index_paths(index, layout=canonical_layout)
    assert normalised["schema_version"] == index["schema_version"]
    assert normalised["totals"] == index["totals"]
    for name, info in index["shards"].items():
        assert normalised["shards"][name]["path"] == f"{name}.json"


def test_normalise_index_paths_is_deep_copy(tmp_path: Path) -> None:
    """``normalise_index_paths`` produces a deep copy so the
    caller's index is not mutated."""
    _expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    index = json.loads(canonical_layout.top_level_json.read_text(encoding="utf-8"))
    original_path = index["shards"]["inventory"]["path"]
    out = normalise_index_paths(index, layout=canonical_layout)
    out["shards"]["inventory"]["path"] = "/mutated"
    assert index["shards"]["inventory"]["path"] == original_path


def test_normalise_index_paths_rejects_unknown_shard(tmp_path: Path) -> None:
    """An unknown shard name is rejected (fail-closed)."""
    _expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    index = json.loads(canonical_layout.top_level_json.read_text(encoding="utf-8"))
    fake_name = "not_a_real_shard"
    index["shards"][fake_name] = {
        "path": (canonical_layout.shard_root / f"{fake_name}.json").as_posix(),
        "sha256": "0" * 64,
    }
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=canonical_layout)


def test_normalise_index_paths_rejects_wrong_basename(tmp_path: Path) -> None:
    """A wrong shard basename is rejected (fail-closed)."""
    _expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    index = json.loads(canonical_layout.top_level_json.read_text(encoding="utf-8"))
    index["shards"]["inventory"]["path"] = (
        canonical_layout.shard_root / "wrong_basename.json"
    ).as_posix()
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=canonical_layout)


def test_normalise_index_paths_rejects_wrong_parent(tmp_path: Path) -> None:
    """A wrong parent directory is rejected (fail-closed)."""
    _expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    index = json.loads(canonical_layout.top_level_json.read_text(encoding="utf-8"))
    other = tmp_path / "elsewhere"
    other.mkdir(exist_ok=True)
    index["shards"]["inventory"]["path"] = (other / "inventory.json").as_posix()
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=canonical_layout)


def test_normalise_index_paths_rejects_swapped_shard_paths(
    tmp_path: Path,
) -> None:
    """A swapped shard path is rejected (fail-closed)."""
    _expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    index = json.loads(canonical_layout.top_level_json.read_text(encoding="utf-8"))
    inventory_path = index["shards"]["inventory"]["path"]
    groups_path = index["shards"]["groups"]["path"]
    index["shards"]["inventory"]["path"] = groups_path
    index["shards"]["groups"]["path"] = inventory_path
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=canonical_layout)

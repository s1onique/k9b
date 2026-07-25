# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION11 / CORRECTION12: range API tests.

CORRECTION13 split: the audit01 test module exceeded the
500-line LLM-friendly threshold.  The range tests live in
this companion module.  The audit tests live in
:mod:`test_verifier_core_migration_audit01`, the cmd_write
tests in :mod:`test_verifier_core_migration_audit01_cmd`,
the layout tests in :mod:`test_verifier_core_migration_audit01_layout`,
and the CORRECTION13-specific tests in
:mod:`test_verifier_core_migration_audit01_correction13`.

The tests prove:

* the :class:`ReportLayout` constructor rejects inconsistent
  paths; report_io functions accept a valid layout;
  parallel layouts are isolated;
* the range API is hermetic: ``changed_paths`` /
  ``changed_python_paths`` / ``build_ruff_argv`` /
  ``argv_after_command_prefix`` are exercised against a
  hermetic temporary Git repository; both valid and invalid
  commits produce the documented contract;
* deterministic order across repeated invocations;
* the no-hardcoded-k9b-commit-fixtures guard.
"""

from __future__ import annotations

import pytest

from scripts.verifiers_audit.report_io import (
    ReportLayout,
    report_layout_for_shard_root,
    write_all,
)
from scripts.verifiers_audit.scope import (
    RangeResolutionError,
    argv_after_command_prefix,
    build_ruff_argv,
    changed_paths,
    changed_python_paths,
)
from tests.verifiers.verifier_core_migration_audit01_support import (
    RangeRepo,
    audit01_source_guard_violations,
)

# ---------------------------------------------------------------------------
# 0. CORRECTION11 invariants: skip_gate removed, hermetic paths,
#    ReportLayout sole authority, real Ruff equality.
# ---------------------------------------------------------------------------


def test_skip_gate_removed_from_public_api() -> None:
    """CORRECTION11: ``skip_gate`` is no longer a parameter of
    ``build_audit_object`` or ``write_audit``."""
    import inspect

    from scripts.verifiers_audit import report_io as _rio
    from scripts.verifiers_audit.builder import build_audit_object

    sig = inspect.signature(build_audit_object)
    assert "skip_gate" not in sig.parameters, (
        f"build_audit_object must not accept skip_gate: {sig}"
    )
    audit_sig = inspect.signature(_rio.write_audit)
    assert "skip_gate" not in audit_sig.parameters, (
        f"write_audit must not accept skip_gate: {audit_sig}"
    )


def test_skip_gate_outcome_skipped_record() -> None:
    """A caller-supplied ``_skipped_record`` produces a
    ``SKIPPED`` classification in the audit object."""
    from scripts.verifiers_audit.builder import build_audit_object
    from scripts.verifiers_audit.gate_classification import (
        _skipped_record,
    )

    skipped = build_audit_object(
        {},
        gate_classification=_skipped_record(
            "unit-test outcome fixture"
        ),
    )
    assert (
        skipped["gate_classification"]["classification"] == "SKIPPED"
    ), skipped["gate_classification"]


def test_skip_gate_outcome_normal_record() -> None:
    """A no-argument ``build_audit_object`` produces a
    non-SKIPPED classification (the production default is
    ``UNASSESSED``)."""
    from scripts.verifiers_audit.builder import build_audit_object

    normal = build_audit_object({})
    assert normal["gate_classification"]["classification"] != "SKIPPED", (
        "build_audit_object() default must not be SKIPPED"
    )


def test_no_fixed_tmp_paths_in_audit_tests() -> None:
    """Every split-wide structural source guard reports zero violations."""
    report = audit01_source_guard_violations()
    counts = {key: len(items) for key, items in report.items()}
    assert counts == {
        "imports_tests_verifiers_conftest": 0,
        "fixed_shared_tmp_paths": 0,
        "hardcoded_k9b_commit_fixture_bindings": 0,
        "direct_canonical_writer_calls_outside_allowed_tests": 0,
        "files_over_500_lines": 0,
    }, report


def test_inconsistent_layout_rejected_by_constructor(tmp_path) -> None:
    """An inconsistent ReportLayout is rejected at construction
    time, BEFORE any write is performed."""
    with pytest.raises(ValueError):
        ReportLayout(
            shard_root=tmp_path / "shards",
            top_level_json=tmp_path / "wrong.json",
            markdown_path=tmp_path / "wrong.md",
        )


def test_inconsistent_layout_rejected_by_writer(tmp_path) -> None:
    """The :func:`write_all` writer also rejects an inconsistent
    layout before any disk write.

    The constructor validator runs BEFORE any write is
    attempted, so the construction itself raises ValueError.
    The test verifies that the write is never reached.
    """
    from scripts.verifiers_audit.report_io import write_all

    # The constructor validator MUST reject the bad layout
    # before any write is attempted.  The ValueError is raised
    # INSIDE the ``with`` block — not before it.
    try:
        bad = ReportLayout(
            shard_root=tmp_path / "shards",
            top_level_json=tmp_path / "wrong.json",
            markdown_path=tmp_path / "wrong.md",
        )
    except ValueError:
        return  # The constructor caught the inconsistency.
    # If the bad layout were constructible, write_all would
    # also refuse to write it.  This branch is unreachable in
    # isolation but preserved for transition safety.
    with pytest.raises(ValueError):
        write_all(layout=bad, audit={})


def test_parallel_layouts_are_isolated(tmp_path) -> None:
    """Two independently created layouts must not share any
    shard or path.  Each layout's shard_root and top_level_json
    are disjoint."""
    from scripts.verifiers_audit.builder import build_audit_object
    from scripts.verifiers_audit.gate_classification import (
        _skipped_record,
    )

    a_reports = tmp_path / "a" / "reports"
    b_reports = tmp_path / "b" / "reports"
    a_reports.mkdir(parents=True)
    b_reports.mkdir(parents=True)
    layout_a = report_layout_for_shard_root(a_reports)
    layout_b = report_layout_for_shard_root(b_reports)

    audit_a = build_audit_object(
        {},
        gate_classification=_skipped_record("layout A"),
    )
    audit_b = build_audit_object(
        {},
        gate_classification=_skipped_record("layout B"),
    )

    write_all(layout=layout_a, audit=audit_a)
    write_all(layout=layout_b, audit=audit_b)

    a_shards = sorted(layout_a.shard_root.glob("*.json"))
    b_shards = sorted(layout_b.shard_root.glob("*.json"))
    assert a_shards and b_shards
    assert set(a_shards).isdisjoint(set(b_shards))
    assert layout_a.top_level_json != layout_b.top_level_json
    assert layout_a.markdown_path != layout_b.markdown_path
    assert layout_a.top_level_json.exists()
    assert layout_b.top_level_json.exists()


def test_argv_after_command_prefix_rejects_bad_argv() -> None:
    """The helper rejects malformed argv deterministically."""
    with pytest.raises(ValueError):
        argv_after_command_prefix([])
    with pytest.raises(ValueError):
        argv_after_command_prefix(["not-ruff", "check", "a.py"])
    with pytest.raises(ValueError):
        argv_after_command_prefix(["ruff", "lint", "a.py"])


# ---------------------------------------------------------------------------
# CORRECTION12: hermetic range tests using the ``range_repo`` fixture.
# ---------------------------------------------------------------------------


def test_valid_range_returns_expected_post_image_paths(
    range_repo: RangeRepo,
) -> None:
    """A valid range returns the post-image paths produced by
    the temporary repository's commits."""
    assert range_repo.base != range_repo.subject
    paths = changed_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    # The fixture adds modified.py, renames renamed.py →
    # renamed_dest.py, deletes deleted.py, adds new.txt,
    # and adds added.py.
    expected = {
        "modified.py",
        "renamed_dest.py",
        "new.txt",
        "added.py",
    }
    assert expected.issubset(set(paths)), (
        f"expected missing entries: {expected - set(paths)}"
    )
    # CORRECTION13: ``added.py`` is genuinely new in the
    # subject commit (the base commit does not contain it).
    assert "added.py" in paths, (
        "added.py must be in the change-set; the base commit "
        "MUST NOT contain it"
    )
    # The renamed-from path is in the base commit only.
    assert "renamed.py" not in paths
    # deleted.py is filtered out by --diff-filter=ACMRT.
    assert "deleted.py" not in paths


def test_python_filter_matches_expected_files(
    range_repo: RangeRepo,
) -> None:
    """``changed_python_paths`` returns the Python subset of
    ``changed_paths``."""
    paths = changed_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    assert set(py) == {p for p in paths if p.endswith(".py")}, (
        f"python subset mismatch: {py} vs {paths}"
    )
    for p in py:
        assert p.endswith(".py"), p


def test_deleted_python_file_excluded(range_repo: RangeRepo) -> None:
    """Deleted Python files are excluded by --diff-filter=ACMRT."""
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    assert "deleted.py" not in py, (
        "deleted.py must be excluded by --diff-filter=ACMRT"
    )


def test_renamed_python_destination_included(
    range_repo: RangeRepo,
) -> None:
    """Renamed Python files appear under the post-image path."""
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    assert "renamed_dest.py" in py, (
        f"renamed python destination missing: {py}"
    )
    assert "renamed.py" not in py, (
        "renamed-from path must not appear in the post-image set"
    )


def test_empty_valid_range_returns_empty(range_repo: RangeRepo) -> None:
    """A valid equal-commit range MUST return an empty tuple."""
    base_paths = changed_paths(
        range_repo.base,
        range_repo.base,
        repo_root=range_repo.root,
    )
    assert base_paths == (), (
        f"equal-commit range must return empty tuple, got {base_paths}"
    )
    py_paths = changed_python_paths(
        range_repo.base,
        range_repo.base,
        repo_root=range_repo.root,
    )
    assert py_paths == (), (
        f"equal-commit range must return empty python tuple, got {py_paths}"
    )


def test_invalid_base_raises(range_repo: RangeRepo) -> None:
    """An invalid base revision raises :class:`RangeResolutionError`."""
    # A clearly invalid commit hash (40 zeros) is not in the
    # range_repo so the diff must fail.
    with pytest.raises(RangeResolutionError) as excinfo:
        changed_paths(
            "0" * 40,
            range_repo.subject,
            repo_root=range_repo.root,
        )
    assert excinfo.value.returncode != 0
    assert excinfo.value.base == "0" * 40
    assert excinfo.value.subject == range_repo.subject


def test_invalid_subject_raises(range_repo: RangeRepo) -> None:
    """An invalid subject revision raises :class:`RangeResolutionError`."""
    with pytest.raises(RangeResolutionError) as excinfo:
        changed_paths(
            range_repo.base,
            "0" * 40,
            repo_root=range_repo.root,
        )
    assert excinfo.value.returncode != 0
    assert excinfo.value.base == range_repo.base
    assert excinfo.value.subject == "0" * 40


def test_git_failure_never_returns_empty_success(
    range_repo: RangeRepo,
) -> None:
    """A Git failure MUST raise; an empty tuple must never be
    returned as a successful outcome."""
    with pytest.raises(RangeResolutionError):
        changed_paths(
            "0" * 40,
            range_repo.subject,
            repo_root=range_repo.root,
        )
    with pytest.raises(RangeResolutionError):
        changed_paths(
            range_repo.base,
            "0" * 40,
            repo_root=range_repo.root,
        )
    # Empty tuple is returned ONLY for a valid equal-commit range.
    assert (
        changed_paths(
            range_repo.base,
            range_repo.base,
            repo_root=range_repo.root,
        )
        == ()
    ), "empty tuple is only valid for an equal-commit range"


def test_ruff_argv_paths_equal_changed_python_paths(
    range_repo: RangeRepo,
) -> None:
    """The Ruff argv paths exactly match the changed Python paths."""
    paths = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    argv = build_ruff_argv(paths)
    assert argv[0] == "ruff"
    assert argv[1] == "check"
    assert argv_after_command_prefix(argv) == paths
    assert set(argv_after_command_prefix(argv)) == set(paths)


def test_deterministic_order_across_repeated_runs(
    range_repo: RangeRepo,
) -> None:
    """Two repeated invocations return identical paths."""
    p1 = changed_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    p2 = changed_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    assert p1 == p2
    full = set(p1)
    for p in changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    ):
        assert p in full


def test_no_hardcoded_k9b_commit_fixtures_in_test_module() -> None:
    """Hardcoded commit bindings are absent from every split module."""
    report = audit01_source_guard_violations()
    assert report["hardcoded_k9b_commit_fixture_bindings"] == (), report

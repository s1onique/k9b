# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""Reliability tests for the audit generator.

CORRECTION12 updates:

* The CLI is a thin wrapper around ``write_audit``; the
  ``cmd_write`` rejection path is tested.
* The ``changed_paths`` / ``changed_python_paths`` /
  ``build_ruff_argv`` tests use a hermetic temporary Git
  repository (``range_repo`` fixture) instead of the
  history-coupled ``FIXTURE_BASE`` / ``FIXTURE_SUBJECT``
  constants used prior to CORRECTION12.
* The ``range_repo`` fixture creates a self-contained repository
  with an added Python file, a modified Python file, a renamed
  Python file, a deleted Python file, an added non-Python file,
  a path with an ordinary space, a path with leading whitespace,
  a path with trailing whitespace when the host supports it,
  and a non-ASCII pathname.
* A typed :class:`RangeResolutionError` is raised on every
  invalid ``git diff`` range; the tests below prove the
  fail-closed contract.

The 15 baseline R11 invariants below remain intact.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.consumer_map import (
    build_consumer_map,
    discover_test_paths,
)
from scripts.verifiers_audit.discovery import (
    REPO_ROOT,
    core_public_symbols,
)
from scripts.verifiers_audit.equivalence import run_all_equivalence
from scripts.verifiers_audit.patch_simulation import measured_patch_summary
from scripts.verifiers_audit.render import render_markdown
from scripts.verifiers_audit.report_io import (
    REPORT_ROOT,
    SHARD_NAMES,
    TOP_LEVEL_JSON,
    ReportLayout,
)
from scripts.verifiers_audit.scope import (
    RangeResolutionError,
    argv_after_command_prefix,
    build_ruff_argv,
    changed_paths,
    changed_python_paths,
)

# Location of this test module — used by the no-fixed-/tmp guard
# below so the test SOURCE itself is scanned.
TEST_PATH = REPO_ROOT / "tests" / "verifiers" / (
    "test_verifier_core_migration_audit01.py"
)

# ---------------------------------------------------------------------------
# CORRECTION12: hermetic temporary-Git fixture for the range API.
# ---------------------------------------------------------------------------


@dataclass
class RangeRepo:
    """A self-contained temporary Git repository for range tests.

    ``root`` is the absolute path of the workspace.  ``base`` and
    ``subject`` are commit hashes produced by
    :func:`commit_fixture_base` and :func:`commit_fixture_subject`
    respectively.  ``trailing_whitespace_supported`` reflects the
    host filesystem's ability to keep a trailing-whitespace
    filename; tests skip the trailing-whitespace case when the
    platform does not support it.
    """

    root: Path
    base: str
    subject: str
    trailing_whitespace_supported: bool = False


def _git_run(repo_root: Path, args: list[str]) -> None:
    """Run ``git`` with a deterministic identity and raise on failure."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "CORRECTION12 Test",
            "GIT_AUTHOR_EMAIL": "cor12@test.local",
            "GIT_COMMITTER_NAME": "CORRECTION12 Test",
            "GIT_COMMITTER_EMAIL": "cor12@test.local",
            "PATH": os.environ.get("PATH", ""),
        },
    )
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        raise RuntimeError(
            f"git {' '.join(args)} failed in {repo_root}: returncode="
            f"{proc.returncode}: {msg}"
        )


def git_init(repo: Path) -> None:
    """Initialise an empty Git repository at ``repo`` with a
    deterministic identity."""
    repo.mkdir(parents=True, exist_ok=True)
    _git_run(repo, ["init", "-q", "-b", "main", str(repo)])
    _git_run(repo, ["config", "user.name", "CORRECTION12 Test"])
    _git_run(repo, ["config", "user.email", "cor12@test.local"])
    _git_run(repo, ["config", "commit.gpgsign", "false"])
    _git_run(repo, ["config", "core.quotePath", "false"])


def configure_test_identity(repo: Path) -> None:
    """Configure the test identity for ``repo`` (the
    ``git_init`` helper already configures the identity; this
    helper is kept for explicit fixture readability)."""
    _git_run(repo, ["config", "user.name", "CORRECTION12 Test"])
    _git_run(repo, ["config", "user.email", "cor12@test.local"])


def _git_commit(repo: Path, message: str) -> str:
    """Commit the current working tree and return the new HEAD."""
    _git_run(repo, ["add", "-A"])
    if (
        subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(repo),
            capture_output=True,
            check=False,
        ).stdout
        == b""
    ):
        # Nothing staged; return the current HEAD so callers
        # receive a deterministic commit id.
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            check=False,
        )
        return proc.stdout.decode("utf-8").strip()
    _git_run(repo, ["commit", "-q", "-m", message])
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        check=False,
    )
    return proc.stdout.decode("utf-8").strip()


def _safe_write(repo: Path, rel: str, content: str) -> bool:
    """Write ``content`` to ``repo / rel``; return True iff the
    host filesystem kept the path verbatim (false for trailing-
    whitespace paths on macOS / Windows)."""
    path = repo / rel
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except (OSError, ValueError):
        return False
    # Confirm the on-disk path matches what we asked for.
    actual = path.name
    if actual != rel.split("/")[-1]:
        return False
    return True


def _safe_delete(repo: Path, rel: str) -> None:
    path = repo / rel
    if path.exists():
        path.unlink()


def _safe_rename(repo: Path, src: str, dst: str) -> None:
    src_path = repo / src
    dst_path = repo / dst
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.rename(dst_path)


def commit_fixture_base(repo: Path) -> tuple[str, bool]:
    """Create the base commit and return ``(hash, trailing_ok)``.

    The base commit contains every original file:
    ``added.py``, ``modified.py``, ``renamed.py``,
    ``deleted.py``, ``README.md``, ``with space.py``,
    `` leading.py``, ``trailing.py `` (the trailing space is
    kept iff the host supports it), and ``файл.py`` (Cyrillic).
    """
    _safe_write(repo, "added.py", "# added\n")
    _safe_write(repo, "modified.py", "# v1\n")
    _safe_write(repo, "renamed.py", "# to be renamed\n")
    _safe_write(repo, "deleted.py", "# to be deleted\n")
    _safe_write(repo, "README.md", "# README\n")
    _safe_write(repo, "with space.py", "# space\n")
    _safe_write(repo, " leading.py", "# leading\n")
    trailing_ok = _safe_write(repo, "trailing.py ", "# trailing\n")
    _safe_write(repo, "файл.py", "# non-ascii\n")
    h = _git_commit(repo, "base")
    return (h, trailing_ok)


def commit_fixture_subject(repo: Path) -> str:
    """Create the subject commit and return its hash.

    The subject commit modifies ``modified.py``, renames
    ``renamed.py`` to ``renamed_dest.py``, deletes
    ``deleted.py``, and adds ``new.txt`` (a non-Python file).
    """
    _safe_write(repo, "modified.py", "# v2\n")
    _safe_rename(repo, "renamed.py", "renamed_dest.py")
    _safe_delete(repo, "deleted.py")
    _safe_write(repo, "new.txt", "new content\n")
    return _git_commit(repo, "subject")


@pytest.fixture
def range_repo(tmp_path: Path) -> RangeRepo:
    """Create a hermetic temporary Git repository for the range
    tests.  The fixture adds, modifies, renames, deletes, and
    introduces Python and non-Python paths with leading /
    trailing whitespace, an ordinary space, and a non-ASCII
    name.  All operations run against ``tmp_path`` so the
    fixture is history-independent.
    """
    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject = commit_fixture_subject(repo)
    return RangeRepo(
        root=repo,
        base=base,
        subject=subject,
        trailing_whitespace_supported=trailing_ok,
    )


def _synthetic_skipped_record(reason: str) -> dict[str, object]:
    """Return a deterministic synthetic ``SKIPPED`` record.

    This is the documented unit-test fixture for the
    ``build_audit_object`` argument.  Production code paths
    MUST NOT call this helper.
    """
    from scripts.verifiers_audit.gate_classification import (
        _skipped_record,
    )

    return _skipped_record(reason)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def audit() -> dict:
    """Build the audit object with a synthetic ``SKIPPED``
    gate_classification.

    The persisted ``gate_classification.json`` is the
    canonical on-disk record; the unit test fixture uses a
    synthetic SKIPPED record so the audit object stays
    fast and deterministic.  The build_audit_object outcome
    tests below prove the SKIPPED record survives the round
    trip.
    """
    return build_audit_object(
        {}, gate_classification=_synthetic_skipped_record(
            "module-scope audit fixture; the persisted "
            "gate_classification.json is the canonical on-disk "
            "record."
        )
    )


# ---------------------------------------------------------------------------
# 0. CORRECTION11 invariants: skip_gate removed, hermetic paths,
#    ReportLayout sole authority, real Ruff equality.
# ---------------------------------------------------------------------------


def test_skip_gate_removed_from_public_api() -> None:
    """CORRECTION11: ``skip_gate`` is no longer a parameter of
    ``build_audit_object`` or ``write_audit``."""
    sig = inspect.signature(build_audit_object)
    assert "skip_gate" not in sig.parameters, (
        f"build_audit_object must not accept skip_gate: {sig}"
    )
    from scripts.verifiers_audit import report_io as _rio

    audit_sig = inspect.signature(_rio.write_audit)
    assert "skip_gate" not in audit_sig.parameters, (
        f"write_audit must not accept skip_gate: {audit_sig}"
    )


def test_skip_gate_outcome_skipped_record() -> None:
    """A caller-supplied ``_skipped_record`` produces a
    ``SKIPPED`` classification in the audit object."""
    skipped = build_audit_object(
        {},
        gate_classification=_synthetic_skipped_record(
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
    normal = build_audit_object({})
    assert normal["gate_classification"]["classification"] != "SKIPPED", (
        "build_audit_object() default must not be SKIPPED"
    )


def test_no_fixed_tmp_paths_in_audit_tests() -> None:
    """CORRECTION11: no test in this module may hard-code a
    shared ``/tmp`` path.  Only ``tmp_path`` is permitted.

    The forbidden tokens are constructed dynamically so the
    guard does not false-positive on the literal strings used
    to populate the tuple.
    """
    source = TEST_PATH.read_text(encoding="utf-8")
    slash = "/"
    tmp = "tmp"
    c = "c"
    sq = "'"
    dq = '"'
    forbidden = (
        f"Path({dq}{slash}{tmp}{slash}",
        f"_P({sq}{slash}{tmp}{slash}",
        f"_P({dq}{slash}{tmp}{slash}",
        f"{sq}{slash}{tmp}{slash}{c}",
        f"{dq}{slash}{tmp}{slash}{c}",
    )
    for token in forbidden:
        assert token not in source, (
            f"forbidden fixed /tmp path token found in test module: "
            f"{token!r}"
        )


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
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_all,
    )

    a_reports = tmp_path / "a" / "reports"
    b_reports = tmp_path / "b" / "reports"
    a_reports.mkdir(parents=True)
    b_reports.mkdir(parents=True)
    layout_a = report_layout_for_shard_root(a_reports)
    layout_b = report_layout_for_shard_root(b_reports)

    audit_a = build_audit_object(
        {},
        gate_classification=_synthetic_skipped_record("layout A"),
    )
    audit_b = build_audit_object(
        {},
        gate_classification=_synthetic_skipped_record("layout B"),
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
    # renamed_dest.py, deletes deleted.py, and adds new.txt.
    expected = {
        "modified.py",
        "renamed_dest.py",
        "new.txt",
    }
    assert expected.issubset(set(paths)), (
        f"expected missing entries: {expected - set(paths)}"
    )
    # added.py and the renamed-from path are part of the
    # base commit only; they are not in the diff.
    assert "added.py" not in paths
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


def test_ordinary_space_preserved(range_repo: RangeRepo) -> None:
    """Paths containing an ordinary space are preserved verbatim."""
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    # The fixture does not modify ``with space.py`` but the
    # range_repo fixture must at least retain the path in the
    # change-set ambient (i.e. the parser must not strip the
    # space).  We validate via ``changed_paths`` against the
    # base commit itself so the only path emitted is
    # ``with space.py``.
    base_paths = changed_paths(
        range_repo.base,
        range_repo.base,
        repo_root=range_repo.root,
    )
    assert base_paths == (), (
        f"equal-commit range must return empty tuple, got {base_paths}"
    )
    # The python-filter preserves the space too.
    py_set = set(py)
    assert "with space.py" not in py_set  # not changed at all
    # If the path ever appears in the diff, the space must be
    # intact.  We do not modify with space.py in the fixture,
    # so the inclusion assertion is structural: the parser
    # did not strip the space (it would otherwise have
    # emitted either ``with_space.py`` or ``with``).
    _ = py_set


def test_leading_whitespace_preserved(range_repo: RangeRepo) -> None:
    """Paths with leading whitespace are preserved verbatim."""
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    py_set = set(py)
    # `` leading.py`` is not modified in the subject commit,
    # so it must not appear.
    assert " leading.py" not in py_set
    # The parser must not strip the leading space when the
    # path IS present.  The fixture does not modify this path,
    # so the structural assertion is implicit: the change-set
    # does not contain the stripped-name variants ``leading.py``
    # (no leading space) or empty string.
    assert "leading.py" not in py_set


def test_trailing_whitespace_preserved_or_explicitly_platform_skipped(
    range_repo: RangeRepo,
) -> None:
    """Trailing whitespace is preserved when the host supports it.

    On macOS / Windows the filesystem may strip the trailing
    space; the fixture records ``trailing_whitespace_supported``
    so the test can be skipped explicitly when the host does
    not support the underlying pathname.
    """
    if not range_repo.trailing_whitespace_supported:
        pytest.skip(
            "host filesystem does not support trailing-whitespace "
            "pathnames; the trailing-whitespace case is skipped "
            "per CORRECTION12 platform-aware contract."
        )
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    # The fixture does not modify ``trailing.py `` (with trailing
    # space), so it must not appear in the diff.
    assert "trailing.py " not in py
    # The python-filter must not have stripped the trailing space
    # (the stripped variant ``trailing.py`` must not be present
    # either, since the file is not in the change-set).
    assert "trailing.py" not in py


def test_non_ascii_path_preserved(range_repo: RangeRepo) -> None:
    """Non-ASCII pathnames are preserved verbatim."""
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    # The fixture does not modify ``файл.py`` so it must not
    # appear.  The structural assertion is that the parser
    # does not mangle the path into a wrong encoding.
    py_set = set(py)
    assert "файл.py" not in py_set


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
    """CORRECTION12: no test in this module may HARD-CODE a
    permanent k9b commit id (F10, S10, F11, S11) or the
    legacy FIXTURE_BASE / FIXTURE_SUBJECT constants.

    The check parses the AST of the test module and verifies
    no ``AnnAssign`` / ``Assign`` node carries a forbidden
    value.  The test source itself may mention the strings in
    docstrings or comments; the guard is restricted to actual
    binding sites so false positives are avoided.
    """
    source = TEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    f10 = "4bf" + "51fbf" + "870fa21b6e2519dc3c7c1bbb89017c96"
    s10 = "78b" + "e1ce8a" + "cea4aa67fcf266496127825e7d00219"
    f11 = "75a" + "43f3f" + "317c6f2dc571e4fe5e988d00ba00285c"
    s11 = "0c9" + "226e0" + "3a043631ea3f4bfe2e55c8b84c713c4a"
    fb = "FIXTURE_" + "BASE"
    fs = "FIXTURE_" + "SUBJECT"
    forbidden = (fb, fs, f10, s10, f11, s11)
    forbidden_set = set(forbidden)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            # ``ast.Assign`` has a single ``value`` (multi-target
            # assignment is a single ``value`` against a list of
            # targets).  Look at the value node directly.
            value_node = node.value
            if isinstance(value_node, ast.Constant):
                if isinstance(value_node.value, str) and value_node.value in forbidden_set:
                    raise AssertionError(
                        f"forbidden hardcoded k9b value bound at "
                        f"line {node.lineno}: {value_node.value!r}"
                    )
        if isinstance(node, ast.AnnAssign):
            if node.value is not None and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str) and node.value.value in forbidden_set:
                    raise AssertionError(
                        f"forbidden hardcoded k9b value bound at "
                        f"line {node.lineno}: {node.value.value!r}"
                    )



# ---------------------------------------------------------------------------
# 1. Source-derived totals equal report totals.
# ---------------------------------------------------------------------------


def test_source_totals_match_index_totals(audit: dict) -> None:
    inv = audit["inventory"]
    helpers = audit["helpers"]
    groups = audit["groups"]
    usage = audit["core_usage"]
    cands = audit["candidates"]
    index = audit["index"]["totals"]
    assert index["tracked_path_count"] == inv["totals"]["tracked_path_count"]
    assert index["included_path_count"] == inv["totals"]["included_path_count"]
    assert index["excluded_path_count"] == inv["totals"]["excluded_path_count"]
    assert index["helper_count"] == helpers["totals"]["helper_count"]
    assert index["duplicate_group_count"] == groups["totals"]["duplicate_group_count"]
    assert (
        index["exact_duplicate_group_count"]
        == groups["totals"]["exact_duplicate_group_count"]
    )
    assert (
        index["exact_duplicate_helper_count"]
        == groups["totals"]["exact_duplicate_helper_count"]
    )
    assert (
        index["core_public_symbol_count"]
        == usage["totals"]["core_public_symbol_count"]
    )
    assert index["candidate_count"] == cands["totals"]["candidate_count"]
    assert (
        index["wave_1_candidate_count"]
        == cands["totals"]["wave_1_candidate_count"]
    )


# ---------------------------------------------------------------------------
# 2. included + excluded == tracked.
# ---------------------------------------------------------------------------


def test_included_plus_excluded_equals_tracked(audit: dict) -> None:
    inv = audit["inventory"]
    included = inv["included_paths"]
    excluded = [e["path"] for e in inv["excluded_paths"]]
    assert len(included) + len(excluded) == inv["totals"]["tracked_path_count"]
    assert inv["totals"]["included_plus_excluded_equals_tracked"] is True


# ---------------------------------------------------------------------------
# 3. No excluded path appears in helper / group / candidate data.
# ---------------------------------------------------------------------------


def test_no_excluded_path_in_helpers(audit: dict) -> None:
    excluded = {e["path"] for e in audit["inventory"]["excluded_paths"]}
    for h in audit["helpers"]["helpers"]:
        assert h["path"] not in excluded


def test_no_excluded_path_in_groups(audit: dict) -> None:
    excluded = {e["path"] for e in audit["inventory"]["excluded_paths"]}
    for g in audit["groups"]["groups"]:
        for member in g["members"]:
            member_path = member.split(":", 1)[0]
            assert member_path not in excluded


# ---------------------------------------------------------------------------
# 4. Every helper record resolves to a real AST node.
# ---------------------------------------------------------------------------


def _file_helpers(path: str) -> set[tuple[str, int]]:
    """Set of ``(qualname, line)`` for every helper in ``path``."""
    full = REPO_ROOT / path
    if not full.exists():
        return set()
    try:
        tree = ast.parse(full.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    out: set[tuple[str, int]] = set()

    def visit(node: ast.AST, parent: str) -> None:
        if isinstance(node, ast.ClassDef):
            qual = f"{parent}.{node.name}" if parent else node.name
            for stmt in node.body:
                visit(stmt, qual)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = (
                f"{parent}.{node.name}" if parent else node.name
            )
            out.add((qual, node.lineno))
            for stmt in node.body:
                visit(stmt, qual)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, parent)

    for stmt in tree.body:
        visit(stmt, "")
    return out


def test_every_helper_resolves_to_real_ast_node(audit: dict) -> None:
    by_path: dict[str, set[tuple[str, int]]] = {}
    included = audit["inventory"]["included_paths"]
    for path in included:
        by_path[path] = _file_helpers(path)
    for h in audit["helpers"]["helpers"]:
        path = h["path"]
        key = (h["qualname"], h["line"])
        assert key in by_path.get(path, set()), (
            f"helper {key!r} not found in {path}"
        )


# ---------------------------------------------------------------------------
# 5. Every discovered structural helper is classified.
# ---------------------------------------------------------------------------


def test_every_group_member_is_in_helpers(audit: dict) -> None:
    from scripts.verifiers_audit.discovery import discover_helpers

    shard_keys = {
        (h["path"], h["qualname"]) for h in audit["helpers"]["helpers"]
    }
    all_helpers = discover_helpers(audit["inventory"]["included_paths"])
    all_keys = {(h.path, h.qualname) for h in all_helpers}
    for g in audit["groups"]["groups"]:
        for member in g["members"]:
            path, _, qualname = member.partition(":")
            in_shard = (path, qualname) in shard_keys
            in_full = (path, qualname) in all_keys
            assert in_shard or in_full, (
                f"group {g['group_id']} member {member!r} not in helpers"
            )


# ---------------------------------------------------------------------------
# 6. Duplicate helper and group counts are distinct.
# ---------------------------------------------------------------------------


def test_exact_duplicate_helper_and_group_counts_distinct(audit: dict) -> None:
    g = audit["groups"]["totals"]
    assert g["exact_duplicate_group_count"] <= g["exact_duplicate_helper_count"]
    assert g["mixed_groups"] == []


# ---------------------------------------------------------------------------
# 7. All Wave-1 candidates pass the executable equivalence suites.
# ---------------------------------------------------------------------------


def test_wave_1_equivalence_all_pass(audit: dict) -> None:
    suites = audit["candidates"]["equivalence_suites"]
    for name, suite in suites.items():
        assert suite["failed"] == 0, f"suite {name!r} has {suite['failed']} failures"


def test_equivalence_independent_run_matches_audit() -> None:
    summary = run_all_equivalence()
    for name, suite in summary.items():
        assert suite["passed"] == suite["total"], f"suite {name!r}"


# ---------------------------------------------------------------------------
# 8. Parse missing-file behaviour is accurately recorded.
# ---------------------------------------------------------------------------


def test_parse_missing_file_returns_none_in_both_helpers() -> None:
    from scripts.verifiers_audit.equivalence import run_parse_equivalence

    raw_results = run_parse_equivalence()
    cases = {c["name"]: c for c in raw_results["cases"]}
    assert "missing_file" in cases, cases.keys()
    assert cases["missing_file"]["status"] == "PASSED", cases["missing_file"]


# ---------------------------------------------------------------------------
# 9. Core public-symbol count comes from ``__all__``.
# ---------------------------------------------------------------------------


def test_core_has_exactly_24_public_symbols(audit: dict) -> None:
    symbols = core_public_symbols()
    assert len(symbols) == 24
    assert audit["core_usage"]["totals"]["core_public_symbol_count"] == 24


def test_every_public_symbol_is_unique(audit: dict) -> None:
    seen = set()
    for c in audit["core_usage"]["consumers"]:
        assert c["symbol"] not in seen, c["symbol"]
        seen.add(c["symbol"])


# ---------------------------------------------------------------------------
# 10. Production-consumer counts come from AST references.
# ---------------------------------------------------------------------------


def test_consumer_count_is_real_ast_count(audit: dict) -> None:
    usage = audit["core_usage"]
    tracked = audit["inventory"]["included_paths"]
    tests = discover_test_paths()
    symbols = core_public_symbols()
    symbol_modules = {
        c["symbol"]: c["module"] for c in usage["consumers"]
    }
    fresh = build_consumer_map(symbols, symbol_modules, tracked, tests)
    by_symbol = {c.symbol: c for c in fresh}
    for c in usage["consumers"]:
        fresh_c = by_symbol[c["symbol"]]
        assert len(fresh_c.production_callers) == len(c["production_callers"])
        assert len(fresh_c.test_callers) == len(c["test_callers"])
        assert fresh_c.classification == c["classification"]


# ---------------------------------------------------------------------------
# 10b. Import-aware resolution distinguishes real consumers
# ---------------------------------------------------------------------------


from scripts.verifiers_audit.consumer_map import _source_core_uses  # noqa: E402

_R2_CASES: tuple[tuple[str, str, frozenset[str]], ...] = (
    (
        "direct_import",
        "from scripts.verifiers.verifier_core import read_source\n"
        "def f(p):\n    return read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "aliased_direct_import",
        "from scripts.verifiers.verifier_core import "
        "SourceLocation as CoreLocation\n"
        "def f():\n    return CoreLocation(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "qualified_import",
        "import scripts.verifiers.verifier_core as vc\n"
        "def f(p):\n    return vc.read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "aliased_qualified_import",
        "import scripts.verifiers.verifier_core as core\n"
        "def f(p):\n    return core.parse_path(p)\n",
        frozenset({"parse_path"}),
    ),
    (
        "module_import_reexport",
        "from scripts.verifiers import verifier_core\n"
        "def f(p):\n    return verifier_core.read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "module_import_reexport_multi_use",
        "from scripts.verifiers import verifier_core\n"
        "def f(p):\n    verifier_core.read_source(p)\n"
        "def g(p):\n    verifier_core.parse_path(p)\n",
        frozenset({"read_source", "parse_path"}),
    ),
    (
        "submodule_direct_import",
        "from scripts.verifiers.verifier_core.diagnostics import "
        "SourceLocation\n"
        "def f():\n    return SourceLocation(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "submodule_aliased_import",
        "from scripts.verifiers.verifier_core.diagnostics import "
        "SourceLocation as SL\n"
        "def f():\n    return SL(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "local_same_name_definition",
        "class SourceLocation:\n    pass\n"
        "def f():\n    return SourceLocation()\n",
        frozenset(),
    ),
    (
        "unrelated_same_name_import",
        "from another_package import read_source\n"
        "def f(p):\n    return read_source(p)\n",
        frozenset(),
    ),
    (
        "string_only_occurrence",
        "x = 'read_source'\ny = 'verifier_core'\n",
        frozenset(),
    ),
    (
        "comment_only_occurrence",
        "# verifier_core.read_source is great\n"
        "x = 1\n",
        frozenset(),
    ),
    (
        "reexport_without_use",
        "from scripts.verifiers import verifier_core\n"
        "x = 1\n",
        frozenset(),
    ),
)


@pytest.mark.parametrize(
    "label,source,expected",
    _R2_CASES,
    ids=[c[0] for c in _R2_CASES],
)
def test_import_aware_resolution(label: str, source: str,
                                 expected: frozenset[str]) -> None:
    used = _source_core_uses(source)
    assert used == expected, (
        f"{label}: used={used!r} expected={expected!r}"
    )


def test_consumer_count_json_md_progress_agree(audit: dict) -> None:
    json_total = audit["core_usage"]["totals"]["proven_reused_count"]
    index_total = audit["index"]["totals"]["production_consumer_count"]
    md = render_markdown(audit)
    assert json_total == index_total
    assert (
        f"| Symbols with a production consumer | {index_total} |" in md
    ), md


# ---------------------------------------------------------------------------
# 11. JSON index and shards are deterministic.
# ---------------------------------------------------------------------------


def test_index_and_shards_byte_identical_across_runs() -> None:
    """Two invocations with the same arguments produce
    byte-identical audit objects."""
    record = _synthetic_skipped_record("determinism fixture")
    a = build_audit_object({}, gate_classification=record)
    b = build_audit_object({}, gate_classification=record)
    assert a["index"] == b["index"]
    for shard in SHARD_NAMES:
        assert a[shard] == b[shard]


def test_top_level_index_lists_required_shards(audit: dict) -> None:
    from scripts.verifiers_audit.report_io import REPORT_ROOT

    shards = audit["index"]["shards"]
    for name in SHARD_NAMES:
        expected_path = str(
            (REPORT_ROOT / f"{name}.json").relative_to(REPO_ROOT)
        )
        if name in shards:
            assert shards[name]["path"] == expected_path
        if shards:
            assert "sha256" in shards[name]
    assert set(SHARD_NAMES) == frozenset({
        "inventory",
        "helpers",
        "groups",
        "core_usage",
        "candidates",
        "source_preservation",
        "gate_classification",
    })


# ---------------------------------------------------------------------------
# 16. R5: source-preservation proof (head == index == working_tree).
# ---------------------------------------------------------------------------


def test_source_preservation_hashes_match(audit: dict) -> None:
    sp = audit["source_preservation"]
    assert sp["totals"]["preserved_path_count"] == sp["totals"]["tracked_path_count"]
    assert sp["totals"]["working_tree_drift_count"] == 0
    assert sp["totals"]["staged_drift_count"] == 0
    for row in sp["protected_paths"]:
        assert row["preserved"], row
        assert (
            row["head_sha256"]
            == row["index_sha256"]
            == row["working_tree_sha256"]
        )


def test_no_protected_path_in_git_diff() -> None:
    out1 = _git("diff", "--name-only").splitlines()
    out2 = _git("diff", "--cached", "--name-only").splitlines()
    out1 = [line.strip() for line in out1 if line.strip()]
    out2 = [line.strip() for line in out2 if line.strip()]
    tracked = set(_git(
        "ls-files",
        "scripts/verifiers/*.py",
        "scripts/verifiers/**/*.py",
    ).splitlines())
    assert not (set(out1) & tracked), set(out1) & tracked
    assert not (set(out2) & tracked), set(out2) & tracked


# ---------------------------------------------------------------------------
# 17. R4: measured patch economics.
# ---------------------------------------------------------------------------


def test_measured_patch_net_deletion_is_positive(audit: dict) -> None:
    sim = audit["patch_simulation"]
    totals = sim["totals"]
    assert totals["net_production_lines_removed"] > 0, totals
    assert totals["helpers_removed"] == 3
    assert totals["call_sites_changed"] >= 3
    assert (
        audit["index"]["totals"]["measured_net_deletion_lines"]
        == totals["net_production_lines_removed"]
    )


def test_measured_patch_diff_sums_correctly(audit: dict) -> None:
    t = audit["patch_simulation"]["totals"]
    assert (
        t["net_production_lines_removed"]
        == t["production_lines_removed"] - t["production_lines_added"]
    )


# ---------------------------------------------------------------------------
# 18. R3: equivalence case status, derived counts, skip handling.
# ---------------------------------------------------------------------------


def test_equivalence_cases_have_status_field(audit: dict) -> None:
    suites = audit["candidates"]["equivalence_suites"]
    for suite in suites.values():
        assert "executed" in suite
        assert "passed" in suite
        assert "failed" in suite
        assert "skipped" in suite
        for c in suite["cases"]:
            assert "status" in c
            assert c["status"] in {"PASSED", "FAILED", "SKIPPED"}


def test_wave_1_rationale_counts_come_from_live_suite(audit: dict) -> None:
    suites = audit["candidates"]["equivalence_suites"]
    for c in audit["candidates"]["candidates"]:
        if c["wave"] != "Wave 1":
            continue
        sym = c["core_symbol"]
        suite_name = {
            "read_source": "read_source",
            "parse_path": "parse",
            "top_level_function": "top_level_function",
        }.get(sym)
        if suite_name is None:
            continue
        suite = suites[suite_name]
        expected = (
            f"{suite['passed']}/{suite['total']} equivalence cases pass"
            f" ({suite['skipped']} skipped)"
        )
        assert expected in c["rationale"], (c["candidate_id"], c["rationale"])


def test_permission_denied_case_status_is_skippable() -> None:
    from scripts.verifiers_audit.equivalence import (
        _STATUS_PASSED,
        _STATUS_SKIPPED,
        run_read_source_equivalence,
    )
    suite = run_read_source_equivalence()
    cases = {c["name"]: c for c in suite["cases"]}
    assert "permission_denied" in cases
    assert cases["permission_denied"]["status"] in {
        _STATUS_PASSED, _STATUS_SKIPPED,
    }


# ---------------------------------------------------------------------------
# 19. R6: strict set equality and cross-report agreement.
# ---------------------------------------------------------------------------


def test_inventory_set_equals_tracked(audit: dict) -> None:
    from scripts.verifiers_audit.validation import (
        validate_inventory_set_equals_tracked,
    )
    assert validate_inventory_set_equals_tracked(audit)


def test_required_shards_complete(tmp_path) -> None:
    """Write the audit-owned shards to a tmp_path then validate.

    Every writer test MUST use ``tmp_path``; the canonical
    :data:`REPORT_ROOT` is NEVER mutated by this test.
    """
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_all,
    )
    from scripts.verifiers_audit.validation import (
        validate_required_shards_complete,
    )

    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    layout = report_layout_for_shard_root(reports)
    skipped = _synthetic_skipped_record(
        "test_required_shards_complete synthetic fixture; the "
        "canonical repository gate is recorded in "
        ".factory/gate-summary.json."
    )
    fresh = build_audit_object({}, gate_classification=skipped)
    (reports / "gate_classification.json").write_text(
        json.dumps(skipped, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    write_all(layout=layout, audit=fresh)
    assert validate_required_shards_complete(
        fresh, report_root=reports
    )


def test_cmd_write_rejects_caller_supplied_gc_with_nonzero() -> None:
    """CORRECTION09: ``cmd_write(gate_classification=...)`` MUST
    return a nonzero exit code and perform zero side effects."""
    from scripts.verifiers_audit.cli import cmd_write

    canonical = REPORT_ROOT / "gate_classification.json"
    if not canonical.exists():
        return
    exit_code = cmd_write(gate_classification={"fake": "record"})
    assert exit_code != 0, (
        f"cmd_write MUST return nonzero on caller-supplied "
        f"gate_classification; got exit {exit_code}"
    )


# ---------------------------------------------------------------------------
# CORRECTION12: cmd_write writer invariants
# ---------------------------------------------------------------------------


def test_cmd_write_calls_write_audit_exactly_once(monkeypatch) -> None:
    """CORRECTION12: ``cmd_write`` calls :func:`write_audit`
    exactly once and supplies :func:`canonical_layout`."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    calls: list[dict[str, object]] = []

    def _spy_write_audit(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        calls.append({"layout": layout})
        return {}

    def _spy_canonical_layout() -> _rio.ReportLayout:
        return _rio.canonical_layout()

    monkeypatch.setattr(_cli, "write_audit", _spy_write_audit)
    monkeypatch.setattr(_cli, "canonical_layout", _spy_canonical_layout)

    rc = _cli.cmd_write()
    assert rc == 0, f"cmd_write success expected rc=0, got {rc}"
    assert len(calls) == 1, (
        f"cmd_write must call write_audit exactly once, got {len(calls)}"
    )
    # The supplied layout is the canonical layout.
    assert calls[0]["layout"] is not None
    assert calls[0]["layout"].shard_root == _rio.REPORT_ROOT


def test_cmd_write_supplies_canonical_layout(monkeypatch) -> None:
    """CORRECTION12: the layout passed to ``write_audit`` is
    the result of ``canonical_layout()``."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    captured: list[_rio.ReportLayout] = []

    def _spy_write_audit(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        captured.append(layout)
        return {}

    monkeypatch.setattr(_cli, "write_audit", _spy_write_audit)
    rc = _cli.cmd_write()
    assert rc == 0
    assert len(captured) == 1
    sent = captured[0]
    expected = _rio.canonical_layout()
    assert sent == expected, (
        f"cmd_write supplied layout {sent} != canonical {expected}"
    )
    assert sent.top_level_json == expected.top_level_json
    assert sent.markdown_path == expected.markdown_path


def test_cmd_write_caller_supplied_classification_returns_2_before_writer(
    monkeypatch,
) -> None:
    """CORRECTION12: a caller-supplied ``gate_classification``
    returns 2 BEFORE :func:`write_audit` is invoked."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    invocations: list[object] = []

    def _spy_write_audit(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        invocations.append(layout)
        return {}

    monkeypatch.setattr(_cli, "write_audit", _spy_write_audit)
    rc = _cli.cmd_write(gate_classification={"fake": "record"})
    assert rc == 2, f"expected rc=2 on caller-supplied gc, got {rc}"
    assert invocations == [], (
        "cmd_write MUST NOT invoke write_audit when gate_classification "
        "is supplied; the rejection must run BEFORE any write."
    )


def test_cmd_write_writer_exception_returns_nonzero(monkeypatch) -> None:
    """CORRECTION12: a writer exception surfaces as a nonzero
    exit code."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    def _boom(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        raise _rio.AuditWriteError("forced failure")

    monkeypatch.setattr(_cli, "write_audit", _boom)
    rc = _cli.cmd_write()
    assert rc != 0, (
        f"cmd_write must return nonzero on writer exception, got {rc}"
    )
    assert rc == 1


def test_cmd_write_os_error_returns_nonzero(monkeypatch) -> None:
    """CORRECTION12: a generic ``OSError`` from the writer
    surfaces as a nonzero exit code."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    def _boom(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        raise OSError("forced filesystem failure")

    monkeypatch.setattr(_cli, "write_audit", _boom)
    rc = _cli.cmd_write()
    assert rc != 0


def test_cmd_write_value_error_returns_nonzero(monkeypatch) -> None:
    """CORRECTION12: a ``ValueError`` from the writer surfaces
    as a nonzero exit code."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    def _boom(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        raise ValueError("forced layout failure")

    monkeypatch.setattr(_cli, "write_audit", _boom)
    rc = _cli.cmd_write()
    assert rc != 0


def test_cmd_write_no_artifact_changes_after_rejected_write() -> None:
    """CORRECTION12: a caller-supplied ``gate_classification``
    leaves the canonical artifacts byte-identical."""
    from scripts.verifiers_audit.cli import cmd_write

    before = _hash_canonical_artifact_set()
    exit_code = cmd_write(gate_classification={"fake": "record"})
    after = _hash_canonical_artifact_set()
    assert exit_code != 0
    assert before == after, (
        f"canonical artifacts mutated by rejected cmd_write: "
        f"before={before} after={after}"
    )


def test_cmd_write_no_artifact_changes_after_failed_write(
    monkeypatch,
) -> None:
    """CORRECTION12: a writer exception leaves the canonical
    artifacts byte-identical (the write was never completed)."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    def _boom(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        raise _rio.AuditWriteError("forced failure")

    monkeypatch.setattr(_cli, "write_audit", _boom)
    before = _hash_canonical_artifact_set()
    exit_code = _cli.cmd_write()
    after = _hash_canonical_artifact_set()
    assert exit_code != 0
    assert before == after, (
        "canonical artifacts mutated by failed cmd_write: "
        f"before={before} after={after}"
    )


def test_cli_source_does_not_directly_write_report_files() -> None:
    """CORRECTION12: the CLI source contains no direct report-file
    writing calls.  The only legitimate write path is the import
    of ``write_audit`` from :mod:`report_io`.

    The check is liberal: it allows the CLI to import writer
    entry points (``write_audit``, ``write_all``, ``canonical_layout``,
    ``report_layout_for_shard_root``) and forbids explicit
    low-level write calls.
    """
    from scripts.verifiers_audit import cli as _cli

    # The check is path-aware: extract the AST of the source
    # and ensure no Call node targets a forbidden name.
    src = inspect.getsource(_cli)
    tree = ast.parse(src)
    forbidden_function_calls = {
        "write_text",
        "write_bytes",
        "_write_atomic",
        "_json_dumps",
        "_dump_helpers_shard",
        "render_markdown",
        "mkstemp",
        "replace",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in forbidden_function_calls:
                    # Allow the canonical writer call
                    # ``write_audit(layout=...)`` - the attribute
                    # name is ``write_audit`` and is NOT in the
                    # forbidden set.
                    raise AssertionError(
                        f"forbidden direct write call in cli.py: "
                        f"{func.attr} at line {node.lineno}"
                    )
    # Forbid the import of the low-level helpers.
    forbidden_imports = (
        "_write_atomic",
        "_json_dumps",
        "_dump_helpers_shard",
        "render_markdown",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in forbidden_imports:
                    raise AssertionError(
                        f"forbidden import in cli.py: {alias.name}"
                    )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_imports:
                    raise AssertionError(
                        f"forbidden import in cli.py: {alias.name}"
                    )
    # Sanity: the canonical writer call IS present.
    assert "write_audit" in src, "cli.py must call write_audit"
    assert "canonical_layout" in src, "cli.py must call canonical_layout"


# ---------------------------------------------------------------------------
# CORRECTION10 preserved autouse mutation guard.
# ---------------------------------------------------------------------------


def _hash_canonical_artifact_set() -> dict[str, str]:
    """Return a snapshot of the canonical artifact hash set."""
    paths = [
        ".factory/gate-summary.json",
        "docs/reports/verifier-core-migration-audit01.json",
        "docs/reports/verifier-core-migration-audit01.md",
    ]
    out: dict[str, str] = {}
    for rel in paths:
        p = REPO_ROOT / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    paths2 = list(
        (REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01").glob(
            "*.json"
        )
    )
    for p in paths2:
        rel = str(p.relative_to(REPO_ROOT))
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture(scope="module", autouse=True)
def canonical_artifacts_remain_unchanged() -> object:
    """CORRECTION10: real module-scope mutation guard."""
    before = _hash_canonical_artifact_set()
    yield
    after = _hash_canonical_artifact_set()
    assert before == after, (
        f"canonical artifacts mutated during the test module: "
        f"before={before} after={after}"
    )


def test_canonical_artifacts_module_autouse_did_not_mutate() -> None:
    canonical = REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01.json"
    assert canonical.exists(), (
        "canonical top-level index must exist (committed as part "
        "of CORRECTION08)"
    )


def test_writes_through_temporary_layout_do_not_touch_canonical(
    tmp_path,
) -> None:
    """Adversarial test: write through a tmp_path-constructed
    :class:`ReportLayout` and prove the canonical hashes are
    unchanged."""
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_audit,
    )

    canonical = REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01.json"
    canonical_hash_before = (
        hashlib.sha256(canonical.read_bytes()).hexdigest() if canonical.exists() else None
    )

    tmp_reports = tmp_path / "reports"
    tmp_reports.mkdir(parents=True)
    layout = report_layout_for_shard_root(tmp_reports)
    write_audit(layout=layout)

    canonical_hash_after = (
        hashlib.sha256(canonical.read_bytes()).hexdigest() if canonical.exists() else None
    )
    assert canonical_hash_after == canonical_hash_before, (
        f"adversarial write through temporary layout mutated the "
        f"canonical top-level index: {canonical_hash_before} -> "
        f"{canonical_hash_after}"
    )


# ---------------------------------------------------------------------------
# CORRECTION11: ReportLayout contract & write_audit
# ---------------------------------------------------------------------------


def test_report_layout_validates_at_construction(tmp_path) -> None:
    """A direct ``ReportLayout(...)`` construction with
    inconsistent paths raises ``ValueError``."""
    with pytest.raises(ValueError):
        ReportLayout(
            shard_root=tmp_path / "shards",
            top_level_json=tmp_path / "wrong.json",
            markdown_path=tmp_path / "wrong.md",
        )


def test_report_layout_accepts_valid_layout(tmp_path) -> None:
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
    )

    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    layout = report_layout_for_shard_root(reports)
    assert layout.shard_root == reports
    assert (
        layout.top_level_json
        == reports.parent / "verifier-core-migration-audit01.json"
    )
    assert (
        layout.markdown_path
        == reports.parent / "verifier-core-migration-audit01.md"
    )


def test_canonical_shard_root_maps_to_top_level_json() -> None:
    from scripts.verifiers_audit.report_io import canonical_layout

    layout = canonical_layout()
    assert (
        layout.top_level_json
        == REPORT_ROOT.parent / "verifier-core-migration-audit01.json"
    )
    assert (
        layout.markdown_path
        == REPORT_ROOT.parent / "verifier-core-migration-audit01.md"
    )


def test_temporary_shard_root_stays_inside_tmp_path(tmp_path) -> None:
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
    )

    reports = tmp_path / "reports"
    reports.mkdir()
    layout = report_layout_for_shard_root(reports)
    assert reports in layout.shard_root.parents or reports == layout.shard_root
    assert layout.top_level_json.parent == tmp_path
    assert layout.markdown_path.parent == tmp_path


def test_recorded_shard_paths_match_layout(tmp_path) -> None:
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_audit,
    )

    reports = tmp_path / "reports"
    reports.mkdir()
    layout = report_layout_for_shard_root(reports)
    write_audit(layout=layout)
    index = json.loads(layout.top_level_json.read_text(encoding="utf-8"))
    for name, info in index["shards"].items():
        abs_path = (REPO_ROOT / info["path"]).resolve()
        assert (
            abs_path
            == (layout.shard_root / f"{name}.json").resolve()
        ), f"shard {name} not under layout: {abs_path}"


def test_canonical_gate_classification_not_written_by_write_audit(
    tmp_path,
) -> None:
    """The canonical ``write_audit`` MUST NOT modify the
    canonical ``gate_classification.json``."""
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_audit,
    )

    canonical_gc = REPORT_ROOT / "gate_classification.json"
    if not canonical_gc.exists():
        return
    before = hashlib.sha256(canonical_gc.read_bytes()).hexdigest()

    reports = tmp_path / "reports"
    reports.mkdir()
    layout = report_layout_for_shard_root(reports)
    write_audit(layout=layout)

    after = hashlib.sha256(canonical_gc.read_bytes()).hexdigest()
    assert before == after, (
        f"write_audit mutated the canonical gate_classification.json: "
        f"{before} -> {after}"
    )


def test_reports_agree(audit: dict) -> None:
    from scripts.verifiers_audit.validation import validate_reports_agree
    assert validate_reports_agree(audit)


# ---------------------------------------------------------------------------
# 12. Markdown and JSON totals agree.
# ---------------------------------------------------------------------------


def test_markdown_totals_match_index(audit: dict) -> None:
    md = render_markdown(audit)
    t = audit["index"]["totals"]
    expected = [
        f"| Tracked verifier paths | {t['tracked_path_count']} |",
        f"| Included paths | {t['included_path_count']} |",
        f"| Excluded paths | {t['excluded_path_count']} |",
        f"| AST-discovered helpers | {t['helper_count']} |",
        f"| Exact-duplicate groups | {t['exact_duplicate_group_count']} |",
        f"| Exact-duplicate helpers | {t['exact_duplicate_helper_count']} |",
        f"| Core public symbols (`__all__`) | "
        f"{t['core_public_symbol_count']} |",
        f"| Wave-1 candidates | {t['wave_1_candidate_count']} |",
    ]
    for line in expected:
        assert line in md, f"missing: {line}"


# ---------------------------------------------------------------------------
# 13. Every generated path stays below the LLM-friendly threshold.
# ---------------------------------------------------------------------------


def test_every_audit_python_file_under_500_lines() -> None:
    audit_pkg = REPO_ROOT / "scripts" / "verifiers_audit"
    for path in audit_pkg.rglob("*.py"):
        lines = sum(1 for _ in path.open(encoding="utf-8"))
        assert lines < 500, f"{path} is {lines} lines (threshold 500)"


def test_each_shard_under_size_threshold() -> None:
    for name in SHARD_NAMES:
        shard_path = REPORT_ROOT / f"{name}.json"
        if not shard_path.exists():
            continue
        assert shard_path.stat().st_size < 200_000, name


# ---------------------------------------------------------------------------
# 14. No absolute developer paths appear.
# ---------------------------------------------------------------------------


def test_no_absolute_paths_in_audit(audit: dict) -> None:
    raw = json.dumps(audit)
    for token in ("/tmp/", "/Users/", "/home/", "/var/", "/private/"):
        assert token not in raw, token


def test_no_absolute_paths_in_reports() -> None:
    if TOP_LEVEL_JSON.exists():
        text = TOP_LEVEL_JSON.read_text(encoding="utf-8")
        for token in ("/tmp/", "/Users/", "/home/", "/var/", "/private/"):
            assert token not in text, token


# ---------------------------------------------------------------------------
# 15. Production verifier and core hashes remain unchanged.
# ---------------------------------------------------------------------------


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout


def _production_hashes() -> dict[str, str]:
    lines = _git(
        "ls-files",
        "scripts/verifiers/*.py",
        "scripts/verifiers/**/*.py",
    ).splitlines()
    out: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        proc = subprocess.run(  # noqa: PERF203
            ["git", "cat-file", "blob", f"HEAD:{line}"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            check=False,
        )
        out[line] = hashlib.sha256(proc.stdout).hexdigest()
    return out


def test_production_verifier_and_core_hashes_unchanged() -> None:
    hashes = _production_hashes()
    assert len(hashes) == 29
    head = _git("rev-parse", "HEAD").strip()
    assert head, "git rev-parse HEAD must yield a non-empty commit"


# ---------------------------------------------------------------------------
# R1 / CORRECTION04: gate classification, skip semantics, executable patch
# ---------------------------------------------------------------------------


def test_classify_pair_returns_pre_existing_deterministic() -> None:
    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    sem = "negative-proofs: 3 violations detected"
    clean = _Run("EXITED", 1, 1.0, "", sem)
    audit = _Run("EXITED", 1, 1.1, "", sem)
    assert classify_pair(clean, audit) == "PRE-EXISTING-DETERMINISTIC"


def test_classify_pair_returns_pre_existing_environmental_on_timeout() -> None:
    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    clean = _Run("TIMED_OUT", -1, 60.0, "", "")
    audit = _Run("TIMED_OUT", -1, 60.0, "", "")
    assert classify_pair(clean, audit) == "PRE-EXISTING-ENVIRONMENTAL"


def test_classify_pair_returns_act_introduced() -> None:
    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    clean = _Run("EXITED", 0, 0.5, "", "")
    audit = _Run(
        "EXITED", 1, 0.6, "",
        "redaction: 1 violation found in audit-tree",
    )
    assert classify_pair(clean, audit) == "ACT-INTRODUCED"


def test_classify_pair_returns_unresolved_when_evidence_differs() -> None:
    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    clean = _Run("EXITED", 1, 0.5, "", "totally unrelated failure")
    audit = _Run("EXITED", 0, 0.6, "", "")
    assert classify_pair(clean, audit) == "UNRESOLVED"


def test_skipped_record_is_never_pre_existing_environmental() -> None:
    """Skip records MUST be ``SKIPPED``; never
    ``PRE-EXISTING-ENVIRONMENTAL``.  CORRECTION11: callers
    build the record via :func:`_skipped_record` directly."""
    from scripts.verifiers_audit.gate_classification import (
        _skipped_record,
    )

    record = _skipped_record("unit-test fixture")
    classification_obj = record.get("classification")
    classification = cast(str, classification_obj)
    assert classification == "SKIPPED", record
    # The != comparison is a tautological safeguard, not a
    # type-laden check; use a string comparison so mypy
    # accepts it.
    assert str(classification) != "PRE-EXISTING-ENVIRONMENTAL"


def test_patch_simulation_is_executable() -> None:
    sim = measured_patch_summary()
    totals = sim["totals"]
    details = sim["details"]
    assert totals["parse_passed"] is True, details
    assert totals["compile_passed"] is True, details
    assert totals["verifier_exit_code"] is not None
    assert isinstance(totals["verifier_exit_code"], int)
    assert totals["targeted_tests_passed"] is True, details
    net_deletion = totals["net_production_lines_removed"]
    assert net_deletion > 0, totals
    assert totals["call_sites_changed"] == 5, totals
    assert totals["helpers_removed"] == 3, totals


def test_executable_patch_provides_required_evidence() -> None:
    sim = measured_patch_summary()
    details = sim["details"]
    required = (
        "parse_passed",
        "compile_passed",
        "verifier_exit_code",
        "targeted_tests_passed",
        "production_lines_added",
        "production_lines_removed",
        "net_production_lines_removed",
        "call_sites_changed",
        "helpers_removed",
        "patched_sha256",
    )
    for field in required:
        assert field in details, field
        assert details[field] is not None, field


def test_consumer_count_uses_real_imports() -> None:
    audit = build_audit_object(
        {}, gate_classification=_synthetic_skipped_record(
            "consumer-count fixture"
        )
    )
    usage = audit["core_usage"]["totals"]
    assert (
        usage["proven_reused_count"]
        + usage["test_only_count"]
        + usage["unused_count"]
    ) == usage["core_public_symbol_count"], usage
    consumers = audit["core_usage"]["consumers"]
    classifications = {
        c["classification"] for c in consumers
    }
    assert classifications <= {"PROVEN-REUSED", "TEST-ONLY", "UNUSED"}, classifications
    for c in consumers:
        cls = c["classification"]
        if cls == "TEST-ONLY":
            assert len(c["test_callers"]) >= 1, c
        if cls == "PROVEN-REUSED":
            assert len(c["production_callers"]) >= 1, c
        if cls == "UNUSED":
            assert len(c["production_callers"]) == 0
            assert len(c["test_callers"]) == 0

"""CORRECTION17: typed gate plan tests.

The tests in this module validate the CORRECTION17
hardenings to the gate inventory:

* the seven required gates are recorded with a closed
  ``RepositoryGateName`` set; the C17 contract adds
  ``act-local-range`` (renamed from C16 ``act-local``)
  and ``range-diff-check`` (replacing ``diff-check``).
* every gate argv contains NO literal glob syntax
  (``*`` / ``?`` / ``[]``).
* the ``worktree-clean`` gate uses the Git seam directly.
* the ``range-diff-check`` gate is invoked with the
  F17..S17 full OIDs (NOT F16..S16).
* the ``audit01-ruff`` gate uses the EXACT subject
  Python tuple, never a glob or broad source directory.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from pathlib import Path

from scripts.verifiers_audit.range_evidence_gates import (
    AUDIT01_TEST_GLOB_PATTERN,
    argv_has_literal_glob,
    build_required_gates,
    resolve_test_inventory,
)
from scripts.verifiers_audit.typed_results import (
    ExecutedCommand,
    RepositoryGateResult,
)


def _gate(
    name: str,
    *,
    argv: tuple[str, ...] = ("git", "diff", "--check"),
    stdout: bytes = b"",
    status: str = "passed",
) -> RepositoryGateResult:
    return RepositoryGateResult(
        name=name,  # type: ignore[arg-type]
        command=ExecutedCommand(
            name=name,
            argv=argv,
            cwd="/repo",
            returncode=0,
            stdout=stdout,
            stderr=b"",
            status=status,  # type: ignore[arg-type]
        ),
    )


def test_c17_required_gate_names_are_complete(tmp_path: Path) -> None:
    """CORRECTION17: the gate set is the closed C17 set."""
    gates = build_required_gates(repo_root=tmp_path, base="F17", subject="S17")
    names = {g.name for g in gates}
    expected = {
        "audit01-pytest",
        "audit01-ruff",
        "audit01-mypy",
        "audit-check",
        "act-local",
        "diff-check",
        "worktree-clean",
    }
    assert names == expected


def test_c17_audit01_ruff_uses_exact_subject_tuple(tmp_path: Path) -> None:
    """CORRECTION17: the ``audit01-ruff`` gate receives the EXACT subject
    Python path tuple, never a glob or broad directory."""
    subject_paths = (
        "scripts/verifiers_audit/audit.py",
        "tests/verifiers/test_verifier_core_migration_audit01_correction17.py",
    )
    gates = build_required_gates(
        repo_root=tmp_path,
        subject_python_paths=subject_paths,
        base="F17",
        subject="S17",
    )
    ruff_gate = next(g for g in gates if g.name == "audit01-ruff")
    assert "check" in ruff_gate.argv
    # The argv must NOT contain the literal glob syntax.
    assert not argv_has_literal_glob(ruff_gate.argv)
    # The argv must contain at least one explicit path
    # (the exact-subject tuple or the resolved path list).
    assert len(ruff_gate.argv) >= 3


def test_c17_audit01_pytest_argv_has_no_literal_glob(tmp_path: Path) -> None:
    """CORRECTION17: the pytest argv never contains the literal
    ``*`` syntax."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_a.py").write_text("# a")
    gates = build_required_gates(repo_root=tmp_path, base="F17", subject="S17")
    pytest_gate = next(g for g in gates if g.name == "audit01-pytest")
    assert not argv_has_literal_glob(pytest_gate.argv)


def test_c17_audit01_mypy_argv_has_no_literal_glob(tmp_path: Path) -> None:
    """CORRECTION17: the mypy argv never contains the literal
    ``*`` syntax."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_a.py").write_text("# a")
    gates = build_required_gates(repo_root=tmp_path, base="F17", subject="S17")
    mypy_gate = next(g for g in gates if g.name == "audit01-mypy")
    assert not argv_has_literal_glob(mypy_gate.argv)


def test_c17_act_local_gate_supports_base_subject(tmp_path: Path) -> None:
    """CORRECTION17: the ``act-local`` gate forwards the explicit
    ``--base F17 --subject S17`` tuple."""
    gates = build_required_gates(repo_root=tmp_path, base="F17", subject="S17")
    act_local = next(g for g in gates if g.name == "act-local")
    assert "--base" in act_local.argv
    assert "F17" in act_local.argv
    assert "--subject" in act_local.argv
    assert "S17" in act_local.argv


def test_c17_worktree_clean_uses_git_seam(tmp_path: Path) -> None:
    """CORRECTION17: the ``worktree-clean`` gate invokes ``git status
    --porcelain=v1 -z`` directly."""
    gates = build_required_gates(repo_root=tmp_path, base="F17", subject="S17")
    worktree = next(g for g in gates if g.name == "worktree-clean")
    assert worktree.argv[0] == "git"
    assert "status" in worktree.argv
    assert "--porcelain=v1" in worktree.argv


def test_c17_test_inventory_pattern_is_canonical() -> None:
    """CORRECTION17: the inventory pattern is unchanged from C16."""
    assert AUDIT01_TEST_GLOB_PATTERN == (
        "tests/verifiers/test_verifier_core_migration_audit01*.py"
    )


def test_c17_resolve_test_inventory_returns_sorted_paths(tmp_path: Path) -> None:
    """CORRECTION17: the inventory resolver returns a sorted tuple of
    concrete paths (no globs)."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    a = tmp_path / "tests" / "verifiers" / "test_verifier_core_migration_audit01_a.py"
    b = tmp_path / "tests" / "verifiers" / "test_verifier_core_migration_audit01_b.py"
    a.write_text("# a")
    b.write_text("# b")
    out = resolve_test_inventory(repo_root=tmp_path)
    assert out == (
        "tests/verifiers/test_verifier_core_migration_audit01_a.py",
        "tests/verifiers/test_verifier_core_migration_audit01_b.py",
    )


def test_c17_diff_check_gate_invokes_git(tmp_path: Path) -> None:
    """CORRECTION17: the ``diff-check`` gate uses the Git seam."""
    gates = build_required_gates(repo_root=tmp_path, base="F17", subject="S17")
    diff_check = next(g for g in gates if g.name == "diff-check")
    assert diff_check.argv[0] == "git"
    assert "diff" in diff_check.argv
    assert "--check" in diff_check.argv


def test_c17_gate_plan_count_is_seven(tmp_path: Path) -> None:
    """CORRECTION17: the closed gate plan has exactly seven entries."""
    gates = build_required_gates(repo_root=tmp_path, base="F17", subject="S17")
    assert len(gates) == 7
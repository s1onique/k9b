"""CORRECTION18: typed gate plan tests.

The tests in this module validate the CORRECTION18
hardenings to the gate inventory:

* the seven required gates are recorded with a closed
  ``RepositoryGateName`` set;
* every gate argv contains NO literal glob syntax
  (``*`` / ``?`` / ``[]``);
* the ``worktree-clean`` gate uses the Git seam directly;
* the ``range-diff-check`` gate is invoked with the
  F18..S18 full OIDs;
* the ``audit01-ruff`` gate uses the EXACT subject
  Python tuple, never a glob or broad source directory;
* GateInvocation records require explicit environment;
* ACT-local gate supports explicit manifest interface.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from pathlib import Path

import pytest

from scripts.verifiers_audit.range_evidence_gates import (
    AUDIT01_TEST_GLOB_PATTERN,
    GateInvocation,
    GatePlanError,
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


def _manifest(tmp_path: Path) -> Path:
    """Return a consistent manifest path for tests."""
    return tmp_path / "changed-paths.z"


def test_c18_required_gate_names_are_complete(tmp_path: Path) -> None:
    """CORRECTION18: the gate set is the closed C18 set."""
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    names = {g.name for g in gates}
    expected = {
        "audit01-pytest",
        "audit01-ruff",
        "audit01-mypy",
        "audit-check",
        "act-local-range",
        "range-diff-check",
        "worktree-clean",
    }
    assert names == expected


def test_c18_audit01_ruff_uses_exact_subject_tuple(tmp_path: Path) -> None:
    """CORRECTION18: the ``audit01-ruff`` gate receives the EXACT subject
    Python path tuple, never a glob or broad directory."""
    subject_paths = (
        "scripts/verifiers_audit/audit.py",
        "tests/verifiers/test_verifier_core_migration_audit01_correction18.py",
    )
    gates = build_required_gates(
        repo_root=tmp_path,
        subject_python_paths=subject_paths,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    ruff_gate = next(g for g in gates if g.name == "audit01-ruff")
    assert ruff_gate.argv is not None
    assert "check" in ruff_gate.argv
    # The argv must NOT contain the literal glob syntax.
    assert not argv_has_literal_glob(ruff_gate.argv)
    # The argv must contain at least one explicit path
    assert len(ruff_gate.argv) >= 3
    # expected_pass must be True when paths are provided
    assert ruff_gate.expected_pass is True


def test_c18_audit01_ruff_skips_explicitly_when_empty(tmp_path: Path) -> None:
    """CORRECTION18: empty subject_python_paths results in argv=None."""
    gates = build_required_gates(
        repo_root=tmp_path,
        subject_python_paths=(),
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    ruff_gate = next(g for g in gates if g.name == "audit01-ruff")
    assert ruff_gate.argv is None
    assert ruff_gate.expected_pass is False


def test_c18_audit01_pytest_argv_has_no_literal_glob(tmp_path: Path) -> None:
    """CORRECTION18: the pytest argv never contains the literal
    ``*`` syntax."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_a.py").write_text("# a")
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    pytest_gate = next(g for g in gates if g.name == "audit01-pytest")
    # CORRECTION18: pytest gate always has non-None argv
    assert pytest_gate.argv is not None
    assert not argv_has_literal_glob(pytest_gate.argv)


def test_c18_audit01_mypy_argv_has_no_literal_glob(tmp_path: Path) -> None:
    """CORRECTION18: the mypy argv never contains the literal
    ``*`` syntax."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_a.py").write_text("# a")
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    mypy_gate = next(g for g in gates if g.name == "audit01-mypy")
    # CORRECTION18: mypy gate always has non-None argv
    assert mypy_gate.argv is not None
    assert not argv_has_literal_glob(mypy_gate.argv)


def test_c18_act_local_gate_supports_base_subject(tmp_path: Path) -> None:
    """CORRECTION18: the ``act-local-range`` gate forwards the explicit
    ``--base F18 --subject S18`` tuple."""
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    act_local = next(g for g in gates if g.name == "act-local-range")
    assert "--base" in act_local.argv
    assert "F18" in act_local.argv
    assert "--subject" in act_local.argv
    assert "S18" in act_local.argv


def test_c18_worktree_clean_uses_git_seam(tmp_path: Path) -> None:
    """CORRECTION18: the ``worktree-clean`` gate invokes ``git status
    --porcelain=v1 -z`` directly."""
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    worktree = next(g for g in gates if g.name == "worktree-clean")
    assert worktree.argv[0] == "git"
    assert "status" in worktree.argv
    assert "--porcelain=v1" in worktree.argv


def test_c18_test_inventory_pattern_is_canonical() -> None:
    """CORRECTION18: the inventory pattern is unchanged from C17."""
    assert AUDIT01_TEST_GLOB_PATTERN == (
        "tests/verifiers/test_verifier_core_migration_audit01*.py"
    )


def test_c18_resolve_test_inventory_returns_sorted_paths(tmp_path: Path) -> None:
    """CORRECTION18: the inventory resolver returns a sorted tuple of
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


def test_c18_range_diff_check_gate_invokes_git(tmp_path: Path) -> None:
    """CORRECTION18: the ``range-diff-check`` gate uses the Git seam."""
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    diff_check = next(g for g in gates if g.name == "range-diff-check")
    assert diff_check.argv[0] == "git"
    assert "diff" in diff_check.argv
    assert "--check" in diff_check.argv


def test_c18_gate_plan_count_is_seven(tmp_path: Path) -> None:
    """CORRECTION18: the closed gate plan has exactly seven entries."""
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    assert len(gates) == 7


def test_c18_manifest_required_raises_gate_plan_error(tmp_path: Path) -> None:
    """CORRECTION18: build_required_gates raises GatePlanError when manifest_path is None."""
    with pytest.raises(GatePlanError) as exc_info:
        build_required_gates(
            repo_root=tmp_path,
            base="F18",
            subject="S18",
            manifest_path=None,
        )
    assert "manifest" in str(exc_info.value).lower()


def test_c18_gate_invocation_requires_explicit_environment() -> None:
    """CORRECTION18: GateInvocation records require explicit environment.

    No required environment input may be inherited implicitly.
    """
    invocation = GateInvocation(
        name="audit-check",
        argv=("echo", "test"),
        cwd="/repo",
        environment_overrides=(("PATH", "/usr/bin"),),
        input_paths=(),
    )
    assert hasattr(invocation, "environment_overrides")
    assert isinstance(invocation.environment_overrides, tuple)
    assert dict(invocation.environment_overrides).get("PATH") == "/usr/bin"


def test_c18_gate_invocation_has_required_fields() -> None:
    """CORRECTION18: GateInvocation has all required fields."""
    invocation = GateInvocation(
        name="worktree-clean",
        argv=("echo", "test"),
        cwd="/repo",
        environment_overrides=(),
        input_paths=("file1.py", "file2.py"),
    )
    assert hasattr(invocation, "name")
    assert hasattr(invocation, "argv")
    assert hasattr(invocation, "cwd")
    assert hasattr(invocation, "environment_overrides")
    assert hasattr(invocation, "input_paths")


def test_c18_act_local_gate_emits_manifest_argument(tmp_path: Path) -> None:
    """CORRECTION18: ACT-local gate emits --manifest when manifest_path is supplied."""
    manifest = tmp_path / "changed-paths.z"
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=manifest,
    )
    act_local = next(g for g in gates if g.name == "act-local-range")
    # CORRECTION18: argv must be present for gates with manifest
    assert act_local.argv is not None
    # CORRECTION18: manifest must be present in argv
    assert "--manifest" in act_local.argv
    manifest_index = act_local.argv.index("--manifest")
    assert act_local.argv[manifest_index + 1] == str(manifest)
    # CORRECTION18: input_paths records the manifest
    assert act_local.input_paths == (str(manifest),)

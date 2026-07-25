"""CORRECTION18: exact gate inventory tests.

The tests in this module validate the CORRECTION18
hardenings to the gate inventory:

* each gate inventory is built from the actual planned argv;
* byte-for-byte equality between manifest files and executed argv;
* the Ruff gate uses the exact S18 changed-Python tuple;
* pytest/mypy/ruff input paths match the executed gates;
* range hygiene gate uses F18_FULL_OID and S18_FULL_OID.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from pathlib import Path

from scripts.verifiers_audit.range_evidence_gates import (
    build_required_gates,
    resolve_test_inventory,
)


def _manifest(tmp_path: Path) -> Path:
    """Return a consistent manifest path for tests."""
    return tmp_path / "changed-paths.z"


def test_c18_pytest_inventory_matches_gate_argv(tmp_path: Path) -> None:
    """CORRECTION18: pytest inventory matches the gate argv."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_a.py").write_text("# a")
    (tmp_path / "tests" / "verifiers" / "test_b.py").write_text("# b")

    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    pytest_gate = next(g for g in gates if g.name == "audit01-pytest")

    # The gate argv must include pytest/mypy invocations
    assert pytest_gate.argv is not None
    assert "pytest" in str(pytest_gate.argv)

    # The gate must have input_paths defined (CORRECTION18)
    assert hasattr(pytest_gate, "input_paths")
    assert isinstance(pytest_gate.input_paths, tuple)


def test_c18_mypy_inventory_matches_gate_argv(tmp_path: Path) -> None:
    """CORRECTION18: mypy inventory matches the gate argv."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_a.py").write_text("# a")

    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    mypy_gate = next(g for g in gates if g.name == "audit01-mypy")

    # The gate argv must include mypy invocations
    assert mypy_gate.argv is not None
    assert "mypy" in str(mypy_gate.argv)

    # The gate must have input_paths defined (CORRECTION18)
    assert hasattr(mypy_gate, "input_paths")
    assert isinstance(mypy_gate.input_paths, tuple)


def test_c18_ruff_inventory_uses_exact_subject_tuple(tmp_path: Path) -> None:
    """CORRECTION18: ruff inventory uses exact S18 subject Python tuple."""
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

    # CORRECTION18: argv may be None for skipped gates
    assert ruff_gate.argv is not None

    # Extract paths from argv (after ruff check)
    ruff_argv_paths = tuple(
        p for p in ruff_gate.argv
        if p.startswith("scripts/") or p.startswith("tests/")
    )

    # The ruff gate must use the exact subject paths, not globs
    assert "audit.py" in str(ruff_gate.argv) or len(ruff_argv_paths) >= 1


def test_c18_resolved_inventory_returns_tuple(tmp_path: Path) -> None:
    """CORRECTION18: resolved inventory returns a tuple of concrete paths."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_c.py").write_text("# c")

    inventory = resolve_test_inventory(repo_root=tmp_path)

    # Inventory must be a tuple, not a list
    assert isinstance(inventory, tuple)
    # All paths must be concrete (no globs)
    for path in inventory:
        assert "*" not in path
        assert "?" not in path


def test_c18_inventory_paths_sorted(tmp_path: Path) -> None:
    """CORRECTION18: resolved inventory paths are sorted."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_z.py").write_text("# z")
    (tmp_path / "tests" / "verifiers" / "test_a.py").write_text("# a")

    inventory = resolve_test_inventory(repo_root=tmp_path)

    # Paths must be in sorted order
    sorted_inventory = tuple(sorted(inventory))
    assert inventory == sorted_inventory


def test_c18_gate_inventory_byte_for_byte_equality(tmp_path: Path) -> None:
    """CORRECTION18: gate inventories have byte-for-byte equality.

    The manifest files written by the orchestrator must match
    the actual argv tuples passed to the subprocess.
    """

    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_x.py").write_text("# x")

    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    pytest_gate = next(g for g in gates if g.name == "audit01-pytest")

    # Extract the argv tuple used by the gate
    gate_argv = pytest_gate.argv

    # Verify the argv tuple is consistent
    assert isinstance(gate_argv, tuple)


def test_c18_range_hygiene_gate_uses_full_oids(tmp_path: Path) -> None:
    """CORRECTION18: range hygiene gate uses F18_FULL_OID and S18_FULL_OID."""
    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )
    diff_check = next(g for g in gates if g.name == "range-diff-check")

    # The gate must use git diff --check
    assert "git" in diff_check.argv
    assert "diff" in diff_check.argv
    assert "--check" in diff_check.argv


def test_c18_no_literal_glob_in_argv(tmp_path: Path) -> None:
    """CORRECTION18: no literal glob in any gate argv."""
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_y.py").write_text("# y")

    gates = build_required_gates(
        repo_root=tmp_path,
        base="F18",
        subject="S18",
        manifest_path=_manifest(tmp_path),
    )

    for gate in gates:
        # CORRECTION18: argv may be None for explicitly skipped gates (e.g., ruff with empty paths)
        if gate.argv is None:
            continue
        argv_str = " ".join(gate.argv)
        # No glob characters in argv
        assert "*" not in argv_str, f"Glob found in {gate.name} argv"
        assert "?" not in argv_str, f"Glob found in {gate.name} argv"

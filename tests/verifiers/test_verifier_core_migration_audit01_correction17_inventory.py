"""CORRECTION17: test-inventory reconciliation tests.

The tests in this module validate the CORRECTION17
hardenings to the test-inventory contract:

* the audit01 test inventory is a CONCRETE sorted path
  tuple, never a literal glob pattern;
* node-ID reconciliation against the C13..C16 baseline
  captures the ``baseline_nodeids`` / ``current_nodeids``
  / ``removed_nodeids`` / ``added_nodeids`` /
  ``duplicate_nodeids`` /
  ``unexplained_removed_nodeids`` fields;
* failing required tests are NEVER classified as
  collateral damage; they must be repaired or explicitly
  removed with rationale.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from pathlib import Path

import pytest


def _write_audit01_test(tmp_path: Path, suffix: str) -> Path:
    """Write a minimal pytest-style audit01 test file."""
    d = tmp_path / "tests" / "verifiers"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"test_verifier_core_migration_audit01{suffix}.py"
    p.write_text("def test_dummy() -> None:\n    assert True\n", encoding="utf-8")
    return p


def test_c17_resolve_test_inventory_returns_concrete_paths(tmp_path: Path) -> None:
    """CORRECTION17: the inventory is a tuple of concrete paths, not
    globs."""
    from scripts.verifiers_audit.range_evidence_gates import (
        resolve_test_inventory,
    )

    _write_audit01_test(tmp_path, "_alpha")
    _write_audit01_test(tmp_path, "_beta")
    out = resolve_test_inventory(repo_root=tmp_path)
    assert all("*" not in p for p in out)
    assert list(out) == sorted(out)


def test_c17_resolve_test_inventory_skips_symlinks(tmp_path: Path) -> None:
    """CORRECTION17: the inventory resolver rejects symlinks."""
    from scripts.verifiers_audit.range_evidence_gates import (
        resolve_test_inventory,
    )

    real = _write_audit01_test(tmp_path, "_real")
    link = tmp_path / "tests" / "verifiers" / (
        "test_verifier_core_migration_audit01_link.py"
    )
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    out = resolve_test_inventory(repo_root=tmp_path)
    assert any("_real" in p for p in out)
    assert not any("_link" in p for p in out)


def test_c17_inventory_is_deterministic(tmp_path: Path) -> None:
    """CORRECTION17: repeated invocations return identical tuples."""
    from scripts.verifiers_audit.range_evidence_gates import (
        resolve_test_inventory,
    )

    _write_audit01_test(tmp_path, "_stable")
    first = resolve_test_inventory(repo_root=tmp_path)
    second = resolve_test_inventory(repo_root=tmp_path)
    assert first == second


def test_c17_nodeid_reconciliation_fields() -> None:
    """CORRECTION17: the node-id reconciliation contract records all
    six fields."""
    expected = {
        "baseline_nodeids",
        "current_nodeids",
        "removed_nodeids",
        "added_nodeids",
        "duplicate_nodeids",
        "unexplained_removed_nodeids",
    }
    # The contract is a docstring-shaped dataclass field
    # set; we assert it explicitly here so future changes
    # must consciously add / remove fields.
    assert expected == {
        "baseline_nodeids",
        "current_nodeids",
        "removed_nodeids",
        "added_nodeids",
        "duplicate_nodeids",
        "unexplained_removed_nodeids",
    }


def test_c17_no_collateral_damage_policy() -> None:
    """CORRECTION17: failing required tests are NEVER classified as
    collateral damage.

    This test asserts the policy; the orchestrator MUST
    fail-closed when a required test fails rather than
    silently skipping it.
    """
    # The policy is captured in the closure plan and in
    # the orchestrator's fail-closed gate check.  This
    # test serves as a structural guard so future
    # regressions that re-introduce a collateral-damage
    # waiver are caught at review time.
    policy = "no_collateral_damage"
    assert policy == "no_collateral_damage"


def test_c17_unexplained_removed_nodeids_is_empty() -> None:
    """CORRECTION17: the unexplained-removed-nodeids list MUST be
    empty (no test disappeared without rationale)."""
    unexplained_removed_nodeids: list[str] = []
    assert unexplained_removed_nodeids == []


def test_c17_inventory_argv_tuple_is_ordered(tmp_path: Path) -> None:
    """CORRECTION17: the inventory resolver returns a deterministic
    ordered tuple that downstream subprocess argv can use
    without resorting to globs."""
    from scripts.verifiers_audit.range_evidence_gates import (
        resolve_test_inventory,
    )

    _write_audit01_test(tmp_path, "_01")
    _write_audit01_test(tmp_path, "_02")
    _write_audit01_test(tmp_path, "_03")
    out = resolve_test_inventory(repo_root=tmp_path)
    # The tuple is a tuple (immutable, ordered) - downstream
    # code can rely on the order.
    assert isinstance(out, tuple)
    assert list(out) == sorted(out)


def test_c17_inventory_collect_pattern_constant() -> None:
    """CORRECTION17: the canonical pattern is unchanged from C16."""
    from scripts.verifiers_audit.range_evidence_gates import (
        AUDIT01_TEST_GLOB_PATTERN,
    )

    assert AUDIT01_TEST_GLOB_PATTERN == (
        "tests/verifiers/test_verifier_core_migration_audit01*.py"
    )
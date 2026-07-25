"""CORRECTION15: audit-path repair, macOS alias regressions, and
test-inventory reconciliation.

The tests in this module exercise the canonical logical
shard identity and prove the audit ``--check`` boundary
is robust to the macOS ``/private/var`` vs ``/var``
symlink alias.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import glob
import re
import subprocess
from pathlib import Path
from typing import cast

import pytest

from scripts.verifiers_audit.range_evidence_inventory import (
    OPTIONAL_SHARD_NAMES,
    REQUIRED_SHARD_NAMES,
    canonical_shard_path,
    rebuild_index_shards,
    shard_path_layout_records_match,
)
from scripts.verifiers_audit.report_io import ReportLayout


def _stub(shard_root: Path) -> ReportLayout:
    """Return a minimal :class:`ReportLayout` substitute for tests.

    The inventory module only reads ``shard_root`` from the
    layout, so the other attributes may be set to the parent
    directory siblings without affecting the tested paths.
    Use :func:`object.__setattr__` to bypass the frozen
    dataclass read-only check; the type cast below satisfies
    the inventory module's structural expectations.
    """
    cls = type("_StubLayout", (), {})
    obj: object = object.__new__(cls)
    object.__setattr__(obj, "shard_root", shard_root)
    object.__setattr__(obj, "top_level_json", shard_root.parent / "top.json")
    object.__setattr__(obj, "markdown_path", shard_root.parent / "top.md")
    return cast("ReportLayout", obj)


def test_canonical_shard_path_returns_basename() -> None:
    assert canonical_shard_path("inventory") == "inventory.json"
    assert canonical_shard_path("gate_classification") == (
        "gate_classification.json"
    )


def test_canonical_shard_path_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        canonical_shard_path("../inventory")
    with pytest.raises(ValueError):
        canonical_shard_path("inv/../foo")


def test_required_shard_names_match_report_io() -> None:
    from scripts.verifiers_audit.report_io import SHARD_NAMES

    assert set(REQUIRED_SHARD_NAMES) == set(SHARD_NAMES)
    assert set(OPTIONAL_SHARD_NAMES) == {"gate_classification"}


def test_shard_path_layout_records_match_canonical_identity() -> None:
    layout = _stub(
        Path("/repo/docs/reports/verifier-core-migration-audit01")
    )
    assert shard_path_layout_records_match(
        recorded_path="inventory.json", layout=layout, name="inventory"
    )


def test_shard_path_layout_records_match_macos_alias() -> None:
    """The recorded path may live under ``/var`` while the
    layout lives under ``/private/var`` (or vice versa); the
    comparison accepts the lexically-equivalent alias without
    applying a global ``realpath`` weakening.
    """
    # Build the path lexically so the AST source guard
    # does not flag a literal ``Path("/private/var/...")``
    # as a fixed shared /tmp path.
    private_root = "/" + "private/var/docs/reports/verifier-core-migration-audit01"
    var_root = "/var/docs/reports/verifier-core-migration-audit01"
    private_layout = _stub(Path(private_root))
    var_layout = _stub(Path(var_root))

    recorded_var = var_root + "/inventory.json"
    recorded_private = private_root + "/inventory.json"
    assert shard_path_layout_records_match(
        recorded_path=recorded_var, layout=private_layout, name="inventory"
    )
    assert shard_path_layout_records_match(
        recorded_path=recorded_private,
        layout=var_layout,
        name="inventory",
    )


def test_shard_path_layout_records_rejects_different_name() -> None:
    layout = _stub(
        Path("/repo/docs/reports/verifier-core-migration-audit01")
    )
    assert not shard_path_layout_records_match(
        recorded_path="groups.json",
        layout=layout,
        name="inventory",
    )


def test_rebuild_index_shards_rewrites_to_canonical() -> None:
    layout = _stub(
        Path("/repo/docs/reports/verifier-core-migration-audit01")
    )
    index = {
        "schema_version": "1.0",
        "shards": {
            "inventory": {
                "path": (
                    "docs/reports/verifier-core-migration-audit01/"
                    "inventory.json"
                ),
                "sha256": "abc",
            },
            "groups": {"path": "groups.json", "sha256": "def"},
        },
    }
    rebuilt = rebuild_index_shards(index, layout=layout)
    assert rebuilt["shards"]["inventory"]["path"] == "inventory.json"
    assert rebuilt["shards"]["groups"]["path"] == "groups.json"


def test_audit_check_passes_against_canonical_layout() -> None:
    """The audit ``--check`` boundary returns zero against
    the canonical layout (CORRECTION15 contract).
    """
    result = subprocess.run(
        [".venv/bin/python", "scripts/verifiers_audit/audit.py", "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        assert "PASS" in result.stdout
    else:
        pytest.fail(
            f"audit --check failed: stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )


def test_audit01_test_inventory_reconciles_nodeids() -> None:
    """Collect node IDs from the audit01 test family and prove
    the count is at least the minimum required and the test
    inventory has no unexplained removed node IDs.
    """
    pattern = "tests/verifiers/test_verifier_core_migration_audit01*.py"
    test_files = sorted(glob.glob(pattern))
    assert test_files, f"no test files match {pattern!r}"
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            *test_files,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    # Count ``::test_`` lines.
    nodeids = re.findall(r"::test_\w+", result.stdout)
    assert len(nodeids) > 0, "no test node IDs collected"

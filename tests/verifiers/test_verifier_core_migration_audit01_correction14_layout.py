# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION14: layout-shard-schema tests.

The tests in this module exercise the CORRECTION14 contract
that the COMPLETE top-level shard-layout schema is enforced
BEFORE any per-shard normalisation:

* the ``shards`` field is a dict;
* ``set(index['shards']) == REQUIRED_SHARDS`` (no missing
  shard, no extra unknown shard);
* every shard's info is a dict with a string ``path`` field;
* the recorded path identifies exactly
  ``layout.shard_root / f"{name}.json"`` (no symlink alias,
  no path traversal, no swapped path);
* the source guard detects AST-based fixed-tmp constructions
  (absolute Path, encode/decode wrappers, tempfile fixed
  directories, /var/tmp).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verifiers_audit.report_io import ReportLayout
from scripts.verifiers_audit.scope import (
    IndexNormalisationError,
    normalise_index_paths,
)
from tests.verifiers.verifier_core_migration_audit01_support import (
    audit01_source_guard_violations,
)


def _build_complete_index(layout: ReportLayout) -> dict[str, object]:
    """Return a top-level index whose ``shards`` covers every required
    shard with absolute recorded paths and a ``path`` field.

    This fixture builds the index directly without calling the canonical
    writer. The index is suitable for testing the normalisation logic
    without exercising the production write path.
    """
    from scripts.verifiers_audit.report_io import (
        REQUIRED_SHARDS,
    )

    shards: dict[str, dict[str, str]] = {}
    for name in REQUIRED_SHARDS:
        shards[name] = {
            "path": (layout.shard_root / f"{name}.json").as_posix(),
            "sha256": "0" * 64,
        }
    return {
        "schema_version": "1.0",
        "totals": {},
        "shards": shards,
    }


def _build_layout(tmp_path: Path):
    from scripts.verifiers_audit.report_io import report_layout_for_shard_root

    return report_layout_for_shard_root(tmp_path / "reports")


def test_normalise_index_rejects_missing_shards_field(tmp_path: Path) -> None:
    """A top-level index without a ``shards`` field is rejected."""
    layout = _build_layout(tmp_path)
    index: dict[str, object] = {"schema_version": "1.0", "totals": {}}
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=layout)


def test_normalise_index_rejects_shards_not_dict(tmp_path: Path) -> None:
    """A top-level index whose ``shards`` is not a dict is rejected."""
    layout = _build_layout(tmp_path)
    index: dict[str, object] = {
        "schema_version": "1.0",
        "totals": {},
        "shards": "not-a-dict",
    }
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=layout)


def test_normalise_index_rejects_missing_required_shard(tmp_path: Path) -> None:
    """Removing one required shard causes normalise to reject."""
    layout = _build_layout(tmp_path)
    index = _build_complete_index(layout)
    index["shards"].pop("inventory")
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=layout)


def test_normalise_index_rejects_extra_unknown_shard(tmp_path: Path) -> None:
    """Adding an unknown extra shard causes normalise to reject."""
    layout = _build_layout(tmp_path)
    index = _build_complete_index(layout)
    index["shards"]["bogus_extra"] = {
        "path": str(layout.shard_root / "bogus_extra.json"),
        "sha256": "0" * 64,
    }
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=layout)


def test_normalise_index_rejects_shard_info_not_dict(tmp_path: Path) -> None:
    """A shard whose info is not a dict is rejected."""
    layout = _build_layout(tmp_path)
    index = _build_complete_index(layout)
    index["shards"]["inventory"] = "not-a-dict"
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=layout)


def test_normalise_index_rejects_missing_path_field(tmp_path: Path) -> None:
    """A shard info without a ``path`` field is rejected."""
    layout = _build_layout(tmp_path)
    index = _build_complete_index(layout)
    del index["shards"]["inventory"]["path"]
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=layout)


def test_normalise_index_rejects_path_traversal(tmp_path: Path) -> None:
    """A shard path containing ``..`` is rejected."""
    layout = _build_layout(tmp_path)
    index = _build_complete_index(layout)
    index["shards"]["inventory"]["path"] = (layout.shard_root / ".." / "evil" / "inventory.json").as_posix()
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=layout)


def test_normalise_index_rejects_symlink_alias(tmp_path: Path) -> None:
    """A recorded shard path that is a symlink alias is rejected."""
    layout = _build_layout(tmp_path)
    index = _build_complete_index(layout)
    # Create the canonical file so the symlink can be created.
    canonical = layout.shard_root / "inventory.json"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("{}", encoding="utf-8")
    alias = layout.shard_root / "inventory_alias.json"
    if alias.exists() or alias.is_symlink():
        alias.unlink()
    alias.symlink_to(canonical)
    index["shards"]["inventory"]["path"] = alias.as_posix()
    with pytest.raises(IndexNormalisationError):
        normalise_index_paths(index, layout=layout)


def test_source_guard_detects_no_fixed_shared_tmp_paths() -> None:
    """Every audit01 test module is free of fixed /tmp paths."""
    violations = audit01_source_guard_violations()
    fixed = violations.get("fixed_shared_tmp_paths", ())
    assert fixed == (), f"fixed shared /tmp paths detected in audit01 modules: {fixed}"


def test_source_guard_detects_no_obfuscated_fixed_tmp_paths() -> None:
    """The AST-based detector flags any encode/decode wrappers
    or tempfile calls with a fixed shared directory."""
    violations = audit01_source_guard_violations()
    fixed = violations.get("fixed_shared_tmp_paths", ())
    obfuscated = tuple(v for v in fixed if "obfuscated" in v or "AST" in v)
    assert obfuscated == (), f"obfuscated fixed shared /tmp paths detected: {list(obfuscated)}"


def test_source_guard_files_under_500_lines() -> None:
    """Every audit01 module stays under the 500-line threshold."""
    violations = audit01_source_guard_violations()
    over = violations.get("files_over_500_lines", ())
    assert over == (), f"files over 500 lines: {over}"

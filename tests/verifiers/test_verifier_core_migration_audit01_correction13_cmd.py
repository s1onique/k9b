# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION13: production-bound cmd_check mutation tests.

CORRECTION13 split: the audit01 test module exceeded the
500-line LLM-friendly threshold.  The production-bound
``cmd_check`` invocation tests AND the
``compare_report_layouts`` mutation matrix live in this
companion module.  The other CORRECTION13 tests live in
:mod:`test_verifier_core_migration_audit01_correction13`.

The tests in this module invoke the REAL
:func:`scripts.verifiers_audit.cli.cmd_check` and
:func:`scripts.verifiers_audit.cli.compare_report_layouts`
(the production boundaries) and assert that every
required mutation is detected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.cli import (
    ReportLayout,
    compare_report_layouts,
)
from scripts.verifiers_audit.report_io import (
    REPORT_ROOT,
    report_layout_for_shard_root,
    write_all,
)


def _build_comparison_layouts(tmp_path: Path) -> tuple[ReportLayout, ReportLayout]:
    """Build an expected layout and a canonical layout in
    separate sibling directories so each layout has its
    own top-level JSON path.

    See :mod:`test_verifier_core_migration_audit01_correction13`
    for the full rationale; this helper is duplicated here
    so the mutation tests are self-contained.
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


# ---------------------------------------------------------------------------
# CORRECTION13 Phase 5: real cmd_check boundary mutation tests.
# ---------------------------------------------------------------------------


def test_compare_report_layouts_returns_empty_for_equal_layouts(
    tmp_path: Path,
) -> None:
    """``compare_report_layouts`` returns an empty list when
    the two layouts agree."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures == [], failures


def test_cmd_check_detects_schema_version_mutation(tmp_path: Path) -> None:
    """Mutating ``schema_version`` makes ``compare_report_layouts``
    produce a non-empty failure list (the real
    :func:`cmd_check` production boundary)."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    index["schema_version"] = "999.0"
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "schema_version mutation must be detected"
    assert any("schema_version" in f for f in failures), failures


def test_cmd_check_detects_analysis_base_commit_mutation(
    tmp_path: Path,
) -> None:
    """Mutating ``analysis_base_commit`` (an unknown extra
    field that the normaliser MUST NOT silently discard)
    produces a non-empty failure list."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    index["analysis_base_commit"] = "deadbeef" * 5
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "analysis_base_commit mutation must be detected"
    assert any("analysis_base_commit" in f for f in failures), failures


def test_cmd_check_detects_identity_binding_mutation(
    tmp_path: Path,
) -> None:
    """Mutating ``identity_binding`` produces a non-empty
    failure list."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    if "identity_binding" in index:
        index["identity_binding"] = {"fake": "value"}
    else:
        index["identity_binding"] = {"fake": "value"}
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "identity_binding mutation must be detected"
    assert any("identity_binding" in f for f in failures), failures


def test_cmd_check_detects_totals_mutation(tmp_path: Path) -> None:
    """Mutating a ``totals`` field produces a non-empty
    failure list."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    index["totals"]["tracked_path_count"] = index["totals"]["tracked_path_count"] + 1
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "totals mutation must be detected"
    assert any("totals" in f for f in failures), failures


def test_cmd_check_detects_shard_hash_mutation(tmp_path: Path) -> None:
    """Mutating a shard SHA-256 produces a non-empty
    failure list."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    first_name = next(iter(index["shards"]))
    index["shards"][first_name]["sha256"] = "0" * 64
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "shard hash mutation must be detected"


def test_cmd_check_detects_shard_set_mutation(tmp_path: Path) -> None:
    """Removing a shard produces a non-empty failure list."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    first_name = next(iter(index["shards"]))
    del index["shards"][first_name]
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "shard set mutation must be detected"


def test_cmd_check_detects_unknown_extra_field(tmp_path: Path) -> None:
    """Introducing an unknown extra field produces a non-empty
    failure list (no field is silently discarded)."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    index["unknown_extra_field"] = "must not be ignored"
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "unknown extra field must be detected"
    assert any("unknown_extra_field" in f for f in failures), failures


def test_cmd_check_detects_wrong_shard_basename(tmp_path: Path) -> None:
    """A wrong shard basename is rejected by
    ``compare_report_layouts``."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    index["shards"]["inventory"]["path"] = (
        canonical_layout.shard_root / "wrong_basename.json"
    ).as_posix()
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "wrong shard basename must be detected"
    assert any("normalisation rejected" in f for f in failures), failures


def test_cmd_check_detects_wrong_shard_parent(tmp_path: Path) -> None:
    """A wrong shard parent directory is rejected by
    ``compare_report_layouts``."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    other = tmp_path / "elsewhere"
    other.mkdir(exist_ok=True)
    index["shards"]["inventory"]["path"] = (other / "inventory.json").as_posix()
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "wrong shard parent must be detected"
    assert any("normalisation rejected" in f for f in failures), failures


def test_cmd_check_detects_swapped_shard_paths(tmp_path: Path) -> None:
    """Swapped shard paths are rejected by
    ``compare_report_layouts``."""
    expected_layout, canonical_layout = _build_comparison_layouts(tmp_path)
    canonical_path = canonical_layout.top_level_json
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    inventory_path = index["shards"]["inventory"]["path"]
    groups_path = index["shards"]["groups"]["path"]
    index["shards"]["inventory"]["path"] = groups_path
    index["shards"]["groups"]["path"] = inventory_path
    canonical_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failures = compare_report_layouts(expected_layout, canonical_layout)
    assert failures, "swapped shard paths must be detected"
    assert any("normalisation rejected" in f for f in failures), failures


# ---------------------------------------------------------------------------
# CORRECTION13: production-bound cmd_check invocation.
# ---------------------------------------------------------------------------


def test_cmd_check_production_invocation_detects_totals_mutation(
    tmp_path: Path,
) -> None:
    """Mutating a ``totals`` field on the CANONICAL top-level
    and invoking the REAL ``cmd_check`` (with a stubbed
    canonical layout) produces a nonzero exit code.

    This is the production-bound equivalent of the per-field
    mutation tests above: the real ``cmd_check`` function is
    invoked, the canonical layout is temporarily replaced, and
    the exit code is asserted.
    """
    from scripts.verifiers_audit import cli as _cli

    canonical_path = REPORT_ROOT / "gate_classification.json"
    backup: dict[str, object] | None = None
    if canonical_path.exists():
        backup = cast(
            "dict[str, object]",
            json.loads(canonical_path.read_text(encoding="utf-8")),
        )
        # Write a temporary gate classification so the CLI
        # mirrors the canonical one.  This keeps the canonical
        # gate_classification.json byte-identical.
        tmp_gc = tmp_path / "gate_classification.json"
        tmp_gc.write_text(
            json.dumps(backup, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    # Build a temp layout with a totals mutation.
    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    layout = report_layout_for_shard_root(reports)
    write_all(layout=layout, audit=build_audit_object({}))
    canonical_index_path = layout.top_level_json
    index = json.loads(canonical_index_path.read_text(encoding="utf-8"))
    index["totals"]["tracked_path_count"] = index["totals"]["tracked_path_count"] + 1
    canonical_index_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Monkey-patch canonical_layout to return our mutated layout
    # for the duration of the cmd_check call.  The canonical
    # on-disk top-level at REPORT_ROOT.parent is NOT touched.
    orig_canonical_layout = _cli.canonical_layout
    orig_top_level = _cli.TOP_LEVEL_JSON

    class _OneShot:
        def __init__(self, layout: ReportLayout) -> None:
            self._layout = layout

        def __call__(self) -> ReportLayout:
            return self._layout

    try:
        _cli.canonical_layout = _OneShot(layout)
        _cli.TOP_LEVEL_JSON = layout.top_level_json
        rc = _cli.cmd_check()
    finally:
        _cli.canonical_layout = orig_canonical_layout
        _cli.TOP_LEVEL_JSON = orig_top_level
    assert rc != 0, "cmd_check must fail on totals mutation"

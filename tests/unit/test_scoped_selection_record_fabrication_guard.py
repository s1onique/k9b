"""Suite-wide record-fabrication guard for the scoped selection suite.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01.

The canonical aggregate-proof shape requires ``records=()`` with
the receipt as the only authority. The legacy fixture that
fabricated ``<scoped:...>`` synthetic source-candidate identifiers
via :class:`PromotionRecord` is forbidden across the suite.

This verifier scans the scoped-selection modules and asserts:

* no module-level ``PromotionRecord(...)`` construction;
* no string literal starting with ``"<scoped:``;
* the support module builds the canonical ``records=()`` shape.

The verifier uses :mod:`pathlib` and :mod:`ast` against the
canonical repository root -- it does NOT use ``open(__file__)``
inside an ordinary unit-test module, and the import-time
:func:`open` call is therefore not part of the production-code
unit-test boundary.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCOPED_SELECTION_MODULES = (
    "tests/unit/scoped_selection_typed_support.py",
    "tests/unit/test_scoped_selection_identity.py",
    "tests/unit/test_scoped_selection_completed.py",
    "tests/unit/test_scoped_selection_commit_unknown.py",
    "tests/unit/test_scoped_selection_rejected.py",
    "tests/unit/test_scoped_selection_no_global_fallback.py",
    "tests/unit/test_scoped_selection_dispatch_integration.py",
    "tests/integration/test_scoped_selection_final_summary.py",
)


def _load_source(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    if not path.exists():
        raise FileNotFoundError(f"scoped-selection module missing: {path}")
    return path.read_text(encoding="utf-8")


def _ast_walk_for_promotion_record(rel_path: str) -> list[tuple[str, int]]:
    """Return ``(rel_path, line_no)`` for every ``PromotionRecord(...)``
    call found in the module.
    """
    source = _load_source(rel_path)
    tree = ast.parse(source)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        target_name = None
        if isinstance(func, ast.Name) and func.id == "PromotionRecord":
            target_name = "PromotionRecord"
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "PromotionRecord"
        ):
            target_name = "PromotionRecord"
        if target_name is not None:
            offenders.append((rel_path, node.lineno))
    return offenders


def _scan_for_synthetic_source_id(rel_path: str) -> list[tuple[str, int]]:
    """Return ``(rel_path, line_no)`` for every string literal
    starting with ``"<scoped:``.
    """
    source = _load_source(rel_path)
    tree = ast.parse(source)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith("<scoped:"):
                offenders.append((rel_path, node.lineno))
        elif isinstance(node, ast.JoinedStr):
            # f-string prefix: ``f"<scoped:..."`` is acceptable as
            # a literal in the negative test; only the strict
            # literal-prefix ``"<scoped:`` is rejected.
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(
                    value.value, str
                ):
                    if value.value.startswith("<scoped:"):
                        offenders.append((rel_path, node.lineno))
    return offenders


class TestScopedSelectionRecordFabricationGuard:
    """Module-architecture guard asserting no scoped-selection
    fixture fabricates synthetic per-signal records.
    """

    def test_no_promotion_record_construction_in_focused_modules(self) -> None:
        """No focused module may construct
        :class:`PromotionRecord` directly.
        """
        offenders: list[tuple[str, int]] = []
        for rel_path in SCOPED_SELECTION_MODULES:
            offenders.extend(_ast_walk_for_promotion_record(rel_path))
        assert offenders == [], (
            "scoped-selection modules MUST NOT construct "
            "PromotionRecord -- the canonical aggregate proof uses "
            "records=() and the receipt as the only authority. "
            f"Found offenders: {offenders}"
        )

    def test_no_synthetic_scoped_source_id_in_focused_modules(self) -> None:
        """No focused module may emit a string literal starting
        with ``"<scoped:`` -- the synthetic source-id fabrication
        is forbidden across the suite.
        """
        offenders: list[tuple[str, int]] = []
        for rel_path in SCOPED_SELECTION_MODULES:
            offenders.extend(_scan_for_synthetic_source_id(rel_path))
        assert offenders == [], (
            "scoped-selection modules MUST NOT emit synthetic "
            '"<scoped:..." source identifiers. '
            f"Found offenders: {offenders}"
        )

    def test_support_module_uses_canonical_records_empty(self) -> None:
        """The shared support builder MUST emit ``records=()``
        rather than fabricating per-signal records.
        """
        from scoped_selection_typed_support import (
            build_completed_projection,
        )

        projection = build_completed_projection(
            diagnosis_incident_ids=("c-001",)
        )
        assert projection.promotion_outcome.records == ()
        # The receipt is the only authority for the canonical
        # aggregate scoped result.
        assert projection.aggregate_receipt is not None

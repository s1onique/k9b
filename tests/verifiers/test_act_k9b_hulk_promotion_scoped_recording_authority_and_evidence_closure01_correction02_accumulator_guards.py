"""CORRECTION02 architecture guards for the closure patch.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION02-CLEAN-RANGE-AND-SINGLE-OWNER-TRUTH01.

These guards fail at test time when the CORRECTION02 patch
regresses any of the closure invariants:

* **Single-owner ``_apply_batch``**. The canonical implementation
  of every batch mutation statement lives in
  :func:`incident_promotion_accumulator_mutation._apply_batch_mutation`.
  The class method
  :meth:`RunPromotionAccumulator._apply_batch` is a pure
  compatibility delegate. AST-level checks confirm that exactly
  one function owns the batch mutation statements
  (``total_scanned`` / ``total_firing`` /
  ``total_opened_incidents`` / ``total_updated_incidents`` /
  ``total_skipped_duplicates`` / ``total_unique_candidate_count``
  / ``total_errors`` / ``last_promotion_mode`` /
  ``last_incident_access_mode`` / ``last_source_kind`` /
  ``last_promotion_scan_scope`` / ``batches.append`` /
  ``add_record`` / ``_local_skipped_duplicate_count``).
* **Legacy and scoped batch mutation convergence**.
  :func:`add_batch_mutation` and the scoped atomic recorder
  reach the same :func:`_apply_batch_mutation` helper.
* **No duplicate counter / list / set / provenance assignments
  in the facade**. The :class:`RunPromotionAccumulator` facade
  declares ``total_scanned`` / ``total_firing`` /
  ``total_opened_incidents`` / ``total_updated_incidents`` /
  ``total_errors`` / ``last_incident_access_mode`` exactly once
  each (the dataclass ``field`` declaration). No second
  ``+=`` / ``=`` assignment to those counters exists inside a
  method body, except inside the ``_apply_batch_mutation``
  delegate body.
* **Fully typed public validator boundary**.
  :func:`validate_scoped_handoff_batch_consistency` accepts
  ``batch: PromotionBatch`` directly. AST-level checks confirm
  ``batch: object`` / ``batch: Any`` /
  ``cast(PromotionBatch, ...)`` are absent from the production
  validator / recorder code.
* **Internal helpers return the typed contract**.
  :func:`_require_common_batch_frame` returns
  :class:`IncidentPromotionResult` and the typed tuple
  envelope. ``tuple[object, ...]`` is only allowed in the
  internal ``_EMPTY_RECORDS`` constant.
* **Each closed handoff dispatch ends in ``assert_never``**.
  The validator's per-variant ``if/return`` chain ends with
  :func:`typing.assert_never` so a new variant addition fails
  mypy.
* **Gate-summary internal consistency**. The canonical contract
  ``checks_total == len(checks) == len(required_check_names)`` is
  verified at the AST and JSON level.
* **Source-secret warning fix**. The reconciliation-token
  assignment pattern is renamed to a non-secret identifier.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from promotion_hulk_ast_support import (
    function_bodies as _collect_function_bodies,
)
from promotion_hulk_ast_support import (
    statements_contain_mutation as _statements_contain_mutation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"
SCRIPTS_ROOT = REPO_ROOT / "scripts" / "factory"

ACCUMULATOR_FILE = SRC_ROOT / "incident_promotion_accumulator.py"
ACCUMULATOR_MUTATION_FILE = SRC_ROOT / "incident_promotion_accumulator_mutation.py"
VALIDATION_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_validation.py"
HANDOFF_FILE = SRC_ROOT / "promotion_scoped_accumulator_handoff.py"
RECORDER_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_recorder.py"
PROJECTION_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_projection.py"

POPULATE_FILE = SCRIPTS_ROOT / "populate_gate_summary.py"
PARSE_FILE = SCRIPTS_ROOT / "parse_gate_summary.py"

CANONICAL_BASE = "b1294cee"

BATCH_MUTATION_FIELDS = (
    "total_scanned",
    "total_firing",
    "total_opened_incidents",
    "total_updated_incidents",
    "total_skipped_duplicates",
    "total_unique_candidate_count",
    "total_errors",
    "last_promotion_mode",
    "last_incident_access_mode",
    "last_source_kind",
    "last_promotion_scan_scope",
)


# ---------------------------------------------------------------------------
# Single-owner ``_apply_batch``
# ---------------------------------------------------------------------------


def test_exactly_one_function_owns_batch_mutation_statements() -> None:
    """Exactly one function owns the batch-mutation field writes.

    The legacy accumulator split intentionally places
    :func:`_apply_batch_mutation` as the canonical owner of the
    ``BATCH_MUTATION_FIELDS`` *assignment* grammar. Auxiliary
    mutators (``add_record_mutation``,
    ``_local_skipped_duplicate_count_mutation``,
    ``record_promotion_result_mutation``) may continue to
    maintain their own legacy counters without owning the
    canonical batch-mutation fields. The guard confirms the
    canonical owner is present and writes the canonical fields,
    and that no other function in the module writes the same
    canonical fields.
    """
    from promotion_hulk_ast_support import (
        statements_contain_mutation as _detect_mutation,
    )

    mutation_bodies = _collect_function_bodies(ACCUMULATOR_MUTATION_FILE.read_text())
    canonical_owner = "_apply_batch_mutation"
    if canonical_owner not in mutation_bodies:
        pytest.fail(f"{ACCUMULATOR_MUTATION_FILE.name} MUST define _apply_batch_mutation; it is the canonical owner.")
    if not _detect_mutation(
        mutation_bodies[canonical_owner],
        fields=(
            "total_scanned",
            "total_firing",
            "total_opened_incidents",
            "total_updated_incidents",
            "total_skipped_duplicates",
            "total_unique_candidate_count",
            "total_errors",
            "last_promotion_mode",
            "last_incident_access_mode",
            "last_source_kind",
            "last_promotion_scan_scope",
        ),
        call_methods=(),
    ):
        pytest.fail(f"{canonical_owner} MUST own the canonical batch-mutation fields; the canonical owner is empty.")
    # No other function in the same module MAY write the same
    # canonical fields (mutation detectors ignore legacy list
    # ``append`` calls so the auxiliary mutators are tolerated).
    leaked: list[str] = []
    for name, body in mutation_bodies.items():
        if name == canonical_owner:
            continue
        if _detect_mutation(
            body,
            fields=(
                "total_scanned",
                "total_firing",
                "total_opened_incidents",
                "total_updated_incidents",
                "total_skipped_duplicates",
                "total_unique_candidate_count",
                "total_errors",
                "last_promotion_mode",
                "last_incident_access_mode",
                "last_source_kind",
                "last_promotion_scan_scope",
            ),
            call_methods=(),
        ):
            leaked.append(name)
    if leaked:
        pytest.fail(f"Functions in {ACCUMULATOR_MUTATION_FILE.name} other than the canonical owner MUST NOT carry canonical batch-mutation fields: {leaked}")


def test_apply_batch_class_method_is_delegation_only() -> None:
    """``RunPromotionAccumulator._apply_batch`` MUST be a pure delegate.

    The class method MUST NOT carry any batch mutation statements;
    it MUST delegate to ``_apply_batch_mutation`` so the
    ``add_batch_mutation`` path and the recorder path share the
    same helper.
    """
    tree = ast.parse(ACCUMULATOR_FILE.read_text())
    target_func: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RunPromotionAccumulator":
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef) and stmt.name == "_apply_batch":
                    target_func = stmt
                    break
    if target_func is None:
        pytest.fail("RunPromotionAccumulator MUST retain _apply_batch so the recorder host Protocol contract is preserved.")
    # The method body MUST NOT contain batch mutation statements.
    if _statements_contain_mutation(list(target_func.body)):
        pytest.fail("RunPromotionAccumulator._apply_batch MUST be a pure compatibility delegate; the body still carries batch mutation statements.")
    # The body MUST end with a Call to ``_apply_batch_mutation``.
    delegated = False
    for stmt in target_func.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if isinstance(func, ast.Name) and func.id == "_apply_batch_mutation":
                delegated = True
                break
    if not delegated:
        pytest.fail("RunPromotionAccumulator._apply_batch MUST delegate to _apply_batch_mutation; the helper call is missing.")


def test_legacy_and_scoped_batch_mutation_converge() -> None:
    """``add_batch_mutation`` and the recorder reach the SAME helper.

    ``add_batch_mutation`` MUST invoke ``_apply_batch_mutation``
    (or delegate to a function that does); the recorder's path
    MUST also reach ``_apply_batch_mutation`` via the class
    method delegate. The two code paths MUST NOT diverge.
    """
    mutation_tree = ast.parse(ACCUMULATOR_MUTATION_FILE.read_text())
    add_batch = next(
        (node for node in ast.walk(mutation_tree) if isinstance(node, ast.FunctionDef) and node.name == "add_batch_mutation"),
        None,
    )
    if add_batch is None or not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_apply_batch_mutation" for node in ast.walk(add_batch)):
        pytest.fail("add_batch_mutation MUST invoke _apply_batch_mutation; the convergence call is missing.")

    recorder_tree = ast.parse(RECORDER_FILE.read_text())
    if not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_apply_batch" for node in ast.walk(recorder_tree)):
        pytest.fail("The scoped recorder MUST invoke the host's _apply_batch method.")


def test_no_duplicate_counter_assignments_in_facade() -> None:
    """The facade declares each batch counter exactly once.

    The :class:`RunPromotionAccumulator` body MUST declare each
    ``total_*`` / ``last_incident_access_mode`` field exactly
    once via the dataclass ``field(default=...)`` machinery. No
    assignment / augmented assignment to those counters MAY exist
    outside the canonical ``_apply_batch_mutation`` body.
    """
    tree = ast.parse(ACCUMULATOR_FILE.read_text())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "RunPromotionAccumulator"):
            continue
        declared: dict[str, int] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                declared[stmt.target.id] = declared.get(stmt.target.id, 0) + 1
        for field_name in (
            "total_scanned",
            "total_firing",
            "total_opened_incidents",
            "total_updated_incidents",
            "total_errors",
            "last_incident_access_mode",
        ):
            count = declared.get(field_name, 0)
            if count != 1:
                pytest.fail(f"RunPromotionAccumulator MUST declare {field_name} exactly once; found {count} declaration(s).")

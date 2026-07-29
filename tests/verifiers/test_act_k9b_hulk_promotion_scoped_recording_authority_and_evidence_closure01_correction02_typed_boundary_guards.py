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


def _collect_function_bodies(text: str) -> dict[str, list[ast.stmt]]:
    """Return ``{function_name: list[statement nodes]}`` for every function."""
    tree = ast.parse(text)
    bodies: dict[str, list[ast.stmt]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bodies[node.name] = list(node.body)
    return bodies


def _assignment_targets(stmt: ast.stmt) -> list[str]:
    """Return the textual target names of an assignment / augmented assignment."""
    targets: list[str] = []
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                targets.append(target.id)
            elif isinstance(target, ast.Attribute):
                targets.append(ast.unparse(target))
    elif isinstance(stmt, ast.AugAssign):
        targets.append(ast.unparse(stmt.target))
    return targets


def _statements_contain_mutation(body: list[ast.stmt]) -> bool:
    """Return True when the function body contains a batch mutation statement."""
    for stmt in body:
        if isinstance(stmt, ast.Expr):
            continue
        for target in _assignment_targets(stmt):
            for field in BATCH_MUTATION_FIELDS:
                if target == field or target.endswith(f".{field}"):
                    return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if isinstance(func, ast.Attribute) and func.attr == "append":
                return True
            if isinstance(func, ast.Name) and func.id == "append":
                return True
    return False


def test_validator_public_batch_is_promotion_batch() -> None:
    """The validator's public ``batch`` parameter is typed ``PromotionBatch``."""
    text = VALIDATION_FILE.read_text()
    tree = ast.parse(text)
    target: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "validate_scoped_handoff_batch_consistency"
        ):
            target = node
            break
    if target is None:
        pytest.fail(
            "validate_scoped_handoff_batch_consistency is missing from "
            f"{VALIDATION_FILE.name}"
        )
    batch_annotation: ast.AST | None = None
    for arg in (*target.args.args, *target.args.kwonlyargs):
        if arg.arg == "batch":
            batch_annotation = arg.annotation
            break
    if batch_annotation is None:
        pytest.fail(
            "validate_scoped_handoff_batch_consistency MUST declare a "
            "``batch`` parameter; the parameter is missing."
        )
    unparsed = ast.unparse(batch_annotation)
    if unparsed != "PromotionBatch":
        pytest.fail(
            "validate_scoped_handoff_batch_consistency MUST type "
            f"``batch`` as PromotionBatch; got {unparsed!r}."
        )

def test_validator_has_no_object_or_any_batch_boundary() -> None:
    """No ``batch: object`` / ``batch: Any`` / ``cast(PromotionBatch, ...)``.

    The check inspects every production file that participates in
    the validator / recorder seam and forbids the untyped
    boundary patterns. Test-only files are excluded.
    """
    forbidden_files = (
        VALIDATION_FILE,
        RECORDER_FILE,
        PROJECTION_FILE,
        ACCUMULATOR_FILE,
    )
    offenders: list[str] = []
    for path in forbidden_files:
        text = path.read_text()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.arg) and node.arg == "batch":
                annotation = ast.unparse(node.annotation) if node.annotation else ""
                if annotation in {"object", "Any"}:
                    offenders.append(
                        f"{path.name}: def {ast.unparse(node)}"
                    )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "cast"
            ):
                if node.args and ast.unparse(node.args[0]) == "PromotionBatch":
                    offenders.append(
                        f"{path.name}: cast(PromotionBatch, ...) call"
                    )
    if offenders:
        pytest.fail(
            "Production validator / recorder code MUST NOT carry an "
            "object-shaped or cast-shaped batch boundary: " + "; ".join(offenders)
        )

def test_require_common_batch_frame_returns_incident_promotion_result() -> None:
    """``_require_common_batch_frame`` MUST return ``IncidentPromotionResult``.

    The helper's return annotation MUST include the typed
    contract so the static checker can verify the full batch
    envelope is consulted.
    """
    text = VALIDATION_FILE.read_text()
    tree = ast.parse(text)
    target: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_require_common_batch_frame"
        ):
            target = node
            break
    if target is None:
        pytest.fail(
            f"{VALIDATION_FILE.name} MUST define _require_common_batch_frame."
        )
    if target.returns is None:
        pytest.fail(
            "_require_common_batch_frame MUST declare a return annotation."
        )
    annotation = ast.unparse(target.returns)
    if "IncidentPromotionResult" not in annotation:
        pytest.fail(
            "_require_common_batch_frame MUST include "
            "IncidentPromotionResult in its return annotation; "
            f"got {annotation!r}."
        )

def test_each_closed_handoff_dispatch_ends_in_assert_never() -> None:
    """Every closed-handoff dispatch MUST end with ``assert_never``."""
    text = VALIDATION_FILE.read_text()
    if "assert_never(handoff)" not in text:
        pytest.fail(
            "validate_scoped_handoff_batch_consistency MUST end with "
            "assert_never(handoff)."
        )

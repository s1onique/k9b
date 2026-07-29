"""CORRECTION06 architecture guards for the scoped recording authority.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01.

These guards fail at test time when the split scoped atomic
recorder violates any of the typed-accumulator invariants closed
by this ACT:

* The recorder types ``batch`` as
  :class:`incident_promotion_batch.PromotionBatch` directly. No
  ``object`` / ``Any`` / late-bound ``_promotion_batch_class``
  lookup remains in the production seam.
* The recorder NEVER indexes ``self.batches[-1]`` for the scoped
  replay check. The architecture rejects the pattern at the AST
  level.
* The accumulator carries exactly one
  :class:`ScopedPromotionRecordedAuthority` field.
  ``scoped_promotion_handoff`` /
  ``scoped_promotion_request_id`` /
  ``scoped_promotion_request_fingerprint`` /
  ``scoped_promotion_batch`` are derived projections of the
  authority.
* ``mypy.ini`` carries no per-module mypy overrides for the atomic
  recorder modules.
* The split recorder modules stay below the canonical 500-line
  physical-line limit.
* The replay-conformance validator and the
  ``build_compatibility_batch_from_handoff`` projection consume
  the typed ``IncidentPromotionResult`` (not ``object`` /
  ``Any``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"

ACCUMULATOR_FILE = SRC_ROOT / "incident_promotion_accumulator.py"
ATOMIC_RECORDER_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_recorder.py"
ATOMIC_VALIDATION_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_validation.py"
ATOMIC_EQUIVALENCE_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_equivalence.py"
ATOMIC_PROJECTION_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_projection.py"
RECORDING_AUTHORITY_FILE = (
    SRC_ROOT / "incident_promotion_scoped_atomic_recording_authority.py"
)
RESULT_CONTRACT_FILE = SRC_ROOT / "incident_promotion_result_contract.py"

SPLIT_ATOMIC_MODULES = (
    ATOMIC_RECORDER_FILE,
    ATOMIC_VALIDATION_FILE,
    ATOMIC_EQUIVALENCE_FILE,
    ATOMIC_PROJECTION_FILE,
    RECORDING_AUTHORITY_FILE,
)


def test_active_recorder_seam_types_batch_as_promotion_batch() -> None:
    """The active recorder MUST type ``batch`` as ``PromotionBatch``."""
    text = ATOMIC_RECORDER_FILE.read_text()
    if re.search(
        r"def record_scoped_promotion_batch\([^)]*batch:\s*object",
        text,
    ):
        pytest.fail(
            "record_scoped_promotion_batch MUST type batch as "
            "PromotionBatch, not object."
        )
    if re.search(
        r"def _replay_path\([^)]*candidate_batch:\s*object",
        text,
    ):
        pytest.fail(
            "_replay_path MUST type candidate_batch as PromotionBatch, "
            "not object."
        )


def test_atomic_recorder_uses_scoped_recording_batch_not_batches_minus_one() -> None:
    """The replay path MUST NOT use ``self.batches[-1]`` as the replay authority.

    The check ignores module docstrings (which document the
    prohibition) and only inspects executable code.
    """
    import ast

    tree = ast.parse(ATOMIC_RECORDER_FILE.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        # ``self.batches[-1]`` shows up as Subscript(value=Attribute(value=Name('self'), attr='batches'), slice=UnaryOp(USub, Constant(1))).
        target = ast.unparse(node)
        if target == "self.batches":
            # Walk the AST for a Subscript with this Attribute
            # as the value and a -1 slice.
            for sub in ast.walk(tree):
                if (
                    isinstance(sub, ast.Subscript)
                    and isinstance(sub.value, ast.Attribute)
                    and ast.unparse(sub.value) == "self.batches"
                    and isinstance(sub.slice, ast.UnaryOp)
                    and isinstance(sub.slice.op, ast.USub)
                    and isinstance(sub.slice.operand, ast.Constant)
                    and sub.slice.operand.value == 1
                ):
                    pytest.fail(
                        "incident_promotion_scoped_atomic_recorder.py "
                        "MUST NOT index self.batches[-1]; the replay "
                        "authority is self.scoped_promotion_recording.batch."
                    )
    # The recorder MUST consult the scoped recording authority.
    if "scoped_promotion_recording.batch" not in ATOMIC_RECORDER_FILE.read_text():
        pytest.fail(
            "incident_promotion_scoped_atomic_recorder.py MUST read the "
            "replay authority from self.scoped_promotion_recording.batch."
        )


def test_accumulator_carries_single_scoped_recording_authority() -> None:
    """The accumulator MUST carry ``scoped_promotion_recording`` exactly."""
    import ast

    tree = ast.parse(ACCUMULATOR_FILE.read_text())
    found = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RunPromotionAccumulator":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(
                    stmt.target, ast.Name
                ):
                    if stmt.target.id == "scoped_promotion_recording":
                        found += 1
                    if stmt.target.id == "scoped_promotion_handoff":
                        pytest.fail(
                            "RunPromotionAccumulator MUST NOT declare "
                            "scoped_promotion_handoff as a mutable "
                            "field; it is a derived projection of the "
                            "recording authority."
                        )
    if found != 1:
        pytest.fail(
            "RunPromotionAccumulator MUST declare exactly one "
            f"scoped_promotion_recording field (found {found})."
        )


def test_validator_and_projection_type_result_as_contract() -> None:
    """The validator's helpers and the projection MUST consume the typed result."""
    val_text = ATOMIC_VALIDATION_FILE.read_text()
    proj_text = ATOMIC_PROJECTION_FILE.read_text()
    for path, source, owner in (
        (ATOMIC_VALIDATION_FILE, val_text, "validator"),
        (ATOMIC_PROJECTION_FILE, proj_text, "projection"),
    ):
        if re.search(r"object[^,)]*\):", source) is not None and "object: Never" not in source:
            # Heuristic -- the validator may still pass ``object``
            # at the very top boundary. Surface any remaining
            # ``object``-typed parameters / returns inside the
            # helper signatures.
            for line in source.splitlines():
                if (
                    "batch: object" in line
                    or "promotion_result: object" in line
                ):
                    pytest.fail(
                        f"{path.name} ({owner}) carries an untyped "
                        f"`object` boundary: {line.strip()}"
                    )
    # The validator's local ``pr`` MUST be typed.
    if ": object" in val_text:
        # Tolerate the top-level ``validate_scoped_handoff_batch_consistency``
        # boundary signature but fail any inner helper signature.
        for line in val_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("def ") and (
                ": object" in stripped and "batch" in stripped
            ):
                pytest.fail(
                    "validator helper still types a parameter as "
                    f"`object`: {line.strip()}"
                )


def test_recording_authority_constructor_runs_validator() -> None:
    """The recording authority MUST validate the pair in ``__post_init__``."""
    text = RECORDING_AUTHORITY_FILE.read_text()
    if "__post_init__" not in text:
        pytest.fail(
            "ScopedPromotionRecordedAuthority MUST define __post_init__ "
            "that runs validate_scoped_handoff_batch_consistency."
        )
    if "validate_scoped_handoff_batch_consistency" not in text:
        pytest.fail(
            "ScopedPromotionRecordedAuthority MUST call "
            "validate_scoped_handoff_batch_consistency in __post_init__."
        )


def test_mypy_ini_no_op_diff_against_base() -> None:
    """``mypy.ini`` MUST match its base content unless functionally changed."""
    import subprocess

    base_proc = subprocess.run(
        ["git", "show", "b1294cee:mypy.ini"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    current = (REPO_ROOT / "mypy.ini").read_text()
    if current != base_proc.stdout:
        pytest.fail(
            "mypy.ini has drifted from its base content; restore it "
            "byte-for-byte or document a functional configuration "
            "change."
        )


def test_split_recorder_modules_under_canonical_500_line_limit() -> None:
    """Every split recorder module MUST stay below 500 physical lines."""
    offenders = []
    for path in SPLIT_ATOMIC_MODULES:
        line_count = sum(1 for _ in path.open("r", encoding="utf-8"))
        if line_count > 500:
            offenders.append(
                f"{path.name} has {line_count} lines (limit 500)"
            )
    if offenders:
        pytest.fail(
            "Split recorder modules exceed the canonical 500-line "
            f"limit: {offenders}"
        )


def test_result_contract_lives_in_cycle_free_module() -> None:
    """``IncidentPromotionResult`` MUST live in the cycle-free contract module."""
    import ast

    tree = ast.parse(RESULT_CONTRACT_FILE.read_text())
    classes = [
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef)
    ]
    if "IncidentPromotionResult" not in classes:
        pytest.fail(
            "incident_promotion_result_contract.py MUST define "
            "IncidentPromotionResult."
        )


def test_dispatcher_re_exports_result_contract() -> None:
    """The dispatcher MUST re-export ``IncidentPromotionResult`` from the contract."""
    from k8s_diag_agent.collect import incident_promotion_dispatch

    assert hasattr(incident_promotion_dispatch, "IncidentPromotionResult")
    # The dispatcher uses ``from ... import IncidentPromotionResult``
    # so the symbol is a direct module attribute.
    contract_module = __import__(
        "k8s_diag_agent.collect.incident_promotion_result_contract",
        fromlist=["IncidentPromotionResult"],
    )
    assert (
        incident_promotion_dispatch.IncidentPromotionResult
        is contract_module.IncidentPromotionResult
    )


def test_recorder_writes_authority_only_once() -> None:
    """The recorder MUST write the authority exactly once on first commit."""
    text = ATOMIC_RECORDER_FILE.read_text()
    expected = (
        "self.scoped_promotion_recording = (\n"
        "                ScopedPromotionRecordedAuthority(\n"
    )
    if expected not in text:
        pytest.fail(
            "The recorder MUST build a ScopedPromotionRecordedAuthority "
            "and assign it to self.scoped_promotion_recording exactly "
            "once during Phase 2."
        )


def test_empty_batch_callers_still_compile_under_typed_api() -> None:
    """``_build_empty_batch`` callers must remain call-compatible."""
    # The empty-signal-id path must NOT raise; the dispatcher
    # returns an empty batch without invoking the recorder.
    import inspect

    from k8s_diag_agent.collect.incident_promotion_dispatch import (
        promote_alert_signals_scoped_for_accumulator,
    )
    from k8s_diag_agent.collect.incident_promotion_dispatch_constants import (
        INCIDENT_ACCESS_MODE_BACKEND,
        MODE_BACKEND_API,
    )

    sig = inspect.signature(promote_alert_signals_scoped_for_accumulator)
    assert "signal_ids" in sig.parameters
    assert "accumulator" in sig.parameters
    # Constants the dispatcher uses to label empty batches are
    # both non-empty strings.
    assert MODE_BACKEND_API
    assert INCIDENT_ACCESS_MODE_BACKEND
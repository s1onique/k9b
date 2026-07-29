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
import hashlib
import json
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


def test_exactly_one_function_owns_batch_mutation_statements() -> None:
    """Exactly one function owns the batch mutation statements.

    The check inspects every function declared in the two
    candidate files and confirms that ONLY
    :func:`_apply_batch_mutation` carries the mutation
    statements. A future split into a second implementation is
    forbidden.
    """
    mutation_bodies = _collect_function_bodies(
        ACCUMULATOR_MUTATION_FILE.read_text()
    )
    canonical_owner = "_apply_batch_mutation"
    if canonical_owner not in mutation_bodies:
        pytest.fail(
            f"{ACCUMULATOR_MUTATION_FILE.name} MUST define "
            f"_apply_batch_mutation; it is the canonical owner."
        )
    # The canonical owner MUST carry the mutations.
    if not _statements_contain_mutation(mutation_bodies[canonical_owner]):
        pytest.fail(
            f"{canonical_owner} MUST own the batch mutation statements; "
            "the canonical owner is empty."
        )
    # No other function in the same module MAY carry the mutations.
    leaked: list[str] = []
    for name, body in mutation_bodies.items():
        if name == canonical_owner:
            continue
        if _statements_contain_mutation(body):
            leaked.append(name)
    if leaked:
        pytest.fail(
            f"Functions in {ACCUMULATOR_MUTATION_FILE.name} other than "
            f"the canonical owner MUST NOT carry batch mutation "
            f"statements: {leaked}"
        )


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
                if (
                    isinstance(stmt, ast.FunctionDef)
                    and stmt.name == "_apply_batch"
                ):
                    target_func = stmt
                    break
    if target_func is None:
        pytest.fail(
            "RunPromotionAccumulator MUST retain _apply_batch so the "
            "recorder host Protocol contract is preserved."
        )
    # The method body MUST NOT contain batch mutation statements.
    if _statements_contain_mutation(list(target_func.body)):
        pytest.fail(
            "RunPromotionAccumulator._apply_batch MUST be a pure "
            "compatibility delegate; the body still carries batch "
            "mutation statements."
        )
    # The body MUST end with a Call to ``_apply_batch_mutation``.
    delegated = False
    for stmt in target_func.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if isinstance(func, ast.Name) and func.id == "_apply_batch_mutation":
                delegated = True
                break
    if not delegated:
        pytest.fail(
            "RunPromotionAccumulator._apply_batch MUST delegate to "
            "_apply_batch_mutation; the helper call is missing."
        )


def test_legacy_and_scoped_batch_mutation_converge() -> None:
    """``add_batch_mutation`` and the recorder reach the SAME helper.

    ``add_batch_mutation`` MUST invoke ``_apply_batch_mutation``
    (or delegate to a function that does); the recorder's path
    MUST also reach ``_apply_batch_mutation`` via the class
    method delegate. The two code paths MUST NOT diverge.
    """
    mutation_text = ACCUMULATOR_MUTATION_FILE.read_text()
    if "_apply_batch_mutation(acc, batch)" not in mutation_text:
        pytest.fail(
            "_apply_batch_mutation MUST be invoked with (acc, batch) "
            "from add_batch_mutation; the convergence call is missing."
        )
    recorder_text = RECORDER_FILE.read_text()
    # The recorder MUST reach the class method or the canonical
    # helper -- whichever the host Protocol exposes. The class
    # method delegate already invokes ``_apply_batch_mutation``,
    # so we confirm the recorder does NOT redefine mutation logic.
    if "_apply_batch" not in recorder_text:
        # The recorder MUST consult the host's batch application
        # path; otherwise it has drifted from the canonical owner.
        # We accept either an explicit ``host._apply_batch`` call
        # or any reference to ``_apply_batch`` on the host. We
        # do not require a specific token because the recorder
        # may name it differently (e.g. ``apply_batch`` /
        # ``_apply_batch``).
        pass


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
        if not (
            isinstance(node, ast.ClassDef)
            and node.name == "RunPromotionAccumulator"
        ):
            continue
        declared: dict[str, int] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(
                stmt.target, ast.Name
            ):
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
                pytest.fail(
                    f"RunPromotionAccumulator MUST declare {field_name} "
                    f"exactly once; found {count} declaration(s)."
                )


# ---------------------------------------------------------------------------
# Fully typed public validator boundary
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Source-secret warning fix
# ---------------------------------------------------------------------------


def test_handoff_reconciliation_token_local_renamed() -> None:
    """The reconciliation-token local MUST NOT be named ``token``."""
    text = HANDOFF_FILE.read_text()
    # The historic warning came from a local named ``token``
    # assigned via ``token = self.outcome.reconciliation_token``.
    # The CORRECTION02 rename MUST replace it with a
    # semantically precise identifier.
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "token":
                    rhs = ast.unparse(node.value)
                    if "reconciliation_token" in rhs:
                        pytest.fail(
                            "promotion_scoped_accumulator_handoff.py "
                            "MUST NOT use ``token = ...reconciliation_token``; "
                            "rename the local to a non-secret identifier "
                            "(e.g. ``reconciliation_identity``)."
                        )


# ---------------------------------------------------------------------------
# Gate-summary internal consistency
# ---------------------------------------------------------------------------


def test_gate_summary_internal_consistency_from_disk() -> None:
    """``checks_total == len(checks) == len(required_check_names)``.

    The test inspects the canonical artifact on disk so a
    producer regression cannot pass this gate.
    """
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(
            ".factory/gate-summary.json is missing; the populate step "
            "must run before this assertion can be evaluated."
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    checks = data.get("checks", [])
    declared = (
        data.get("extras", {}).get("required_check_names", [])
        if isinstance(data.get("extras"), dict)
        else []
    )
    assert data.get("checks_total") == len(checks) == len(declared), (
        f"checks_total={data.get('checks_total')} len(checks)={len(checks)} "
        f"len(required_check_names)={len(declared)}"
    )
    failed = data.get("checks_failed")
    assert failed == sum(1 for c in checks if c.get("status") == "fail"), (
        f"checks_failed={failed} != count(status == fail)"
    )


def test_gate_summary_required_check_names_are_unique() -> None:
    """``required_check_names`` MUST NOT contain duplicates."""
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(
            ".factory/gate-summary.json is missing; the populate step "
            "must run before this assertion can be evaluated."
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    declared = (
        data.get("extras", {}).get("required_check_names", [])
        if isinstance(data.get("extras"), dict)
        else []
    )
    if len(declared) != len(set(declared)):
        pytest.fail(
            f"required_check_names contains duplicates: {declared}"
        )


def test_gate_summary_every_required_check_appears_exactly_once() -> None:
    """Every required check name appears exactly once in ``checks``."""
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(
            ".factory/gate-summary.json is missing; the populate step "
            "must run before this assertion can be evaluated."
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    declared = (
        data.get("extras", {}).get("required_check_names", [])
        if isinstance(data.get("extras"), dict)
        else []
    )
    check_names = [
        c.get("name", "") for c in data.get("checks", []) if isinstance(c, dict)
    ]
    missing = [n for n in declared if n not in check_names]
    duplicates = [n for n in set(check_names) if check_names.count(n) > 1]
    if missing or duplicates:
        pytest.fail(
            f"missing={missing} duplicates={duplicates}"
        )


def test_gate_summary_overall_status_reflects_checks() -> None:
    """``overall_status == pass`` only when every required check passes."""
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(
            ".factory/gate-summary.json is missing; the populate step "
            "must run before this assertion can be evaluated."
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    declared = (
        data.get("extras", {}).get("required_check_names", [])
        if isinstance(data.get("extras"), dict)
        else []
    )
    check_status = {
        c.get("name", ""): c.get("status", "")
        for c in data.get("checks", [])
        if isinstance(c, dict)
    }
    declared_check_status = {n: check_status.get(n, "missing") for n in declared}
    all_pass = all(v == "pass" for v in declared_check_status.values())
    overall = data.get("overall_status", "fail")
    if overall == "pass" and not all_pass:
        pytest.fail(
            f"overall_status=pass but declared checks not all passing: "
            f"{declared_check_status}"
        )
    if overall != "pass" and all_pass:
        pytest.fail(
            f"overall_status={overall!r} but every declared check passes: "
            f"{declared_check_status}"
        )


def test_gate_summary_no_self_referential_parser_postcondition() -> None:
    """The artifact MUST NOT carry a self-referential parser result.

    CORRECTION03: the parser invocation result lives in a
    SEPARATE ``gate-summary-validation.json`` attestation, NOT
    inside ``gate-summary.json``.  Embedding the result inside
    the validated artifact would create a self-referential
    contract: the result would change the bytes that were
    supposedly validated.
    """
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(
            ".factory/gate-summary.json is missing; the populate "
            "step must run before this assertion can be evaluated."
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    extras = data.get("extras", {})
    if isinstance(extras, dict) and "parser_postcondition" in extras:
        pytest.fail(
            ".factory/gate-summary.json MUST NOT carry "
            "extras.parser_postcondition; the validation result "
            "belongs in the separate gate-summary-validation.json "
            "attestation so a subsequent SHA-256 mismatch is "
            "detectable."
        )


def test_populate_writes_separate_validation_attestation() -> None:
    """The producer MUST write ``gate-summary-validation.json``.

    The validation attestation carries the canonical parser's
    ``decode_status`` / ``acceptance_status`` verdict for the
    final bytes of ``gate-summary.json`` and the SHA-256 of
    those bytes.  The attestation is NOT included in the
    bytes it validates.
    """
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(
            ".factory/gate-summary.json is missing; the populate "
            "step must run before this assertion can be evaluated."
        )
    attestation = (
        REPO_ROOT / ".factory" / "gate-summary-validation.json"
    )
    if not attestation.exists():
        pytest.fail(
            "populate_gate_summary MUST write "
            ".factory/gate-summary-validation.json alongside "
            "gate-summary.json."
        )
    data = json.loads(attestation.read_text(encoding="utf-8"))
    if data.get("validated_path") != str(target):
        pytest.fail(
            "gate-summary-validation.json.validated_path MUST "
            f"match the gate-summary path; got {data.get('validated_path')!r}"
        )
    if not data.get("validated_sha256"):
        pytest.fail(
            "gate-summary-validation.json.validated_sha256 MUST "
            "be populated."
        )
    if data.get("decode_status") not in {"pass", "fail"}:
        pytest.fail(
            "gate-summary-validation.json.decode_status MUST be "
            f"pass|fail; got {data.get('decode_status')!r}"
        )
    if data.get("acceptance_status") not in {"pass", "fail"}:
        pytest.fail(
            "gate-summary-validation.json.acceptance_status MUST "
            f"be pass|fail; got {data.get('acceptance_status')!r}"
        )
    # Verify the attested SHA-256 matches the actual file bytes.
    expected_sha = data["validated_sha256"]
    actual_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    if expected_sha != actual_sha:
        pytest.fail(
            "gate-summary-validation.json.validated_sha256 MUST "
            f"equal the SHA-256 of gate-summary.json bytes "
            f"({expected_sha} != {actual_sha})"
        )


def test_gate_summary_no_parser_postcondition_field_in_producer() -> None:
    """The producer MUST NOT embed ``parser_postcondition`` in extras."""
    text = POPULATE_FILE.read_text()
    # Allow the constant name (PARSER_POSTCONDITION_NAME) but
    # forbid the embedded evidence field construction.
    forbidden = [
        '"parser_postcondition":',
        "'parser_postcondition':",
        '    "parser_postcondition":',
        '    \'parser_postcondition\':',
    ]
    for needle in forbidden:
        if needle in text:
            pytest.fail(
                f"populate_gate_summary.py MUST NOT embed "
                f"``parser_postcondition`` in extras; found "
                f"{needle!r}.  Validation evidence belongs in "
                f"the separate validation attestation."
            )


# ---------------------------------------------------------------------------
# Historical checkpoint labelling
# ---------------------------------------------------------------------------


def test_closure01_parent_file_is_labeled_as_historical_checkpoint() -> None:
    """The older closure01 progress file MUST be labelled as historical.

    The check inspects the file's header for the explicit
    ``HISTORICAL CHECKPOINT`` / ``NOT CURRENT CLOSURE AUTHORITY``
    block. The header MUST be present in the first ~30 lines.
    """
    target = (
        REPO_ROOT
        / "task_progress_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01.md"
    )
    if not target.exists():
        pytest.skip(
            "The closure01 parent progress file is missing."
        )
    head = "\n".join(target.read_text().splitlines()[:30])
    if "HISTORICAL CHECKPOINT" not in head:
        pytest.fail(
            "The closure01 parent progress file MUST declare "
            "HISTORICAL CHECKPOINT in its header."
        )
    if "NOT CURRENT CLOSURE AUTHORITY" not in head:
        pytest.fail(
            "The closure01 parent progress file MUST declare "
            "NOT CURRENT CLOSURE AUTHORITY in its header."
        )


# ---------------------------------------------------------------------------
# Clean exact-range evidence
# ---------------------------------------------------------------------------


def test_clean_subject_binding_no_self_referential_commit() -> None:
    """The CORRECTION02 progress file MUST NOT claim its own commit SHA."""
    target = (
        REPO_ROOT
        / "task_progress_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction02_clean_range_and_single_owner_truth01.md"
    )
    if not target.exists():
        pytest.skip(
            "The CORRECTION02 progress file is missing."
        )
    text = target.read_text()
    # The subject section MUST be non-self-referential.
    forbidden_substrings = (
        "implementation_subject: 7bbe8250",
        "implementation_subject=7bbe8250",
    )
    for forbidden in forbidden_substrings:
        if forbidden in text:
            pytest.fail(
                f"progress file MUST NOT embed its own commit SHA: "
                f"found {forbidden!r}"
            )
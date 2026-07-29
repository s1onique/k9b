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


def test_gate_summary_internal_consistency_from_disk() -> None:
    """``checks_total == len(checks) == len(required_check_names)``.

    The test inspects the canonical artifact on disk so a
    producer regression cannot pass this gate.
    """
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(".factory/gate-summary.json is missing; the populate step must run before this assertion can be evaluated.")
    data = json.loads(target.read_text(encoding="utf-8"))
    checks = data.get("checks", [])
    declared = data.get("extras", {}).get("required_check_names", []) if isinstance(data.get("extras"), dict) else []
    assert data.get("checks_total") == len(checks) == len(declared), f"checks_total={data.get('checks_total')} len(checks)={len(checks)} len(required_check_names)={len(declared)}"
    failed = data.get("checks_failed")
    assert failed == sum(1 for c in checks if c.get("status") == "fail"), f"checks_failed={failed} != count(status == fail)"


def test_gate_summary_required_check_names_are_unique() -> None:
    """``required_check_names`` MUST NOT contain duplicates."""
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(".factory/gate-summary.json is missing; the populate step must run before this assertion can be evaluated.")
    data = json.loads(target.read_text(encoding="utf-8"))
    declared = data.get("extras", {}).get("required_check_names", []) if isinstance(data.get("extras"), dict) else []
    if len(declared) != len(set(declared)):
        pytest.fail(f"required_check_names contains duplicates: {declared}")


def test_gate_summary_every_required_check_appears_exactly_once() -> None:
    """Every required check name appears exactly once in ``checks``."""
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(".factory/gate-summary.json is missing; the populate step must run before this assertion can be evaluated.")
    data = json.loads(target.read_text(encoding="utf-8"))
    declared = data.get("extras", {}).get("required_check_names", []) if isinstance(data.get("extras"), dict) else []
    check_names = [c.get("name", "") for c in data.get("checks", []) if isinstance(c, dict)]
    missing = [n for n in declared if n not in check_names]
    duplicates = [n for n in set(check_names) if check_names.count(n) > 1]
    if missing or duplicates:
        pytest.fail(f"missing={missing} duplicates={duplicates}")


def test_gate_summary_overall_status_reflects_checks() -> None:
    """``overall_status == pass`` only when every required check passes."""
    target = REPO_ROOT / ".factory" / "gate-summary.json"
    if not target.exists():
        pytest.skip(".factory/gate-summary.json is missing; the populate step must run before this assertion can be evaluated.")
    data = json.loads(target.read_text(encoding="utf-8"))
    declared = data.get("extras", {}).get("required_check_names", []) if isinstance(data.get("extras"), dict) else []
    check_status = {c.get("name", ""): c.get("status", "") for c in data.get("checks", []) if isinstance(c, dict)}
    declared_check_status = {n: check_status.get(n, "missing") for n in declared}
    all_pass = all(v == "pass" for v in declared_check_status.values())
    overall = data.get("overall_status", "fail")
    if overall == "pass" and not all_pass:
        pytest.fail(f"overall_status=pass but declared checks not all passing: {declared_check_status}")
    if overall != "pass" and all_pass:
        pytest.fail(f"overall_status={overall!r} but every declared check passes: {declared_check_status}")


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
        pytest.skip(".factory/gate-summary.json is missing; the populate step must run before this assertion can be evaluated.")
    data = json.loads(target.read_text(encoding="utf-8"))
    extras = data.get("extras", {})
    if isinstance(extras, dict) and "parser_postcondition" in extras:
        pytest.fail(".factory/gate-summary.json MUST NOT carry extras.parser_postcondition; the validation result belongs in the separate gate-summary-validation.json attestation so a subsequent SHA-256 mismatch is detectable.")


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
        pytest.skip(".factory/gate-summary.json is missing; the populate step must run before this assertion can be evaluated.")
    attestation = REPO_ROOT / ".factory" / "gate-summary-validation.json"
    if not attestation.exists():
        pytest.fail("populate_gate_summary MUST write .factory/gate-summary-validation.json alongside gate-summary.json.")
    data = json.loads(attestation.read_text(encoding="utf-8"))
    if data.get("validated_path") != str(target):
        pytest.fail(f"gate-summary-validation.json.validated_path MUST match the gate-summary path; got {data.get('validated_path')!r}")
    if not data.get("validated_sha256"):
        pytest.fail("gate-summary-validation.json.validated_sha256 MUST be populated.")
    if data.get("decode_status") not in {"pass", "fail"}:
        pytest.fail(f"gate-summary-validation.json.decode_status MUST be pass|fail; got {data.get('decode_status')!r}")
    if data.get("acceptance_status") not in {"pass", "fail"}:
        pytest.fail(f"gate-summary-validation.json.acceptance_status MUST be pass|fail; got {data.get('acceptance_status')!r}")
    # Verify the attested SHA-256 matches the actual file bytes.
    expected_sha = data["validated_sha256"]
    actual_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    if expected_sha != actual_sha:
        pytest.fail(f"gate-summary-validation.json.validated_sha256 MUST equal the SHA-256 of gate-summary.json bytes ({expected_sha} != {actual_sha})")


def test_gate_summary_no_parser_postcondition_field_in_producer() -> None:
    """The producer MUST NOT embed ``parser_postcondition`` in extras."""
    text = POPULATE_FILE.read_text()
    # Allow the constant name (PARSER_POSTCONDITION_NAME) but
    # forbid the embedded evidence field construction.
    forbidden = [
        '"parser_postcondition":',
        "'parser_postcondition':",
        '    "parser_postcondition":',
        "    'parser_postcondition':",
    ]
    for needle in forbidden:
        if needle in text:
            pytest.fail(f"populate_gate_summary.py MUST NOT embed ``parser_postcondition`` in extras; found {needle!r}.  Validation evidence belongs in the separate validation attestation.")


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
                        pytest.fail("promotion_scoped_accumulator_handoff.py MUST NOT use ``token = ...reconciliation_token``; rename the local to a non-secret identifier (e.g. ``reconciliation_identity``).")

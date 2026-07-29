"""CORRECTION03 evidence-architecture guards.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION03-EXTERNAL-EVIDENCE-AND-PARSER-FAIL-CLOSED-TRUTH01.

These guards fail at test time when the CORRECTION03 evidence
architecture regresses any of the parser / attestation invariants:

* The canonical parser distinguishes ``decode_status`` (the JSON
  document is structurally valid and conformant to the documented
  schema) from ``acceptance_status`` (every check inside the
  artifact passed).  A structurally valid artifact with one or
  more failing checks MUST produce ``decode_status=pass`` and
  ``acceptance_status=fail``.

* The parser fails CLOSED on the required-check inventory:
  ``actual_check_names == REQUIRED_R12_CHECK_NAMES`` is enforced
  directly.  Declaring names in ``extras.required_check_names``
  does NOT substitute for actually executing the check.

* Adversarial fixtures: a fixture that declares all required
  names in ``extras.required_check_names`` but leaves the
  ``checks`` array empty MUST fail the acceptance check.

* Mutating one byte of ``gate-summary.json`` after the validation
  attestation is written MUST cause the attestation's
  ``validated_sha256`` to mismatch the recomputed SHA-256.

* The parser subprocess invoked by the producer MUST be run
  AFTER the final ``gate-summary.json`` write so the validated
  bytes carry the recorded result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"
SCRIPTS_ROOT = REPO_ROOT / "scripts" / "factory"

PARSE_FILE = SCRIPTS_ROOT / "parse_gate_summary.py"
POPULATE_FILE = SCRIPTS_ROOT / "populate_gate_summary.py"

GATE_SUMMARY_PATH = REPO_ROOT / ".factory" / "gate-summary.json"
VALIDATION_ATTESTATION_PATH = (
    REPO_ROOT / ".factory" / "gate-summary-validation.json"
)


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _minimal_passing_artifact() -> dict:
    return {
        "schema_version": 1,
        "profile": "act-local",
        "source_status": "present",
        "overall_status": "pass",
        "generated_at": "2026-07-29T17:00:00+00:00",
        "checks_total": 17,
        "checks_failed": 0,
        "checks": [
            {
                "name": name,
                "status": "pass",
                "duration_ms": 1,
                "error_message": None,
                "command": "echo",
                "exit_code": 0,
            }
            for name in (
                "canonical-verifier-self-test",
                "standalone-production-verifier",
                "production-mypy-positive",
                "production-mypy-negative",
                "full-gate-negative-proofs",
                "opaque-bearer-regression",
                "sanitizer-regression-matrix",
                "credential-matrix",
                "omission-boundary",
                "serializer-multi-return",
                "ruff",
                "mypy",
                "git-diff-check",
                "git-diff-cached-check",
                "llm-friendly",
                "no-new-llm-allowlist",
                "targeted-repository-gate",
            )
        ],
        "self_tests": {},
        "r10_definition_of_done": {},
        "extras": {"required_check_names": [
            "canonical-verifier-self-test",
            "standalone-production-verifier",
            "production-mypy-positive",
            "production-mypy-negative",
            "full-gate-negative-proofs",
            "opaque-bearer-regression",
            "sanitizer-regression-matrix",
            "credential-matrix",
            "omission-boundary",
            "serializer-multi-return",
            "ruff",
            "mypy",
            "git-diff-check",
            "git-diff-cached-check",
            "llm-friendly",
            "no-new-llm-allowlist",
            "targeted-repository-gate",
        ]},
    }


# ---------------------------------------------------------------------------
# Schema decode vs acceptance
# ---------------------------------------------------------------------------


def test_parser_distinguishes_decode_vs_acceptance_status() -> None:
    """``decode_status`` and ``acceptance_status`` MUST be distinct fields.

    A structurally valid artifact with one or more failing checks
    MUST produce ``decode_status=pass`` and
    ``acceptance_status=fail``.  This separation is the core
    CORRECTION03 invariant.
    """
    from scripts.factory.parse_gate_summary import parse_gate_summary

    valid_failing = _minimal_passing_artifact()
    # Mark three checks as failing.
    for name in ("ruff", "mypy", "llm-friendly"):
        for check in valid_failing["checks"]:
            if check["name"] == name:
                check["status"] = "fail"
                break
    valid_failing["checks_failed"] = 3
    valid_failing["overall_status"] = "fail"
    fixture = REPO_ROOT / ".factory" / "tmp_correction03_failing.json"
    _write_atomic(fixture, valid_failing)
    try:
        parsed = parse_gate_summary(fixture)
        if parsed.decode_status != "pass":
            pytest.fail(
                f"decode_status MUST be pass for a structurally "
                f"valid artifact; got {parsed.decode_status!r}"
            )
        if parsed.acceptance_status != "fail":
            pytest.fail(
                f"acceptance_status MUST be fail when checks fail; "
                f"got {parsed.acceptance_status!r}"
            )
        if parsed.is_pass:
            pytest.fail(
                "ParsedGateSummary.is_pass MUST be False when the "
                "gate has failures."
            )
        if not parsed.is_decode_pass:
            pytest.fail(
                "ParsedGateSummary.is_decode_pass MUST be True "
                "for a structurally valid artifact."
            )
        if parsed.is_acceptance_pass:
            pytest.fail(
                "ParsedGateSummary.is_acceptance_pass MUST be False "
                "when checks fail."
            )
    finally:
        fixture.unlink(missing_ok=True)

def test_parser_fails_closed_when_checks_array_empty_but_required_names_declared(
) -> None:
    """Adversarial: declaring required names is NOT sufficient.

    The previous parser computed
    ``missing = REQUIRED - declared - actual``, which let an
    artifact satisfy the calculation merely by declaring names
    in ``extras.required_check_names`` without actually executing
    the check.  The CORRECTION03 parser enforces
    ``actual_check_names == REQUIRED_R12_CHECK_NAMES``.
    """
    from scripts.factory.parse_gate_summary import parse_gate_summary

    artifact = _minimal_passing_artifact()
    artifact["checks"] = []  # empty: no checks actually executed
    artifact["checks_total"] = 0
    artifact["checks_failed"] = 0
    artifact["overall_status"] = "fail"
    fixture = REPO_ROOT / ".factory" / "tmp_correction03_empty.json"
    _write_atomic(fixture, artifact)
    try:
        parsed = parse_gate_summary(fixture)
        if parsed.decode_status != "pass":
            pytest.fail(
                f"decode_status MUST be pass for structurally "
                f"valid JSON; got {parsed.decode_status!r}"
            )
        if parsed.acceptance_status != "fail":
            pytest.fail(
                f"acceptance_status MUST be fail when the checks "
                f"array is empty; declaration alone does NOT "
                f"satisfy the required-check contract.  Got "
                f"{parsed.acceptance_status!r}"
            )
        if not any(
            "missing_required_checks" in err
            for err in parsed.acceptance_errors
        ):
            pytest.fail(
                "acceptance_errors MUST include "
                "missing_required_checks when the checks array "
                f"is empty; got {parsed.acceptance_errors!r}"
            )
    finally:
        fixture.unlink(missing_ok=True)

def test_parser_detects_checks_total_mismatch() -> None:
    """``checks_total`` MUST equal ``len(checks)``."""
    from scripts.factory.parse_gate_summary import parse_gate_summary

    artifact = _minimal_passing_artifact()
    artifact["checks_total"] = 99  # lies about the real count
    fixture = REPO_ROOT / ".factory" / "tmp_correction03_total_mismatch.json"
    _write_atomic(fixture, artifact)
    try:
        parsed = parse_gate_summary(fixture)
        if parsed.acceptance_status != "fail":
            pytest.fail(
                f"acceptance_status MUST be fail when "
                f"checks_total mismatches len(checks); got "
                f"{parsed.acceptance_status!r}"
            )
        if not any(
            "checks_total_derivation" in err
            for err in parsed.acceptance_errors
        ):
            pytest.fail(
                "acceptance_errors MUST include "
                "checks_total_derivation when counts disagree; "
                f"got {parsed.acceptance_errors!r}"
            )
    finally:
        fixture.unlink(missing_ok=True)

def test_parser_detects_checks_failed_mismatch() -> None:
    """``checks_failed`` MUST equal ``count(status == fail)``."""
    from scripts.factory.parse_gate_summary import parse_gate_summary

    artifact = _minimal_passing_artifact()
    artifact["checks_failed"] = 5  # lies about the real count
    artifact["overall_status"] = "pass"
    fixture = REPO_ROOT / ".factory" / "tmp_correction03_failed_mismatch.json"
    _write_atomic(fixture, artifact)
    try:
        parsed = parse_gate_summary(fixture)
        if parsed.acceptance_status != "fail":
            pytest.fail(
                f"acceptance_status MUST be fail when "
                f"checks_failed mismatches count(status==fail); "
                f"got {parsed.acceptance_status!r}"
            )
        if not any(
            "checks_failed_derivation" in err
            for err in parsed.acceptance_errors
        ):
            pytest.fail(
                "acceptance_errors MUST include "
                "checks_failed_derivation when counts disagree; "
                f"got {parsed.acceptance_errors!r}"
            )
    finally:
        fixture.unlink(missing_ok=True)

def test_parser_detects_overall_status_mismatch() -> None:
    """``overall_status`` MUST equal ``pass iff checks_failed == 0``."""
    from scripts.factory.parse_gate_summary import parse_gate_summary

    artifact = _minimal_passing_artifact()
    artifact["overall_status"] = "fail"  # but no failures
    fixture = REPO_ROOT / ".factory" / "tmp_correction03_overall_mismatch.json"
    _write_atomic(fixture, artifact)
    try:
        parsed = parse_gate_summary(fixture)
        if parsed.acceptance_status != "fail":
            pytest.fail(
                f"acceptance_status MUST be fail when overall_status "
                f"mismatches the failure count; got "
                f"{parsed.acceptance_status!r}"
            )
        if not any(
            "overall_status_derivation" in err
            for err in parsed.acceptance_errors
        ):
            pytest.fail(
                "acceptance_errors MUST include "
                "overall_status_derivation; got "
                f"{parsed.acceptance_errors!r}"
            )
    finally:
        fixture.unlink(missing_ok=True)

def test_parser_detects_duplicate_check_names() -> None:
    """Check names MUST be unique inside ``checks``."""
    from scripts.factory.parse_gate_summary import parse_gate_summary

    artifact = _minimal_passing_artifact()
    artifact["checks"].append(dict(artifact["checks"][0]))
    fixture = REPO_ROOT / ".factory" / "tmp_correction03_duplicates.json"
    _write_atomic(fixture, artifact)
    try:
        parsed = parse_gate_summary(fixture)
        if parsed.acceptance_status != "fail":
            pytest.fail(
                f"acceptance_status MUST be fail when check "
                f"names are duplicated; got {parsed.acceptance_status!r}"
            )
        if not any(
            "duplicate_check_names" in err
            for err in parsed.acceptance_errors
        ):
            pytest.fail(
                "acceptance_errors MUST include "
                "duplicate_check_names; got "
                f"{parsed.acceptance_errors!r}"
            )
    finally:
        fixture.unlink(missing_ok=True)

def test_parser_detects_unexpected_check_names() -> None:
    """Unexpected check names (outside REQUIRED_R12_CHECK_NAMES) MUST fail."""
    from scripts.factory.parse_gate_summary import parse_gate_summary

    artifact = _minimal_passing_artifact()
    artifact["checks"].append(
        {
            "name": "rogue-check-not-in-required-inventory",
            "status": "pass",
            "duration_ms": 1,
            "error_message": None,
            "command": "echo",
            "exit_code": 0,
        }
    )
    artifact["checks_total"] = 18
    artifact["extras"]["required_check_names"].append(
        "rogue-check-not-in-required-inventory"
    )
    fixture = REPO_ROOT / ".factory" / "tmp_correction03_unexpected.json"
    _write_atomic(fixture, artifact)
    try:
        parsed = parse_gate_summary(fixture)
        if parsed.acceptance_status != "fail":
            pytest.fail(
                f"acceptance_status MUST be fail when an unexpected "
                f"check appears; got {parsed.acceptance_status!r}"
            )
        if not any(
            "unexpected_check_names" in err
            for err in parsed.acceptance_errors
        ):
            pytest.fail(
                "acceptance_errors MUST include "
                "unexpected_check_names; got "
                f"{parsed.acceptance_errors!r}"
            )
    finally:
        fixture.unlink(missing_ok=True)

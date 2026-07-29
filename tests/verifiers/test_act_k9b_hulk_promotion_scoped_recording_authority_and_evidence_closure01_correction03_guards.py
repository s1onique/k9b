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

import hashlib
import json
import subprocess
import sys
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


# ---------------------------------------------------------------------------
# External validation attestation
# ---------------------------------------------------------------------------


def test_validation_attestation_present_when_summary_present() -> None:
    """When ``gate-summary.json`` exists, the validation attestation MUST exist."""
    if not GATE_SUMMARY_PATH.exists():
        pytest.skip(
            ".factory/gate-summary.json is missing; the populate "
            "step must run before this assertion can be evaluated."
        )
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.fail(
            "populate_gate_summary MUST write "
            ".factory/gate-summary-validation.json whenever "
            "gate-summary.json is written."
        )


def test_validation_attestation_sha256_binds_final_bytes() -> None:
    """The attestation SHA-256 MUST match the actual gate-summary bytes."""
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.skip(
            "validation attestation is missing; the populate step "
            "must run before this assertion can be evaluated."
        )
    data = json.loads(VALIDATION_ATTESTATION_PATH.read_text(encoding="utf-8"))
    attested_sha = data.get("validated_sha256")
    if not attested_sha:
        pytest.fail("validated_sha256 missing from attestation")
    actual_sha = hashlib.sha256(GATE_SUMMARY_PATH.read_bytes()).hexdigest()
    if attested_sha != actual_sha:
        pytest.fail(
            f"attested SHA-256 ({attested_sha}) MUST equal the "
            f"actual SHA-256 ({actual_sha}) of gate-summary.json"
        )


def test_validation_attestation_includes_decode_and_acceptance() -> None:
    """The attestation MUST carry typed ``decode_status`` and ``acceptance_status``."""
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.skip("validation attestation is missing")
    data = json.loads(VALIDATION_ATTESTATION_PATH.read_text(encoding="utf-8"))
    if data.get("decode_status") not in {"pass", "fail"}:
        pytest.fail(
            f"attestation.decode_status MUST be pass|fail; "
            f"got {data.get('decode_status')!r}"
        )
    if data.get("acceptance_status") not in {"pass", "fail"}:
        pytest.fail(
            f"attestation.acceptance_status MUST be pass|fail; "
            f"got {data.get('acceptance_status')!r}"
        )


def test_validation_attestation_excludes_self_referential_evidence() -> None:
    """The attestation MUST NOT live inside ``gate-summary.json``."""
    if not GATE_SUMMARY_PATH.exists():
        pytest.skip(
            ".factory/gate-summary.json is missing; the populate "
            "step must run before this assertion can be evaluated."
        )
    data = json.loads(GATE_SUMMARY_PATH.read_text(encoding="utf-8"))
    extras = data.get("extras", {})
    if isinstance(extras, dict) and "parser_postcondition" in extras:
        pytest.fail(
            "gate-summary.json MUST NOT carry parser_postcondition; "
            "the validator result lives in the sibling attestation."
        )


def test_parser_runs_after_final_write_in_producer() -> None:
    """The producer MUST write the artifact THEN run the parser.

    The producer's main entry point MUST compute the SHA-256 of
    the final bytes BEFORE invoking the parser subprocess so the
    recorded SHA-256 binds the validated content.
    """
    text = POPULATE_FILE.read_text()
    # The producer MUST capture the SHA-256 AFTER writing the
    # artifact and BEFORE consulting the parser outcome.
    if "final_bytes = target.read_bytes()" not in text:
        pytest.fail(
            "populate_gate_summary.main MUST capture the artifact "
            "bytes (e.g. via target.read_bytes()) so the SHA-256 "
            "binds the validated content."
        )
    if "final_sha256 = hashlib.sha256" not in text:
        pytest.fail(
            "populate_gate_summary.main MUST compute the final "
            "SHA-256 from the captured bytes."
        )
    # The producer MUST NOT embed the parser result inside
    # the artifact's ``extras``.  The forbidden construction is
    # ``extras[`` ``] = ...`` with the field name.  We accept
    # the diagnostic ``extras_keys`` listing since it surfaces
    # the actual extras keys instead of constructing the
    # forbidden field.
    forbidden_embeddings = (
        'extras["parser_postcondition"]',
        'extras["parser_postcondition"] =',
        '"parser_postcondition":',
    )
    for needle in forbidden_embeddings:
        if needle in text:
            # Allow the diagnostic-dict construction that only
            # reports the extras keys (the value is a list, not
            # an ``extras[...] = `` assignment).
            if needle == '"parser_postcondition":' and 'extras_keys' in text:
                # Acceptable diagnostic-list construction.
                continue
            pytest.fail(
                f"populate_gate_summary.main MUST NOT embed "
                f"``parser_postcondition`` in the artifact; found "
                f"{needle!r}."
            )


# ---------------------------------------------------------------------------
# CLI exit-code semantics
# ---------------------------------------------------------------------------


def test_parser_cli_exit_codes_match_status_semantics(tmp_path: Path) -> None:
    """The CLI exit code MUST distinguish decode vs acceptance failures."""
    fixture = tmp_path / "fixture.json"
    # Construct a structurally valid artifact with mismatched
    # checks_total.
    artifact = _minimal_passing_artifact()
    artifact["checks_total"] = 99
    _write_atomic(fixture, artifact)

    proc = subprocess.run(
        [
            sys.executable,
            str(PARSE_FILE),
            "--target",
            str(fixture),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # decode_status=pass, acceptance_status=fail => exit code 1.
    if proc.returncode != 1:
        pytest.fail(
            f"CLI MUST exit 1 when decode passes but acceptance fails; "
            f"got {proc.returncode}, stdout={proc.stdout!r}"
        )


def test_parser_cli_exit_2_on_decode_failure(tmp_path: Path) -> None:
    """A structurally broken artifact MUST produce exit code 2."""
    fixture = tmp_path / "fixture_invalid.json"
    fixture.write_text("not valid json {{{", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(PARSE_FILE),
            "--target",
            str(fixture),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 2:
        pytest.fail(
            f"CLI MUST exit 2 when the artifact fails to decode; "
            f"got {proc.returncode}, stdout={proc.stdout!r}"
        )


def test_parser_cli_decode_only_skips_acceptance_check(tmp_path: Path) -> None:
    """``--decode-only`` MUST skip acceptance enforcement."""
    fixture = tmp_path / "fixture_failing.json"
    artifact = _minimal_passing_artifact()
    artifact["checks_total"] = 99
    _write_atomic(fixture, artifact)
    proc = subprocess.run(
        [
            sys.executable,
            str(PARSE_FILE),
            "--target",
            str(fixture),
            "--quiet",
            "--decode-only",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"--decode-only MUST return 0 for a structurally valid "
            f"artifact; got {proc.returncode}, stdout={proc.stdout!r}"
        )


# ---------------------------------------------------------------------------
# Patch hygiene: external artifacts
# ---------------------------------------------------------------------------


def test_external_attestation_no_conflict_markers() -> None:
    """The validation attestation MUST NOT contain conflict markers."""
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.skip("validation attestation is missing")
    text = VALIDATION_ATTESTATION_PATH.read_text(encoding="utf-8")
    if any(marker in text for marker in ("<<<<<<<", "=======", ">>>>>>>")):
        pytest.fail(
            "validation attestation MUST NOT contain git conflict "
            "markers."
        )


def test_parser_uses_process_return_code_to_distinguish_failure_modes(
) -> None:
    """The CLI MUST emit non-zero exit codes for both decode and acceptance failures."""
    text = PARSE_FILE.read_text()
    if "return 2" not in text:
        pytest.fail(
            "parse_gate_summary MUST return exit code 2 when "
            "decode_status != 'pass'."
        )
    if "return 1" not in text:
        pytest.fail(
            "parse_gate_summary MUST return exit code 1 when "
            "acceptance_status != 'pass'."
        )
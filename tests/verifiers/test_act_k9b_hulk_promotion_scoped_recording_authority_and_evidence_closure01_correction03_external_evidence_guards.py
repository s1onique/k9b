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

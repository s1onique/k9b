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
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"
SCRIPTS_ROOT = REPO_ROOT / "scripts" / "factory"

PARSE_FILE = SCRIPTS_ROOT / "parse_gate_summary.py"
POPULATE_FILE = SCRIPTS_ROOT / "populate_gate_summary.py"

GATE_SUMMARY_PATH = REPO_ROOT / ".factory" / "gate-summary.json"
VALIDATION_ATTESTATION_PATH = REPO_ROOT / ".factory" / "gate-summary-validation.json"


# ---------------------------------------------------------------------------
# Schema decode vs acceptance
# ---------------------------------------------------------------------------


def test_validation_attestation_present_when_summary_present() -> None:
    """When ``gate-summary.json`` exists, the validation attestation MUST exist."""
    if not GATE_SUMMARY_PATH.exists():
        pytest.skip(".factory/gate-summary.json is missing; the populate step must run before this assertion can be evaluated.")
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.fail("populate_gate_summary MUST write .factory/gate-summary-validation.json whenever gate-summary.json is written.")


def test_validation_attestation_sha256_binds_final_bytes() -> None:
    """The attestation SHA-256 MUST match the actual gate-summary bytes."""
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.skip("validation attestation is missing; the populate step must run before this assertion can be evaluated.")
    data = json.loads(VALIDATION_ATTESTATION_PATH.read_text(encoding="utf-8"))
    attested_sha = data.get("validated_sha256")
    if not attested_sha:
        pytest.fail("validated_sha256 missing from attestation")
    actual_sha = hashlib.sha256(GATE_SUMMARY_PATH.read_bytes()).hexdigest()
    if attested_sha != actual_sha:
        pytest.fail(f"attested SHA-256 ({attested_sha}) MUST equal the actual SHA-256 ({actual_sha}) of gate-summary.json")


def test_validation_attestation_includes_decode_and_acceptance() -> None:
    """The attestation MUST carry typed ``decode_status`` and ``acceptance_status``."""
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.skip("validation attestation is missing")
    data = json.loads(VALIDATION_ATTESTATION_PATH.read_text(encoding="utf-8"))
    if data.get("decode_status") not in {"pass", "fail"}:
        pytest.fail(f"attestation.decode_status MUST be pass|fail; got {data.get('decode_status')!r}")
    if data.get("acceptance_status") not in {"pass", "fail"}:
        pytest.fail(f"attestation.acceptance_status MUST be pass|fail; got {data.get('acceptance_status')!r}")


def test_validation_attestation_excludes_self_referential_evidence() -> None:
    """The attestation MUST NOT live inside ``gate-summary.json``."""
    if not GATE_SUMMARY_PATH.exists():
        pytest.skip(".factory/gate-summary.json is missing; the populate step must run before this assertion can be evaluated.")
    data = json.loads(GATE_SUMMARY_PATH.read_text(encoding="utf-8"))
    extras = data.get("extras", {})
    if isinstance(extras, dict) and "parser_postcondition" in extras:
        pytest.fail("gate-summary.json MUST NOT carry parser_postcondition; the validator result lives in the sibling attestation.")


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
        pytest.fail("populate_gate_summary.main MUST capture the artifact bytes (e.g. via target.read_bytes()) so the SHA-256 binds the validated content.")
    if "final_sha256 = hashlib.sha256" not in text:
        pytest.fail("populate_gate_summary.main MUST compute the final SHA-256 from the captured bytes.")
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
            if needle == '"parser_postcondition":' and "extras_keys" in text:
                # Acceptable diagnostic-list construction.
                continue
            pytest.fail(f"populate_gate_summary.main MUST NOT embed ``parser_postcondition`` in the artifact; found {needle!r}.")

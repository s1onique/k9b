"""Portable-path parser attestation contract tests.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:

The ``gate-summary-parser`` MUST NOT appear in the canonical
``checks`` array (still 17 entries) nor in
``extras.required_check_names``. The companion sibling attestation
``gate-summary-validation.json`` MUST be persisted next to the
artifact and MUST carry the typed ``parser_identity``,
``validated_sha256``, ``decode_status``, ``acceptance_status``,
and the portable ``validated_path`` (repository-relative path only;
absolute host paths are rejected by the runtime verifier).

The test verifies the canonical producer
(:mod:`scripts.factory.populate_gate_summary`) is wired to
mirror the contracts. The real attestation verifier tests live in
:mod:`tests.unit.test_gate_summary_validation_attestation`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.unit.test_gate_summary_population_r12 import _populate_for_test


def test_parser_check_is_not_written_to_artifact(tmp_path: Path) -> None:
    """The gate-summary-parser MUST be kept out of the artifact's
    ``checks`` inventory (it is the self-referential validator and
    including it would create a circular contract between the
    artifact and the parser that consumes it).

    ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:

    * ``gate-summary-parser`` MUST NOT appear in the canonical
      ``checks`` array (still 17 entries).
    * ``gate-summary-parser`` MUST NOT appear in
      ``extras.required_check_names`` -- the parser invocation is
      tracked separately as a typed ``parser_postcondition`` field
      so the contract never cycles.
    * The companion sibling attestation
      ``gate-summary-validation.json`` MUST be persisted next to the
      artifact (same directory) and MUST carry the typed
      ``parser_identity``, ``validated_sha256``, ``decode_status``,
      ``acceptance_status``, and the portable
      ``validated_path`` (repository-relative path only; absolute
      host paths are rejected by the runtime verifier).
    * The artifact's bytes MUST round-trip through SHA-256 and the
      ``validated_sha256`` MUST equal the final file SHA.
    """
    target = tmp_path / "gate-summary.json"
    final = _populate_for_test(target)
    written_bytes = target.read_bytes()
    written_sha = hashlib.sha256(written_bytes).hexdigest()
    written = json.loads(written_bytes.decode("utf-8"))

    # 1. The parser inventory MUST NOT be embedded in checks or
    # required_check_names.
    written_names = {c["name"] for c in written.get("checks", [])}
    assert "gate-summary-parser" not in written_names, (
        "gate-summary-parser must not be a member of the executed checks list"
    )
    extras = written.get("extras", {}) or {}
    required = set(extras.get("required_check_names", []))
    assert "gate-summary-parser" not in required, (
        "gate-summary-parser must not appear in extras.required_check_names"
    )
    assert "parser_postcondition" not in extras, (
        "parser_postcondition must NOT be embedded inside the artifact's "
        "extras; it belongs in the sibling validation attestation."
    )

    # 2. The canonical 17 checks remain stable.
    assert final.checks_total == 17, (
        f"expected 17 canonical checks; got {final.checks_total!r}"
    )
    assert len(written_names) == 17, (
        f"expected 17 distinct check names; got {sorted(written_names)!r}"
    )
    assert final.checks_failed == 0

    # 3. The sibling validation attestation MUST be persisted and
    # contain typed fields.
    attestation_path = tmp_path / "gate-summary-validation.json"
    assert attestation_path.exists(), (
        f"sibling validation attestation missing at {attestation_path}"
    )
    attestation = json.loads(
        attestation_path.read_text(encoding="utf-8")
    )
    # Parser identity is a typed string.
    parser_identity = attestation.get("parser_identity")
    assert isinstance(parser_identity, str) and parser_identity, (
        f"attestation.parser_identity MUST be a non-empty string; got {parser_identity!r}"
    )
    # Validated SHA MUST equal the final artifact bytes.
    assert attestation.get("validated_sha256") == written_sha, (
        "attestation.validated_sha256 MUST equal the SHA-256 of the "
        "final gate-summary bytes; subsequent mutation of the artifact "
        "must surface as a SHA mismatch."
    )
    # Validated path MUST be a portable repository-relative POSIX path
    # (no absolute prefix, no Windows drive, no home-prefixed path).
    validated_path_value = attestation.get("validated_path")
    assert isinstance(validated_path_value, str), (
        "attestation.validated_path MUST be a string"
    )
    for forbidden in ("/Users/", "/home/runner/", "\\"):
        assert forbidden not in validated_path_value, (
            f"attestation.validated_path MUST NOT contain {forbidden!r}; "
            f"got {validated_path_value!r}"
        )
    assert not validated_path_value.startswith("/"), (
        f"attestation.validated_path MUST be repository-relative; "
        f"got {validated_path_value!r}"
    )
    assert ".." not in validated_path_value.split("/"), (
        f"attestation.validated_path MUST NOT contain '..' path traversal; "
        f"got {validated_path_value!r}"
    )

    # 4. Typed verdict fields MUST be present.
    for field_name in ("decode_status", "acceptance_status"):
        value = attestation.get(field_name)
        assert value in {"pass", "fail"}, (
            f"attestation.{field_name} MUST be 'pass' or 'fail'; got {value!r}"
        )

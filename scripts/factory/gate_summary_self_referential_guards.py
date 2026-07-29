"""Self-referential guard helpers for the gate-summary parser.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05
-CI-SHARD-PORTABILITY-AND-PROMOTION-REGRESSION-CLOSURE01:

The canonical ``gate-summary-parser`` is the self-referential
validator of the ``.factory/gate-summary.json`` artifact. A
self-referential contract would let the validated bytes mutate the
verdict they were supposedly attested by, defeating the artefact's
canonical purpose: every subsequent mutation of the artifact must
surface as a SHA-256 mismatch with the sibling validation
attestation.

The helpers in this module expose the three forbidden self-referential
shapes so :mod:`scripts.factory.parse_gate_summary` can call them
without inflating its line count:

* :data:`PARSER_POSTCONDITION_CHECK_NAME` -- the canonical name of
  the parser check; the parser rejects both declaration in
  ``extras.required_check_names`` and presence in the executed
  ``checks`` list.
* :data:`FORBIDDEN_PARSER_EXTRAS_KEYS` -- extras keys that MUST NOT
  appear in the artifact's ``extras`` mapping because embedding the
  parser verdict inside the validated bytes is the exact shape that
  would defeat the contract.

The parser invokes these helpers from a single :func:`check_no_self_referential`
function which mutates the provided ``acceptance_errors`` list so
the canonical parser stays focused on the schema/contract
machinery rather than the policy surface.
"""

from __future__ import annotations

# ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:
# The parser is the self-referential validator; it MUST NOT appear
# as a member of the executed checks list (the producer filters it
# out at :func:`populate_gate_summary.build_gate_summary`) and it
# MUST NOT be declared in ``extras.required_check_names``.
PARSER_POSTCONDITION_CHECK_NAME = "gate-summary-parser"

# ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:
# ``extras.parser_postcondition`` and any other key whose value
# would carry the parser invocation result INSIDE the validated
# artifact are forbidden because they would mutate the bytes
# the parser attests to. The canonical location for the parser
# verdict is the sibling ``gate-summary-validation.json``
# attestation produced by
# :mod:`scripts.factory.gate_summary_validation_attestation`.
FORBIDDEN_PARSER_EXTRAS_KEYS: frozenset[str] = frozenset(
    {"parser_postcondition"}
)


def check_no_self_referential(
    *,
    actual_set: set[str],
    extras: dict[str, object],
    acceptance_errors: list[str],
) -> None:
    """Fail-closed guard against self-referential parser contracts.

    Appends zero or more acceptance errors to ``acceptance_errors``
    so the canonical parser's loop body stays small. Idempotent
    within a single artifact decode.
    """
    bad_extras_keys = sorted(
        FORBIDDEN_PARSER_EXTRAS_KEYS.intersection(extras.keys())
    )
    if bad_extras_keys:
        acceptance_errors.append(
            "self_referential_extras_keys: parser result MUST live in "
            "the sibling validation attestation; artifact extras "
            f"forbidden keys present: {bad_extras_keys}"
        )
    if PARSER_POSTCONDITION_CHECK_NAME in actual_set:
        acceptance_errors.append(
            f"self_referential_check: {PARSER_POSTCONDITION_CHECK_NAME!r} "
            "MUST NOT be a member of the executed checks list"
        )
    declared_required = extras.get("required_check_names")
    if (
        isinstance(declared_required, list)
        and PARSER_POSTCONDITION_CHECK_NAME in declared_required
    ):
        acceptance_errors.append(
            f"self_referential_required_check_name: "
            f"{PARSER_POSTCONDITION_CHECK_NAME!r} MUST NOT be declared "
            f"in extras.required_check_names"
        )


__all__ = [
    "FORBIDDEN_PARSER_EXTRAS_KEYS",
    "PARSER_POSTCONDITION_CHECK_NAME",
    "check_no_self_referential",
]

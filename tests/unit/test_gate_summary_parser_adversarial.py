"""Adversarial test: artifact embedding the parser result MUST be rejected.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:

The canonical contract is that ``gate-summary-parser`` MUST NOT appear
in the artifact's ``checks`` array or in
``extras.required_check_names`` -- embedding the parser invocation
result inside the validated artefact creates a self-referential
contract (the bytes that were supposedly validated would be the same
bytes that recorded the validation outcome).

This test mutates a freshly-produced artifact to embed the parser
result inside ``extras.parser_postcondition`` and verifies that the
canonical parser correctly rejects the result.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.factory.build_gate_summary import GateSummary
from scripts.factory.parse_gate_summary import parse_gate_summary
from scripts.factory.populate_gate_summary import REQUIRED_CHECK_NAMES


def _build_passing_artifact() -> GateSummary:
    """Build a canonical 17-check passing artifact without invoking
    the populate subprocess."""
    from scripts.factory.build_gate_summary import (
        CheckOutcome,
        SubsystemSelfTestCount,
        make_r10_defaults,
    )

    checks = [
        CheckOutcome(
            name=name,
            status="pass",
            duration_ms=1,
            error_message=None,
            command="<test>",
            exit_code=0,
        )
        for name in REQUIRED_CHECK_NAMES
    ]
    return GateSummary(
        schema_version=1,
        profile="act-local",
        overall_status="pass",
        source_status="present",
        generated_at="2026-07-30T00:00:00+00:00",
        checks=checks,
        self_tests={
            "verifier_self_tests": SubsystemSelfTestCount(
                accepted=1, rejected=1, failed=0
            )
        },
        r10_definition_of_done=make_r10_defaults(),
    )


def test_artifact_with_parser_postcondition_in_extras_is_rejected(tmp_path: Path) -> None:
    """An adversarial artifact that embeds a ``parser_postcondition``
    field inside ``extras`` MUST be rejected by the canonical
    parser (the parser MUST refuse to acknowledge a self-referential
    artefact). Embedding the parser result inside the validated
    bytes would mutate the very bytes the parser attests to."""
    target = tmp_path / "gate-summary.json"
    summary = _build_passing_artifact()
    # Adversarial mutation: embed the parser invocation result
    # inside the artifact's extras. The canonical contract is that
    # this is forbidden -- the test asserts the parser rejects
    # any artifact that carries this field at all.
    injected = GateSummary(
        schema_version=summary.schema_version,
        profile=summary.profile,
        overall_status=summary.overall_status,
        source_status=summary.source_status,
        generated_at=summary.generated_at,
        checks=summary.checks,
        self_tests=summary.self_tests,
        r10_definition_of_done=summary.r10_definition_of_done,
        extras={
            "required_check_names": list(REQUIRED_CHECK_NAMES),
            "parser_postcondition": {
                "name": "gate-summary-parser",
                "decode_status": "pass",
                "acceptance_status": "pass",
            },
        },
    )
    injected.write(target)
    written = json.loads(target.read_text(encoding="utf-8"))
    # Sanity: the parser result IS in the bytes the parser would
    # otherwise attest to. This is the forbidden shape.
    assert "parser_postcondition" in written.get("extras", {})
    parsed = parse_gate_summary(target)
    # The parser MUST refuse a decode_status=='pass' verdict for an
    # artifact that carries the parser result inside it -- embedding
    # the verdict in the validated bytes makes the verdict
    # unauditable. The acceptance contract fails closed.
    assert parsed.acceptance_status == "fail", (
        f"parser MUST reject an artifact embedding parser_postcondition "
        f"in extras; got decode={parsed.decode_status}, "
        f"acceptance={parsed.acceptance_status}"
    )


def test_artifact_with_gate_summary_parser_in_checks_is_rejected(tmp_path: Path) -> None:
    """Adding the parser as an 18th check (instead of keeping the
    canonical 17 checks) MUST be rejected by the parser."""
    from scripts.factory.build_gate_summary import CheckOutcome

    target = tmp_path / "gate-summary.json"
    summary = _build_passing_artifact()
    adversarial_checks = list(summary.checks) + [
        CheckOutcome(
            name="gate-summary-parser",
            status="pass",
            duration_ms=0,
            error_message=None,
            command="<forbidden>",
            exit_code=0,
        ),
    ]
    injected = GateSummary(
        schema_version=summary.schema_version,
        profile=summary.profile,
        overall_status="pass",
        source_status="present",
        generated_at="2026-07-30T00:00:00+00:00",
        checks=adversarial_checks,
        self_tests=summary.self_tests,
        r10_definition_of_done=summary.r10_definition_of_done,
        extras={"required_check_names": list(REQUIRED_CHECK_NAMES)},
    )
    injected.write(target)
    parsed = parse_gate_summary(target)
    # ``unexpected_check_names`` MUST include ``gate-summary-parser``
    # and the acceptance_status MUST be fail.
    assert parsed.acceptance_status == "fail"
    assert "gate-summary-parser" in parsed.unexpected_check_names
    assert parsed.decode_status == "pass"


def test_artifact_with_parser_in_required_check_names_is_rejected(tmp_path: Path) -> None:
    """Declaring ``gate-summary-parser`` in
    ``extras.required_check_names`` -- without it actually being
    in the checks array -- MUST be rejected.

    The acceptance contract is that declaring names without actually
    executing the check does NOT satisfy the gate; the contract
    requires real execution. The adversarial test double-checks
    this by surgically violating the contract on both sides.
    """
    target = tmp_path / "gate-summary.json"
    summary = _build_passing_artifact()
    injected = GateSummary(
        schema_version=summary.schema_version,
        profile=summary.profile,
        overall_status="pass",
        source_status="present",
        generated_at="2026-07-30T00:00:00+00:00",
        checks=summary.checks,
        self_tests=summary.self_tests,
        r10_definition_of_done=summary.r10_definition_of_done,
        extras={
            "required_check_names": list(REQUIRED_CHECK_NAMES)
            + ["gate-summary-parser"],
        },
    )
    injected.write(target)
    parsed = parse_gate_summary(target)
    # Declaring the parser name in ``extras.required_check_names``
    # is a self-referential contract -- the parser is itself the
    # validator, so \"declaring satisfies the gate\" is a documented
    # lie. The acceptance contract fails closed.
    assert parsed.acceptance_status == "fail"
    assert any(
        "self_referential_required_check_name" in err
        for err in parsed.acceptance_errors
    ), (
        f"expected self_referential_required_check_name in "
        f"acceptance_errors; got {parsed.acceptance_errors!r}"
    )

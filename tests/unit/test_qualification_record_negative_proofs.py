"""Negative-proof tests for the qualification record verdict derivation.

ACT-K9B-HULK-PROMOTION-AUTOMATED-CLOSURE-LIVE-QUALIFICATION-AND-CI-TIMING01
WAVE CORRECTION01 / P0-12 — proves that a contradictory supplied
verdict is REJECTED before atomic write.

Each test pairs a deliberately-misconfigured flag with the
``VERDICT_CLOSED_PASS`` claim and expects
:class:`VerdictInconsistentError`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.qualification_record import (
    QUALIFICATION_RECORD_KEYS,
    VERDICT_CLOSED_PASS,
    VERDICT_FAIL,
    VERDICT_PARTIAL,
    VerdictInconsistentError,
    derive_verdict,
    verify_supplied_verdict,
    write_qualification_record,
)


def _base_pass_values() -> dict[str, object]:
    """All-passing flags; PARTIAL is permitted."""
    v = {key: "test" for key in QUALIFICATION_RECORD_KEYS}
    v.update(
        BASE="f09348dc6f7dd8887c51278ee0a504c7e22d1417",
        RANGE_BASE="f09348dc6f7dd8887c51278ee0a504c7e22d1417",
        WORKTREE_CLEAN="true",
        GATE_SUMMARY_STATUS="pass",
        GATE_SUMMARY_CHECKS_FAILED=0,
        PARSER_EXIT_CODE=0,
        DECODE_STATUS="pass",
        ACCEPTANCE_STATUS="pass",
        GIT_RECONSTRUCTED_MANIFEST_EQUALITY="match",
        LLM_FRIENDLY="pass",
        FULL_GATE_NEGATIVE_PROOFS_THREE_RUN="pass",
        TARGETED_REPOSITORY_GATE="pass",
        VERIFY_CONCLUSION="success",
        BUILD_CONCLUSION="success",
        DEPLOY_CONCLUSION="success",
        QUALIFICATION_CONCLUSION="success",
        READINESS_STATUS="pass",
        UI_TOKEN_CONFIGURED="true",
        INTERNAL_TOKEN_CONFIGURED="true",
        ANONYMOUS_MUTATION_REJECTED="true",
        CREDENTIAL_CLASS_ISOLATION="true",
        NETWORK_POLICY_VERIFIED="true",
        INITIAL_OUTCOME="committed",
        RECONCILIATION_OUTCOME="n/a",
        DUPLICATE_LOGICAL_PROMOTIONS=0,
        DISPATCH_EQUALITY="match",
        RUN_SUMMARY_EQUALITY="match",
        UI_INDEX_EQUALITY="match",
        API_RUN_EQUALITY="match",
        DIAGNOSTIC_PACK_EQUALITY="match",
        CONTENT_INDEX_EQUALITY="match",
        NOTIFICATION_EQUALITY="match",
        READY_FOR_IMAGE_PUBLICATION="true",
        READY_FOR_REPEATED_LIVE_RUNS="true",
        READY_FOR_LIVE_ACCEPTANCE="true",
        TEST_TIMING_ACCEPTED="true",
        VERDICT=VERDICT_CLOSED_PASS,
    )
    return v


@pytest.mark.parametrize(
    "flag",
    [
        "DEPLOY_CONCLUSION",
        "ANONYMOUS_MUTATION_REJECTED",
        "NETWORK_POLICY_VERIFIED",
        "DUPLICATE_LOGICAL_PROMOTIONS",
        "DISPATCH_EQUALITY",
        "API_RUN_EQUALITY",
        "READY_FOR_LIVE_ACCEPTANCE",
        "GATE_SUMMARY_CHECKS_FAILED",
        "PARSER_EXIT_CODE",
        "INITIAL_OUTCOME",
    ],
)
def test_contradictory_verdict_rejected(flag: str) -> None:
    """A contradictory flag MUST downgrade the verdict; CLOSED_PASS is rejected."""
    v = _base_pass_values()
    if flag in ("DUPLICATE_LOGICAL_PROMOTIONS", "GATE_SUMMARY_CHECKS_FAILED", "PARSER_EXIT_CODE"):
        v[flag] = 1
    else:
        v[flag] = "failure" if flag.endswith("_CONCLUSION") else "fail"
    # Don't supply a verdict; derive then attempt to write CLOSED_PASS
    derived = derive_verdict(v)
    assert derived == VERDICT_FAIL
    v["VERDICT"] = VERDICT_CLOSED_PASS
    with pytest.raises(VerdictInconsistentError):
        verify_supplied_verdict(v)


def test_partial_permits_only_timing_failure() -> None:
    """Only TEST_TIMING_ACCEPTED may be unhealthy for PARTIAL."""
    v = _base_pass_values()
    v["TEST_TIMING_ACCEPTED"] = "false"
    assert derive_verdict(v) == VERDICT_PARTIAL

    # Adding another failure downgrades to FAIL
    v["ANONYMOUS_MUTATION_REJECTED"] = "false"
    assert derive_verdict(v) == VERDICT_FAIL


def test_atomic_write_is_rejected_for_contradictory_verdict(
    tmp_path: Path,
) -> None:
    """``write_qualification_record`` MUST reject contradictory verdict."""
    v = _base_pass_values()
    v["DEPLOY_CONCLUSION"] = "failure"
    v["VERDICT"] = VERDICT_CLOSED_PASS
    target = tmp_path / "record.json"
    with pytest.raises(VerdictInconsistentError):
        write_qualification_record(target, v)
    # The atomic temp must NOT have leaked
    assert not target.exists(), "target must not exist after rejected write"
    assert not target.with_suffix(target.suffix + ".tmp").exists(), (
        "tmp file must be cleaned up"
    )


def test_full_record_round_trip(tmp_path: Path) -> None:
    v = _base_pass_values()
    v["VERDICT"] = derive_verdict(v)
    target = tmp_path / "record.json"
    record = write_qualification_record(target, v)
    assert record["VERDICT"] == VERDICT_CLOSED_PASS
    body = target.read_text(encoding="utf-8")
    assert '"VERDICT": "CLOSED_PASS"' in body
    # round-trip via JSON
    import json
    parsed = json.loads(body)
    assert parsed == record


def test_partial_record_round_trip(tmp_path: Path) -> None:
    v = _base_pass_values()
    v["TEST_TIMING_ACCEPTED"] = "false"
    v["VERDICT"] = derive_verdict(v)
    target = tmp_path / "record.json"
    record = write_qualification_record(target, v)
    assert record["VERDICT"] == VERDICT_PARTIAL
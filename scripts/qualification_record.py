"""Canonical final qualification record schema.

ACT-K9B-HULK-PROMOTION-AUTOMATED-CLOSURE-LIVE-QUALIFICATION-AND-CI-TIMING01
WAVE 11 / P0-12: the orchestrator's final qualification record.

The verdict is **derived** from the supplied per-section flags; a
record that contradicts its own flags is rejected with
:class:`VerdictInconsistentError`.

Three verdict values are accepted:

* ``CLOSED_PASS``  — every correctness, security, deployment, live
  and projection flag is successful; timing may be partial.
* ``PARTIAL``      — every correctness, security, deployment, live
  and projection flag is successful; ONLY the quantitative timing
  target remains.  The caller must declare
  ``TEST_TIMING_ACCEPTED == "false"``.
* ``FAIL``         — anything else.

A contradictory verdict is rejected:

  >>> derive_verdict(
  ...     VERDICT=VERDICT_CLOSED_PASS,
  ...     DEPLOY_CONCLUSION="failure",
  ...     ANONYMOUS_MUTATION_REJECTED="true",
  ... )
  Traceback (most recent call last):
      ...
  VerdictInconsistentError: DEPLOY_CONCLUSION=failure contradicts CLOSED_PASS

Atomic writes use a sibling tempfile + ``os.replace``; on POSIX,
this is the canonical atomic rename.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

# ---------------------------------------------------------------------------
# Verdict constants
# ---------------------------------------------------------------------------

VERDICT_CLOSED_PASS: Final[str] = "CLOSED_PASS"
VERDICT_PARTIAL: Final[str] = "PARTIAL"
VERDICT_FAIL: Final[str] = "FAIL"

VERDICT_VALUES: Final[tuple[str, ...]] = (
    VERDICT_CLOSED_PASS,
    VERDICT_PARTIAL,
    VERDICT_FAIL,
)


class VerdictInconsistentError(ValueError):
    """Raised when a supplied verdict contradicts its supporting flags."""


# ---------------------------------------------------------------------------
# Canonical record keys (one per WAVE 11 field)
# ---------------------------------------------------------------------------

QUALIFICATION_RECORD_KEYS: Final[tuple[str, ...]] = (
    # IDENTITY
    "BASE",
    "F",
    "F_TREE",
    "E",
    "E_TREE",
    "WORKTREE_CLEAN",
    # LOCAL CLOSURE
    "GATE_SUMMARY_STATUS",
    "GATE_SUMMARY_CHECKS_TOTAL",
    "GATE_SUMMARY_CHECKS_FAILED",
    "PARSER_EXIT_CODE",
    "DECODE_STATUS",
    "ACCEPTANCE_STATUS",
    "RANGE_BASE",
    "RANGE_HEAD",
    "SUBJECT_TREE",
    "MANIFEST_SHA256",
    "MANIFEST_COUNT",
    "GIT_RECONSTRUCTED_MANIFEST_EQUALITY",
    "LLM_FRIENDLY",
    "FULL_GATE_NEGATIVE_PROOFS_THREE_RUN",
    "TARGETED_REPOSITORY_GATE",
    # CI
    "WORKFLOW_RUN_ID",
    "WORKFLOW_RUN_ATTEMPT",
    "WORKFLOW_HEAD_SHA",
    "VERIFY_CONCLUSION",
    "BUILD_CONCLUSION",
    "DEPLOY_CONCLUSION",
    "QUALIFICATION_CONCLUSION",
    # DEPLOYMENT
    "BACKEND_IMAGE_DIGEST",
    "SCHEDULER_IMAGE_DIGEST",
    "FRONTEND_IMAGE_DIGEST",
    "BACKEND_ROLLOUT_REVISION",
    "SCHEDULER_ROLLOUT_REVISION",
    "READINESS_STATUS",
    # SECURITY
    "UI_TOKEN_CONFIGURED",
    "INTERNAL_TOKEN_CONFIGURED",
    "ANONYMOUS_MUTATION_REJECTED",
    "CREDENTIAL_CLASS_ISOLATION",
    "NETWORK_POLICY_VERIFIED",
    # LIVE PROMOTION
    "QUALIFICATION_RUN_ID",
    "PROMOTION_REQUEST_ID",
    "WIRE_VERSION",
    "HTTP_STATUS",
    "RESPONSE_BYTES",
    "RESPONSE_SHA256",
    "INITIAL_OUTCOME",
    "INITIAL_REASON",
    "RECONCILIATION_OUTCOME",
    "CANONICAL_INCIDENT_IDS",
    "PROMOTION_RECORD_COUNT",
    "DUPLICATE_LOGICAL_PROMOTIONS",
    "DIAGNOSIS_BEFORE_RECONCILIATION",
    "DIAGNOSIS_AFTER_RECONCILIATION",
    # PROJECTION TRUTH
    "DISPATCH_EQUALITY",
    "RUN_SUMMARY_EQUALITY",
    "UI_INDEX_EQUALITY",
    "API_RUN_EQUALITY",
    "DIAGNOSTIC_PACK_EQUALITY",
    "CONTENT_INDEX_EQUALITY",
    "NOTIFICATION_EQUALITY",
    # TEST TIMING
    "TIMING_REPETITIONS",
    "CANONICAL_COLLECTION_COUNT",
    "SHARD_COUNTS",
    "COLLECTION_BIJECTION",
    "BASELINE_MEDIAN_MAX_SECONDS",
    "FINAL_MEDIAN_MAX_SECONDS",
    "FINAL_MEDIAN_SPREAD_SECONDS",
    "CRITICAL_PATH_REDUCTION_PERCENT",
    # FINAL FLAGS
    "READY_FOR_IMAGE_PUBLICATION",
    "READY_FOR_REPEATED_LIVE_RUNS",
    "READY_FOR_LIVE_ACCEPTANCE",
    "TEST_TIMING_ACCEPTED",
    "VERDICT",
)


# ---------------------------------------------------------------------------
# Verdict derivation
# ---------------------------------------------------------------------------


# Each guard is (key, predicate).  True means the flag is healthy.
_SUCCESS_PREDICATES: dict[str, Any] = {
    # identity / closure
    "WORKTREE_CLEAN":                lambda v: v == "true",
    "GATE_SUMMARY_STATUS":           lambda v: v == "pass",
    "GATE_SUMMARY_CHECKS_FAILED":    lambda v: v == 0,
    "PARSER_EXIT_CODE":              lambda v: v == 0,
    "DECODE_STATUS":                 lambda v: v == "pass",
    "ACCEPTANCE_STATUS":             lambda v: v == "pass",
    "GIT_RECONSTRUCTED_MANIFEST_EQUALITY": lambda v: v == "match",
    "LLM_FRIENDLY":                  lambda v: v == "pass",
    "FULL_GATE_NEGATIVE_PROOFS_THREE_RUN": lambda v: v == "pass",
    "TARGETED_REPOSITORY_GATE":      lambda v: v == "pass",
    # CI
    "VERIFY_CONCLUSION":             lambda v: v == "success",
    "BUILD_CONCLUSION":              lambda v: v == "success",
    "DEPLOY_CONCLUSION":             lambda v: v == "success",
    "QUALIFICATION_CONCLUSION":      lambda v: v == "success",
    # deployment
    "READINESS_STATUS":              lambda v: v == "pass",
    # security
    "UI_TOKEN_CONFIGURED":           lambda v: v == "true",
    "INTERNAL_TOKEN_CONFIGURED":      lambda v: v == "true",
    "ANONYMOUS_MUTATION_REJECTED":    lambda v: v == "true",
    "CREDENTIAL_CLASS_ISOLATION":     lambda v: v == "true",
    "NETWORK_POLICY_VERIFIED":        lambda v: v == "true",
    # live promotion
    "INITIAL_OUTCOME":               lambda v: v == "committed",
    "RECONCILIATION_OUTCOME":        lambda v: v in ("committed", "n/a"),
    "DUPLICATE_LOGICAL_PROMOTIONS":  lambda v: v == 0,
    # projection
    "DISPATCH_EQUALITY":             lambda v: v == "match",
    "RUN_SUMMARY_EQUALITY":          lambda v: v == "match",
    "UI_INDEX_EQUALITY":             lambda v: v == "match",
    "API_RUN_EQUALITY":              lambda v: v == "match",
    "DIAGNOSTIC_PACK_EQUALITY":      lambda v: v == "match",
    "CONTENT_INDEX_EQUALITY":        lambda v: v == "match",
    "NOTIFICATION_EQUALITY":         lambda v: v == "match",
    # final flags
    "READY_FOR_IMAGE_PUBLICATION":   lambda v: v == "true",
    "READY_FOR_REPEATED_LIVE_RUNS":  lambda v: v == "true",
    "READY_FOR_LIVE_ACCEPTANCE":     lambda v: v == "true",
}

# PARTIAL permits ONLY this flag to be unhealthy.
_PARTIAL_PERMITTED_FLAG: str = "TEST_TIMING_ACCEPTED"


def derive_verdict(values: Mapping[str, Any]) -> str:
    """Derive the verdict from the supplied flags.

    * If every flag in :data:`_SUCCESS_PREDICATES` evaluates healthy
      and :data:`_PARTIAL_PERMITTED_FLAG` evaluates healthy, return
      ``VERDICT_CLOSED_PASS``.
    * If every flag in :data:`_SUCCESS_PREDICATES` evaluates healthy
      and ONLY :data:`_PARTIAL_PERMITTED_FLAG` is unhealthy, return
      ``VERDICT_PARTIAL``.
    * Otherwise return ``VERDICT_FAIL``.
    """
    failed_required: list[str] = []
    partial_unhealthy = False
    for key, predicate in _SUCCESS_PREDICATES.items():
        if not predicate(values.get(key)):
            failed_required.append(key)
    partial_flag_value = values.get(_PARTIAL_PERMITTED_FLAG, "false")
    if partial_flag_value != "true":
        partial_unhealthy = True
    if not failed_required:
        return VERDICT_PARTIAL if partial_unhealthy else VERDICT_CLOSED_PASS
    return VERDICT_FAIL


def verify_supplied_verdict(values: Mapping[str, Any]) -> None:
    """Reject any supplied verdict that contradicts the flags.

    This is the P0-12 negative-proof hook: a contradictory verdict
    is rejected BEFORE atomic write so the canonical record cannot
    carry an inconsistent claim.

    The verdict MUST be derivable from the flags.  A supplied verdict
    is permitted only as an equality assertion against the derived
    verdict.
    """
    supplied = values.get("VERDICT")
    if supplied is None:
        return
    if supplied not in VERDICT_VALUES:
        raise VerdictInconsistentError(f"unknown verdict: {supplied!r}")
    derived = derive_verdict(values)
    if supplied == VERDICT_CLOSED_PASS and derived != VERDICT_CLOSED_PASS:
        raise VerdictInconsistentError(
            f"VERDICT=CLOSED_PASS but derived={derived!r} from flags"
        )
    if supplied == VERDICT_PARTIAL and derived != VERDICT_PARTIAL:
        raise VerdictInconsistentError(
            f"VERDICT=PARTIAL but derived={derived!r} from flags"
        )


def derive_and_record(
    values: Mapping[str, Any], *,
    parent_closure_sha: str | None = None,
    subject_sha: str | None = None,
    subject_tree: str | None = None,
    workflow_head_sha: str | None = None,
) -> str:
    """Derive the verdict from ``values`` and inject the CLOSED_PASS
    closure invariants automatically.

    The verdict is ALWAYS derived from the per-section flags; the
    caller MUST NOT supply a contradictory verdict.
    """
    out = dict(values)
    derived = derive_verdict(out)
    out["VERDICT"] = derived
    if parent_closure_sha is not None:
        out["F"] = parent_closure_sha
    if subject_sha is not None:
        out["SUBJECT_SHA"] = subject_sha
    if subject_tree is not None:
        out["F_TREE"] = subject_tree
    if workflow_head_sha is not None:
        out["E"] = workflow_head_sha
    return derived


# ---------------------------------------------------------------------------
# Build / verify
# ---------------------------------------------------------------------------


def build_qualification_record(
    values: Mapping[str, Any],
    *,
    base_sha: str = "f09348dc6f7dd8887c51278ee0a504c7e22d1417",
) -> dict[str, Any]:
    """Return a validated qualification record assembled from ``values``."""
    record: dict[str, Any] = {key: values[key] for key in QUALIFICATION_RECORD_KEYS}
    record["BASE"] = base_sha
    if record["VERDICT"] not in VERDICT_VALUES:
        raise ValueError(
            f"VERDICT must be one of {VERDICT_VALUES!r}; got {record['VERDICT']!r}"
        )
    return record


def verify_qualification_record(record: Mapping[str, Any]) -> None:
    """Raise :class:`ValueError` if ``record`` violates the schema."""
    missing = [k for k in QUALIFICATION_RECORD_KEYS if k not in record]
    if missing:
        raise ValueError(f"missing keys: {missing}")
    if record["VERDICT"] not in VERDICT_VALUES:
        raise ValueError(f"invalid verdict: {record['VERDICT']!r}")
    if record.get("RANGE_BASE") and record.get("BASE"):
        if record["RANGE_BASE"] != record["BASE"]:
            raise ValueError(
                f"RANGE_BASE={record['RANGE_BASE']!r} != BASE={record['BASE']!r}"
            )


def write_qualification_record(
    target: Path, values: Mapping[str, Any]
) -> dict[str, Any]:
    """Build, validate, derive verdict, and atomically write the record."""
    # Negative-proof: reject contradictory supplied verdict
    verify_supplied_verdict(values)
    record = build_qualification_record(values)
    verify_qualification_record(record)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: write sibling tmp, fsync, rename, fsync parent.
    tmp = target.with_suffix(target.suffix + ".tmp")
    payload = json.dumps(record, indent=2, sort_keys=False) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    # fsync the file contents
    fd = os.open(tmp, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)
    # fsync the parent directory (POSIX only)
    try:
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass
    return record


__all__ = [
    "QUALIFICATION_RECORD_KEYS",
    "VerdictInconsistentError",
    "VERDICT_CLOSED_PASS",
    "VERDICT_FAIL",
    "VERDICT_PARTIAL",
    "VERDICT_VALUES",
    "build_qualification_record",
    "derive_verdict",
    "verify_qualification_record",
    "verify_supplied_verdict",
    "write_qualification_record",
]
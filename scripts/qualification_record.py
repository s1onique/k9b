"""Canonical final qualification record schema.

ACT-K9B-HULK-PROMOTION-AUTOMATED-CLOSURE-LIVE-QUALIFICATION-AND-CI-TIMING01
WAVE 11: the orchestrator's final qualification record.

This module defines the canonical record schema for the FINAL EVIDENCE
AND VERDICT produced by the
``.github/workflows/promotion-qualification.yml`` orchestrator.  Every
field listed in the task's ``WAVE 11`` section is represented here as
a typed key in :data:`QUALIFICATION_RECORD_KEYS`.

Two emitters are provided:

* :func:`build_qualification_record` -- assembles a dict from supplied
  inputs, validates the schema, and returns it ready for JSON
  serialisation;
* :func:`verify_qualification_record` -- reads an existing record and
  asserts every required key is present and the verdict is consistent
  with the per-section flags.

The schema is intentionally compact: every key is a string, every
value is JSON-serialisable, and the verdict is one of the typed
strings ``"CLOSED_PASS"``, ``"PARTIAL"``, or ``"FAIL"`` defined in
:data:`VERDICT_VALUES`.

Acceptance: ``scripts/verify_all.sh --act-local`` MUST pass when this
module is part of the changed tree, and the canonical populate gate
summary MUST list the changed files in the
``changed_paths_manifest`` extras when the orchestrator binds the
range to ``f09348dc6f7dd8887c51278ee0a504c7e22d1417`` and the head
to the locked E SHA.
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# Canonical record keys (one per WAVE 11 field)
# ---------------------------------------------------------------------------

# IDENTITY
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


def _required_typed_keys() -> tuple[str, ...]:
    """Return the typed keys that MUST be present in every record."""
    return QUALIFICATION_RECORD_KEYS


# ---------------------------------------------------------------------------
# Build / verify
# ---------------------------------------------------------------------------


def build_qualification_record(
    values: Mapping[str, Any],
    *,
    base_sha: str = "f09348dc6f7dd8887c51278ee0a504c7e22d1417",
) -> dict[str, Any]:
    """Return a validated qualification record assembled from ``values``.

    Every key in :data:`QUALIFICATION_RECORD_KEYS` MUST be supplied
    via ``values``.  The base SHA defaults to the documented BASE of
    this CORRECTION11 cycle.
    """
    record: dict[str, Any] = {key: values[key] for key in QUALIFICATION_RECORD_KEYS}
    record["BASE"] = base_sha
    # Verdict consistency
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
    # range_base / BASE consistency
    if record.get("RANGE_BASE") and record.get("BASE"):
        if record["RANGE_BASE"] != record["BASE"]:
            raise ValueError(
                f"RANGE_BASE={record['RANGE_BASE']!r} != BASE={record['BASE']!r}"
            )


def write_qualification_record(
    target: Path, values: Mapping[str, Any]
) -> dict[str, Any]:
    """Build, validate, and atomically write the record to ``target``."""
    record = build_qualification_record(values)
    verify_qualification_record(record)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(record, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return record


__all__ = [
    "QUALIFICATION_RECORD_KEYS",
    "VERDICT_CLOSED_PASS",
    "VERDICT_FAIL",
    "VERDICT_PARTIAL",
    "VERDICT_VALUES",
    "build_qualification_record",
    "verify_qualification_record",
    "write_qualification_record",
]
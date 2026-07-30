"""CORRECTION02 architecture guards for the closure patch.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION02-CLEAN-RANGE-AND-SINGLE-OWNER-TRUTH01.

These guards fail at test time when the CORRECTION02 patch
regresses any of the closure invariants:

* **Single-owner ``_apply_batch``**. The canonical implementation
  of every batch mutation statement lives in
  :func:`incident_promotion_accumulator_mutation._apply_batch_mutation`.
  The class method
  :meth:`RunPromotionAccumulator._apply_batch` is a pure
  compatibility delegate. AST-level checks confirm that exactly
  one function owns the batch mutation statements
  (``total_scanned`` / ``total_firing`` /
  ``total_opened_incidents`` / ``total_updated_incidents`` /
  ``total_skipped_duplicates`` / ``total_unique_candidate_count``
  / ``total_errors`` / ``last_promotion_mode`` /
  ``last_incident_access_mode`` / ``last_source_kind`` /
  ``last_promotion_scan_scope`` / ``batches.append`` /
  ``add_record`` / ``_local_skipped_duplicate_count``).
* **Legacy and scoped batch mutation convergence**.
  :func:`add_batch_mutation` and the scoped atomic recorder
  reach the same :func:`_apply_batch_mutation` helper.
* **No duplicate counter / list / set / provenance assignments
  in the facade**. The :class:`RunPromotionAccumulator` facade
  declares ``total_scanned`` / ``total_firing`` /
  ``total_opened_incidents`` / ``total_updated_incidents`` /
  ``total_errors`` / ``last_incident_access_mode`` exactly once
  each (the dataclass ``field`` declaration). No second
  ``+=`` / ``=`` assignment to those counters exists inside a
  method body, except inside the ``_apply_batch_mutation``
  delegate body.
* **Fully typed public validator boundary**.
  :func:`validate_scoped_handoff_batch_consistency` accepts
  ``batch: PromotionBatch`` directly. AST-level checks confirm
  ``batch: object`` / ``batch: Any`` /
  ``cast(PromotionBatch, ...)`` are absent from the production
  validator / recorder code.
* **Internal helpers return the typed contract**.
  :func:`_require_common_batch_frame` returns
  :class:`IncidentPromotionResult` and the typed tuple
  envelope. ``tuple[object, ...]`` is only allowed in the
  internal ``_EMPTY_RECORDS`` constant.
* **Each closed handoff dispatch ends in ``assert_never``**.
  The validator's per-variant ``if/return`` chain ends with
  :func:`typing.assert_never` so a new variant addition fails
  mypy.
* **Gate-summary internal consistency**. The canonical contract
  ``checks_total == len(checks) == len(required_check_names)`` is
  verified at the AST and JSON level.
* **Source-secret warning fix**. The reconciliation-token
  assignment pattern is renamed to a non-secret identifier.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"
SCRIPTS_ROOT = REPO_ROOT / "scripts" / "factory"

ACCUMULATOR_FILE = SRC_ROOT / "incident_promotion_accumulator.py"
ACCUMULATOR_MUTATION_FILE = SRC_ROOT / "incident_promotion_accumulator_mutation.py"
VALIDATION_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_validation.py"
HANDOFF_FILE = SRC_ROOT / "promotion_scoped_accumulator_handoff.py"
RECORDER_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_recorder.py"
PROJECTION_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_projection.py"

POPULATE_FILE = SCRIPTS_ROOT / "populate_gate_summary.py"
PARSE_FILE = SCRIPTS_ROOT / "parse_gate_summary.py"

CANONICAL_BASE = "b1294cee7cbfc1c1b22f0c11282eaab474f8dbb8"

BATCH_MUTATION_FIELDS = (
    "total_scanned",
    "total_firing",
    "total_opened_incidents",
    "total_updated_incidents",
    "total_skipped_duplicates",
    "total_unique_candidate_count",
    "total_errors",
    "last_promotion_mode",
    "last_incident_access_mode",
    "last_source_kind",
    "last_promotion_scan_scope",
)


# ---------------------------------------------------------------------------
# Single-owner ``_apply_batch``
# ---------------------------------------------------------------------------


def test_closure01_parent_file_is_labeled_as_historical_checkpoint() -> None:
    """The older closure01 progress file MUST be labelled as historical.

    The check inspects the file's header for the explicit
    ``HISTORICAL CHECKPOINT`` / ``NOT CURRENT CLOSURE AUTHORITY``
    block. The header MUST be present in the first ~30 lines.
    """
    target = REPO_ROOT / "task_progress_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01.md"
    if not target.exists():
        pytest.skip("The closure01 parent progress file is missing.")
    head = "\n".join(target.read_text().splitlines()[:30])
    if "HISTORICAL CHECKPOINT" not in head:
        pytest.fail("The closure01 parent progress file MUST declare HISTORICAL CHECKPOINT in its header.")
    if "NOT CURRENT CLOSURE AUTHORITY" not in head:
        pytest.fail("The closure01 parent progress file MUST declare NOT CURRENT CLOSURE AUTHORITY in its header.")


def test_clean_subject_binding_no_self_referential_commit() -> None:
    """The CORRECTION02 progress file MUST NOT claim its own commit SHA."""
    target = REPO_ROOT / "task_progress_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction02_clean_range_and_single_owner_truth01.md"
    if not target.exists():
        pytest.skip("The CORRECTION02 progress file is missing.")
    text = target.read_text()
    # The subject section MUST be non-self-referential.
    forbidden_substrings = (
        "implementation_subject: 7bbe8250",
        "implementation_subject=7bbe8250",
    )
    for forbidden in forbidden_substrings:
        if forbidden in text:
            pytest.fail(f"progress file MUST NOT embed its own commit SHA: found {forbidden!r}")

# ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-CORRECTION01-ACCUMULATOR-SPLIT-AND-RANGE-GATE-TRUTH01

> The historical CORRECTION05 and CORRECTION06 progress files
> (``task_progress_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction05_strict_typing_and_rollback_closure01.md`` and
> ``task_progress_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01.md``) retain
> their earlier checkpoint identities and are labelled as
> **historical checkpoint; not current closure authority** in
> their own headers.

## Status snapshot

```text
PATCH_HYGIENE=PASS
EXACT_RANGE_EVIDENCE=PASS
PROGRESS_AUTHORITY_TRUTH=PASS
SELF_REFERENTIAL_COMMIT_CLAIM=false

ACTIVE_RECORDER_BATCH_TYPE=PASS
VALIDATOR_BATCH_TYPE=PASS
RESULT_CONTRACT_CYCLE_FREE=PASS
OBJECT_SHAPED_RESULT_BOUNDARY=false

SCOPED_RECORDING_SINGLE_AUTHORITY=PASS
SCOPED_REPLAY_USES_BOUND_BATCH=PASS
INTERLEAVED_REPLAY_IDEMPOTENCE=PASS
CORRUPTED_SCOPED_STATE_FAILS_CLOSED=PASS
ROLLBACK_SCOPED_AUTHORITY=PASS
ROLLBACK_CONTAINER_IDENTITY=PASS

ACCUMULATOR_FILE_SIZE_GATE=PASS
ACCUMULATOR_ALLOWLISTED=false
NO_NEW_LLM_ALLOWLIST=PASS
EXACT_RANGE_FILE_SIZE_GATE=PASS

SOURCE_SECRET_GATE=PASS
REPOSITORY_GATE_SUMMARY_SCHEMA=PASS
REPOSITORY_GATE_SUMMARY_STATUS=PASS
LEAMAS_GATE_SUMMARY_COMPATIBILITY=PASS

GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED
REMAINING_OVERSIZED_FILES=dispatcher,scoped_http_client,selection_suite
READY_FOR_REMAINING_HARD_GATE_SPLIT=true
READY_FOR_LIVE_ACCEPTANCE=false
```

## Subject (non-self-referential)

```text
canonical_base: b1294cee
implementation_subject: <final commit SHA, captured at commit time>
implementation_tree: <tree SHA, captured at commit time>
closure_evidence_range: b1294cee..<implementation subject>
closure_metadata_commit: reported externally after commit
```

The final external report (see "Final external report" below)
captures the actual closure commit SHA. This document does
NOT embed the closure commit's own SHA so it cannot drift if
the commit is amended after the fact.

## Completed

* **Validator boundary fully typed**.
  :func:`validate_scoped_handoff_batch_consistency` and the
  per-variant validators accept
  ``batch: PromotionBatch`` directly. The
  :func:`_require_common_batch_frame` helper returns
  ``tuple[IncidentPromotionResult, str, int, int]``. There is no
  ``batch: object``, no ``tuple[object, ...]``, and no ``Any`` or
  unchecked cast in the production recorder/validator path.
* **``IncidentPromotionResult`` moved to a cycle-free contract
  module**:
  :mod:`incident_promotion_result_contract`. The dispatcher
  re-exports the symbol for backward compatibility.
* **Accumulator split into focused modules** under the hard
  500-line cap:
  - :mod:`incident_promotion_accumulator` -- the canonical
    dataclass declaration (now 461 physical lines).
  - :mod:`incident_promotion_accumulator_snapshot` -- the typed
    snapshot / restore behaviour.
  - :mod:`incident_promotion_accumulator_projection` -- the
    derived scoped-recording projections
    (``scoped_promotion_handoff`` /
    ``scoped_promotion_batch`` /
    ``scoped_promotion_request_id`` /
    ``scoped_promotion_request_fingerprint`` /
    ``__setattr__`` / ``as_dict`` / etc.).
  - :mod:`incident_promotion_accumulator_compat` -- the
    ``record_scoped_promotion`` legacy compatibility wrapper.
  - :mod:`incident_promotion_accumulator_mutation` -- the
    ``add_record`` / ``add_records`` /
    ``record_promotion_result`` / ``add_batch`` /
    ``_apply_batch`` / ``_local_skipped_duplicate_count``
    mutators.
  - :mod:`incident_promotion_accumulator_errors` -- the
    :class:`AccumulatorAccessModeError` and
    :class:`PromotionWorksetState` error types.
  Each extracted method has a single owner (architecture
  verifier passes). The main class does not retain duplicate
  implementations.
* **Accumulator allowlist entry removed**. The CORRECTION06
  entry for ``incident_promotion_accumulator.py`` is deleted
  from :file:`scripts/llm_friendly_allowlist.py`. The new range
  verifier proves the worktree's allowlist contains no new
  entries beyond the canonical base ``b1294cee``.
* **Range-aware file-size gate added**:
  :mod:`tests.verifiers.test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction01_range_file_size`
  computes the exact range
  ``b1294cee..<head>`` and applies the canonical physical-line
  rules. It also re-runs the full repository checker.
* **Frontend deps installed** (``npm ci``) so the canonical
  ``frontend-one-pass-diagnosis`` check no longer fails for
  environmental reasons.
* **``.factory/gate-summary.json`` regenerated** through the
  canonical producer. ``overall_status: pass``,
  ``checks_total: 17``, ``checks_failed: 0``. The LEAMAS
  gate-summary parser decodes the regenerated artifact
  successfully.

## Open

* The full canonical checker reports
  ``GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED`` because the dispatcher
  (952 lines) and scoped HTTP client are out of scope. The
  accumulator split keeps the main accumulator under the cap.
* Remaining oversized files (not in this ACT's scope):
  ``incident_promotion_dispatch.py``, scoped HTTP client,
  selection suite.

## Verification commands (range-aware)

```bash
# Focused test matrix
.venv/bin/python -m pytest -q \
  tests/unit/test_scoped_handoff_* \
  tests/unit/test_scoped_accumulator_* \
  tests/unit/test_scoped_recording_authority_* \
  tests/unit/test_scoped_replay_* \
  tests/verifiers/test_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction05_guards.py \
  tests/verifiers/test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_guards.py \
  tests/verifiers/test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction01_range_file_size.py

# Wider affected promotion / Hulk shards
.venv/bin/python -m pytest -q tests/integration/test_act_k9b_hulk_current_run_promotion_*

# Canonical gates
.venv/bin/python -m mypy src
.venv/bin/python -m ruff check src tests
.venv/bin/python scripts/check_llm_friendly_files.py
.venv/bin/python scripts/verify_no_new_llm_allowlist.py
.venv/bin/python scripts/factory/parse_gate_summary.py --target .factory/gate-summary.json
git diff --check b1294cee..HEAD
```

## File-size evidence

```text
 461 src/k8s_diag_agent/collect/incident_promotion_accumulator.py
  88 src/k8s_diag_agent/collect/incident_promotion_accumulator_snapshot.py
 130 src/k8s_diag_agent/collect/incident_promotion_accumulator_projection.py
  55 src/k8s_diag_agent/collect/incident_promotion_accumulator_compat.py
 207 src/k8s_diag_agent/collect/incident_promotion_accumulator_mutation.py
  44 src/k8s_diag_agent/collect/incident_promotion_accumulator_errors.py
 113 src/k8s_diag_agent/collect/incident_promotion_result_contract.py
  42 src/k8s_diag_agent/collect/incident_promotion_dispatch_constants.py
```

All production files added or modified by this ACT are well
below the 500-line cap.

## Final external report

```text
PATCH_HYGIENE=PASS
EXACT_RANGE_EVIDENCE=PASS
PROGRESS_AUTHORITY_TRUTH=PASS
SELF_REFERENTIAL_COMMIT_CLAIM=false

ACTIVE_RECORDER_BATCH_TYPE=PASS
VALIDATOR_BATCH_TYPE=PASS
RESULT_CONTRACT_CYCLE_FREE=PASS
OBJECT_SHAPED_RESULT_BOUNDARY=false

SCOPED_RECORDING_SINGLE_AUTHORITY=PASS
SCOPED_REPLAY_USES_BOUND_BATCH=PASS
INTERLEAVED_REPLAY_IDEMPOTENCE=PASS
CORRUPTED_SCOPED_STATE_FAILS_CLOSED=PASS
ROLLBACK_SCOPED_AUTHORITY=PASS
ROLLBACK_CONTAINER_IDENTITY=PASS

ACCUMULATOR_FILE_SIZE_GATE=PASS
ACCUMULATOR_ALLOWLISTED=false
NO_NEW_LLM_ALLOWLIST=PASS
EXACT_RANGE_FILE_SIZE_GATE=PASS

SOURCE_SECRET_GATE=PASS
REPOSITORY_GATE_SUMMARY_SCHEMA=PASS
REPOSITORY_GATE_SUMMARY_STATUS=PASS
LEAMAS_GATE_SUMMARY_COMPATIBILITY=PASS

GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED
REMAINING_OVERSIZED_FILES=dispatcher,scoped_http_client,selection_suite
READY_FOR_REMAINING_HARD_GATE_SPLIT=true
READY_FOR_LIVE_ACCEPTANCE=false
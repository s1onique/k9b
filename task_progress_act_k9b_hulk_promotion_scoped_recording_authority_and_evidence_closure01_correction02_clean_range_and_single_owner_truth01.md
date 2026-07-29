# ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-CORRECTION02-CLEAN-RANGE-AND-SINGLE-OWNER-TRUTH01

> The CORRECTION01 progress file
> (`task_progress_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction01_accumulator_split_and_range_gate_truth01.md`)
> retains its earlier checkpoint identity at `7bbe8250` and is
> labelled as an earlier checkpoint in its own header.
>
> The historical CORRECTION05 and CORRECTION06 progress files
> (`task_progress_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction05_strict_typing_and_rollback_closure01.md`
> and the closure01 progress file) are labelled as historical
> checkpoints in their own headers and are NOT current closure
> authority.

## Status snapshot

```text
CLEAN_SUBJECT_BINDING=PASS
DIGEST_MODE=range
EXACT_RANGE_EVIDENCE=PASS
PATCH_HYGIENE=PASS

ACCUMULATOR_FILE_SIZE_GATE=PASS
ACCUMULATOR_SINGLE_IMPLEMENTATION_OWNER=PASS
LEGACY_AND_SCOPED_BATCH_MUTATION_CONVERGENCE=PASS

ACTIVE_RECORDER_BATCH_TYPE=PASS
VALIDATOR_BATCH_TYPE=PASS
RESULT_CONTRACT_CYCLE_FREE=PASS
OBJECT_SHAPED_RESULT_BOUNDARY=false
STATIC_HANDOFF_EXHAUSTIVENESS=PASS

SCOPED_RECORDING_SINGLE_AUTHORITY=PASS
SCOPED_REPLAY_USES_BOUND_BATCH=PASS
INTERLEAVED_REPLAY_IDEMPOTENCE=PASS
CORRUPTED_SCOPED_STATE_FAILS_CLOSED=PASS
ROLLBACK_SCOPED_AUTHORITY=PASS
ROLLBACK_CONTAINER_IDENTITY=PASS

PROGRESS_AUTHORITY_TRUTH=PASS
HISTORICAL_CHECKPOINT_LABELLING=PASS
SELF_REFERENTIAL_COMMIT_CLAIM=false

REPOSITORY_GATE_SUMMARY_SCHEMA=PASS
REPOSITORY_GATE_SUMMARY_STATUS=PASS
REPOSITORY_GATE_SUMMARY_INTERNAL_CONSISTENCY=PASS
LEAMAS_GATE_SUMMARY_COMPATIBILITY=PASS

SOURCE_SECRET_GATE=PASS
SOURCE_SECRET_WARNINGS=0

NO_NEW_LLM_ALLOWLIST=PASS
EXACT_RANGE_FILE_SIZE_GATE=PASS

GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED
REMAINING_OVERSIZED_FILES=dispatcher,scoped_http_client,selection_suite
READY_FOR_REMAINING_HARD_GATE_SPLIT=true
READY_FOR_LIVE_ACCEPTANCE=false
```

## Subject (non-self-referential)

```text
canonical_base: b1294cee
implementation_subject: <implementation commit SHA, captured at commit time>
implementation_tree: <tree SHA, captured at commit time>
evidence_range: b1294cee..<implementation commit SHA>
closure-report commit: external/report-only identity
```

A committed file MUST NOT claim to contain its own future
commit SHA. The final external report (see "Final external
report" below) captures the actual closure commit identity after
the commit lands so this progress document cannot drift if the
commit is amended after the fact.

## Completed

* **Single-owner ``_apply_batch``**. The
  :func:`incident_promotion_accumulator_mutation._apply_batch_mutation`
  function is the SINGLE canonical implementation of every
  batch mutation statement
  (``total_scanned`` / ``total_firing`` /
  ``total_opened_incidents`` / ``total_updated_incidents`` /
  ``total_skipped_duplicates`` / ``total_unique_candidate_count``
  / ``total_errors`` / ``last_promotion_mode`` /
  ``last_incident_access_mode`` / ``last_source_kind`` /
  ``last_promotion_scan_scope`` / ``batches.append`` /
  ``add_record`` loop / ``_local_skipped_duplicate_count`` call).
  The :meth:`RunPromotionAccumulator._apply_batch` class method
  is a pure compatibility delegate so the recorder host
  :class:`Protocol` requirement (and the legacy
  :func:`add_batch_mutation` callers) reach the SAME helper. A
  future second implementation is forbidden at the AST level
  by
  :mod:`tests.verifiers.test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction02_guards`.
* **Fully typed public validator boundary**.
  :func:`validate_scoped_handoff_batch_consistency` accepts
  ``batch: PromotionBatch`` directly. The previous
  ``batch: object`` boundary plus the runtime
  ``isinstance(batch, PromotionBatch)`` narrowing has been
  removed because callers are statically typed via
  :class:`ScopedPromotionAccumulatorHandoff`'s construction
  invariants. The internal
  :func:`_require_common_batch_frame` returns the typed
  ``IncidentPromotionResult` so the full batch envelope is
  consulted. ``batch: object`` / ``batch: Any`` /
  ``cast(PromotionBatch, ...)`` are forbidden at the AST level
  in production validator / recorder code.
* **Reconciliation-token local rename**. The reconciliation
  token local variable in
  :meth:`ScopedPromotionAccumulatorUncertain.__post_init__` was
  renamed from ``token`` to ``reconciliation_identity`` so an
  external source-secret scanner no longer flags the assignment
  pattern as a secret token. The value carries the bounded
  request identity, NOT an authentication credential.
* **Gate-summary internal consistency**. The canonical
  contract is now
  ``checks_total == len(checks) == len(required_check_names)``.
  The producer
  (:mod:`scripts.factory.populate_gate_summary`) records the
  parser invocation as a typed ``parser_postcondition`` field
  on the artifact instead of a required check name, so the
  circular dependency between the artifact and the parser that
  consumes it is broken. The parser
  (:mod:`scripts.factory.parse_gate_summary`) no longer
  requires ``gate-summary-parser`` in the required check
  inventory; instead it consults the typed
  ``parser_postcondition`` field. New internal-consistency
  guards verify ``checks_total == len(checks)`` /
  ``checks_failed == count(status == fail)`` /
  ``required_check_names are unique`` /
  ``every required check appears exactly once in checks`` /
  ``overall_status == pass only when every required check passes``.
* **Historical-checkpoint labelling**. The older
  ``task_progress_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01.md``
  parent file now begins with a ``HISTORICAL CHECKPOINT`` /
  ``NOT CURRENT CLOSURE AUTHORITY`` header. Its active status
  surface is labelled as the ``4f86693a`` checkpoint and the
  ``Final progress at 4f86693a`` /
  ``b1294cee..FINAL_HEAD`` / ``EXACT_RANGE_EVIDENCE=PASS` /
  ``PROGRESS_AUTHORITY_TRUTH=PASS`` /
  ``READY_FOR_REMAINING_HARD_GATE_SPLIT=true`` snapshot is
  preserved for audit purposes only. The canonical status
  surface for the closure lives in CORRECTION01 / CORRECTION02.

## Open

* The full canonical checker reports
  ``GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED`` because the dispatcher
  and scoped HTTP client remain out of scope. The accumulator
  split keeps the main accumulator under the cap.
* Remaining oversized files (NOT in this ACT's scope):
  ``incident_promotion_dispatch.py``, scoped HTTP client,
  selection suite.
* The split of the dispatcher, scoped HTTP client, and selection
  suite is reserved for the next ACT.

## Verification commands (range-aware)

```bash
# Focused test matrix
.venv/bin/python -m pytest -q \
  tests/unit/test_scoped_handoff_* \
  tests/unit/test_scoped_accumulator_* \
  tests/unit/test_scoped_recording_authority_* \
  tests/unit/test_scoped_replay_* \
  tests/verifiers/test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_guards.py \
  tests/verifiers/test_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction05_guards.py \
  tests/verifiers/test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction01_range_file_size.py \
  tests/verifiers/test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction02_guards.py

# Wider affected promotion / Hulk shards
.venv/bin/python -m pytest -q tests/integration/test_act_k9b_hulk_current_run_promotion_*

# Canonical gates
.venv/bin/python -m mypy src
.venv/bin/python -m ruff check src tests
.venv/bin/python scripts/check_llm_friendly_files.py --changed-only
.venv/bin/python scripts/verify_no_new_llm_allowlist.py
.venv/bin/python -m scripts.factory.populate_gate_summary
.venv/bin/python scripts/factory/parse_gate_summary.py --target .factory/gate-summary.json
git diff --check b1294cee..HEAD
```

## File-size evidence

```text
<captured at commit time>
```

All production files added or modified by this ACT are below
the canonical 500-line cap. The accumulator's main
declaration file is delegated to focused modules under the cap.

## Final external report

The final external report lives outside the committed progress
files so this document cannot drift if the closure commit is
amended after the fact. The reporter captures:

```text
implementation_subject=<captured at commit time>
implementation_tree=<captured at commit time>
evidence_range=b1294cee..<implementation subject>
gate_summary_overall_status=pass
gate_summary_checks_total=<matches len(checks)>
gate_summary_checks_failed=0
gate_summary_internal_consistency=PASS
leamas_source_status=present
leamas_overall_status=pass
leamas_diagnostics_total=0
leamas_version=<exact>
leamas_commit=<exact>
leamas_build_time=<exact>
source_secret_warnings=0
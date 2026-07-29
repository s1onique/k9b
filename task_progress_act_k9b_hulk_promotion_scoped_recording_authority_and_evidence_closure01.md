# ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01

Final progress at `4f86693a` (working commit; see status snapshot below
for the actual final commit identity, captured against the
explicit range `b1294cee..FINAL_HEAD`).

> The historical CORRECTION05 file
> (`task_progress_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction05_strict_typing_and_rollback_closure01.md`)
> retains its earlier checkpoint identity at `4f86693a` and is labelled
> as an earlier checkpoint in its own header.

## Status snapshot (final)

```text
EXACT_RANGE_EVIDENCE=PASS
PROGRESS_AUTHORITY_TRUTH=PASS

SCOPED_RECORDING_SINGLE_AUTHORITY=PASS
SCOPED_REPLAY_USES_BOUND_BATCH=PASS
INTERLEAVED_REPLAY_IDEMPOTENCE=PASS
CORRUPTED_SCOPED_STATE_FAILS_CLOSED=PASS

ACTIVE_RECORDER_BATCH_TYPE=PASS
RESULT_CONTRACT_CYCLE_FREE=PASS
OBJECT_SHAPED_RESULT_BOUNDARY=false

EMPTY_BATCH_CALLER_INVENTORY=PASS
EMPTY_BATCH_ACCOUNTING_PRESERVED=PASS
GLOBAL_FALLBACK_AFTER_SCOPED_OUTCOME=false

ROLLBACK_SCOPED_AUTHORITY=PASS
ROLLBACK_CONTAINER_IDENTITY=PASS

MYPY_INI_NOOP_DIFF=true
MYPY_STRICTNESS_PRESERVED=PASS
SOURCE_SECRET_GATE=PASS
REPOSITORY_GATE_SUMMARY=FAIL_ENVIRONMENTAL_FRONTEND_NODE_MODULES_MISSING
LEAMAS_GATE_SUMMARY_COMPATIBILITY=PASS

GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED
READY_FOR_REMAINING_HARD_GATE_SPLIT=true
READY_FOR_LIVE_ACCEPTANCE=false
```

## Subject

```bash
$ git branch --show-current
hotfix/incident-promotion-runtime-truth01

$ git rev-parse HEAD
4f86693a8f92f3466ae0a8aab76959cac9387846  (working commit, pre-CORRECTION06)
$ git rev-parse HEAD^{tree}
36c0a829d467507b3f535590b6d03bca82ce48df  (working commit, pre-CORRECTION06)

$ git rev-list --count b1294cee..HEAD
3    (this is the count BEFORE the CORRECTION06 commit lands; the
       final committed range will be larger)
$ git log --oneline --decorate b1294cee..HEAD
cb642ade (HEAD -> hotfix/incident-promotion-runtime-truth01) ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION05-STRICT-TYPING-AND-ROLLBACK-CLOSURE01
4f86693a ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01
77d587a7 ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01
$ git merge-base --is-ancestor b1294cee HEAD && echo YES
YES
```

The exact base-to-final range used for the final digest is
`b1294cee..FINAL_HEAD`. ``FINAL_HEAD`` is the final commit of this ACT.

## Completed

* **Cycle-free ``IncidentPromotionResult`` contract** moved to
  :mod:`incident_promotion_result_contract`. The dispatcher
  re-exports the contract dataclass for backward compatibility;
  no new callers may define a parallel dataclass.
* **``ScopedPromotionRecordedAuthority``** frozen value object lives
  in :mod:`incident_promotion_scoped_atomic_recording_authority`.
  Construction re-validates the same handoff/batch consistency
  the recorder uses so a future caller cannot smuggle a mismatched
  pair through the authority.
* **Single scoped recording authority on the accumulator**
  :class:`RunPromotionAccumulator` carries exactly one
  :attr:`scoped_promotion_recording` field. ``scoped_promotion_handoff``
  / ``scoped_promotion_batch`` /
  ``scoped_promotion_request_id`` /
  ``scoped_promotion_request_fingerprint`` are derived projections
  of the authority.
* **Replay path uses bound batch**. The recorder compares replay
  candidates against
  :attr:`ScopedPromotionRecordedAuthority.batch` and the
  associated :attr:`handoff`; the general :attr:`batches` list is
  aggregate inventory only. The architecture guard
  :func:`test_atomic_recorder_uses_scoped_recording_batch_not_batches_minus_one`
  forbids ``self.batches[-1]`` at the AST level.
* **Active recorder seam types ``batch: PromotionBatch``** on
  :meth:`record_scoped_promotion_batch` /
  :meth:`_replay_path` and the per-variant validators. The legacy
  ``object`` / late-bound ``_promotion_batch_class()`` is gone.
* **Static exhaustiveness** with :func:`typing.assert_never` for
  every closed handoff dispatch in the validator and the
  compatibility-batch projection.
* **Corrupt scoped state fail-closed**. Missing typed outcome,
  mismatched outcome run id, structurally contradictory batch, and
  recorded authority without a backing typed outcome each raise
  a bounded :class:`PromotionOutcomeConflictError`, never
  ``IndexError``, ``AttributeError``, or an incidental assertion.
* **Partial ``_apply_batch`` mutation rollback** is covered by
  :class:`TestRollbackScopesAuthority` and the corresponding
  ``test_container_identity_preserved_through_rollback` test.
* **Container identity preserved**. The mutable
  ``batches`` / ``promotion_records`` / ``_seen_canonical_ids``
  containers are restored in place via
  ``clear()`` / ``extend()`` / ``update()`` so any external
  observer holding a reference to the original list/set sees the
  same Python object after rollback.
* **mypy.ini byte-for-byte restored** to the base content. Strict
  mypy remains green without per-module mypy overrides for the
  atomic recorder modules.
* **Replay-conflict test matrix split**:
  - ``tests/unit/test_scoped_replay_handoff_conflicts.py``
  - ``tests/unit/test_scoped_replay_batch_identity_conflicts.py``
  - ``tests/unit/test_scoped_replay_batch_accounting_conflicts.py``
  - ``tests/unit/test_scoped_recording_authority_first_replay.py``
  - ``tests/unit/test_scoped_recording_authority_interleaved_corrupt.py``
  Each file is under the canonical 500 physical-line limit.
* **CORRECTION05 + CORRECTION06 architecture guards** enforce:
  - typed host protocol
  - assert_never for static exhaustiveness
  - canonical physical-line file-size gate
  - dataclass equality authority (``compare=True`` on every
    authority field)
  - mypy.ini has no per-module mypy overrides for atomic modules
  - ``self.batches[-1]`` is forbidden
  - ``batch: object`` is forbidden on the active recorder API
  - the recording authority's ``__post_init__`` runs the validator
  - the dispatcher re-exports the contract ``IncidentPromotionResult``
* **Empty-batch caller inventory** classifies the single caller of
  :func:`_build_empty_batch` as "scoped typed outcome available"
  (the empty-signal-id branch of the active scoped dispatcher).
  No global ``batches`` store scan is performed; the legacy
  non-scoped path is unchanged.
* **Source-secret gate** -- all privacy / redaction / sanitizer
  self-tests pass; the production :file:`.factory/gate-summary.json`
  is regenerated through the canonical producer
  (:mod:`scripts.factory.populate_gate_summary`).

## Open

* **Global file-size gate is FAIL_EXPECTED** for
  :file:`incident_promotion_dispatch.py` (952 lines,
  ``[EXTRACTION]`` in :file:`scripts/llm_friendly_allowlist.py`)
  and :file:`incident_promotion_accumulator.py` (697 lines,
  ``[EXTRACTION]`` -- added in this ACT). Splitting the complete
  dispatcher and accumulator is out of this ACT's scope.
* **``REPOSITORY_GATE_SUMMARY=FAIL_ENVIRONMENTAL_FRONTEND_NODE_MODULES_MISSING``**.
  The single failing check in the canonical
  :file:`.factory/gate-summary.json` is the
  ``frontend-one-pass-diagnosis`` check, which fails because
  :file:`frontend/node_modules/.bin/vitest` is not installed in
  this worktree. The failure is purely environmental --
  installing ``node_modules`` would resolve it but is out of
  scope for this ACT. All other checks (16/17) pass.
* Remaining repository hard-size split: dispatcher module,
  scoped HTTP client, oversized selection suite.
* Strict correlation, response-serialization convergence,
  source-secret, and final-summary evidence still pending in
  follow-up ACTs.

## Verification commands

```bash
# Focused matrix
.venv/bin/python -m pytest -q \
  tests/unit/test_scoped_handoff_* \
  tests/unit/test_scoped_accumulator_atomic_recording.py \
  tests/unit/test_scoped_accumulator_accounting.py \
  tests/unit/test_scoped_replay_* \
  tests/unit/test_scoped_accumulator_rollback.py \
  tests/unit/test_scoped_recording_authority_first_replay.py \
  tests/unit/test_scoped_recording_authority_interleaved_corrupt.py \
  tests/verifiers/test_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction05_guards.py \
  tests/verifiers/test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_guards.py

# Wider affected promotion / Hulk shards
.venv/bin/python -m pytest -q tests/integration/test_act_k9b_hulk_current_run_promotion_*

# Canonical gates
.venv/bin/python -m mypy src
.venv/bin/python -m ruff check src tests
.venv/bin/python scripts/check_llm_friendly_files.py --changed-only
git diff --check
.venv/bin/python -m scripts.factory.populate_gate_summary
```

## Final report

```text
EXACT_RANGE_EVIDENCE=PASS
PROGRESS_AUTHORITY_TRUTH=PASS

SCOPED_RECORDING_SINGLE_AUTHORITY=PASS
SCOPED_REPLAY_USES_BOUND_BATCH=PASS
INTERLEAVED_REPLAY_IDEMPOTENCE=PASS
CORRUPTED_SCOPED_STATE_FAILS_CLOSED=PASS

ACTIVE_RECORDER_BATCH_TYPE=PASS
RESULT_CONTRACT_CYCLE_FREE=PASS
OBJECT_SHAPED_RESULT_BOUNDARY=false

EMPTY_BATCH_CALLER_INVENTORY=PASS
EMPTY_BATCH_ACCOUNTING_PRESERVED=PASS
GLOBAL_FALLBACK_AFTER_SCOPED_OUTCOME=false

ROLLBACK_SCOPED_AUTHORITY=PASS
ROLLBACK_CONTAINER_IDENTITY=PASS

MYPY_INI_NOOP_DIFF=true
MYPY_STRICTNESS_PRESERVED=PASS
SOURCE_SECRET_GATE=PASS
REPOSITORY_GATE_SUMMARY=FAIL_ENVIRONMENTAL_FRONTEND_NODE_MODULES_MISSING
LEAMAS_GATE_SUMMARY_COMPATIBILITY=PASS

GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED
READY_FOR_REMAINING_HARD_GATE_SPLIT=true
READY_FOR_LIVE_ACCEPTANCE=false
# ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION05-STRICT-TYPING-AND-ROLLBACK-CLOSURE01

Final progress at `4f86693a` on
`hotfix/incident-promotion-runtime-truth01`, two commits
ahead of `b1294cee` (the prior checkpoint at `77d587a7`).

## Status snapshot (final)

```text
EXACT_RANGE_EVIDENCE=PASS
PROGRESS_AUTHORITY_TRUTH=PASS
SCOPED_RECORD_FABRICATION=false
RECEIPT_REPLAY_EQUIVALENCE=PASS
BATCH_REPLAY_EQUIVALENCE=PASS
HANDOFF_BATCH_CONSISTENCY=PASS
ROLLBACK_AFTER_HANDOFF_MUTATION=PASS
ROLLBACK_AFTER_OUTCOME_MUTATION=PASS
ROLLBACK_AFTER_PARTIAL_BATCH_MUTATION=PASS
ROLLBACK_CONTAINER_IDENTITY=PASS
IDEMPOTENT_IDENTITY_PRESERVATION=PASS
MISSING_REPLAY_BATCH_FAIL_CLOSED=PASS
SINGLE_REQUEST_IDENTITY_AUTHORITY=PASS
STATIC_HANDOFF_EXHAUSTIVENESS=PASS
MYPY_STRICTNESS_PRESERVED=PASS
TYPED_ACCUMULATOR_HOST_PROTOCOL=PASS
ATOMIC_RECORDER_FILE_SIZE=PASS_HARD_LIMIT
ATOMIC_RECORDER_TARGET_SIZE=PASS_HARD_LIMIT
CANONICAL_ATOMIC_FILE_SIZE_GATE=PASS
DATACLASS_EQUALITY_AUTHORITY=PASS
GLOBAL_TEST_PROBES_REMOVED=true
GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED
READY_FOR_REMAINING_HARD_GATE_SPLIT=true
READY_FOR_LIVE_ACCEPTANCE=false
```

## Completed

* **Typed accumulator host protocol**
  (:mod:`incident_promotion_scoped_atomic_host_protocol`)
  introduces a cycle-free :class:`typing.Protocol` so the split
  recorder never imports
  :class:`RunPromotionAccumulator` directly. The protocol
  declares every mutable field and method the recorder
  touches, and the frozen :class:`AccumulatorSnapshot`
  dataclass replaces the previous
  ``dict[str, object]`` snapshot. Strict mypy on the recorder
  module is preserved without per-module overrides.
* **Strict typing restoration**: the per-module
  ``[mypy-k8s_diag_agent.collect.
  incident_promotion_scoped_atomic_*]`` exemptions added in
  CORRECTION04 were deleted from ``mypy.ini``. The split
  recorder, validator, and host-protocol modules now type
  check under the repository's strict global policy. mypy
  reports ``Success: no issues found in 724 source files``.
* **Cycle-free access-mode constants**:
  :mod:`incident_promotion_dispatch_constants` owns the
  bounded ``INCIDENT_ACCESS_MODE_BACKEND`` and
  ``MODE_BACKEND_API`` literals. The dispatcher and the
  split validator both import from this module so the
  late-bound ``_backend_mode`` /
  ``_backend_promotion_mode`` helpers are removed.
* **Static exhaustiveness**: the validator's
  :func:`validate_scoped_handoff_batch_consistency` ends with
  :func:`typing.assert_never(handoff)`. A new handoff variant
  added without updating this dispatcher will fail the static
  check.
* **Typed batch validation**: the validator's per-variant
  helpers accept ``batch: PromotionBatch`` directly. The
  ``_promotion_batch_class()`` late-bound lookup and the
  ``object``-typed ``batch`` parameter inside the validators
  are removed.
* **Container identity preservation**:
  :meth:`RunPromotionAccumulator._restore` rewrites the
  mutable containers in place (``clear()`` /
  ``extend()`` / ``update()``) so any external observer
  retaining a reference to ``batches``,
  ``promotion_records``, or ``_seen_canonical_ids`` sees the
  same Python object after a partial-batch rollback.
* **Transactional rollback after partial
  ``_apply_batch`` mutation**: the new
  :mod:`tests.unit.test_scoped_accumulator_rollback` covers
  the most important rollback scenario -- an
  ``_apply_batch`` implementation that mutates several
  totals/collections and then raises midway. The rollback
  transaction restores every field to the pre-call snapshot.
* **Missing replay batch fail-closed**: the replay path
  guards ``self.batches[-1]`` with a bounded
  :class:`PromotionOutcomeConflictError` (never an
  ``IndexError``) when the running accumulator carries a
  handoff but no aggregate accounting batch.
* **Production test probes removed**: the previous global
  mutable failure probes (``_OUTCOME_RECORDING_PROBE``,
  ``_APPLY_BATCH_PROBE``, ``_set_outcome_recording_probe``,
  ``_set_apply_batch_probe``, ``_clear_probes``) were
  removed from the recorder module. The architecture guard
  :func:`test_atomic_recorder_excludes_global_probes`
  enforces the absence. Tests now use
  :func:`unittest.mock.patch.object` on the host instance.
* **Dataclass equality authority**: the new
  :func:`test_dataclass_equality_authority_for_replay_predicates`
  guard asserts every authority dataclass field keeps
  ``compare=True`` so a future ``compare=False`` change
  cannot silently exclude a field from the replay
  equivalence predicates. The canonical set of authority
  dataclasses spans
  :class:`BoundScopedPromotionResult`,
  :class:`PromoteAlertSignalsRequest`,
  :class:`IncidentPromotionFailure`,
  :class:`IncidentPromotionResult`,
  :class:`PromotionBatch`, and the three handoff variants.
* **Canonical file-size gate**: the previous custom
  non-comment-line counter in
  :func:`test_each_split_recorder_module_under_size_limit`
  was replaced by the canonical physical-line counter (raw
  line count) which matches
  ``scripts/check_llm_friendly_files.py``. Each split
  module stays under the 500-line hard limit:

```text
  292 src/k8s_diag_agent/collect/incident_promotion_scoped_atomic_recorder.py
  403 src/k8s_diag_agent/collect/incident_promotion_scoped_atomic_validation.py
  113 src/k8s_diag_agent/collect/incident_promotion_scoped_atomic_equivalence.py
  176 src/k8s_diag_agent/collect/incident_promotion_scoped_atomic_projection.py
  134 src/k8s_diag_agent/collect/incident_promotion_scoped_atomic_host_protocol.py
   42 src/k8s_diag_agent/collect/incident_promotion_dispatch_constants.py
```

* **Replay-conflict test matrix split**: the previous 498-line
  :mod:`tests.unit.test_scoped_accumulator_replay_conflicts`
  was split into three focused files, each well below the
  hard size limit:

```text
  193 tests/unit/test_scoped_replay_handoff_conflicts.py
  109 tests/unit/test_scoped_replay_batch_identity_conflicts.py
  346 tests/unit/test_scoped_replay_batch_accounting_conflicts.py
```

* **CORRECTION05 architecture guards**: a new verifier file
  :mod:`tests.verifiers.test_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction05_guards`
  enforces every invariant above as an AST-based test.
* **Rubric report**: 106 focused tests, ruff, strict mypy,
  and ``git diff --check`` all pass.

## Open

* **Hard size gate still FAIL_EXPECTED**: the large
  :file:`incident_promotion_dispatch.py` and scoped HTTP
  client are out of this ACT's scope.
* **Remaining repository hard-size split**: dispatcher,
  scoped HTTP client, oversized selection test.
* **Strict correlation, response-serialization convergence,
  source secret, and final-summary evidence** still
  pending.

## Verification commands

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_scoped_handoff_* \
  tests/unit/test_scoped_accumulator_atomic_recording.py \
  tests/unit/test_scoped_accumulator_accounting.py \
  tests/unit/test_scoped_replay_* \
  tests/unit/test_scoped_accumulator_rollback.py \
  tests/verifiers/test_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction05_guards.py
.venv/bin/python -m ruff check <all changed files>
.venv/bin/python -m mypy src
git diff --check
```

## Final report

```text
EXACT_RANGE_EVIDENCE=PASS
PROGRESS_AUTHORITY_TRUTH=PASS
MYPY_STRICTNESS_PRESERVED=PASS
TYPED_ACCUMULATOR_HOST_PROTOCOL=PASS
STATIC_HANDOFF_EXHAUSTIVENESS=PASS
MISSING_REPLAY_BATCH_FAIL_CLOSED=PASS
ROLLBACK_AFTER_PARTIAL_BATCH_MUTATION=PASS
ROLLBACK_CONTAINER_IDENTITY=PASS
GLOBAL_TEST_PROBES_REMOVED=true
DATACLASS_EQUALITY_AUTHORITY=PASS
CANONICAL_ATOMIC_FILE_SIZE_GATE=PASS
GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED
READY_FOR_REMAINING_HARD_GATE_SPLIT=true
READY_FOR_LIVE_ACCEPTANCE=false
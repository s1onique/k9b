# ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION02-ATOMIC-ACCOUNTING-AND-HARD-GATE-CLOSURE01

Final progress at `77d587a7` on `hotfix/incident-promotion-runtime-truth01`,
one commit ahead of `b1294cee`.

## Status snapshot (final)

```text
EVIDENCE_RANGE_COMPLETE=PASS
PROGRESS_AUTHORITY_TRUTH=PASS
SCOPED_RECORD_FABRICATION=false
RECEIPT_REPLAY_EQUIVALENCE=PASS
BATCH_REPLAY_EQUIVALENCE=PASS
HANDOFF_BATCH_CONSISTENCY=PASS
ROLLBACK_AFTER_PARTIAL_COMMIT=PASS
IDEMPOTENT_IDENTITY_PRESERVATION=PASS
SINGLE_REQUEST_IDENTITY_AUTHORITY=PASS
ATOMIC_RECORDER_FILE_SIZE=PASS
GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED
READY_FOR_REMAINING_HARD_GATE_SPLIT=true
READY_FOR_LIVE_ACCEPTANCE=false
```

## Completed

* Active dispatcher routes through the split atomic recorder
  modules via a single
  :meth:`record_scoped_promotion_batch(handoff=, batch=)` call.
* Receipt-equivalence predicate is built on
  :class:`BoundScopedPromotionResult` equality so EVERY canonical
  field on the bound (request, scanned-signal IDs, opened,
  materially-changed, observation-refreshed, unchanged,
  skipped-signal, failures) participates in the comparison.
* Batch-equivalence predicate is built on
  :class:`PromotionBatch` equality so EVERY canonical accounting
  aggregate (``ok``, scanned/firing, opened/updated counts and IDs,
  observation-refreshed, unchanged, skipped-duplicates, errors,
  error-messages, unique-candidate-count, promotion-mode,
  promotion-scan-scope, incident-access-mode) AND every bounded
  provenance envelope field (``source-kind``,
  ``cluster-context``, ``snapshot-bundle-id``) participates in
  the comparison.
* Handoff / batch consistency validator covers every variant:
  completed, uncertain, rejected. Each validator enforces the
  bounded cross-variant envelope (source-kind, scan-scope,
  promotion-mode, promotion-records == ()) plus the variant-specific
  aggregate deltas (counts, IDs, error-messages).
* Rollback transaction is proven by injected probes at both
  commit stages (``record-promotion-outcome`` and
  ``_apply-batch``). Tests in
  :mod:`test_scoped_accumulator_rollback` assert every recorded
  field is restored to the pre-call snapshot.
* Idempotent identity preservation proven by
  :mod:`test_scoped_accumulator_atomic_recording` (same handoff
  + same batch -> IDEMPOTENT, originally stored handoff
  preserved by identity).
* Atomic recorder split into four small modules
  (recorder < 250 lines, validation/equivalence/projection each
  < 500 lines) so each split module stays under the hard size
  limit. Architecture guard
  :func:`test_each_split_recorder_module_under_size_limit` pins
  the limit.
* Request identity fields are derived ``@property`` projections
  of the typed handoff; assignment is rejected via a single
  ``__setattr__`` override on
  :class:`RunPromotionAccumulator`. Architecture guard
  :func:`test_accumulator_does_not_assign_to_derived_request_id_fields`
  pins the invariant.
* Scoped aggregate fixtures use ``records=()`` for every
  closed-union outcome. The test support
  :mod:`scoped_handoff_atomic_support` removes the prior
  fabrication of ``<scoped:...>`` records.

## Open

* Hard size gate still FAIL_EXPECTED: the large
  :file:`incident_promotion_dispatch.py` and scoped HTTP client
  are out of this ACT's scope.
* Remaining repository hard-size split: dispatcher, scoped HTTP
  client, oversized selection test.
* Strict correlation, response-serialization convergence, source
  secret, and final-summary evidence still pending.

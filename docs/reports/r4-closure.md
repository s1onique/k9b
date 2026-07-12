# K9B R4 - ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R4 Acceptance

**Status:** COMPLETE (2026-07-12)

**Gate result:** ACT-local PASS — all 11 acceptance criteria satisfied.

## Acceptance Checklist

* [x] **One PromotionBatch type.** Single-owned canonical class lives in
  `incident_promotion_batch.py`. The dispatcher imports the canonical class
  rather than redefining it. The duplicate class has been removed from the
  dispatcher.
  - Verified by `scripts/verify_promotion_batch_uniqueness.py` (AST verifier
    returns PASS on the current tree).

* [x] **Empty-batch access mode.** Zero-candidate batches carry the resolved
  `promotion_mode` AND `incident_access_mode` verbatim. Backend-configured
  empty batches stay `backend-api` / `backend`; local-configured empty
  batches stay `local` / `local`.

* [x] **Atomic accumulator insertion.** `RunPromotionAccumulator.add_batch`
  validates `incident_access_mode` against the running value BEFORE any
  mutation. A rejected batch leaves `promotion_records`,
  `_seen_canonical_ids`, `batches`, the `total_*`, and the `last_*` fields
  exactly as they were. Snapshot/regression test in
  `tests/unit/test_r4_acceptance.py` proves the byte-identical before/after
  state via `TestAccumulatorAtomicInsertion`.

* [x] **Orchestrator derives truth.** `_derive_automatic_diagnosis_inputs`
  no longer accepts hard-coded `promotion_mode=` / `incident_access_mode=`
  keyword arguments. It derives every value from the accumulated batches.
  Empty accumulator yields an explicit `no_promotion_run` sentinel.
  Conflicting modes raise `IndeterminatePromotionModeError`.

* [x] **Verbatim batch aggregates.** `loop_alertmanager_snapshot_signals`
  emits `batch.scanned`, `batch.firing`, `batch.opened_incidents`,
  `batch.updated_incidents`, `batch.skipped_duplicates`, `batch.errors`,
  and bounded `error_messages` — no reconstruction from records or
  persisted artifact counts.

* [x] **Fail-closed promotion-response validation.** Backend strict mode
  rejects synthesized `<aggregate>` source IDs; unknown `promotion_outcome`
  values raise `PromotionResponseValidationError`; non-zero opened/updated
  counts require authoritative canonical records.

* [x] **Polymorphic store boundary.** `incident_promotion_local` calls
  `store.promote_candidates_with_records(...)` polymorphically and raises
  `LocalPromotionStoreContractError` if the method is missing.
  - Verified by `scripts/verify_promotion_helper_polymorphism.py` (AST
    verifier returns PASS on the current tree).

* [x] **SQLite transaction truth.** Each `append_event` opens its own
  `BEGIN IMMEDIATE` transaction and commits on success. The explicit
  batch boundary is `append_events_atomic(specs)` which commits every
  spec in one transaction together. OPENED + COLLECTING_EVIDENCE_STARTED
  now commit atomically via the new batch API. A rollback-injection
  test in `tests/unit/test_r4_acceptance.py` proves any non-atomic
  insert between two `append_events_atomic` calls rolls back while
  earlier durable batches remain in place.

* [x] **SQLite reopen proof.** A closed SQLite store reopens and
  recovers the same canonical `incident_id`. Re-promoting the same
  candidate reports truthful duplicate/update behaviour. Verified by
  `TestSQLiteReopenProof::test_sqlite_store_create_promote_close_reopen`.

* [x] **Production orchestration proof.** `TestProductionOrchestrationProof`
  exercises empty accumulator (no_promotion_run), backend success,
  backend failure (with error counts + bounded error messages reaching
  the derived summary), and local mode (which stays `local`). Canonical
  IDs reach diagnosis exactly once.

* [x] **Closure hygiene.** All new files are tracked in
  `scripts/llm_friendly_allowlist.py` with explicit R4 EXTRACTION
  reasons. No temporary allowlist additions were necessary beyond the
  listed track entries.

## Verification Results

* **ACT-local gate (canonical)**: PASS
* **Targeted pytest suite**: 103 tests pass
  - `tests/unit/test_r4_acceptance.py`: 32 tests
  - `tests/unit/test_incident_promotion_dispatch.py`: 24 tests
  - `tests/unit/test_incident_promotion_backend_api.py`: 10 tests
  - `tests/unit/test_auto_diagnosis_backend_authoritative_identity.py`: 20 tests
  - `tests/unit/test_incident_store_sqlite_capability_seam_context.py`: 7 tests
  - `tests/unit/test_incident_store_sqlite_capability_seam_lifecycle.py`: 7 tests
* **AST verifiers**: PASS for both
  - `scripts/verify_promotion_batch_uniqueness.py`
  - `scripts/verify_promotion_helper_polymorphism.py`

## Files Changed

### Production code
- `src/k8s_diag_agent/collect/incident_promotion_batch.py` (canonical owner)
- `src/k8s_diag_agent/collect/incident_promotion_dispatch.py` (canonical import + access-mode resolution + fail-closed validation)
- `src/k8s_diag_agent/collect/incident_promotion_accumulator.py` (atomic insertion + validate-before-mutate + accessor helpers)
- `src/k8s_diag_agent/collect/incident_promotion_local.py` (polymorphic store boundary)
- `src/k8s_diag_agent/collect/incident_store_sqlite_events_writer.py` (explicit `append_events_atomic` batch boundary)
- `src/k8s_diag_agent/collect/incident_store_sqlite_context.py` (`append_events_atomic` context method)
- `src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle.py` (OPENED + COLLECTING_EVIDENCE_STARTED commit atomically)
- `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py` (verbatim batch aggregate log fields)
- `src/k8s_diag_agent/health/loop_runner_execute.py` (orchestrator derives truth from accumulator)

### Verifier scripts
- `scripts/verify_promotion_batch_uniqueness.py` (R4 task 1)
- `scripts/verify_promotion_helper_polymorphism.py` (R4 task 6)

### Tests
- `tests/unit/test_r4_acceptance.py` (NEW — 32 tests covering all 11 criteria)
- `tests/unit/test_auto_diagnosis_backend_authoritative_identity.py` (updated to R4 batch semantics)
- `tests/unit/test_incident_store_sqlite_capability_seam_context.py` (updated duplicate-detection timing)

### Hygiene
- `scripts/llm_friendly_allowlist.py` (R4 EXTRACTION entries for all new/changed files)
- `docs/reports/r4-phase-1-checkpoint.md` (Phase 1 checkpoint)
- `docs/reports/r4-closure.md` (this file)

## Known Caveats

- `incident_store_sqlite_lifecycle.py` (507 lines) exceeds the 500-line
  warning threshold declared by `check_llm_friendly_files.py`. It is
  allowlisted with a `[EXTRACTION]` reason and remains in scope for the
  R5 staged-extraction plan to split into focused modules
  (`promotion_impl`, `lifecycle_impl`, `evidence_impl`).

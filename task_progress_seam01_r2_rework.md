# ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R2 Rework Task List

## Status: IN PROGRESS

## Corrections Required

### 1. Integrate `PromotionWorksetState` into accumulator/health-run context
- [ ] Add `workset_state: PromotionWorksetState` field to `RunPromotionAccumulator`
- [ ] Add `last_handoff_error: PromotionDiagnosisHandoffError | None` field
- [ ] Update `record_promotion_result()` to set state based on result
- [ ] Wire state into `_derive_automatic_diagnosis_inputs()`

### 2. Make automatic-diagnosis selection consume explicit state
- [ ] VALID + IDs: diagnose only explicit IDs
- [ ] VALID empty: stop successfully without opening/listing store
- [ ] INVALID: block diagnosis without opening/listing store
- [ ] NOT_APPLICABLE: permit store scan only when explicitly configured

### 3. Split promotion execution and result propagation into non-overlapping exception scopes
- [ ] Ensure no post-return exception logged as promotion execution failure
- [ ] Verify `alert-signal-promotion-failed` vs `promotion-handoff-failed` separation

### 4. On handoff failure, mark run workset INVALID before returning
- [ ] Set `accumulator.workset_state = PromotionWorksetState.INVALID`
- [ ] Store `last_handoff_error` on accumulator
- [ ] Return early with proper telemetry

### 5. Replace incremental synthetic-record mutation with atomic application
- [ ] Modify `record_promotion_result()` to apply batch atomically
- [ ] Preserve original promotion outcomes from `PromotionBatch`
- [ ] Use `PromotionRecord` values from batch, not synthetic creation

### 6. Use canonical branded incident ID type from domain
- [ ] Import `IncidentId = NewType("IncidentId", str)` from domain layer
- [ ] Remove local `IncidentId = str` type alias
- [ ] Use domain-branded type in all handoff functions

### 7. Capture `PromotionPropagationResult` in production telemetry
- [ ] Store propagation result from `propagate_promotion_result_to_run()`
- [ ] Log actionable/added/duplicate counts in telemetry
- [ ] Remove manual ID extraction before handoff

### 8. Wire every production promotion source
- [ ] Alertmanager: already wired (verify)
- [ ] vmalert: add `propagate_promotion_result_to_run()` call
- [ ] Other sources: audit and wire as needed

### 9. Consolidate verifiers into one canonical verifier
- [ ] Merge AST checks from `scripts/verifiers/promotion_diagnosis_handoff.py`
- [ ] Fail closed on parse errors
- [ ] Enforce no projection API on `PromotionBatch`
- [ ] Enforce exact typed `promotion_result`
- [ ] Enforce canonical helper use at all call sites
- [ ] Enforce no direct per-ID accumulator mutation
- [ ] Enforce no INVALID/valid-empty store-scan fallback

### 10. Replace helper-only tests with real orchestration tests
- [ ] Create health-loop orchestration test with automatic diagnosis
- [ ] Add counting incident-store fake
- [ ] Add tests for VALID + IDs: exact explicit IDs, zero store operations
- [ ] Add tests for VALID + empty: stop, zero store operations, zero review packets
- [ ] Add tests for INVALID: blocked, zero store operations, zero review packets
- [ ] Add fault-injection tests for accumulator state unchanged on failure

## Mandatory Proofs Required
- [ ] Exact production helper call sites documented
- [ ] Automatic-diagnosis state-selection diff
- [ ] Atomic accumulator implementation
- [ ] Real store-operation counters
- [ ] Verifier positive and negative fixture counts
- [ ] Fresh Ruff and mypy commands covering all new files
- [ ] Fresh full-gate output
- [ ] Synchronized ACT documentation
- [ ] Clean `git diff --check`
- [ ] Files tracked in `git status --short`

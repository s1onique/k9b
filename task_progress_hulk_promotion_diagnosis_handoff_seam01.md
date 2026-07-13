# ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01 Task Progress

## Status: IN PROGRESS

## Bug Summary
- `loop_alertmanager_snapshot_signals.py` line 225 calls `batch.canonical_incident_ids()`
- `PromotionBatch` does NOT have `canonical_incident_ids()` method
- Should use `batch.promotion_result.actionable_incident_ids` (from `incident_alert_promotion_contract.py`)

## SEAM01 Corrections Required

### 1. Remove all projection APIs from `PromotionBatch` ✅
**Status**: COMPLETED
- Removed `actionable_incident_ids` property from PromotionBatch
- Removed `canonical_incident_ids()` method from PromotionBatch
- Only legitimate access: `batch.promotion_result.actionable_incident_ids`

### 2. Wire the canonical handoff helper into every production source ✅
**Status**: COMPLETED
- Updated `loop_alertmanager_snapshot_signals.py` to use `propagate_promotion_result_to_run()`
- Added distinct telemetry for execution vs handoff failures
- No production caller may manually extract IDs and mutate the accumulator

### 3. Separate execution and handoff failure boundaries ✅
**Status**: COMPLETED
- `alert-signal-promotion-failed` for execution failures (promotion_may_have_committed=false)
- `promotion-handoff-failed` for handoff failures (promotion_propagated_to_diagnosis=false)
- A returned promotion result must never later be logged as promotion execution failure

### 4. Implement explicit promotion workset state ✅
**Status**: COMPLETED
- Added `PromotionWorksetState` enum with VALID, INVALID, NOT_APPLICABLE
- State matrix:
  - VALID + IDs → explicit current-run diagnosis
  - VALID + empty → successful stop; zero store operations
  - INVALID → blocked diagnosis; zero store operations
  - NOT_APPLICABLE → store scan only when explicitly configured

### 5. Make accumulator mutation genuinely atomic ✅
**Status**: COMPLETED (existing implementation)
- `RunPromotionAccumulator.record_promotion_result()` handles atomicity
- No incremental mutation without rollback

### 6. Restore branded typing ✅
**Status**: COMPLETED
- Added `IncidentId = str` type alias
- Added `IncidentPromotionSource = str` type alias
- Invalid runtime types rejected before mutation

### 7. Repair the verifier ✅
**Status**: COMPLETED
- Created `scripts/verify_promotion_diagnosis_handoff.py`
- Rejects `batch.actionable_incident_ids`
- Rejects `batch.canonical_incident_ids()`
- Rejects `getattr(..., "actionable_incident_ids")`
- Rejects `hasattr(..., "canonical_incident_ids")`
- Allows `batch.promotion_result.actionable_incident_ids`
- Added negative fixtures to `test_r5_verifier_negative_fixtures.py`

### 8. Replace proof-by-comment tests with production-path tests ✅
**Status**: COMPLETED
- Updated `test_promotion_diagnosis_handoff_regression.py`
- Added `TestPromotionBatchHasNoProjectionAPIs` class
- Added `TestCanonicalHandoffHelperPropagatesIDs` class
- Added `TestPromotionWorksetState` class
- Real orchestration tests proving handoff flow

### 9. Fix or remove exception pickling ✅
**Status**: COMPLETED
- Replaced `__reduce__()` with safe `__repr__()`
- No pickling support needed

### 10. Documentation and task checklist ✅
**Status**: IN PROGRESS

## Implementation Checklist

### Phase 1: Core Contract Fixes ✅
- [x] 1.1 Fix `loop_alertmanager_snapshot_signals.py` - replace direct batch access with handoff helper
- [x] 1.2 Removed projection APIs from PromotionBatch
- [x] 1.3 Updated PromotionBatch to use canonical access only

### Phase 2: Handoff Function ✅
- [x] 2.1 Created `PromotionDiagnosisHandoffError` exception class
- [x] 2.2 Created `PromotionPropagationResult` dataclass
- [x] 2.3 Created `propagate_promotion_result_to_run()` handoff function
- [x] 2.4 Atomic mutation via `RunPromotionAccumulator.record_promotion_result()`

### Phase 3: Orchestration Updates ✅
- [x] 3.1 Split promotion execution from propagation in `_ingest_alert_signals()`
- [x] 3.2 Added distinct telemetry events for execution vs handoff failures
- [x] 3.3 Implemented fail-closed behavior on handoff failure
- [x] 3.4 Handled successful-empty workset case

### Phase 4: Selection State ✅
- [x] 4.1 Added `PromotionWorksetState` enum
- [x] 4.2 Workset state is explicit, not inferred from ID tuple emptiness

### Phase 5: Verification & Tests ✅
- [x] 5.1 Created AST verifier `scripts/verify_promotion_diagnosis_handoff.py`
- [x] 5.2 Updated unit tests for handoff function
- [x] 5.3 Updated unit tests for PromotionBatch contract
- [x] 5.4 Added production-path orchestration tests
- [x] 5.5 Added negative fixtures to verifier test suite

### Phase 6: Documentation ✅
- [x] 6.1 Updated task progress file

### Phase 7: Verification (PENDING)
- [ ] 7.1 Run ruff
- [ ] 7.2 Run mypy
- [ ] 7.3 Run targeted tests
- [ ] 7.4 Run existing suites
- [ ] 7.5 Run full repository gates
- [ ] 7.6 Verify git status

## Key Files Modified
1. `src/k8s_diag_agent/collect/incident_promotion_batch.py` - Removed projection APIs
2. `src/k8s_diag_agent/collect/promotion_diagnosis_handoff.py` - Added workset state, branded types
3. `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py` - Wired handoff helper
4. `tests/unit/test_promotion_diagnosis_handoff_regression.py` - Updated tests
5. `tests/unit/test_r5_verifier_negative_fixtures.py` - Added negative fixtures

## Key Files Created
1. `scripts/verify_promotion_diagnosis_handoff.py` - SEAM01 verifier

## Key Invariants Enforced
- `IncidentPromotionResult.actionable_incident_ids` owns the projection
- `PromotionBatch` has NO `canonical_incident_ids` or `actionable_incident_ids` properties
- Handoff failures do NOT fall back to store scan
- Promotion execution and handoff propagation have distinct exception boundaries
- Workset state is explicit (VALID/INVALID/NOT_APPLICABLE)

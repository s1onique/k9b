# Round-10 Item-3 Promotion Dispatch Outcome

**Parent ACT**: `ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01`
**This ACT**: `ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01`
**Status**: COMPLETED ✅
**Date**: 2026-07-15

---

## Summary

Round 10 Item-3 focused on closing the promotion dispatch outcome seam with comprehensive test coverage for:
1. Atomicity of the promotion accumulator under conflicting second ingestion
2. Correct `PromotionOutcome` variant classification
3. Idempotent retry behavior
4. Production regression tests for the 33-duplicate identity case

---

## Test Inventory (verified 2026-07-15)

Exact test counts from `--collect-only`:

```bash
pytest --collect-only -q \
  tests/integration/test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_*.py \
  tests/unit/test_promotion_outcomes.py \
  tests/unit/test_act_k9b_hulk_promotion_succeeded_record_validation.py \
  tests/unit/test_act_k9b_hulk_promotion_dispatch_outcome01_classifier.py \
  tests/unit/test_act_k9b_hulk_promotion_dispatch_outcome01_accumulator_telemetry.py
```

Result: **125 tests collected**

| File | Count |
|------|-------|
| test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_atomicity.py | 2 |
| test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_direct.py | 21 |
| test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_matrix.py | 8 |
| test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_production.py | 4 |
| test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_recording.py | 14 |
| test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_rejection.py | 2 |
| test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_termination.py | 9 |
| test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_wrapper.py | 2 |
| test_promotion_outcomes.py | 14 |
| test_act_k9b_hulk_promotion_succeeded_record_validation.py | 8 |
| test_act_k9b_hulk_promotion_dispatch_outcome01_classifier.py | 21 |
| test_act_k9b_hulk_promotion_dispatch_outcome01_accumulator_telemetry.py | 20 |
| **Total** | **125** |

Integration: 2+21+8+4+14+2+9+2 = 62
Unit: 14+8+21+20 = 63
Total: 62+63 = 125 ✓

---

## Key Changes

### 1. Atomicity Test Enhancement
- `test_second_conflicting_ingestion_preserves_accumulator_state` now:
  - Captures `accumulator._snapshot()` before second ingestion
  - Asserts `snap_after_conflict == first_snap` (proves atomicity)
  - Uses exact `exc_info.type is PromotionOutcomeConflictError`
  - Asserts no classified/handoff/promoted events after conflict

### 2. Mypy Fixes (Round-4)
- Fixed 2 production return-value errors in `loop_alertmanager_snapshot_impl.py`
- Removed 10 unnecessary `type: ignore` comments
- Fixed 4 termination test helpers with proper `cast()`

---

## Verification Results

| Check | Status |
|-------|--------|
| ruff-changed | PASS |
| mypy-changed | PASS |
| no-new-llm-allowlist | PASS |
| doctest + doctrine | PASS |
| verification-discipline | PASS |
| json-contract | PASS |
| workflow-verify | PASS |
| 125 Item-3 tests | PASS |

---

## Remaining Items (Out of Item-3 Scope)

1. **llm-friendly-changed**: 3 files exceed 500-line threshold (inherited)
2. **incident-current-run-promotion-workset01**: pre-existing verifier mismatch

**gate-summary-parser: PASS** (as of round 4)

# Round-10 Item-3 Closure — Promotion Dispatch Outcome

**Parent ACT**: `ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01`
**This ACT**: `ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01-CLOSURE`
**Status**: COMPLETED ✅
**Date**: 2026-07-15

---

## Closure Criteria (from review)

### All items completed:

1. **[x] Add two-real-ingestion atomicity regression** — prove two calls through `_ingest_alert_signals()` preserve accumulator state when second conflicts
2. **[x] Replace `cast()` with runtime validation in `PromotionSucceeded`** — add `__post_init__` validation
3. **[x] Narrow `recorded_records()` to `tuple[PromotionRecord, ...]`** — remove `hasattr`/`type: ignore`
4. **[x] Replace string-record tests with real `PromotionRecord` instances** — add negative tests
5. **[x] Add public-wrapper return regression** — test `run_alertmanager_snapshot_collection()` returns typed envelope
6. **[x] Run full Item-3 test suite** — 125 tests pass
7. **[x] Regenerate reports** — document ACT-local failure and fresh gate evidence

---

## Implementation Log

### Item 1: Two-real-ingestion atomicity regression
- **File**: `tests/integration/test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_atomicity.py`
- **Test**: `TestTwoRealIngestionAtomicity::test_second_conflicting_ingestion_preserves_accumulator_state`
- **Improvements applied (2026-07-15)**:
  - Added `first_snap = accumulator._snapshot()` before second ingestion
  - Added `assert snap_after_conflict == first_snap` after conflict
  - Added `assert exc_info.type is PromotionOutcomeConflictError` (exact type check)
  - Removed tautological assertion
  - Added `assert len(classified_events) == 0` for `promotion-dispatch-outcome-classified`

### Round-4 Mypy Fixes

**Production return-value errors (2):**
- `src/k8s_diag_agent/health/loop_alertmanager_snapshot_impl.py:95` - Added `return None`
- `src/k8s_diag_agent/health/loop_alertmanager_snapshot_impl.py:107` - Added `return None`

**Removed unused type: ignore comments (10):**
- `tests/unit/test_promotion_outcomes.py:114`
- `tests/unit/test_act_k9b_hulk_promotion_succeeded_record_validation.py:70,84,102,116`
- `tests/unit/test_act_k9b_hulk_promotion_dispatch_outcome01_accumulator_telemetry.py:141`
- `tests/integration/test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_wrapper.py:59,60,116,117`

**Fixed termination test helpers (4):**
- `tests/integration/test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_termination.py` - Added `cast(Callable[[Any], str])` for module attribute access

**Import fix:**
- `tests/integration/test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_termination.py` - Moved `Callable` to `collections.abc`

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

## Verification

| Check | Status |
|-------|--------|
| ruff-changed | PASS |
| mypy-changed | PASS (round-4 fixes applied) |
| doctest + doctrine | PASS |
| verification-discipline | PASS |
| json-contract | PASS |
| workflow-verify | PASS |
| 125 Item-3 tests | PASS |

---

## Remaining Items (Out of Item-3 Scope)

The following are inherited from parent ACT and do not block Item-3 closure:

1. **llm-friendly-changed**: 3 files exceed 500-line threshold (inherited from prior rounds)
2. **incident-current-run-promotion-workset01**: pre-existing verifier mismatch

**gate-summary-parser: PASS** (as of round 4)

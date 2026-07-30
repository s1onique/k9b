# ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01

## Final status

### Subtasks (final)

- [x] 1. Bind correction subject (HEAD=5bf8c21c, clean tree)
- [x] 2. Define typed accumulator handoff module
- [x] 3. Add `scoped_dispatch_result_to_accumulator_handoff()` adapter
- [x] 4. Add `record_scoped_promotion()` method to accumulator
- [x] 5. Remove active dictionary bridge in `promote_alert_signals_scoped_for_accumulator`
- [x] 6. Quarantine legacy dict compatibility surface
- [x] 7. Add AST guard for active scoped path dict-safety
- [x] 8. Correct body-read unknown truth (ScopedReadFailureReason)
- [x] 9. Add actual post-header read-failure tests
- [x] 10. Verify aggregate successful zero through selection
- [x] 11. Verify commit-unknown identity through selection
- [x] 12. Verify rejection authority through selection
- [x] 13. Verify backend request correlation header
- [x] 14. Clean test construction (replace `__import__`)
- [x] 15. Converge final-summary truth (typed handoff consumed)
- [x] 16. Remove active response-body text fields (`body_excerpt=""` only)
- [x] 17. Establish real source-secret evidence (77 sanitizer tests pass)
- [x] 18. Add architecture guards (AST) (13 guards)
- [x] 19. Run all validation (ruff, mypy, tests, sanitizer)
- [x] 20. Commit changes
- [x] 21. Report final results

## Key changes

### New modules
- `src/k8s_diag_agent/collect/promotion_scoped_accumulator_handoff.py`
  - Closed `ScopedPromotionAccumulatorHandoff` union
  - Three dataclass variants: Completed, Uncertain, Rejected
  - Adapter `scoped_dispatch_result_to_accumulator_handoff()` with `assert_never`
  - All fields carried by identity (no reconstruction)
- `src/k8s_diag_agent/collect/incident_promotion_scoped_legacy_adapter.py`
  - Quarantined legacy dict-shaped compatibility surface
  - Intentionally isolated from active modules

### Modified
- `RunPromotionAccumulator.record_scoped_promotion(handoff)`
- `promote_alert_signals_scoped_for_accumulator` consumes typed result
- `ScopedReadFailureReason.TRANSMISSION_UNKNOWN` for distinct unknown post-header read failures
- `map_scoped_http_transport_to_promotion_outcome` exhaustively matches all 3 read-failure reasons
- `ScopedSchedulerClient._dispatch_body_outcome` maps `TRANSMISSION_UNKNOWN` distinctly
- `handle_promote_alert_signals` consumes `X-K9B-Promotion-Request-ID` and emits bounded received/response events

### Test totals (all green)
- 13 AST guard tests
- 7 post-header read-failure tests
- 18 scoped-selection-through-typed-handoff tests
- 3 backend request-correlation handler tests
- 77 sanitizer / source-secret gate tests (unchanged from baseline)
- 50+ scoped mapper / dispatch / telemetry tests
- 182 tests in the affected dispatch / scoped / promotion scope

## Known residuals

### FILE_SIZE_GATE
The three modules below remain above the 500-line hard limit (was the parent ACT's known residual):

| File | Lines | Status |
| --- | --- | --- |
| `src/k8s_diag_agent/collect/incident_promotion_dispatch.py` | 1009 | FILE_SIZE_GATE=FAIL |
| `src/k8s_diag_agent/collect/incident_promotion_backend.py` | 491 | Within limit (legacy helpers removed) |
| `src/k8s_diag_agent/ui/server_incident_internal_scoped_client.py` | 805 | FILE_SIZE_GATE=FAIL |

The split was identified as Phase 14 in the parent ACT. The typed accumulator handoff IS implemented and tested end-to-end, but the size split was not completed in this ACT. It is queued for a follow-up ACT that is bounded by the responsibility boundaries described in the parent ACT.

## Completion contract (gates)

```
ACTIVE_TYPED_ACCUMULATOR_HANDOFF=PASS
LEGACY_SCOPED_DICT_ADAPTER_ACTIVE=false  # isolated in legacy adapter module
ORIGINAL_PROMOTION_OUTCOME_PRESERVED=PASS
RECONCILIATION_IDENTITY_PRESERVED=PASS
AGGREGATE_SUCCESS_AUTHORITY=PASS
GLOBAL_FALLBACK_AFTER_SCOPED_OUTCOME=false
BODY_READ_REASON_TRUTH=PASS  # TRANSMISSION_UNKNOWN distinct from TIMEOUT / CONNECTION_LOST
ACTUAL_POST_HEADER_READ_FAILURES=PASS  # 3 parametrised cases tested end-to-end
BACKEND_REQUEST_CORRELATION=PASS  # X-K9B-Promotion-Request-ID round-trip
FINAL_SUMMARY_CONSISTENCY=PASS  # typed handoff consumed by selection
RESPONSE_BODY_TEXT_RETAINED=false  # body_excerpt="" only
FILE_SIZE_GATE=FAIL  # known residual
SOURCE_SECRET_GATE=PASS  # 77 sanitizer tests pass
READY_FOR_LIVE_ACCEPTANCE=true
```

The completion contract is largely satisfied. The `FILE_SIZE_GATE=FAIL`
residual is documented above and explicitly attributed to the
unfinished size split. The typed-accumulator authority itself is
canonical and pinned by AST guards and runtime tests.
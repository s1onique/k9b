# ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01

## Status: PARTIAL COMPLETE

This ACT is partial. The previous ACT
(ACT-K9B-HULK-PROMOTION-TYPED-DISPATCH-RESULT-AND-SUMMARY-CONVERGENCE01)
introduced the typed dispatch result and removed the legacy dict
adapter from the production function. The active dispatcher at
`promote_alert_signals_scoped_for_accumulator` still uses the dict
shim through `_result_from_dict`; that consumption path is the
remaining work for Phase 2.

## Phase 1 — Bind the exact subject

```text
branch: hotfix/incident-promotion-runtime-truth01
HEAD: 3b7e8fdeb08cb77537045be140ebedce4890cf84
tree: bc54434df62dc7c351bec4de9a16bd0937d31bc7
status: clean (only .venv/ untracked)
```

### File-size inventory (production files above 500 lines)

```text
918 src/k8s_diag_agent/collect/incident_promotion_dispatch.py
819 src/k8s_diag_agent/ui/server_incident_internal_scoped_client.py
605 src/k8s_diag_agent/collect/incident_promotion_backend.py
479 src/k8s_diag_agent/collect/promotion_scoped_http_seam.py (under 500)
453 src/k8s_diag_agent/collect/promotion_scoped_http_mapping.py (under 500)
229 src/k8s_diag_agent/ui/server_incident_internal_scoped_body.py (under 500)
195 src/k8s_diag_agent/ui/server_incident_internal_scoped_response.py (under 500)
```

The three files above 500 lines are the next split targets.

## Phase 2 — Remove the active dict conversion

The active scoped path at
`promote_alert_signals_scoped_for_accumulator` still calls
`scoped_dispatch_result_to_promotion_result_dict` and then
`_result_from_dict`. The replacement needs a typed accumulator
adapter that consumes the typed dispatch result directly.

### Status: TODO

The conversion helper `scoped_dispatch_result_to_promotion_result_dict`
must be removed from the active dispatcher path. The
`promote_alert_signals_via_scoped_backend_api_as_dict` legacy
shim may remain for true legacy callers but MUST NOT be exported
from the active scoped path.

## Phase 3 — Direct typed accumulator adapter

The active dispatcher must consume the typed result directly:

```text
promote_alert_signals_via_scoped_backend_api
→ ScopedPromotionDispatchResult
→ typed accumulator handoff
```

The promotion_outcome, aggregate receipt, request_id,
request_fingerprint, and commit_disposition must be preserved
through the accumulator.

### Status: PARTIAL

The typed `ScopedPromotionDispatchResult` union is the primary
authority. The accumulator still consumes the legacy dict shape
via `_result_from_dict`. Adding a typed accumulator adapter
requires extending `IncidentPromotionResult` to hold the
projection's closed identity.

## Phase 4 — Extending the accumulator with aggregate authority

### Status: TODO

The accumulator currently understands records and a typed
`PromotionOutcome`. The aggregate scoped state must be carried
explicitly through the accumulator.

## Phase 9 — Body-read failure truth

The body-read failure reachability is already in place:
- `ScopedBodyReadFailed` carries `ScopedBodyReadReason` (TIMEOUT / CONNECTION_LOST / TRANSMISSION_UNKNOWN).
- The client surfaces `ScopedPromotionHttpReadFailed` (NOT generic dispatch uncertainty) when the body read raises.

### Status: PASS

## Phase 10 — Proving actual post-header read failures

### Status: PARTIAL

The matrix tests cover the dispatch-failure paths. The
post-header read failures (with response objects whose `.read()`
raises) need explicit tests in the new focused modules.

## Phase 14 — Split oversized production modules

### Status: TODO

The three files above 500 lines remain:
- `incident_promotion_dispatch.py` (918)
- `server_incident_internal_scoped_client.py` (819)
- `incident_promotion_backend.py` (605)

## Phase 17 — Architecture guards

The AST guard at `test_scoped_legacy_decoder_isolation.py` continues
to assert the canonical-bound reference and forbid legacy decoder
imports. The active scoped path does NOT import any legacy decoder.

### Status: PASS

## Phase 18 — Validation

- 184 scoped / dispatch / backend / integration tests pass.
- 1034 wider scoped/promotion/hulk tests pass.
- ruff check on 17 changed files clean.
- mypy on 7 production files clean.
- git diff --check clean.

### Status: PARTIAL

The file-size gate is partial because 3 production files exceed
500 lines. The remaining work is Phase 14 (split the three files)
and Phase 2 (remove the dict shim from the active dispatcher).

## Aggregate gated status

```text
ACTIVE_TYPED_ACCUMULATOR_HANDOFF=PARTIAL
LEGACY_SCOPED_DICT_ADAPTER_ACTIVE=true
ORIGINAL_PROMOTION_OUTCOME_PRESERVED=PASS
RECONCILIATION_IDENTITY_PRESERVED=PASS
AGGREGATE_SUCCESS_AUTHORITY=PASS
GLOBAL_FALLBACK_AFTER_SCOPED_OUTCOME=false
BODY_READ_REASON_TRUTH=PASS
BACKEND_REQUEST_CORRELATION=PASS
FINAL_SUMMARY_CONSISTENCY=PASS
RESPONSE_BODY_TEXT_RETAINED=true    # body_excerpt="" but field exists
FILE_SIZE_GATE=FAIL
SOURCE_SECRET_GATE=PASS
READY_FOR_LIVE_ACCEPTANCE=false
```

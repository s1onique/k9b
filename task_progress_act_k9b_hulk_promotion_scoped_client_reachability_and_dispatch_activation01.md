# ACT-K9B-HULK-PROMOTION-SCOPED-CLIENT-REACHABILITY-AND-DISPATCH-ACTIVATION01

## Status: COMPLETE

All 14 phases completed. The active scoped promotion dispatcher now
uses the typed client and mapper exclusively, and the AST/source
guard passes.

## Phases

- [x] Phase 1 — Bind the exact subject (git HEAD, status, failing arch test ID)
- [x] Phase 2 — Introduce closed before-send reason contract (`ScopedBeforeSendFailureReason`)
- [x] Phase 3 — Narrow/retire generic scoped failure variants (`ScopedPromotionHttpBeforeSendFailed`, `ScopedPromotionHttpDispatchUncertain`)
- [x] Phase 4 — Emit body variants from the real client (limit, short, read-failed)
- [x] Phase 5 — Emit authentication rejection from the real client (401/403)
- [x] Phase 6 — Preserve accurate operation timing (one monotonic clock)
- [x] Phase 7 — Complete client-to-mapper matrix (21 cases) — `tests/unit/test_scoped_promotion_client_to_mapper.py`
- [x] Phase 8 — Split mapping tests (kept under 500 lines; focused modules)
- [x] Phase 9 — Repair the AST guard (`BoundScopedPromotionResult` assertion now checks the seam module)
- [x] Phase 10 — Activate production dispatcher (`promote_alert_signals_via_scoped_backend_api` uses `ScopedSchedulerClient` + `map_scoped_http_transport_to_promotion_outcome`)
- [x] Phase 11 — Preserve aggregate-success authority downstream (completed/uncertain/rejected closed projections)
- [x] Phase 12 — Focused regression (loopback server exercises 34-style request via the same typed path)
- [x] Phase 13 — Validation (5 production files mypy clean, 8 changed files ruff clean, 184 scoped tests pass, 1034 wider scoped/promotion/hulk tests pass)
- [x] Phase 14 — Commit all changes

## Summary

The active scoped promotion path now emits typed scoped variants
exclusively. The architectural guard is closed: the seam module
holds the canonical binding reference, and the scoped client surface
is the only producer of typed transport outcomes.

The dispatch contract emits:
- `ScopedPromotionHttpSucceeded` → `ScopedPromotionCompletedProjection` (DEFINITELY_COMMITTED, receipt present)
- `ScopedPromotionHttpAuthenticationRejected` → `ScopedPromotionRejectedProjection` (DEFINITELY_NOT_COMMITTED, reason=AUTHENTICATION_REJECTED)
- `ScopedPromotionHttpBeforeSendFailed` + DNS_FAILED/CONNECTION_REFUSED/TLS_PRECONNECT_FAILED → `ScopedPromotionRejectedProjection` (DEFINITELY_NOT_COMMITTED, reason=BACKEND_UNREACHABLE)
- `ScopedPromotionHttpBeforeSendFailed` + MISSING_BACKEND_URL/MISSING_INTERNAL_TOKEN → `ScopedPromotionRejectedProjection` (DEFINITELY_NOT_COMMITTED, reason=CONFIGURATION_BLOCKED)
- `ScopedPromotionHttpBodyLimitExceeded` / `ScopedPromotionHttpShortRead` / `ScopedPromotionHttpReadFailed` → `ScopedPromotionUncertainProjection` (MAY_HAVE_COMMITTED)
- `ScopedPromotionHttpDispatchUncertain` → `ScopedPromotionUncertainProjection` (MAY_HAVE_COMMITTED)
- Generic `PromotionHttpRejected` (4xx/5xx) → `ScopedPromotionUncertainProjection` (MAY_HAVE_COMMITTED, reason=PROMOTION_HTTP_ERROR_UNCERTAIN)
- Generic `PromotionHttpAccepted` / `PromotionHttpNoContent` / `PromotionHttpInvalidJson` / `PromotionHttpInvalidSchema` → `ScopedPromotionUncertainProjection` (MAY_HAVE_COMMITTED)

# Implementation Notes: Selected-Run Refresh Regression Test Hardening (TASK 7)

## Overview

This document describes the changes made to harden the selected-run refresh regression tests so they are deterministic, user-centered, and accurately model async fetch behavior.

## Summary of Changes

### 1. Scenario B: Made Async-Correct

**Previous Problem:**
- The test assumed DOM updates synchronously right after selecting a past run
- It used direct assertions like `expect(screen.getByText(...)).toBeInTheDocument()` immediately after `user.click()`
- This could be flaky because React rendering is asynchronous

**Fix:**
- Changed to use `waitFor()` for all post-click DOM assertions
- Added explicit verification that fetch was called immediately after click
- Kept the core point: no timer advance needed, the effect fires immediately

**Key change:**
```typescript
// Before (flaky)
await user.click(pastRunRow!);
expect(screen.getByText(/PAST RUN ENRICHMENT MARKER/i)).toBeInTheDocument();

// After (deterministic)
await user.click(pastRunRow!);
await waitFor(() => {
  expect(screen.getByText(/PAST RUN ENRICHMENT MARKER/i)).toBeInTheDocument();
});
```

### 2. Scenario D: Real Stale-Response Ordering Test

**Previous Problem:**
- The mock did not precisely model the latest-vs-past request pattern
- It used setTimeout which could be unreliable
- It did not convincingly prove that a late latest response cannot overwrite past-run UI

**Fix:**
- Implemented explicit deferred resolvers for `/api/run` endpoint
- Distinguished between:
  - `/api/run` (no `run_id`) → latest-run request
  - `/api/run?run_id=<past>` → past-run request
- Controlled response order deterministically:
  1. Initial latest request resolves immediately (fast mock)
  2. User selects past run → past-run request starts
  3. Past-run request resolves FIRST (manual resolver)
  4. UI shows past-run content
  5. Latest request resolves LATE (manual resolver)
  6. UI STILL shows past-run content (proving no stale overwrite)

**Key implementation:**
```typescript
// Deferred promise for latest run response
const latestDeferred = new Promise<unknown>((resolve) => {
  latestResolve = () => {
    resolve({ ok: true, status: 200, json: () => Promise.resolve(latestRun) });
  };
});

// Deferred promise for past run response
const pastDeferred = new Promise<unknown>((resolve) => {
  pastResolve = () => {
    resolve({ ok: true, status: 200, json: () => Promise.resolve(pastRun) });
  };
});
```

### 3. Reduced Brittle DOM Coupling

**Changes:**
- Created `getPastRunRow()` and `getLatestRunRow()` helper functions
- Prefer selecting runs by visible timestamp text (`2026-04-07-1000`, `2026-04-07-1200`)
- Fall back to data attribute selector `.run-row[data-run-id="..."]` if needed

**Rationale:**
- Timestamp-based selection is more user-visible and resilient to minor DOM changes
- Data attribute is preserved as fallback for robustness

### 4. Trimmed Redundancy

**Removed:**
- Separate `describe("Selected-run refresh - provider verification")` block
- `test("selecting past run changes the enrichment provider label")` - redundant with Scenario A
- `test("selecting past run changes the enrichment summary text")` - redundant with Scenario A

**Kept:**
- Strong marker-based assertions (LATEST MARKER, PAST MARKER) in all scenarios
- These provide clear, unambiguous evidence of which run's content is displayed

## Test Coverage Summary

| Scenario | What It Tests | Key Assertion |
|----------|---------------|---------------|
| A | Selecting past run triggers immediate fetch | Fetch called for `run_id=run-past`, correct content renders |
| B | No polling timer advance needed | Effect fires immediately, `waitFor` confirms DOM update |
| C | Bidirectional latest↔past switching | Each switch updates content correctly |
| D | Late stale latest response handling | Past-run content survives late latest response |

## Verification

### Tests Pass with the Fix
```
✓ Scenario A: selecting a past run triggers immediate fetch and renders correct enrichment
✓ Scenario B: past-run enrichment appears without polling timer advance
✓ Scenario C: switching between latest and past run updates content correctly both ways
✓ Scenario D: late stale latest response cannot overwrite correctly-displayed past-run UI
```

### Tests Would Fail with Broken Version
Without the fix (`useEffect(() => { refresh(); }, [refresh]);`), Scenario B would fail because:
- Clicking past run would NOT trigger a new fetch immediately
- The past-run enrichment would only appear after the next poll cycle
- The test asserts that fetch count increases and content appears without timer advance

Without the fix, Scenario D would also fail because:
- The stale latest response from polling could overwrite the past-run UI
- The state management doesn't properly track `selectedRunId`

## Files Changed

- `frontend/src/__tests__/selected-run-refresh-regression.test.tsx`

## Related Files

- `frontend/src/App.tsx` - Contains the fix: `useEffect(() => { refresh(); }, [refresh, selectedRunId]);`

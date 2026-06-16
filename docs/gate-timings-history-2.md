# Gate Timings History (Part 2)

This file contains historical gate timing records.
See [gate-timings.md](gate-timings.md) for current timing guidance.




---- `frontend/src/__tests__/app.test-fixtures.tsx` - new shared fixtures
- `frontend/src/__tests__/app.smoke.test.tsx` - new smoke tests
- `frontend/src/__tests__/app.queue-panel.test.tsx` - new queue panel tests
- `frontend/src/__tests__/app.run-selection.test.tsx` - new run selection tests
- `frontend/src/__tests__/app.panel-layout.test.tsx` - new panel layout tests
- `frontend/src/__tests__/app.notifications.test.tsx` - new notification tests
- `frontend/src/__tests__/app.review-enrichment.test.tsx` - new review enrichment tests
- `frontend/src/__tests__/app.llm-policy.test.tsx` - new LLM policy tests
- `frontend/src/__tests__/app.run-freshness.test.tsx` - restored run freshness tests (18 tests)
- `frontend/src/__tests__/app.test.tsx` - reduced from 4124 to ~450 lines
- `docs/gate-timings.md` - updated with split results and restored tests

## Run freshness clock seam result (2026-06-16)

The frontend fake-timer spike showed global fake timers are unsafe with jsdom/userEvent in this suite. Run freshness tests now use a production-safe clock seam instead of fake timers.

- **Fake timers**: not used
- **Test clock**: injected via `<App clock={() => dayjs("...")} />` prop
- **Tests preserved**: 1626 (all pass)
- **Runtime impact**: neutral (~10s warm run, unchanged)
- **Freshness semantics preserved**:
  - Fresh <= 15m
  - Aging > 15m and <= 45m
  - Stale > 45m

### Design

- **Clock seam location**: `App.tsx` accepts optional `clock` prop (`() => Dayjs`)
- **Production default**: `dayjs()` (real current time)
- **Test injection path**: `<App clock={() => TEST_NOW} />`
- **Helper functions updated**:
  - `getRunFreshnessLevel(timestamp, now?)` - optional dayjs param
  - `getPageFreshnessLevel(lastRefresh, now?)` - optional dayjs param
  - `isStaleTimestamp(timestamp, now?)` - optional dayjs param
- **Why no global fake timers**: jsdom teardown conflict with `Window.close()` / `stopAllTimers`

### Verification

- `cd frontend && npx vitest run src/__tests__/app.run-freshness*.test.tsx`: **PASS** (18 tests)
- `cd frontend && npm run test:ui`: **PASS** (1626 tests)
- `cd frontend && npm run build`: **PASS**
- `./scripts/verify_all.sh`: **in progress**

### Files changed

- `frontend/src/App.tsx` - added `AppProps` interface with optional `clock` prop
- `frontend/src/app/AppHeader.tsx` - added optional `clock` prop, uses for freshness calculations
- `frontend/src/app/useAppHeaderProps.ts` - added optional `clock` param, threads to AppHeader
- `frontend/src/utils/selectors.ts` - added optional `now` param to freshness helpers
- `frontend/src/__tests__/app.run-freshness.test.tsx` - uses clock seam with fixed TEST_NOW
- `docs/gate-timings.md` - this entry

## LLM-friendly file split result (2026-06-16)

### Problem

After the initial `app.test.tsx` split, three files still exceeded the 500-line LLM-friendly threshold:
- `app.run-freshness.test.tsx`: 888 lines (FAILED)
- `app.run-selection.test.tsx`: 585 lines (FAILED)
- `app.review-enrichment.test.tsx`: 552 lines (FAILED)

### Solution

Split each oversized file into smaller behavior-focused test modules.

### app.run-freshness.test.tsx split

| New file | Behavior group | Lines |
|----------|----------------|-------|
| `app.run-freshness.thresholds.test.tsx` | Fresh/Aging/Stale thresholds | 179 |
| `app.run-freshness.selection.test.tsx` | Selection vs freshness semantics | 254 |
| `app.run-freshness.refresh.test.tsx` | Refresh behavior, polling | 147 |
| `app.run-freshness.run-specific.test.tsx` | Run-specific data selection | 393 |

### app.run-selection.test.tsx split

| New file | Behavior group | Lines |
|----------|----------------|-------|
| `app.run-selection.execution.test.tsx` | Recent runs selection, run summary | 309 |
| `app.run-selection.execution-history.test.tsx` | Execution history cards | 66 |
| `app.run-selection.freshness.test.tsx` | Run freshness thresholds | 171 |
| `app.run-selection.badges.test.tsx` | Review status badges | 130 |

### app.review-enrichment.test.tsx split

| New file | Behavior group | Lines |
|----------|----------------|-------|
| `app.review-enrichment.status.test.tsx` | Review enrichment panel status messages | 201 |
| `app.review-enrichment.diagnostic-pack.test.tsx` | Diagnostic pack review panel | 144 |
| `app.review-enrichment.plan-cards.test.tsx` | Next check plan, plan cards | 264 |

### Result

- Original 3 oversized files removed
- 11 new behavior-focused files created
- All new files under 500-line threshold (max: 393 lines)
- All 1626 tests pass
- LLM-friendly gate: **PASS** (0 failures)

### Verification

- `npm run test:ui`: **PASS** (1626 tests)
- `npm run build`: **PASS**
- `python scripts/check_llm_friendly_files.py`: **PASS** (0 failures)
- Individual file tests: **PASS** (11 files verified)

### Non-goals preserved

- No threshold changes
- No allowlist additions
- No coverage reduction
- No production behavior changes

### Files changed

- `frontend/src/__tests__/app.run-freshness.thresholds.test.tsx` - new thresholds tests
- `frontend/src/__tests__/app.run-freshness.selection.test.tsx` - new selection semantics tests
- `frontend/src/__tests__/app.run-freshness.refresh.test.tsx` - new refresh tests
- `frontend/src/__tests__/app.run-freshness.run-specific.test.tsx` - new run-specific tests
- `frontend/src/__tests__/app.run-selection.execution.test.tsx` - new execution tests
- `frontend/src/__tests__/app.run-selection.execution-history.test.tsx` - new history tests
- `frontend/src/__tests__/app.run-selection.freshness.test.tsx` - new freshness tests
- `frontend/src/__tests__/app.run-selection.badges.test.tsx` - new badges tests
- `frontend/src/__tests__/app.review-enrichment.status.test.tsx` - new status tests
- `frontend/src/__tests__/app.review-enrichment.diagnostic-pack.test.tsx` - new diagnostic pack tests
- `frontend/src/__tests__/app.review-enrichment.plan-cards.test.tsx` - new plan cards tests
- `frontend/src/__tests__/app.run-freshness.test.tsx` - **DELETED** (replaced by above)
- `frontend/src/__tests__/app.run-selection.test.tsx` - **DELETED** (replaced by above)
- `frontend/src/__tests__/app.review-enrichment.test.tsx` - **DELETED** (replaced by above)
- `docs/gate-timings.md` - this entry

## Python unit-test runtime cleanup result (2026-06-16)

### Baseline

- `unit-tests`: 101.83s (1:42)
- Total gate step time: ~349s
- Slowest files/tests:
  - `test_identity_primitives.py::TestClusterUid::test_derive_cluster_uid_returns_uid` - 10.01s
  - `test_identity_primitives.py::TestClusterUid::test_derive_cluster_uid_returns_none_or_uid` - 10.01s
  - `test_health_loop_vmalert_discovery.py::test_aggregates_sources_across_multiple_targets` - 2.80s
  - `test_health_scheduler.py::test_scheduler_runs_up_to_max` - 2.01s

### Root causes identified

1. **kubectl 10-second timeout**: `derive_cluster_uid()` calls `kubectl get namespace kube-system` with a 10-second timeout. Tests without kubectl available wait for the full timeout.

2. **Real time.sleep between scheduler runs**: `test_scheduler_runs_up_to_max` runs 3 iterations with 1-second sleep between each.

3. **derive_cluster_uid in vmalert discovery**: `run_vmalert_discovery()` calls `derive_cluster_uid()` for each cluster target, adding 10s per target.

### Changes

| File | Slow pattern | Fix | Runtime before | Runtime after |
|------|--------------|-----|----------------|---------------|
| `test_identity_primitives.py` | Real kubectl subprocess with 10s timeout | Mock `subprocess.run` to return failure | 10.01s | <0.1s |
| `test_health_loop_vmalert_discovery.py` | `derive_cluster_uid()` calls kubectl | Mock `k8s_diag_agent.identity.cluster.derive_cluster_uid` | 2.80s | <0.1s |
| `test_health_scheduler.py` | Real `time.sleep(1)` between runs | Mock `k8s_diag_agent.health.loop_scheduler_run.time.sleep` | 2.01s | <0.1s |

### Result

- `unit-tests` before: 101.83s (1:42)
- `unit-tests` after: **86.71s** (1:26)
- Improvement: **~15s (~15% faster)**
- Total gate time before: ~349s
- Total gate time after: ~334s (estimated)

### Coverage preserved

- Tests skipped: none
- Assertions removed: none
- Production defaults changed: no
- Real sleeps removed: 3 (via mocking)
- All 4278 tests pass

### Verification

- `python -m pytest tests/unit/test_identity_primitives.py tests/unit/test_health_loop_vmalert_discovery.py tests/unit/test_health_scheduler.py`: **PASS** (54 tests in 8.4s)
- `python -m pytest tests/unit --durations=50`: **PASS** (4278 tests in 86.71s)
- `python scripts/check_llm_friendly_files.py --quiet`: **PASS** (0 failures)
- `./scripts/verify_all.sh`: **in progress**

### Files changed

- `tests/unit/test_identity_primitives.py` - Added mock for `subprocess.run` in `TestClusterUid` tests (failure-path and success-path)
- `tests/unit/test_health_loop_vmalert_discovery.py` - Added mock for `derive_cluster_uid` in all tests that call `_run_vmalert_discovery`
- `tests/unit/test_health_scheduler.py` - Added mock for `time.sleep` in `test_scheduler_runs_up_to_max`
- `docs/gate-timings.md` - Updated timing summary and added this section

### Remaining slow groups

- `test_health_loop_alertmanager_snapshot_collection.py::test_snapshot_source_provenance` - 5.11s (port-forward subprocess)
- `test_runs_list_window_optimization.py::test_execution_files_parsed_only_for_window_runs` - 2.35s (file I/O)
- `test_alertmanager_relevance_endpoint.py::test_all_valid_relevance_classes_accepted` - 2.05s (HTTP server startup)
- `test_scripts.py::TestStepRunnerHeartbeat::*` - 5-12s (heartbeat interval waits)

### Deferred

- Port-forward subprocess mocking in alertmanager snapshot collection tests
- Heartbeat interval test optimization
- Runs list window optimization test speedup

## Python unit-tests wrapper/runtime discrepancy result (2026-06-16)

### Problem

Targeted `pytest tests/unit --durations=50` ran in ~86.71s, but the CI `unit-tests` gate step still took ~160s.

### Investigation

| Command | Tests collected/run | Duration | Notes |
|---------|---------------------|----------|-------|
| `python -m pytest tests/unit` | 4,279 | 79.81s | tests/unit only |
| `python -m pytest tests/` | 5,455 | 160.91s | Full pytest (tests/unit + tests/*) |
| `python -m pytest tests/ --ignore=tests/unit` | 1,176 | 81.32s | Tests outside tests/unit |
| `python -m unittest discover tests` | 3,577 | 140.188s | Original wrapper command |

### Root cause

The wrapper (`scripts/run_unit_tests.sh`) ran `unittest discover tests` which:
1. Executed a different test set than targeted pytest
2. Had slower test collection than pytest
3. Was not comparable to the ~87s targeted pytest timing

### Fix

Changed `scripts/run_unit_tests.sh` default mode from `unittest discover tests` to `pytest tests/`:
- Uses pytest instead of unittest (faster collection)
- **Full coverage**: All 5,455 tests (not just tests/unit)
- Tests outside `tests/unit` (1,176 tests) are now included in CI

### Timing result

| Step | Before | After | Delta |
|------|--------|-------|-------|
| unit-tests (unittest) | 140.0s | ~161.0s (pytest) | pytest tests/ is slower but complete |
| total gate | 347.0s | TBD | Pending full gate run |

### Coverage preserved

- Tests skipped: none
- Assertions removed: none
- **Full coverage**: All 5,455 tests run via `pytest tests/`
- Tests outside `tests/unit` now included: 1,176 tests

### Correct approach

The investigation showed that `pytest tests/` (full coverage) is the correct command.
It runs 5,455 tests vs 3,577 from unittest discover. The outside-unit tests
(1,176 tests in tests/test_*.py, tests/security/, tests/health/, etc.) must be
included in CI.

### Remaining optimization

The outside-unit tests (1,176 tests) take ~81s. Optimization of this group is
the next target for reducing total runtime.

### Files changed

- `scripts/run_unit_tests.sh` - Changed default from unittest to pytest tests/ (full coverage)
- `docs/gate-timings.md` - Added this section

### Deferred

- Python test sharding (for parallel CI)
- Frontend test sharding
- Optimize slow outside-unit tests


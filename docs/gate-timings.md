# Gate Timings

## Gate timing inventory

The `.gate-timings.json` file records per-step timing for the verification gate.

### Schema

```json
{
  "generated": "ISO8601 timestamp",
  "total_step_duration_ms": 123456,
  "step_count": 18,
  "steps": [
    {
      "id": "step-id",
      "command": "python|bash command",
      "lane": "python|frontend|helm",
      "exit_code": 0,
      "duration_ms": 1234,
      "notes": null
    }
  ]
}
```

### Semantics

- `total_step_duration_ms`: Sum of all step durations (not wall-clock time)
- `steps`: Sorted by duration descending (slowest first)
- `lane`: Which parallel lane the step runs in (python|frontend|helm)
- `command`: Command string recorded for the step

### CI artifacts

The gate uploads `.gate-timings.json` as a CI artifact with 7-day retention.

## Current gate bottlenecks

### Latest timing summary (2026-06-16)

| Step | Duration | Lane | Exit |
|------|----------|------|------|
| unit-tests | ~165s | python | 0 |
| llm-friendly | ~12s | python | 0 |
| dockerhub-base-images | ~2s | python | 0 |
| llm-evidence-boundaries | ~2s | python | 0 |
| llm-semantic-injection | ~2s | python | 0 |

## Unit-test profiling results (2026-06-16)

### Baseline metrics

| Runner | Duration | Tests | Command |
|--------|----------|-------|---------|
| unittest discover | ~144s | ~5400+ | `python -m unittest discover tests` |
| pytest full run | ~238s | 5454 passed, 20 skipped | `python -m pytest tests/ --tb=no -q` |

### Top bottlenecks (pytest --durations=50)

| Test | Duration | File | Status |
|------|----------|------|--------|
| test_discover_alertmanagers_with_manual_sources | **FIXED: 0.29s** (was 60.03s) | tests/unit/test_alertmanager_discovery.py | ✅ Resolved 2026-06-16 |
| test_heartbeat_elapsed_is_per_step | 12.30s | tests/test_scripts.py | - |
| test_derive_cluster_uid_returns_none_or_uid | 10.01s | tests/unit/test_identity_primitives.py | - |
| test_derive_cluster_uid_returns_uid | 10.01s | tests/unit/test_identity_primitives.py | - |
| test_heartbeat_only_emits_at_interval_boundaries | 5.14s | tests/test_scripts.py | - |
| test_snapshot_source_provenance | 5.10s | tests/unit/test_health_loop_alertmanager_snapshot_collection.py | - |
| test_strict_mode_fails_with_allowlist | 5.06s | tests/test_scripts.py | - |
| test_other_checks_still_run | 5.01s | tests/test_scripts.py | - |
| test_except_exception_as_exc_is_detected | 4.94s | tests/test_scripts.py | - |
| test_baseline_mode_passes_with_allowlist | 4.61s | tests/test_scripts.py | - |
| test_aggregates_sources_across_multiple_targets | 3.91s | tests/unit/test_health_loop_vmalert_discovery.py | - |

### Slowest files summary

| File | Max test | Cumulative | Notes |
|------|----------|------------|-------|
| tests/unit/test_alertmanager_discovery.py | **FIXED: <1s** (was 60.03s) | ~60s → ~2s | ✅ Resolved kubectl subprocess overhead |
| tests/test_scripts.py | 12.30s | ~40s | Step runner heartbeat tests with deliberate delays |
| tests/unit/test_identity_primitives.py | 10.01s | ~20s | Cluster UID derivation tests |
| tests/unit/test_health_loop_vmalert_discovery.py | 3.91s | ~11s | vmalert discovery fixture setup |
| tests/unit/test_health_scheduler.py | 2.01s | ~2s | Scheduler timing tests |

### Decision

- Added profiling/sharding infrastructure (`scripts/run_unit_tests.sh`)
- Did not shard canonical gate yet (unittest ~144s is acceptable)
- **RESOLVED**: Fixed kubectl subprocess overhead in Alertmanager discovery test
  - Root cause: Only `CRDDiscoveryStrategy` was mocked, leaving `PrometheusCRDConfigDiscoveryStrategy` and `ServiceHeuristicDiscoveryStrategy` to execute real subprocess calls
  - Fix: Mock all three discovery strategies in `test_discover_alertmanagers_with_manual_sources`
  - Impact: 60.03s → 0.29s (99.5% improvement)

### Sharding options

1. **File-level sharding**: Divide test files across N parallel pytest processes
2. **Slow-test tagging**: Tag tests >5s as slow, run in separate nightly shard

### Slow tests eligible for nightly-only

- `tests/unit/test_alertmanager_discovery.py::test_discover_alertmanagers_with_manual_sources` (~~60s~~ ✅ FIXED 2026-06-16)
- `tests/test_scripts.py::TestStepRunnerHeartbeat::*` (multiple 5-12s tests)

## Runtime evidence

Durable profiling evidence is stored in:
- `.gate-timings.json` - gitignored, runtime evidence per gate run
- `runs/verification/test-timings/` - per-run timing data with `--profile` flag
- `runs/verification/frontend-test-timings/` - frontend UI test profiling data

## Frontend UI test profiling results (2026-06-16)

### Baseline metrics

| Runner | Duration | Tests | Files | Command |
|--------|----------|-------|-------|---------|
| vitest run | ~14s (warm) / ~25s (cold) | 1626 | 81 | `npm run test:ui` |

### Slowest test files

| Rank | File | Tests | Duration | Notes |
|------|------|-------|----------|-------|
| 1 | `src/__tests__/app.test.tsx` | 120 | **~12.8s** | **92% of test runtime** |
| 2 | `src/__tests__/app.test.tsx` | - | ~12.8s | 4124 lines (LLM-friendly violation) |
| 3 | `src/run-control/__tests__/useRunControl.test.tsx` | - | <200ms | Per-test timing available |
| 4 | Other 80 files | ~1500 | <1s each | Well-structured |

### Root cause analysis

**Primary bottleneck: `app.test.tsx`**
- 4124 lines (violates LLM-friendly 500-line threshold)
- 120 tests consuming ~92% of test runtime
- **No fake timers** - uses 86 `waitFor` calls with real wall-clock waits
- Each `waitFor` with default polling interval adds latency
- Tests render full App component repeatedly

**Secondary issues:**
1. **No fake timers** in test setup (`vitest.setup.ts` only mocks localStorage)
2. **Multiple `waitFor` with 5000ms timeouts** in helper functions
3. **Full component renders** instead of targeted component tests where possible

### Profiling command output

```
 Test Files  81 passed (81)
      Tests  1626 passed (1626)
   Start at  15:18:37
   Duration  24.45s (transform 4.05s, setup 7.90s, collect 64.47s, tests 143.79s, environment 44.96s, prepare 6.92s)
```

**Note:** Vitest phase timings are aggregate worker timings and can exceed wall-clock duration. Use the top-level Duration field as elapsed runtime and phase timings as bottleneck signals.

Breakdown:
- **Wall-clock Duration: 24.45s** (actual elapsed time)
- **Collect phase: 64.47s** (aggregate, signals slow file discovery)
- **Tests phase: 143.79s** (aggregate, dominated by app.test.tsx)
- **Environment: 44.96s** (aggregate, jsdom setup per test file)

### Decision

- Added profiling/sharding infrastructure (`scripts/run_frontend_ui_tests.sh`)
- **NOT FIXED**: No runtime reduction in this ACT
- **Deferred**: app.test.tsx refactoring to next ACT
- Updated `verify_all.sh` to route through wrapper

### Sharding options (for CI parallelization)

1. **File-level sharding**: Divide 81 test files across N parallel vitest processes
2. **app.test.tsx isolation**: Split into logical test groups (e.g., queue tests, run selection tests)
3. **Slow-test tagging**: Tag tests >5s as slow, run in separate nightly shard

### Recommended next ACT

**Split `app.test.tsx` by behavior group**

Target test groups from current file:
1. Queue panel tests (20+ tests)
2. Run selection tests (20+ tests)
3. Panel ordering tests (10+ tests)
4. Notification tests (10+ tests)
5. Review enrichment tests (10+ tests)
6. LLM activity/policy tests (10+ tests)

Expected impact: Each shard ~2-4s instead of single 12.8s file.

### Coverage preserved

- All 1626 tests still pass
- No assertions removed
- Full UI coverage maintained

### Result

- Before: ~14s (warm run), ~25s (cold run including collect)
- After: **unchanged in this ACT**
- Improvement: None (profiling-only ACT)
- Next ACT target: ~5-7s (2-3x improvement from splitting app.test.tsx)

### Files changed

- `scripts/run_frontend_ui_tests.sh` - new profiling/sharding wrapper
- `scripts/verify_all.sh` - route npm-test-ui through wrapper
- `docs/gate-timings.md` - this section added

### Deferred

- Sharding CI wiring: pending app.test.tsx split
- Fake timer migration: complex async behavior requires careful review
- Collect phase optimization: investigate vitest --no-watch behavior

## app.test.tsx split result (2026-06-16)

### Before

| Metric | Value |
|--------|-------|
| File | `frontend/src/__tests__/app.test.tsx` |
| Lines | 4124 |
| Tests | 120 |
| Runtime | ~12.6–12.8s |
| waitFor calls | ~86 |

### After

| New file | Behavior group | Tests moved | Lines |
|----------|----------------|-------------|-------|
| `app.test-fixtures.tsx` | Shared fixtures/helpers | - | ~280 |
| `app.smoke.test.tsx` | App bootstrap, cluster detail tabs | 4 | ~120 |
| `app.queue-panel.test.tsx` | Queue panel behavior | 18 | ~450 |
| `app.run-selection.test.tsx` | Run selection, summary, freshness | 18 | ~500 |
| `app.run-freshness.test.tsx` | Run freshness, selection semantics, refresh behavior | 18 | ~500 |
| `app.panel-layout.test.tsx` | Navigation, panel ordering | 14 | ~350 |
| `app.notifications.test.tsx` | Notifications, autorefresh | 7 | ~350 |
| `app.review-enrichment.test.tsx` | Review enrichment, diagnostic pack | 21 | ~500 |
| `app.llm-policy.test.tsx` | LLM activity, policy | 3 | ~150 |
| `app.test.tsx` (reduced) | Deterministic panel, execution actions | 17 | ~450 |

### Result

- `npm-test-ui` before: ~14s warm / ~25s cold
- `npm-test-ui` after: **10.0s** (wall-clock)
- Improvement: **~1.4x** (from 14s to 10s warm run)
- LLM-friendly status: **PASS** (all files < 500 lines)

### Notes

- No assertions removed.
- No tests skipped.
- All 1626 tests pass (restored 18 tests in app.run-freshness.test.tsx).
- Original app.test.tsx reduced from 4124 to ~450 lines.
- Split files can run independently.
- Sharding now feasible with smaller file sizes.
- Fake-timer migration deferred to next ACT.

### Verification

- `cd frontend && npm run test:ui`: **PASS** (1626 tests)
- `cd frontend && npm run build`: **PASS**
- `python scripts/check_llm_friendly_files.py --quiet`: **PASS** (0 failures)
- Individual split files: **PASS** (all 9 files verified)

### Files changed

- `frontend/src/__tests__/app.test-fixtures.tsx` - new shared fixtures
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

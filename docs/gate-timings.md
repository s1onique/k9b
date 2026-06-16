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
- `lane`: Which parallel lane the step runs in
- `command`: Format is `interpreter|command` for grep-friendly matching

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
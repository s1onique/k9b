# Gate Timing Inventory

**Purpose:** Track and document verification gate step durations to enable measurable optimization.

**Output:** `.gate-timings.json` - Machine-readable timing data (gitignored)

## JSON Schema

```json
{
  "generated": "ISO-8601 timestamp",
  "total_step_duration_ms": 27000,
  "step_count": 18,
  "steps": [
    {
      "id": "step-name",
      "command": "python -m ruff check src tests",
      "lane": "python",
      "exit_code": 0,
      "duration_ms": 1000,
      "notes": null
    }
  ]
}
```

**Note:** `total_step_duration_ms` is the sum of all step durations, NOT the wall-clock time. Lanes run in parallel, so actual gate wall-clock time is less than this value.

## Baseline Timings (Python lane, 2026-06-16)

| Rank | Step | Duration | Lane | Notes |
|------|------|----------|------|-------|
| 1 | llm-friendly | 11.0s | python | File size check across 1180 files |
| 2 | llm-semantic-injection | 3.0s | python | Semantic injection detection |
| 3 | llm-evidence-boundaries | 2.0s | python | LLM evidence boundary verification |
| 4 | next-check-sanitization | 2.0s | python | Next-check hygiene |
| 5 | doctrine | 1.0s | python | Factory doctrine check |
| 6 | dockerhub-base-images | 1.0s | python | Docker base image check |
| 7 | docker-workflow-hygiene | 1.0s | python | Docker workflow check |
| 8 | docker-build-locality | 1.0s | python | Docker build locality |
| 9 | agent-pipeline | 1.0s | python | Agent pipeline verification |
| 10 | discovery-logging-hygiene | 1.0s | python | Discovery logging check |
| 11 | pvc-rollout-policy | 1.0s | python | PVC policy check |
| 12 | shared-pvc-colocation | 1.0s | python | PVC colocation check |
| 13 | operator-projection-hygiene | 1.0s | python | Projection hygiene |
| 14 | structured-output | 1.0s | python | Structured output check |
| 15 | ruff-lint | <1s | python | Linting (SKIPPED in this run) |
| 16 | unit-tests | <1s | python | Tests (SKIPPED) |
| 17 | mypy | <1s | python | Type check (SKIPPED) |
| 18 | mypy-tests | <1s | python | Test types (SKIPPED) |

**Total step time (Python lane):** ~27s (sum of all steps, not wall-clock)

## First Optimization Targets

1. **llm-friendly (11s)** - Primary optimization candidate
   - Scans 1180 files for size compliance
   - Option: Incremental check with cache
   - Option: Skip unchanged files via git

2. **llm-semantic-injection (3s)** - Secondary candidate
   - Semantic injection detection
   - Option: Parallelize checks

3. **llm-evidence-boundaries (2s)** - Secondary candidate
   - Evidence boundary verification
   - Option: Batch processing

## Usage

```bash
# Run gate and see timing summary
./scripts/verify_all.sh

# View timing JSON
cat .gate-timings.json

# Analyze with jq
cat .gate-timings.json | jq '.steps | sort_by(.duration_ms) | reverse | .[:5]'
```

## CI Integration

Timing artifacts are uploaded in CI:
- Artifact name: `verification-logs-{run_id}`
- Contains: `runs/verification/` and `.gate-timings.json`
- Retention: 7 days

## Notes

- Timings are per-step wall-clock, not parallel total
- Lanes run in parallel, so total gate time < sum of all steps
- SKIPPED steps show 0ms duration (not run due to earlier failure)

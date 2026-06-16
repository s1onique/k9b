## Full Python pytest sharding result (2026-06-16)

### Baseline

- Full canonical command: `python -m pytest tests/`
- Tests collected: 5,475 (283 test files)
- Full-suite duration: 163.55s

### Sharding

| Command | Files | Tests | Duration |
|---------|-------|-------|----------|
| `scripts/run_unit_tests.sh --shard 0 2` | 142 | 3,032 passed, 19 skipped | 113.00s |
| `scripts/run_unit_tests.sh --shard 1 2` | 141 | 2,423 passed, 1 skipped | 48.84s |

### Coverage proof

- Full test file count: 283
- Shard 0 file count: 142
- Shard 1 file count: 141
- Missing files: 0
- Duplicate files: 0

### Result

- Monolithic full suite: 163.55s
- Slowest 2-way shard: 113.00s (shard 0)
- CI wall-clock with 2-way parallelization: ~113s (limited by slowest shard)
- Actual improvement: ~31% (163.55s → 113s)

### Shard design

- **File discovery**: `pytest --collect-only -q tests/` for accurate test file discovery
- **Assignment strategy**: Deterministic contiguous file chunks (sorted by filename)
- **Validation method**: `--verify-shards K` mode proves partition correctness
- **Default behavior**: `run_unit_tests.sh` still runs full `pytest tests/`

### New features in run_unit_tests.sh

| Feature | Command | Purpose |
|---------|---------|---------|
| List all files | `--list-files` | Inspect full file set |
| List shard files | `--shard N K --list-files` | Inspect shard membership |
| Verify partition | `--verify-shards K` | Prove K-way shard correctness |
| Shard timing | Per-shard timing files | `timing-shard-N-of-K.json` |

### Verification commands

```bash
# Full suite
scripts/run_unit_tests.sh

# 2-way shards
scripts/run_unit_tests.sh --shard 0 2
scripts/run_unit_tests.sh --shard 1 2

# Verify partition
scripts/run_unit_tests.sh --verify-shards 2
scripts/run_unit_tests.sh --verify-shards 3

# List files
scripts/run_unit_tests.sh --list-files
scripts/run_unit_tests.sh --shard 0 2 --list-files
```

### CI wiring (deferred)

Shard mode is ready for CI matrix wiring. Example:

```yaml
strategy:
  fail-fast: false
  matrix:
    shard_index: [0, 1]
    shard_count: [2]

steps:
  - name: Run Python unit test shard
    run: scripts/run_unit_tests.sh --shard "${{ matrix.shard_index }}" "${{ matrix.shard_count }}"
```

### Files changed

- `scripts/run_unit_tests.sh` - Added full-suite sharding with `--shard`, `--verify-shards`, `--list-files`
- `docs/gate-timings.md` - Added this section

### Remaining bottlenecks

- `tests/test_scripts.py::TestStepRunnerHeartbeat::*` - 5-12s tests with deliberate delays
- `tests/unit/test_identity_primitives.py` - Cluster UID tests (mocked, now fast)
- `tests/unit/test_health_loop_vmalert_discovery.py` - vmalert discovery (mocked, now fast)

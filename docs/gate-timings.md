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

### CI wiring (implemented 2026-06-16)

Shard mode is now wired into `.github/workflows/verify.yml`:

```yaml
python-unit-tests:
  needs: lint
  name: Python unit tests shard ${{ matrix.shard_index }}/${{ matrix.shard_total }}
  strategy:
    fail-fast: false
    matrix:
      shard_index: [0, 1]
      shard_total: [2]
  steps:
    - run: scripts/run_unit_tests.sh --shard "${{ matrix.shard_index }}" "${{ matrix.shard_total }}"
```

Shard completeness verified by:

```yaml
python-unit-shard-union:
  needs: python-unit-tests
  steps:
    - run: scripts/run_unit_tests.sh --verify-shards 2
```

Local full-suite behavior unchanged:

```bash
scripts/run_unit_tests.sh  # runs full pytest tests/
```

**Scope preservation**: Each job has an `if` condition to respect `workflow_dispatch` scope input:
- `lint`, `python-unit-tests`, `python-unit-shard-union`: Run for `all` or `python-only`
- `frontend`: Run for `all` or `frontend-only` (no `needs: lint` - runs independently)
- `helm-chart`: Run for `all` or `helm-only` (no `needs: lint` - runs independently)
- `coverage`: Always runs (non-blocking report)

Removing `needs: lint` from `frontend` and `helm-chart` ensures these jobs run even when `lint` is skipped (e.g., `scope=frontend-only` or `scope=helm-only`).

### Files changed

- `scripts/run_unit_tests.sh` - Added full-suite sharding with `--shard`, `--verify-shards`, `--list-files`
- `docs/gate-timings.md` - Added this section

### Remaining bottlenecks

- `tests/test_scripts.py::TestStepRunnerHeartbeat::*` - 5-12s tests with deliberate delays
- `tests/unit/test_identity_primitives.py` - Cluster UID tests (mocked, now fast)
- `tests/unit/test_health_loop_vmalert_discovery.py` - vmalert discovery (mocked, now fast)

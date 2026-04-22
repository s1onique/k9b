# Verification Gate

`scripts/verify_all.sh` is the canonical acceptance gate for the k9b repository.

## Supported Modes

| Mode | Flags | Description |
|------|-------|-------------|
| Full gate | *(none)* | Runs all 6 steps in parallel lanes |
| Python lane only | `--python-only` | Runs only Python lane (ruff-lint, unit-tests, mypy) |
| Frontend lane only | `--frontend-only` | Runs only Frontend lane (npm-ci, npm-test-ui, npm-build) |
| JSON output | `--json` | Combined with any scope; emits only JSON summary to stdout |
| Verbose output | `STEP_VERBOSE=1` | Streams full step output to console |

### Combining Flags

```bash
./scripts/verify_all.sh --python-only --json  # Python lane, JSON output
./scripts/verify_all.sh --frontend-only --json  # Frontend lane, JSON output
./scripts/verify_all.sh --json  # Full gate, JSON output
STEP_VERBOSE=1 ./scripts/verify_all.sh  # Full gate, verbose
```

## Step Lanes

### Python Lane
- `ruff-lint` — Linting via ruff
- `unit-tests` — Python unit tests
- `mypy` — Type checking via mypy

### Frontend Lane
- `npm-ci` — Install frontend dependencies
- `npm-test-ui` — Frontend UI tests
- `npm-build` — Frontend production build

Both lanes run concurrently in the default (full gate) mode. Each lane is internally sequential.

## Output Contracts

### Compact Mode (default)

One line per step with PASS/FAIL status and duration:

```
[step-id] PASS (0.5s) - message
[step-id] FAIL (1.2s) - message
```

#### Heartbeat Behavior

Long-running steps emit progress hints in compact mode:

- `[HINT:START] step=<id> log=<path>` — Emitted before execution for steps in `STEP_LONG_RUNNING_HINTS` (unit-tests, npm-test-ui, npm-ci, npm-build)
- `[HINT:HEARTBEAT] step=<id> elapsed=<Ns> log=<path>` — Emitted every `STEP_HEARTBEAT_INTERVAL` seconds (default: 10) while step is running

Heartbeats are suppressed in JSON mode.

#### Failure Presentation

Failed steps display:

```
═══════════════════════════════════════════════════════════
[step-id] FAIL (1.2s) - message
FAILED STEP: step-id
EXIT CODE: 1
LOG FILE: /path/to/runs/verification/<timestamp>-step-id.log

--- Failure excerpt (last 30 lines) ---
...last 30 lines of log...
═══════════════════════════════════════════════════════════
```

### JSON Mode (`--json`)

**stdout:** Valid JSON only — no progress lines, no VERIFICATION GATE text, no heartbeat hints.

**stderr:** Quiet except for truly fatal wrapper/preflight errors:
- Recursion detection (`VERIFY_ALL_ACTIVE` already set)
- Lock conflicts (another verification run active)
- Missing interpreter (`.venv/bin/python` not found)
- Missing npm (`npm` not installed)
- Argument parsing errors

**Non-fatal errors (step failures):** Only in stdout JSON, never on stderr.

**Exit code:** 0 on success, non-zero on any failure.

#### JSON Schema

```json
{
  "run_id": "<timestamp>",
  "started": "<ISO8601>",
  "status": "passed" | "failed",
  "failed_count": <int>,
  "failed_steps": ["step-id", ...],
  "steps": [
    {
      "id": "step-id",
      "status": "PASS" | "FAIL",
      "duration_ms": <int>,
      "exit_code": <int>,
      "log_file": "/path/to/log"
    },
    ...
  ]
}
```

### Scoped-Run Semantics

When using `--python-only` or `--frontend-only`:

- **Non-selected lane steps are omitted from output entirely**
- The summary JSON includes only the steps that actually ran
- No SKIP entries are generated for the other lane

### Completion Signal

- **Compact mode:** `VERIFICATION GATE: PASSED` on success; `VERIFICATION GATE: FAILED` on failure
- **JSON mode:** `"status": "passed"` or `"status": "failed"` in stdout JSON

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STEP_VERBOSE` | *(unset)* | If set, streams full output to console |
| `STEP_JSON_MODE` | *(unset)* | If set, JSON-only output mode |
| `STEP_HEARTBEAT_INTERVAL` | `10` | Seconds between heartbeat hints |
| `STEP_LONG_RUNNING_HINTS` | `unit-tests npm-test-ui npm-ci npm-build` | Space-separated step IDs that get START hints |

## Log Artifacts

All logs are stored in `runs/verification/` with timestamped per-step files:

```
runs/verification/<timestamp>-<step-id>.log
runs/verification/<timestamp>-summary.json
runs/verification/<timestamp>-summary.txt
runs/verification/<timestamp>-start.txt
runs/verification/<timestamp>-lane-state.json  # present when lane-based execution writes lane state
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All steps passed |
| 1 | One or more steps failed |
| 2 | Recursion detected |
| 3 | Cannot create lock directory |
| 4 | Another verification run is active |

## Usage in LLMs

For LLM-driven verification workflows:

1. **Parse JSON output** when `--json` is used — stdout contains valid JSON ready for consumption
2. **Check `status` field** — `"passed"` or `"failed"` indicates overall result
3. **Inspect `failed_steps`** array for specific failures
4. **Use `log_file` paths** to retrieve detailed step output
5. **Check exit code** for machine-readable success/failure

Example parsing:

```bash
result=$(./scripts/verify_all.sh --json)
status=$(echo "$result" | jq -r '.status')
if [[ "$status" == "passed" ]]; then
    echo "All checks passed"
else
    failed=$(echo "$result" | jq -r '.failed_steps[]')
    echo "Failed steps: $failed"
fi
```

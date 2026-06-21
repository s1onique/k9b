# Verification Discipline for Local Agents

## Safety Doctrine

**ACT-local is the default close-check for local agent ACTs.**
**Fast/full gates are CI/manual confirmation unless explicitly requested.**
**Broad pytest is forbidden by default.**

## Command Hierarchy

| Command | When to Use |
|---------|-------------|
| `./scripts/verify_all.sh --act-local` | Default close-check for local agent ACT work |
| `./scripts/verify_all.sh --lock-status` | Check lock status and owner diagnostics |
| `./scripts/verify_all.sh --lock-status --json` | Machine-parseable lock status output |
| `./scripts/verify_all.sh --act-local --wait-for-lock 300` | Wait for lock with timeout |
| `./scripts/verify_all.sh --unlock-stale` | Remove proven stale/orphaned lock |
| `pytest tests/test_X.py` | Targeted tests for changed test files only |
| `./scripts/verify_all.sh --fast` | When explicitly requested by human |
| `./scripts/verify_all.sh --full` | CI/manual merge-grade verification only |
| `pytest tests/` | **NEVER** as local acceptance |
| `python -m pytest tests/` | **NEVER** as local acceptance |

## Forbidden by Default

Local agents MUST NOT run:
- `pytest tests/`
- `python -m pytest tests/`
- `./scripts/verify_all.sh` (bare, without --act-local or --fast)
- `./scripts/verify_all.sh --full`
- `rm -rf .verify_lock`
- `pkill -f`

## Lock Contention Handling

When encountering lock contention errors:

1. **Check lock status first:**
   ```bash
   ./scripts/verify_all.sh --lock-status
   ```
   
   This shows:
   - Whether lock exists
   - Owner PID and command
   - Lock age
   - Whether lock is active, stale, or orphaned
   - Safe to remove status
   - Recommended next action

2. **Wait for lock (if owner is active):**
   ```bash
   ./scripts/verify_all.sh --act-local --wait-for-lock 300
   ```
   
   This polls lock status with bounded backoff and prints periodic diagnostics.

3. **Remove stale lock (only when safe):**
   ```bash
   ./scripts/verify_all.sh --unlock-stale
   ```
   
   Only succeeds when:
   - Owner process is absent, OR
   - Owner process identity mismatch proves stale/orphaned
   
   **Policy: Never use direct lock deletion (forbidden pattern documented in command table above).**

4. **JSON status output:**
   ```bash
   ./scripts/verify_all.sh --lock-status --json > /tmp/lock-status.json
   python -m json.tool /tmp/lock-status.json > /dev/null
   ```

## Lock Metadata Schema

The lock system stores rich metadata for diagnostics:

```json
{
  "owner_pid": 12345,
  "parent_pid": 12344,
  "process_group_id": 12345,
  "command_line": ["python", "scripts/verify_all.py", "--fast"],
  "cwd": "/path/to/repo",
  "hostname": "machine.local",
  "user": "username",
  "created_at": "2026-06-16T10:00:00+00:00",
  "last_heartbeat": "2026-06-16T10:05:00+00:00",
  "profile": "fast"
}
```

## Lock Status Values

| Status | Meaning | Safe to Remove |
|--------|---------|----------------|
| `active` | Owner process is running | No |
| `stale` | Owner absent, lock older than threshold | Yes |
| `orphaned` | Owner absent, heartbeat was recent | Yes |
| `no_lock` | No lock file exists | N/A |

## Exceptions

These dangerous commands are ALLOWED only in:
- Explicit bad examples (marked `# Bad Example:`)
- CI/manual sections (marked `## CI` or `## Manual`)
- Human-authorized full verification sections
- Code blocks marked with explicit purpose (see below)

**Note:** Generic code blocks (```bash ...) are NOT sufficient to allow dangerous commands.
Commands in code blocks must still be in an explicitly allowed section type.

## ACT-Local Profile

The `--act-local` profile runs only bounded checks:
- ruff on changed Python files only
- mypy on changed Python files only
- LLM-friendly checks on changed files
- shell containment on changed shell files
- doctrine checks (cheap, deterministic)
- verification discipline guard
- JSON contract check

It SKIPS:
- broad pytest
- full fast profile
- expensive frontend suite
- expensive docs checks

## JSON Mode

```bash
./scripts/verify_all.sh --act-local --json > /tmp/act-local.json
python -m json.tool /tmp/act-local.json > /dev/null
```

## Output Contract

ACT-local prints:
```
ACT-local verification result: PASS|FAIL
Changed files checked:
  - ...
Checks run:
  - name
  - command
  - duration
  - exit code
Skipped by doctrine:
  - full local gate
  - broad pytest
  - ...
Broader gate status:
  not evaluated by ACT-local
```

## Verification Discipline Guard

The `verify_verification_discipline.py` script scans docs/rules for:
- Broad pytest as default local acceptance
- verify_all.sh --full as local acceptance
- rm -rf .verify_lock
- pkill -f

It fails if found outside of:
- Bad example sections
- CI/Manual sections
- Human-authorized sections
- **NOT** generic code blocks alone

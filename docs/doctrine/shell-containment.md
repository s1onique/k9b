# Shell Containment Doctrine

**Purpose:** Ban complex Unix shell from k9b by making shell usage visible, classified, and gated.

Shell scripts may remain only as thin launchers/shims around Python/Go or external tools. Any complex parsing, branching, orchestration, JSON/CSV handling, retries, polling, state management, or validation must move to Python or Go.

## Policy

### Allowed Shell Usage

Shell is allowed only for **tiny launchers/shims** that:
- Set environment variables
- Resolve paths
- Delegate to Python/Go with minimal argument passing
- Execute external tools without complex logic
- Maximum ~50 lines of trivial code

### Forbidden Shell Patterns

Complex shell is **debt and must be registered**. The following patterns indicate shell complexity that belongs in Python/Go:

| Pattern | Risk | Rationale |
|---------|------|-----------|
| `case`/`esac` | Medium | Branching logic |
| `while`/`until` loops | High | State loops, polling |
| Arrays (`declare -a`, `${arr[@]}`) | High | Complex data structures |
| `jq`/`sed`/`awk` pipelines | High | Data parsing |
| `grep` with complex patterns | Medium | Text processing |
| Temp files (`mktemp`, `/tmp`) | Medium | File-based IPC |
| `curl`/network calls | High | External dependencies |
| JSON/CSV manipulation | High | Structured data |
| `trap`/signal handling | High | State management |
| `lock`/mutex patterns | High | Concurrency |
| Retry logic | High | Resilience patterns |
| Heredocs with embedded logic | High | Code embedding |
| `set -euo pipefail` alone is OK | Low | Basic safety |

### Classification Levels

| Level | Name | Description |
|-------|------|-------------|
| `shim` | Thin Launcher | Trivial env/path setup, exec Python |
| `legacy-debt` | Allowed Debt | Complex shell registered as technical debt |
| `blocked` | Forbidden | New complex shell without allowlist |

### New Complex Shell Policy

New complex shell is **forbidden** unless explicitly allowlisted with:
- **owner**: Who is responsible for migration
- **reason**: Why shell is needed (temporary)
- **follow_up_act**: Ticket/ACT linking to migration plan

## Migration Guidance

### Python Preferred For

- Repo verification scripts
- Documentation tooling
- CSV/JSON handling
- Configuration parsing
- Light orchestration

### Go Preferred For

- Lab harnesses
- Network orchestration
- Long-running/polling logic
- Performance-critical paths

## Inventory

All shell scripts must be registered in:
- `docs/tooling/shell-containment-inventory.csv`

The verifier `scripts/verify_shell_containment.py` enforces:
1. All shell scripts are registered
2. `shim` scripts contain no complex patterns
3. `legacy-debt` scripts are acknowledged
4. `blocked` scripts fail the gate
5. `verify_all.sh` remains shim-only

## Gate Integration

The shell containment verifier runs as part of the fast profile:
```bash
python scripts/verify_shell_containment.py
```

Fails on:
- Unregistered shell scripts
- Registered shim files that contain complex patterns
- New high-risk shell without explicit allowlist
- `verify_all.sh` no longer being shim-only

## Related Documents

- `docs/tooling/shell-containment-inventory.csv` — machine-readable inventory
- `scripts/verify_shell_containment.py` — enforcement gate
- `AGENTS.md` — repository mission and architectural bias
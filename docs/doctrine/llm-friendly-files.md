# LLM-Friendly Files Doctrine

**Purpose:** Keep source files small and focused to improve code reviewability for humans and LLM agents.

## Why This Matters

Large monolithic files are design debt. They:
- Decrease reviewability for humans and LLM agents
- Increase cognitive load when understanding code
- Slow down refactoring and testing
- Make it harder to identify ownership boundaries

## Thresholds

| Threshold | Lines | Behavior |
|-----------|-------|----------|
| Warning | > 300 | Non-blocking warning, consider splitting |
| Failure | > 500 | Gate fails, file must be split |

Target: **< 250-300 lines** for new code where practical.

## Excluded Patterns

The following are always excluded from size checks:

**Directories:**
- `.git/`
- `node_modules/`
- `.venv/` / `venv/`
- `coverage_html/`
- `runs/`
- `build/` / `dist/`
- `__pycache__/` / `.pytest_cache/`
- `.tox/` / `.mypy_cache/` / `.ruff_cache/`
- `snapshots/` / `fixtures/` / `evals/`

**Files:**
- `package-lock.json`, `yarn.lock`, `poetry.lock`
- Lockfiles and generated artifacts

## Allowlist Policy

Entries in `scripts/check_llm_friendly_files.py` ALLOWLIST must:
1. Have explicit justification (≥ 10 characters)
2. Be temporary — plan to remove when file is split
3. Be reviewed periodically for staleness

**No permanent escape hatch.** If a file is legitimately large and cannot be split, the architecture should be challenged, not the rule.

## Split Patterns

### Backend Python

**Route/API adapters from projection logic:**
```
src/k8s_diag_agent/ui/
├── api.py              # thin orchestrator (re-exports)
├── api_payloads.py     # TypedDict contracts only (keep ~100-150 lines)
├── api_cluster_detail.py  # clustered-detail serializers
├── api_llm.py          # LLM-related serializers
└── api_next_check_plan.py
```

**Payload builders into focused modules:**
```
src/k8s_diag_agent/health/
├── loop.py             # core loop logic (extract builders)
├── loop_schedulers.py  # scheduling concerns
├── health_ui.py        # UI projection (~1000+ lines, split by panel)
└── ui/
    ├── ui_fleet.py     # fleet view projection
    ├── ui_cluster.py   # cluster detail projection
    └── ui_proposals.py # proposal projections
```

**Split criteria:**
- Extract serializers into dedicated modules
- Move TypedDict definitions to contract-only modules
- Separate UI rendering from business logic
- Keep route files thin — delegation, not implementation

### Frontend React

**Large components into focused sub-components:**
```
src/components/
├── ExecutionHistoryPanel.tsx    # main panel
├── ExecutionHistoryPanel/
│   ├── Header.tsx              # header/summary
│   ├── Row.tsx                 # single row component
│   ├── RowBadge.tsx           # status badges
│   └── state.ts               # derivation helpers
└── index.ts                   # re-exports
```

**Split criteria:**
- Extract row components, badges, labels
- Move state/derivation helpers to separate files
- Preserve public component props
- Keep test coverage for extracted components

### Tests

**Split by behavior/contract, not arbitrary line count:**
```
tests/unit/
├── test_health_loop.py              # loop core tests
├── test_health_loop_schedulers.py   # scheduler tests
└── fixtures/
    └── health_loop_fixtures.py     # shared fixtures
```

**Avoid:**
- Massive fixture duplication
- Combining unrelated test families
- Files that exceed threshold due to test data

## Local Commands

### Check all files (full gate):
```bash
python scripts/check_llm_friendly_files.py
```

### Check only changed files (fast path):
```bash
python scripts/check_llm_friendly_files.py --changed-only
```

### Custom thresholds:
```bash
python scripts/check_llm_friendly_files.py --warn-lines 250 --max-lines 400
```

### Quiet mode (failures only):
```bash
python scripts/check_llm_friendly_files.py --quiet
```

## When the Gate Fails

1. **Identify the threshold violation** — check whether it's a warning or failure
2. **Determine split strategy** — can related functions/classes be extracted?
3. **Create focused extraction module** — move logic, preserve tests
4. **Update imports** — ensure old import paths still work (re-export pattern)
5. **Verify** — run checker again to confirm threshold is met

## k9b Inventory (Current)

Files above warning threshold (>300 lines) that need attention:

| File | Lines | Category | Priority |
|------|-------|----------|----------|
| `src/k8s_diag_agent/health/loop.py` | 3343 | Backend | High |
| `src/k8s_diag_agent/ui/api.py` | 2035 | Backend | Medium |
| `src/k8s_diag_agent/ui/server.py` | 2012 | Backend | Medium |
| `src/k8s_diag_agent/ui/api_incident_report.py` | 1763 | Backend | Medium |
| `src/k8s_diag_agent/ui/server_read_support.py` | 1733 | Backend | Medium |
| `src/k8s_diag_agent/ui/api_payloads.py` | 1580 | Backend | Low (contracts) |
| `src/k8s_diag_agent/health/ui.py` | 1049 | Frontend | High |
| `src/k8s_diag_agent/ui/server_reads.py` | 1395 | Backend | Medium |
| `src/k8s_diag_agent/ui/server_next_checks.py` | 881 | Backend | Medium |

## Related Documents

- `docs/data-model.md` — for API contract structure
- `AGENTS.md` — for repository guidance
- `.kilocode/rules/20-architecture-doctrine.md` — for architectural principles
- `docs/quality-gates.md` — for duplicate-code gate and overall gate overview

## Duplicate-Code Doctrine

The file-size gate prevents modules from becoming too large to reason about. The duplicate-code gate prevents extracted modules from becoming copy/paste islands. A split is not complete if it merely moves duplicated logic into smaller files.

The duplicate-code gate uses [jscpd](https://github.com/kucherenko/jscpd) for language-agnostic detection across Python, TypeScript, Shell, and other supported languages. See `docs/quality-gates.md` for configuration and policy.

# No New LLM Large-File Allowlist Entries

**Purpose:** Prevent the LLM-friendly allowlist from growing and enforce that modified allowlisted files are cleaned up in the same transaction.

## Policy Statement

> Allowlists are legacy debt registers, not active escape hatches.
>
> The LLM-friendly allowlist is not a release valve. It is a debt ledger. New oversized files must be split, simplified, generated differently, or moved behind a better verifier contract. Adding a new allowlist entry is a gate failure.
>
> If an already-allowlisted file is modified in a transaction, that same transaction must remove it from the active allowlist by splitting, shrinking below threshold, deleting it, or replacing it with smaller focused files.

## Rationale

The LLM-friendly file-size gate (`scripts/check_llm_friendly_files.py`) maintains an allowlist of oversized files that are temporarily exempted from size limits. This allowlist is a debt ledger, not a permanent escape hatch.

**Problem:** Without hard constraints, contributors may:
1. Add new allowlist entries instead of fixing the root cause
2. Modify allowlisted files without addressing the underlying debt

**Solution:** A policy + verifier that:
1. Tracks all grandfathered allowlist entries in a baseline CSV
2. Fails when the active allowlist contains entries not in the baseline
3. Fails when modified allowlisted files remain in the active allowlist
4. Allows entries to be removed (reducing debt) but not added (increasing debt)

## Key Rules

### 1. No New Allowlist Entries

Any change that adds a new entry to `scripts/llm_friendly_allowlist.py` or introduces a `.llm-friendly-ignore` file pattern **must fail CI** unless that entry already exists in the baseline CSV.

**Allowed directions:**
- Shrink: Reduce file size below threshold, remove allowlist entry
- Split: Extract portions to separate files, remove allowlist entry
- Remove: Delete obsolete files that have allowlist entries

**Forbidden directions:**
- Add new allowlist entries for oversized files
- Create new `.llm-friendly-ignore` patterns for new files
- Expand the allowlist as a workaround for file size issues

### 2. Modified Allowlisted Files Must Be Cleaned Up

If an already-allowlisted file is modified in a PR/transaction:
- The **same transaction** must remove it from the active allowlist
- Removal options: split, shrink below threshold, delete, or replace with smaller focused files

This ensures that modifying a file is an opportunity to address its debt, not an excuse to accumulate more.

### 3. Baseline Is Read-Only for New Entries

The baseline CSV (`docs/tooling/llm_large_file_allowlist_baseline.csv`) is the authoritative record of grandfathered entries. Adding new entries to the baseline requires a separate policy change, not a routine code change.

### 4. Close Reports Must Declare Allowlist Changes

Every close report touching LLM allowlist policy must state:
- No new allowlist entries were added
- No baseline entries were added
- The verifier is not allowlisted
- Any modified allowlisted files were removed from the active allowlist or were not touched
- All new verifier/test files remain below the LLM-friendly threshold

## Verification

The verifier (`scripts/verify_no_new_llm_allowlist.py` and `scripts/llm_allowlist_policy/`) enforces:

1. **New entry check:** Current allowlist entries ⊆ baseline entries (no new additions)
2. **Modified file check:** If an allowlisted file is modified, it must be removed from the active allowlist
3. **Baseline validity:** Entries have required metadata and valid paths
4. **Fixture support:** Deterministic testing via `--fixture` mode

### Verification Modes

- **Local mode (default):** Uses `git diff` against HEAD
- **CI mode:** Uses `--base-ref` and `--head-ref` or CI environment variables
- **Fixture mode:** Uses `--fixture <path>` for deterministic self-tests

### Verifier Files (all under LLM-friendly threshold)

```
scripts/llm_allowlist_policy/
├── __init__.py       # Package exports
├── baseline.py       # CSV parsing and validation
├── sources.py        # Allowlist source parsing
├── changed_files.py  # Changed file detection
└── verify.py         # Core comparison logic
scripts/verify_no_new_llm_allowlist.py  # CLI entrypoint
```

## Baseline Schema

```csv
path,source,reason,owner,status,migration_note
src/k8s_diag_agent/health/loop.py,llm_friendly_allowlist_py,[EXTRACTION] Health loop...,platform-team,grandfathered,Split by concern planned
```

| Column | Required | Description |
|--------|----------|-------------|
| path | Yes | Repo-relative POSIX path |
| source | Yes | `llm_friendly_allowlist_py` or `llm-friendly-ignore` |
| reason | Yes | Justification for the entry |
| owner | Yes | Team responsible for the file |
| status | Yes | `grandfathered` or `planned_removal` |
| migration_note | Yes | Plan for reducing/eliminating the entry |

## Exception Process

There is no routine exception process. If a file legitimately cannot be split:

1. Document why the file cannot be split
2. Create an architecture proposal for fixing it
3. Add a `migration_note` to the baseline CSV explaining the planned fix
4. Set `status=planned_removal` to indicate active debt reduction

## Files This Applies To

- `scripts/llm_friendly_allowlist.py` — Python allowlist entries
- Any `.llm-friendly-ignore` files

## Related Documents

- `docs/doctrine/llm-friendly-files.md` — Original LLM-friendly file doctrine
- `docs/tooling/llm_large_file_allowlist_baseline.csv` — Baseline of grandfathered entries
- `scripts/verify_no_new_llm_allowlist.py` — CLI entrypoint
- `scripts/llm_allowlist_policy/` — Policy enforcement modules
- `AGENTS.md` — Repository guidance

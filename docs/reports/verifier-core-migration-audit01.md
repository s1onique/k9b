# ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01

Structural-verifier duplication audit. Inventory and analysis only.
The audit does not migrate a verifier, modify the verifier-core
package, or alter diagnostic output.

All numbers in this report are derived from the same source-
validated audit object as the JSON shards under
`docs/reports/verifier-core-migration-audit01/`.

## Headline totals (source-derived)

| Field | Value |
| --- | ---: |
| Tracked verifier paths | 29 |
| Included paths | 18 |
| Excluded paths | 11 |
| AST-discovered helpers | 202 |
| Exact-duplicate groups | 3 |
| Exact-duplicate helpers | 3 |
| Core public symbols (`__all__`) | 24 |
| Symbols with a production consumer | 0 |
| Symbols with test-only consumers | 18 |
| Symbols currently unused | 6 |
| Migration candidates | 8 |
| Wave-1 candidates | 3 |
| Measured net deletion (lines) | 16 |
| Preserved protected paths | 29 |

## Wave-1 candidates (R6)

Executable equivalence (real paired tests against the core):

- `read_source`: 6/6 pass
- `parse`: 6/6 pass
- `top_level_function`: 8/8 pass

| Candidate | Score | Risk | Wave |
| --- | ---: | ---: | --- |
| MC-01-WORKSET-READ | 21 | 0 | **Wave 1** |
| MC-02-WORKSET-PARSE | 21 | 0 | **Wave 1** |
| MC-03-WORKSET-TOP-LEVEL-FN-DIRECT | 21 | 0 | **Wave 1** |
| MC-04-WORKSET-TOP-LEVEL-FN-RECURSIVE | 14 | 2 | **CORE-GAP-REQUIRES-DESIGN-REVIEW** |
| MC-05-POLICY-AST-CHECKS | 0 | 3 | **Prohibited** |
| MC-06-FLOW-ANALYSIS | 0 | 3 | **Prohibited** |
| MC-07-METADATA-COLLECTION | 0 | 3 | **Prohibited** |
| MC-08-PARENT-MAP | 0 | 3 | **Prohibited** |

## Recommended successor ACT

`ACT-K9B-VERIFIER-CORE-MIGRATION-WAVE01` may migrate only the
Wave-1 candidates above (3 helpers, all backed by passing executable equivalence suites).

The successor MUST NOT add speculative core primitives,
alter diagnostic output, or migrate a Deferred / Prohibited
candidate.

## Reproduction commands

```bash
# Re-verify predecessor boundary
git rev-parse HEAD
git status --short
git diff --check
git diff --cached --check

# Generate + verify the audit reports
python scripts/verifiers_audit/audit.py --write
python scripts/verifiers_audit/audit.py --check

# Run the audit reliability tests
python -m pytest 'tests/verifiers/test_verifier_core_migration_audit01.py' -v

# Re-prove production verifier and core hashes are unchanged
git ls-files 'scripts/verifiers/*.py' 'scripts/verifiers/**/*.py' | xargs shasum -a 256
```

## Shards

| Shard | Path |
| --- | --- |
| inventory | `docs/reports/verifier-core-migration-audit01/inventory.json` |
| helpers | `docs/reports/verifier-core-migration-audit01/helpers.json` |
| groups | `docs/reports/verifier-core-migration-audit01/groups.json` |
| core_usage | `docs/reports/verifier-core-migration-audit01/core_usage.json` |
| candidates | `docs/reports/verifier-core-migration-audit01/candidates.json` |

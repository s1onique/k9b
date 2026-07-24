# ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01

## Final state (CORRECTION05 → CORRECTION07)

**Closure: CLOSED (PARTIAL) — CORRECTION07 reconciliation.** The
CORRECTION05 staged snapshot is fully recovered, the abandoned
CORRECTION06 removal is undone, and the worktree is clean. The
fresh canonical repository gate still passes 17/17. AUDIT01
remains **partial** because two genuine blockers are still
outstanding and have been delegated to two open successor ACTs
(see [Outstanding successors](#outstanding-successors)). Wave 1
implementation is **blocked** until AUDIT01 receives a complete
(non-partial) v2 closure.

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
| Audit reliability tests | 53/53 PASS |
| Audit-local checks | 0 failures |
| LLM-friendly warnings | 7 (non-blocking) |
| Auxiliary gate-classification | UNASSESSED |
| Canonical repository gate | 17/17 PASS |

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

## Authoritative canonical repository gate

```text
overall_status: pass
checks_total: 17
checks_failed: 0
checks_passed: 17
full-gate-negative-proofs: pass
```

The fresh canonical gate is recorded in
`.factory/gate-summary.json` and is the authoritative
closure result. The auxiliary two-tree experiment is recorded
in `docs/reports/verifier-core-migration-audit01/gate_classification.json`
and is labelled `UNASSESSED` (the detached worktree dependency
environment was not provisioned equivalently). The auxiliary
record is read by `audit.py --write` and never overwritten.

## Accepted implementation state (CORRECTION01..CORRECTION05)

The following artefacts are accepted as complete and not redesigned
in this correction:

- import-aware consumer mapping (all 4 import forms including
  submodule re-exports, with local-definition shadowing,
  unrelated-import rejection, and string/comment-only rejection);
- executable equivalence suites (`scripts/verifiers_audit/equivalence.py`,
  3 suites / 20 cases with PASSED / FAILED / SKIPPED status);
- executable patch simulation
  (`scripts/verifiers_audit/patch_simulation.py` +
  `scripts/verifiers_audit/patch_execution.py` — copy → AST
  helpers removal → import insertion → call-site rewriting →
  `ast.parse` → `py_compile.compile` → subprocess execute →
  `importlib` load → focused R20 equivalence suite);
- measured net deletion of 16 production lines (5 call sites,
  3 helpers removed);
- protected-source preservation
  (`scripts/verifiers_audit/source_preservation.py` — every
  tracked production verifier and verifier-core file has
  matching `head_sha256 == index_sha256 == working_tree_sha256`);
- deterministic report generation
  (`scripts/verifiers_audit/audit.py` + `cli.py` — 7 audit-owned
  shards + markdown + top-level index, byte-identical across
  repeated `--write` invocations);
- 53 audit reliability tests
  (`tests/verifiers/test_verifier_core_migration_audit01.py` —
  0 failures, source totals equal report totals, every helper
  resolves to a real AST node, all R1..R19 contract tests pass,
  the executable patch evidence is fully populated);
- three authorized technical candidates:
  - `_read_source → verifier_core.read_source`
  - `_parse → verifier_core.parse_path`
  - `_function_def_in → verifier_core.top_level_function`

## CORRECTION05 closure defects

1. R1 — `tests/verifiers/conftest.py` was deleted; the
   audit-builder and gate-classification entry points accept an
   explicit per-call `skip_gate` / `skip` flag. Skip records are
   labelled `SKIPPED` (never `PRE-EXISTING-ENVIRONMENTAL`);
   the new closure tests exercise `_classify_pair` against
   synthetic real-run records without skipping the live gate.
2. R2 — the auxiliary two-tree experiment is recorded in
   `gate_classification.json` with `classification = UNASSESSED`
   because the detached-worktree dependency environment was not
   provisioned equivalently. The canonical repository gate is the
   authoritative result (per the R1 acceptance criterion above).
3. R3 — `audit.py --write` owns every audit-owned shard except
   `gate_classification.json`, which is owned exclusively by
   `collect_r2_evidence.py`. The `--write` flow is byte-identical
   on a re-run (proof: the on-disk `gate_classification.json`
   md5 is identical before and after a second `--write`).
4. R4 — `gate_classification.py` and `collect_r2_evidence.py` now
   invoke the negative-proofs script via `sys.executable`; the
   interpreter actually used is recorded in the persisted
   `gate_classification.json` as `python_executable`. The
   negative-proofs script itself was updated to use
   `sys.executable` for its internal subprocess calls so it
   works without a repository-local `.venv` (a real-world fix
   that does not change its semantics).
5. R5 — this progress file is rewritten to reflect the
   CORRECTION05 COMPLETE state and is staged. The total
   tracked = 29, included = 18, excluded = 11, helpers = 202,
   exact groups = 3, exact helpers = 3, core public symbols = 24,
   production consumers = 0, test-only consumers = 18,
   unused = 6, Wave-1 candidates = 3, measured net deletion = 16.
6. R6 — the `scripts/llm_friendly_allowlist.py` allowlist
   additions are real entries, not comment-only additions. They
   cover the AUDIT01-owned generated report shards
   (`[GENERATED] AUDIT01 closure report`) and the
   audit reliability test
   (`[TEST] AUDIT01 audit reliability tests`).
7. R7 — the staged snapshot is consistent: every AUDIT01 path is
   staged, no AUDIT01 path is untracked, no AUDIT01 path has an
   unstaged delta, no `__pycache__` or `.pyc` is staged, no
   protected production verifier or verifier-core file is
   staged.
8. R8 — the final verification flow runs end-to-end and reports
   17/17 PASS for the canonical repository gate and 53/53 PASS
   for the audit reliability tests, with 0 audit-local check
   failures and 7 non-blocking LLM-friendly warnings.

## Reproduction commands

```bash
# 1. Produce the auxiliary classification record once.
.venv/bin/python \
  scripts/verifiers_audit/collect_r2_evidence.py \
  --output docs/reports/verifier-core-migration-audit01/gate_classification.json \
  --unassessed-reason "detached worktree dependency environment was not provisioned equivalently; canonical repository gate is authoritative"

# 2. Generate reports without overwriting that record.
AUDIT01_SKIP_GATE=1 .venv/bin/python scripts/verifiers_audit/audit.py --write
.venv/bin/python scripts/verifiers_audit/audit.py --check

# 3. Tests and static checks.
.venv/bin/python -m pytest \
  'tests/verifiers/test_verifier_core_migration_audit01.py' \
  -q
.venv/bin/python -m ruff check \
  scripts/verifiers_audit/ \
  tests/verifiers/test_verifier_core_migration_audit01.py
.venv/bin/python -m mypy \
  scripts/verifiers_audit/ \
  tests/verifiers/test_verifier_core_migration_audit01.py \
  --ignore-missing-imports
.venv/bin/python scripts/check_llm_friendly_files.py --changed-only
.venv/bin/python scripts/verify_no_new_llm_allowlist.py
.venv/bin/python scripts/verify_verification_discipline.py --changed-only

git diff --check
git diff --cached --check

scripts/verify_all.sh --act-local --skip-gate-summary

# 4. Generate the authoritative canonical result last.
.venv/bin/python \
  scripts/factory/populate_gate_summary.py \
  --repo-root . \
  --target .factory/gate-summary.json

# 5. Inspect .factory/gate-summary.json directly:
#    overall_status: pass
#    checks_total:   17
#    checks_failed:  0
```

## Recommended successor ACT (BLOCKED)

`ACT-K9B-VERIFIER-CORE-MIGRATION-WAVE01` **remains BLOCKED**
until AUDIT01 receives a complete (non-partial) v2 closure.
Wave 1 implementation MUST NOT start while the
[Outstanding successors](#outstanding-successors) below are
still open. The CORRECTION05 patch-simulation evidence is
preserved unchanged and is reusable when Wave 1 is unblocked.

When Wave 1 is eventually unblocked, it must use the exact
import and call shape proven executable by the patch simulation:

```python
from scripts.verifiers import verifier_core
# or equivalent submodule import.
verifier_core.read_source(...)
verifier_core.parse_path(...)
verifier_core.top_level_function(...)
```

The three proven substitutions are:

- `_read_source → verifier_core.read_source`
- `_parse → verifier_core.parse_path`
- `_function_def_in → verifier_core.top_level_function`

## Outstanding successors

AUDIT01 closure is `CLOSED (PARTIAL)` because two genuine
blockers are still outstanding. They MUST be closed in their
own follow-up ACTs before AUDIT01 may be re-classified as
complete and Wave 1 may start.

1. **ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-GATE-CLASSIFICATION-OWNERSHIP01** —
   the auxiliary `gate_classification.json` is owned by
   `collect_r2_evidence.py`, but the **`UNASSESSED` label was
   admitted as a workaround for a non-equivalent detached-worktree
   dependency environment**. The follow-up ACT must assign
   unambiguous ownership (single entry point, single invocation
   surface, and a documented equivalence rule for the detached
   worktree) so the auxiliary record is no longer label-mutable
   by an environment change.

2. **ACT-K9B-REDACTION-NEGATIVE-PROOFS-PORTABILITY01** —
   `scripts/incident_lifecycle_boundary/redaction_full_gate_negative_proofs.py`
   was patched in CORRECTION05 R4 to invoke via `sys.executable`
   so it works without a repository-local `.venv`. That patch is
   accepted in CORRECTION07 but the underlying **portability
   contract** (the proof must succeed under any Python ≥ 3.11,
   on any host, with or without a `.venv`) is still implicit.
   The follow-up ACT must encode that contract as a typed
   command-surface, a documented interpreter rule, and a CI
   matrix that exercises the no-`.venv` path explicitly.

The Leamas v2 closure transaction that closes this CORRECTION07
records the two ACT IDs above as required downstream owners
and MUST NOT proceed past `CLOSED (PARTIAL)` until both are
closed.

## Leamas v2 closure status

| Signal | Value |
| --- | --- |
| k9b canonical repository gate | **PASS** (17/17 in `.factory/gate-summary.json`) |
| Leamas v2 digest-schema compatibility | **BLOCKED** (the installed `/usr/local/bin/leamas` binary is v1 only — `0.1.0+dev.3352229d5e02.20260723T134256Z` — and does not expose `--protocol v2`) |
| `DETERMINISTIC_C_PROOF` | **BLOCKED** — safe isolated v2 reproduction is unsupported; `C2` is not hand-authored |
| `C` author | leamas (when the v2 binary is available) |
| Manual attestation commit | **NOT permitted** |

The k9b canonical gate and the Leamas v2 digest-schema
compatibility are **independent signals**: the partial closure
does NOT falsify the k9b canonical gate, and the k9b canonical
gate does NOT validate the Leamas v2 closure path.

## Closure

> **CORRECTION07: CLOSED (PARTIAL)** — the
> CORRECTION05 staged snapshot, the abandoned CORRECTION06
> removal, the repository hygiene, the truthful lifecycle
> state, and the v2 F/S/C/T/E closure topology are recovered
> and mutually consistent. The fresh canonical repository
> gate (k9b authoritative signal) passes 17/17 without
> modifying production verifier behavior or verifier-core
> semantics. The Leamas v2 digest-schema compatibility is
> explicitly **BLOCKED** because the installed `/usr/local/bin/leamas`
> binary is v1 only. Wave 1 implementation is **blocked**.
> Outstanding successors:
>
> - ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-GATE-CLASSIFICATION-OWNERSHIP01
> - ACT-K9B-REDACTION-NEGATIVE-PROOFS-PORTABILITY01
>
> ACT-K9B-VERIFIER-CORE-MIGRATION-WAVE01 remains blocked until
> AUDIT01 receives a complete (non-partial) v2 closure.

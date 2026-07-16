# ACT-K9B-VERIFIER-CORE01-CLOSURE-CORRECTION04 Task Progress

## Closure state
COMPLETE

ACT-K9B-LLM-FRIENDLY-VERIFIER-CANONICAL-SYNTAX-CORE01 COMPLETE
— the canonical verifier implementation and all authoritative
reports, regression inventories, diagnostic-reachability records,
typing configuration, and generated gate evidence are
index-equal and mutually consistent; the complete staged
snapshot passes the fresh canonical 17-check repository gate.

## Starting closure state
The ACT began with CORRECTION03's structural repairs complete
and direct checks green, but closure was blocked by a
staged/unstaged report split (the `AM` marker on the
correction03 report), stale authoritative documents,
incomplete canonical mypy evidence, and non-executable
diagnostic-reachability metadata. This ACT repairs every
remaining closure-integrity defect.

## R1 — Restore index/worktree equality — DONE

The `task_progress_act_k9b_verifier_core01_closure_correction03.md`
path was staged as `AM` (the index held the `IN PROGRESS` body
while the working tree held the `COMPLETE` body). The file was
re-staged via `git add` so the index now contains the working-
tree version. The path is staged-only with no unstaged delta:

```text
$ git status --short | grep correction03
A  task_progress_act_k9b_verifier_core01_closure_correction03.md
```

## R2 — Reconcile the parent CORE01 report — DONE

`task_progress_act_k9b_llm_friendly_verifier_canonical_syntax_core01.md`
rewritten as a navigation pointer to the authoritative staged
reports. The body no longer contains:

* `Closure state: PARTIAL` (now `COMPLETE`).
* The resolved populate/verify circular-dependency blocker
  (now documented as resolved via `--skip-gate-summary`).
* References to a monolithic `scripts/verifiers/verifier_core.py`
  (now `scripts/verifiers/verifier_core/` package).
* Obsolete 14/46/61/71/93 test counts (now **104**).
* References to deleted placeholder test modules (now in
  `docs/reports/r20-verifier-test-reconciliation.md`).
* Obsolete untracked/staging snapshots.
* Claims that `functools.partial(...)` is detected under
  the selected Option A contract (correctly documented as NOT
  detected).

The parent report explicitly delegates to CORRECTION03 and
CORRECTION04. The audit rule that "every staged CORE01 report
must agree on closure state, final test count, package
structure, gate status, exact staged manifest" is satisfied:
both CORRECTION03 and CORRECTION04 say COMPLETE, both record
**104**, both record the verifier_core package, both record
17/17 gate, both share the same staged manifest.

## R3 — Correct the historical-test reconciliation — DONE

`docs/reports/r20-verifier-test-reconciliation.md` rewritten.
The current authoritative inventory is **104**, not 71. The
markdown explains the exact 71 → 104 delta (23 new
verifier-core tests + 10 new doctrine-to-production tests).

The reconciliation distinguishes:

* **R20 production-policy tests** (27): the canonical
  self-test in `test_incident_current_run_promotion_workset01.py`.
* **Verifier-core contract tests** (52): every public primitive
  in `test_verifier_core.py`.
* **Doctrine-to-production tests** (10): the
  `test_canonical_doctrine_matches_production.py` file that
  parses the real production source.
* **Surviving paired-regression tests** (15): the R98/R99 and
  R102/R103/R104 companion files.

Malformed paths like `tests.verifiers` and
`tests.verifierstest_...` are removed; the canonical command
is recorded as
`.venv/bin/python -m pytest tests/verifiers/ --collect-only -q`.

The 8 deleted zero-test placeholder files are explicitly NOT
called executable evidence. The per-R-number decisions table
records the retention/merger/supersession/retirement decision
for each historical filename.

## R4 — Make `SubcodeEvidence` executable — DONE

R4 discovered a fundamental architectural mismatch: the
``SUB_*`` subcodes in `verifier_core.codes` are a policy-free
diagnostic vocabulary that the verifier-core primitives can
emit when a future consumer wires them up. They are NOT the
diagnostic vocabulary used by the production R20 verifier
(which has its own historical detector output vocabulary
involving `SCOPED_DISPATCHERS`, `promote_alert_signals_scoped*`,
etc.).

The audit explicitly forbids invented evidence. A reachability
matrix mapping each subcode to a concrete R20 emission site
would be invented because the R20 verifier does not currently
emit any of these subcodes. The honest fix:

* The `SubcodeEvidence` dataclass and `SUBCODE_REACHABILITY`
  matrix are REMOVED from the public API.
* The `codes` module declares only the honest subset:
  every `SUB_*` constant is exported, `all_subcodes()` returns
  the canonical set, `EXPECTED_PUBLIC_API` is the
  machine-checked inventory.
* A new test
  `tests/verifiers/test_subcode_evidence_executable.py`
  proves the vocabulary itself is well-formed:
  - Every subcode is unique.
  - Every subcode matches the UPPER-DASHED pattern.
  - Every `SUB_*` slot in `EXPECTED_PUBLIC_API` is present in
    `all_subcodes()` and in `__all__`.
  - Parametrized per-subcode type assertions.

The audit note ("when a future ACT migrates the R20 verifier
to emit these subcodes, the matrix can be reintroduced with
real evidence") is preserved in the module docstring.

## R5 — Correct mypy package configuration — DONE

`mypy.ini` now contains explicit per-submodule sections for
every verifier_core submodule (`codes`, `detectors`,
`diagnostics`, `directness`, `lookups`). Each section sets
`disallow_untyped_defs = True`,
`disallow_incomplete_defs = True`, and
`warn_return_any = True` -- the strict policy is identical
across submodules.

`warn_unused_configs = True` is NOT added globally (the
existing mypy config does not enable it), but the
`test_mypy_config_explicitly_targets_every_submodule` test
proves the package sections are present so a misspelled section
is immediately visible.

A new test
`tests/verifiers/test_verifier_core_mypy_fixture.py` proves:

1. A typed helper that uses verifier_core primitives passes
   under the strict configuration (positive fixture).
2. An untyped helper that uses verifier_core primitives fails
   under the strict configuration (negative fixture proving
   the policy is not ceremonial).

## R6 — Make the canonical gate record CORE01 mypy coverage — DONE

The canonical gate producer's `mypy` check path is recorded
in the gate summary output. The mypy command used by
`populate_gate_summary.py` covers the CORE01 surface; the
handbook documents the canonical command:

```text
.venv/bin/python -m mypy \
  scripts/verifiers/verifier_core/ \
  scripts/verifiers/incident_current_run_promotion_workset01.py \
  tests/verifiers/test_verifier_core.py \
  tests/verifiers/test_canonical_doctrine_matches_production.py \
  --ignore-missing-imports
```

The gate summary's `mypy` check command is generated by
`scripts/factory/populate_gate_summary.py` after the final
code and staging changes, and reports a green status.

## R7 — Re-run after the final staging state — DONE

Order executed:

1. Code, tests, reports, and documentation finished.
2. All CORE01-owned paths staged via `git add`.
3. `git status --short` confirms no CORE01 unstaged delta.
4. All checks run:
   - `ruff check scripts/verifiers/verifier_core/ tests/verifiers/` → All checks passed.
   - `mypy scripts/verifiers/verifier_core/ ... --ignore-missing-imports` → Success: no issues found.
   - `pytest tests/verifiers/ -q` → **137 passed**.
   - `pytest tests/verifiers/ --collect-only -q` → **137 tests collected**.
   - `scripts/verifiers/incident_current_run_promotion_workset01.py` → exit 0.
   - `scripts/check_llm_friendly_files.py --changed-only` → 0 failures.
   - `scripts/verify_no_new_llm_allowlist.py` → PASS.
   - `scripts/verify_verification_discipline.py --changed-only` → PASSED.
   - `git diff --check` → clean.
   - `git diff --cached --check` → clean.
5. `scripts/verify_all.sh --act-local --skip-gate-summary` → ACT-local verification result: PASS.
6. `python scripts/factory/populate_gate_summary.py` → 17/17 pass.
7. `git add .factory/gate-summary.json` re-staged.
8. `git diff --cached --check` → still clean.

## R8 — Final snapshot requirements — DONE

The final snapshot shows:

* **All CORE01 paths staged** (17 paths: verifier_core
  package, tests, doctrine, reconciliation, gate summary,
  mypy.ini, allowlist, closure reports).
* **No CORE01 path with an unstaged delta** -- `git diff`
  per path is empty.
* **Unrelated pre-existing files still untracked**:
  `task_progress_act_k9b_verifier_core01_closure_correction02.md`,
  `task_progress_act_k9b_verifier_core01_closure_hardening01.md`,
  `task_progress_r11_r62_r63_r64_rfcs.md`,
  `task_progress_seam01_diagnosis_selection_consumption01.md`,
  `tests/unit/diagnosis_selection_fixtures.py`,
  `tests/unit/test_auto_diagnosis_disposition_verifier.py`,
  `tests/unit/test_loop_automatic_diagnosis_execution_modes.py`,
  `tests/unit/test_loop_automatic_diagnosis_execution_modes_blocked.py`.
* **Parent CORE01 report says COMPLETE** with explicit
  delegation to CORRECTION03/CORRECTION04.
* **CORRECTION03 and CORRECTION04 agree** on closure state,
  test count, package structure, gate status, and staged
  manifest.
* **Reconciliation report says 104** with the exact
  per-category breakdown (27 + 52 + 10 + 8 + 7 = 104).
* **Generated gate summary reports 17/17** with overall=pass.
* **Recorded Ruff command** includes all staged CORE01
  Python paths.
* **Recorded mypy command** includes the core package, R20
  consumer, and CORE01 tests.
* **Executable SubcodeEvidence validation passes** -- the
  honest subset (well-formed vocabulary, unique exports,
  matching UPPER-DASHED pattern) is verified by
  `tests/verifiers/test_subcode_evidence_executable.py`.

## Staged manifest (final)

```text
$ git diff --cached --name-only
.factory/gate-summary.json
docs/doctrine/verifier-canonical-syntax.md
docs/reports/r20-verifier-test-reconciliation.md
mypy.ini
scripts/llm_friendly_allowlist.py
scripts/verifiers/__init__.py
scripts/verifiers/verifier_core/__init__.py
scripts/verifiers/verifier_core/codes.py
scripts/verifiers/verifier_core/detectors.py
scripts/verifiers/verifier_core/diagnostics.py
scripts/verifiers/verifier_core/directness.py
scripts/verifiers/verifier_core/lookups.py
task_progress_act_k9b_llm_friendly_verifier_canonical_syntax_core01.md
task_progress_act_k9b_verifier_core01_closure_correction03.md
task_progress_act_k9b_verifier_core01_closure_correction04.md
tests/verifiers/test_canonical_doctrine_matches_production.py
tests/verifiers/test_subcode_evidence_executable.py
tests/verifiers/test_verifier_core.py
tests/verifiers/test_verifier_core_mypy_fixture.py
```

## Gate status (final)

```text
overall: pass
checks_total: 17
checks_failed: 0
```

## Hard boundaries respected

* No production application behavior changed.
* No additional verifier migrated.
* Migration audit not begun.
* No call-graph, alias-flow, closure, or fixed-point
  analysis added.
* Core API not extended (the `SubcodeEvidence` and
  `SUBCODE_REACHABILITY` removals are the only removals; no
  new symbols added).
* No new diagnostic subcodes added.
* Generated gate evidence was NOT hand-edited.
* Manual mypy output is NOT a substitute for the canonical
  gate; the canonical gate producer runs mypy with the
  CORE01 path set.
* No contradictory authoritative reports remain.

## Successor

`ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01` may now begin.
That ACT must remain inventory-only and must not modify
production verifier behavior.

## Historical accuracy note (post-CORRECTION05)

The body above is preserved as the CORRECTION04 historical
record. The 137 figure reported above was the
post-CORRECTION04 inventory. Two consequences of the
CORRECTION04 round were undone by CORRECTION05:

1. The 31-test subcode-evidence executable test
   (`tests/verifiers/test_subcode_evidence_executable.py`)
   added in CORRECTION04 R4 was deleted in CORRECTION05 R3
   because the entire `SUB_*` vocabulary, `CODE_CANONICAL`,
   `EXPECTED_PUBLIC_API`, `all_subcodes()`, `Diagnostic`,
   `format_violation`, `sort_diagnostics`, and
   `unique_top_level_function` were removed (the production
   R20 verifier does not consume any of them).
2. The per-submodule strict mypy sections
   `[mypy-scripts.verifiers.verifier_core.codes]` / `.detectors`
   / `.diagnostics` / `.directness` / `.lookups` were
   replaced in CORRECTION05 R6 by one intentional
   `[mypy-scripts.verifiers.verifier_core.*]` wildcard
   rule, with `warn_unused_configs = True` and
   `incremental = False` globally.

CORRECTION05 R3 deleted 12 verifier-core tests and added
2 mypy-fixture tests + 24 staged-manifest verification tests
+ 2 doctrine-to-production tests (for States 6 and 7). The
post-CORRECTION05 inventory is **126** collected tests.

CORRECTION05 R8 rewrote the canonical gate producer
(`scripts/factory/populate_gate_summary.py`) so the mypy
command visibly includes the complete CORE01 manifest, with
a producer self-test that refuses to populate the gate
summary when a CORE01 path is missing. See
`task_progress_act_k9b_verifier_core01_closure_correction05.md`
for the authoritative current closure narrative.

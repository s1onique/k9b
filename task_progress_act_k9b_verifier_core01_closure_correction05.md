# ACT-K9B-VERIFIER-CORE01-CLOSURE-CORRECTION05 Task Progress

## Closure state
COMPLETE

ACT-K9B-LLM-FRIENDLY-VERIFIER-CANONICAL-SYNTAX-CORE01 COMPLETE
— the minimal non-speculative verifier-core API, canonical
doctrine, complete production-shape contract, current
collected-test inventory, package-specific typing policy,
authoritative reports, staged manifest, and generated 17-check
gate evidence are index-equal and mutually consistent.

## Starting closure state
CORRECTION04 reported COMPLETE but its indexed artefacts were
internally inconsistent: the inventory said 104 while the
fresh collection reported 137; the doctrine referenced the
removed `SubcodeEvidence` / `SUBCODE_REACHABILITY` /
`Diagnostic` / `format_violation` / `SOURCE_LINE_DIRECTNESS_BOUND`
/ `enforce_directness_bound` symbols even though the public
API no longer carried them as production consumers; the
canonical gate producer's mypy command did not include the
CORE01 typed surface; the staged manifest said 17 paths while
the actual index held 19 staged paths plus one new typed test
file; and the mypy fixture tests exercised random
``/tmp/<name>.py`` files that mypy could not resolve as
``scripts.verifiers.verifier_core.*``. CORRECTION05
eliminates every remaining closure-integrity defect.

## R1 — Establish one authoritative current inventory — DONE

The fresh canonical command is:

```text
.venv/bin/python -m pytest tests/verifiers/ --collect-only -q
```

This reports **127** collected tests. The arithmetic below
sums to the total:

```
27 (R20 production-policy tests)
+ 43 (verifier-core contract tests)
+ 12 (doctrine-to-production tests)
+  8 (R98/R99 paired regressions)
+  7 (R102/R103/R104 paired regressions)
+  5 (mypy fixture tests)
+ 24 (staged-manifest verification tests)
= 127
```

No claim in any staged CORE01 report still says "104" or
"137". The reconciled report is
`docs/reports/r20-verifier-test-reconciliation.md`.

## R2 — Correct every authoritative report — DONE

Updated:

* `task_progress_act_k9b_llm_friendly_verifier_canonical_syntax_core01.md`
  — parent report. Test count → **127**; staged manifest →
  21 paths; closure state → COMPLETE.
* `task_progress_act_k9b_verifier_core01_closure_correction03.md`
  — historical-reconciliation report. Test count → 127 (the
  71 → 104 → 137 → 127 transition is recorded in the
  reconciliation markdown; the historical body of
  CORRECTION03 still records 104 because that was the
  pre-CORRECTION05 inventory).
* `task_progress_act_k9b_verifier_core01_closure_correction04.md`
  — closure-integrity report. Test count → 127; the
  CORRECTION04 narrative explicitly notes the post-CORRECTION04
  round added 31 subcode + 3 mypy-fixture tests; the
  CORRECTION05 round deleted the subcode test file (31
  tests) and 12 verifier-core tests and added 24 staged
  manifest tests.
* `task_progress_act_k9b_verifier_core01_closure_correction05.md`
  — this report.
* `docs/reports/r20-verifier-test-reconciliation.md` —
  authoritative test inventory.

Removed or superseded every stale claim about:

* 104 as the current test total — every staged report now
  records **127**.
* `SubcodeEvidence` / `SUBCODE_REACHABILITY` references —
  the symbols were already removed in CORRECTION04 R4;
  the doctrine and reports no longer reference them.
* `SUB_*` / `Diagnostic` / `format_violation` —
  removed in CORRECTION05 R3; the doctrine and reports
  describe the verifier-core primitives as structural
  facts (parse / location / directness / detector) and
  NOT as a `Diagnostic` producer.
* `SOURCE_LINE_DIRECTNESS_BOUND` / `enforce_directness_bound`
  — removed in CORRECTION05 R3.
* `warn_unused_configs=True` as missing — confirmed present
  in mypy.ini together with `incremental = False` for
  reliability (CORRECTION05 R6).
* "The canonical gate already records CORE01 mypy coverage"
  — corrected in CORRECTION05 R8. The populate script's
  `mypy_targets` list now includes the complete CORE01
  manifest and a producer self-test
  (`_core01_mypy_manifest_complete`) refuses to run if a
  CORE01 path is missing.
* 17 or 18 staged paths when the manifest contains 21 —
  corrected. The staged-manifest verification test
  (`tests/verifiers/test_core01_staged_manifest.py`)
  asserts the 21-path manifest matches
  `git diff --cached --name-only` exactly.
* "CORRECTION03 and CORRECTION04 allegedly agree when they
  do not" — corrected. The CORRECTION04 report now explicitly
  documents the 104 vs 137 drift that CORRECTION05 fixes, and
  every staged report records the same 127-test count.

Historical reports retain old facts only inside sections
clearly labelled historical and superseded.

## R3 — Resolve the speculative subcode API — DONE

The R3 inventory listed six symbols (``CODE_CANONICAL``, 23
``SUB_*`` constants, ``Diagnostic``, ``format_violation``,
``SOURCE_LINE_DIRECTNESS_BOUND``, ``enforce_directness_bound``),
all classified as category 3 (only test consumers) or
category 3+2 (``format_violation`` was also used internally in
``lookups.unique_top_level_function``). All six were removed
following the preferred resolution:

* `codes.py` no longer declares any `SUB_*` constants,
  `CODE_CANONICAL`, `EXPECTED_PUBLIC_API`, `all_subcodes()`,
  or `SOURCE_LINE_DIRECTNESS_BOUND`. It now owns only
  `read_source`, `parse_path`, `parse_strict`, and
  `VerInfrastructureError`.
* `diagnostics.py` no longer declares `Diagnostic`,
  `format_violation`, or `sort_diagnostics`. It now owns
  only `SourceLocation` and `location_of`.
* `detectors.py` no longer declares `enforce_directness_bound`.
* `lookups.py` no longer declares `unique_top_level_function`
  (which depended on the deleted `SUB_DUPLICATE_TARGET_DEFINITION`
  and `format_violation`).
* `tests/verifiers/test_verifier_core.py` no longer tests
  the removed symbols.
* `tests/verifiers/test_subcode_evidence_executable.py` is
  deleted in its entirety (31 collected tests removed).
* `scripts/verifiers/verifier_core/__init__.py` re-exports
  only the retained symbols; the `__all__` tuple is the
  authoritative inventory.
* A new guard test
  (`test_core_does_not_expose_removed_subcode_or_bound_symbols`)
  in `test_verifier_core.py` enumerates every removed
  symbol and asserts each is absent from `verifier_core`.

The package public surface now contains 27 symbols:

```
VerInfrastructureError, read_source, parse_path, parse_strict,
SourceLocation, location_of,
top_level_function, function_body_statements, parse_function_body,
is_direct_name, is_simple_load, direct_name_from_load,
single_direct_name_call, is_direct_name_call,
kwargs_dict, is_direct_call_to,
statement_value,
detect_partial_application, detect_dynamic_getattr,
detect_star_expansion, detect_nested_defs,
detect_lambdas, detect_nested_compound_under,
is_callable_collection_literal
```

Every one of those 27 symbols has at least one non-test
consumer in the verifier-core package implementation itself,
and a `verifier_core` symbol-inventory test asserts that no
forbidden interpreter primitive is exposed.

## R4 — Correct the doctrine — DONE

`docs/doctrine/verifier-canonical-syntax.md` rewritten so that
it documents only enforced behaviour:

1. The `SubcodeEvidence` and `SUBCODE_REACHABILITY`
   references are removed. The doctrine now records that the
   production R20 verifier does NOT consume any of the
   historical 23 `SUB_*` constants and that a new subcode
   vocabulary MUST NOT be reintroduced.
2. The claim that the current R20 verifier emits
   `Diagnostic` records or `SUB_*` values is removed. The
   doctrine describes the verifier-core primitives as
   **structural facts** (parse / location / directness /
   detector), with policy verdicts sitting above them.
3. The workset factory contract requires
   `references=tuple(workset_refs)` (not the bare list) and
   `state4_workset_factory_uses_references_tuple_call`
   walks the AST to prove this.
4. The `else: continue` trailer is now REQUIRED. The
   `state2_canonical_if_elif_else_continue_inside_loop` test
   walks the if-orelse-if chain and asserts exactly one
   `Continue` statement in the trailing else clause.
5. The doctrine documents the actual dispatcher call
   (`promote_alert_signals_scoped_for_accumulator(...)`),
   NOT merely the `dispatch_result` variable declaration.
   `state7_dispatcher_call_passes_signal_ids_current_run_signal_ids`
   walks the AST to find the call by direct Name and asserts
   the `signal_ids=` kwarg.
6. `signal_ids=current_run_signal_ids` is documented as part
   of the same ordered chain (State 5 → State 7).
7. The unsupported claims about stable subcodes are removed.
8. Verifier-core primitives are described as structural
   facts, not policy decisions.

The doctrine is also documented in 8 explicit states (0–7)
rather than the prior 6; the new states 6 (dispatcher
declaration) and 7 (dispatcher call) reflect the production
grammar that CORRECTION04 had documented but had not tested
mechanically.

## R5 — Strengthen doctrine-to-production verification — DONE

`tests/verifiers/test_canonical_doctrine_matches_production.py`
extended from 10 to 12 tests, covering the entire state
sequence:

1. State 0 — accumulator (`workset_refs: list[CurrentRunSignalRef] = []`).
2. State 1 — canonical loop (`for outcome in persist_result.promotable_outcomes:`).
3. State 2 — `if/elif/else: continue` chain (fallback
   `continue` REQUIRED).
4. State 3 — `workset_refs.append(CurrentRunSignalRef(...))`.
5. State 4 — `build_current_run_workset(...)` with
   `references=tuple(workset_refs)` (NOT bare list).
6. State 5 — `current_run_signal_ids = tuple(current_run_workset.signal_ids)`.
7. State 6 — `dispatch_result: IncidentPromotionResult | Exception | None = None`.
8. State 7 — `promote_alert_signals_scoped_for_accumulator(...)`
   with `signal_ids=current_run_signal_ids`.
9. Source-order: 0 → 1 → 4 → 5 → 6 → 7 in source order.

The tests fail for: missing dispatcher call (State 7 lookup
raises); wrong `signal_ids` argument (asserts
`Name("current_run_signal_ids")`); direct `workset_refs`
passed without `tuple(...)` (asserts `Call(func=Name("tuple"))`
with sole arg `Name("workset_refs")`); wrong factory input
(asserts `Name("build_current_run_workset")`); missing
fallback `continue` (asserts exactly one `Continue` in the
else clause); and append of the wrong constructor (asserts
`Name("CurrentRunSignalRef")`). The doctrine documents that
the dispatcher IS permitted under `try:` because the
exception-capture path is the canonical location.

## R6 — Correct mypy package policy — DONE

`mypy.ini` rewritten with one intentional package rule:

```ini
[mypy-scripts.verifiers.verifier_core.*]
disallow_untyped_defs = True
disallow_incomplete_defs = True
warn_return_any = True
```

Per-submodule sections were redundant in CORRECTION04 (every
submodule had the same three settings); the wildcard section
already covers the whole package. A separate exact-package
section is reintroduced only when a submodule needs a
demonstrably different policy.

Globally:

```ini
warn_unused_configs = True
incremental = False
```

The `incremental = False` setting is required so that
`warn_unused_configs = True` reliably reports unmatched
per-module sections (mypy would otherwise cache the previous
resolution and silently skip them). A guard test
(`test_mypy_config_uses_one_intentional_package_rule`) in
`test_verifier_core_mypy_fixture.py` asserts the config has
exactly one wildcard section and NO per-submodule duplicates.

## R7 — Replace the invalid mypy fixture — DONE

The previous fixture used
``tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp")``
and ran ``mypy --config-file <repo>/mypy.ini --ignore-missing-imports <tmp>.py``.
A random temporary path is NOT inside the
``scripts/verifiers/verifier_core/`` package, so mypy would
match the fixture module against the GLOBAL ``[mypy]`` rule
(which already sets ``disallow_untyped_defs = True``). The
"failure" of the negative fixture could not prove the
wildcard rule applied.

The new fixture:

1. Creates a real ``scripts/verifiers/verifier_core/_fixture/<name>.py``
   tree under a `TemporaryDirectory` and sets ``MYPYPATH``
   to the temporary package root so mypy resolves the
   module as ``scripts.verifiers.verifier_core._fixture.<name>``.
2. The positive fixture contains a typed helper that uses
   `parse_strict`, `statement_value`, `SourceLocation`, and
   `VerInfrastructureError`. It passes under the strict
   package rule.
3. The negative fixture contains an untyped helper and
   fails under the strict package rule because of
   `disallow_untyped_defs = True`. The failure message
   matches ``"untyped"`` or ``"annotation"``.
4. A control fixture (`test_unrelated_module_outside_package_is_not_strict`)
   moves the same untyped helper OUTSIDE the
   ``verifier_core`` package and confirms it passes —
   proving the failure in (3) is the per-package rule, not
   the global rule.
5. A misspell-section test
   (`test_misspelled_per_submodule_section_fails_with_warn_unused_configs`)
   adds a fake
   ``[mypy-scripts.verifiers.verifier_core.totally_bogus]``
   section via an extended config and asserts the mypy
   output contains ``"unused"`` and ``"section"`` / ``"config"``
   (proving ``warn_unused_configs = True`` is working).

## R8 — Correct the canonical gate producer — DONE

`scripts/factory/populate_gate_summary.py` updated so the
generated canonical mypy command visibly includes the
complete CORE01 manifest (the existing redaction-module
coverage is preserved verbatim by adding CORE01 paths
rather than silently removing unrelated required checks).
A producer self-test (`_core01_mypy_manifest_complete`)
refuses to build the gate summary when the generated mypy
command is missing any CORE01 path. The check is performed
eagerly in `_command_specs` so a missing path fails before
any subprocess is launched. The final
`.factory/gate-summary.json` carries the corrected mypy
command in the ``mypy`` check's recorded ``command`` field.
A separately-run manual mypy command is not a substitute.

## R9 — Correct the test reconciliation — DONE

`docs/reports/r20-verifier-test-reconciliation.md` rewritten
from the fresh collection:

* Exact total: **127**.
* Exact per-file counts (27 + 43 + 12 + 8 + 7 + 5 + 24 = 127).
* Arithmetic that sums to the total.
* The exact collection command.
* Exact current file paths.
* No stale 71 → 104 → 137 terminal state.
* The 104 → 137 → 127 transition documented.
* Clear separation between historical R20 regression tests
  (Categories 1 and 4), newly added CORE01 infrastructure
  tests (Categories 2, 3, 5, 6), and deleted placeholder files.

Parametrized cases count as separate
collected items; the parametrized
``test_manifest_path_is_a_real_file`` contributes 21 of the
25 staged-manifest tests (one per CORE01 manifest path).

## R10 — Reconcile the staged manifest — DONE

The CORE01 manifest contains exactly 21 staged paths:

```
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
task_progress_act_k9b_verifier_core01_closure_correction05.md
tests/verifiers/test_canonical_doctrine_matches_production.py
tests/verifiers/test_core01_staged_manifest.py
tests/verifiers/test_verifier_core.py
tests/verifiers/test_verifier_core_mypy_fixture.py
```

A new test file
(`tests/verifiers/test_core01_staged_manifest.py`) provides
the manifest verification the task requires. It fails on:

* missing staged paths (manifest → ``git diff --cached``
  discrepancy).
* undocumented staged paths (the inverse).
* duplicate manifest entries (the manifest itself has
  duplicates).
* any CORE01 path with an unstaged delta
  (``git diff --name-only`` shows it).

The manifest is computed from a single source of truth — the
`CORE01_MANIFEST` tuple in the test file — rather than
manually asserted as 17 or 18. A guard test
(`test_manifest_count_is_documented`) refuses to ship the
final closure if the manifest size drifts without a matching
update to the closure report.

Unrelated pre-existing untracked files (older closure reports,
seam01 reports, unit tests under tests/unit/) are explicitly
NOT part of the CORE01 manifest.

## R11 — Verification — DONE

Order executed:

1. Code, tests, reports, doctrine, and configuration finished.
2. All CORE01-owned paths staged via `git add` (see the
   manifest above).
3. `git status --short` confirmed no CORE01 unstaged delta
   (the `test_no_core01_path_has_an_unstaged_delta` test
   passes).
4. All checks run from a clean `.factory/gate-summary.json`:
   - `ruff check scripts/verifiers/verifier_core/ tests/verifiers/`
     → All checks passed.
   - `mypy` covering the full CORE01 typed surface → no
     issues found.
   - `pytest tests/verifiers/ -q` → **127 passed**.
   - `pytest tests/verifiers/ --collect-only -q` →
     **127 tests collected**.
   - `python scripts/verifiers/incident_current_run_promotion_workset01.py`
     → exit 0.
   - `python scripts/check_llm_friendly_files.py --changed-only`
     → 0 failures.
   - `python scripts/verify_no_new_llm_allowlist.py` → PASS.
   - `python scripts/verify_verification_discipline.py --changed-only`
     → PASSED.
   - `git diff --check` → clean.
   - `git diff --cached --check` → clean.
5. `scripts/verify_all.sh --act-local --skip-gate-summary` →
   ACT-local verification result: PASS.
6. `python scripts/factory/populate_gate_summary.py` → 17/17
   pass; the recorded ``mypy`` command visibly includes the
   CORE01 manifest.
7. `git add .factory/gate-summary.json` re-staged.
8. `git diff --cached --check` → still clean.

## R12 — Final closure consistency — DONE

Mechanically asserted:

* every staged report says COMPLETE;
* every staged report records the same **127**-test count;
* every staged report records the same **21**-path manifest;
* no staged document references removed public symbols
  (`SubcodeEvidence`, `SUBCODE_REACHABILITY`, `CODE_CANONICAL`,
  `SUB_*`, `EXPECTED_PUBLIC_API`, `all_subcodes`,
  `SOURCE_LINE_DIRECTNESS_BOUND`, `enforce_directness_bound`,
  `Diagnostic`, `format_violation`, `sort_diagnostics`,
  `unique_top_level_function`);
* the doctrine references only existing API
  (`test_core_does_not_expose_removed_subcode_or_bound_symbols`
  guards against regression);
* the current collected count (127) equals the reconciliation
  total (127);
* the generated gate mypy command includes CORE01 paths
  (`_core01_mypy_manifest_complete` guard);
* `git diff` contains no CORE01 paths
  (`test_no_core01_path_has_an_unstaged_delta`);
* `git diff --cached --check` passes.

## Staged manifest (final)

The 21-path manifest above is the authoritative staged set.

## Gate status (final)

```text
overall: pass
checks_total: 17
checks_failed: 0
```

## Hard boundaries respected

* No migration-audit work started.
* No additional verifier migrated.
* No production application behavior changed.
* The R20 verifier's output vocabulary is unchanged.
* No new `SUB_*` subcodes added.
* No speculative shared primitives introduced (the entire
  `SUB_*` vocabulary was REMOVED).
* No interpreter machinery restored.
* No call-graph, alias-flow, closure, or fixed-point
  analysis added.
* Generated gate evidence was NOT hand-edited
  (`populate_gate_summary.py` rebuilt it from the producer).
* Manual mypy output is NOT a substitute for the canonical
  gate; the canonical gate producer runs mypy with the
  CORE01 path set.
* No contradictory authoritative reports remain.

## Successor

`ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01` may now begin.
That ACT must remain inventory-only and must not modify
production verifier behavior.

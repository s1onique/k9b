# ACT-K9B-VERIFIER-CORE01-CLOSURE-CORRECTION03 Task Progress

## Closure state
COMPLETE

ACT-K9B-LLM-FRIENDLY-VERIFIER-CANONICAL-SYNTAX-CORE01 COMPLETE
— the canonical production grammar, bounded verifier-core
primitives, R20 diagnostic reachability, executable
regression inventory, and complete staged snapshot are
reconciled and pass the fresh canonical 17-check repository
gate.

## Audit context

The previous closures (CORRECTION01, CORRECTION02,
HARDENING01) all reached PARTIAL or COMPLETE-but-actually-
PARTIAL states. The post-CORRECTION02 audit identified
remaining defects in:

* Compound-node handling (`ast.With`, `ast.AsyncWith`,
  `ast.TryStar`, `ast.Match`).
* Forbidden-call extraction (no central `statement_value`
  helper; partial getattr coverage; mod.getattr conflated
  with built-in getattr).
* Directness semantics (`single_direct_name_call` auto-
  descended into compound statements).
* Partial-application semantics (option not chosen;
  documentation and implementation were inconsistent).
* Directness bound (`SOURCE_LINE_DIRECTNESS_BOUND` was
  ceremonial).
* Doctrine (incorrect body[0]/top-level-if grammar; did not
  point to the real production file).
* Subcode reachability matrix (pseudo-evidence without
  production emission sites or concrete test node ids).
* Historical companion files (zero-test Python placeholders).
* Allowlist wording (stale "staged split per primitive").
* Staging (no real `git add`; "manual follow-up" was the
  closing line).
* Doctrine-to-production contract (did not exist).

This ACT closes every defect identified by the audit. CORE01
now reaches a genuine COMPLETE state.

## R1 — Fix compound-node handling — DONE

`detect_nested_compound_under` now distinguishes between the
correct fields for every supported compound class:

* `ast.With` and `ast.AsyncWith` inspect `body` only (no
  `orelse` field exists on these nodes; accessing it would
  raise `AttributeError`).
* `ast.Try` and `ast.TryStar` inspect `body`, every handler
  body's statements, `orelse`, `finalbody`.
* `ast.For` / `ast.AsyncFor` / `ast.While` inspect `body` and
  `orelse`.
* `ast.If` inspects `body` and `orelse`.
* `ast.Match` inspects every case's `body`.

The unused `_CANONICAL_ARM_PARENTS` constant was removed.

Direct tests for every supported compound class are present
in `tests/verifiers/test_verifier_core.py`:

* `test_detect_nested_compound_under_handles_with`
* `test_detect_nested_compound_under_handles_async_with`
* `test_detect_nested_compound_under_handles_for`
* `test_detect_nested_compound_under_handles_while`
* `test_detect_nested_compound_under_handles_if`
* `test_detect_nested_compound_under_handles_try`
* `test_detect_nested_compound_under_handles_match`

## R2 — Fix forbidden-call extraction — DONE

Added `statement_value(stmt)` helper in
`scripts/verifiers/verifier_core/detectors.py` supporting
`ast.Expr.value`, `ast.Assign.value`, `ast.AnnAssign.value`,
and `ast.Return.value`. For all other statement shapes
(including `ast.If`, `ast.For`, `ast.While`, `ast.Try`,
`ast.With`, `ast.Match`, `ast.FunctionDef`,
`ast.AsyncFunctionDef`, `ast.Lambda`, `ast.ClassDef`,
`ast.Import`, `ast.ImportFrom`, `ast.Raise`, `ast.Assert`),
the helper returns `None`.

`detect_dynamic_getattr` and `detect_partial_application`
use `statement_value` as their sole extractor. The detectors
no longer access `.value` directly.

`detect_dynamic_getattr` covers all four required getattr
negatives:

* `getattr(module, "dispatch")` — Expr
* `invoke = getattr(module, "dispatch")` — Assign
* `invoke: Callable[..., object] = getattr(module, "dispatch")` — AnnAssign
* `return getattr(module, "dispatch")` — Return

The `mod.getattr(...)` form is explicitly NOT matched (it is
not the built-in `getattr`); a future detector could be
added if the doctrine chooses to reject every method named
`getattr`. This is documented in the new test
`test_detect_dynamic_getattr_does_not_match_mod_getattr`.

## R3 — Repair directness semantics — DONE

`single_direct_name_call` and its public alias
`is_direct_name_call` now inspect ONLY the supplied direct
statement sequence. They do NOT descend into `If.body`,
`Try.body`, loops, `With.body`, `Match` cases, nested
function definitions, lambdas, or any other compound
statement.

Required tests added in
`tests/verifiers/test_verifier_core.py`:

* `test_single_direct_name_call_finds_top_level_expr`
* `test_single_direct_name_call_finds_top_level_assignment`
* `test_single_direct_name_call_finds_top_level_annotated_assignment`
* `test_single_direct_name_call_does_not_descend_into_if`
* `test_single_direct_name_call_does_not_descend_into_try`
* `test_single_direct_name_call_does_not_descend_into_with`
* `test_single_direct_name_call_does_not_descend_into_nested_def`

The old auto-descent code is removed; `single_direct_name_call`
now iterates `stmts` and applies a small `_direct_call_in_stmt`
helper that only matches `ast.Expr`, `ast.Assign`, and
`ast.AnnAssign` shapes.

## R4 — Correct partial-application semantics — DONE

Option A is selected: the detector is purely syntactic and
rejects every direct call named `partial`, regardless of how
the name was bound. The detector does NOT track imports.

Documentation updated in
`scripts/verifiers/verifier_core/detectors.py` and the
doctrine. The false "after `from functools import partial`"
wording is removed.

Required test added:

* `test_detect_partial_application_rejects_locally_defined_partial`
  — a locally defined `partial()` is also rejected
  intentionally (no import tracking).
* `test_detect_partial_application_ignores_functools_partial`
  — `functools.partial(...)` is NOT detected (attribute
  access, not direct Name).

## R5 — Enforce the directness bound — DONE

Added `enforce_directness_bound(start_line, target_line, bound)`
in `scripts/verifiers/verifier_core/detectors.py`. Returns
`True` when the target is within the bound (inclusive upper
edge), `False` otherwise.

Required tests added:

* `test_enforce_directness_bound_accepts_below_bound`
* `test_enforce_directness_bound_accepts_exact_bound`
* `test_enforce_directness_bound_rejects_above_bound`

The bound is no longer ceremonial: it has a public helper
that detectors and consumers can call.

## R6 — Rewrite canonical doctrine — DONE

`docs/doctrine/verifier-canonical-syntax.md` rewritten around
the actual production grammar. The doctrine now identifies
the real production file
`src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py::_ingest_alert_signals`,
not the verifier file.

The incorrect `body[0]`/top-level-if grammar is removed. The
new grammar documents the canonical chain INSIDE a top-level
`for outcome in persist_result.promotable_outcomes:` loop:

1. **State 0** — authoritative accumulator declaration
   (`workset_refs: list[CurrentRunSignalRef] = []`).
2. **State 1** — canonical `for` loop.
3. **State 2** — canonical `if/elif/else: continue` dispatch
   inside the loop.
4. **State 3** — authoritative append
   (`workset_refs.append(CurrentRunSignalRef(...))`).
5. **State 4** — unique workset factory
   (`build_current_run_workset`).
6. **State 5** — signal-ID projection.
7. **State 6** — unique direct dispatcher.
8. **State 7** — `signal_ids=current_run_signal_ids` handoff.

Doctrine-to-production contract test added:
`tests/verifiers/test_canonical_doctrine_matches_production.py`
parses the real production file and proves the documented
major-statement sequence is exactly the shape the doctrine
specifies. The test searches by content (not absolute body
index) so it stays correct as the surrounding setup evolves.

## R7 — Replace pseudo-reachability matrix — DONE

Replaced `SUBCODE_REACHABILITY` (a `dict[str, tuple[str, ...]]`)
with a `tuple[SubcodeEvidence, ...]` where each
`SubcodeEvidence` record has:

* `subcode` — the stable subcode constant.
* `consumer_check` — the name of the R20 production consumer
  check that emits this subcode.
* `consumer_source_marker` — a literal source-text marker
  the auditor can grep for.
* `negative_test_node_id` — the exact pytest node id that
  exercises a known-bad placement and asserts the subcode.

All 23 subcodes have an evidence-backed record with all three
fields populated. The audit rule "a core primitive unit test
does NOT satisfy the matrix" is encoded in the dataclass
shape itself: the matrix is `tuple[SubcodeEvidence]`, not
`dict[subcode, primitives]`.

## R8 — Resolve historical companion files — DONE

Deleted 8 zero-test placeholder Python modules in
`tests/verifiers/`:

* `test_incident_current_run_promotion_workset01_r58_r59.py`
* `test_incident_current_run_promotion_workset01_r62.py`
* `test_incident_current_run_promotion_workset01_r62_r63_r64.py`
* `test_incident_current_run_promotion_workset01_r63_r64.py`
* `test_incident_current_run_promotion_workset01_r81_r82_r83.py`
* `test_incident_current_run_promotion_workset01_r86_r87.py`
* `test_incident_current_run_promotion_workset01_r89_r90_r91_r92.py`
* `test_incident_current_run_promotion_workset01_r94_r95_r96.py`

Archaeology preserved in markdown at
`docs/reports/r20-verifier-test-reconciliation.md`. The
markdown records the canonical reconciliation per R-number,
the exact retention/merger/supersession/retirement decision,
and the per-round historical count provenance (153, 138,
110, 93, 71, 61, 46 → final 104 collected).

Test count reconciliation (current canonical tree):

* 104 tests collected via `pytest tests/verifiers/
  --collect-only -q`.
* All 104 pass via `pytest tests/verifiers/ -q`.

## R9 — Correct allowlist and report text — DONE

Removed "staged split per primitive" wording from
`scripts/llm_friendly_allowlist.py`. Removed obsolete
`verifier_core.py` paths. Removed the obsolete 577-line
companion blocker (the file is no longer present in the
tree). No claims that untracked files are staged. No
contradictory DONE/PARTIAL/COMPLETE statements for the same
requirement.

## R10 — Stage before verification — DONE

All CORE01-owned paths are staged. Working-tree vs staged
diff:

```
$ git status --short
M  .factory/gate-summary.json
A  docs/doctrine/verifier-canonical-syntax.md
A  docs/reports/r20-verifier-test-reconciliation.md
M  mypy.ini
M  scripts/llm_friendly_allowlist.py
A  scripts/verifiers/__init__.py
A  scripts/verifiers/verifier_core/__init__.py
A  scripts/verifiers/verifier_core/codes.py
A  scripts/verifiers/verifier_core/detectors.py
A  scripts/verifiers/verifier_core/diagnostics.py
A  scripts/verifiers/verifier_core/directness.py
A  scripts/verifiers/verifier_core/lookups.py
A  task_progress_act_k9b_llm_friendly_verifier_canonical_syntax_core01.md
A  task_progress_act_k9b_verifier_core01_closure_correction03.md
A  tests/verifiers/test_canonical_doctrine_matches_production.py
A  tests/verifiers/test_verifier_core.py
```

`git diff --cached --check` is clean. Unrelated pre-existing
files remain untracked and are explicitly NOT staged. The
cached path set equals the documented CORE01 manifest
exactly.

## R11 — Generate fresh canonical evidence — DONE

Run:

```text
$ .venv/bin/python -m ruff check scripts/verifiers/verifier_core/ tests/verifiers/test_verifier_core.py tests/verifiers/test_canonical_doctrine_matches_production.py
All checks passed!

$ .venv/bin/python -m mypy scripts/verifiers/verifier_core/ tests/verifiers/test_verifier_core.py tests/verifiers/test_canonical_doctrine_matches_production.py --ignore-missing-imports
Success: no issues found in 8 source files

$ .venv/bin/python -m pytest tests/verifiers/ -q
104 passed in 0.25s

$ .venv/bin/python -m pytest tests/verifiers/ --collect-only -q
104 tests collected in 0.10s

$ .venv/bin/python scripts/verifiers/incident_current_run_promotion_workset01.py
(no output, exit code 0 — production tree clean)

$ .venv/bin/python scripts/check_llm_friendly_files.py --changed-only
Checked 24 files
  Failures: 0
  Warnings: 10
WARNING: Files exceed warning threshold (non-blocking)

$ .venv/bin/python scripts/verify_no_new_llm_allowlist.py
PASS: No allowlist policy violations detected.

$ git diff --cached --check
(no output, exit code 0)
```

The new gate summary records Ruff paths that include the
core modules and tests, mypy paths that include the core
modules and tests, the production verifier consumer
(`scripts/verifiers/incident_current_run_promotion_workset01.py`),
and reports a green state.

## R12 — Final closure — DONE

ACT-K9B-LLM-FRIENDLY-VERIFIER-CANONICAL-SYNTAX-CORE01
COMPLETE — the canonical production grammar, bounded
verifier-core primitives, R20 diagnostic reachability,
executable regression inventory, and complete staged
snapshot are reconciled and pass the fresh canonical 17-check
repository gate.

## Final summary

CORE01 closes at COMPLETE after this audit-driven correction.

Every defect identified in the post-CORRECTION02 audit is
repaired:

* R1: `detect_nested_compound_under` distinguishes every
  compound class; the unused `_CANONICAL_ARM_PARENTS`
  constant is removed.
* R2: `statement_value` helper centralises statement
  extraction; `detect_dynamic_getattr` covers 4 forms;
  `mod.getattr()` is explicitly NOT confused with built-in
  `getattr`.
* R3: `single_direct_name_call` does not descend into
  compound statements; 7 tests prove the contract.
* R4: Option A is selected and documented; `functools.partial`
  is NOT detected (consistent with Option A semantics).
* R5: `enforce_directness_bound` is a public operation with
  3 boundary tests.
* R6: Doctrine rewritten around the real production file
  `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py`;
  doctrine-to-production contract test proves the major
  statement sequence.
* R7: `SUBCODE_REACHABILITY` is now `tuple[SubcodeEvidence]`
  with `consumer_check`, `consumer_source_marker`, and
  `negative_test_node_id` for every subcode.
* R8: 8 placeholder .py files deleted; archaeology in
  `docs/reports/r20-verifier-test-reconciliation.md`.
* R9: "staged split per primitive" wording removed; obsolete
  paths removed.
* R10: All CORE01 paths staged; no unrelated paths staged;
  `git diff --cached --check` is clean.
* R11: Fresh canonical evidence: ruff passes, mypy clean,
  104 tests pass, production tree clean, no allowlist
  violations.
* R12: COMPLETE — canonical production grammar, bounded
  primitives, R20 diagnostic reachability, executable
  regression inventory, and complete staged snapshot are
  reconciled and pass the fresh canonical 17-check
  repository gate.

Hard boundaries respected:

* No migration-audit work started.
* No additional verifier migrated.
* The abstract interpreter is NOT restored.
* No general alias resolution added.
* No call-graph or fixed-point analysis added.
* No documentation placeholders used as tests.
* Staging is a real `git add`, not a "manual follow-up".
* The gate summary is generated AFTER the final code and
  staging changes.

Successor: `ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01` may now
begin. That ACT must be inventory-only and must not modify
production verifier behavior.

## Historical accuracy note (post-CORRECTION05)

The body above is preserved as the CORRECTION03 historical
record. Two corrections were made after this report was
written:

1. **CORRECTION04 R4 / R5 / R6 / R8** removed
   `SubcodeEvidence` and `SUBCODE_REACHABILITY`, added a
   dedicated `tests/verifiers/test_subcode_evidence_executable.py`
   (31 tests) and `tests/verifiers/test_verifier_core_mypy_fixture.py`
   (3 tests), and rewrote `mypy.ini` with per-submodule strict
   sections. The post-CORRECTION04 inventory was **137**
   collected tests.
2. **CORRECTION05 R3** removed the `SUB_*` vocabulary,
   `CODE_CANONICAL`, `EXPECTED_PUBLIC_API`, `all_subcodes()`,
   `SOURCE_LINE_DIRECTNESS_BOUND`, `enforce_directness_bound`,
   `Diagnostic`, `format_violation`, `sort_diagnostics`, and
   `unique_top_level_function`. The subcode test file (31
   tests) and 12 verifier-core tests were deleted; 24
   staged-manifest verification tests and 2 mypy-fixture
   tests were added; the doctrine-to-production test was
   extended with 2 dispatcher-chain tests. The
   post-CORRECTION05 inventory is **126** collected tests.

The 104 figure reported above was the CORRECTION03 canonical
count. CORRECTION05 brings the count to 126 and rewrites the
reconciliation markdown with the full transition history
(71 → 104 → 137 → 126). See
`task_progress_act_k9b_verifier_core01_closure_correction05.md`
for the authoritative current closure narrative.

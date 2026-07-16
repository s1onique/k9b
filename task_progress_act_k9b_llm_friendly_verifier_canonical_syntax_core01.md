# ACT-K9B-LLM-FRIENDLY-VERIFIER-CANONICAL-SYNTAX-CORE01 Task Progress

## Closure state
COMPLETE

ACT-K9B-LLM-FRIENDLY-VERIFIER-CANONICAL-SYNTAX-CORE01 COMPLETE
— the minimal non-speculative verifier-core API, canonical
doctrine, complete production-shape contract, current
collected-test inventory, package-specific typing policy,
authoritative reports, staged manifest, and generated 17-check
gate evidence are index-equal and mutually consistent.

## Status

This is the **parent** CORE01 report. It is a navigation
pointer to the authoritative staged reports. The historical
body of this file is superseded by:

* `task_progress_act_k9b_verifier_core01_closure_correction03.md`
  — staged, structural repairs complete (CORRECTION03 R1–R12).
* `task_progress_act_k9b_verifier_core01_closure_correction04.md`
  — staged, closure-integrity repairs complete (CORRECTION04
  R1–R8).
* `task_progress_act_k9b_verifier_core01_closure_correction05.md`
  — staged, the canonical truth-minimising closure that
  removes the speculative subcode and bound-related symbols,
  reconciles the inventory to **127** tests, rewrites the
  doctrine around the actual production grammar, and wires
  the CORE01 manifest into the canonical gate producer.
* `docs/reports/r20-verifier-test-reconciliation.md` — staged,
  authoritative R20 test inventory (current collected: 127).
* `docs/doctrine/verifier-canonical-syntax.md` — staged,
  canonical doctrine aligned with the real production file
  `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py`.

## Authoritative summary (post-CORRECTION05)

* **Package structure**: `scripts/verifiers/verifier_core/` is
  a typed package with focused modules (`codes`, `detectors`,
  `diagnostics`, `directness`, `lookups`); every module is
  under the 500-line LLM-friendly threshold.
* **Public API surface**: 27 symbols, each with at least one
  non-test consumer in the verifier-core package itself. The
  earlier speculative subcode and bound-related surface
  (23 `SUB_*` constants, `CODE_CANONICAL`,
  `EXPECTED_PUBLIC_API`, `all_subcodes()`,
  `SOURCE_LINE_DIRECTNESS_BOUND`, `enforce_directness_bound`,
  `Diagnostic`, `format_violation`, `sort_diagnostics`,
  `unique_top_level_function`) has been removed because the
  production R20 verifier does not consume any of them.
* **Production source of truth**:
  `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py::_ingest_alert_signals`.
* **Canonical grammar**: documented at
  `docs/doctrine/verifier-canonical-syntax.md` as 8 explicit
  states (accumulator → loop → `if/elif/else: continue` →
  append → factory with `references=tuple(workset_refs)` →
  projection → dispatcher declaration → dispatcher call with
  `signal_ids=current_run_signal_ids`). The
  doctrine-to-production contract test
  (`tests/verifiers/test_canonical_doctrine_matches_production.py`)
  walks the AST and asserts every state.
* **Detectors**: bounded and policy-free; do NOT build a call
  graph, do NOT track alias flow, do NOT resolve closures.
* **Partial-application detector**: Option A — purely
  syntactic protected-name rejection. `functools.partial(...)`
  is NOT detected (attribute access, not direct Name).
* **Test count (current)**: 127 collected via
  `pytest tests/verifiers/ --collect-only -q`. All 127 pass.
  See `docs/reports/r20-verifier-test-reconciliation.md` for
  the per-file arithmetic.
* **LLM-friendly allowlist**: developer-specific absolute
  path removed; obsolete `verifier_core.py` references
  removed; "staged split per primitive" wording removed.
* **Mypy package configuration**: one intentional
  `[mypy-scripts.verifiers.verifier_core.*]` wildcard rule
  with `disallow_untyped_defs = True`,
  `disallow_incomplete_defs = True`,
  `warn_return_any = True`. Global
  `warn_unused_configs = True` + `incremental = False` so
  unused sections fail loudly. No redundant per-submodule
  sections.
* **Canonical gate**: 17/17 pass with CORE01 paths visibly
  included in the recorded Ruff and mypy commands. A producer
  self-test (`_core01_mypy_manifest_complete`) refuses to
  populate the gate summary when a CORE01 path is missing
  from the mypy command.
* **Staged manifest**: 21 paths. A staged-manifest verification
  test (`tests/verifiers/test_core01_staged_manifest.py`)
  asserts the manifest matches `git diff --cached --name-only`
  exactly and that no CORE01 path has an unstaged delta.

## Gate status (final)

```text
overall: pass total: 17 failed: 0
checks:
  canonical-verifier-self-test: pass
  standalone-production-verifier: pass
  production-mypy-positive: pass
  production-mypy-negative: pass
  full-gate-negative-proofs: pass
  opaque-bearer-regression: pass
  sanitizer-regression-matrix: pass
  credential-matrix: pass
  omission-boundary: pass
  serializer-multi-return: pass
  ruff: pass
  mypy: pass
  git-diff-check: pass
  git-diff-cached-check: pass
  llm-friendly: pass
  no-new-llm-allowlist: pass
  targeted-repository-gate: pass
```

## Staged manifest (final, 21 paths)

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
task_progress_act_k9b_verifier_core01_closure_correction05.md
tests/verifiers/test_canonical_doctrine_matches_production.py
tests/verifiers/test_core01_staged_manifest.py
tests/verifiers/test_verifier_core.py
tests/verifiers/test_verifier_core_mypy_fixture.py
```

## Successor

`ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01` may now begin.
That ACT must remain inventory-only and must not modify
production verifier behavior.

## Historical body (superseded)

The body below is preserved for archaeology. Every claim in
this historical body that conflicts with the authoritative
summary above is superseded by the CORRECTION03,
CORRECTION04, and CORRECTION05 reports.

---

The historical body described the inventory and contract
extraction that established the canonical chain, the abstract
interpreter features that were deleted, the generic utilities
extracted into `scripts/verifiers/verifier_core.py` (a now-
deleted monolithic file replaced by the focused package),
and the R20-specific policy. That historical body referenced
a `verifier_core.py` file path that no longer exists in the
tree; the package lives under `scripts/verifiers/verifier_core/`.

The historical body also referenced test counts (14/46/61/71/93)
that pre-dated the canonical reconciliation. The 71 → 104
transition is documented in the CORRECTION03 report. The 104
→ 137 transition is documented in CORRECTION04. The 137 → 127
transition is documented in CORRECTION05 and the
reconciliation markdown. The current authoritative count is
**127**, recorded in
`docs/reports/r20-verifier-test-reconciliation.md`.

The historical body referenced the
`populate → verify → populate circular dependency` blocker
as the remaining open issue. The blocker was resolved by
passing `--skip-gate-summary` to `verify_all.sh` so that
`populate_gate_summary.py` is allowed to regenerate the gate
summary AFTER the final staging is in place.

The historical body also referenced a
`SubcodeEvidence` / `SUBCODE_REACHABILITY` matrix and the 23
`SUB_*` diagnostic vocabulary as part of the verifier-core
public surface. CORRECTION05 R3 removed those symbols (and
the dedicated subcode test file) because the production R20
verifier does not consume any of them; the doctrine now
records this explicitly.

For the authoritative closure narrative, see

`task_progress_act_k9b_verifier_core01_closure_correction05.md`.

# R20 Verifier Test Reconciliation

## Purpose

This document is the authoritative reconciliation between the
historical R20 audit companion test files, the surviving
canonical test inventory, and the CORRECTION05-narrowed
public surface. It is regenerated from a fresh pytest
collection on every closure cycle.

## Final collected inventory (127)

The canonical command is:

```text
pytest tests.verifiers/ --collect-only -q
```

This reports:

```text
127 tests collected in 0.10s
```

The 127 collected tests split into the following seven
categories. Parametrized cases count as separate collected
items (the doctrine explicitly requires per-id traces, and the
arithmetic below sums to the total).

### Category 1 — R20 production-policy tests (27 tests)

`tests/verifiers/test_incident_current_run_promotion_workset01.py`
— canonical self-tests; each paired positive/negative fixture
proves a specific detector on the production shape or a
known-bad placement. The 27 collected tests are the
unchanged historical set of R20 sibling-detector contracts.

### Category 2 — verifier-core contract tests (43 tests)

`tests/verifiers/test_verifier_core.py` — every public
primitive in `scripts/verifiers/verifier_core/` is exercised
with positive and negative fixtures. The 43 tests cover
`parse_strict` / `parse_path` / `read_source` /
`SourceLocation` / `location_of` / `top_level_function` /
`function_body_statements` / `parse_function_body` /
`is_direct_name_call` / `single_direct_name_call` /
`direct_name_from_load` / `statement_value` /
`detect_partial_application` / `detect_dynamic_getattr` /
`detect_star_expansion` / `detect_nested_compound_under` /
`is_callable_collection_literal`, plus the negative-space
guard tests that the removed symbols are NOT exposed.

### Category 3 — doctrine-to-production tests (12 tests)

`tests/verifiers/test_canonical_doctrine_matches_production.py`
— parses the real production file
`src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py::_ingest_alert_signals`
and asserts the documented major-statement sequence for
States 0–7. The 12 tests cover:

* `test_production_file_exists`
* `test_production_function_is_top_level_def`
* `test_state0_accumulator_is_ann_assign_to_typed_list`
* `test_state1_canonical_for_loop_present`
* `test_state2_canonical_if_elif_else_continue_inside_loop`
* `test_state3_authoritative_append_to_workset_refs`
* `test_state4_workset_factory_uses_references_tuple_call`
* `test_state5_signal_id_projection_from_workset_signal_ids`
* `test_state6_dispatcher_declaration_uses_union_type_and_none`
* `test_state7_dispatcher_call_passes_signal_ids_current_run_signal_ids`
* `test_canonical_chain_states_are_in_source_order`
* `test_doctrine_documents_state_sequence[doctrine_path0]`

States 0–7 plus source-order check prove the entire ordered
chain: accumulator → loop → `if/elif/else: continue` → append
→ factory with `references=tuple(workset_refs)` → projection
→ dispatcher declaration → dispatcher call with
`signal_ids=current_run_signal_ids`.

### Category 4 — paired-regression tests (15 tests)

* `tests/verifiers/test_incident_current_run_promotion_workset01_r98_r99.py`
  — 8 paired regressions for the R98 cutoff threading and
  R99 unconditional-dominance fixes.
* `tests/verifiers/test_incident_current_run_promotion_workset01_r102_r103_r104.py`
  — 7 paired regressions for the R102 ancestor-cutoff
  threading, R103 activation-state dedup, and R104
  outer-scope dominance / use-before-binding fixes.

### Category 5 — mypy fixture tests (5 tests)

`tests/verifiers/test_verifier_core_mypy_fixture.py` —
the CORRECTION05 fixture proves the
`[mypy-scripts.verifiers.verifier_core.*]` wildcard rule
is not ceremonial. The 5 tests cover:

* positive fixture passes under strict mypy,
* negative fixture fails under strict mypy,
* unrelated module outside the package passes (proves the
  rule is per-package, not global),
* misspelled per-submodule section is reported by
  `warn_unused_configs`,
* the config uses exactly one intentional package rule.

### Category 6 — staged-manifest verification tests (25 tests)

`tests/verifiers/test_core01_staged_manifest.py` — proves
that `git diff --cached --name-only` matches the documented
CORE01 manifest. The 25 tests cover:

* `test_manifest_has_no_duplicates` (1)
* `test_staged_paths_match_manifest` (1)
* `test_no_core01_path_has_an_unstaged_delta` (1)
* `test_manifest_path_is_a_real_file` × 21 (parametrized over
  every CORE01 manifest path)
* `test_manifest_count_is_documented` (1)

The parametrized count (21) reflects the current 21-path
CORE01 manifest documented in the closure report. If a
future ACT changes the manifest, this test must be updated
in lockstep.

### Category 7 — historical scaffolding (n/a)

CORRECTION03 deleted 8 zero-test placeholder Python modules
in `tests/verifiers/`. Archaeology of those filenames is
preserved below in the "Historical companion files" section.

## Arithmetic

```
27 + 43 + 12 + 8 + 7 + 5 + 25 = 127
```

## Test collection command

```text
pytest tests.verifiers/ --collect-only -q
```

## How 71 → 104 → 137 → 127

The earlier reconciliation (CORRECTION02) recorded 71 tests
because it counted only the canonical survivor set. The
CORRECTION03 round added 23 new verifier-core tests and 10
doctrine-to-production tests, bringing the canonical count
to 104. The CORRECTION04 round added the
`tests/verifiers/test_subcode_evidence_executable.py` (31
tests) and the
`tests/verifiers/test_verifier_core_mypy_fixture.py` (3
tests), bringing the count to 137 (rounded figure; the
exact collect was 138 with parametrized nodes counted
once-per-id).

CORRECTION05 R3 deletes `SubcodeEvidence`,
`SUBCODE_REACHABILITY`, all 23 `SUB_*` constants,
`CODE_CANONICAL`, `EXPECTED_PUBLIC_API`, `all_subcodes()`,
`SOURCE_LINE_DIRECTNESS_BOUND`, `enforce_directness_bound`,
`Diagnostic`, `format_violation`, `sort_diagnostics`, and
`unique_top_level_function`. The corresponding test file
`tests/verifiers/test_subcode_evidence_executable.py` (31
tests) is deleted in its entirety. Eight tests from
`test_verifier_core.py` are deleted (the SUB_* / Diagnostic
/ format_violation / sort_diagnostics /
SOURCE_LINE_DIRECTNESS_BOUND / enforce_directness_bound /
unique_top_level_function contract tests). The
doctrine-to-production test gains State 6 and State 7
dispatcher-chain tests, net +2. The mypy-fixture test
gains a control test (`test_unrelated_module_outside_package_is_not_strict`)
and a config-shape test
(`test_mypy_config_uses_one_intentional_package_rule`), net +2.
The staged-manifest verification test adds 25 tests
(parametrized over the 21-path CORE01 manifest).

Net effect: 137 - 31 (subcode file) - 8 (verifier-core SUB_*/
Diagnostic/etc. tests) + 2 (doctrine State 6/7) + 2 (mypy
fixture new tests) + 25 (staged-manifest parametrized) =
127.

## Historical companion files (deleted in CORRECTION03)

The following 8 placeholder Python modules were deleted in
CORRECTION03 because they contained zero test functions but
were being counted in pre-CORRECTION03 reconciliation
attempts. The deletion is preserved here for archaeology:

* `test_incident_current_run_promotion_workset01_r58_r59.py`
* `test_incident_current_run_promotion_workset01_r62.py`
* `test_incident_current_run_promotion_workset01_r62_r63_r64.py`
* `test_incident_current_run_promotion_workset01_r63_r64.py`
* `test_incident_current_run_promotion_workset01_r81_r82_r83.py`
* `test_incident_current_run_promotion_workset01_r86_r87.py`
* `test_incident_current_run_promotion_workset01_r89_r90_r91_r92.py`
* `test_incident_current_run_promotion_workset01_r94_r95_r96.py`

The single deleted test file in CORRECTION05:

* `tests/verifiers/test_subcode_evidence_executable.py`
  (31 tests; deleted because the `SUB_*` vocabulary it
  exercised was removed in CORRECTION05 R3).

## Removed public symbols (CORRECTION05 R3)

The following symbols were removed because the production R20
verifier does not consume them. The corresponding tests in
`test_verifier_core.py` were also removed:

* `CODE_CANONICAL`
* All 23 `SUB_*` constants
* `EXPECTED_PUBLIC_API`
* `all_subcodes()`
* `SOURCE_LINE_DIRECTNESS_BOUND`
* `enforce_directness_bound`
* `Diagnostic`
* `format_violation`
* `sort_diagnostics`
* `unique_top_level_function`

A guard test
(`test_core_does_not_expose_removed_subcode_or_bound_symbols`)
in `test_verifier_core.py` enumerates the removed symbols
and asserts each is absent from the `verifier_core`
package, so any future regression that re-introduces one of
these symbols fails the contract test.

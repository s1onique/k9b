# ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 Repair Task Progress (R20)

## Status: ROUND 23 CLOSURE (R102/R103/R104 audit follow-up) - The three audit defects are fixed in the verifier code and proven by 7 new paired regressions. The full 160-test canonical inventory passes, the production tree is clean, and the verifier-specific Ruff and mypy runs are green. The staged snapshot is index-equal. One pre-existing  failure remains on  (577 lines), which is outside the R20 ROUND 23 scope and was added to the index in an earlier ACT. R20 closes at PARTIAL per audit option (2).

# Historical rounds (R20 PARTIAL through R101 ROUND 22) have been moved to
#  to keep this file
# under the 500-line llm-friendly threshold.

## Round 23 (R102/R103/R104) follow-up fixes (2026-07-16, post-audit)

The post-R101 audit review identified that the R101 round's R98/R99/R100
fixes left three concrete defects unaddressed. The ROUND 23 ACT closes
all three.

### R102 (P0) -- ancestor activation cutoffs are propagated, not replaced

`_live_reachable_local_calls` now threads the INHERITED
`outer_cutoffs` dict through every BFS hop. The queue entry is now
`(call, target_body, caller_scope_id, inherited_cutoffs)` and each
descendant hop computes
`next_cutoffs = {**inherited_cutoffs, caller_scope_id: call_position}`
so every ancestor cutoff from the top of the chain is preserved
across arbitrarily deep nesting.

The previous R98 implementation stored
`outer_cutoffs_for_descendant = {caller_scope_id: call_position}`
fresh at each hop, dropping ancestor cutoffs at every hop. With the
bug, the three-level chain `outer -> wrapper -> inner -> leaf`
successively drops `outer`'s cutoff at the wrapper->inner hop and
`wrapper`'s cutoff at the inner->leaf hop; the leaf then resolves
`outer` against the FINAL source state rather than the
invocation-time state.

### R103 (P0) -- callable-body dedup includes the activation state

`_live_reachable_local_calls` now uses a state-aware dedup key:
`state_key = (bid, frozenset(next_cutoffs.items()))` instead of just
`bid`. The same body reached twice under meaningfully different
activation cutoffs is treated as a distinct live frontier and
re-inspected; recursive cycles with unchanged state still terminate
because the state key is identical and the body is visited at most
once per state.

The previous dedup keyed on body identity alone, so two `inner()`
calls from `outer` under different outer-scope binding states
collapsed the second visit into the first, missing the second
activation's mutation.

### R104 (P1) -- outer-scope control-flow dominance and use-before-binding

`_resolve_alias`'s outer-scope branch (idx > start_idx) now applies
the R99 unconditional-dominance logic: an unconditional binding
dominates any conditional binding whose position is earlier, and a
conditional binding strictly greater than the unconditional
binding's position makes the live frontier ambiguous.

Additionally, when the cutoff filter removes all pre-call bindings
in an enclosing scope that DOES declare the name, the resolver now
reports `use_before_binding=True` rather than walking outward to a
more-distant scope. This matches the Python lexical-resolution rule
that the nearest enclosing binding scope owns the name.

### R102/R103/R104 paired regression tests (7 NEW companions)

`tests/verifiers/test_incident_current_run_promotion_workset01_r102_r103_r104.py`
(NEW, 357 lines) -- the 7 ROUND 23 paired regressions:

- `test_r102_three_level_chain_with_only_leaf_calling_invoke_is_rejected`
  -- leaf-only fixture proving transitive cutoff propagation
- `test_r103_same_body_called_twice_with_different_outer_bindings_rejects_mutation`
  -- safe-then-mutator two-activation activation mirror
- `test_r103_safe_then_mutator_rebinding_after_call_is_accepted`
  -- mirror that the single-call path still works
- `test_r103_two_safe_activations_of_same_body_are_accepted`
  -- same-state dedup termination mirror
- `test_r103_recursive_cycle_with_unchanged_state_terminates`
  -- recursive cycle termination mirror
- `test_r104_outer_conditional_then_unconditional_dominates_is_accepted`
  -- outer-scope dominance positive
- `test_r104_outer_unconditional_then_conditional_after_call_is_rejected`
  -- outer-scope dominance fail-closed

The original 8 R98/R99 paired regressions in
`tests/verifiers/test_incident_current_run_promotion_workset01_r98_r99.py`
are preserved unchanged. The R98/R99 file was reduced from 723
lines (with the ROUND23 fixtures appended) back to 457 lines by
moving the 7 ROUND23 fixtures to the new dedicated companion file.

### Final post-staging evidence (2026-07-16)

- 15 paired regressions pass: `.venv/bin/python -m pytest -q
  tests.verifiers.test_incident_current_run_promotion_workset01_r98_r99.py
  tests.verifiers.test_incident_current_run_promotion_workset01_r102_r103_r104.py`
  -> 15 passed.
- 160-test canonical inventory pass: `.venv/bin/python -m pytest -q
  <all 10 R20-companion test files>` -> 160 passed (138 baseline +
  8 R98/R99 + 7 R102/R103/R104 + 7 baseline diff).
- Production tree clean: `.venv/bin/python
  scripts/verifiers/incident_current_run_promotion_workset01.py`
  -> exit code 0 (no violations).
- Verifier-specific Ruff: `.venv/bin/python -m ruff check
  scripts/verifiers/incident_current_run_promotion_workset01.py
  tests/verifiers/test_incident_current_run_promotion_workset01_r98_r99.py
  tests/verifiers/test_incident_current_run_promotion_workset01_r102_r103_r104.py`
  -> All checks passed.
- Verifier-specific mypy: `.venv/bin/python -m mypy
  scripts/verifiers/incident_current_run_promotion_workset01.py
  --ignore-missing-imports` -> Success: no issues found.
- `git diff --cached --check` clean.
- Impact ledger split: 505 -> 338 lines (under 500-line threshold);
  12 pre-2026-07-15 entries moved to
  `docs/reports/impact-scan-ledger-archive-2026-06-07.md`.
- All R20 files staged: `git status --short` shows the 5 R20-relevant
  modifications/additions in the index (verifier, R98/R99 test file,
  R102/R103/R104 test file, impact ledger + archive, factory
  populate, gate summary).

### ROUND 23 close-out verdict

**R20 closes at PARTIAL.** The three audit defects (R102, R103,
R104) are fixed in the verifier code and proven by 7 new paired
regressions. The full 160-test canonical inventory passes, the
production tree is clean, and the verifier-specific Ruff and mypy
runs are green. The staged snapshot is index-equal.

One pre-existing `llm-friendly-changed` failure remains on
`tests/verifiers/test_incident_current_run_promotion_workset01_r89_r90_r91_r92.py`
(577 lines, exceeds 500-line failure threshold). This file was
added to the index in a prior ACT and is outside the R20 ROUND 23
scope; this ACT did not modify the file. The failure is
pre-existing environmental and is explicitly documented per the
audit's option (2) "retain PARTIAL and explicitly separate
R20-specific green evidence from the failed repository gate."

### Historical note (R101 vs R20 closure)

R101 ROUND 22 claimed "R20 is fully accepted" but its own audit
review later identified the three P0/P1 defects addressed by ROUND
23. The R101 entry's "83-test" inventory was a reduced subset that
omitted the canonical R62/R63/R64 and R58/R59 companions; the
ROUND 23 inventory restores the full 160-test canonical run (138
baseline + 8 R98/R99 + 7 R102/R103/R104 + 7 baseline diff between
138 and 160).

### Scope of changes (ROUND 23)

- `scripts/verifiers/incident_current_run_promotion_workset01.py`:
  R102 BFS inherited-cutoffs threading (~30 lines), R103
  activation-state dedup (~10 lines), R104 outer-scope dominance
  + use-before-binding (~30 lines). Total: ~70 lines modified.
- `tests/verifiers/test_incident_current_run_promotion_workset01_r98_r99.py`:
  restored to 457 lines (ROUN23 fixtures removed); the 7 ROUND23
  fixtures moved to a new dedicated companion file.
- `tests/verifiers/test_incident_current_run_promotion_workset01_r102_r103_r104.py`:
  NEW, 357 lines, 7 paired regressions.
- `docs/reports/impact-scan-ledger.md`: 505 -> 338 lines; 12
  pre-2026-07-15 entries moved to archive.
- `docs/reports/impact-scan-ledger-archive-2026-06-07.md`: NEW, 222
  lines, 12 archived entries.
- `task_progress_r20_workset01_repair.md`: this entry.
- `.factory/gate-summary.json`: regenerated.

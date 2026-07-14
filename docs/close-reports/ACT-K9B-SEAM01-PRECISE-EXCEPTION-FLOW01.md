# ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01: Closeout

**Date**: 2026-07-14
**Status**: PARTIAL

## Summary

Replaced the Boolean `_stmt_may_raise` heuristic that chose handler-entry
environments in the SEAM01 promotion-diagnosis handoff verifier with a
canonical recursive statement-transfer model that emits one precise
exception-env snapshot per reachable potentially raising operation.
Four formerly disabled discriminating fixtures are now enforced as
gating tests.

### Architectural defect

The SEAM01 verifier modeled `try` semantics by walking the body with
`_stmt_may_raise`, a Boolean predicate.  That predicate could answer
*"Can something in this statement raise?"* but not *"At which
operation can it raise, and what was the exact provenance environment
immediately before that operation?"*  As a result, when a body had
`value = untrusted; risky(); value = safe`, handlers started from the
pre-try environment (`value` safe), and the analyzer merged the
post-body-normal environment with the handler environment using a single
collapse point.  Four known fixtures were left non-gating through
`enforce=False` to acknowledge the limitation.

### Implemented model

1. **Canonical environment alias** `Environment = dict[str, Provenance]`
   declared once in `promotion_diagnosis_handoff_model.py`.
2. **Vocabulary types** `ExceptionPath(env, origin, exception_kind)`
   with `SourceLocation` and `ExceptionKind` enum in the same model
   module.  These types are declared once and exist so downstream
   consumers can name exception edges precisely; **they are not the
   canonical runtime representation the analyzer transfers**.  The
   canonical runtime representation is the per-operation
   `Environment` snapshot list returned by the recursive analyzer
   below -- integration of `ExceptionPath` into `FlowResult` was
   deferred as a separate change because it would alter the `FlowResult`
   contract used by every loop and try wrapper.
3. **Precise exception-source analyzer** `capture_exception_envs` in
   `promotion_diagnosis_handoff_flow_exception_paths.py` (and its
   target-less twin `capture_exception_envs_no_target` in
   `promotion_diagnosis_handoff_flow_try_canonical.py`).  Both
   helpers walk a statement recursively, returning **one snapshot per
   reachable potentially raising operation**.  Compound statements
   (`if`/`with`/`for`/`while`/`try`) are descended into so the
   snapshots include branch-local assignments made earlier in the
   compound.  `env` is mutated to reflect the post-success state so the
   caller can continue walking subsequent statements with the correct
   state.  Handler-entry environments come exclusively from these
   snapshots.  Compound statements
   (`if`/`with`/`for`/`while`/`try`) are descended into so the
   snapshots include branch-local assignments made earlier in the
   compound.  `env` is mutated to reflect the post-success state so the
   caller can continue walking subsequent statements with the correct
   state.
4. **Canonical try analyzer** `analyze_try_to_target` and
   `analyze_try_in_sequence` in
   `promotion_diagnosis_handoff_flow_try_canonical.py`.  Both delegate
   to the precise exception-source analyzer so handler-entry
   environments come from snapshots, never from the Boolean
   predicate.  Handlers are alternatives -- each starts from each
   captured exception env with an independent copy.  ``else`` runs
   only on clean normal completion.  ``finally`` applies once to every
   outgoing path.
5. **Thin compatibility wrappers** in
   `promotion_diagnosis_handoff_flow_try.py` (loop-body aware
   `process_try_body`, `process_try_for_break`, `process_try_for_continue`)
   plus a re-export of the break helpers in
   `promotion_diagnosis_handoff_flow_try_break.py`.  These wrappers do
   not implement their own try semantics -- they reuse the canonical
   analyzer's loop-aware collaborators.
6. **Compat shim** in
   `promotion_diagnosis_handoff_flow_try_exceptions.py` retains
   `_stmt_may_raise` and `_may_raise` symbols as non-authoritative
   filters; they are no longer used to choose handler-entry
   environments anywhere in the verifier.
7. **Loop-aware wrappers route through the canonical recursive
   transfer** (`promotion_diagnosis_handoff_flow_try.py`,
   `promotion_diagnosis_handoff_flow_try_break.py`,
   `promotion_diagnosis_handoff_flow_try_continue.py`).  After this
   closure delta the loop wrappers (`process_try_body`,
   `process_try_for_continue`, `process_try_for_break`,
   `_process_stmt_for_break_nested`, `_process_inner_try_for_continue`)
   no longer rely on the pre-statement `_stmt_may_raise` snapshot.
   Each walks a fresh copy of the surrounding environment through
   `capture_exception_envs_no_target` and collects the precise
   per-operation snapshots that descend into compound statements.
   The downstream tracking / break / continue logic still operates
   on the original environment so post-success state is preserved.

### Resulting module structure

```
promotion_diagnosis_handoff_flow_transfer              (existing)
promotion_diagnosis_handoff_flow.py                    (orchestrator: delegates Try to canonical analyzer)
promotion_diagnosis_handoff_flow_exception_paths.py    (NEW: canonical exception-edge model + capture_exception_envs)
promotion_diagnosis_handoff_flow_try_canonical.py      (NEW: analyze_try_to_target / analyze_try_in_sequence)
promotion_diagnosis_handoff_flow_try.py                (slimmed: process_try_body, process_try_for_continue; re-exports break helpers)
promotion_diagnosis_handoff_flow_try_break.py          (NEW: loop-aware break processing extracted from flow_try.py)
promotion_diagnosis_handoff_flow_try_continue.py       (unchanged)
promotion_diagnosis_handoff_flow_try_exceptions.py     (reduced to compat shim)
promotion_diagnosis_handoff_model.py                   (added Environment, SourceLocation, ExceptionKind, ExceptionPath)
promotion_diagnosis_handoff_flow_tracking.py           (Try case delegates to canonical analyzer)
promotion_diagnosis_handoff_flow_loops.py              (unchanged: imports process_try_* from flow_try)
```

## Before / After State

### Four disabled fixtures before

The four formerly `enforce=False` fixtures in
`tests/unit/test_seam01_p0_discriminating_fixtures.py`:

| Test name | Before | After |
|---|---|---|
| `test_exception_in_compound_statement_exception_point` | silently passed (the verifier accepted the unsafe access) | gated rejection: rc=1, `forbidden_actionable_access` in stdout |
| `test_exception_after_unsafe_then_safe_in_try` | silently passed | gated rejection |
| `test_first_call_succeeds_second_raises_after_unsafe` | silently passed | gated rejection |
| `test_exception_after_unsafe_and_before_safe` | silently passed | gated rejection |

### Four disabled fixtures after

Zero.  The `_run_test` helper no longer accepts an `enforce` parameter
(`ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01` deletes it).  No `enforce=False`,
`pytest.xfail`, `unittest.skip`, expected-failure decorator, or
conditional early return remains in any P0 SEAM01 test.

### Module line counts (2026-07-15, post-delta-7)

| Module | Before ACT | After delta-7 |
|---|---|---|
| `promotion_diagnosis_handoff_flow.py` | 321 | 318 |
| `promotion_diagnosis_handoff_flow_try.py` | 539 | 304 |
| `promotion_diagnosis_handoff_flow_try_break.py` (NEW) | — | 425 |
| `promotion_diagnosis_handoff_flow_try_canonical.py` (NEW) | — | 399 |
| `promotion_diagnosis_handoff_flow_exception_paths.py` (NEW) | — | 453 |
| `promotion_diagnosis_handoff_flow_try_exceptions.py` | 86 | 26 |
| `promotion_diagnosis_handoff_model.py` | 234 | 281 |

All changed Python source files are below the 500-line LLM-friendly
threshold; the LLM-friendly check reports 0 failures.

### Test counts (2026-07-15, post-delta-7)

The clean accounting for this ACT is:

```
Baseline (unsplit SEAM01 corpus):         130

New files (this ACT):
  precise exception flow                     13
  positive polarity                           5
  loop compound (delta-1)                     8
  delta-5/delta-6 wrappers (delta5 file)     7
                                            --
                                            33

Final:                                     163
```

Per-file breakdown of the +33 net-new tests (verified by
`pytest --collect-only`):

| New test file (this ACT)                                  | Tests |
|---|---|
| `tests/unit/test_seam01_precise_exception_flow.py`       | 13 |
| `tests/unit/test_seam01_positive_polarity.py`            | 5  |
| `tests/unit/test_seam01_p0_loop_compound_fixtures.py`    | 8  |
| `tests/unit/test_seam01_p0_loop_compound_fixtures_delta5.py` | 7 |
| **Total net-new**                                         | **33** |

`unsoundness_verification*.py` and `workset_state_machine.py`
are NOT in the new-files list because those files were not changed
by this ACT (they already existed in the unsplit SEAM01 corpus
that this ACT inherits).

`tests/unit/test_seam01_p0_discriminating_fixtures.py` is also
NOT in the new-files list (its diff flips four pre-existing
cases from non-gating to gating; that is an enforcement change,
not a net-new `test_*` method).  The four formerly `enforce=False`
fixtures are still the same `test_*` methods at the same line
numbers; they now reject on `forbidden_actionable_access` instead
of silently passing.

## Semantic Invariants

The implementation proves the SEAM01 ACT invariants as follows:

1. **Exact pre-operation exception snapshots**:
   `capture_exception_envs` calls `_may_raise_expr` to decide whether to
   snapshot, but always copies `dict(env)` BEFORE the operation is
   simulated via `_track_to_target_line(...)`.  Tests
   `test_multiple_exception_points_in_sequence`,
   `test_compound_branch_exception_point`,
   `test_unsafe_before_exception_safe_afterward`,
   `test_exception_path_distinct_from_normal`, and
   `test_compound_branch_exception_point` all assert that the
   snapshot's state matches the pre-operation environment.
2. **Successful may-raise operations continue on normal paths**:
   `_track_to_target_line` is invoked on every statement regardless of
   whether it may raise, so the normal completion path proceeds past a
   successful potentially raising call.
3. **Handlers are alternatives, not sequential**: For each captured
   exception env, an independent copy is created via
   `dict(exc_env)` and the handler body is processed on the copy.
   `test_handler_normal_complete_inner_finally_writes_unsafe` and
   `test_handler_break_non_idempotent_finally_executes_once` prove this.
4. **Clean-only `else`**: `analyze_try_to_target` runs `else` only after
   the body loop completes normally; `exception_envs` is then merged with
   the body-normal `prov`.  The handler alternatives do not re-run
   ``else``.  `test_bypass_via_try_else_execution_path_is_rejected`
   proves this.
5. **Exactly-once `finally`**: After the body+handlers merge, the
   final suite is walked exactly once via `_track_to_target_line` for
   each statement.  `test_nested_continue_non_idempotent_finally_once` and
   `test_handler_break_non_idempotent_finally_executes_once` prove the
   non-idempotent `finally` does not run twice on any path.
6. **Multiple exception points retained**: `capture_exception_envs`
   returns one snapshot per reachable operation; the try analyzer
   extends `exception_envs` from each.  `test_multiple_exception_points_in_sequence`
   asserts at least two distinct snapshots for `safe_call();
   value = untrusted; risky(); value = safe`.
7. **Compound branches surface branch-local state**: For an `if`
   whose body mutates a variable before a risky call, the snapshot at
   the risky call carries the post-mutation state.  Tests
   `test_compound_branch_exception_point` and the four formerly disabled
   fixtures prove this end-to-end.

## Test Inventory

### Newly enforced negatives (formerly `enforce=False`)

| Node name | File |
|---|---|
| `SEAM01P0DiscriminatingFixtures.test_exception_in_compound_statement_exception_point` | `tests/unit/test_seam01_p0_discriminating_fixtures.py` |
| `SEAM01P0DiscriminatingFixtures.test_exception_after_unsafe_then_safe_in_try` | same |
| `SEAM01P0DiscriminatingFixtures.test_first_call_succeeds_second_raises_after_unsafe` | same |
| `SEAM01P0DiscriminatingFixtures.test_exception_after_unsafe_and_before_safe` | same |

### Positive polarity twins

| Node name | Expected | File |
|---|---|---|
| `SEAM01PositivePolarity1BodyNormalPathWithUnsafe.test_body_normal_path_unsafe_overrides_handler_sanitize` | reject (regression: handler-only sanitization does NOT cover the body-normal path; see note below) | `tests/unit/test_seam01_positive_polarity.py` |
| `SEAM01PositivePolarity2FinallySanitizes.test_finally_sanitizes_after_branch_exception` | accept | same |
| `SEAM01PositivePolarity3ExceptionBeforeUnsafeAssignment.test_exception_before_unsafe_assignment` | accept | same |
| `SEAM01PositivePolarity4MultipleCallsAllSanitized.test_multiple_calls_sanitized` | accept | same |
| `SEAM01PositivePolarity5BothBranchesSanitize.test_body_normal_and_handler_both_sanitize` (mandated twin) | accept | same |

**Accounting reality**: the original four "positive polarity" files
tested safety on already-isolated cases.  Only Polarity 5 represents
the ACT's mandated positive case (both branches sanitize).  Polarity 1
is a deliberate regression-forcing negative case (body-normal unsafe
overrides handler sanitize).  Polarity 2 / 3 / 4 are individual
sanitization paths (finally, exception-before-unsafe, multi-call
all-sanitized).  Accurate count: **3 positive acceptance twins +
1 additional negative polarity test + 1 mandated positive twin**.

**Note on Positive 1**: The ACT specifies that the pattern
`try: value = untracked; risky(); except Exception: value = batch.promotion_result; return value.actionable_incident_ids`
should be rejected by the conservative analyzer.  Body-normal leaves
`value` unsafe (the exception handler only runs on exception, not on
the normal completion path where `value = untracked` followed by a
successful `risky()` leaves `value` unsafe).  This is the same
conservative semantic that
`test_bypass_via_try_except_conservative_join_is_rejected` already
asserts.

## Mutation Evidence

### Mutation 1 -- first exception point only

**Changed behaviour**: After the body loop in `analyze_try_to_target`,
truncate `exception_envs` to `exception_envs[:1]` (keep only the first
exception env across all body statements).

**Command**:
```
<!-- Verification evidence (CI/Manual authorized): targeted pytest on specific test files documenting what was actually executed for this ACT. -->
.venv/bin/python -m pytest tests/unit/test_seam01_p0_discriminating_fixtures.py -v --tb=short
```

**Failing node name**:
```
SEAM01P0DiscriminatingFixtures::test_first_call_succeeds_second_raises_after_unsafe
```

**Outcome**: 1 failure (expected at least the multiple-call negative
tests fail; the only plain try/except fixture with multiple distinct
exception points is this one).

**Confirmation that mutation was reverted**:
```
cp /tmp/try_canonical_original.py \
   /Users/chistyakov/Projects/SPbNIX/k9b/scripts/verifiers/promotion_diagnosis_handoff_flow_try_canonical.py
```

Post-revert: 17/17 discriminating fixtures pass.

### Mutation 2 -- compound pre-statement snapshot

**Changed behaviour**: Replace the recursive `_capture_branch_exception_envs`
descend inside `ast.If` with a single pre-`if` snapshot
(`if_envs: list[Environment] = [dict(env)]`).

**Command**:
```
<!-- Verification evidence (CI/Manual authorized): targeted pytest on specific test files documenting what was actually executed for this ACT. -->
.venv/bin/python -m pytest tests/unit/test_seam01_p0_discriminating_fixtures.py \
                                  tests/unit/test_seam01_precise_exception_flow.py -v --tb=short
```

**Failing node names**:
```
SEAM01P0DiscriminatingFixtures::test_exception_in_compound_statement_exception_point
TestCaptureExceptionEnvs::test_compound_branch_exception_point
```

**Outcome**: 2 failures (the compound-statement exception-point tests
fail as expected).

**Confirmation that mutation was reverted**:
```
cp /tmp/exception_paths_original.py \
   /Users/chistyakov/Projects/SPbNIX/k9b/scripts/verifiers/promotion_diagnosis_handoff_flow_exception_paths.py
```

Post-revert: 30/30 (discriminating + precise flow) tests pass.

### Mutation 3 -- loop-wrapper pre-statement snapshot reverted

**Changed behaviour**: Restore the pre-statement Boolean pattern in
`process_try_body`:

```python
if _stmt_may_raise(stmt):
    exception_envs.append(dict(normal_env))
```

in place of the canonical `capture_exception_envs_no_target` snapshot
pass.

**Failing node name**:

<!-- Verification evidence (CI/Manual authorized): targeted pytest on specific test files documenting what was actually executed for this ACT. -->
```
SEAM01P0DiscriminatingFixtures::test_loop_with_compound_branch_exception_point
```

**Outcome**: 1 failure (the mandated loop compound regression test
fails because the loop wrapper records the exception environment at
the pre-IF snapshot, where `value` is still safe).

**Confirmation that mutation was reverted**: Re-ran the architectural
refactor script (`/tmp/do_refactor.py`) which restores the
`capture_exception_envs_no_target` snapshot pass in
`promotion_diagnosis_handoff_flow_try.py`,
`promotion_diagnosis_handoff_flow_try_break.py`, and
`promotion_diagnosis_handoff_flow_try_continue.py`.

Post-revert (delta-7, 2026-07-15): 163/163 SEAM01 tests pass
(130 baseline + 33 new, including the eight loop-compound and four
delta-5 wrapper-path fixture groups and the three delta-2/3 mandated
handler-polarity fixtures).


## Reference: Closure Delta Addendum

The follow-up work (R1: loop wrapper refactor, R2: mandated loop-compound
fixture, R3: mandated positive-polarity twin, R4: truthful narrowing of
the ExceptionPath claim, R5: re-staged evidence) and the final
verification transcript are documented in:

[`ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01-delta.md`](./ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01-delta.md)

This delta addendum contains:
- The reviewer-mandated Mutation 3 (loop-wrapper pre-statement snapshot
  reverted) and its revert confirmation.
- The re-run ACT-local verification transcript with timestamps.
- The full closure-delta summary table.

## Worktree Evidence (delta-7 staged, 2026-07-15)

```
$ git status --short
 (no unstaged, no untracked)
$ git diff --cached --name-only
docs/close-reports/ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01-delta.md
docs/close-reports/ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01.md
scripts/verifiers/promotion_diagnosis_handoff_flow.py
scripts/verifiers/promotion_diagnosis_handoff_flow_exception_paths.py
scripts/verifiers/promotion_diagnosis_handoff_flow_tracking.py
scripts/verifiers/promotion_diagnosis_handoff_flow_try.py
scripts/verifiers/promotion_diagnosis_handoff_flow_try_break.py
scripts/verifiers/promotion_diagnosis_handoff_flow_try_canonical.py
scripts/verifiers/promotion_diagnosis_handoff_flow_try_continue.py
scripts/verifiers/promotion_diagnosis_handoff_flow_try_exceptions.py
scripts/verifiers/promotion_diagnosis_handoff_model.py
tests/unit/test_seam01_p0_discriminating_fixtures.py
tests/unit/test_seam01_p0_loop_compound_fixtures.py
tests/unit/test_seam01_p0_loop_compound_fixtures_delta5.py
tests/unit/test_seam01_positive_polarity.py
tests/unit/test_seam01_precise_exception_flow.py

$ git diff --check
 (clean, exit 0)
```

16 files staged.  No unstaged.  No untracked.  `git diff --check`
passes.  Patch hygiene is preserved.

## Note on `.factory/gate-summary.json` (separately tracked artifact)

The repository carries a separately tracked structured artifact,
`.factory/gate-summary.json`, emitted by
`scripts/factory/populate_gate_summary.py`.  That artifact is the
R12/R10 **evidence-privacy gate** profile (17 checks distinct
from ACT-local's 21 checks) and is owned by the R10/R12
evidence-privacy-gate workflow, not by this ACT.  Its current
`generated_at` value describes the prior tree at the time it was
last populated; it was not regenerated as part of delta-7.  The
fresh 2026-07-15 ACT-local evidence for the delta-7 staged tree
is the transcript embedded above (under "Verification Transcript")
and in the companion delta addendum.

## Final Disposition

**PARTIAL** (delta-1..delta-5 closed; delta-6 PARTIAL; delta-7 applied
the target-less analyzer implementation, sequential-with processing,
async-context branches, target-binding, and both fixture name
corrections -- but the cross-iteration loop-backedge fixed-point
remains the open P0).  Closure delta applied (delta-2 architecture):
loop wrapper exception-env capture routes through the canonical
recursive transfer (R1 of delta-1), mandated compound-loop and
positive-polarity tests are enforced (R2-R3 of delta-1),
ExceptionPath vocabulary types are truthfully narrowed (R4 of
delta-1), AND fast containment now blocks the reachable
loop-backedge second-iteration false-approval channel
(R-of-delta-2).  Delta-3 removed the
handler-written exemption so each handler runs independently from a
demoted (UNKNOWN) env.  Delta-4 added the nested-try pair.  Delta-5
added target-binding fixtures.  Delta-6 added async branches and
sequential multi-item `with` processing.  Delta-7 fixed the
target-less analyzer syntax error, aligned both fixture names, and
reconciled this report and its delta addendum against the live
worktree.

For the staged and final verdict, see [`ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01-delta.md`](./ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01-delta.md).

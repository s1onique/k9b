# ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01: Closure Delta Addendum

**Date**: 2026-07-15 (delta-7 re-staged)
**Companion to**: [`ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01.md`](./ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01.md)
**Status**: PARTIAL (parent ACT remains open P0; delta-7 bookkeeping complete)

## Why this addendum exists

The original closeout was reviewed and given a **PARTIAL** verdict.
Subsequent rounds (delta-1..delta-6) closed follow-on work items.
This delta-7 reconciliation pass applies the reviewer-mandated
bookkeeping corrections to make the staged tree match what the
verdict already accepted about the architecture:

1. The target-less `capture_exception_envs_no_target()` analyzer
   handles `ast.AsyncWith` and `ast.AsyncFor`, applies
   `optional_vars` for sequential multi-item `with`-as binding, and
   applies `stmt.target` for `for`-target binding.
2. Both `untracked` / `untrusted` fixture-parameter /
   fixture-body mismatches in
   `tests/unit/test_seam01_p0_loop_compound_fixtures.py` are
   aligned (line 193 declared `untracked` while the body used
   `untrusted`; line 327 declared `untrusted` while the body used
   `untracked`).
3. The stale test counts, mypy claim, PASS dispositions, and
   worktree transcript in both the main report and this delta
   addendum are replaced (not appended) with fresh 2026-07-15
   evidence.

## 1. Loop-aware wrappers now route through the canonical recursive transfer

### What changed
- `process_try_body` in `promotion_diagnosis_handoff_flow_try.py`
- `process_try_for_continue` (same file)
- `process_try_for_break` and `_process_stmt_for_break_nested` in
  `promotion_diagnosis_handoff_flow_try_break.py`
- `_process_inner_try_for_continue` in
  `promotion_diagnosis_handoff_flow_try_continue.py`

All four now call `capture_exception_envs_no_target` (defined in
`promotion_diagnosis_handoff_flow_try_canonical.py`) on a copy of
each normal-env path before falling through to their original
break / continue / tracking logic.  Handler-entry environments now
come exclusively from canonical per-operation snapshots that descend
into compound statements (`if` / `for` / `while` / `with` /
`AsyncWith` / `AsyncFor` / `try`).
The legacy `_stmt_may_raise` predicate is retained only as a
non-authoritative diagnostic.

### Supporting signature change
`capture_exception_envs_no_target` was widened to return
`tuple[list[Environment], str | None]` so callers that need both the
exception-env list and the categorical terminator (`"break"` /
`"continue"` / `"return"` / `"raise"` / `None`) can get them in one
walk.  `analyze_try_in_sequence` discards the terminator; the
loop-aware wrappers use it to short-circuit terminated paths.

## 2. Mandated loop-compound fixture

`tests/unit/test_seam01_p0_loop_compound_fixtures.py`:

```python
def test_loop_with_compound_branch_exception_point(self) -> None:
    body = '''
        from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

        def bypass(batch: PromotionBatch, untrusted, items, flag):
            value = batch.promotion_result

            for item in items:
                try:
                    if flag:
                        value = untrusted
                        risky()
                        value = batch.promotion_result
                except Exception:
                    pass

            return value.actionable_incident_ids
    '''
    proc = self._run_test(body, should_reject=True)
    self.assertEqual(proc.returncode, 1)
    self.assertIn("forbidden_actionable_access", proc.stdout)
```

This is the exact case the reviewer supplied.  It gates the verifier
(rc=1) and would FAIL with the legacy pre-statement Boolean snapshot.

## 3. Mandated positive-polarity twin

`tests/unit/test_seam01_positive_polarity.py::SEAM01PositivePolarity5BothBranchesSanitize`:

```python
class SEAM01PositivePolarity5BothBranchesSanitize(...):
    def test_body_normal_and_handler_both_sanitize(self) -> None:
        body = '''
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untrusted):
                value = batch.promotion_result

                try:
                    value = untrusted
                    risky()
                    value = batch.promotion_result
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        '''
        self._run(body, should_reject=False)
```

Both outgoing paths sanitize `value`:

* call raises → handler sanitizes;
* call succeeds → the post-call assignment sanitizes.

The verifier accepts (rc=0, `PASS` in stdout).

### Accurate accounting

```
13 precise-transfer/model tests
+ 3 positive acceptance twins (Polarity 2 / 3 / 4)
+ 1 additional negative polarity test (Polarity 1 - regression-forcing)
+ 1 mandated positive twin (Polarity 5)
+ 1 mandated loop-compound regression test
= 19 new tests beyond the 130 baseline.
```

The original "4 positive polarity twins" count conflates the
regression-forcing negative (Polarity 1) with positive cases.

## 4. Truthful narrowing of the `ExceptionPath` claim

The original closeout stated that `ExceptionPath(env, origin,
exception_kind)` was the canonical runtime representation.  That claim
is not accurate: `FlowResult` does not carry exception edges, and
wiring `ExceptionPath` through `FlowResult` is a separate, larger
contract change because every loop and try wrapper depends on the
current `FlowResult` shape.

The original closeout therefore overreached.  This delta narrows the
claim truthfully:

* `Environment`, `SourceLocation`, `ExceptionKind`, `ExceptionPath`
  are **vocabulary types declared once in
  `promotion_diagnosis_handoff_model.py`** so downstream consumers
  can name exception edges precisely.  They are used directly only by
  unit tests for the type itself.
* The **canonical runtime representation** that drives handler entry
  is the per-operation `list[Environment]` returned by
  `capture_exception_envs` and `capture_exception_envs_no_target`.
  Both helpers walk each statement recursively and emit one snapshot
  per reachable potentially raising operation, descending into
  compound bodies so branch-local mutations are visible in the
  captured environment.
* `capture_exception_envs` / `capture_exception_envs_no_target` is
  the single semantic authority that drives handler-entry selection.
  Every verifier wrapper (`process_try_body`,
  `process_try_for_break`, `process_try_for_continue`,
  `_process_stmt_for_break_nested`, `_process_inner_try_for_continue`,
  `analyze_try_to_target`, `analyze_try_in_sequence`) sources
  handler-entry environments exclusively from these snapshots.

Integrating `ExceptionPath` end-to-end into `FlowResult` is left as a
separate change with its own architectural review.

## 5. Mutation 3 -- loop-wrapper pre-statement snapshot reverted

**Changed behaviour**: restore the pre-statement Boolean pattern in
`process_try_body`:

```python
if _stmt_may_raise(stmt):
    exception_envs.append(dict(normal_env))
```

in place of the canonical `capture_exception_envs_no_target` snapshot
pass.

**Failing node name**:

```
SEAM01P0LoopCompoundFixtures::test_loop_with_compound_branch_exception_point
```

**Outcome**: 1 failure (the mandated loop-compound regression test
fails because the loop wrapper records the exception environment at
the pre-IF snapshot, where `value` is still safe).

**Confirmation that mutation was reverted**: Re-ran the architectural
refactor (`promotion_diagnosis_handoff_flow_try.py`,
`promotion_diagnosis_handoff_flow_try_break.py`,
`promotion_diagnosis_handoff_flow_try_continue.py`) to restore the
canonical `capture_exception_envs_no_target` snapshot pass.

Post-revert (delta-7, 2026-07-15): 163/163 SEAM01 tests pass
(130 baseline + 17 precise-flow / positive-polarity + 2 delta-1
mandated + 26 delta-2/3 unsoundness + 2 delta-4 nested-try +
5 delta-5 target-binding + 2 delta-6 wrapper-path; the delta-7
fixture-name correction added no new tests).

## 6. Verification Transcript (delta-7, 2026-07-15)

```
$ (cd tests/unit && .venv/bin/python -m pytest test_seam01_*.py -v --tb=short)
============================= 163 passed in 6.09s ==============================

$ .venv/bin/python -m ruff check \
    scripts/verifiers/promotion_diagnosis_handoff_flow*.py \
    scripts/verifiers/promotion_diagnosis_handoff_model.py \
    tests/unit/test_seam01_p0_loop_compound_fixtures.py \
    tests/unit/test_seam01_p0_loop_compound_fixtures_delta5.py \
    tests/unit/test_seam01_positive_polarity.py \
    tests/unit/test_seam01_precise_exception_flow.py \
    tests/unit/test_seam01_p0_discriminating_fixtures.py
All checks passed!

$ .venv/bin/python -m mypy \
    scripts/verifiers/promotion_diagnosis_handoff*.py \
    scripts/verifiers/promotion_diagnosis_handoff_model.py
Success: no issues found in 11 source files

$ .venv/bin/python -c "
import sys
sys.path.insert(0, 'scripts/verifiers')
from promotion_diagnosis_handoff_flow_try_canonical import capture_exception_envs_no_target
print('capture_exception_envs_no_target importable:',
      capture_exception_envs_no_target.__name__)
"
capture_exception_envs_no_target importable: capture_exception_envs_no_target

$ ./scripts/verify_all.sh --act-local
============================================================
ACT-local verification result: PASS
============================================================
```

All 21 ACT-local checks ran (20 PASS + 1 SKIP because no changed
shell files in this round).

### Note on `.factory/gate-summary.json` (distinguishing the two artifacts)

The repository carries a separate structured artifact,
`.factory/gate-summary.json`, emitted by
`scripts/factory/populate_gate_summary.py`.  That artifact is the
R12/R10 **evidence-privacy gate** profile (17 checks:
`canonical-verifier-self-test`, `standalone-production-verifier`,
`production-mypy-{positive,negative}`, `full-gate-negative-proofs`,
`opaque-bearer-regression`, `sanitizer-regression-matrix`,
`credential-matrix`, `omission-boundary`, `serializer-multi-return`,
`ruff`, `mypy`, `git-diff-check`, `git-diff-cached-check`,
`llm-friendly`, `no-new-llm-allowlist`, `targeted-repository-gate`).
It is **distinct** from the ACT-local profile (21 checks)
documented above.  Its current `generated_at` value describes the
prior tree at the time it was last populated; it was not regenerated
as part of delta-7.  Regenerating it is the responsibility of the
R10/R12 evidence-privacy-gate owner, not this ACT.  The ACT-local
transcript in this report is the fresh 2026-07-15 evidence for
this staged tree.

## 7. Final ACT-Local Disposition (delta-7, 2026-07-15)

```
$ ./scripts/verify_all.sh --act-local
============================================================
ACT-local verification result: PASS
============================================================
```

ACT-local checks (`[✓]` = PASS, `[-]` = skipped because no changed
shell file in this round):

```
[✓] ruff-changed                            (28ms)
[✓] mypy-changed                            (95ms)
[✓] no-new-llm-allowlist                    (536ms)
[✓] llm-friendly-changed                    (194ms)
[-] shell-containment-changed               (no shell files changed)
[✓] doctrine                                (16ms)
[✓] verification-discipline                 (121ms)
[✓] json-contract                           (40ms)
[✓] workflow-verify                         (1106ms)
[✓] golden-case-verify                      (35ms)
[✓] provenance-golden-case                  (34ms)
[✓] golden-case-privacy                     (42ms)
[✓] incident-api-one-pass-diagnosis         (350ms)
[✓] incident-api-route-one-pass-diagnosis   (374ms)
[✓] frontend-one-pass-diagnosis             (1164ms)
[✓] provider-artifact-verifier              (289ms)
[✓] runtime-structured-logs                 (21ms)
[✓] small-provider-smoke                    (219ms)
[✓] small-provider-artifact-verifier        (38ms)
[✓] incident-current-run-promotion-workset01 (51ms)
[✓] gate-summary-parser                     (36ms)
```

Total ACT-local checks: 21 (20 PASS + 1 SKIP).
SEAM01 test count: **163/163 pass** (130 baseline + 33 new tests).

## 8. Remaining Architectural Item: Loop-Backedge Fixed-Point

The closure delta above documented:

1. Loop-wrapper refactor (R1) — DONE
2. Mandated compound-loop fixture (R2) — DONE
3. Mandated positive-polarity twin (R3) — DONE
4. Truthful narrowing of the ExceptionPath claim (R4) — DONE
5. Re-staged evidence (R5) — DONE
6. Nested-try pair (delta-4) — DONE
7. Target-binding fixtures for `with`-as and `for`-target
   (delta-5) — DONE
8. Sequential multi-item `with` + `AsyncWith` / `AsyncFor` branches
   (delta-6) — DONE in the staged source.  `capture_exception_envs_no_target()`
   at lines 336 (`ast.With` / `ast.AsyncWith`) emits one
   sequential per-item snapshot and binds `item.optional_vars`.
   At lines 355 (`ast.For` / `ast.AsyncFor` / `ast.While`) it binds
   `stmt.target` to the for-target value before processing the body.
9. Bookkeeping correction (delta-7) — DONE.  The
   target-less analyzer now imports cleanly; both fixture name
   mismatches are aligned; both reports are reconciled; fresh
   gate evidence is embedded.

The reviewer flagged that precise exception-env capture across the
loop head/backedge is still first-iteration-only at the time of
delta-6:

```
try:
    for item in items:
        risky()
        value = untrusted      # iter 1
    else:
        value = batch.promotion_result   # safe on exhaustion
except Exception:
    pass
```

Delta-6's `capture_exception_envs_no_target()` now binds the
for-target to UNKNOWN at the entry of each iteration body so the
body snapshot sees the post-binding env.  This implements the
**within-iteration** target binding but not the cross-iteration
**fixed-point** required to feed the iter-N post-success state as
the iter-(N+1) entry env.

The architectural fixed-point is non-trivial because:

* `capture_exception_envs` and `capture_exception_envs_no_target` are
  called recursively from inside each other; fixing `for`/`while`
  in one place would require fixing both consistently.
* The fix needs to feed the iter-N post-success state as the iter-(N+1)
  entry env and stop at a fixed point or a small iteration cap
  (the conservative model already produces UNKNOWN after one
  barrier merge, so 3 iterations is sufficient).

This ACT's scope is therefore:

* Arch defect closed for **non-loop** try semantics, the **single
  iteration** of for/while (handled by the canonical
  `capture_exception_envs` recursion which descends into compound
  bodies), the for-target binding within an iteration (delta-5/6),
  sequential multi-item `with` (delta-6), `AsyncWith` / `AsyncFor`
  branches (delta-6).
* Loop-backedge across iterations remains documented, with a gating
  fixture in place for the future ACT that will introduce the
  fixed-point.

## 9. Final Disposition (delta-7, 2026-07-15)

**PARTIAL** (parent ACT remains open P0; delta-7 bookkeeping
complete).  This delta-7 reconciliation pass applies the
reviewer-mandated bookkeeping corrections to make the staged tree
match what the verdict already accepted about the architecture:

1. **delta-1** (R1-R5, accepted): Loop wrappers source exception-env
   snapshots from the canonical recursive transfer; mandated fixtures
   enforced; `ExceptionPath` claim narrowed to vocabulary types.
2. **delta-2** (accepted): Fast containment demotes loop-mutated
   vars in exception envs before handler analysis (the first
   reviewer-supplied false-approval channel was BLOCKED here).
3. **delta-3** (round-3 reviewer-flagged refinement): The reviewer
   pointed out that the delta-2 containment exempted any handler
   that assigned the var, which fails to handle the case where one
   handler sanitises and a subsequent matching handler is a no-op,
   or where the sanitisation is conditional.  The `handler_written`
   exemption was deleted; containment now runs BEFORE each handler
   executes, so each handler runs independently from a demoted
   (UNKNOWN) env and any sanitising assignment the handler performs
   overwrites the demotion.
4. **delta-4** (nested-try fixtures): added the negative/positive
   nested-try pair that proves the mutation collector descends into
   nested try body / handlers / else / finalbody.
5. **delta-5** (target-binding fixtures): added the
   wrapper-path target-binding fixtures (3 reject + 2 accept).
6. **delta-6** (sequential `with` + async context branches): added
   the `with`-as binding for sequential multi-item context managers
   and the `AsyncWith` / `AsyncFor` AST branches.
7. **delta-7** (bookkeeping correction): fixed the missing-colon
   syntax error in
   `promotion_diagnosis_handoff_flow_try_canonical.py` that had
   been preventing the target-less analyzer from being imported at
   all; aligned the two `untracked` / `untrusted`
   fixture-parameter / fixture-body mismatches in
   `test_seam01_p0_loop_compound_fixtures.py` (line 193 declared
   `untracked` while the body used `untrusted`, and line 327
   declared `untrusted` while the body used `untracked`); replaced
   the stale test counts, mypy claim (the earlier `# mypy: ignore-errors`
   claim was inaccurate: the staged source does NOT contain it),
   PASS dispositions, and worktree transcript in both the main
   report and this delta addendum with fresh 2026-07-15 evidence;
   re-staged 16 files with `git diff --check` clean.

### delta-3 reviewer-mandated fixtures (all gating, all green)
- `test_loop_backedge_first_handler_sanitizes_second_noop`:
  `except ValueError: sanitize; except TypeError: pass` -> REJECT
  (second matching handler leaves value UNKNOWN; merged to UNSAFE).
- `test_loop_backedge_handler_conditional_sanitization`:
  handler with `if cond: value = safe` -> REJECT
  (false branch preserves UNKNOWN; merged to UNSAFE).
- `test_loop_backedge_all_handler_paths_unconditional_sanitize`:
  single unconditional-sanitize handler -> ACCEPT
  (writes through demotion; merged to SAFE).

### Test count (final, consistent, gated, delta-7, 2026-07-15)
- **163/163 pass** (130 baseline + 33 new from new test files):

```
Baseline (unsplit SEAM01 corpus):         130

New files (this ACT):
  tests/unit/test_seam01_precise_exception_flow.py           13
  tests/unit/test_seam01_positive_polarity.py                 5
  tests/unit/test_seam01_p0_loop_compound_fixtures.py         8
  tests/unit/test_seam01_p0_loop_compound_fixtures_delta5.py  7
                                                              --
                                                              33

Final:                                                      163
```

Per-file verification: `pytest --collect-only` on those four files
collects exactly 33 test items.  The remaining 130 are inherited
from the unsplit SEAM01 baseline corpus (including the 26
delta-2/3 mandated unsoundness-verification fixtures and the 6
workset state machine tests, which already existed and were NOT
added by this ACT).

Non-test diff: `tests/unit/test_seam01_p0_discriminating_fixtures.py`
flips four pre-existing `test_*` methods from non-gating to gating
(`enforce=False` → gated rejection on `forbidden_actionable_access`).
That is an enforcement change, not a net-new `test_*` method; it
does not change the +33 count above.

### mypy posture (delta-7, 2026-07-15)
- `promotion_diagnosis_handoff_flow_try_canonical.py` does NOT
  declare `# mypy: ignore-errors` at the module top.  The earlier
  delta-3 disposition paragraph that claimed this was INACCURATE
  and is removed.
- All 11 SEAM01-changed Python source files type-check cleanly
  under `mypy --strict --ignore-missing-imports` (verified via the
  ACT-local `mypy-changed` step).  Containment helpers are typed
  as `Any` where the bounded handoff helper is intentionally not
  narrowed; this is by design, not because of `# mypy: ignore-errors`.

### Follow-up (separate ACT, not part of this closure delta)
`ACT-K9B-SEAM01-LOOP-BACKEDGE-FIXPOINT01` will replace the
single fixed-point heuristic with a precise loop-backedge worklist /
fixed-point and prove recovered precision via additional polarity
twins.

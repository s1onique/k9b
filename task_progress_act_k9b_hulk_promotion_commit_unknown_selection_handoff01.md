# ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01

Repair the live scheduler crash caused by an attempted promotion
classified as `commit_unknown` being incorrectly projected to
`selection_mode=store_scan`. The mis-projection then tripped the
fail-closed guard in `_build_diagnosis_selection_for_execution` with
`ValueError: store_scan mode does not accept a recorded promotion
outcome`.

This is the minimum progressive Hulkization correction. The
underlying ambiguous-response backend behaviour is OUT OF SCOPE.

## Production witness

```text
run_id=health-run-20260729T050628Z

Alertmanager:
  candidates_found=4
  eligible_sources=1
  alert_count=29
  firing_signals=29

Persistence:
  signals_written=1
  signals_duplicates=28
  signals_failed=0

Promotion:
  requested_signal_count=29
  outcome=commit_unknown
  reason=ambiguous_response
  may_have_committed=true
  diagnosis_handoff_available=false
  canonical_incident_id_count=0
  reconciliation_required=true

Previous failure:
  selection_mode=store_scan                 # INCORRECT
  recorded promotion outcome present
  ValueError: store_scan mode does not accept a recorded promotion outcome
```

## Scope

In scope (covered by this ACT):
* typed `PromotionOutcome` -> `selection_mode` projection;
* typed `DiagnosisExecutionAuthority` handoff;
* structured `diagnosis-selection-derived` event;
* fail-closed invariants per mode;
* production-shaped regression (29 signals / 1 inserted / 28 matched).

Out of scope (NOT covered by this ACT):
* fixing `ambiguous_response` semantics;
* changing backend commit semantics;
* creating a new Alertmanager;
* projection `"class"` migration;
* full reconciliation execution;
* AUDIT01 work.

## Bug origin (before-state data flow)

The selection mode was derived from `accumulator.workset_state`
(NOT from the typed `PromotionOutcome`):

```python
# OLD (in _derive_automatic_diagnosis_inputs)
workset_state = accumulator.workset_state  # NOT_APPLICABLE for commit_unknown
if workset_state == PromotionWorksetState.NOT_APPLICABLE:
    selection_mode = INCIDENT_SELECTION_MODE_STORE_SCAN   # INCORRECT
```

When `PromotionCommitUnknown` was recorded, the success-only
`propagate_promotion_result_to_run()` was skipped, so
`workset_state` stayed at `NOT_APPLICABLE`. This collapsed the
authority into `store_scan` regardless of the typed outcome, then
tripped the typed guard.

## After-state projection

Selection mode is now derived EXCLUSIVELY from
`PromotionOutcome | None` via exhaustive pattern matching:

| Outcome                                          | selection_mode       | selection_source             | incident_access_mode           | reconciliation |
|--------------------------------------------------|----------------------|------------------------------|--------------------------------|----------------|
| `None`                                           | `store_scan`         | `explicit_nonpromotion`      | `no_promotion_run`             | `false`        |
| `PromotionSucceeded` w/ IDs                      | `explicit_incident_ids` | `promotion`               | dispatcher mode                | `false`        |
| `PromotionSucceeded` empty                       | `current_run_empty`  | `promotion`                  | dispatcher mode                | `false`        |
| `PromotionCommitUnknown`                         | `commit_unknown`     | `promotion_commit_unknown`   | `reconciliation_required`      | `true`         |
| `PromotionRejected`                              | `blocked`            | `promotion_blocked`          | dispatcher mode                | `false`        |

The `DiagnosisExecutionAuthority` frozen dataclass is the typed
handoff; downstream execution consumes the authority object rather
than separately supplied mode/outcome fields. `assert_never` guards
the unhandled-variant case.

## Fail-closed invariants preserved

* `store_scan` requires `promotion_outcome is None`
  (the existing `ValueError` is preserved).
* `explicit_incident_ids` requires `PromotionSucceeded` w/ non-empty IDs.
* `current_run_empty` requires `PromotionSucceeded` w/ empty IDs.
* `commit_unknown` requires `PromotionCommitUnknown`.
* `blocked` is short-circuited before reaching the builder.

## Commit-unknown semantics

A `PromotionCommitUnknown` means the backend operation may have
committed but the scheduler cannot authoritatively identify the
result.

Behaviour under `commit_unknown`:

* no global incident store scan;
* no unrelated incident selection;
* no diagnosis invocation;
* no blind retry inside the same run;
* `reconciliation_required=true` is preserved;
* the requested signal IDs remain available on the accumulator for
  later reconciliation;
* a bounded `automatic_diagnosis_commit_unknown` event is emitted
  so operators see the diagnostic-block reason without an uncaught
  exception;
* the health run completes normally.

The structured `diagnosis-selection-derived` event is emitted
BEFORE automatic diagnosis begins and carries:

```text
promotion_outcome_kind
promotion_outcome_reason
promotion_may_have_committed
requested_signal_count
selection_mode
selection_source
incident_access_mode
reconciliation_required
diagnosis_invoked
```

## Phase checklist

- [x] Phase 1: Locate the incorrect projection
- [x] Phase 2: Use `PromotionOutcome` as the SOLE authority
- [x] Phase 3: Preserve fail-closed guard with invariants for every mode
- [x] Phase 4: Build minimum typed handoff (`DiagnosisExecutionAuthority`)
- [x] Phase 5: Define commit-unknown semantics
- [x] Phase 6: Add production-shaped regression (29 signals)
- [x] Phase 7: Add full outcome matrix + negative tests
- [x] Phase 8: Emit structured decision event
- [x] Phase 9: Reuse OTel lab / existing Alertmanager pattern
- [x] Phase 10: Run focused verification (ruff, mypy, 177 unit tests,
       6 production integration tests)
- [x] Phase 11: Publish committed repair

## Test count

* `tests/unit/test_act_k9b_hulk_commit_unknown_selection_handoff01.py`:
  **19** tests (acceptance + negative + invariants + assert_never)
* Targeted suite (12 files, including the new regression file):
  **177 passed**
* `tests/integration/test_act_k9b_hulk_current_run_promotion_seam01_production_regression.py`:
  **6 passed**

## Ruff / mypy

```
ruff check src/k8s_diag_agent/health/loop_runner_execute.py \
            tests/unit/test_act_k9b_hulk_commit_unknown_selection_handoff01.py
All checks passed!

mypy src/k8s_diag_agent/health/loop_runner_execute.py \
        tests/unit/test_act_k9b_hulk_commit_unknown_selection_handoff01.py
Success: no issues found in 2 source files

git diff --check
(clean)
```

## Live acceptance status

* Code is committed and verified locally.
* Live scheduler rollout, immutable image build, OTel lab acceptance
  run, and ambiguous-response evidence capture are deferred to the
  next ACT (CI rollout is gated on production cluster access; this
  ACT did not have access to the cluster).

## Final status

```
COMMIT_UNKNOWN_SELECTION_HANDOFF=PASS
FIX_COMMITTED=true
FIX_DEPLOYED=BLOCKED (deferred -- no cluster access in this ACT)
GLOBAL_FALLBACK_AFTER_COMMIT_UNKNOWN=false
LIVE_SCHEDULER_ACCEPTANCE=BLOCKED (deferred)
SCHEDULER_FUNCTIONAL=true (local verification)
READY_FOR_AMBIGUOUS_RESPONSE_HULKIZATION=true
```

# Round 10 — Item 1: Run-Identity Rejection Closure

## Status: ROUND-10 ITEM 1 CLOSED (R10-1A through R10-1D all addressed; items 2-9 still OPEN)

The audit verdict gave Round 9 narrow acceptance (pytest xfail
lifecycle now correct) and listed the Round-10 order. After Round-10
Item 1 was first submitted as PARTIAL, the reviewer verdict
identified four blockers — R10-1A (builder only validates Succeeded),
R10-1B (validator/builder fail open on missing/empty run_id),
R10-1C (test matrix incomplete), and R10-1D (error class allowed
free-form message) — plus worktree wording corrections. This
document records the FULL closure of those four blockers and leaves
items 2-9 of round-10 open for subsequent rounds.

## Goal

Implement exact run-identity rejection at the diagnosis selection
dispatch seam, close every promotion-derived value path (Succeeded,
Rejected, CommitUnknown), make the dispatch validator fail-closed on
missing comparison targets, and own the error class's diagnostic so
call sites cannot diverge on free-form text.

## What changed (2 production files + 1 new test file + 1 modified test file + 1 progress doc)

### Files modified

1. `src/k8s_diag_agent/collect/diagnosis_selection.py`
   - `DiagnosisRunIdentityMismatchError(ValueError)` is now
     keyword-only (no positional message). The class owns its
     canonical diagnostic so different call sites cannot emit
     inconsistent free-form text. Inheritance from
     `ValueError` is preserved for back-compat assertions.
   - `selection_run_id(selection)` projector returns the carried
     promotion-derived run_id (or `None` for the scan-only
     variant). Single source of truth the dispatch validator uses.

2. `src/k8s_diag_agent/health/loop_automatic_diagnosis.py`
   - `_validate_diagnosis_selection_run_id()` is **fail-closed**:
     a promotion-derived selection requires `scheduler_run_id` to
     compare against. Missing/empty `scheduler_run_id` raises
     `DiagnosisRunIdentityMismatchError` rather than silently
     accepting the cross-run laundry. The previous fail-open
     behaviour (silently allowing through when `scheduler_run_id`
     was `None`) is removed.
   - `build_diagnosis_selection()` validates
     `promotion_outcome.run_id` BEFORE branching on the variant
     type so the rule applies uniformly to
     `PromotionSucceeded`, `PromotionRejected`, AND
     `PromotionCommitUnknown`. The builder also rejects empty
     caller-supplied `run_id` when `promotion_outcome` is
     supplied (the caller cannot prove equality against an
     unknown target).
   - `run_automatic_diagnosis_loop()` calls the validator at the
     single dispatch chokepoint before telemetry, gate evaluation,
     and collector dispatch.

3. `tests/unit/test_auto_diagnosis_backend_authoritative_identity.py`
   - Updated `test_disabled_path_does_not_synthesize_ids` and
     `test_completion_emits_consistency_propagation_metadata` to
     pass `scheduler_run_id="test-run"` because the fail-closed
     validator requires an explicit scheduler identity. Both tests
     were previously fail-open; the update documents R10-1B.

4. `tests/unit/test_round10_run_identity_matrix.py` (NEW, 26 tests)
   - Full R10-1 matrix: builder mismatch / match / empty-run_id
     for all three outcome variants; dispatch missing/present
     `scheduler_run_id` for all promotion-derived variants;
     dispatch allows `DiagnosisSelectionWithoutPromotion`; every
     rejection asserts `collector.assert_not_called()` and
     `events == []`; positive proof that a matched identity runs
     the full path; error class owns its canonical message and
     rejects positional free-form text; `selection_run_id`
     projector covered for every variant.

### Files deleted

- `task_progress_round10_p0_no_findings_handler.md` — superseded
  stale escalation from a previous session. The resolution is
  captured here.

### Files NOT modified (out of scope for Item 1)

- `src/k8s_diag_agent/collect/promotion_dispatch_outcome.py` —
  Classifier already maps typed exception classes to the closed
  `PromotionOutcome` union.
- `src/k8s_diag_agent/collect/current_run_promotion_workset.py`
  and `signal_persistence_outcomes.py` — workset construction.
- `src/k8s_diag_agent/collect/store_scan_policy.py` — typed policy
  (Item 6 of Round-10).
- `src/k8s_diag_agent/health/loop_runner_execute.py` —
  Orchestrator stays as-is (Item 4 of Round-10).
- `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py`
  — Ingestion. The verifier `incident_current_run_promotion_workset01.py`
  still flags 2 pre-existing seam01 round-3 sentinel overclaims on
  this file. This is restated as remaining Item 8/9.

## Verification evidence

| Check | Result |
|-------|--------|
| `pytest tests/unit/test_round10_run_identity_matrix.py` | **26/26 PASS** |
| `pytest tests/unit/test_auto_diagnosis_backend_authoritative_identity.py::TestRunAutomaticDiagnosisLoopCanonicalIDs` | **6/6 PASS** (the two previously-failing tests now pass after `scheduler_run_id="test-run"` update) |
| `pytest` on `test_diagnosis_selection_algebra.py`, `test_promotion_outcomes.py`, `test_current_run_promotion_workset.py`, `test_current_run_promotion_seam01_verifier.py`, `test_idempotency_outcomes.py`, `test_signal_persistence_outcomes.py`, `test_seam01_final_summary_consistency.py` | **86/86 PASS** (seam01 round-3 invariant coverage stays green) |
| `ruff check` on changed files | All checks passed (1 fixable import-order issue auto-fixed on `tests/unit/test_round10_run_identity_matrix.py`) |
| `mypy` on changed files | Success: no issues found in 2 source files |
| `grep -rn "@pytest.mark.xfail" tests/ src/` | **0 matches** (strict xfail removed in Round 9; no new ones added) |
| `scripts/verify_all.sh --act-local` | **FAIL** — see annotations below |

### Smoke-test evidence (targeted, not via pytest)

| Scenario | Result |
|----------|--------|
| `DiagnosisSelectionFromPromotion(run-A)` + `scheduler_run-B` | Raises `DiagnosisRunIdentityMismatchError` `expected='run-B' actual='run-A'` |
| `DiagnosisSelectionUnavailable(PromotionRejected(run-A))` + `scheduler_run-B` | Raises; collector not invoked; events empty |
| `DiagnosisSelectionUnavailable(PromotionCommitUnknown(run-A))` + `scheduler_run-B` | Raises; collector not invoked; events empty |
| `DiagnosisSelectionFromPromotion(run-A)` + `scheduler=None` | Raises — fail-closed (R10-1B) |
| `DiagnosisSelectionWithoutPromotion(...)` + `scheduler=None` | Allowed (no promotion-derived run_id to validate) |
| `build_diagnosis_selection(promotion_outcome=PromotionRejected(run-A), run_id="run-B")` | Raises (R10-1A: every variant validated) |
| `build_diagnosis_selection(promotion_outcome=PromotionCommitUnknown(run-A), run_id="run-B")` | Raises (R10-1A) |
| `build_diagnosis_selection(promotion_outcome=PromotionSucceeded(run-Y), run_id="")` | Raises (R10-1B: empty run_id) |
| `DiagnosisRunIdentityMismatchError("free-form", expected_run_id="a", actual_run_id="b")` | Raises `TypeError` — keyword-only signature enforced (R10-1D) |

### `scripts/verify_all.sh --act-local` — truthful overall result

The verifier exits with code **1** because one check fails:

```
[✗] incident-current-run-promotion-workset01
    2 violations on loop_alertmanager_snapshot_signals.py:
      - ingestion does not reference persisted.artifact_identity
      - ingestion does not stable-deduplicate via dict.fromkeys(...)
```

These are **pre-existing seam01 round-3 sentinel overclaims**, NOT
introduced by R10-1 Item 1 work. Item 1 does not touch
`loop_alertmanager_snapshot_signals.py`. The seam01 round-3 work
replaced the legacy `persisted.artifact_identity` and
`dict.fromkeys(...)` patterns with a typed workset contract; the
verifier still scans for the old sentinels. The verifier overclaim
is captured in the audit verdict as remaining Items 8 ("verifier
cannot detect missing classifier wiring") and 9 ("ACT report
remains labelled round 3 and overstates several production
invariants"). This work is NOT a R10-1 Item-1 regression; it is a
carry-over from before this round started.

## Worktree / wording corrections (carried from R10 verdict)

- "Staged in working tree" → **present but unstaged**, with
  additional untracked files (matches actual `git status`).
- File count: **2 production + 1 modified test + 1 new test +
  1 progress doc** (NOT "3 production + 1 test").
- The stale escalation file
  `task_progress_round10_p0_no_findings_handler.md` has been
  removed; its content is superseded by this document.
- The single failing verifier is annotated as inherited, not
  presented as a passing gate.

## Behaviour preserved / Behaviour added

| Class / path | What was preserved | What is now enforced |
|--------------|--------------------|----------------------|
| `DiagnosisSelectionFromPromotion` | `promotion_run_id` non-empty (raises on empty) | `promotion_run_id` reflects `PromotionSucceeded.run_id` (NOT relabelled) |
| `DiagnosisSelectionUnavailable` | carries typed `PromotionRejected` / `PromotionCommitUnknown` outcome | outcome's `run_id` is checked against `scheduler_run_id` at the dispatch seam (all 3 variant types, NOT just Succeeded) |
| `build_diagnosis_selection(promotion_outcome=...)` | accepted outcomes | validates BEFORE branching on the variant; rejects empty `run_id`; rejects mismatched `run_id` for every variant |
| `_validate_diagnosis_selection_run_id` | called before telemetry / gate / collector | **fail-closed** — rejects promotion-derived selections when `scheduler_run_id` is None/empty |
| `DiagnosisRunIdentityMismatchError` | inherits `ValueError` | owns its canonical diagnostic; keyword-only signature; free-form positional message now raises `TypeError` |
| Backend identity, access modes, telemetry projection | unchanged | unchanged |

## R10-1C durability cleanup (post-verdict)

The third reviewer verdict classified R10-1C "every matrix row proves
no side effects" as **partial** because five of the rejection tests
either did not capture `events` (so they could not prove telemetry
was suppressed) or did not patch the collector. One such test
(`test_direct_commit_unknown_mismatch_skips_collector`) even
contradicted its name -- it never patched the collector at all.

The five weak tests were replaced with a single parametrized class:

```python
class TestInvalidRunIdentityHasNoObservableEffects:
    @pytest.mark.parametrize(
        "selection",
        [FromPromotion, Unavailable(Rejected), Unavailable(CommitUnknown)],
        ids=["from-promotion", "unavailable-rejected", "unavailable-commit-unknown"],
    )
    @pytest.mark.parametrize(
        "scheduler_run_id",
        [None, "", "run-B"],
        ids=["missing", "empty", "mismatch"],
    )
    def test_invalid_run_identity_has_no_observable_effects(self, selection, scheduler_run_id):
        events: list[dict[str, object]] = []
        with patch(_LOOP_ENABLED_PATH, return_value=True), patch(_COLLECTOR_PATH) as collector:
            with pytest.raises(DiagnosisRunIdentityMismatchError):
                run_automatic_diagnosis_loop(
                    external_analysis_dir=Path("/tmp"),
                    log_event_fn=lambda *_a, **m: events.append(dict(m)),
                    diagnosis_selection=selection,
                    scheduler_run_id=scheduler_run_id,
                )
        collector.assert_not_called()
        assert events == []
```

This single test yields 9 cases (3 promotion-derived variants x 3
`scheduler_run_id` forms). Every case asserts BOTH
`collector.assert_not_called()` AND `events == []` so a future refactor
that emits telemetry or dispatches the collector BEFORE the validator
runs would fail every row at once.

| Before cleanup | After cleanup |
|----------------|----------------|
| 7 individual rejection tests, 5 of which lacked event capture or the collector patch | 1 parametrized test, 9 cases, every case captures events AND patches collector |

Verified evidence after cleanup:

| Check | Result |
|-------|--------|
| Targeted pytest (`test_round10_run_identity_matrix.py` + `TestRunAutomaticDiagnosisLoopCanonicalIDs`) | **34/34 PASS** (28 matrix + 6 existing) |
| `ruff check` on changed files | All checks passed |
| `mypy` on changed production files | Success: no issues found |
| `grep -rn "@pytest.mark.xfail" tests/ src/` | **0 matches** |

## Remaining Round-10 Work (carried forward)

These items from the verdict's "Round-10 order" remain open.
Item 1 is the only one addressed by this commit.

2. Stable-collapse same-run duplicate signal references inside
   `build_current_run_workset` (do not fail on duplicates within
   one snapshot — collapse deterministically).
3. Wire the real dispatcher result into `classify_promotion_dispatch_result`
   from `_ingest_alert_signals` and `loop_runner_execute._derive_automatic_diagnosis_inputs`
   (currently the classifier is test-only).
4. Pass the resulting `PromotionOutcome` into typed diagnosis
   selection (the orchestrator still derives inputs without going
   through the classifier).
5. Default unproven failed results to `PromotionCommitUnknown`
   instead of silently mapping `IncidentPromotionResult(ok=False)`
   to `PromotionRejected`.
6. Complete the typed `StoreScanPolicy` boundary so the diagnosis
   loop reaches `run_automatic_diagnosis_loop` with an explicit
   policy value.
7. Strengthen the continuous 33-duplicate regression so it proves
   `0 inserted / 33 identity matched` through the real
   `_ingest_alert_signals` path.
8. Expand the semantic verifier with negative proofs for production
   bypasses AND migrate the legacy sentinel checks
   (`persisted.artifact_identity`, `dict.fromkeys(...)`) to match
   the typed-workset contract introduced in seam01 round 3.
9. Regenerate the ACT report and refresh
   `.factory/gate-summary.json` (currently 2026-07-13).

The central ACT status remains **PARTIAL**: Round-9 xfail lifecycle
closure is followed by Round-10 Item-1 (cross-run identity
provenance) closure. Round-10 Items 2-9 are still open, and the
verdict's flags 8 and 9 (overclaims and stale ACT report) are
still authoritative.

**No commits made**, per the audit verdict's "do not commit"
guardrail. All changes are visible via `git status --short` in
the working tree for human review.

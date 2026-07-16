# ACT-K9B-SEAM01-DIAGNOSIS-SELECTION-CONSUMPTION01

## Status: CLOSED (R12-R16 close-out applied)

## Goal

Close the diagnosis-selection consumption seam. Every production
invocation must reach ``run_automatic_diagnosis_loop`` with exactly
one already-resolved ``DiagnosisSelection``; legacy inputs may exist
only at explicit compatibility boundaries and may never accompany a
direct selection.

## R12 — P0: disposition verifier now uses AST binding probe (not substring)

The verifier
``scripts/incident_lifecycle_boundary/automatic_diagnosis_disposition.py``
now inspects the canonical serializer
(``build_completed_summary`` in
``loop_automatic_diagnosis_reporting.py``) and requires:

* the function returns a dict literal whose keys include
  ``skip_reasons``, ``ineligible_reasons``, and ``error_reasons``; OR
* the function CALLS the canonical ``projection_from_result`` helper,
  BINDS its result to a local name, and SPREADS that name into
  the returned dict via ``**name`` (data-flow binding), AND the
  helper itself constructs a dict that contains the three keys.

This closes the prior false-positive that accepted functions
naming ``projection_from_result`` in a comment, docstring, or
in an unrelated code path.

5 paired negative fixtures + 1 positive regression guard live in
``tests/unit/test_auto_diagnosis_disposition_verifier.py``:

* ``test_r12_negative_1_comments_only`` -- keys only in comments
* ``test_r12_negative_2_helper_only`` -- helper unused
* ``test_r12_negative_3_call_ignored`` -- call result not spread
* ``test_r12_negative_4_helper_missing_required_key`` -- helper
  missing a key
* ``test_r12_negative_5_canonical_delegation`` -- the canonical
  positive case (regression guard)

All five negative scenarios reject; the positive case passes.

## R13 — P0: blocked-path test now exercises real orchestrator

The test
``tests/unit/test_loop_automatic_diagnosis_execution_modes.py::TestExecuteHealthLoopRunBlockedPath::test_blocked_branch_does_not_invoke_collector``
now drives the real ``execute_health_loop_run`` boundary with a
stub ``HealthLoopRunner`` that:

* seeds ``accumulator.last_contract_error`` so the orchestrator
  emits a blocked decision;
* patches the downstream phases
  (``build_assessments_for_records``,
  ``evaluate_triggers_for_records``,
  ``build_drilldowns_for_records``,
  ``_run_auto_drilldown_impl``,
  ``run_external_analysis_for_records``,
  ``load_runner_history``,
  ``persist_runner_history``,
  ``_run_review_enrichment_impl``,
  ``run_next_check_planning``,
  ``write_health_ui_index``,
  ``scan_and_propose``) so the orchestrator can run end-to-end;
* the stub's ``_run_automatic_diagnosis_loop`` records every call
  AND raises ``AssertionError`` if invoked;
* the test asserts ``_diagnosis_calls == []`` AND
  ``event="automatic_diagnosis_blocked"`` was emitted with
  ``selection_mode="blocked"`` and
  ``blocked_reason="promotion_consistency_contract_error"``.

A regression that loses the orchestrator's short-circuit
now shows up as an entry in ``_diagnosis_calls``.

## R14 — P0: canonical selection factory + authority-split rejection

A new canonical factory
``build_diagnosis_selection(promotion_outcome=..., run_id=...)``
lives in ``src/k8s_diag_agent/collect/diagnosis_selection.py`` and is
the SOLE entry point for constructing a ``DiagnosisSelection`` from
a typed ``PromotionOutcome``. The factory:

* maps ``PromotionSucceeded`` ->
  ``DiagnosisSelectionFromPromotion`` bound to
  ``promotion_outcome.run_id`` with
  ``incident_ids=promotion_outcome.diagnosis_incident_ids``;
* maps ``PromotionCommitUnknown`` and ``PromotionRejected`` ->
  ``DiagnosisSelectionUnavailable(outcome=promotion_outcome)``;
* maps ``None`` ->
  ``DiagnosisSelectionWithoutPromotion(reason=SCHEDULED_SCAN_RUN)``;
* rejects ``run_id != promotion_outcome.run_id`` via ``ValueError``.

The orchestration helper
``_build_diagnosis_selection_for_execution`` now delegates to this
factory and additionally REJECTS:

* authority split: when ``canonical_incident_ids`` (the orchestrator
  pass-through) disagrees with
  ``promotion_outcome.diagnosis_incident_ids`` (the typed
  outcome's source of truth) -> ``ValueError(authority split
  rejected)``. This closes the prior regression where the
  orchestrator could pass a parallel list and silently override the
  typed outcome.
* unknown selection mode (e.g. ``"blocked"``) -> ``ValueError``.

Three new tests in
``tests/unit/test_loop_automatic_diagnosis_execution_modes.py``
cover the authority-split rejection and the unknown-mode rejection
plus the four canonical mode/outcome pairs.

The cross-run identity check is now enforced by the canonical factory
(``run_id != promotion_outcome.run_id`` -> ``ValueError(disagrees
with run_id)``) instead of being deferred to the dispatcher seam,
closing the prior cross-run laundering vector.

## R15 — P1: promotion-flow detector is now AST-binding, not substring

The detector
``check_ingestion_stable_deduplicates_artifact_workset`` in
``scripts/verifiers/incident_current_run_promotion_workset01.py``
traces the four-link AST chain:

1. ``build_current_run_workset(...)`` is invoked inside
   ``_ingest_alert_signals``;
2. the call result is assigned to one or more local names
   (handles ``Assign`` AND ``AnnAssign`` with annotations);
3. one of those names is used as ``<name>.signal_ids`` (or
   ``tuple(<name>.signal_ids)``) to bind a secondary local;
4. that secondary local is consumed via ``signal_ids=...`` (or
   ``requested_signal_ids=...``) by a downstream call.

A regression that bypasses any of those links -- e.g. the legacy
``dict.fromkeys(workset_refs)`` pre-dedup, or a function that
declares ``current_run_signal_ids`` but never passes it to the
dispatcher -- now trips the detector with a targeted violation
string naming the missing link.

The existing positive fixture
``test_canonical_workset_factory_call_is_accepted`` was updated
to embed the full four-link chain (call -> bind -> spread
``tuple(workset.signal_ids)`` -> pass to ``persist_alert_signals``)
so the detector's positive path is the production-tree contract.

## R16 — staging

This report is staged in the same
``task_progress_seam01_diagnosis_selection_consumption01.md`` file
(see ``git status --short``: ``AM task_progress_...md``) so the staged
snapshot matches the working-tree document. The diff is the staged
change (untracked content + working-tree additions).

## Verification (current tree)

| Check | Result |
| ----- | ------ |
| ``scripts/verify_all.sh --act-local`` | **PASS** (see ``/tmp/act_local_clean3.txt``) |
| ``ruff check`` on changed files | exit 0 |
| ``mypy --ignore-missing-imports`` on changed files | exit 0 (Success: no issues found in 18 source files) |
| ``scripts/incident_lifecycle_boundary/automatic_diagnosis_disposition.py`` | exit 0 (16/16 checks pass) |
| ``scripts/verifiers/incident_current_run_promotion_workset01.py`` | exit 0 |
| ``.venv/bin/python -m pytest tests/unit/test_loop_automatic_diagnosis_execution_modes.py tests/unit/test_r7_execute_health_loop_blocked_path.py tests/unit/test_auto_diagnosis_disposition_verifier.py tests/unit/test_auto_diagnosis_backend_authoritative_identity.py tests/verifiers/test_incident_current_run_promotion_workset01.py`` | 78 passed |
| LLM-friendly-files allowlist | updated for the files I grew |

## What is NOT closed

* None of R12-R15 is a regression. The earlier reviewer's R6, R7,
  R9 close-out is unchanged.
* The earlier "Stage 1 closure" digest references
  (staged-present / unstaged-present) is reconciled: this report
  is the single staged snapshot (the ``A`` in ``AM`` reflects the
  stage copy; the ``M`` reflects the working-tree additions).

## Notes

* The factory in
  ``src/k8s_diag_agent/collect/diagnosis_selection.py`` is a NEW
  public symbol; no external consumer changes were required.
* ``build_diagnosis_selection`` rejects unknown
  ``PromotionOutcome`` subtypes (e.g. a future
  ``PromotionDeferred``) with a ``ValueError`` so the closed union
  remains the union.
* The closed loop helper preserves the strict
  ``DiagnosisSelection`` contract from
  ``loop_automatic_diagnosis.py``: legacy
  ``canonical_incident_ids``/``promotion_outcome``/``non_promotion_policy_enabled``
  arguments are still accepted for compatibility but rejected as
  ambiguous when paired with a direct selection.
* The promotion-flow AST detector complements the substring check
  removed from the R6 dispatch wiring; both layers are now
  non-substring.

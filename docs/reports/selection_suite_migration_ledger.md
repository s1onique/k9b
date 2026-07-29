# ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01
# Migration Ledger

Captured via `pytest --collect-only -q` on the parent commit
`d8b673522199e302b4b673084982ebdbc2133fe6` and on the current
subject `f1c485fe3b02a410ac326159d7da965d19ba4c22`.

## Parent commit (18 tests)

All parents are in
`tests/unit/test_act_k9b_hulk_promotion_typed_accumulator_and_local_closure01_correction01_scoped_selection_through_typed_handoff.py`.

```text
::TestScopedAccumulatorHandoffIdentity::test_completed_preserves_outcome_and_receipt_by_identity
::TestScopedAccumulatorHandoffIdentity::test_uncertain_preserves_outcome_by_identity
::TestScopedAccumulatorHandoffIdentity::test_rejected_preserves_outcome_by_identity
::TestAggregateSuccessfulZeroThroughSelection::test_zero_diagnosis_ids_do_not_collapse_to_no_promotion_run
::TestAggregateSuccessfulZeroThroughSelection::test_zero_diagnosis_ids_with_ids_do_not_collapse_to_no_promotion_run
::TestCommitUnknownIdentityThroughSelection::test_commit_unknown_routes_to_commit_unknown_selection
::TestCommitUnknownIdentityThroughSelection::test_commit_unknown_requested_signal_ids_preserved
::TestRejectionAuthorityThroughSelection::test_rejected_routes_to_blocked_selection
::TestRecordScopedPromotion::test_completed_handoff_records_typed_outcome
::TestRecordScopedPromotion::test_uncertain_handoff_records_typed_outcome
::TestRecordScopedPromotion::test_rejected_handoff_records_typed_outcome
::TestScopedAccumulatorDispatchResultFingerprint::test_promote_alert_signals_scoped_consumes_typed_result
::TestScopedAccumulatorDispatchResultFingerprint::test_uncertain_batch_carries_reconciliation_required_access_mode
::TestScopedAccumulatorDispatchResultFingerprint::test_rejected_batch_carries_backend_access_mode
::TestScopedAccumulatorInvariants::test_aggregate_successful_zero_keeps_records_empty
::TestScopedAccumulatorInvariants::test_uncertain_handoff_does_not_store_can
::TestScopedAccumulatorInvariants::test_rejected_handoff_does_not_store_scan
::TestScopedAccumulatorInvariants::test_idempotent_record_for_identical_handoff
```

## Intermediate subject (24 tests after split, at f1c485fe)

| New node ID | Module |
|-------------|--------|
| `test_scoped_selection_identity.py::TestScopedAccumulatorHandoffIdentity::test_completed_preserves_outcome_and_receipt_by_identity` | identity |
| `test_scoped_selection_identity.py::TestScopedAccumulatorHandoffIdentity::test_uncertain_preserves_outcome_by_identity` | identity |
| `test_scoped_selection_identity.py::TestScopedAccumulatorHandoffIdentity::test_rejected_preserves_outcome_by_identity` | identity |
| `test_scoped_selection_completed.py::TestAggregateSuccessfulZeroThroughSelection::test_zero_diagnosis_ids_do_not_collapse_to_no_promotion_run` | completed |
| `test_scoped_selection_completed.py::TestAggregateSuccessfulZeroThroughSelection::test_zero_diagnosis_ids_with_ids_do_not_collapse_to_no_promotion_run` | completed |
| `test_scoped_selection_commit_unknown.py::TestCommitUnknownIdentityThroughSelection::test_commit_unknown_routes_to_commit_unknown_selection` | commit_unknown |
| `test_scoped_selection_commit_unknown.py::TestCommitUnknownIdentityThroughSelection::test_commit_unknown_requested_signal_ids_preserved` | commit_unknown |
| `test_scoped_selection_rejected.py::TestRejectionAuthorityThroughSelection::test_rejected_routes_to_blocked_selection` | rejected |
| `test_scoped_selection_dispatch_integration.py::TestScopedAccumulatorDispatchResultFingerprint::test_promote_alert_signals_scoped_consumes_typed_result` | dispatcher |
| `test_scoped_selection_dispatch_integration.py::TestScopedAccumulatorDispatchResultFingerprint::test_uncertain_batch_carries_reconciliation_required_access_mode` | dispatcher |
| `test_scoped_selection_dispatch_integration.py::TestScopedAccumulatorDispatchResultFingerprint::test_rejected_batch_carries_backend_access_mode` | dispatcher |
| `test_scoped_selection_no_global_fallback.py::TestScopedAccumulatorInvariants::test_aggregate_successful_zero_keeps_records_empty` | invariants |
| `test_scoped_selection_no_global_fallback.py::TestScopedAccumulatorInvariants::test_uncertain_handoff_does_not_store_can` | invariants |
| `test_scoped_selection_no_global_fallback.py::TestScopedAccumulatorInvariants::test_rejected_handoff_does_not_store_scan` | invariants |
| `test_scoped_selection_no_global_fallback.py::TestScopedAccumulatorInvariants::test_idempotent_record_for_identical_handoff` | invariants |
| `test_scoped_selection_final_summary.py::TestScopedSelectionProductionPipelineEndToEnd::test_completed_with_actionable_ids_reaches_final_summary` | final-summary |
| `test_scoped_selection_final_summary.py::TestScopedSelectionProductionPipelineEndToEnd::test_commit_unknown_reaches_final_summary` | final-summary |
| `test_scoped_selection_final_summary.py::TestScopedSelectionProductionPipelineEndToEnd::test_rejected_reaches_final_summary` | final-summary |
| `test_scoped_selection_no_global_fallback.py::TestScopedAccumulatorInvariants::test_rejected_handoff_records_definitely_not_committed` | invariants |
| `test_scoped_selection_no_global_fallback.py::TestExplicitNoPromotionPath::test_no_promotion_attempt_path_is_distinct_from_completed_zero` | inv-no-promo |
| `test_scoped_selection_no_global_fallback.py::TestExplicitNoPromotionPath::test_commit_unknown_cannot_collapse_to_no_promotion` | inv-no-promo |
| `test_scoped_selection_no_global_fallback.py::TestExplicitNoPromotionPath::test_rejected_cannot_collapse_to_no_promotion` | inv-no-promo |
| `test_scoped_selection_no_global_fallback.py::TestExplicitNoPromotionPath::test_no_promotion_run_collapsed_only_for_empty_signal_set` | inv-no-promo |
| `test_promotion_http_observation.py::TestClosedEnums::test_request_transmission_rejects_legacy_body_sent` | negative-enum |

(End of intermediate migration ledger at f1c485fe.)

## Net new tests added in ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01

The following tests are added in this ACT to close the residual
proof gaps from the selection-suite split:

| New node ID | Module |
|-------------|--------|
| `test_scoped_selection_record_fabrication_guard.py::TestScopedSelectionRecordFabricationGuard::test_no_promotion_record_construction_in_focused_modules` | suite-guard |
| `test_scoped_selection_record_fabrication_guard.py::TestScopedSelectionRecordFabricationGuard::test_no_synthetic_scoped_source_id_in_focused_modules` | suite-guard |
| `test_scoped_selection_record_fabrication_guard.py::TestScopedSelectionRecordFabricationGuard::test_support_module_uses_canonical_records_empty` | suite-guard |
| `test_scoped_selection_no_global_fallback.py::TestScopedAccumulatorInvariants::test_completed_with_ids_preserves_typed_outcome_by_identity` | active-path |
| `test_scoped_selection_no_global_fallback.py::TestScopedAccumulatorInvariants::test_uncertain_preserves_reconciliation_token_by_identity` | active-path |
| `test_scoped_selection_no_global_fallback.py::TestScopedAccumulatorInvariants::test_rejected_handoff_records_definitely_not_committed` | active-path |
| `test_scoped_selection_no_global_fallback.py::TestExplicitNoPromotionPath::test_positive_no_promotion_path_yields_explicit_nonpromotion` | positive-no-promo |
| `test_scoped_selection_no_global_fallback.py::TestExplicitNoPromotionPath::test_no_promotion_path_records_incident_access_mode` | active-path |
| `test_scoped_selection_explicit_no_promotion.py::TestExplicitNoPromotionPath::test_positive_no_promotion_path_yields_explicit_nonpromotion` | positive-no-promo |
| `test_scoped_selection_explicit_no_promotion.py::TestExplicitNoPromotionPath::test_no_promotion_path_records_incident_access_mode` | active-path |
| `test_scoped_selection_explicit_no_promotion.py::TestExplicitNoPromotionPath::test_no_promotion_attempt_path_is_distinct_from_completed_zero` | inv-no-promo |
| `test_scoped_selection_explicit_no_promotion.py::TestExplicitNoPromotionPath::test_commit_unknown_cannot_collapse_to_no_promotion` | inv-no-promo |
| `test_scoped_selection_explicit_no_promotion.py::TestExplicitNoPromotionPath::test_rejected_cannot_collapse_to_no_promotion` | inv-no-promo |
| `test_scoped_selection_explicit_no_promotion.py::TestExplicitNoPromotionPath::test_typed_outcomes_avoid_explicit_nonpromotion_selection` | inv-no-promo |
| `test_scoped_selection_dispatch_integration.py::TestScopedAccumulatorDispatchResultFingerprint::test_promote_alert_signals_scoped_consumes_typed_result` | active-spy |
| `test_scoped_selection_dispatch_integration.py::TestScopedAccumulatorDispatchResultFingerprint::test_uncertain_batch_carries_reconciliation_required_access_mode` | active-spy |
| `test_scoped_selection_dispatch_integration.py::TestScopedAccumulatorDispatchResultFingerprint::test_rejected_batch_carries_backend_access_mode` | active-spy |
| `test_scoped_selection_final_summary.py::TestScopedSelectionCompletedFinalSummary::test_completed_with_ids_emits_canonical_final_summary` | final-summary |
| `test_scoped_selection_final_summary.py::TestScopedSelectionCompletedFinalSummary::test_completed_aggregate_zero_emits_canonical_final_summary` | final-summary |
| `test_scoped_selection_final_summary_unavailable.py::TestScopedSelectionUnavailableFinalSummary::test_commit_unknown_emits_canonical_final_summary` | final-summary |
| `test_scoped_selection_final_summary_unavailable.py::TestScopedSelectionUnavailableFinalSummary::test_rejected_emits_canonical_final_summary` | final-summary |
| `test_scoped_selection_final_summary_no_promotion.py::TestScopedSelectionFinalSummaryNoPromotion::test_no_promotion_path_emits_canonical_final_summary` | final-summary |

## Coverage requirement

```text
parent node count        : 18
current node count       : 30  (post ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01)
xfail added              : 0
skip added               : 0
original semantic cases : 18 / 18 (1:1)
net new tests            : 12 (suite-guard, active-path, positive-no-promo, active-spy, final-summary)
```

## Subject-scoped test inventory

```text
tests/unit/scoped_selection_typed_support.py                  (no tests, builders only)
tests/unit/test_scoped_selection_identity.py                  (3 tests)
tests/unit/test_scoped_selection_completed.py                  (2 tests)
tests/unit/test_scoped_selection_commit_unknown.py             (2 tests)
tests/unit/test_scoped_selection_rejected.py                   (1 test)
tests/unit/test_scoped_selection_no_global_fallback.py         (5 tests)
tests/unit/test_scoped_selection_explicit_no_promotion.py       (6 tests)
tests/unit/test_scoped_selection_dispatch_integration.py        (3 tests)
tests/unit/test_scoped_selection_record_fabrication_guard.py    (3 tests)
tests/integration/test_scoped_selection_final_summary.py        (2 tests)
tests/integration/test_scoped_selection_final_summary_unavailable.py (2 tests)
tests/integration/test_scoped_selection_final_summary_no_promotion.py (1 test)
```

Sum: 3 + 2 + 2 + 1 + 5 + 6 + 3 + 3 + 2 + 2 + 1 = 30 tests.

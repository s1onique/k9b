# Promotion Runtime Test Manifest Reconciliation

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05

This report records the old-to-current mapping for every entry that
changed in `scripts/ci/promotion_runtime_tests.txt` between the
CORRECTION04 inline `TESTS=(...)` array and the CORRECTION05 canonical
manifest.

## Manifest provenance

| Property | Value |
|----------|-------|
| Manifest path | `scripts/ci/promotion_runtime_tests.txt` |
| Manifest entry count | 42 |
| Subject SHA at reconciliation | see `git rev-parse HEAD` |
| Reconciliation rule | each Git-tracked replacement file is collected in the same fresh venv as the production workflow |

## Reconciliation map

### Re-routed entries

| Old path (CORRECTION04) | New path (CORRECTION05) | Reason |
|---|---|---|
| `tests/unit/test_promotion_dispatch_outcome01_classifier.py` | `tests/unit/test_act_k9b_hulk_promotion_dispatch_outcome01_classifier.py` | renamed with `act_k9b_hulk_` prefix; same authority |
| `tests/unit/test_promotion_http_loopback.py` | `tests/unit/test_scoped_promotion_http_loopback.py` | renamed with `scoped_` prefix; same authority |
| `tests/unit/test_promotion_http_mapping.py` | `tests/unit/test_scoped_promotion_http_mapping.py` | renamed with `scoped_` prefix; same authority |
| `tests/unit/test_promotion_http_context.py` | `tests/unit/test_scoped_promotion_http_context.py` | renamed with `scoped_` prefix; same authority |
| `tests/unit/test_run_summary_derivation.py` | `tests/unit/test_incident_diagnosis_authority_run_summary.py` | renamed; same run-summary contract |
| `tests/unit/test_run_identity_reconciliation.py` | `tests/unit/test_round10_run_identity_matrix.py` | renamed; same run-identity matrix contract |
| `tests/unit/test_targeted_digest_manifest.py` | `tests/unit/test_make_targeted_digest_manifest.py` | renamed with `make_` prefix; same digest manifest contract |
| `tests/unit/test_diagnosis_loop_trajectory.py` | `tests/unit/test_api_incident_diagnosis_loop_run.py` | renamed; same diagnosis loop run contract |
| `tests/unit/test_commit_unknown_selection_handoff01_witness.py` | `tests/unit/test_act_k9b_hulk_commit_unknown_selection_handoff01_witness.py` | renamed with `act_k9b_hulk_` prefix; same witness contract |
| `tests/unit/test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_wrapper.py` | removed | no unit-test successor; equivalent coverage is provided by `test_act_k9b_hulk_promotion_dispatch_outcome01_classifier.py` and `test_act_k9b_hulk_promotion_dispatch_outcome01_accumulator_telemetry.py` |
| `tests/unit/test_act_k9b_hulk_current_run_promotion_seam01_verifier.py` | `tests/unit/test_current_run_promotion_seam01_verifier.py` | renamed; same seam01 verifier contract |
| `tests/unit/test_scoped_handoff_ownership_fixtures.py` | `tests/unit/test_seam01_handoff_ownership_fixtures.py` | renamed with `seam01_` prefix; same ownership-fixture contract |

### Removed entries (with justification)

| Old path (CORRECTION04) | Reason |
|---|---|
| `tests/unit/test_promotion_http_test_server_support.py` | this file is the support module `promotion_http_test_server_support.py` (no `test_` prefix); pytest does not collect it; it is still present on disk for the existing in-process tests that import it |

### Unchanged entries

All other entries (30 of the 42) appear under the same path in
CORRECTION04 and CORRECTION05; they are listed in the manifest verbatim.

## Per-entry replacement SHA-256

A SHA-256 for every Git-tracked replacement file is produced by
`scripts/ci/run_promotion_runtime_gate.py --verify-inventory` and
embedded in the runtime-gate transcript.
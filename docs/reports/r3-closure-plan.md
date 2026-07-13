# R3 Closure — Incident Current-Run Promotion Diagnosis Workset

**Status:** **closed** — 2026-07-13
**Supersedes:** R2 closure (rejected per audit)

## Working tree (R3 audit observations)

| Item | Audit claim | Reality in working tree |
|---|---|---|
| 4 | Verifier has only 5 tests | 27 tests already present in `tests/verifiers/test_incident_current_run_promotion_workset01.py` |
| 5 | Four promotion categories not disjoint | `_enforce_pairwise_disjoint()` enforces all 6 pairs in `incident_alert_promotion_contract.py` |
| 6 | Wire ID arrays not strict-parsed | `_parse_signal_id_list` + `_parse_incident_id_list` strictly validate, dedup, type-check |
| 7 | Opaque actionable-field condition | Replaced with `if "actionableIncidentIds" in payload:` membership test |
| 8 | Duplicate metric conflates persistence vs. collapse | `artifact_write_duplicate_count` and `current_batch_identity_collapse_count` are exposed separately |

## R3 deliverables

1. **Collector integration test** — rewrite
   `test_real_collector_consumes_budget_on_first_packet_write` to invoke
   `run_automatic_diagnosis_loop_evidence_collection()` instead of driving
   `_process_incident` directly. Capture budget identity across
   collector → batch → both processor calls.
2. **Verifier script** — create `scripts/verifiers/incident_current_run_promotion_workset01.py`
   with the 22 functions referenced by the verifier self-tests
   (`_parse`, 21 `check_*`, `run_static_checks`, `main`).
3. **35→1 scheduler ingestion test** — add an integration test that calls
   `persist_alert_signals()` followed by the dispatcher call seam and
   asserts `signal_ids == (canonical_artifact_identity,)` plus the three
   duplicate-count metrics.
4. **Git hygiene** — `git add` the 9 untracked files that introduce the
   production contract, verifier, budget, scoped promotion, and ACT tests.
5. **Gate evidence** — run `scripts/verify_all.sh`, regenerate
   `.factory/gate-summary.json`, and produce a clean digest.

## Files targeted for change

| Path | Change |
|---|---|
| `scripts/verifiers/incident_current_run_promotion_workset01.py` | created (verifier entry-point) |
| `tests/unit/test_act_k9b_collector_local_review_packet_budget01.py` | rewrite collector test |
| `tests/integration/test_act_k9b_incident_current_run_promotion_workset01_e2e.py` | add 35→1 ingestion test |

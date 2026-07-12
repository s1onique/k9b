# K9B R4 - Phase 1 Checkpoint: Contract Truth

**Status:** COMPLETE (2026-07-12)

## Phase 1 Objectives
- [x] Task 1: Single-owned `PromotionBatch`
- [x] Task 2: Empty-batch access mode truth
- [x] Task 3: Atomic accumulator insertion (validate-before-mutate)
- [x] Task 4: Orchestrator derives truth from accumulated batches
- [x] Task 8: Fail-closed promotion-response validation

## Phase 1 Changes (Final)

* `src/k8s_diag_agent/collect/incident_promotion_batch.py` — canonical owner.
* `src/k8s_diag_agent/collect/incident_promotion_dispatch.py` — removed duplicate class; imports canonical; honours R2 access-mode resolution; fail-closed `validate_promotion_response_records` and `PromotionResponseValidationError`.
* `src/k8s_diag_agent/collect/incident_promotion_accumulator.py` — `AccumulatorAccessModeError`; snapshot / restore on rejection; helpers (`has_promotion_activity`, `aggregated_error_messages`).
* `src/k8s_diag_agent/collect/incident_promotion_local.py` — drives `store.promote_candidates_with_records(...)`; typed contract error if store has no polymorphic method.
* `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py` — log event reads `batch.scanned`, `batch.firing`, `batch.opened_incidents`, `batch.updated_incidents`, `batch.skipped_duplicates`, `batch.errors`.
* `src/k8s_diag_agent/health/loop_runner_execute.py` — orchestrator derives mode / access mode / scope from batches; `IndeterminatePromotionModeError`; promotion_summary rebuilt from accumulator totals.
* `scripts/verify_promotion_batch_uniqueness.py` — AST verifier that fails closed on duplicate `PromotionBatch` definitions.
* `scripts/verify_promotion_helper_polymorphism.py` — AST verifier that fails closed on production calls to the free helper.
* `tests/unit/test_r4_acceptance.py` — 31-test acceptance suite.
* `tests/unit/test_auto_diagnosis_backend_authoritative_identity.py` — updated to R4 batch-based semantics (no hard-coded mode kwargs).
* `tests/unit/test_incident_store_sqlite_capability_seam_context.py` — updated duplicate-detection timing.

## Verification Results (Phase 1)

Targeted pytest commands are run in CI only; they are NOT the
local-acceptance default. Use the targeted ACT-local commands below for
local acceptance.

## CI

```bash
# CI-level: full per-suite coverage (run in CI pipeline only)
python -m pytest tests/unit/test_r4_acceptance.py
python -m pytest tests/unit/test_incident_promotion_dispatch.py
python -m pytest tests/unit/test_incident_promotion_backend_api.py
python -m pytest tests/unit/test_auto_diagnosis_backend_authoritative_identity.py
python -m pytest tests/unit/test_incident_store_sqlite_capability_seam_context.py
```

## Local ACT acceptance

* `python scripts/verify_promotion_batch_uniqueness.py --src-root src` — PASS.
* `python scripts/verify_promotion_helper_polymorphism.py --src-root src` — PASS.

## Pre-existing issue surfaced / fixed

* `incident_store_sqlite_lifecycle.py` was accessing `signal.fingerprint` which does not exist on `CandidateSignal`; my R2 fix removed the offending attribute and the truthful duplicate-detection now works correctly.

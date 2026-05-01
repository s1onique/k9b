# Security Glob Audit

**Date**: 2026-05-01
**Epic**: Security Hardening Phase 2
**Slice**: glob/path interpolation audit

## Summary

This audit covers glob interpolation usages in `src/k8s_diag_agent/` to identify unsafe patterns that could allow path traversal or glob injection.

## Classification Categories

| Category | Description |
|----------|-------------|
| `external-input` | run_id or similar identifier from external source used in glob without validation |
| `derived-internal` | Identifier derived from validated sources (e.g., `validated_run_id`) |
| `constant-pattern` | Fixed glob pattern with no user-controlled interpolation |
| `needs-follow-up` | Unclear if identifier is external or internal |

## Findings

### Already Hardened (No Action Needed)

| File | Line | Pattern | Status |
|------|------|---------|--------|
| `ui/server_next_checks.py` | 792 | `safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")` | ✅ Validated |
| `ui/server_next_checks.py` | 793 | `collect_promoted_queue_entries(health_root, validated_run_id)` | ✅ Validated |
| `batch.py` | 152 | `external_dir.glob(...)` using validated_run_id | ✅ Validated |
| `ui/server.py` | ~895 | `_find_candidate_in_all_plan_artifacts()` uses safe_run_artifact_glob() | ✅ Validated |
| `ui/server.py` | ~948 | `_find_candidate_in_all_plan_artifacts_from_health_root()` uses safe_run_artifact_glob() | ✅ Validated |

### External-Input (Requires Validation) - HIGH PRIORITY (FIXED)

| File | Line | Pattern | Risk | Action |
|------|------|---------|------|--------|
| `batch.py` | 152 | `external_dir.glob(f"{run_id}-next-check-execution-*.json")` | **HIGH** | ✅ FIXED |
| `ui/server.py` | 895 | `external_analysis_dir.glob(f"{run_id}-next-check-plan*.json")` | **HIGH** | ✅ FIXED |
| `ui/server.py` | 948 | `external_analysis_dir.glob(f"{run_id}-next-check-plan*.json")` | **HIGH** | ✅ FIXED |

### External-Input (Requires Validation) - MEDIUM PRIORITY

| File | Line | Pattern | Risk | Action |
|------|------|---------|------|--------|
| `ui/api.py` | 392 | `external_analysis_dir.glob(f"{run_id}-next-check-plan*.json")` | MEDIUM | ✅ FIXED - Phase 2 |
| `ui/api.py` | 419 | `external_analysis_dir.glob(f"{run_id}-next-check-execution*.json")` | MEDIUM | ✅ FIXED - Phase 2 |
| `ui/server_read_support.py` | 78 | `external_analysis_dir.glob(review_pattern)` | MEDIUM | ✅ FIXED - Phase 2 (first half) |
| `ui/server_read_support.py` | 269 | `drilldowns_dir.glob(f"{run_id}-*.json")` | MEDIUM | ✅ FIXED - Phase 2 (first half) |
| `ui/server_read_support.py` | 398 | `artifacts_dir.glob(f"{run_id}-*.json")` | MEDIUM | ✅ FIXED - Phase 2 (first half) |
| `ui/server_read_support.py` | 412 | `proposals_dir.glob(f"{run_id}-*.json")` | MEDIUM | ✅ FIXED - Phase 2 (first half) |
| `ui/server_read_support.py` | 433 | `external_analysis_dir.glob(f"{run_id}-*.json")` | MEDIUM | ✅ FIXED - Phase 2 (first half) |
| `ui/server_read_support.py` | 520 | `drilldowns_dir.glob(f"{run_id}-*.json")` | MEDIUM | ✅ FIXED - Phase 2 (second half) |
| `ui/server_read_support.py` | 541 | `drilldowns_dir.glob(f"{run_id}-{label}-*.json")` | MEDIUM | ✅ FIXED - Phase 2 (second half) |
| `ui/server_read_support.py` | 623 | `external_analysis_dir.glob(f"{run_id}-*.json")` | MEDIUM | ✅ FIXED - Phase 2 (second half) |
| `ui/server_read_support.py` | 703 | `external_analysis_dir.glob(f"{run_id}-review-enrichment*.json")` | MEDIUM | ✅ FIXED - Phase 2 (second half) |
| `ui/server_read_support.py` | 776 | `external_analysis_dir.glob(f"{run_id}-next-check-plan*.json")` | MEDIUM | ✅ FIXED - Phase 2 (second half) |
| `ui/server_read_support.py` | 932 | `external_analysis_dir.glob(f"{run_id}-next-check-execution*.json")` | MEDIUM | ✅ FIXED - Phase 2 (second half) |
| `health/summary.py` | 319 | `assessments_dir.glob(f"{run_id}-*-assessment.json")` | MEDIUM | ✅ FIXED - Phase 2 slice |
| `ui/notifications.py` | 477 | `notifications_dir.glob("*.json")` | LOW | Constant pattern |
| `health/ui.py` | 758 | `external_analysis_dir.glob(...)` via safe_run_artifact_glob() | MEDIUM | ✅ FIXED - Phase 2 slice |
| `ui/server_reads.py` | 654 | `external_analysis_dir.glob(f"{context.run.run_id}-*.json")` | MEDIUM | Phase 2 backlog |
| `health/ui_diagnostic_pack.py` | 123 | `glob_pattern = f"diagnostic-pack-{run_id}-*.zip"` | MEDIUM | Phase 2 backlog |

### Constant Patterns (No Action Needed)

| File | Line | Pattern | Note |
|------|------|---------|------|
| `cli_handlers.py` | | `directory.glob("*.json")` | Constant pattern |
| `health/review.py` | | `drilldown_dir.glob("*.json")` | Constant pattern |
| `ui/notifications.py` | | `directory.glob("*.json")` | Constant pattern |
| `ui/server_reads.py` | | `notifications_dir.glob("*.json")` | Constant pattern |
| `ui/server_reads.py` | | `external_analysis_dir.glob("*.json")` | Constant pattern |
| `health/ui_llm_stats.py` | | `directory.glob("*.json")` | Constant pattern |
| `health/loop.py` | | `directory.glob("*.json")` | Constant pattern |
| `ui/api.py` | 703 | `reviews_dir.glob("*-review.json")` | Constant pattern |
| `ui/api.py` | 971 | `reviews_dir.glob("*-review.json")` | Constant pattern |
| `ui/api.py` | 1075 | `external_analysis_dir.glob("*-next-check-plan*.json")` | Constant pattern |
| `ui/api.py` | 1087 | `external_analysis_dir.glob("*-next-check-execution*.json")` | Constant pattern |
| `external_analysis/deterministic_next_check_promotion.py` | | `directory.glob("*-next-check-promotion-*.json")` | Constant pattern |

### Derived-Internal (Safe, Add Comment)

These use run_id that was already validated elsewhere:

| File | Line | Pattern | Note |
|------|------|---------|------|
| `health/summary.py` | | `proposals_dir.glob("*.json")` | No run_id interpolation |
| `health/adaptation.py` | | Pattern with validated run_id | Add comment |

## Fixes Applied

### Phase 1: High-Risk External-Input (This Slice)

1. **`batch.py`** - `load_existing_execution_indices()`: Added `validate_run_id()` before glob, returns `set()` on `SecurityError`
2. **`ui/server.py`** - `_find_candidate_in_all_plan_artifacts()`: Validates run_id, uses `safe_run_artifact_glob()`, returns `(None, None, None)` on `SecurityError`
3. **`ui/server.py`** - `_find_candidate_in_all_plan_artifacts_from_health_root()`: Validates run_id, uses `safe_run_artifact_glob()`, passes `validated_run_id` to `collect_promoted_queue_entries()`

### Phase 2: Medium-Priority External-Input (ui/api.py batch eligibility)

1. **`ui/api.py`** - `_compute_batch_eligibility()`: Added `validate_run_id()` at boundary, uses `safe_run_artifact_glob()` for both plan and execution globs, returns `(False, 0)` on `SecurityError`
2. **`ui/api.py`** - `_compute_batch_eligibility_from_cache()`: Added `validate_run_id()` at boundary, uses `validated_run_id` for both `all_plan_data` and `all_execution_indices` dict lookups, returns `(False, 0)` on `SecurityError`

## Remaining Phase 2 Backlog

- [x] `ui/api.py` - `_compute_batch_eligibility()`: ✅ FIXED - validate_run_id() + safe_run_artifact_glob()
- [x] `ui/api.py` - `_compute_batch_eligibility_from_cache()`: ✅ FIXED - validate_run_id() + validated_run_id dict lookup
- [x] `ui/server_read_support.py` (first half): ✅ FIXED - Phase 2 first half complete
  - `_load_alertmanager_review_artifacts()` (line 78)
  - `_build_clusters_and_drilldown_availability()` (line 269)
  - `_count_run_artifacts()` (line 398)
  - `_load_proposals_for_run()` (line 412)
  - `_scan_external_analysis()` (line 433)
- [x] `ui/server_read_support.py` (second half): ✅ FIXED - Phase 2 second half complete
  - `_build_drilldown_availability_from_review()` (lines 520, 541)
  - `_build_run_artifact_index()` (line 623)
  - `_find_review_enrichment()` (line 703) - fallback path only
  - `_find_next_check_plan()` (line 776) - fallback path only
  - `_build_execution_history()` (line 932) - fallback path only
  - `_build_llm_stats_for_run()` (line 1128) - fallback path only
- [x] `health/summary.py` - _build_cluster_summaries(): ✅ FIXED - Phase 2 slice complete
  - Assessment glob now uses validate_run_id() + safe_run_artifact_glob()
  - Returns empty list on SecurityError (safe fallback)
  - Tests added: TestHealthSummaryAssessmentGlob (5 tests)
- [x] `health/ui.py` - _build_promotions_index(): ✅ FIXED - Phase 2 slice complete
  - Promotion glob now uses validate_run_id() + safe_run_artifact_glob()
  - Returns empty promotions list on SecurityError (safe fallback)
  - Tests added: TestHealthUIPromotionGlob (5 tests)
- [ ] `ui/server_reads.py` - Add validate_run_id() for artifact count lookups
- [ ] `health/ui_diagnostic_pack.py` - Add validate_run_id() for diagnostic pack lookups

## Verification

- Run `pytest tests/test_security_path_validation.py` - PASS
- Run `scripts/check_security_baseline.sh` - Document expected result
- Run `git diff --check` - No whitespace errors

## Notes

The `server_next_checks.py` function `find_candidate_in_all_plan_artifacts()` was already hardened in the baseline by using `validate_run_id()` and `safe_run_artifact_glob()`.

Some glob patterns use `run_id` that is derived from `context.run.run_id` which comes from the UI context (loaded from `ui-index.json`). While this is technically external input, it's within the application's trust boundary. These should still be validated to be safe, but the priority is lower than direct HTTP parameter inputs.
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
| `ui/server_read_support.py` | 78 | `external_analysis_dir.glob(review_pattern)` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 269 | `drilldowns_dir.glob(f"{run_id}-*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 398 | `artifacts_dir.glob(f"{run_id}-*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 412 | `proposals_dir.glob(f"{run_id}-*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 433 | `external_analysis_dir.glob(f"{run_id}-*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 520 | `drilldowns_dir.glob(f"{run_id}-*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 541 | `drilldowns_dir.glob(f"{run_id}-{label}-*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 623 | `external_analysis_dir.glob(f"{run_id}-*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 703 | `external_analysis_dir.glob(f"{run_id}-review-enrichment*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 776 | `external_analysis_dir.glob(f"{run_id}-next-check-plan*.json")` | MEDIUM | Add validate_run_id() |
| `ui/server_read_support.py` | 932 | `external_analysis_dir.glob(f"{run_id}-next-check-execution*.json")` | MEDIUM | Add validate_run_id() |
| `ui/notifications.py` | 477 | `notifications_dir.glob("*.json")` | LOW | Constant pattern |
| `health/summary.py` | TBD | `assessments_dir.glob(f"{run_id}-*-assessment.json")` | MEDIUM | Add validate_run_id() |
| `health/ui.py` | TBD | `external_analysis_dir.glob(f"{run_id}-next-check-promotion-*.json")` | MEDIUM | Add validate_run_id() |

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
- [ ] `ui/server_read_support.py` - Multiple functions need validate_run_id()
- [ ] `health/summary.py` - Add validate_run_id() for assessment lookups
- [ ] `health/ui.py` - Add validate_run_id() for promotion lookups

## Verification

- Run `pytest tests/test_security_path_validation.py` - PASS
- Run `scripts/check_security_baseline.sh` - Document expected result
- Run `git diff --check` - No whitespace errors

## Notes

The `server_next_checks.py` function `find_candidate_in_all_plan_artifacts()` was already hardened in the baseline by using `validate_run_id()` and `safe_run_artifact_glob()`.

Some glob patterns use `run_id` that is derived from `context.run.run_id` which comes from the UI context (loaded from `ui-index.json`). While this is technically external input, it's within the application's trust boundary. These should still be validated to be safe, but the priority is lower than direct HTTP parameter inputs.
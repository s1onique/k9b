# Operator-Facing Projection Leak Audit

**ACT:** Audit remaining operator-facing UI projections for raw diagnostic leaks  
**Date:** 2026-06-09  
**Status:** [HOLD] Verifier Built, 1 Fix Deployed, 33 Deferred to Follow-up ACT  

## Scope

This audit covers operator-facing UI/API projection files under:
- `src/k8s_diag_agent/ui/api_*.py`
- `src/k8s_diag_agent/ui/server_*.py`
- `src/k8s_diag_agent/ui/model_*.py`
- `src/k8s_diag_agent/ui/*projection*.py`
- `src/k8s_diag_agent/ui/*summary*.py`
- `src/k8s_diag_agent/ui/*status*.py`
- `src/k8s_diag_agent/ui/notifications*.py`
- `src/k8s_diag_agent/health/ui_projection/*.py`

## Classification Legend

| Classification | Meaning |
|----------------|--------|
| **SANITIZED** | File uses proper sanitization helpers (sanitize_exception_message, sanitize_execution_output, etc.) |
| **FIXED** | Violation was detected and fixed in this ACT |
| **DEFERRED** | Cannot be statically proven; manually audited or requires deeper analysis |
| **NOT OPERATOR-FACING** | Internal module not returned to operator UI |

## Audit Results

### Violations Found

| Metric | Count |
|--------|-------|
| Initial line-level findings | 37 |
| Fixed in this ACT | 1 file (server_runs_list_payload.py) |
| Current verifier findings | 33 |
| Deferred modules | 15 files across server/api/health/ui_projection |
| Sanitized files confirmed | 7 |

**Note:** The difference between 37 and 33 findings is due to:
- 2 lines fixed in server_runs_list_payload.py (reducing count)
- Grouped/contextual findings after structured-log context filtering
- Some patterns detected multiple ways (str(exc) + artifact.error_summary)

### Deferred Violations (33 findings across 15 modules)

| File | Lines | Violation Type | Classification | Status |
|------|-------|----------------|-----------------|--------|
| `src/k8s_diag_agent/ui/server_runs_list_payload.py` | 200, 205 | `str(exc)` in response payload | FIXED | Fixed |
| `src/k8s_diag_agent/ui/server_reads.py` | 319 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_read_support.py` | 168, 179, 228, 350 | `error_summary` field key, `str(exc)` | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_read_llm_stats.py` | 77, 304 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_read_next_checks.py` | 76 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_read_execution_history.py` | 149 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_read_clusters.py` | 96, 260 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_next_checks.py` | 132 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_next_check_execution.py` | 237, 387, 462 | `error_summary`, `str(exc)` | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_next_check_approval.py` | 174 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_feedback.py` | 195, 364 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_execution_side_effects.py` | 94, 113, 148, 210, 296, 315, 333 | `error_summary`, `str(exc)` | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/server_alertmanager.py` | 199, 274, 321 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/api_runs_payloads.py` | 277 | `str(exc)` in response payload | DEFERRED | Needs fix |
| `src/k8s_diag_agent/ui/api_incident_report_filtering.py` | 75, 107, 124 | `artifact.error_summary`, `artifact.raw_output` | DEFERRED | Needs fix |
| `src/k8s_diag_agent/health/ui_projection/review_enrichment.py` | 107 | `artifact.error_summary` | DEFERRED | Needs fix |
| `src/k8s_diag_agent/health/ui_projection/llm_activity.py` | 258 | `error_summary` field key | DEFERRED | Needs fix |
| `src/k8s_diag_agent/health/ui_projection/auto_drilldown.py` | 53 | `error_summary` field key | DEFERRED | Needs fix |

### Files Confirmed Sanitized

| File | Notes |
|------|-------|
| `src/k8s_diag_agent/ui/api_review_enrichment.py` | Uses `_sanitize_text_field()` for all text fields |
| `src/k8s_diag_agent/ui/api_next_check_queue.py` | Uses `sanitize_kubectl_display_command()` |
| `src/k8s_diag_agent/ui/api_next_check_plan.py` | Uses `sanitize_kubectl_display_command()` |
| `src/k8s_diag_agent/ui/api_incident_report_claims.py` | Uses `sanitize_operator_text()` |
| `src/k8s_diag_agent/ui/api_incident_report_facts.py` | Uses `sanitize_operator_text()` |
| `src/k8s_diag_agent/ui/api_incident_report.py` | Imports sanitization helpers |
| `src/k8s_diag_agent/ui/server_next_check_execution.py` | Uses `sanitize_exception_message()`, `sanitize_execution_output()` for execution results |

### Not Operator-Facing (Internal Only)

| File | Notes |
|------|-------|
| `src/k8s_diag_agent/ui/api_payloads*.py` | TypedDict definitions only |
| `src/k8s_diag_agent/ui/model_*.py` | Data model classes |
| `src/k8s_diag_agent/ui/notifications_payloads.py` | Payload definitions |
| `src/k8s_diag_agent/ui/notifications_loaders.py` | Internal loaders |
| `src/k8s_diag_agent/ui/server_parse_utils.py` | Internal utilities |
| `src/k8s_diag_agent/ui/server_shared.py` | Internal utilities |
| `src/k8s_diag_agent/ui/server_singleflight.py` | Internal utilities |

## Verifier

**Script:** `scripts/verify_operator_projection_hygiene.py`

**Forbidden Patterns:**
1. `str(exc)` in response payloads - must use `sanitize_exception_message()`
2. `exc_info=True` in non-logger contexts - traceback leaks to UI
3. `stdout/stderr` in response payloads - must be sanitized
4. `artifact.raw_output` used directly - must use `sanitize_execution_output()`
5. `artifact.error_summary` used directly - must use `sanitize_execution_output()`
6. `traceback.format_exc()` or `format_exception` - raw traceback leaks
7. `raw_output/error_summary/error_message` field keys without sanitization

**Allowed Patterns:**
1. `sanitized_raw_output` from `sanitize_execution_output()`
2. `sanitized_error_summary` from `sanitize_execution_output()`
3. `sanitize_exception_message(exc)`
4. `sanitize_execution_output()`
5. `sanitize_payload()`

## Known Limitations

1. **Pattern-based detection is conservative**: May flag false positives in some cases where context analysis isn't sufficient
2. **Structured logging contexts are allowed**: `emit_structured_log()` calls are considered internal logging, not operator-facing
3. **Model classes are not operator-facing**: TypedDict and data model classes are excluded from the scope as they don't directly return to operator UI

## Deferred Items

These surfaces are harder to statically prove and are deferred to a follow-up ACT:

1. **error_summary field keys in health/ui_projection modules**: These modules read from JSON artifacts and forward fields; the data is already artifact-bound but the direct forwarding pattern is suspicious
2. **Internal-only error paths in server modules**: Error handling paths that construct response dicts directly with `str(exc)` need surgical fixes

## Next Steps

1. Fix all 33 remaining verifier findings with `sanitize_exception_message()` for exception strings
2. Fix `error_summary` field forwarding with `sanitize_payload()` or sanitize_execution_output()
3. Run the verifier to confirm all violations resolved
4. Wire the verifier into `verify_all.sh` once all findings are resolved
5. Update this audit to mark all deferred findings as fixed

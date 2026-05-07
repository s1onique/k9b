# Security Exception Audit - Read-Model Artifact Parsing

## Scope
This audit covers broad `except Exception` handlers in artifact scan/read-model paths and broader exception audit for UI/API mutation paths.
Phase 2 security baseline work: replacing silent catches with explicit exception handling and structured warnings.

## Classification Legend
- **fixed-this-slice**: Handler fixed in this audit slice
- **reviewed-safe**: Handler reviewed, confirmed safe as-is
- **needs-follow-up**: Handler identified but not yet fixed
- **out-of-scope**: Handler outside current audit scope

---

## Findings by File

### src/k8s_diag_agent/ui/server_next_checks.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| 60 | `except (json.JSONDecodeError, UnicodeDecodeError, ValueError)` | Payload parsing in handle_next_check_execution | **fixed-this-slice** |
| 190 | `except (OSError, json.JSONDecodeError, ValueError)` | Plan artifact JSON read in handle_next_check_execution | **fixed-this-slice** |
| 323 | `except Exception as exc:` | execute_manual_next_check external execution boundary | **reviewed-safe** |
| 373 | `except (OSError, json.JSONDecodeError, TypeError)` | Artifact persistence (pack_refresh_status write) | **fixed-this-slice** |
| 446 | `except (OSError, json.JSONDecodeError, ValueError)` | ui-index.json persistence + nested touch | **fixed-this-slice** |
| 477 | `except (json.JSONDecodeError, UnicodeDecodeError, ValueError)` | Payload parsing in handle_deterministic_promotion | **fixed-this-slice** |
| 544 | `except (FileExistsError, OSError)` | write_deterministic_next_check_promotion call | **fixed-this-slice** |
| 579 | `except (json.JSONDecodeError, UnicodeDecodeError, ValueError)` | Payload parsing in handle_next_check_approval | **fixed-this-slice** |
| 612 | `except (OSError, json.JSONDecodeError, ValueError)` | Plan artifact JSON read in handle_next_check_approval | **fixed-this-slice** |
| 699 | `except (FileExistsError, OSError)` | record_next_check_approval mutation | **fixed-this-slice** |
| 821 | `except (OSError, json.JSONDecodeError, ValueError)` | Artifact JSON read in find_candidate_in_all_plan_artifacts | **fixed-this-slice** |

**Total in file**: 11 handlers (10 fixed, 1 reviewed-safe, 0 needs-follow-up, 0 out-of-scope)

---

### src/k8s_diag_agent/ui/server_read_support.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| 115 | `except Exception: continue` | JSON parse/read for Alertmanager review artifacts | **fixed-this-slice** |
| 338 | `except Exception: continue` | JSON parse/read for drilldown data in `_build_clusters_and_drilldown_availability` | **fixed-this-slice** |
| 459 | `except Exception: continue` | JSON parse/read for proposals in `_load_proposals_for_run` | **fixed-this-slice** |
| 510 | `except Exception: continue` | JSON parse/read for external analysis scan | **fixed-this-slice** |
| 548 | `except Exception: continue` | JSON parse/read for notifications | **fixed-this-slice** |
| 799 | `except Exception: continue` | JSON parse/read in `_build_run_artifact_index` | **fixed-this-slice** |
| 868 | `except Exception: continue` | JSON parse/read for review enrichment fallback | **fixed-this-slice** |
| 963 | `except Exception: continue` | JSON parse/read for next-check plan | **fixed-this-slice** |
| 1147 | `except Exception: continue` | JSON parse/read for execution artifacts | **fixed-this-slice** |
| 1315 | `except Exception: continue` | JSON parse/read for LLM stats | **fixed-this-slice** |

**Total in file**: 10 handlers (10 fixed, 0 remaining)

### src/k8s_diag_agent/health/ui.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| 335 | `except Exception: continue` | `ExternalAnalysisArtifact.from_dict()` in `_serialize_review_enrichment` | **fixed-this-slice** |
| 554 | `except Exception: continue` | JSON parse/read for review timestamps in `_collect_review_timestamps` | **fixed-this-slice** |
| 594 | `except Exception: continue` | JSON parse/read for recent runs summary in `_build_recent_runs_summary` | **fixed-this-slice** |
| 776 | `except Exception: continue` | JSON parse/read for promotions in `_build_promotions_index` | **fixed-this-slice** |
| 862 | `except Exception: pass` | `write_text` in `_write_proposal_status_summary_to_review` | **fixed-this-slice** |

**Total in file**: 5 handlers (5 fixed, 0 remaining)

### src/k8s_diag_agent/health/summary.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| 307 | `except Exception: return {}` | JSON parse/read in `_load_history` | **fixed-this-slice** (opportunistic) |
| 366 | `except Exception: return {}` | JSON parse/read in `_load_json` | **fixed-this-slice** |
| 537 | `except Exception: return []` | JSON parse/read in `_collect_comparison_summaries` | **fixed-this-slice** |

**Total in file**: 3 handlers (3 fixed, 0 remaining)

---

## Broader Exception Audit - server.py Slice 15 (Mutation Handlers)

### src/k8s_diag_agent/ui/server.py

**Actual remaining `except Exception` in server.py** (verified via `rg -n 'except Exception'`):
| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| ~925 | `except (OSError, json.JSONDecodeError)` | Artifact JSON read in `_find_candidate_in_all_plan_artifacts` | **fixed** |
| ~990 | `except (OSError, json.JSONDecodeError)` | Artifact JSON read in `_find_candidate_in_all_plan_artifacts_from_health_root` | **fixed** |
| ~1158 | `except (OSError, json.JSONDecodeError)` | Review artifact read in `_load_context_for_run` | **fixed** |
| ~1697 | `except OSError` | Static file read in `_send_file` | **fixed** |
| ~1743 | `except (OSError, json.JSONDecodeError)` | ui-index.json read in `_persist_batch_execution_history_to_ui_index` | **fixed** |
| ~1814 | `except OSError` | ui-index.json write in `_persist_batch_execution_history_to_ui_index` | **fixed** |
| ~593 | `except (OSError, ImportError, ModuleNotFoundError, AttributeError)` | Script import in `_export_usefulness_review_for_run` | **fixed** (Slice 15) |
| ~699 | `except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError)` | _get_run_label defensive utility | **fixed-this-slice** |
| ~724 | `except Exception` | do_GET framework catch-all | **reviewed-safe** (framework boundary) |
| ~776 | `except Exception` | do_POST framework catch-all | **reviewed-safe** (framework boundary) |
| ~697 | `except (json.JSONDecodeError, UnicodeDecodeError)` | JSON payload parse in `_handle_run_batch_next_check_execution` | **fixed** (Slice 15) |
| ~722 | `except (ModuleNotFoundError, ImportError, AttributeError)` | Module import in `_handle_run_batch_next_check_execution` | **fixed** (Slice 15) |
| ~1065 | `except Exception` | Batch execution in `_handle_run_batch_next_check_execution` | **reviewed-safe** |
| ~1117 | `except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError)` | ui-index.json read/build in `_load_context` | **fixed** |
| ~1244 | `except (OSError, json.JSONDecodeError, ValueError, KeyError)` | Index read in `_load_context_for_run` (notification index) | **fixed** |
| ~1317 | `except (OSError, json.JSONDecodeError)` | Alertmanager compact read in `_load_context_for_run` | **fixed** |
| ~1333 | `except (OSError, json.JSONDecodeError, ValueError, KeyError)` | Alertmanager sources build in `_load_context_for_run` | **fixed** |
| ~1402 | `except (ValueError, TypeError, KeyError)` | Context build in `_load_context_for_run` | **fixed** |
| ~1528 | `except (OSError, ValueError, TypeError, json.JSONDecodeError)` | Runs list build in `_build_runs_list_payload` | **fixed** |

**Total in file**: 19 handlers (17 fixed, 3 reviewed-safe, 0 needs-follow-up, 0 deferred)

**Unreviewed broad handlers**: 0
**Reviewed-safe broad handlers**: 3
- ~724: `do_GET` - framework catch-all with `# REVIEWED:` comment (reviewed-safe)
- ~776: `do_POST` - framework catch-all with `# REVIEWED:` comment (reviewed-safe)
- ~1065: `_handle_run_batch_next_check_execution` - external execution boundary (reviewed-safe)

**This slice (Slice 15) fixed**: 3 mutation handlers
- ~593 `_export_usefulness_review_for_run`: `OSError, ImportError, ModuleNotFoundError, AttributeError` (script import boundary)
- ~697 `_handle_run_batch_next_check_execution`: `json.JSONDecodeError, UnicodeDecodeError` (JSON payload parse)
- ~722 `_handle_run_batch_next_check_execution`: `ModuleNotFoundError, ImportError, AttributeError` (module import)

**Reviewed-safe boundaries**:
- Batch execution external boundary (~1065): `run_batch_next_checks` may raise diverse exceptions from artifact writes, subprocess calls, JSON serialization. Narrowing would risk leaking uncontrolled failures.

**Already correct**: 1 handler
- 1 static file send: explicit `OSError` (verified correct before Slice 13)

**Security hardening applied**:
- Request JSON/body parse: explicit `json.JSONDecodeError, UnicodeDecodeError`
- Script/module import boundary: explicit `OSError, ImportError, ModuleNotFoundError, AttributeError`
- File I/O: explicit `OSError` tuple
- JSON parse errors: explicit `json.JSONDecodeError`
- Data shape/malformed: explicit `ValueError, TypeError, KeyError`
- Logging: safe metadata only (run_id, error string, no full paths/secrets)
- Behavior preserved: graceful fallback, non-fatal continue

**Deferred categories**:
- `deferred-framework-boundary`: HTTP framework-level catch-alls in do_GET/do_POST (needs route architecture review)

### src/k8s_diag_agent/ui/api.py

| Line (approx) | Handler | Context | Classification |
|---------------|---------|---------|----------------|
| ~406 | `except (OSError, json.JSONDecodeError, ValueError)` | Plan artifact JSON read in _compute_batch_eligibility | **fixed-this-slice** |
| ~437 | `except (OSError, json.JSONDecodeError, ValueError)` | Execution artifact JSON read in _compute_batch_eligibility | **fixed-this-slice** |
| ~600 | `except (OSError, UnicodeDecodeError, ValueError, ijson.common.IncompleteJSONError)` | ijson streaming parse in _extract_review_metadata_streaming | **fixed-this-slice** |
| ~626 | `except (OSError, json.JSONDecodeError, ValueError)` | Review artifact JSON parse in _build_runs_list_review_streaming | **fixed-this-slice** |
| ~1028 | `except (OSError, json.JSONDecodeError, ValueError)` | Plan artifact parse in batch eligibility prescan loop | **fixed-this-slice** |
| ~1061 | `except (OSError, json.JSONDecodeError, ValueError)` | Execution artifact parse in batch eligibility prescan loop | **fixed-this-slice** |
| ~966 | `except (OSError, json.JSONDecodeError, ValueError)` | Execution artifact JSON read in build_runs_list (Stage 2b) | **fixed-this-slice** |
| ~1098 | `except (OSError, json.JSONDecodeError, ValueError)` | JSON parse fallback in build_runs_list (review fast-path) | **fixed-this-slice** |
| ~892 | `except (OSError, json.JSONDecodeError, ValueError)` | ui-index.json read in _build_runs_list_super_fast | **fixed-this-slice** |

**Total in file**: 9 handlers (9 fixed, 0 needs-follow-up, 0 broad remaining)

**ijson exception used**: `ijson.common.IncompleteJSONError` (ijson.common module)
- Available ijson exceptions: `IncompleteJSONError`, `JSONError`
- Malformed/incomplete JSON raises `IncompleteJSONError` during stream iteration
- Verified: `ijson.common.IncompleteJSONError` is raised for `{ invalid json` input

### src/k8s_diag_agent/ui/server_feedback.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| 50 | `except (json.JSONDecodeError, UnicodeDecodeError, ValueError)` | Payload parsing in handle_usefulness_feedback | **fixed-this-slice** |
| 100 | `except (OSError, ValueError)` | Artifact path resolve in handle_usefulness_feedback | **fixed-this-slice** |
| 109 | `except (OSError, json.JSONDecodeError, ValueError)` | Execution artifact read in handle_usefulness_feedback | **fixed-this-slice** |
| 173 | `except OSError` | Review artifact write in handle_usefulness_feedback | **fixed-this-slice** |
| 187 | `except OSError` | UI index touch (non-fatal) in handle_usefulness_feedback | **fixed-this-slice** |
| 237 | `except (json.JSONDecodeError, UnicodeDecodeError, ValueError)` | Payload parsing in handle_alertmanager_relevance_feedback | **fixed-this-slice** |
| 287 | `except (OSError, ValueError)` | Artifact path resolve in handle_alertmanager_relevance_feedback | **fixed-this-slice** |
| 296 | `except (OSError, json.JSONDecodeError, ValueError)` | Execution artifact read in handle_alertmanager_relevance_feedback | **fixed-this-slice** |
| 348 | `except OSError` | Review artifact write in handle_alertmanager_relevance_feedback | **fixed-this-slice** |
| 362 | `except OSError` | UI index touch (non-fatal) in handle_alertmanager_relevance_feedback | **fixed-this-slice** |

**Total in file**: 10 handlers (10 fixed, 0 remaining)

**Security hardening applied**:
- Request payload parse: explicit tuple with `json.JSONDecodeError, UnicodeDecodeError, ValueError`
- Path resolve: explicit tuple with `OSError, ValueError`
- Artifact read: explicit tuple with `OSError, json.JSONDecodeError, ValueError` + safe error logging
- Artifact write: explicit `OSError` with safe error logging (returns 500)
- UI index touch: explicit `OSError` (non-fatal, silently passed)
- Logs exclude raw feedback content (usefulness_summary, alertmanager_relevance_summary)

### src/k8s_diag_agent/ui/server_alertmanager.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| ~88 | `except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError, AttributeError)` | Request body parse + validation in handle_alertmanager_source_action | **fixed-this-slice** |
| ~196 | `except OSError` | Override artifact write in handle_alertmanager_source_action | **fixed-this-slice** |
| ~264 | `except OSError` | Registry write in handle_alertmanager_source_action | **fixed-this-slice** |
| ~304 | `except OSError` | Action artifact write in handle_alertmanager_source_action | **fixed-this-slice** |
| ~329 | `except OSError` | UI index touch (non-fatal) in handle_alertmanager_source_action | **fixed-this-slice** |
| ~369 | `except (OSError, json.JSONDecodeError, ValueError, KeyError)` | Artifact ID read from action artifact | **fixed-this-slice** |

**Total in file**: 6 handlers (6 fixed, 0 remaining)

**Security hardening applied**:
- Request payload parse: explicit tuple with `json.JSONDecodeError, UnicodeDecodeError, ValueError`
- Override artifact write: explicit `OSError` with error logging and 500 response
- Registry write: explicit `OSError` with warning logging (non-fatal, request succeeds)
- Action artifact write: explicit `OSError` with warning logging (non-fatal, request succeeds)
- UI index touch: explicit `OSError` (non-fatal, silently passed)
- Artifact ID read: explicit tuple with `OSError, json.JSONDecodeError, ValueError, KeyError` (non-fatal)
- Logs exclude raw request payloads, Alertmanager URLs containing credentials, kubeconfig, bearer tokens

### src/k8s_diag_agent/health/loop.py

Many `except Exception` handlers in the main health loop. These are central to the health assessment flow.

**Review status**: Deferred to future slice

### src/k8s_diag_agent/ui/notifications.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| ~247 | `except (json.JSONDecodeError, UnicodeDecodeError, OSError)` | JSON parse/read in _load_notification_records | **fixed-this-slice** |
| ~348 | `except (json.JSONDecodeError, UnicodeDecodeError, OSError)` | JSON parse/read in _load_notification_records_optimized | **fixed-this-slice** |
| ~433 | `except (json.JSONDecodeError, UnicodeDecodeError, OSError)` | JSON parse/read in _count_matching_records | **fixed-this-slice** |
| ~563 | `except (ValueError, OSError)` | Path resolution in _relative_path | **fixed-this-slice** |

**Total in file**: 4 handlers (4 fixed, 0 remaining)

**Security hardening applied**:
- JSON parse/read in artifact loops: explicit tuple with `json.JSONDecodeError, UnicodeDecodeError, OSError`
- Path resolution fallback: explicit tuple with `ValueError, OSError`
- Non-fatal behavior preserved (continue on parse errors, graceful fallback on path resolution)
- Logs do not include raw notification content or secret-like values

**Notes**:
- `src/k8s_diag_agent/notifications/delivery.py`: Already uses explicit `(OSError, json.JSONDecodeError)` at line ~35
- `src/k8s_diag_agent/notifications/mattermost.py`: Uses precise `requests.RequestException` at line ~50
- `src/k8s_diag_agent/health/notifications.py`: No broad exception handlers, uses explicit `ValueError` in `from_dict()`

### src/k8s_diag_agent/health/ui_planner_queue.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| ~153 | `except (OSError, ValueError)` | Path name extraction in _plan_paths_match | **fixed-this-slice** |

**Total in file**: 1 handler (1 fixed, 0 remaining)

**Security hardening applied**:
- Path name extraction fallback: explicit tuple with `OSError, ValueError`
- Behavior preserved (returns False on invalid paths, graceful fallback)

### src/k8s_diag_agent/health/ui_llm_stats.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| ~88 | `except (OSError, json.JSONDecodeError, UnicodeDecodeError)` | JSON parse/read in _collect_historical_external_analysis_entries | **fixed-this-slice** |

**Total in file**: 1 handler (1 fixed, 0 remaining)

**Security hardening applied**:
- JSON parse/read in historical artifact loop: explicit tuple with `OSError, json.JSONDecodeError, UnicodeDecodeError`
- Non-fatal behavior preserved (continue on parse/read errors, graceful fallback)

---

## Phase 2 Audit - Slice 12: external_analysis/*

### src/k8s_diag_agent/external_analysis/llamacpp_adapter.py

| Line | Handler | Old Type | New Type | Context | Classification |
|------|---------|----------|----------|---------|----------------|
| ~57 | `except Exception` | bare Exception | `(ValueError, TypeError)` | Provider config from_env boundary | **fixed-this-slice** |
| ~214 | `except Exception` | bare Exception | `(ValueError, TypeError, AttributeError)` | Prompt diagnostics in LLMResponseParseError handler | **fixed-this-slice** |
| ~241 | `except Exception` | bare Exception | reviewed-safe | LLM provider failure boundary (catch-all) | **reviewed-safe** |
| ~263 | `except Exception` | bare Exception | `(ValueError, TypeError, AttributeError, OSError)` | Prompt diagnostics fallback in general handler | **fixed-this-slice** |

**Total in file**: 4 handlers (3 fixed, 1 reviewed-safe, 0 remaining)

### src/k8s_diag_agent/external_analysis/alertmanager_discovery.py

| Line | Handler | Old Type | New Type | Context | Classification |
|------|---------|----------|----------|---------|----------------|
| ~959 | `except Exception` | bare Exception | `(OSError, json.JSONDecodeError, ValueError, TimeoutError)` | Alertmanager version fetch endpoint | **fixed-this-slice** |

**Total in file**: 1 handler (1 fixed, 0 remaining)

### src/k8s_diag_agent/external_analysis/deterministic_next_check_promotion.py

| Line | Handler | Old Type | New Type | Context | Classification |
|------|---------|----------|----------|---------|----------------|
| ~202 | `except Exception` | bare Exception | `(OSError, json.JSONDecodeError)` | Promotion artifact JSON read | **fixed-this-slice** |
| ~216 | `except Exception` | bare Exception | `(ValueError, TypeError, KeyError)` | ExternalAnalysisArtifact.from_dict deserialization | **fixed-this-slice** |

**Total in file**: 2 handlers (2 fixed, 0 remaining)

### src/k8s_diag_agent/external_analysis/utils.py

| Line | Handler | Old Type | New Type | Context | Classification |
|------|---------|----------|----------|---------|----------------|
| ~18 | `except Exception` | bare Exception | `(ValueError, TypeError)` | Path name extraction fallback | **fixed-this-slice** |

**Total in file**: 1 handler (1 fixed, 0 remaining)

### src/k8s_diag_agent/external_analysis/next_check_planner.py

| Line | Handler | Old Type | New Type | Context | Classification |
|------|---------|----------|----------|---------|----------------|
| ~1017 | `except Exception` | bare Exception | `(OSError, json.JSONDecodeError, ValueError, KeyError)` | plan_next_checks context building | **fixed-this-slice** |

**Total in file**: 1 handler (1 fixed, 0 remaining)

**external_analysis/* now has 0 unreviewed broad exception handlers.**

---

## Exception Type Mapping

For artifact scan loops, the following exception types should be caught explicitly:

```python
# File I/O errors
from pathlib import Path
except OSError:  # Covers IOError, FileNotFoundError, PermissionError, etc.
    continue

# JSON parsing errors
import json
except (json.JSONDecodeError, ValueError):
    continue

# Combined for artifact loops
except (OSError, json.JSONDecodeError):
    continue
```

For request payload parsing:
```python
except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
    handler._send_json({"error": "Invalid JSON payload"}, 400)
    return
```

---

## Audit Summary

| Category | Count |
|----------|-------|
| Fixed this slice (ui/api.py - Phase 2 Slice 7) | 9 |
| Fixed this slice (server_next_checks.py - Phase 2 Slice 6) | 10 |
| Fixed this slice (server_feedback.py - Phase 2 Slice 8) | 10 |
| Fixed this slice (server_alertmanager.py - Phase 2 Slice 9) | 6 |
| Fixed this slice (ui/notifications.py - Phase 2 Slice 10) | 4 |
| Fixed this slice (ui_planner_queue.py + ui_llm_stats.py - Phase 2 Slice 11) | 2 |
| Fixed this slice (external_analysis/* - Phase 2 Slice 12) | 8 |
| Fixed this slice (server.py - Phase 2 Slice 13) | 3 |
| Fixed this slice (server.py - Phase 2 Slice 14) | 8 |
| Fixed this slice (server.py - Phase 2 Slice 15) | 3 |
| Fixed this slice (server.py - Phase 2 Slice 16) | 1 |
| Fixed previous slices (read-model scope) | 18 |
| Reviewed safe (Phase 2 Slice 16) | 3 |
| Needs follow-up | 0 |
| Out of scope (deferred modules) | ~100+ |
| **Total fixed** | **82** |

### Fixed This Slice (Phase 2 Audit - Slice 6: server_next_checks.py mutation write paths)

| Function | Line | Type | Context |
|----------|------|------|---------|
| handle_next_check_execution | 60 | JSON decode | Payload parsing |
| handle_next_check_execution | 190 | OSError, JSON | Plan artifact read |
| handle_next_check_execution | ~373 | OSError, JSON, TypeError | Artifact persistence (pack_refresh_status write) |
| handle_next_check_execution | ~449 | OSError, JSON, ValueError | ui-index.json write + touch |
| handle_deterministic_promotion | 477 | JSON decode | Payload parsing |
| handle_deterministic_promotion | ~544 | FileExistsError, OSError | write_deterministic_next_check_promotion call |
| handle_next_check_approval | 579 | JSON decode | Payload parsing |
| handle_next_check_approval | 612 | OSError, JSON | Plan artifact read |
| handle_next_check_approval | ~699 | FileExistsError, OSError | record_next_check_approval call |
| find_candidate_in_all_plan_artifacts | 821 | OSError, JSON | Artifact glob scan |

**server_next_checks.py now has 0 unreviewed broad exception handlers.**

### Phase 2 server_next_checks.py Summary

All 10 handlers in server_next_checks.py are now fixed:
- 4 JSON/payload parse handlers: explicit tuple with `json.JSONDecodeError, UnicodeDecodeError, ValueError`
- 3 artifact read handlers: explicit tuple with `OSError, json.JSONDecodeError, ValueError`
- 1 mutable artifact write handler: `OSError, json.JSONDecodeError, TypeError` with warning-only behavior
- 1 mutable ui-index write handler: `OSError, json.JSONDecodeError, ValueError` with touch fallback
- 1 immutable artifact write handler: `FileExistsError, OSError` with error logging
- 1 immutable artifact write handler: `FileExistsError, OSError` with error logging

### Remaining Backlog

| File | Handler Count | Notes |
|------|---------------|-------|
| health/loop.py | ~14 | Main health loop (deferred) |

**Note**: These are deferred to future slices pending careful review of framework/async behavior.
**ui_planner_queue.py**: All 1 broad handler fixed in Slice 11 (0 remaining)
**ui_llm_stats.py**: All 1 broad handler fixed in Slice 11 (0 remaining)
**ui/notifications.py**: All 4 broad handlers fixed in Slice 10 (0 remaining)
**server_alertmanager.py**: All 6 broad handlers fixed in Slice 9 (0 remaining)
**server_feedback.py**: All 10 broad handlers fixed in Slice 8 (0 remaining)
**api.py**: All 9 broad handlers fixed in Slice 7 (0 remaining)
**external_analysis/***: All 9 broad handlers fixed in Slice 12 (0 remaining, 1 reviewed-safe as LLM boundary)

---

## Next Steps

1. **Immediate**: Continue auditing remaining UI/API exception handlers
2. **Short-term**: Address needs-follow-up handlers in server_next_checks.py
3. **Medium-term**: Audit server.py and api.py exception handlers
4. **Long-term**: Add eval coverage for exception handling behavior

---

*Audit created: 2026-05-01*
*Audit scope: Phase 2 Security Hardening - Read-Model Artifact Parsing Paths*
*Updated: 2026-05-05 (Slice 15: server.py mutation handlers - 3 fixed, 1 reviewed-safe)*
*Total handlers fixed in Phase 2: 81 (18 read-model + 10 server_next_checks.py + 9 ui/api.py + 10 server_feedback.py + 6 server_alertmanager.py + 4 ui/notifications.py + 2 ui_planner_queue.py + ui_llm_stats.py + 8 external_analysis/* + 14 server.py)*

**Phase 2 Slice 15 summary**:
- 3 mutation handlers narrowed in server.py
- 1 reviewed-safe boundary (external execution boundary at ~1065)
- 4 remaining broad handlers: 1 framework utility, 2 framework catch-alls (deferred), 1 reviewed-safe
- server.py now has 16 fixed handlers, 1 reviewed-safe, 3 deferred

---

## Phase 2 Audit - health loop post-split reassessment

### Current broad handler inventory (src/k8s_diag_agent/health/)

After `health/loop.py` was split into focused modules, the following broad `except Exception` handlers exist:

| File | Line | Handler | Context | Classification |
|------|------|---------|---------|----------------|
| loop_alertmanager_discovery.py | 149 | `except (OSError, RuntimeError, TimeoutError) as exc` | Cluster discovery (kubectl/cluster boundary) | **fixed-this-slice** |
| loop_alertmanager_discovery.py | 265 | `except (OSError, RuntimeError)` | Alertmanager sources artifact write | **fixed-this-slice** |
| loop_alertmanager_snapshot.py | 311 | `except (OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc` | Snapshot fetch (HTTP/urllib boundary) | **fixed-this-slice** |
| loop_alertmanager_snapshot.py | 371 | `except OSError` | Snapshot artifacts write | **fixed-this-slice** |
| loop_config_logging.py | 36 | `except (ValueError, TypeError, AttributeError)` | URL sanitization fallback | **fixed-this-slice** |
| loop_review_pipeline.py | 79 | `except Exception` | Health review build (LLM/domain boundary) | **reviewed-safe** (LLM adapter boundary) |
| loop_review_pipeline.py | 114 | `except Exception as exc` | Proposal generation (LLM/domain boundary) | **reviewed-safe** (LLM adapter boundary) |
| loop_alertmanager_port_forward.py | 222 | `except (OSError, subprocess.SubprocessError, TimeoutError)` | Port-forward cleanup (typed) | **fixed-this-slice** |
| loop_alertmanager_port_forward.py | 232 | `except Exception` | Port-forward cleanup final containment | **reviewed-safe** (finalizer) |
| loop.py | 1938 | `except OSError` | UI index artifact write | **fixed-this-slice** |
| loop.py | 2059 | `except (OSError, RuntimeError, TimeoutError) as exc` | Image pull secret inspection (kubectl boundary) | **fixed-this-slice** |
| loop.py | ~2426 | `except Exception as exc` | LLM call in auto-drilldown (provider/HTTP/LLM boundary) | **reviewed-safe** (LLM provider boundary) |
| loop.py | ~2480 | `except (TypeError, AttributeError, KeyError, ValueError)` | Prompt diagnostics fallback (internal extraction boundary) | **fixed-this-slice** |
| loop.py | ~2632 | `except Exception as exc` | Review enrichment LLM call (provider/HTTP boundary) | **reviewed-safe** (LLM provider boundary) |
| loop.py | ~2847 | `except (ValueError, TypeError, KeyError, AttributeError, OSError)` | Review pipeline write (domain transformation boundary) | **fixed-this-slice** |
| loop.py | 3095 | `except OSError` | History fact artifacts write | **fixed-this-slice** |

**Total tracked handlers**: 15
**This slice fixed (Phase 2 Slice 18)**: 3 handlers narrowed + 1 reviewed-safe = 4 total
- `loop_alertmanager_discovery.py:149`: cluster discovery → `(OSError, RuntimeError, TimeoutError)` — **fixed**
- `loop_alertmanager_snapshot.py:311`: snapshot fetch HTTP → `(OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError)` — **fixed**
- `loop.py:2059`: kubectl inspection → `(OSError, RuntimeError, TimeoutError)` — **fixed**
- `loop_alertmanager_port_forward.py:222`: port-forward cleanup → **reviewed-safe** (subprocess boundary, must not crash loop)

**Prior slice (Phase 2 Slice 17) fixed**: 4 handlers
- `loop_alertmanager_discovery.py:265`: artifact write → `(OSError, RuntimeError)`
- `loop_alertmanager_snapshot.py:371`: artifact write → `OSError`
- `loop.py:1938`: UI index write → `OSError`
- `loop.py:3095`: history fact artifacts write → `OSError`

**Remaining broad handlers**: 6 (5 reviewed-safe, 1 out-of-scope deferred)
**Unreviewed broad handlers**: 0
**Reviewed-safe**: 5 handlers (subprocess/HTTP/LLM/port-forward boundaries - need architecture review)
**This slice (Phase 2 Slice 18) narrowed**: 2 handlers
- `loop.py:~2480`: prompt diagnostics fallback → `(TypeError, AttributeError, KeyError, ValueError)` — **fixed**
- `loop.py:~2847`: review pipeline write → `(ValueError, TypeError, KeyError, AttributeError, OSError)` — **fixed**
**Out-of-scope deferred**: 0 handlers (loop_config_logging URL sanitization - fixed this slice)

### Rationale for this slice

Artifact write failures are the smallest coherent fix batch because:
1. Explicit `OSError` is the correct type for file I/O operations (`write_text`, `Path.write_text`, `json.dump`)
2. Behavior is preserved: run continues, error is logged with safe metadata
3. No changes to subprocess/kubectl/helm execution boundaries
4. No changes to LLM/provider execution boundaries
5. No changes to main loop orchestration

### Files changed this slice:
- `src/k8s_diag_agent/health/loop_alertmanager_discovery.py`
- `src/k8s_diag_agent/health/loop_alertmanager_snapshot.py`
- `src/k8s_diag_agent/health/loop.py`

### Deferred handlers (needs-follow-up / reviewed-safe)

| File | Line | Context | Deferral Reason |
|------|------|---------|----------------|
| loop_config_logging.py | 39 | URL sanitization | **fixed-this-slice** (narrowed to ValueError, TypeError, AttributeError) |
| loop_review_pipeline.py | 82 | LLM adapter call | Provider boundary |
| loop_review_pipeline.py | 117 | Proposal LLM call | Provider boundary |
| loop.py | 2438 | LLM call | Provider boundary |
| loop.py | 2654 | Review enrichment | Provider boundary |

### Audit Summary Update

| Category | Count |
|----------|-------|
| Fixed Phase 2 Slice 17 (health-loop artifact write) | 4 |
| Reviewed-safe (boundaries) | 10 |
| Out-of-scope (deferred) | 1 |
| **Total handlers in health/ loop modules** | **15** |

**Phase 2 total fixed**: 91 (89 prior + 2 this slice: loop.py:2480, loop.py:2847)

---

## Phase 2 Audit - CLOSED

**Audit status**: COMPLETE

All handlers in scope have been classified:
- **91 handlers fixed** across 17 slices
- **6 handlers reviewed-safe** (external boundaries requiring architecture review)
- **1 handler out-of-scope** (no file I/O, logging-only)
- **0 unreviewed broad handlers** remaining in scope

**Verified**:
- `rg -n 'except Exception' src/k8s_diag_agent/health/`: 6 remaining (5 reviewed-safe + 1 out-of-scope)
- `pytest tests/test_health_loop.py`: 37 passed
- `pytest tests/ -k security`: 178 passed
- `git diff --check`: no whitespace errors

**Reviewed-safe boundaries** (require architecture review for potential narrowing):
- `loop_review_pipeline.py:82`: LLM adapter call (provider boundary)
- `loop_review_pipeline.py:117`: Proposal LLM call (provider boundary)
- `loop_alertmanager_port_forward.py:227`: Subprocess cleanup (must not crash loop)
- `loop.py:2438`: LLM call (provider boundary)
- `loop.py:2654`: Review enrichment (provider boundary)

**Next**: These reviewed-safe boundaries may be narrowed in future work, but require careful review of the provider/framework/subprocess contracts.

---

## Security Baseline Allowlist

The `scripts/check_security_baseline.sh` script enforces the security baseline for CI guardrails. It operates in two modes:

### Modes

**baseline (default)**: Permits documented reviewed-safe findings, fails on new unreviewed patterns. This is the current CI gate mode.

**strict**: Fails on all broad `except Exception` findings, including reviewed-safe. Useful for future cleanup or local hardening. This mode is allowed to fail today.

### Allowlist

The reviewed-safe handlers are documented in `scripts/security_baseline_allowlist.txt`. This allowlist uses a simple text format:

```
<file_path> <function_pattern> <reason>
```

Where:
- `file_path`: Path relative to `src/` (e.g., `k8s_diag_agent/ui/server.py`)
- `function_pattern`: A unique substring in the function or context near the handler (e.g., `do_GET`)
- `reason`: Description of why this is reviewed-safe, optionally with audit reference

### Adding a New Allowlist Entry

1. Identify the handler that needs to be allowlisted
2. Add an entry to `scripts/security_baseline_allowlist.txt` with:
   - The file path (relative to `src/`, without the `src/` prefix)
   - A unique pattern that appears in the function name or context near the except
   - A reason explaining why this is reviewed-safe
   - Optionally, reference the audit section or line number

Example:
```
k8s_diag_agent/ui/server.py do_GET HTTP framework catch-all boundary - docs/security-exception-audit.md line ~724
```

### What "Reviewed-Safe" Means

"Reviewed-safe" is NOT the same as "ignore forever". It means:

1. The handler was consciously reviewed and accepted as a boundary that requires architecture-level refactor to narrow
2. The context is documented (typically with a `# REVIEWED:` comment in the code)
3. The handler is in the allowlist and linked to this audit
4. Any new handler MUST be either:
   - Narrowed to specific exception types (preferred)
   - Reviewed and added to the allowlist if narrowing is impractical

### When to Narrow vs. Allowlist

**Narrow (preferred)**:
- Handlers that catch specific, predictable exceptions (file I/O, JSON parse, etc.)
- Handlers where the failure mode is known and bounded
- Handlers that can be tested with specific exception types

**Allowlist (when narrowing is impractical)**:
- HTTP framework catch-alls that must not leak raw tracebacks
- LLM provider boundaries where unexpected exceptions may occur
- Subprocess boundaries where failures are non-fatal (like port-forward cleanup)
- Path traversal guards that must not crash the server

### Verification

```bash
# Baseline mode (default for CI)
bash scripts/check_security_baseline.sh

# Strict mode (for future cleanup)
bash scripts/check_security_baseline.sh --mode strict

# Run the security baseline tests
pytest tests/test_scripts.py::TestSecurityBaseline -v
```

---

## Typed Artifact Reader Pilot

### Overview

Phase 2 follow-up: Introduced a typed artifact reader boundary for `ExternalAnalysisArtifact` family to reduce ad-hoc `json.loads()` + `dict[str, Any]` artifact parsing patterns.

### Motivation

The security exception audit fixed broad `except Exception` handlers, but artifact read paths still used scattered raw JSON parsing patterns:

```python
# Before: scattered pattern
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    continue
artifact = ExternalAnalysisArtifact.from_dict(data)
```

### Solution

Created `src/k8s_diag_agent/external_analysis/artifact_readers.py` with two functions:

**Strict reader** (raises on failure):
```python
def read_external_analysis_artifact(path: Path) -> ExternalAnalysisArtifact:
    """Read and parse an ExternalAnalysisArtifact from disk.

    Raises:
        OSError: If the file cannot be read
        json.JSONDecodeError: If the file content is not valid JSON
        ValueError: If the JSON is valid but not a mapping, or from_dict validation fails
        TypeError: If from_dict receives unexpected type
        KeyError: If required fields are missing in from_dict
    """
```

**Optional reader** (returns None on failure, with optional logging):
```python
def try_read_external_analysis_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "external-analysis",
    log_failures: bool = True,
) -> ExternalAnalysisArtifact | None:
```

### Contract

- **Strict reader**: Raises specific exceptions - callers must handle failures explicitly
- **Optional reader**: Returns `None` on failure, logs safe metadata only when `log_failures=True`
- **Logging policy**: Only safe metadata logged - never raw content, prompts, responses, kubeconfig, tokens, or secrets
- **Behavior preservation**: Malformed artifacts are skipped (non-fatal), valid artifacts load correctly

### Path Classification

**Broad scan paths** (use `log_failures=False`):
- `batch.py::load_existing_execution_indices` - Scans execution artifacts to find already-executed indices
- `deterministic_next_check_promotion.py::collect_promoted_next_check_payloads` - Scans promotion artifacts to collect payloads

**Targeted reads** (use `log_failures=True`):
- `server_feedback.py::handle_usefulness_feedback` - Reads a specific execution artifact for feedback
- `server_feedback.py::handle_alertmanager_relevance_feedback` - Reads a specific execution artifact for feedback

Rationale: Broad scan paths iterate over potentially many files where malformed artifacts are expected noise. Targeted reads read a specific artifact where failures are unexpected and should be logged for debugging.

### Call Sites Migrated (Pilot Slice)

| File | Function | Pattern | Classification |
|------|----------|---------|----------------|
| `batch.py` | `load_existing_execution_indices` | Next-check-execution scan | **fixed-this-slice** |
| `external_analysis/deterministic_next_check_promotion.py` | `collect_promoted_next_check_payloads` | Promotion artifact scan | **fixed-this-slice** |
| `ui/server_feedback.py` | `handle_usefulness_feedback` | Execution artifact read | **fixed-this-slice** |
| `ui/server_feedback.py` | `handle_alertmanager_relevance_feedback` | Execution artifact read | **fixed-this-slice** |

### Files Changed

- **New**: `src/k8s_diag_agent/external_analysis/artifact_readers.py`
- **Modified**: `src/k8s_diag_agent/batch.py`
- **Modified**: `src/k8s_diag_agent/external_analysis/deterministic_next_check_promotion.py`
- **Modified**: `src/k8s_diag_agent/ui/server_feedback.py`
- **New**: `tests/unit/test_artifact_readers.py`

### Tests Added

| Test | Purpose |
|------|---------|
| `test_valid_artifact_loads_and_returns_typed_object` | Valid artifact roundtrip |
| `test_malformed_json_fails_with_json_decode_error` | Malformed JSON raises JSONDecodeError |
| `test_missing_required_field_fails_with_value_error` | Missing fields raise ValueError |
| `test_non_object_json_fails` | Array/non-mapping JSON raises ValueError |
| `test_unreadable_missing_file_raises_os_error` | Missing file raises OSError |
| `test_malformed_json_returns_none_and_logs` | Optional reader returns None + logs safe metadata |
| `test_batch_execution_indices_still_work` | Regression: batch pattern preserves skip-malformed behavior |
| `test_promotion_artifact_preserves_run_id_filter` | Regression: promotion pattern preserves run_id filter |

### Migration Rule

**New artifact readers should prefer typed boundary helpers:**

1. If an artifact family has a `from_dict()` class method, create a typed reader module (e.g., `artifact_readers.py`)
2. Use `read_<artifact>_artifact()` for paths where failures should propagate (strict boundary)
3. Use `try_read_<artifact>_artifact()` for paths where failures should be skipped (graceful fallback)
4. Log only safe metadata: filename, run_id, error type - never raw content
5. Catch only expected shape errors: `ValueError`, `TypeError`, `KeyError` from `from_dict()`

### Next Artifact Family Recommendation

In priority order for future migration:

1. **`HealthProposal`**: Already has `from_dict()` in `health/adaptation.py`, UI reads in `health/ui.py`
2. **`DrilldownArtifact`**: Used in CLI handlers and UI, has `from_dict()`
3. **`ClusterSnapshot`**: Used in CLI and batch, has `from_dict()`
4. **`NotificationArtifact`**: Uses `from_dict()` in `health/notifications.py`

---

## Typed Artifact Reader: HealthProposal Pilot (Phase 2 Follow-up)

### Overview
This section documents the HealthProposal typed artifact reader expansion as a follow-up to Phase 2 security hardening.

### New Files
- `src/k8s_diag_agent/health/artifact_readers.py` - HealthProposal typed readers
- `tests/unit/test_health_proposal_artifact_readers.py` - Reader tests

### Reader API

```python
# Strict reader - raises on failure
def read_health_proposal_artifact(path: Path) -> HealthProposal:
    """Read and parse a HealthProposal from disk.

    Raises:
        OSError: If the file cannot be read
        json.JSONDecodeError: If the file content is not valid JSON
        ValueError: If the JSON is valid but not a mapping, or from_dict validation fails
        TypeError: If from_dict receives unexpected type
        KeyError: If required fields are missing in from_dict
    """

# Optional reader - returns None on failure
def try_read_health_proposal_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "health-proposal",
    log_failures: bool = True,
) -> HealthProposal | None:
    """Try to read a HealthProposal, returning None on failure.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.
    """
```

### Error Handling Contract
- **Strict reader raises**:
  - `OSError`
  - `json.JSONDecodeError`
  - `ValueError`
  - `TypeError`
  - `KeyError`
- **Optional reader returns** `None` on those failures
- **Optional reader logs only when** `log_failures=True`

### Logging Policy
- Safe metadata only:
  - artifact filename
  - artifact kind
  - run_id (if safe)
  - error type
- Never log raw proposal payloads, command text, kubeconfig, env vars, prompts/responses, tokens, or full absolute paths

### Migrated Call Sites

| Call Site | Type | log_failures | Notes |
|----------|------|-------------|-------|
| `ui/server_read_support.py::_load_proposals_for_run` | broad scan | True | Preserves existing logged failure behavior |

### Preserved Behavior
- Valid proposals still load and render the same
- Malformed proposals still skip/fallback exactly as before
- No API response shape changes

### Tests Added

| Test | Purpose |
|------|---------|
| `test_valid_proposal_loads_typed_object` | Valid proposal parses into HealthProposal |
| `test_malformed_json_raises_json_decode_error` | Strict reader raises JSONDecodeError |
| `test_missing_file_raises_os_error` | Strict reader raises OSError |
| `test_non_object_json_raises_value_error` | Strict reader raises ValueError |
| `test_missing_required_confidence_field_raises_value_error` | Strict reader raises ValueError |
| `test_invalid_confidence_value_raises_value_error` | Strict reader raises ValueError |
| `test_valid_proposal_returns_typed_object` | Optional reader returns typed object |
| `test_malformed_json_returns_none_with_logging` | Optional reader returns None + logs |
| `test_malformed_json_returns_none_silently_without_logging` | log_failures=False suppresses warnings |
| `test_missing_file_returns_none` | Optional reader returns None |
| `test_missing_file_silent_with_log_failures_false` | log_failures=False suppresses warnings |
| `test_non_object_json_returns_none` | Optional reader returns None |
| `test_missing_required_field_returns_none` | Optional reader returns None |
| `test_log_failures_true_logs_warning_with_safe_message` | Logs only safe metadata |
| `test_roundtrip_serialization_preserves_fields` | Roundtrip preserves all fields |
| `test_log_failures_false_does_not_log_raw_content` | Sensitive content never logged |

### Verification

```bash
# Run new reader tests
pytest tests/unit/test_health_proposal_artifact_readers.py -v

# Run affected call-site tests
pytest tests/ -k "proposal" -v

# Run ruff check on changed files
ruff check src/k8s_diag_agent/health/artifact_readers.py
ruff check src/k8s_diag_agent/ui/server_read_support.py

# Run security baseline
bash scripts/check_security_baseline.sh --mode baseline
```

### Next Artifact Family Recommendation

After HealthProposal, consider:

1. **`DrilldownArtifact`**: Used in CLI handlers and UI, has `from_dict()`
2. **`ClusterSnapshot`**: Used in CLI and batch, has `from_dict()`
3. **`NotificationArtifact`**: Uses `from_dict()` in `health/notifications.py`

---

## Typed Artifact Reader: DrilldownArtifact (Phase 2 Follow-up)

### Overview
This section documents the DrilldownArtifact typed artifact reader as the next step after HealthProposal.

### New Files
- `src/k8s_diag_agent/health/artifact_readers.py` - DrilldownArtifact typed readers (added to existing module)
- `tests/unit/test_drilldown_artifact_readers.py` - Reader tests

### Reader API

```python
# Strict reader - raises on failure
def read_drilldown_artifact(path: Path) -> DrilldownArtifact:
    """Read and parse a DrilldownArtifact from disk.

    Raises:
        OSError: If the file cannot be read
        json.JSONDecodeError: If the file content is not valid JSON
        ValueError: If the JSON is valid but not a mapping, or from_dict validation fails
        TypeError: If from_dict receives unexpected type
        KeyError: If required fields are missing in from_dict
    """

# Optional reader - returns None on failure
def try_read_drilldown_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "drilldown",
    log_failures: bool = True,
) -> DrilldownArtifact | None:
    """Try to read a DrilldownArtifact, returning None on failure.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.
    """
```

### Error Handling Contract
- **Strict reader raises**:
  - `OSError`
  - `json.JSONDecodeError`
  - `ValueError`
  - `TypeError`
  - `KeyError`
- **Optional reader returns** `None` on those failures
- **Optional reader logs only when** `log_failures=True`

### Logging Policy
- Safe metadata only:
  - artifact filename
  - artifact kind
  - run_id (if safe)
  - error type
- Never log raw drilldown content, command output, kubectl output, pod logs, kubeconfig, tokens, or full absolute paths

### DrilldownArtifact Call Site Inventory

| File | Function | Type | Pattern | Classification |
|------|----------|------|---------|----------------|
| `health/review.py` | `collect_drilldown_candidates` | broad scan | drilldown glob scan | **fixed-this-slice** |
| `ui/server_read_support.py` | `_build_clusters_and_drilldown_availability` | broad scan | drilldown data read | **skipped** (UI path uses dict-based scan, not typed) |
| `cli_handlers.py` | `handle_assess_drilldown` | targeted read | CLI artifact read | **skipped** (CLI path, no fallback needed) |
| `health/validators.py` | `DrilldownArtifactValidator` | validation | schema validation | **skipped** (test/validation only) |

### Chosen Call Sites and Rationale

**Migrated (1 call site)**:
- `health/review.py::collect_drilldown_candidates`: Uses `log_failures=False` for silent scan behavior. Previously used raw `json.loads()` + `from_dict()` pattern. Migration preserves behavior where malformed artifacts are skipped silently.

**Skipped**:
- `ui/server_read_support.py::_build_clusters_and_drilldown_availability`: Already uses dict-based JSON scan with explicit exception handling. The drilldown data is used for metadata display (cluster availability), not for typed object operations. Migration would be low-value here.
- `cli_handlers.py::handle_assess_drilldown`: CLI entry point expects strict parsing - malformed artifacts should fail fast. No fallback behavior needed.
- `health/validators.py::DrilldownArtifactValidator`: Test/validation path, not a production read path.

### Compatibility Decision

**No legacy dict fallback needed**: Unlike HealthProposal, DrilldownArtifact does not have the same legacy fallback requirement because:
1. DrilldownArtifact schema is stable with no optional fields that caused issues for HealthProposal
2. All existing artifacts should pass `from_dict()` validation
3. Migration preserves behavior where malformed artifacts are skipped

### Preserved Behavior
- Valid drilldowns still load and render the same
- Malformed drilldowns still skip/fallback exactly as before
- No API response shape changes
- No CLI output shape changes
- No change to write-path schema

### Tests Added

| Test | Purpose |
|------|---------|
| `test_valid_drilldown_loads_typed_object` | Valid drilldown parses into DrilldownArtifact |
| `test_malformed_json_raises_json_decode_error` | Strict reader raises JSONDecodeError |
| `test_missing_file_raises_os_error` | Strict reader raises OSError |
| `test_non_object_json_raises_value_error` | Strict reader raises ValueError |
| `test_missing_required_timestamp_field_raises_value_error` | Strict reader raises ValueError |
| `test_invalid_timestamp_raises_value_error` | Strict reader raises ValueError |
| `test_valid_drilldown_returns_typed_object` | Optional reader returns typed object |
| `test_malformed_json_returns_none_with_logging` | Optional reader returns None + logs |
| `test_malformed_json_returns_none_silently_without_logging` | log_failures=False suppresses warnings |
| `test_missing_file_returns_none` | Optional reader returns None |
| `test_missing_file_silent_with_log_failures_false` | log_failures=False suppresses warnings |
| `test_non_object_json_returns_none` | Optional reader returns None |
| `test_missing_required_field_returns_none` | Optional reader returns None |
| `test_log_failures_true_logs_warning_with_safe_message` | Logs only safe metadata |
| `test_roundtrip_serialization_preserves_fields` | Roundtrip preserves all fields |
| `test_log_failures_false_does_not_log_raw_content` | Sensitive content never logged |
| `test_exception_carrying_safe_path` | DrilldownArtifactReadError uses basename only |
| `test_exception_with_cause` | DrilldownArtifactReadError chains cause |
| `test_multiple_artifacts_scanned_preserves_valid_skips_invalid` | Call-site behavior preserved |
| `test_legacy_dict_compatibility_not_needed_for_current_artifacts` | Schema stability documented |

### Verification

```bash
# Run new reader tests
pytest tests/unit/test_drilldown_artifact_readers.py -v

# Run affected call-site tests
pytest tests/ -k "drilldown" -v

# Run ruff check on changed files
ruff check src/k8s_diag_agent/health/artifact_readers.py
ruff check src/k8s_diag_agent/health/review.py

# Run security baseline
bash scripts/check_security_baseline.sh --mode baseline
```

### Next Artifact Family Recommendation

After DrilldownArtifact, consider:

1. **`ClusterSnapshot`**: Used in CLI and batch, has `from_dict()`
2. **`NotificationArtifact`**: Uses `from_dict()` in `health/notifications.py`
3. **`HealthAssessmentArtifact`**: Used in review pipeline, has `from_dict()`

---

## Typed Artifact Reader: ClusterSnapshot (Phase 2 Follow-up)

### Overview

This section documents the ClusterSnapshot typed artifact reader as the next step after DrilldownArtifact.

### New Files

- `src/k8s_diag_agent/health/artifact_readers.py` - ClusterSnapshot typed readers (added to existing module)
- `tests/unit/test_cluster_snapshot_artifact_readers.py` - Reader tests

### Reader API

```python
# Strict reader - raises on failure
def read_cluster_snapshot_artifact(path: Path) -> ClusterSnapshot:
    """Read and parse a ClusterSnapshot from disk.

    Raises:
        OSError: If the file cannot be read
        json.JSONDecodeError: If the file content is not valid JSON
        ValueError: If the JSON is valid but not a mapping, or from_dict validation fails
        TypeError: If from_dict receives unexpected type
        KeyError: If required fields are missing in from_dict
    """

# Optional reader - returns None on failure
def try_read_cluster_snapshot_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "cluster-snapshot",
    log_failures: bool = True,
) -> ClusterSnapshot | None:
    """Try to read a ClusterSnapshot, returning None on failure.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.
    """
```

### Error Handling Contract

- **Strict reader raises**:
  - `OSError`
  - `json.JSONDecodeError`
  - `ValueError`
  - `TypeError`
  - `KeyError`
- **Optional reader returns** `None` on those failures
- **Optional reader logs only when** `log_failures=True`

### Logging Policy

- Safe metadata only:
  - artifact filename
  - artifact kind
  - run_id (if safe)
  - error type
- Never log raw snapshot content, Kubernetes object specs, pod logs, events, kubeconfig, tokens, or full absolute paths

### ClusterSnapshot Call Site Inventory

| File | Function | Type | Pattern | Classification |
|------|----------|------|---------|----------------|
| `cli_handlers.py` | `_load_snapshot` | targeted read | CLI compare/assess snapshot read | **fixed-this-slice** |
| `health/adaptation.py` | `_load_fixture_snapshot` | fixture load | Test/fixture loading | **skipped** (not a production read path) |
| `external_analysis/alertmanager_artifact.py` | `read_alertmanager_snapshot` | targeted read | Alertmanager snapshot read | **skipped** (different artifact type) |

### Chosen Call Sites and Rationale

**Migrated (1 call site)**:

- `cli_handlers.py::_load_snapshot`: Targeted CLI read used by `handle_compare` and `handle_assess_snapshots`. This is a strict CLI path where failures should propagate (malformed snapshots should fail fast, as is appropriate for CLI operations). The pattern already uses `json.loads() + from_dict()` which maps directly to the typed reader.

**Skipped**:

- `health/adaptation.py::_load_fixture_snapshot`: Fixture loading for testing, not a production read path. The fixture validation already handles malformed input.
- `external_analysis/alertmanager_artifact.py::read_alertmanager_snapshot`: Alertmanager snapshots are a different artifact type with their own schema and `from_dict()`.

### Compatibility Decision

**No legacy dict fallback needed**: ClusterSnapshot does not have the same legacy fallback requirement because:

1. ClusterSnapshot schema is stable with required `cluster_id` field in metadata
2. All existing artifacts should pass `from_dict()` validation
3. CLI behavior (strict parsing) is preserved - malformed snapshots fail fast

### Preserved Behavior

- Valid snapshots still load and render the same
- Malformed snapshots still fail with explicit exceptions (CLI behavior)
- No API response shape changes
- No CLI output shape changes
- No change to write-path schema

### Tests Added

| Test | Purpose |
|------|---------|
| `test_valid_snapshot_loads_and_returns_typed_object` | Valid snapshot parses into ClusterSnapshot |
| `test_malformed_json_fails_with_json_decode_error` | Strict reader raises JSONDecodeError |
| `test_missing_required_cluster_id_field_fails` | Strict reader raises KeyError/ValueError |
| `test_non_object_json_fails` | Strict reader raises ValueError |
| `test_unreadable_missing_file_raises_os_error` | Strict reader raises OSError |
| `test_roundtrip_with_all_fields` | Snapshot roundtrip preserves all fields |
| `test_valid_snapshot_returns_typed_object` | Optional reader returns typed object |
| `test_malformed_json_returns_none_and_logs` | Optional reader returns None + logs |
| `test_missing_file_returns_none` | Optional reader returns None |
| `test_log_failures_false_returns_none_without_logging` | log_failures=False suppresses warnings |
| `test_log_failures_false_with_valid_snapshot` | Valid snapshot returns object even with log_failures=False |
| `test_missing_cluster_id_returns_none` | Optional reader returns None |
| `test_array_json_returns_none` | Optional reader returns None |
| `test_cli_load_snapshot_still_works` | Regression: CLI pattern preserved |
| `test_cli_compare_reports_differences_still_works` | Regression: compare behavior preserved |
| `test_malformed_snapshot_raises_in_strict_mode` | Regression: strict mode behavior preserved |

### Verification

```bash
# Run new reader tests
pytest tests/unit/test_cluster_snapshot_artifact_readers.py -v

# Run affected call-site tests
pytest tests/unit/test_cli_compare.py -v

# Run ruff check on changed files
ruff check src/k8s_diag_agent/health/artifact_readers.py
ruff check src/k8s_diag_agent/cli_handlers.py

# Run security baseline
bash scripts/check_security_baseline.sh --mode baseline
```

### Next Artifact Family Recommendation

After ClusterSnapshot, consider:

1. **`NotificationArtifact`**: Uses `from_dict()` in `health/notifications.py`
2. **`HealthAssessmentArtifact`**: Used in review pipeline, has `from_dict()`

---

## Typed Artifact Reader: NotificationArtifact (Phase 2 Follow-up)

### Overview

This section documents the NotificationArtifact typed artifact reader as the next step after ClusterSnapshot.

### New Files

- `src/k8s_diag_agent/health/artifact_readers.py` - NotificationArtifact typed readers (added to existing module)
- `tests/unit/test_notification_artifact_readers.py` - Reader tests

### Reader API

```python
# Strict reader - raises on failure
def read_notification_artifact(path: Path) -> NotificationArtifact:
    """Read and parse a NotificationArtifact from disk.

    Raises:
        OSError: If the file cannot be read
        json.JSONDecodeError: If the file content is not valid JSON
        ValueError: If the JSON is valid but not a mapping, or from_dict validation fails
        TypeError: If from_dict receives unexpected type
        KeyError: If required fields are missing in from_dict
    """

# Optional reader - returns None on failure
def try_read_notification_artifact(
    path: Path,
    *,
    run_id: str = "",
    artifact_kind: str = "notification",
    log_failures: bool = True,
) -> NotificationArtifact | None:
    """Try to read a NotificationArtifact, returning None on failure.

    Logs a warning with safe metadata on failure when log_failures=True.
    Never logs raw content.
    """
```

### Error Handling Contract

- **Strict reader raises**:
  - `OSError`
  - `json.JSONDecodeError`
  - `ValueError`
  - `TypeError`
  - `KeyError`
- **Optional reader returns** `None` on those failures
- **Optional reader logs only when** `log_failures=True`

### Logging Policy

- Safe metadata only:
  - artifact filename
  - artifact kind
  - run_id (if safe)
  - error type
- Never log raw notification content, notification message text, cluster details, Kubernetes object specs, pod logs, events, kubeconfig, tokens, or full absolute paths

### NotificationArtifact Call Site Inventory

| File | Function | Type | Pattern | Classification |
|------|----------|------|---------|----------------|
| `ui/notifications.py` | `_load_notification_records` | broad scan | notification glob scan | **fixed-this-slice** |
| `ui/notifications.py` | `_load_notification_records_optimized` | broad scan | notification glob scan | **fixed-this-slice** |
| `ui/notifications.py` | `_count_matching_records` | broad scan | count pass scan | **fixed-this-slice** |
| `ui/server_read_support.py` | `_load_notifications_for_run` | broad scan | run-specific notification scan | **available** (not migrated) |
| `health/ui.py` | `_serialize_notifications` | read path | notification serialization | **available** (not migrated) |
| `health/notifications.py` | write path | write | notification artifact write | **skipped** (write path) |

### Chosen Call Sites and Rationale

**Migrated in this slice**: The three `ui/notifications.py` functions use `try_read_notification_artifact()` with `log_failures=False` for broad scan patterns:
- `_load_notification_records`: Full glob scan with metadata-first filtering; malformed notifications are silently skipped
- `_load_notification_records_optimized`: Same pattern, optimized for large directories
- `_count_matching_records`: Count pass scan; uses kind_filter to force full parse (skips malformed)

These functions preserve the existing behavior: valid notifications load, malformed are silently skipped, and legacy notifications without `artifact_id` load through permissive `from_dict()`.

**Available for future migration**:
- `ui/server_read_support.py::_load_notifications_for_run`: run-specific notification scan
- `health/ui.py::_serialize_notifications`: notification serialization

### Compatibility Decision

**Permissive from_dict() behavior preserved**: NotificationArtifact.from_dict() is intentionally permissive:
- Missing `kind` field → becomes empty string `""`
- Missing `summary` field → becomes empty string `""`
- Missing `artifact_id` field → becomes `None` (legacy compatibility)

This permissive behavior is by design to handle legacy notifications and notifications from older schema versions. The typed reader preserves this behavior.

### Preserved Behavior

- Valid notifications still load and render the same
- Malformed JSON still causes explicit exceptions (from `json.loads`)
- Non-object JSON (array) raises `ValueError` (from reader's mapping check)
- Malformed from_dict data still returns object (permissive from_dict)
- No API response shape changes
- No change to write-path schema
- Legacy notifications without `artifact_id` still load correctly

### Tests Added

| Test | Purpose |
|------|---------|
| `test_valid_notification_loads_typed_object` | Valid notification parses into NotificationArtifact |
| `test_malformed_json_raises_json_decode_error` | Strict reader raises JSONDecodeError |
| `test_missing_file_raises_os_error` | Strict reader raises OSError |
| `test_non_object_json_raises_value_error` | Strict reader raises ValueError |
| `test_missing_kind_field_becomes_empty_string` | Permissive from_dict behavior |
| `test_missing_summary_field_becomes_empty_string` | Permissive from_dict behavior |
| `test_roundtrip_with_all_fields` | Notification roundtrip preserves all fields |
| `test_valid_notification_returns_typed_object` | Optional reader returns typed object |
| `test_malformed_json_returns_none_with_logging` | Optional reader returns None + logs |
| `test_malformed_json_returns_none_silently_without_logging` | log_failures=False suppresses warnings |
| `test_missing_file_returns_none` | Optional reader returns None |
| `test_missing_file_silent_with_log_failures_false` | log_failures=False suppresses warnings |
| `test_non_object_json_returns_none` | Optional reader returns None |
| `test_missing_required_field_returns_object_permissively` | Permissive from_dict behavior |
| `test_log_failures_true_logs_warning_with_safe_message` | Logs only safe metadata |
| `test_roundtrip_serialization_preserves_fields` | Roundtrip preserves all fields |
| `test_log_failures_false_does_not_log_raw_content` | Sensitive content never logged |
| `test_exception_carrying_safe_path` | NotificationArtifactReadError uses basename only |
| `test_exception_with_cause` | NotificationArtifactReadError chains cause |
| `test_notification_scan_preserves_valid_skips_invalid` | Call-site behavior preserved |
| `test_notification_with_artifact_id_loads_correctly` | artifact_id handling verified |
| `test_legacy_notification_without_artifact_id_loads_correctly` | Legacy compatibility verified |

### Verification

```bash
# Run new reader tests
pytest tests/unit/test_notification_artifact_readers.py -v

# Run ruff check on changed files
ruff check src/k8s_diag_agent/health/artifact_readers.py
ruff check tests/unit/test_notification_artifact_readers.py

# Run security baseline
bash scripts/check_security_baseline.sh --mode baseline
```

### Next Artifact Family Recommendation

After NotificationArtifact, consider:

1. **`HealthAssessmentArtifact`**: Used in review pipeline, has `from_dict()`
2. No further artifact families identified for typed reader migration at this time

---

## Typed Artifact Reader: HealthAssessmentArtifact (Phase 2 Follow-up)

### Overview

This section documents the HealthAssessmentArtifact typed artifact reader as the final step in the typed reader hardening sequence.

### New Files

- `src/k8s_diag_agent/health/artifact_readers.py` - HealthAssessmentArtifact typed readers (added to existing module)
- `tests/unit/test_health_assessment_artifact_readers.py` - Reader tests

### HealthAssessmentArtifact Call Site Inventory

| File | Function | Type | Pattern | Classification |
|------|----------|------|---------|----------------|
| `health/loop.py` | write path | artifact creation | Health assessment artifact write | **skipped** (write path) |
| `health/review.py` | `load_assessment` | targeted read | Assessment artifact read for drilldown | **available** (not migrated) |
| `health/summary.py` | `_load_json` | broad scan | Assessment glob scan | **available** (not migrated) |
| `health/ui.py` | `_serialize_assessment` | read path | Assessment serialization | **available** (not migrated) |
| `health/review_feedback.py` | `_extract_assessment_data` | data extraction | Assessment data access | **skipped** (in-memory, not read) |

### Chosen Call Sites and Rationale

**Migrated (0 call sites in this slice)**: No existing call sites currently use raw `json.loads() + from_dict()` pattern for HealthAssessmentArtifact reading. The existing paths use different approaches:

- `health/summary.py::_load_json`: Uses raw dict access for summary building (not typed object operations)
- `health/review.py::load_assessment`: Reads `AssessorAssessment` from the `assessment` field, not the outer HealthAssessmentArtifact
- `health/ui.py::_serialize_assessment`: Uses in-memory objects passed directly to serialization

The typed reader helper is provided for future use, but no existing call sites require migration at this time.

### from_dict() Added to HealthAssessmentArtifact

Added `from_dict()` class method to `HealthAssessmentArtifact` in `health/loop.py`:

```python
@classmethod
def from_dict(cls, raw: Mapping[str, Any]) -> HealthAssessmentArtifact:
    """Parse a HealthAssessmentArtifact from a dict (e.g., from JSON).

    Preserves permissive behavior for backward compatibility with
    legacy artifacts that may have partial data.
    """
```

**Key design decisions**:

- `assessment` field: Can be dict or None → becomes `{}` for partial/legacy artifacts
- `health_rating`: String or HealthRating → attempts enum parse, defaults to `HealthRating.UNKNOWN`
- `missing_evidence`: Can be list/tuple → converts to tuple
- All other fields: permissive str() conversion with empty string defaults

### Compatibility Decision

**Permissive from_dict() behavior preserved**: HealthAssessmentArtifact.from_dict() is intentionally permissive to handle legacy artifacts:

- Missing `assessment` field → becomes `{}`
- Missing/invalid `health_rating` → becomes `HealthRating.UNKNOWN`
- Missing `timestamp` → becomes current time (for partial artifacts)
- Missing `notes`/`artifact_path` → becomes `None`

This permissive behavior ensures backward compatibility with partial or older artifacts.

### Error Handling Contract

- **Strict reader raises**:
  - `OSError`
  - `json.JSONDecodeError`
  - `ValueError`
  - `TypeError`
  - `KeyError`
- **Optional reader returns** `None` on those failures
- **Optional reader logs only when** `log_failures=True`

### Logging Policy

- Safe metadata only:
  - artifact filename
  - artifact kind
  - run_id (if safe)
  - error type
- Never log raw assessment content, findings, hypotheses, prompts, responses, kubeconfig, tokens, or full absolute paths

### Preserved Behavior

- Valid assessments still load and render the same
- Malformed JSON still causes explicit exceptions (from `json.loads`)
- Non-object JSON (array) raises `ValueError` (from reader's mapping check)
- Partial/legacy artifacts still load through permissive `from_dict()`
- No API response shape changes
- No change to write-path schema

### Tests Added

| Test | Purpose |
|------|---------|
| `test_valid_assessment_loads_and_returns_typed_object` | Valid assessment parses into HealthAssessmentArtifact |
| `test_malformed_json_fails_with_json_decode_error` | Strict reader raises JSONDecodeError |
| `test_non_object_json_fails` | Strict reader raises ValueError |
| `test_unreadable_missing_file_raises_os_error` | Strict reader raises OSError |
| `test_roundtrip_with_all_fields` | Assessment roundtrip preserves all fields |
| `test_empty_assessment_field_becomes_empty_dict` | Permissive from_dict behavior |
| `test_invalid_health_rating_defaults_to_unknown` | Default rating for invalid value |
| `test_valid_assessment_returns_typed_object` | Optional reader returns typed object |
| `test_malformed_json_returns_none_and_logs` | Optional reader returns None + logs |
| `test_missing_file_returns_none` | Optional reader returns None |
| `test_log_failures_false_returns_none_without_logging` | log_failures=False suppresses warnings |
| `test_log_failures_false_with_valid_assessment` | Valid assessment returns object even with log_failures=False |
| `test_array_json_returns_none` | Optional reader returns None |
| `test_log_failures_true_logs_warning_with_safe_message` | Logs only safe metadata |
| `test_exception_carrying_safe_path` | HealthAssessmentArtifactReadError uses basename only |
| `test_exception_without_path` | Handles None path |
| `test_exception_with_cause` | Chains cause properly |
| `test_roundtrip_preserves_all_fields` | Roundtrip preserves all fields |

### Verification

```bash
# Run new reader tests
pytest tests/unit/test_health_assessment_artifact_readers.py -v

# Run ruff check on changed files
ruff check src/k8s_diag_agent/health/artifact_readers.py
ruff check tests/unit/test_health_assessment_artifact_readers.py

# Run security baseline
bash scripts/check_security_baseline.sh --mode baseline
```

### Summary

**HealthAssessmentArtifact typed reader is complete**.

All typed artifact reader families have been implemented:
1. ✅ `ExternalAnalysisArtifact` (external_analysis/artifact_readers.py)
2. ✅ `HealthProposal` (health/artifact_readers.py)
3. ✅ `DrilldownArtifact` (health/artifact_readers.py)
4. ✅ `ClusterSnapshot` (health/artifact_readers.py)
5. ✅ `NotificationArtifact` (health/artifact_readers.py)
6. ✅ `HealthAssessmentArtifact` (health/artifact_readers.py) - **this slice**

No further artifact families identified for typed reader migration at this time.

---

## LLM/Provider Boundary Cleanup Plan

### Scope

This section documents the LLM/provider exception boundary review as part of Security Hardening Phase 2 follow-up.

**Reviewed date**: 2026-05-07

### Remaining LLM/Provider Broad Handlers

| File | Line | Context | Classification | Exception Surface | Current Handling |
|------|------|---------|----------------|-------------------|-----------------|
| `health/loop_review_pipeline.py` | 82 | `build_health_review()` call | **reviewed-safe** (domain boundary) | ValueError, TypeError, AttributeError | `return None, ()` — review not built, no proposals |
| `health/loop_review_pipeline.py` | 117 | `generate_proposals_from_review()` call | **reviewed-safe** (domain boundary) | Various exceptions from assessment/drilldown processing | Structured log + returns review_path only |
| `external_analysis/llamacpp_adapter.py` | 249 | HTTP call to LLM provider in `_run_http` | **reviewed-safe** (LLM provider boundary) | Provider HTTP errors, connection errors, timeouts, unexpected SDK errors | Produces structured `ExternalAnalysisArtifact` with `LLMFailureMetadata` |
| `health/loop.py` | 2500 | LLM call for auto-drilldown in `_run_auto_drilldown_analysis` | **reviewed-safe** (LLM provider boundary) | Provider network/HTTP errors, wrapped exceptions, SDK errors | FAILED status with `failure_metadata` (when available) |
| `health/loop.py` | 2716 | LLM call for review enrichment in `_run_review_enrichment` | **reviewed-safe** (LLM provider boundary) | Provider network/HTTP errors, wrapped exceptions, SDK errors | FAILED status with bounded `error_summary` |
| `health/loop_alertmanager_port_forward.py` | 237 | Port-forward cleanup finalizer | **reviewed-safe** (finalizer boundary) | Any unexpected exception during cleanup | Logs error + continues — must not crash loop |

### Why These Are Harder Than File/Parser Boundaries

Unlike file I/O and JSON parsing, LLM/provider boundaries face:

1. **Opaque exception surfaces**: Provider errors may include network failures, protocol errors, rate limiting, authentication failures, malformed responses, schema validation errors, unexpected SDK errors, and wrapped exceptions (via `__cause__`/`__context__`).

2. **Provider-specific behavior**: Each provider (llamacpp, openai, anthropic, etc.) has unique error shapes. Narrowing requires comprehensive testing of each provider's exception surface.

3. **Non-fatal containment requirement**: All LLM provider failures must be non-fatal. The health loop must continue regardless of provider failures. Narrowing must preserve this guarantee.

4. **Structured failure artifacts**: The current implementation already produces typed `ExternalAnalysisArtifact` with structured `failure_metadata`. This is the "right" abstraction — exceptions flow into failure artifacts, not into caller code.

5. **Classified failure metadata**: `classify_llm_failure()` already categorizes exceptions into `LLMFailureClass` (e.g., `TIMEOUT`, `CONNECTION_ERROR`, `RATE_LIMITED`, `AUTH_ERROR`, `SCHEMA_ERROR`, `UNKNOWN`). This is the typed boundary we want.

### Current Design

The LLM/provider boundary already has a well-structured design:

```
Provider Call → classify_llm_failure() → LLMFailureMetadata → ExternalAnalysisArtifact
                                            ↓
                                    failure_metadata dict
                                    (safe fields only)
```

**Safe fields in failure_metadata**:
- `failure_class` — LLMFailureClass enum value (string)
- `exception_type` — exception class name (string)
- `timeout_seconds` — configured timeout
- `elapsed_ms` — call duration
- `endpoint` — sanitized endpoint (no credentials)
- `summary` — bounded error message
- `llm_call`, `llm_call_id`, `llm_provider`, `llm_operation` — call metadata

**What is NOT logged**:
- Raw prompts
- Raw responses
- Tokens
- Authorization headers
- Kubeconfig
- Cluster object payloads

### Why Existing Patterns Are Sufficient

1. **Typed failure artifacts**: `ExternalAnalysisArtifact` with `SKIPPED`/`FAILED` status is the right abstraction for provider failures.

2. **Classified metadata**: `LLMFailureMetadata` with `LLMFailureClass` already provides the taxonomy that a `ProviderBoundaryError` hierarchy would provide — but without the complexity.

3. **Structured logging**: Safe metadata fields are logged, not raw exception content.

4. **Non-fatal behavior**: All handlers produce failure artifacts and continue, preserving the health loop guarantee.

5. **No credential exposure**: Error summaries use bounded extraction, not raw `str(exc)`.

### Recommended Migration Path

**If future work is needed**, consider these in priority order:

1. **Add adapter-level specific exception handling**: If a specific provider (e.g., llamacpp) has known recoverable errors, add specific exception handlers within that adapter's `_run_http` method before the broad catch.

2. **Document the failure artifact contract**: Ensure all consumers of `ExternalAnalysisArtifact` handle `SKIPPED`/`FAILED` status consistently. This is the "error boundary" contract.

3. **Add provider-specific error codes**: If providers return structured error codes (e.g., OpenAI's `error.code`), extract them into `failure_metadata`. Currently only `failure_class` (enum) is used.

4. **Consider typed `ProviderError` hierarchy only if**: Multiple providers need shared error classification logic that `LLMFailureMetadata` can't capture. At that point, a `ProviderError` base class with specific subclasses would reduce duplication.

### Why Not Introduce ProviderBoundaryError Taxonomy Now

Introducing a `ProviderBoundaryError` hierarchy would:
- Add a new exception hierarchy with multiple subclasses
- Require changes to all LLM call sites
- Need comprehensive test coverage for each exception type
- Risk breaking the non-fatal guarantee if any exception escapes

The current pattern:
- Uses existing `Exception` catch with `classify_llm_failure()` for categorization
- Produces typed failure artifacts (not raising exceptions)
- Preserves non-fatal behavior without exception hierarchies

### First Safe Candidate (for future reference)

The `loop_alertmanager_port_forward.py` port-forward cleanup finalizer (line 237) is the "easiest" boundary — but it should NOT be narrowed because:
1. It's a finalizer that MUST not propagate exceptions
2. The subprocess has already been closed by the typed handler above it (line 222)
3. The broad catch is intentional defensive containment

**Recommendation**: Do not narrow any LLM/provider boundary handlers at this time. The current design is sufficient and well-documented.

### Verification Status

```bash
# Baseline check (should pass)
bash scripts/check_security_baseline.sh --mode baseline

# Strict check:
# - expected to fail while reviewed-safe broad handlers remain
# - currently reports 27 allowlisted findings overall
# - 6 of those are LLM/provider/finalizer handlers covered by this section
bash scripts/check_security_baseline.sh --mode strict
```

**Allowlist entries for these handlers (6 total — subset of 27 global allowlisted)**:
- `health/loop.py assess_drilldown_artifact LLM call boundary in auto-drilldown`
- `health/loop.py _enrich_with_llm_review review enrichment LLM call boundary`
- `health/loop.py _run_review_enrichment review enrichment LLM call boundary`
- `health/loop_review_pipeline.py write_review_and_proposals health review build boundary`
- `external_analysis/llamacpp_adapter.py _run_http LLM provider failure boundary`
- `health/loop_alertmanager_port_forward.py stop_alertmanager_port_forward port-forward cleanup final containment`

### Summary

All 6 remaining LLM/provider broad handlers are **reviewed-safe**:
- Current handling is structured and well-documented
- `LLMFailureMetadata` + `classify_llm_failure()` provides the taxonomy
- Typed `ExternalAnalysisArtifact` is the right error boundary abstraction
- Non-fatal behavior is preserved
- No credential exposure in logging/metadata

**Decision**: Design-only (no code changes). Document the boundary contract and recommend maintaining the current pattern.

**Next recommended boundary**: Continue with other reviewed-safe areas in the allowlist (e.g., UI read loops, batch execution, CLI handlers) or wait for a specific provider exception surface to be identified that warrants narrowing.

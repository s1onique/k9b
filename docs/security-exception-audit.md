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

## Broader Exception Audit - Out-of-Scope Modules

### src/k8s_diag_agent/ui/server.py

Multiple `except Exception` handlers in the main server module. These require careful review as they handle HTTP request/response semantics and framework behavior.

**Review status**: Deferred to future slice

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
| Fixed previous slices (read-model scope) | 18 |
| Reviewed safe | 1 |
| Needs follow-up | 0 |
| Out of scope (deferred modules) | ~100+ |
| **Total fixed** | **57** |

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
| server.py | ~15 | Main server handlers |
| health/loop.py | ~14 | Main health loop |
| health/ui_planner_queue.py | ~1 | Planner queue |
| health/ui_llm_stats.py | ~1 | LLM stats |
| external_analysis/* | ~8 | External analysis modules |

**Note**: These are deferred to future slices pending careful review of framework/async behavior.
**ui/notifications.py**: All 4 broad handlers fixed in Slice 10 (0 remaining)
**server_alertmanager.py**: All 6 broad handlers fixed in Slice 9 (0 remaining)
**server_feedback.py**: All 10 broad handlers fixed in Slice 8 (0 remaining)
**api.py**: All 9 broad handlers fixed in Slice 7 (0 remaining)

---

## Next Steps

1. **Immediate**: Continue auditing remaining UI/API exception handlers
2. **Short-term**: Address needs-follow-up handlers in server_next_checks.py
3. **Medium-term**: Audit server.py and api.py exception handlers
4. **Long-term**: Add eval coverage for exception handling behavior

---

*Audit created: 2026-01-05*
*Audit scope: Phase 2 Security Hardening - Read-Model Artifact Parsing Paths*
*Updated: 2026-05-04 (Slice 10: ui/notifications.py all 4 handlers fixed)*
*Total handlers fixed in Phase 2: 57 (18 read-model + 10 server_next_checks.py + 9 ui/api.py + 10 server_feedback.py + 6 server_alertmanager.py + 4 ui/notifications.py)*

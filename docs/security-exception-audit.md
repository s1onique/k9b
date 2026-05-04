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

Multiple `except Exception` handlers in the API module. Requires careful review for framework semantics.

**Review status**: Deferred to future slice

### src/k8s_diag_agent/ui/server_feedback.py

Multiple `except Exception` handlers in feedback handlers. Requires careful review.

**Review status**: Deferred to future slice

### src/k8s_diag_agent/ui/server_alertmanager.py

Multiple `except Exception` handlers in Alertmanager UI handlers.

**Review status**: Deferred to future slice

### src/k8s_diag_agent/health/loop.py

Many `except Exception` handlers in the main health loop. These are central to the health assessment flow.

**Review status**: Deferred to future slice

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
| Fixed this slice (server_next_checks.py - Phase 2 Slice 6) | 10 |
| Fixed previous slices (read-model scope) | 18 |
| Reviewed safe | 1 |
| Needs follow-up | 0 |
| Out of scope (deferred modules) | ~100+ |
| **Total fixed** | **28** |

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
| api.py | ~10 | API mutation handlers |
| server_feedback.py | ~10 | Feedback handlers |
| server_alertmanager.py | ~6 | Alertmanager UI |
| notifications.py | ~4 | Notification handlers |
| health/loop.py | ~14 | Main health loop |
| health/ui_planner_queue.py | ~1 | Planner queue |
| health/ui_llm_stats.py | ~1 | LLM stats |
| external_analysis/* | ~8 | External analysis modules |

**Note**: These are deferred to future slices pending careful review of framework/async behavior.

---

## Next Steps

1. **Immediate**: Continue auditing remaining UI/API exception handlers
2. **Short-term**: Address needs-follow-up handlers in server_next_checks.py
3. **Medium-term**: Audit server.py and api.py exception handlers
4. **Long-term**: Add eval coverage for exception handling behavior

---

*Audit created: 2026-01-05*
*Audit scope: Phase 2 Security Hardening - Read-Model Artifact Parsing Paths*
*Updated: 2026-05-04 (Slice 6: server_next_checks.py mutation write paths - all 10 handlers fixed)*
*Total handlers fixed in Phase 2: 28 (18 read-model + 10 server_next_checks.py)*

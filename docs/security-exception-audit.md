# Security Exception Audit - Read-Model Artifact Parsing

## Scope
This audit covers broad `except Exception` handlers in artifact scan/read-model paths.
Phase 2 security baseline work: replacing silent catches with explicit exception handling and structured warnings.

## Classification Legend
- **fixed-this-slice**: Handler fixed in this audit slice
- **reviewed-safe**: Handler reviewed, confirmed safe as-is
- **needs-follow-up**: Handler identified but not yet fixed
- **out-of-scope**: Handler outside current audit scope

---

## Findings by File

### src/k8s_diag_agent/ui/server_read_support.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| 115 | `except Exception: continue` | JSON parse/read for Alertmanager review artifacts | **fixed-this-slice** |
| 338 | `except Exception: continue` | JSON parse/read for drilldown data in `_build_clusters_and_drilldown_availability` | **fixed-this-slice** |
| 459 | `except Exception: continue` | JSON parse/read for proposals in `_load_proposals_for_run` | **fixed-this-slice** |
| 510 | `except Exception: continue` | JSON parse/read for external analysis scan | **fixed-this-slice** |
| 548 | `except Exception: continue` | JSON parse/read for notifications | **fixed-this-slice** |
| 744 | `except Exception: continue` | JSON parse/read in `_build_run_artifact_index` | needs-follow-up |
| 802 | `except Exception: continue` | JSON parse/read for review enrichment fallback | needs-follow-up |
| 886 | `except Exception: continue` | JSON parse/read for next-check plan | needs-follow-up |
| 1059 | `except Exception: continue` | JSON parse/read for execution artifacts | needs-follow-up |
| 1216 | `except Exception: continue` | JSON parse/read for LLM stats | needs-follow-up |

**Total in file**: 10 handlers (5 fixed, 5 remaining)

### src/k8s_diag_agent/health/ui.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| 335 | `except Exception: continue` | `ExternalAnalysisArtifact.from_dict()` in `_serialize_review_enrichment` | **fixed-this-slice** |
| 554 | `except Exception: continue` | JSON parse/read for review timestamps in `_collect_review_timestamps` | needs-follow-up |
| 594 | `except Exception: continue` | JSON parse/read for recent runs summary in `_build_recent_runs_summary` | needs-follow-up |
| 776 | `except Exception: continue` | JSON parse/read for promotions in `_build_promotions_index` | needs-follow-up |
| 862 | `except Exception: pass` | `write_text` in `_write_proposal_status_summary_to_review` | needs-follow-up |

**Total in file**: 5 handlers (1 fixed, 4 remaining)

### src/k8s_diag_agent/health/summary.py

| Line | Handler | Context | Classification |
|------|---------|---------|----------------|
| 307 | `except Exception: return {}` | JSON parse/read in `_load_history` | **fixed-this-slice** (opportunistic) |
| 366 | `except Exception: return {}` | JSON parse/read in `_load_json` | needs-follow-up |
| 537 | `except Exception: return []` | JSON parse/read in `_collect_comparison_summaries` | needs-follow-up |

**Total in file**: 3 handlers (1 fixed, 2 remaining)

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
except (OSError, json.JSONDecodeError, UnicodeDecodeError):
    continue
```

For `ExternalAnalysisArtifact.from_dict()` calls:
```python
except (ValueError, KeyError, TypeError):
    continue
```

---

## Audit Summary

| Category | Count |
|----------|-------|
| Fixed this slice | 7 |
| Reviewed safe | 0 |
| Needs follow-up | 11 |
| Out of scope | 0 |
| **Total** | **18** |

### Fixed This Slice (Phase 2 Audit - Read-Model Artifact Paths)

| File | Line | Handler | Type | Logging |
|------|------|---------|------|---------|
| server_read_support.py | 115 | `_load_alertmanager_review_artifacts` | OSError, json.JSONDecodeError | **yes** |
| server_read_support.py | 338 | `_build_clusters_and_drilldown_availability` | OSError, json.JSONDecodeError | **yes** |
| server_read_support.py | 459 | `_load_proposals_for_run` | OSError, json.JSONDecodeError | **yes** |
| server_read_support.py | 510 | `_scan_external_analysis` | OSError, json.JSONDecodeError | **yes** |
| server_read_support.py | 548 | `_load_notifications_for_run` | OSError, json.JSONDecodeError | **yes** |
| health/ui.py | 335 | `_serialize_review_enrichment` | ValueError, KeyError, TypeError | no (from_dict shape) |
| health/summary.py | 307 | `_load_history` | OSError, json.JSONDecodeError | no (opportunistic) |

### Logging Behavior by Category

- **server_read_support.py handlers**: Explicit exceptions `(OSError, json.JSONDecodeError)` + structured `logger.warning(..., exc_info=True)` with artifact metadata
- **health/ui.py handler**: Explicit exceptions `(ValueError, KeyError, TypeError)` for `from_dict()` shape errors, no warning (payload conversion is expected to fail on malformed data)
- **health/summary.py handler**: Explicit exceptions `(OSError, json.JSONDecodeError)` for `_load_history`, no warning (opportunistic narrowing, not part of primary artifact scan loop)

### Remaining Backlog (11 handlers)

| File | Count | Lines |
|------|-------|-------|
| server_read_support.py | 5 | 744, 802, 886, 1059, 1216 |
| health/ui.py | 4 | 554, 594, 776, 862 |
| health/summary.py | 2 | 366, 537 |

---

## Next Steps

1. **Immediate**: Continue fixing remaining server_read_support.py handlers
2. **Short-term**: Fix remaining handlers in health/ui.py and health/summary.py
3. **Medium-term**: Audit remaining exception handlers in other modules (server.py, api.py, etc.)
4. **Long-term**: Add structured logging infrastructure for artifact scan telemetry

---

*Audit created: 2026-01-05*
*Audit scope: Phase 2 Security Hardening - Read-Model Artifact Parsing Paths*
*Updated: 2026-01-05 (6 handlers fixed in this slice)*

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

For `ExternalAnalysisArtifact.from_dict()` calls:
```python
except (ValueError, KeyError, TypeError):
    continue
```

---

## Audit Summary

| Category | Count |
|----------|-------|
| Fixed this slice | 18 |
| Reviewed safe | 0 |
| Needs follow-up | 0 |
| Out of scope | 0 |
| **Total** | **18** |

### Fixed This Slice (Phase 2 Audit - Slice 4: health/summary.py remaining handlers)

| File | Line | Handler | Type | Logging |
|------|------|---------|------|---------|
| health/summary.py | 366 | `_load_json` | OSError, json.JSONDecodeError | **yes** |
| health/summary.py | 537 | `_collect_comparison_summaries` | OSError, json.JSONDecodeError | **yes** |

### Logging Behavior by Category

- **health/summary.py handlers**: Explicit exceptions `(OSError, json.JSONDecodeError)` + structured `logger.warning(..., exc_info=True)` with artifact metadata
- **health/ui.py handlers**: Explicit exceptions `(OSError, json.JSONDecodeError)` + structured `logger.warning(..., exc_info=True)` with artifact metadata
- **health/ui.py write handler**: Explicit `OSError` for write failures + structured `logger.warning(..., exc_info=True)`

### Remaining Backlog (0 handlers)

| File | Count | Lines |
|------|-------|-------|
| health/ui.py | 0 | (all fixed) |
| health/summary.py | 0 | (all fixed) |

**Read-model exception-audit scope: COMPLETE**

---

## Next Steps

1. **Immediate**: Audit remaining exception handlers in other modules (server.py, api.py, etc.)
2. **Short-term**: Add structured logging infrastructure for artifact scan telemetry
3. **Medium-term**: Implement comprehensive artifact validation schema
4. **Long-term**: Add eval coverage for exception handling behavior

---

*Audit created: 2026-01-05*
*Audit scope: Phase 2 Security Hardening - Read-Model Artifact Parsing Paths*
*Updated: 2026-05-04 (2 additional handlers fixed in slice 4 - read-model scope complete)*
*Total handlers fixed in Phase 2: 18*

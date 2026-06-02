# Health Loop Orchestration Seams — Post Result Extraction

**ACT**: Reconnaissance for next health-loop extraction  
**Date**: 2026-05-13  
**Commit**: d42a304f1ae58b4b5d8124a643f625f3115533f4  
**Status**: Reconnaissance complete

---

## 1. Current State

### File Line Counts

| File | Lines | Allowlisted |
|------|-------|-------------|
| `src/k8s_diag_agent/health/loop.py` | 2902 | ✅ Yes |
| `src/k8s_diag_agent/health/loop_scheduler.py` | 743 | ✅ Yes |
| `build_health_assessment()` | 334 (675–1008) | N/A (function) |
| `HealthLoopRunner` | 1574 (1270–2843) | N/A (class) |

### HealthLoopRunner Method Breakdown

| Lines | Method | Concern |
|-------|--------|---------|
| 302 | `_run_auto_drilldown_analysis` | LLM call handling with extensive diagnostics |
| 256 | `_run_review_enrichment` | LLM call handling with preflight and error classification |
| 157 | `_evaluate_triggers` | Comparison trigger evaluation |
| 127 | `execute` | Top-level orchestration |
| 91 | `_build_assessments` | Snapshot→assessment pipeline |
| 72 | `_run_next_check_planning` | Next-check planning from enrichment |
| 66 | `_run_external_analysis` | Manual external analysis dispatch |
| 66 | `_build_drilldowns` | Drilldown collection |
| 63 | `_write_review_artifact` | Review pipeline delegation |
| 49 | `_collect_snapshots` | Snapshot collection |
| 48 | `__init__` | Initialization |
| 33 | `_persist_history` | History persistence |
| 24 | `_run_alertmanager_snapshot_collection` | Alertmanager snapshot |
| 22 | `_run_vmalert_discovery` | vmalert discovery |
| 21 | `_run_alertmanager_discovery` | Alertmanager discovery |
| 21 | `_start_alertmanager_port_forward` | Port-forward wrapper |
| 17 | `_stop_alertmanager_port_forward` | Port-forward cleanup |
| 16 | `_run_vmalert_rule_state_collection` | vmalert rule state |
| 15 | `_determine_drilldown_reasons` | Drilldown reason delegation |
| 12 | `_wait_for_port_ready` | Port readiness wait |
| 10 | `_log_event` | Structured logging |
| 9 | `_load_history` | History loading |
| 7 | `_prune_external_analysis_history` | Retention pruning |
| 7 | `_failure_metadata_field` | Failure metadata extraction |
| 6 | `_choose_free_local_port` | Port selection |
| 4 | `_record_notification` | Notification recording |
| 2 | `latest_external_artifacts` | Artifact property |

### Checker Results

```
Checked 893 files
  Failures: 0
  Warnings: 202 (non-blocking)
```

### Test Results

```
179 passed in 6.89s
```

---

## 2. Already Extracted Health-Loop Modules

| Module | Lines | Responsibility |
|--------|-------|----------------|
| `loop_assessment_warning_events.py` | 315 | Warning event pattern matching |
| `loop_assessment_baseline.py` | 170 | Baseline policy assessment |
| `loop_assessment_history_drift.py` | 176 | Previous run drift detection |
| `loop_assessment_counts.py` | 162 | Node/pod count issue detection |
| `loop_assessment_summary.py` | 107 | Assessment summary derivation |
| `loop_assessment_regressions.py` | 157 | Regression detection from history |
| `loop_assessment_missing_evidence.py` | 113 | Missing evidence assessment |
| `loop_assessment_image_pull.py` | 93 | Image pull issue assessment |
| `loop_assessment_result.py` | 48 | HealthAssessmentResult construction (latest) |

**Total extracted**: 1241 lines

### Methods Already Delegating to Helpers

| Method | Delegates To |
|--------|--------------|
| `build_health_assessment()` | `assess_missing_evidence`, `assess_baseline_policy`, `assess_previous_run_drift`, `assess_count_issues`, `assess_image_pull_issues`, `check_regression_from_history`, `match_warning_event_patterns`, `derive_assessment_summary`, `build_health_assessment_result` |
| `_write_review_artifact()` | `loop_review_pipeline._write_review_and_proposals_impl` |
| `_determine_drilldown_reasons()` | `loop_drilldown_helpers._determine_drilldown_reasons_impl` |
| `_prune_external_analysis_history()` | `loop_retention.prune_external_analysis_history` |
| `_run_alertmanager_discovery()` | `loop_alertmanager_discovery._run_alertmanager_discovery_impl` |
| `_run_alertmanager_snapshot_collection()` | `loop_alertmanager_snapshot._run_alertmanager_snapshot_collection_impl` |
| `_run_vmalert_discovery()` | `loop_vmalert_discovery._run_vmalert_discovery_impl` |
| `_run_vmalert_rule_state_collection()` | `loop_vmalert_rule_state._run_vmalert_rule_state_collection_impl` |
| `_choose_free_local_port()` | `loop_port_forward_helpers._choose_free_local_port` |
| `_wait_for_port_ready()` | `loop_port_forward_helpers._wait_for_port_ready` |
| `_start_alertmanager_port_forward()` | `loop_alertmanager_port_forward.start_alertmanager_port_forward` |
| `_stop_alertmanager_port_forward()` | `loop_alertmanager_port_forward.stop_alertmanager_port_forward` |

---

## 3. Remaining `loop.py` Inventory

### Candidate Extraction Blocks

| Line Range | Lines | Concern | Local State | Creates Artifacts | Mutates Runner | External | Risk | Recommended Style |
|------------|-------|---------|-------------|-------------------|----------------|----------|------|-------------------|
| 2343–2414 | 72 | `_run_next_check_planning` | None | Yes (plan artifact) | No | Yes (plan_next_checks) | **Low** | Pure helper |
| 1340–1343 | 4 | `_record_notification` | `_notification_records` | Yes | Yes | Yes (write_notification_artifact) | **Low** | Stateful helper |
| 2654–2662 | 9 | `_load_history` | None (returns dict) | No | No | Yes (file read) | **Low** | Pure helper |
| 2664–2696 | 33 | `_persist_history` | None | Yes (history.json, facts) | No | Yes (file write) | **Medium** | Stateful helper |
| 1499–1505 | 7 | `_prune_external_analysis_history` | None | No | No | Yes (retention prune) | **Low** | Pure helper |
| 1557–1647 | 91 | `_build_assessments` | `record.assessment`, history dict | Yes (assessment artifacts) | Yes (record mutation) | Yes (kubectl, file write) | **Medium** | Stateful helper |
| 1716–1781 | 66 | `_run_external_analysis` | None | Yes | No | Yes (adapter.run, file write) | **Medium** | Stateful helper |
| 2496–2652 | 157 | `_evaluate_triggers` | None | Yes (trigger artifacts) | No | Yes (comparison, file write) | **Medium** | Stateful helper |
| 1349–1475 | 127 | `execute` | Multiple state fields | Yes | Yes | Yes (orchestrates all) | **High** | Leave in place |
| 1783–2084 | 302 | `_run_auto_drilldown_analysis` | None | Yes | No | Yes (LLM calls) | **High** | Leave in place |
| 2086–2341 | 256 | `_run_review_enrichment` | None | Yes | No | Yes (LLM calls) | **High** | Leave in place |

### Config/Environment Helpers Remaining

| Line Range | Lines | Concern | Risk |
|------------|-------|---------|------|
| 90–96 | 7 | `_is_openai_compatible_provider` | Low (pure function) |
| 104–114 | 11 | `HealthTarget` dataclass | Low (data model) |
| 117–138 | 22 | `ComparisonPeer`, `ComparisonIntent` | Low (data model) |
| 141–145 | 5 | `ManualComparison` | Low (data model) |
| 147–151 | 5 | `ManualExternalAnalysisRequest` | Low (data model) |
| 153–162 | 10 | `TriggerPolicy` | Low (data model) |
| 164–174 | 11 | `HealthAssessmentResult` | Low (data model) |
| 176–269 | 94 | `HealthAssessmentArtifact` | Low (data model + serialization) |
| 271–298 | 28 | `TriggerDetail` | Low (data model + serialization) |
| 300–414 | 115 | `ComparisonTriggerArtifact` | Low (data model + serialization) |
| 416–452 | 37 | `ComparisonDecision` | Low (data model + serialization) |
| 455–673 | 219 | `HealthRunConfig.load` | **Medium** (config loading, validation) |

---

## 4. Remaining `loop_scheduler.py` Inventory

### Structure Summary

| Component | Lines | Type | Status |
|-----------|-------|------|--------|
| `HealthLoopScheduler` class | ~550 | Core scheduler | Remainder |
| `schedule_health_loop()` | ~53 | Entry point | Facade |
| Re-exports | ~15 | Public API | Compatibility |

### HealthLoopScheduler Methods

| Lines | Method | Concern | Extraction Risk |
|-------|--------|---------|------------------|
| ~200 | `_evaluate_lock_state` | Lock staleness evaluation | **Medium** (policy logic) |
| ~120 | `_parse_lock_metadata` | Lock file parsing (JSON + legacy) | **Medium** (compatibility surface) |
| ~70 | `_load_lock_snapshot` | Lock file loading | **Low** (data transformation) |
| ~50 | Identity methods | Process identity handling | **Medium** (policy logic) |
| ~35 | `__init__` | Initialization | **Medium** (state management) |
| ~10 | `_log_event` | Logging | **Low** (already delegates) |

### Analysis

- `loop_scheduler.py` is already substantially decomposed:
  - `loop_scheduler_config.py` — config constants and helpers
  - `loop_scheduler_cycle.py` — cycle policy
  - `loop_scheduler_diagnostics.py` — diagnostics
  - `loop_scheduler_lock_facade.py` — lock facade
  - `loop_scheduler_locking.py` — LockManager
  - `loop_scheduler_models.py` — data models
  - `loop_scheduler_run.py` — run_scheduler_loop

- Remaining code in `loop_scheduler.py` is primarily:
  1. **Lock evaluation policy** (`_evaluate_lock_state`) — complex decision tree
  2. **Lock parsing** (`_parse_lock_metadata`) — JSON + legacy compatibility
  3. **Identity tracking** — process identity management

- **Assessment**: No compelling low-risk extraction remains. The next steps would be high-risk policy rewrites that could affect lock semantics.

---

## 5. Candidate Next Seams

### Candidate A: `_run_next_check_planning` Extraction
**Potential module**: `loop_runner_next_check_planning.py`

| Attribute | Value |
|-----------|-------|
| Lines | 72 |
| Delegate target | `plan_next_checks` (already external) |
| Artifact creation | Yes (plan artifact) |
| Runner state | None |
| Extraction risk | **Low** |
| Style | Pure helper |

**Why safe**: Single responsibility, delegates to existing pure function, creates one artifact type, no runner state mutation.

**Why not now**: Diminishing returns — already small, extraction overhead vs. benefit.

### Candidate B: `_build_assessments` Artifact Construction
**Potential module**: `loop_runner_assessment_artifacts.py`

| Attribute | Value |
|-----------|-------|
| Lines | 91 |
| Delegate targets | Multiple (image inspector, build_health_assessment, validators) |
| Artifact creation | Yes (assessment artifacts, notifications) |
| Runner state | Yes (record.assessment, record.pattern_reasons, record.pattern_metadata) |
| Extraction risk | **Medium** |
| Style | Stateful helper |

**Why safe**: Consistent with other extraction patterns, assessment artifact shape is stable.

**Why not now**: Record mutation tightens coupling, image inspector integration adds complexity.

### Candidate C: `_evaluate_triggers` Extraction
**Potential module**: `loop_runner_triggers.py`

| Attribute | Value |
|-----------|-------|
| Lines | 157 |
| Delegate targets | `_policy_eligible_pair`, `determine_pair_trigger_reasons` |
| Artifact creation | Yes (comparison, trigger, decision artifacts) |
| Runner state | None |
| Extraction risk | **Medium** |
| Style | Stateful helper |

**Why safe**: Pure-ish, delegates to existing helpers, well-defined artifact shapes.

**Why not now**: Still substantial (157 lines), comparison logic is cohesive.

### Candidate D: `_record_notification` + Notification Pattern
**Potential module**: `loop_runner_notifications.py`

| Attribute | Value |
|-----------|-------|
| Lines | 4 (+ call sites) |
| Delegate targets | `write_notification_artifact` |
| Artifact creation | Yes (notifications) |
| Runner state | Yes (`_notification_records`) |
| Extraction risk | **Low** |
| Style | Stateful helper |

**Why safe**: Tiny, clear boundary, delegates to pure helper.

**Why not now**: Very small gain, called from multiple contexts.

### Candidate E: Scheduler Lock Evaluation
**Potential module**: `loop_scheduler_evaluation.py`

| Attribute | Value |
|-----------|-------|
| Lines | ~200 (largest remaining block) |
| Runner state | Yes (LockManager) |
| Extraction risk | **High** |
| Style | Policy extraction |

**Why safe**: Strong boundary exists.

**Why not now**: Lock policy is subtle, changes could affect run correctness. High risk without comprehensive test coverage.

---

## 6. Recommendation

### Selected: Option A — `_run_next_check_planning` Extraction

**Target module**: `src/k8s_diag_agent/health/loop_runner_next_check_planning.py`

**Rationale**:

1. **Small and self-contained** (72 lines) — extraction overhead is proportional
2. **Pure delegation** — calls `plan_next_checks` which is already external
3. **Single artifact type** — creates one predictable artifact
4. **No runner state** — does not mutate `self`
5. **Cohesive concern** — next-check planning from enrichment is distinct from other pipeline stages
6. **Low risk** — failure mode is planning skips gracefully, which it already does

**Why safer than other candidates**:
- Safer than `_build_assessments` (no record mutation, no image inspector integration)
- Safer than `_evaluate_triggers` (smaller, fewer artifact types)
- Safer than scheduler lock evaluation (no correctness implications)
- More cohesive than `_record_notification` (clearer boundary than tiny wrapper)

**Alternative considered**: `_build_assessments` artifact construction — rejected due to record mutation complexity and image inspector integration.

---

## 7. Next Implementation Prompt

```markdown
# [Open] ACT: Extract next-check planning seam from HealthLoopRunner

**Target module**: `src/k8s_diag_agent/health/loop_runner_next_check_planning.py`

**Scope**: Extract `_run_next_check_planning` method from `HealthLoopRunner` in `loop.py`

**Behavior-preservation constraints**:
- Preserve exact artifact shape and path construction
- Preserve null-skip behavior when review_path or enrichment_artifact is None
- Preserve logging events and metadata
- Preserve `execution_artifacts` filtering by `ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION`
- Preserve payload construction via `plan.to_payload()`

**Expected caller shape**:
```python
# In loop.py, HealthLoopRunner.execute() replaces:
review_path, proposals = self._write_review_artifact(...)
enrichment_artifact = self._run_review_enrichment(review_path, directories)
plan_artifact = self._run_next_check_planning(review_path, enrichment_artifact, directories, execution_artifacts)

# With:
from .loop_runner_next_check_planning import run_next_check_planning
...
review_path, proposals = _write_review_and_proposals_impl(...)
enrichment_artifact = self._run_review_enrichment(review_path, directories)
plan_artifact = run_next_check_planning(
    review_path=review_path,
    enrichment_artifact=enrichment_artifact,
    directories=directories,
    run_id=self.run_id,
    log_event=self._log_event,
    execution_artifacts=execution_artifacts,
)
```

**Function signature**:
```python
def run_next_check_planning(
    review_path: Path | None,
    enrichment_artifact: ExternalAnalysisArtifact | None,
    directories: dict[str, Path],
    run_id: str,
    log_event: Callable[..., None],
    execution_artifacts: tuple[ExternalAnalysisArtifact, ...] | None = None,
) -> ExternalAnalysisArtifact | None:
```

**Dependencies to preserve**:
- `plan_next_checks` from `..external_analysis.next_check_planner`
- `write_external_analysis_artifact` from `..external_analysis.artifact`
- `ExternalAnalysisArtifact`, `ExternalAnalysisPurpose`, `ExternalAnalysisStatus` from `..external_analysis.artifact`
- `emit_structured_log` / `_log_event` for logging

**Test requirements**:
- Add unit tests for `run_next_check_planning` covering:
  - Null review_path → returns None
  - Null enrichment_artifact → returns None
  - Valid inputs → creates artifact
  - Empty plan → returns None with log
  - Non-empty plan → creates artifact with correct payload

**Verification commands**:
```bash
.venv/bin/python -m pytest tests/unit/test_loop_runner_next_check_planning.py -v
.venv/bin/python scripts/check_llm_friendly_files.py --quiet
.venv/bin/python scripts/verify_all.sh
```

**Acceptance criteria**:
- [ ] `loop_runner_next_check_planning.py` exists with `run_next_check_planning` function
- [ ] `loop.py` imports from `loop_runner_next_check_planning`
- [ ] `HealthLoopRunner._run_next_check_planning` delegates to extracted function
- [ ] Unit tests pass (if any added)
- [ ] LLM-friendly checker reports 0 failures
- [ ] `scripts/verify_all.sh` exits 0 with `VERIFICATION GATE: PASSED`
- [ ] `loop.py` and `loop_scheduler.py` remain allowlisted
- [ ] Repository is clean after commit
```

---

## 8. Summary Table

| Metric | Value |
|--------|-------|
| `loop.py` lines | 2902 |
| `loop_scheduler.py` lines | 743 |
| `build_health_assessment()` lines | 334 |
| `HealthLoopRunner` lines | 1574 |
| Largest remaining method | `_run_auto_drilldown_analysis` (302 lines) |
| Next-check planning method | `_run_next_check_planning` (72 lines) |
| LLM-friendly failures | 0 |
| Tests passing | 179/179 |
| Commit | d42a304f1ae58b4b5d8124a643f625f3115533f4 |

---

## 9. Findings

1. **`build_health_assessment()` is substantially decomposed** — 9 helper modules cover signal/finding/hypothesis/next-check logic. Only final result assembly remains.

2. **`HealthLoopRunner` is the primary extraction target** — 1574 lines across 27 methods. Largest methods are LLM call handlers and trigger evaluation.

3. **`_run_next_check_planning` is the safest next candidate** — 72 lines, pure delegation, single artifact, no state mutation.

4. **`loop_scheduler.py` is near-complete** — Remaining code is lock evaluation policy (~200 lines) which is high-risk to refactor.

5. **No production code moved in this reconnaissance** — Report is informational only.

# Seam Map: Assessment and Comparison Orchestration

## Status: Already Extracted

Assessment and comparison orchestration wrappers are already minimal. No further extraction is needed.

---

## 1. Assessment Orchestration Seam

### `HealthLoopRunner._build_assessments`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 648-667)

**Wrapper size:** 20 lines

**Extracted implementation:** `src/k8s_diag_agent/health/loop_runner_assessments.py`
- 181 lines total
- Function: `build_assessments_for_records(...)`

**Dependencies passed explicitly:**
- `records`, `history`, `assessment_dir`, `notification_dir` - data and paths
- `run_id`, `run_label` - for artifact metadata
- `warning_event_threshold` - from `self.config.trigger_policy`
- `record_notification_fn` - `self._record_notification` callback
- `image_pull_inspector` - `self._image_pull_secret_inspector`
- `log_event_fn` - `self._log_event` callback

**Runner-state coupling:** None beyond explicit parameter passing.

**Behavior preserved:**
- Image pull secret inspection (best-effort, non-fatal)
- Health assessment building with warning threshold
- Assessment artifact validation and writing
- Degraded-health notification emission
- History mutation for each cluster

---

## 2. Drilldown Orchestration Seam

### `HealthLoopRunner._build_drilldowns`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 669-685)

**Wrapper size:** 17 lines

**Extracted implementation:** `src/k8s_diag_agent/health/loop_runner_drilldowns.py`
- 147 lines total
- Function: `build_drilldowns_for_records(...)`

**Dependencies passed explicitly:**
- `records`, `previous_history`, `directory` - data and paths
- `run_id`, `run_label` - for artifact metadata
- `drilldown_collector` - `self._drilldown_collector`
- `manual_drilldown_contexts` - `self._manual_drilldown_contexts`
- `warning_event_threshold` - from `self.config.trigger_policy`
- `log_event_fn` - `self._log_event` callback

**Runner-state coupling:** None beyond explicit parameter passing.

**Behavior preserved:**
- Drilldown reason determination using assessment data
- Drilldown evidence collection using DrilldownCollector
- Drilldown artifact validation and writing
- Non-fatal collection failures (logged as warnings)

---

## 3. Comparison Orchestration Seam

### `HealthLoopRunner._evaluate_triggers`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1362-1386)

**Wrapper size:** 25 lines

**Extracted implementation:** `src/k8s_diag_agent/health/loop_runner_comparisons.py`
- 290 lines total
- Function: `evaluate_triggers_for_records(...)`

**Dependencies passed explicitly:**
- `records` - list of health snapshot records
- `peers` - from `self.config.peers`
- `trigger_policy` - from `self.config.trigger_policy`
- `baseline_registry` - `self.baseline_registry`
- `history` - previous history entries
- `run_id`, `run_label` - for artifact metadata
- `manual_comparison_keys` - `self._manual_keys`
- `comparison_fn` - `self.comparison_fn`
- `record_notification_fn` - `self._record_notification` callback
- `log_event_fn` - `self._log_event` callback
- `directories` - dict with comparison, triggers, root, notifications paths

**Runner-state coupling:** None beyond explicit parameter passing.

**Behavior preserved:**
- Policy eligibility checking using `_policy_eligible_pair`
- Trigger reason determination using `determine_pair_trigger_reasons`
- Snapshot comparison for triggered pairs
- Trigger artifact validation and writing
- Comparison decisions artifact with full policy metadata
- Suspicious comparison notification emission
- No-peer health-only mode logging

---

## 4. Existing Helper Modules

| Module | Lines | Function | Imports loop.py? | Imports HealthLoopRunner? |
|--------|-------|----------|------------------|--------------------------|
| `loop_runner_assessments.py` | 181 | `build_assessments_for_records` | No | No |
| `loop_runner_drilldowns.py` | 147 | `build_drilldowns_for_records` | No | No |
| `loop_runner_comparisons.py` | 290 | `evaluate_triggers_for_records` | No | No |

---

## 5. Existing Tests

### Assessment Tests (`tests/test_health_loop.py`)
- `test_build_health_assessment_crashloop_backoff_degrades` - degraded health detection
- `test_build_health_assessment_reports_history_changes` - history integration

### Comparison Tests (`tests/test_health_loop.py`)
- `test_no_comparison_when_no_trigger_fires` - trigger evaluation
- `test_no_cross_cluster_findings_when_no_comparison_triggers` - cross-cluster logic

### Drilldown Tests (`tests/unit/test_health_notifications.py`)
- `test_record_notification_drilldown_with_degraded_clusters` - drilldown notifications

### Integration Tests (`tests/test_health_loop.py`)
- Full health loop orchestration tests covering assessment/comparison/drilldown flow

---

## 6. Why Extraction Was Deferred

**Not deferred** - all seams are already fully extracted.

The extraction follows the standard pattern used throughout the health-loop epic:

1. **Thin wrappers in `HealthLoopRunner`**: Pass dependencies explicitly, delegate to helper modules
2. **Helper modules own all logic**: `loop_runner_assessments.py`, `loop_runner_drilldowns.py`, `loop_runner_comparisons.py`
3. **No `Any` at boundaries**: All parameters are typed with explicit types or duck-typed callbacks
4. **No `type: ignore` comments**: Clean typing throughout
5. **Helper modules import neither `loop.py` nor `HealthLoopRunner`**
6. **Comprehensive test coverage**: Integration and unit tests

**Wrapper sizes confirm minimality:**
- `_build_assessments`: 20 lines
- `_build_drilldowns`: 17 lines
- `_evaluate_triggers`: 25 lines

Further extraction would only create redundant indirection without adding value.

---

## 7. Next Recommended ACT

Based on remaining seam sizes in `HealthLoopRunner`, the next candidates are:

1. **`_write_review_artifact`** (lines 1282-1344)
   - 63 lines of runner logic
   - Delegates to `loop_review_pipeline.py`
   - Check if wrapper is truly minimal

2. **`_determine_drilldown_reasons`** (lines 1346-1360)
   - 15 lines but already delegates to `_determine_drilldown_reasons_impl`
   - Could potentially be removed if callers are updated

3. **LLM-heavy methods** (explicitly deferred in epic scope)
   - `_run_auto_drilldown_analysis` (lines 705-1006) - 302 lines
   - `_run_review_enrichment` (lines 1008-1263) - 256 lines
   - These require larger extraction efforts and are explicitly out of scope

---

## 8. Acceptance Criteria

- [x] `_build_assessments` inspected and documented
- [x] `_build_drilldowns` inspected and documented
- [x] `_evaluate_triggers` inspected and documented
- [x] Wrapper minimality confirmed
- [x] Existing helper modules identified and verified
- [x] Test coverage identified
- [x] No extraction needed (already extracted)
- [x] Next ACT candidates identified

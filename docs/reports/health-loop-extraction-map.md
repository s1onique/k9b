# Health Loop Extraction Map

**ACT**: `[Open] ACT: Map health loop extraction seams`  
**Generated**: 2026-01-06  
**Status**: RECONNAISSANCE COMPLETE

## 1. Current State

| Metric | Value |
|--------|-------|
| `loop.py` lines | 3,345 |
| `loop_scheduler.py` lines | 743 |
| Allowlist entry | Present (extraction target) |
| Checker result | 0 failures |

## 2. Function/Class Inventory

| Name | Line | Concern | Public/Imported |
|------|------|---------|-----------------|
| `_is_openai_compatible_provider` | 81 | Provider utility | Internal only |
| `HealthTarget` | 96 | Config dataclass | Yes (imported by tests) |
| `ComparisonPeer` | 109 | Config dataclass | Yes (imported by tests) |
| `ComparisonIntent` | 117 | Enum | Yes (imported) |
| `ManualComparison` | 133 | Config dataclass | Yes |
| `ManualExternalAnalysisRequest` | 139 | Config dataclass | Yes |
| `TriggerPolicy` | 145 | Config dataclass | Yes (imported by tests) |
| `HealthAssessmentResult` | 156 | Result dataclass | Internal |
| `HealthAssessmentArtifact` | 168 | Artifact dataclass | Yes (imported by tests) |
| `TriggerDetail` | 264 | Trigger detail | Internal |
| `ComparisonTriggerArtifact` | 293 | Trigger artifact | Yes (imported by tests) |
| `ComparisonDecision` | 409 | Decision dataclass | Yes (imported by tests) |
| `HealthRunConfig` | 447 | Config class | Yes (imported by tests) |
| `build_health_assessment` | 666 | Assessment logic | Yes (standalone function) |
| `HealthSnapshotRecord` | 1456 | Record dataclass | Internal |
| `determine_pair_trigger_reasons` | 1471 | Trigger logic | Yes (standalone function) |
| `HealthLoopRunner` | 1714 | Orchestration class | Yes (imported by tests) |
| `run_health_loop` | 3290 | Entry point | Yes (exported via __init__.py) |

## 3. Concern Grouping

### Group A: Config/Environment (Lines 81-659)
- Provider checking helper
- Config dataclasses (HealthTarget, ComparisonPeer, TriggerPolicy, HealthRunConfig)
- Config loading (`HealthRunConfig.load`)

### Group B: Assessment Building (Lines 666-1455)
- `build_health_assessment()` — standalone function (790 lines)
- Health rating logic, signal processing, evidence checking
- Image pull secret insight integration

### Group C: Trigger Determination (Lines 1456-1713)
- `HealthSnapshotRecord` dataclass
- `determine_pair_trigger_reasons()` — standalone function (242 lines)
- Pair comparison logic, history-based drift detection

### Group D: HealthLoopRunner Orchestration (Lines 1714-3290)
- Main run pipeline (`execute()`)
- Snapshot collection (`_collect_snapshots`)
- Assessment building (`_build_assessments`)
- Drilldown build (`_build_drilldowns`)
- Trigger evaluation (`_evaluate_triggers`)
- External analysis (`_run_external_analysis`, `_run_auto_drilldown_analysis`)
- Review pipeline (`_write_review_artifact`, `_run_review_enrichment`)
- Next-check planning (`_run_next_check_planning`)
- UI index writing
- Alertmanager/vmalert wiring (delegates)
- Notification recording
- History persistence

### Group E: Already-Extracted Delegators
The following methods in `HealthLoopRunner` already delegate to extracted modules:
- `_run_alertmanager_discovery` → `loop_alertmanager_discovery`
- `_run_alertmanager_snapshot_collection` → `loop_alertmanager_snapshot`
- `_run_vmalert_discovery` → `loop_vmalert_discovery`
- `_run_vmalert_rule_state_collection` → `loop_vmalert_rule_state`
- `_determine_drilldown_reasons` → `loop_drilldown_helpers`
- `_write_review_artifact` → `loop_review_pipeline`
- `_choose_free_local_port` → `loop_port_forward_helpers`
- `_wait_for_port_ready` → `loop_port_forward_helpers`
- `_start_alertmanager_port_forward` → `loop_alertmanager_port_forward`
- `_stop_alertmanager_port_forward` → `loop_alertmanager_port_forward`

## 4. Coupling Notes

### High Coupling (Must Stay)
- `HealthLoopRunner.execute()` — central orchestrator, many dependencies
- `HealthRunConfig` — config root, imported by many modules
- `run_health_loop()` — entry point, re-exported

### Medium Coupling
- `build_health_assessment()` — standalone but used in `_build_assessments`
- `determine_pair_trigger_reasons()` — standalone but used in `_evaluate_triggers`

### Low Coupling (Extractable)
- Config dataclasses (`HealthTarget`, `ComparisonPeer`, `TriggerPolicy`, `ComparisonIntent`) — pure data
- `HealthAssessmentArtifact` — artifact serialization
- `ComparisonTriggerArtifact` — artifact serialization
- `ComparisonDecision` — artifact serialization

### Test Coverage Map

| Concern | Test Files |
|---------|-----------|
| HealthLoopRunner | `test_health_loop.py`, `test_health_notifications.py`, `test_llm_call_labels.py`, `test_auto_drilldown_failure_metadata_production.py` |
| Assessment building | `test_health_assessment_artifact_readers.py` |
| Trigger determination | `test_health_comparison_policy.py` |
| Config loading | `test_inspect_health_config.py`, `test_health_config_baseline.py` |
| Alertmanager discovery | `test_health_loop_alertmanager_discovery.py` |
| Alertmanager snapshot | `test_health_loop_alertmanager_snapshot_collection.py` |
| vmalert discovery | `test_loop_vmalert_discovery.py`, `test_health_loop_vmalert_discovery.py` |
| vmalert rule state | `test_loop_vmalert_rule_state.py` |
| Notifications | `test_health_notifications.py` |
| UI index | `test_update_ui_index.py` |
| History | `test_health_history_fact_artifact.py` |
| Port forward | `test_port_forward_cleanup.py`, `test_loop_alertmanager_port_forward.py` |
| Scheduler config | `test_scheduler_config_logging.py` |

### Coverage Gaps
- `build_health_assessment()` — no direct unit test (covered indirectly via integration tests)
- `determine_pair_trigger_reasons()` — no direct unit test (covered via `test_health_comparison_policy.py`)
- Assessment artifact serialization — covered via `test_health_assessment_artifact_readers.py`

## 5. Recommended First Extraction Seam

**Option E: Assessment Building**

**New module**: `src/k8s_diag_agent/health/loop_assessment.py`

**Rationale**:
1. `build_health_assessment()` is ~790 lines, the largest standalone function
2. Function is already well-isolated (takes snapshot, target, history as inputs)
3. Produces `HealthAssessmentResult` which is a simple dataclass
4. Already has indirect test coverage via integration tests
5. Extracting it reduces `loop.py` by ~790 lines (~24% reduction)
6. No circular import risk: only depends on `collect`, `models`, `baseline` modules

**What to extract**:
- `build_health_assessment()` function (lines 666-1455)
- `HealthAssessmentResult` dataclass (lines 156-162)
- Helper constants used only by assessment logic

**What stays in `loop.py`**:
- Caller (`HealthLoopRunner._build_assessments`)
- Import compatibility re-export: `from .loop_assessment import build_health_assessment`

**Estimated extracted size**: ~800 lines

## 6. Next Implementation ACT Prompt

```
## ACT: Extract health assessment building to loop_assessment.py

### Objective
Extract `build_health_assessment()` function from `loop.py` into a new module `loop_assessment.py`.

### Constraints
- No behavior changes to `build_health_assessment()`
- No JSON artifact shape changes
- No timestamp semantics changes
- Preserve structured logging messages and metadata keys
- Preserve existing import compatibility via re-exports
- New module must remain below 500 lines (may need to split if larger)
- Do not remove `loop.py` from allowlist

### Steps
1. Create `src/k8s_diag_agent/health/loop_assessment.py`
2. Move `build_health_assessment()` function
3. Move `HealthAssessmentResult` dataclass
4. Add necessary imports
5. Add re-export in `loop.py`: `from .loop_assessment import build_health_assessment, HealthAssessmentResult`
6. Verify tests pass:
   ```
   .venv/bin/python -m pytest tests/test_health_loop.py -q
   .venv/bin/python -m pytest tests/unit/test_health_assessment_artifact_readers.py -q
   ```
7. Verify checker: `python scripts/check_llm_friendly_files.py --quiet`
8. Run ruff: `.venv/bin/python -m ruff check src/k8s_diag_agent/health/loop_assessment.py`
9. Commit with message: "Extract health assessment building to loop_assessment.py"

### Test Coverage
- Direct test: Add `test_build_health_assessment.py` if gap analysis shows need
- Indirect coverage: `test_health_loop.py`, `test_health_assessment_artifact_readers.py`
```

## 7. Verification Output

```bash
# Checker (pre-flight)
python scripts/check_llm_friendly_files.py --quiet
# Expected: 0 failures

# Tests (pre-flight)
.venv/bin/python -m pytest tests/unit/test_health_loop*.py tests/unit/test_loop*.py -q
# Expected: 67 passed

# Git status (pre-flight)
git status --short
# Expected: clean or only unrelated changes
```

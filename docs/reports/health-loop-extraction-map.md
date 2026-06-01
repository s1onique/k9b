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

**Selected: Warning Event Pattern Matching (Sub-Seam)**

**New module**: `src/k8s_diag_agent/health/loop_assessment_warning_events.py`

### Blocker Avoided
The original recommendation proposed extracting `build_health_assessment()` wholesale (~790 lines), which would create a new module exceeding the 500-line threshold. The revised approach extracts a coherent sub-seam within that function instead.

### Rationale
1. **Cohesive block**: Warning event pattern matching (lines 1101-1332, ~231 lines)
2. **Clear boundary**: Nested helper functions operate only on `warning_events` and `signals`
3. **Pure logic**: No dependencies on `HealthTarget`, `BaselinePolicy`, or `image_pull_secret_insight`
4. **Testable**: Pattern matching logic can be unit tested independently
5. **Below threshold**: ~250 lines extraction, well under 500-line limit
6. **Reduces loop.py**: ~231 lines (~7% reduction), building toward eventual full extraction

### Internal Inventory of `build_health_assessment()` (lines 666-1453, ~787 lines)

| Nested Function | Lines | Concern | Extractable |
|-----------------|-------|---------|-------------|
| `add_signal()` | 687-696 | Signal creation | No (uses generator) |
| `record_finding()` | 698-708 | Finding creation | No (uses generator) |
| `_record_issue()` | 710-713 | Combined signal+Finding | No (uses above) |
| `_check_regression()` | 1065-1074 | Regression detection | Marginal |
| `_unused_warning_events()` | 1102-1104 | Event filtering | **Yes** (pattern block) |
| `_capture_namespaces()` | 1107-1115 | Namespace collection | **Yes** (pattern block) |
| `_record_pattern()` | 1122-1177 | Pattern recording | **Yes** (pattern block) |
| `_mark_events()` | 1184-1187 | Event marking | **Yes** (pattern block) |
| `_describe_namespace()` | 1194-1203 | Namespace description | **Yes** (pattern block) |
| `_match_probe_events()` | 1210-1249 | Probe pattern | **Yes** (pattern block) |
| `_match_scheduling_events()` | 1256-1285 | Scheduling pattern | **Yes** (pattern block) |
| `_match_metrics_events()` | 1291-1294 | Metrics pattern | **Yes** (pattern block) |
| `_match_pvc_events()` | 1297-1302 | PVC pattern | **Yes** (pattern block) |
| `_match_ingress_events()` | 1305-1326 | Ingress pattern | **Yes** (pattern block) |
| `_pick_layer()` | 1334-1337 | Layer selection | Marginal (used at end) |

### What to Extract
- `HealthAssessmentResult` dataclass (lines 156-162)
- All warning-event-related nested functions
- Pattern constants if any

### What Stays in `loop.py`
- `build_health_assessment()` function (now calls extracted module)
- Non-pattern helper functions
- Caller (`HealthLoopRunner._build_assessments`)

### Estimated Extracted Size
~250 lines (well below 500-line threshold)

## 6. Next Implementation ACT Prompt

**Title**: `[Open] ACT: Extract build_health_assessment warning-event pattern sub-seam`

### Objective
Extract warning-event pattern matching logic from `build_health_assessment()` into `loop_assessment_warning_events.py`.

### Constraints
- No behavior changes to `build_health_assessment()` pattern matching output
- No JSON artifact shape changes
- No timestamp semantics changes
- Preserve structured logging messages and metadata keys
- New module must remain below 500 lines
- Do not remove `loop.py` from allowlist
- Pattern matching calls return the same results as before extraction

### Pre-flight: Internal Line/Block Inventory
Before code movement, document the exact line boundaries for each pattern-matching function:
- `_unused_warning_events()`: lines 1102-1104
- `_capture_namespaces()`: lines 1107-1115
- `_record_pattern()`: lines 1122-1177
- `_mark_events()`: lines 1184-1187
- `_describe_namespace()`: lines 1194-1203
- `_match_probe_events()`: lines 1210-1249
- `_match_scheduling_events()`: lines 1256-1285
- `_match_metrics_events()`: lines 1291-1294
- `_match_pvc_events()`: lines 1297-1302
- `_match_ingress_events()`: lines 1305-1326

### Steps
1. Create `src/k8s_diag_agent/health/loop_assessment_warning_events.py`
2. Move pattern-matching nested functions
3. Add necessary imports (models, typing, etc.)
4. Export main function: `match_warning_events(signals, generator, warning_events, matched_event_ids)`
5. Update `build_health_assessment()` to call the extracted function
6. Add re-export in `loop.py` if needed for backward compatibility
7. Verify tests pass:
   ```
   .venv/bin/python -m pytest tests/unit/test_health_loop*.py -q
   .venv/bin/python -m pytest tests/unit/test_loop_vmalert_rule_state.py -q
   ```
8. Verify checker: `python scripts/check_llm_friendly_files.py --quiet`
9. Run ruff: `.venv/bin/python -m ruff check src/k8s_diag_agent/health/loop_assessment_warning_events.py`
10. Run mypy: `.venv/bin/python -m mypy src/k8s_diag_agent/health/loop_assessment_warning_events.py`
11. Commit with message: "Extract warning event pattern matching from build_health_assessment"

### Test Coverage
- Direct test: Add `test_loop_assessment_warning_events.py` for pattern matching
- Indirect coverage: `test_health_loop.py` (integration test via HealthLoopRunner)
- Target coverage: pattern matching functions return same results

### Expected Result
- New module: ~250 lines (below 500-line threshold)
- `loop.py` reduction: ~231 lines (~7% reduction)
- Pattern matching behavior unchanged

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

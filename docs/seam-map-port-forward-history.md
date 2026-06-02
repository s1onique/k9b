# Seam Map: Port-Forward Lifecycle and History Loading/Persistence

## Status: Already Extracted

Both port-forward lifecycle and history loading/persistence seams are already extracted. No further extraction is needed.

---

## 1. Port-Forward Lifecycle Seams

### `HealthLoopRunner._start_alertmanager_port_forward`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1506-1526)

**Current shape:**
```python
def _start_alertmanager_port_forward(
    self,
    namespace: str,
    service_name: str,
    context: str | None,
) -> tuple[subprocess.Popen[str], int]:
    """Start kubectl port-forward to an Alertmanager service.

    Delegates to start_alertmanager_port_forward from loop_alertmanager_port_forward module.
    Kept as a wrapper for backward compatibility.
    """
    return start_alertmanager_port_forward(
        namespace=namespace,
        service_name=service_name,
        context=context,
        run_id=self.run_id,
        run_label=self.run_label,
        log_event=self._log_event,
        choose_free_local_port=self._choose_free_local_port,
        wait_for_port_ready=self._wait_for_port_ready,
    )
```

**Wrapper size:** 21 lines

**Extracted implementation:** `src/k8s_diag_agent/health/loop_alertmanager_port_forward.py`
- 248 lines total
- Function: `start_alertmanager_port_forward(...)`
- Returns `(subprocess.Popen[str], int)` - process handle and local port

**Dependencies passed explicitly:**
- `namespace`, `service_name`, `context` - cluster targeting
- `run_id`, `run_label` - for logging
- `log_event` - structured logging callback
- `choose_free_local_port` - port selection callback
- `wait_for_port_ready` - port readiness polling callback

**Runner-state coupling:** None. Only passes `self` fields as function arguments.

---

### `HealthLoopRunner._stop_alertmanager_port_forward`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1528-1544)

**Current shape:**
```python
def _stop_alertmanager_port_forward(
    self,
    process: subprocess.Popen[str],
    local_port: int | None,
) -> None:
    """Stop the port-forward process and log the event.

    Delegates to stop_alertmanager_port_forward from loop_alertmanager_port_forward module.
    Kept as a wrapper for backward compatibility.
    """
    stop_alertmanager_port_forward(
        process=process,
        local_port=local_port,
        run_id=self.run_id,
        run_label=self.run_label,
        log_event=self._log_event,
    )
```

**Wrapper size:** 17 lines

**Extracted implementation:** `src/k8s_diag_agent/health/loop_alertmanager_port_forward.py`
- Function: `stop_alertmanager_port_forward(...)`
- Returns `None`; all exceptions caught internally

**Dependencies passed explicitly:**
- `process`, `local_port` - process handle and port
- `run_id`, `run_label` - for logging
- `log_event` - structured logging callback

**Runner-state coupling:** None. Only passes `self` fields as function arguments.

**Subprocess lifecycle behavior:**
- Graceful termination with 2-second timeout
- Force kill fallback on timeout
- All exceptions caught and logged as warnings
- Never propagates exceptions (final containment)

---

## 2. History Loading/Persistence Seams

### `HealthLoopRunner._load_history`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1388-1389)

**Current shape:**
```python
def _load_history(self, history_path: Path) -> dict[str, HealthHistoryEntry]:
    return load_runner_history(history_path=history_path)
```

**Wrapper size:** 2 lines

**Extracted implementation:** `src/k8s_diag_agent/health/loop_runner_history.py`
- Function: `load_runner_history(history_path: Path) -> dict[str, HealthHistoryEntry]`

**Deep delegation:** `loop_runner_history.py` further delegates to `loop_history.py`:
- Function: `load_history(history_path: Path) -> dict[str, HealthHistoryEntry]`

**Behavior preserved:**
- Returns empty dict if file doesn't exist
- Parses JSON and constructs `HealthHistoryEntry` for each cluster
- Skips non-dict entries gracefully

**Runner-state coupling:** None.

---

### `HealthLoopRunner._persist_history`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1391-1397)

**Current shape:**
```python
def _persist_history(self, history: dict[str, HealthHistoryEntry], directories: dict[str, Path]) -> None:
    return persist_runner_history(
        history=history,
        directories=directories,
        run_id=self.run_id,
        log_event_fn=self._log_event,
    )
```

**Wrapper size:** 7 lines

**Extracted implementation:** `src/k8s_diag_agent/health/loop_runner_history.py`
- Function: `persist_runner_history(history, directories, run_id, log_event_fn)`

**Behavior preserved (success):**
- Writes immutable fact artifacts for each cluster
- Success metadata: `artifact_count`, `history_facts_dir`, `event="history-facts-written"`

**Behavior preserved (failure):**
- Fact artifact write failure is non-fatal
- Failure metadata: `severity_reason`, `event="history-facts-failed"`

**Deep delegation:** `loop_runner_history.py` further delegates to `loop_history.py`:
- `persist_history_fact_artifacts(...)` - fact artifact persistence
- `persist_history(...)` - mutable aggregate history.json

**History JSON shape preserved:**
- Backward compatible with existing readers
- Tests verify `history.json` unchanged after fact artifact writes

**Runner-state coupling:** Only `self.run_id` and `self._log_event` passed as arguments.

---

## Call Sites

### Port-Forward Lifecycle

Used by `loop_alertmanager_snapshot.py` via callbacks:

```python
def _run_alertmanager_snapshot_collection_impl(
    ...
    start_port_forward: Callable[..., tuple[subprocess.Popen[str], int]],
    stop_port_forward: Callable[..., None],
) -> None:
    # Called during snapshot collection
    process, local_port = start_port_forward(namespace, service_name, context)
    try:
        # ... collect snapshot ...
    finally:
        stop_port_forward(process, local_port)
```

**Pattern:** Paired lifecycle with cleanup in `finally` block.

### History Loading/Persistence

Called in `HealthLoopRunner.execute()`:

```python
def execute(self, ...) -> ...:
    ...
    history = self._load_history(directories["history"])
    previous_history = {key: entry for key, entry in history.items()}
    ...
    # Run health checks that use previous_history
    ...
    self._persist_history(history, directories)
```

**Pattern:** Load at start of run, persist at end of run.

---

## Existing Tests

### Port-Forward Tests (`tests/unit/test_port_forward_cleanup.py`)
- `test_normal_cleanup_with_running_process` - normal cleanup behavior
- `test_normal_cleanup_with_already_stopped_process` - handles ended process
- `test_oserror_during_terminate_is_caught` - OSError handling
- `test_subprocess_timeout_error_during_wait_is_caught` - timeout handling
- `test_kill_and_wait_timeout_error_is_caught` - kill fallback
- `test_no_credentials_in_log_output` - no secret leakage
- `test_error_type_is_exception_class_name_not_raw_text` - safe error logging
- `test_cleanup_exceptions_never_propagate` - final containment
- `test_cleanup_behavior_preserved_after_fix` - terminate/kill behavior

### Alertmanager Snapshot Tests (`tests/unit/test_health_loop_alertmanager_snapshot_collection.py`)
- `test_port_forward_success` - full port-forward lifecycle integration
- `test_port_forward_failure_non_fatal` - failures are non-fatal

### History Fact Artifact Tests (`tests/unit/test_health_history_fact_artifact.py`)
- `test_single_cluster_fact_artifact_written` - fact artifact creation
- `test_same_run_id_same_cluster_fails` - immutability enforcement
- `test_multiple_clusters_separate_artifacts` - multi-cluster handling
- `test_shared_artifact_id_across_clusters` - artifact ID sharing
- `test_no_history_writes_nothing` - empty history handling
- `test_history_json_unchanged_after_fact_artifact_write` - JSON compatibility

### Health Loop Tests (`tests/test_health_loop.py`)
- `test_build_health_assessment_reports_history_changes` - history integration

---

## Why Extraction Was Deferred

**Not deferred** - both seams are already fully extracted.

The extraction follows the standard pattern used throughout the health-loop epic:

1. **Thin wrappers in `HealthLoopRunner`**: Pass dependencies explicitly, delegate to helper modules
2. **Helper modules own all logic**: `loop_alertmanager_port_forward.py`, `loop_runner_history.py`, `loop_history.py`
3. **No `Any` at boundaries**: All parameters are typed
4. **No `type: ignore` comments**: Clean typing throughout
5. **Helper modules import neither `loop.py` nor `HealthLoopRunner`**: Clean separation
6. **Comprehensive test coverage**: Both unit and integration tests

**Wrapper sizes confirm minimality:**
- `_start_alertmanager_port_forward`: 21 lines
- `_stop_alertmanager_port_forward`: 17 lines
- `_load_history`: 2 lines
- `_persist_history`: 7 lines

Further extraction would only create redundant indirection without adding value.

---

## Port-Forward Behavior Summary

| Aspect | Behavior |
|--------|----------|
| Port selection | Free local port via `choose_free_local_port()` callback |
| Readiness | 5-second timeout with 0.1s polling via `wait_for_port_ready()` callback |
| Start failure | Logs error, raises `RuntimeError` |
| Stop behavior | Graceful terminate → 2s timeout → force kill |
| Stop failures | Caught and logged as warnings, never propagated |
| Secret leakage | Error logs use only exception class name, not raw text |

---

## History Behavior Summary

| Aspect | Behavior |
|--------|----------|
| Load missing file | Returns empty dict |
| Load corrupt file | Skips non-dict entries |
| Fact artifact write | Immutable, one per cluster per run |
| Fact artifact failure | Non-fatal, logs warning with `severity_reason` |
| Aggregate history | Backward-compatible `history.json` |
| Success logging | `artifact_count`, `history_facts_dir`, `event="history-facts-written"` |
| Failure logging | `severity_reason`, `event="history-facts-failed"` |

---

## Next Recommended ACT

Based on remaining seam sizes in `HealthLoopRunner`, the next candidates are:

1. **`_run_assessments`** (if not yet minimal)
   - Should delegate to `loop_runner_assessments.py`
   - Check wrapper minimality

2. **`_run_comparisons`** (if not yet minimal)
   - Should delegate to `loop_comparison_triggers.py`
   - Check wrapper minimality

3. **LLM-heavy methods** (explicitly deferred in epic scope)
   - `_run_auto_drilldown_analysis`
   - `_run_review_enrichment`
   - These require larger extraction efforts and are explicitly out of scope for this ACT

The assessments and comparisons helpers are likely already thin wrappers similar to the patterns observed here.

---

## Acceptance Criteria for This ACT

- [x] `_start_alertmanager_port_forward` inspected and documented
- [x] `_stop_alertmanager_port_forward` inspected and documented
- [x] `_load_history` inspected and documented
- [x] `_persist_history` inspected and documented
- [x] Wrapper minimality confirmed
- [x] Existing helper modules identified and verified
- [x] Test coverage identified
- [x] No extraction needed (already extracted)
- [x] Next ACT candidates identified

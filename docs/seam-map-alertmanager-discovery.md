# Seam Map: Alertmanager Discovery and Snapshot Collection

## Status: Already Extracted

Both Alertmanager discovery and snapshot collection seams are already extracted.

## Inspected Seams

### 1. `HealthLoopRunner._run_alertmanager_discovery`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1399-1419)

**Current shape:**
```python
def _run_alertmanager_discovery(
    self,
    records: list[HealthSnapshotRecord],
    directories: dict[str, Path],
) -> None:
    def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
        self._log_event(component, severity, message, **metadata)

    self._alertmanager_inventory = _run_alertmanager_discovery_impl(
        records=records,
        directories=directories,
        log_event=log_callback,
        run_id=self.run_id,
    )
```

**Wrapper size:** 21 lines (minimal)

**Extracted implementation:** `src/k8s_diag_agent/health/loop_alertmanager_discovery.py`
- 282 lines
- Function: `run_alertmanager_discovery(records, directories, log_event, run_id)`
- Local alias: `_run_alertmanager_discovery_impl`

**Dependencies:**
- `HealthSnapshotRecord` (from `loop_types.py`)
- `AlertmanagerSourceInventory` (from `external_analysis.alertmanager_discovery`)
- `write_alertmanager_sources` (from `external_analysis.alertmanager_artifact`)
- `derive_cluster_uid` (from `identity.cluster`)

**Store location:** `self._alertmanager_inventory`

---

### 2. `HealthLoopRunner._run_alertmanager_snapshot_collection`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1421-1444)

**Current shape:**
```python
def _run_alertmanager_snapshot_collection(
    self,
    directories: dict[str, Path],
) -> None:
    def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
        self._log_event(component, severity, message, **metadata)

    _run_alertmanager_snapshot_collection_impl(
        inventory=self._alertmanager_inventory,
        run_id=self.run_id,
        run_label=self.run_label,
        log_event=log_callback,
        directories=directories,
        start_port_forward=self._start_alertmanager_port_forward,
        stop_port_forward=self._stop_alertmanager_port_forward,
    )
```

**Wrapper size:** 24 lines (minimal)

**Extracted implementation:** `src/k8s_diag_agent/health/loop_alertmanager_snapshot.py`
- 390 lines
- Function: `run_alertmanager_snapshot_collection(inventory, run_id, run_label, log_event, directories, start_port_forward, stop_port_forward)`
- Local alias: `_run_alertmanager_snapshot_collection_impl`

**Dependencies:**
- `AlertmanagerSourceInventory` (from `external_analysis.alertmanager_discovery`)
- `write_alertmanager_artifacts` (from `external_analysis.alertmanager_artifact`)
- `AlertmanagerSnapshot`, `normalize_alertmanager_payload`, `snapshot_to_compact` (from `external_analysis.alertmanager_snapshot`)

**Input source:** `self._alertmanager_inventory` (set by discovery phase)

**Runner-state coupling:**
- Uses `self._start_alertmanager_port_forward` and `self._stop_alertmanager_port_forward` callbacks
- Uses `self.run_id` and `self.run_label` for artifact naming

---

## Call Sites

Both methods are called in `execute()`:

```python
def execute(self, ...) -> ...:
    ...
    self._run_alertmanager_discovery(records, directories)
    self._run_alertmanager_snapshot_collection(directories)
    ...
```

**Pattern:** Sequential, discovery before snapshot. Snapshot reads the inventory stored by discovery.

---

## Verification

- No `Any` at seam boundaries
- No `type: ignore` comments in wrappers
- Shared types from `loop_types.py` and `external_analysis` modules
- Both wrappers pass `run_id` explicitly
- Both methods are non-fatal (failures logged, run continues)

---

## Why Extraction Was Deferred

**Not deferred** - both seams are already extracted.

The extraction follows the standard pattern used for other runner helpers:
1. Wrapper in `HealthLoopRunner` creates log callback and passes dependencies
2. Helper module contains all the logic
3. Helper imports neither `loop.py` nor `HealthLoopRunner`
4. Tests exist in `tests/unit/test_health_loop_alertmanager_discovery.py` and `tests/unit/test_health_loop_alertmanager_snapshot_collection.py`

---

## Existing Tests

### Discovery Tests (`tests/unit/test_health_loop_alertmanager_discovery.py`)
- `test_method_exists` - verifies wrapper method exists
- `test_writes_sources_inventory` - verifies artifact is written
- `test_no_records_skips_discovery` - verifies no-records behavior
- `test_write_error_is_non_fatal` - verifies write failures are non-fatal
- `test_multiple_records_aggregated` - verifies multi-cluster aggregation

### Snapshot Collection Tests (`tests/unit/test_health_loop_alertmanager_snapshot_collection.py`)
- `test_no_inventory_skips_collection` - verifies no-inventory behavior
- `test_no_eligible_sources_skips_collection` - verifies source selection logic
- `test_direct_fetch_success` - verifies direct endpoint fetch
- `test_port_forward_success` - verifies port-forward lifecycle
- `test_port_forward_failure_non_fatal` - verifies port-forward failures are non-fatal
- `test_http_error_handling` - verifies HTTP error handling
- `test_url_error_handling` - verifies URL/network error handling
- `test_write_error_non_fatal` - verifies write failures are non-fatal

### Port-Forward Tests (`tests/unit/test_port_forward_cleanup.py`)
- Tests for `stop_alertmanager_port_forward` boundary behavior

---

## Next Recommended ACT

Based on the extraction progress, the next candidates for extraction are:

1. **History loading/persistence** (`_load_history`, `_persist_history` at lines 1388-1397)
   - Already delegated to `loop_runner_history.py`
   - Verify wrapper minimality

2. **Port-forward lifecycle** (`_start_alertmanager_port_forward`, `_stop_alertmanager_port_forward`)
   - `loop_alertmanager_port_forward.py` exists (82 lines)
   - Check if runner methods are thin wrappers

3. **Health assessments** (`_run_assessments` at lines ~1500)
   - Delegates to `loop_runner_assessments.py`
   - Check wrapper minimality

4. **Comparison trigger** (`_run_comparisons` at lines ~1520)
   - Delegates to `loop_comparison_triggers.py`
   - Check wrapper minimality

The port-forward lifecycle and history loading are the smallest remaining seams closest to the Alertmanager pattern.

---

## Acceptance Criteria for This ACT

- [x] `_run_alertmanager_discovery` inspected and documented
- [x] `_run_alertmanager_snapshot_collection` inspected and documented
- [x] Call sites identified
- [x] Wrapper minimality confirmed
- [x] Test coverage identified
- [x] Next ACT candidates identified

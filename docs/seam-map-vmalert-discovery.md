# Seam Map: VMAlert Discovery and Rule-State

## Status: Already Extracted

The VMAlert discovery and rule-state seams are already extracted.

## Inspected Seams

### 1. `HealthLoopRunner._run_vmalert_discovery`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1446-1467)

**Current shape:**
```python
def _run_vmalert_discovery(
    self,
    records: list[HealthSnapshotRecord],
    directories: dict[str, Path],
) -> None:
    def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
        self._log_event(component, severity, message, **metadata)

    self._vmalert_inventory = _run_vmalert_discovery_impl(
        records=records,
        directories=directories,
        log_event=log_callback,
        run_id=self.run_id,
    )
```

**Wrapper size:** 22 lines (minimal)

**Extracted implementation:** `src/k8s_diag_agent/health/loop_vmalert_discovery.py`
- 253 lines
- Function: `run_vmalert_discovery(records, directories, log_event, run_id)`

**Dependencies:**
- `HealthSnapshotRecord` (from `loop_types.py`)
- `VmalertSourceInventory` (from `external_analysis.vmalert_discovery`)
- `write_vmalert_sources` (from `external_analysis.vmalert_artifact`)
- `derive_cluster_uid` (from `identity.cluster`)

**Store location:** `self._vmalert_inventory`

---

### 2. `HealthLoopRunner._run_vmalert_rule_state_collection`

**Location:** `src/k8s_diag_agent/health/loop.py` (lines 1469-1484)

**Current shape:**
```python
def _run_vmalert_rule_state_collection(
    self,
    directories: dict[str, Path],
) -> None:
    _run_vmalert_rule_state_collection_impl(
        inventory=self._vmalert_inventory,
        directories=directories,
        run_id=self.run_id,
        cluster_label=self.run_label,
    )
```

**Wrapper size:** 15 lines (minimal)

**Extracted implementation:** `src/k8s_diag_agent/health/loop_vmalert_rule_state.py`
- 164 lines
- Function: `run_vmalert_rule_state_collection(inventory, directories, run_id, cluster_label)`

**Dependencies:**
- `VmalertSourceInventory` (from `external_analysis.vmalert_discovery`)
- `collect_vmalert_rule_state`, `write_vmalert_rule_state` (from `external_analysis.vmalert_rule_state_artifact`)

**Input source:** `self._vmalert_inventory` (set by discovery phase)

---

## Call Sites

Both methods are called in `execute()`:

```python
def execute(self, ...) -> ...:
    ...
    self._run_vmalert_discovery(records, directories)
    self._run_vmalert_rule_state_collection(directories)
    ...
```

**Pattern:** Sequential, discovery before rule-state. Rule-state reads the inventory stored by discovery.

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
4. Tests exist in `tests/unit/test_loop_vmalert_discovery.py` and `tests/unit/test_loop_vmalert_rule_state.py`

---

## Existing Tests

### Discovery Tests (`tests/unit/test_loop_vmalert_discovery.py`)
- `test_run_vmalert_discovery_writes_artifact`
- `test_run_vmalert_discovery_continues_on_discovery_error`
- `test_run_vmalert_discovery_continues_on_verification_error`
- `test_run_vmalert_discovery_marks_unreachable_as_discovered_but_unverified`
- `test_run_vmalert_discovery_writes_empty_artifact`
- `test_run_vmalert_discovery_skips_when_no_records`
- `test_run_vmalert_discovery_continues_on_write_error`
- `test_run_vmalert_discovery_aggregates_multiple_records`
- `test_run_vmalert_discovery_deduplication_merges_provenances`
- `test_run_vmalert_discovery_tags_sources_with_cluster_provenance`

### Rule-State Tests (`tests/unit/test_loop_vmalert_rule_state.py`)
- Coverage for collection, artifact writing, and error handling

---

## Next Recommended ACT

Based on the extraction progress, the next candidates for extraction are:

1. **Alertmanager discovery wrapper** (`_run_alertmanager_discovery` at lines 1399-1419)
   - Similar pattern to VMAlert discovery
   - Already delegated to `loop_alertmanager_discovery.py`

2. **Alertmanager snapshot collection wrapper** (`_run_alertmanager_snapshot_collection` at lines 1421-1444)
   - Delegates to `loop_alertmanager_snapshot.py`
   - Passes port-forward callbacks

3. **History loading/persistence** (`_load_history`, `_persist_history` at lines 1388-1397)
   - Already delegated to `loop_runner_history.py`

The Alertmanager methods are the most analogous to the VMAlert pattern and would be the safest next extraction candidates.

---

## Acceptance Criteria for This ACT

- [x] `_run_vmalert_discovery` inspected and documented
- [x] `_run_vmalert_rule_state_collection` inspected and documented
- [x] Call sites identified
- [x] Wrapper minimality confirmed
- [x] Test coverage identified
- [x] Next ACT candidates identified
# Seam Map: HealthLoopRunner._determine_drilldown_reasons

## Status: REMAPPED (no extraction needed)

## Method Overview

**Location**: `src/k8s_diag_agent/health/loop.py:1346-1360`

**Size**: 15 lines (docstring + delegate call)

**Wrapper shape**:
```python
def _determine_drilldown_reasons(
    self,
    record: HealthSnapshotRecord,
    previous_history: dict[str, HealthHistoryEntry],
) -> tuple[str, ...]:
    """Determine drilldown reasons for a cluster record.

    Delegates to the extracted drilldown helpers module for the core logic.
    """
    return _determine_drilldown_reasons_impl(
        record=record,
        previous_history=previous_history,
        manual_drilldown_contexts=self._manual_drilldown_contexts,
        warning_event_threshold=self.config.trigger_policy.warning_event_threshold,
    )
```

## Call Sites

| Caller | Location | Pattern |
|--------|----------|---------|
| `loop_runner_drilldowns.build_drilldowns_for_records()` | Line 77-82 | Direct import of `loop_drilldown_helpers.determine_drilldown_reasons` |

**Key finding**: `loop_runner_drilldowns.py` does NOT call `HealthLoopRunner._determine_drilldown_reasons`. It imports `determine_drilldown_reasons` from `loop_drilldown_helpers` directly and passes runner-state as parameters.

**Wrapper is self-referencing**: The only reference to `_determine_drilldown_reasons` in source code is the method definition itself and the import alias `_determine_drilldown_reasons_impl`.

## Helper Module State

**File**: `src/k8s_diag_agent/health/loop_drilldown_helpers.py` (107 lines)

**Function**: `determine_drilldown_reasons(...)` at line 21

**Dependencies**:
- `loop_types.HealthSnapshotRecord` ✓ (not runner)
- `loop_history.HealthHistoryEntry, HealthRating` ✓ (not runner)
- `image_pull_secret.BROKEN_IMAGE_PULL_SECRET_REASON` ✓ (not runner)
- `utils.normalize_ref` ✓ (not runner)

**Verification**: `loop_drilldown_helpers.py` imports NEITHER `loop.py` NOR `HealthLoopRunner` ✓

## Runner-State Coupling

The wrapper binds two pieces of runner state:
1. `self._manual_drilldown_contexts` (set[str])
2. `self.config.trigger_policy.warning_event_threshold` (int)

These are passed explicitly to the helper function. The helper is stateless and pure.

## Drilldown Reason Behavior

Preserved from original implementation:
- `manual_request`: explicit context in manual drilldown set
- `health_regression`: previously healthy → now degraded
- `CrashLoopBackOff`: pod count > 0
- `ImagePullBackOff`: pod count > 0
- `warning_event_threshold`: len(warning_events) >= threshold (or > 0 if threshold <= 0)
- `job_failures`: job failures > 0
- `BROKEN_IMAGE_PULL_SECRET_REASON`: from image_pull_secret_insight
- `pattern_reasons`: from assessment

Deduplication via `dict.fromkeys` preserves order of first occurrence.

## Why Extraction Was Not Needed

1. **Helper already extracted**: `loop_drilldown_helpers.py` contains the full implementation (107 lines)
2. **No runner logic in wrapper**: The wrapper is a pure passthrough - 15 lines including docstring
3. **Callers use helper directly**: `loop_runner_drilldowns.py` imports from `loop_drilldown_helpers`, not through the wrapper
4. **No external callers**: No test or external code calls `HealthLoopRunner._determine_drilldown_reasons` directly
5. **Backward compatibility value**: Keeping the wrapper provides a stable interface even though it's not currently called internally

## Test Coverage

Existing drilldown tests in `tests/test_health_loop.py`:
- `test_drilldown_trigger_created_on_crashloop` - CrashLoopBackOff reason
- `test_drilldown_reasons_include_image_pull_secret_supply_chain` - image pull secret reason
- `test_drilldown_collects_pattern_details_for_probe` - pattern_reasons
- `test_drilldown_not_created_when_healthy` - no drilldown when healthy
- `test_drilldown_artifact_serialization` - artifact creation

Tests call through `HealthLoopRunner.execute()` → `_build_drilldowns()` → `build_drilldowns_for_records()` → `determine_drilldown_reasons()`.

## Recommendation

**Do not extract the wrapper**. The wrapper serves as a backward-compatibility shim and is minimal (15 lines). If future callers need to call drilldown reason determination with different state, they can use `loop_drilldown_helpers.determine_drilldown_reasons` directly.

## Next Suggested Seam

The next small seam to inspect is `_record_notification` (already noted as deferred in prior ACT).

**Next ACT acceptance criteria**:
- Inspect `_record_notification` wrapper
- Check if `notifications.write_notification_artifact` handles all artifact writing
- Determine if wrapper is needed for logging/notification record tracking
- Create seam map documenting wrapper state

---

*Seam map created: 2026-02-06*
*Reason: Remap-only - helper already extracted, wrapper is thin passthrough*

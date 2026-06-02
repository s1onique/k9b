# Seam Map: HealthLoopRunner._record_notification

**Status:** Not extracted. Deferred to safer seam.

**Date:** 2026-06-02

## What This Seam Is

`HealthLoopRunner._record_notification` is a 4-line method that:
1. Calls `write_notification_artifact()` to persist a notification artifact
2. Appends `(artifact, artifact_path)` to `self._notification_records`
3. Returns the artifact path

Call sites (3 total):
- Line 1628: `_build_assessments` - degraded health notification
- Line 1780: `_run_external_analysis` - external analysis notification  
- Line 2592: `_trigger_comparisons` - suspicious comparison notification

## Why Extraction Was Not Pursued

### Coupling Analysis

The method has TWO distinct concerns:

1. **Pure concern:** Writing notification artifact to disk
   - Implemented by: `notifications.write_notification_artifact()`
   - Already standalone; no coupling to HealthLoopRunner

2. **Stateful concern:** Appending to `self._notification_records`
   - Mutation of runner's internal state
   - This list feeds into UI index generation (passed to `write_health_ui_index`)
   - Cannot be extracted without passing the list as a parameter

### What Extraction Would Look Like

A hypothetical helper:
```python
# loop_runner_notifications.py
def record_runner_notification(
    directory: Path,
    artifact: NotificationArtifact,
) -> Path:
    return write_notification_artifact(directory, artifact)
```

The wrapper would remain:
```python
def _record_notification(self, directory: Path, artifact: NotificationArtifact) -> Path:
    artifact_path = record_runner_notification(directory, artifact)
    self._notification_records.append((artifact, artifact_path))
    return artifact_path
```

### Why It's Not Worthwhile

1. **Marginal value:** The helper is a 2-line wrapper around an existing standalone function
2. **State mutation stays:** `self._notification_records.append()` MUST remain in the wrapper
3. **No new testability:** `write_notification_artifact` is already tested (826-line test suite)
4. **Above-threshold module:** New module would be ~30 lines - below 500-line threshold but still trivial

### What Coupling Blocked Extraction

- `self._notification_records` - runner state that tracks all notifications for UI index
- This list is initialized at runner creation (line 1314), cleared per-run (line 1358), and passed to `write_health_ui_index` (line 1449)
- Cannot move mutation to helper without passing the list, which defeats the extraction purpose

## Next Safer Seam: `_build_assessments`

**Recommendation:** Pursue `_build_assessments` (lines 1558-1648) as the next ACT.

### Why `_build_assessments` is Better

1. **Rich logic:** 90 lines of substantial behavior (vs 4-line `_record_notification`)
2. **Cleaner dependencies:** Only uses `self.config` for threshold, `self.run_id`, `self.run_label`
3. **Already parameterized:** Receives `notification_dir` as argument
4. **Notification recording is natural:** `_record_notification` calls fit contextually inside
5. **Artifact-heavy:** Assessment artifacts, validators, history entries - good extraction target

### Current `_build_assessments` Signature

```python
def _build_assessments(
    self,
    records: list[HealthSnapshotRecord],
    history: dict[str, HealthHistoryEntry],
    assessment_dir: Path,
    root_dir: Path,
    notification_dir: Path,
) -> list[HealthAssessmentArtifact]:
```

### Extraction Potential

A helper `build_assessments_for_records(...)` could accept:
- `records`, `history`, `assessment_dir`, `notification_dir`
- `run_id`, `run_label` (strings, no self needed)
- `warning_event_threshold` (from config)
- Optional `log_event_fn` for observability

Notification recording would naturally be part of the helper, preserving ordering and behavior.

## Summary

| Aspect | _record_notification | _build_assessments |
|--------|---------------------|-------------------|
| Lines | 4 | 90 |
| Coupling | Runner state (records list) | Config only |
| Extraction value | Marginal | High |
| Notification handling | Isolated | Natural fit |
| Risk | Low (trivial) | Medium (more logic) |

**Decision:** Remap to `_build_assessments` ACT. Document this seam as reference for future notification extraction if more notification handling logic accumulates in the runner.
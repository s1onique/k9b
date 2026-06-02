# Seam Map: Health Loop Review Artifact

**Status**: Already extracted (no further action needed)  
**Inspected**: `_write_review_artifact`  
**Epic**: Health loop extraction

---

## Current State

The review artifact seam is **already extracted**.

### Wrapper: `HealthLoopRunner._write_review_artifact`

**Location**: `src/k8s_diag_agent/health/loop.py` lines 1282-1344

**Size**: 62 lines (thin wrapper)

**Shape**:

```python
def _write_review_artifact(
    self,
    assessments: list[HealthAssessmentArtifact],
    drilldowns: list[DrilldownArtifact],
    directories: dict[str, Path],
) -> tuple[Path | None, tuple[HealthProposal, ...]]:
    try:
        review_path, proposals = _write_review_and_proposals_impl(
            run_id=self.run_id,
            run_label=self.run_label,
            assessments=assessments,
            drilldowns=drilldowns,
            directories=directories,
            warning_threshold=self.config.trigger_policy.warning_event_threshold,
            baseline_policy=self.config.baseline_policy,
        )
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        self._log_event(...)
        return None, ()

    if review_path is None:
        return None, ()

    self._log_event("review-assessment", "INFO", "Health review written", ...)
    for proposal in proposals:
        self._log_event("proposal-promotion", "INFO", "Health proposal written", ...)
    return review_path, proposals
```

### Extracted Helper: `loop_review_pipeline.write_review_and_proposals`

**Location**: `src/k8s_diag_agent/health/loop_review_pipeline.py`

**Size**: 139 lines

**Responsibilities**:

1. Build health review from assessments and drilldowns via `build_health_review`
2. Write review artifact to `{run_id}-review.json`
3. Collect trigger details from `triggers/` directory
4. Generate proposals via `generate_proposals_from_review`
5. Write proposal artifacts to `{proposal_id}.json`
6. Validate proposals with `HealthProposalValidator`
7. Create notifications for each proposal

**Imports**: Does NOT import `loop.py` or `HealthLoopRunner`

---

## Call Sites

Single call site at `loop.py` line 473:

```python
review_path, proposals = self._write_review_artifact(assessments, drilldowns, directories)
enrichment_artifact = self._run_review_enrichment(review_path, directories)
```

---

## Dependencies Passed Through

| Dependency | Source | Purpose |
|------------|--------|---------|
| `run_id` | `self.run_id` | Artifact naming, logging |
| `run_label` | `self.run_label` | Logging |
| `warning_threshold` | `self.config.trigger_policy.warning_event_threshold` | Review building |
| `baseline_policy` | `self.config.baseline_policy` | Proposal generation |
| `_log_event` | `self._log_event` | Structured logging |
| `assessments` | method param | Review input |
| `drilldowns` | method param | Review input |
| `directories` | method param | Artifact output paths |

---

## Runner State Coupling

Minimal coupling:

- Passes `run_id` and `run_label` for logging metadata
- Uses `self._log_event` callback for structured logging
- No state mutation beyond logging

---

## Artifact Behavior

### Review Artifact

- **Path**: `{run_id}-review.json` in `directories["reviews"]`
- **Payload**: Dict from `build_health_review(...).to_dict()`
- **Non-fatal**: Returns `None` on build failure

### Proposal Artifacts

- **Path**: `{proposal_id}.json` in `directories["proposals"]`
- **Payload**: Dict from `HealthProposal.to_dict()` with validator check
- **Non-fatal**: Proposal generation failure doesn't fail review write

### Notification Artifacts

- **Path**: `...notifications.../{notification_id}.json`
- **Created**: For each proposal via `build_proposal_created_notification`

---

## Logging Behavior

| Event | Severity | When |
|-------|----------|------|
| `review-failed` | ERROR | Exception during review/proposal pipeline |
| `review-created` | INFO | Successful review write (with path, counts) |
| `proposal-generated` | INFO | Per proposal (with proposal_id, path) |

---

## Validator Behavior

`HealthProposalValidator.validate(proposal.to_dict())` called for each proposal before writing.

---

## LLM-Heavy Coupling

**None**. The seam does not touch:
- `_run_auto_drilldown_analysis`
- `_run_review_enrichment`
- Any LLM provider calls

Review enrichment happens **after** this seam returns.

---

## Test Coverage

Relevant test files:

- `tests/test_health_loop.py` - Full health loop tests including review enrichment
- `tests/test_alertmanager_durable_learning.py` - Proposal generation tests
- `tests/unit/test_review_artifact_identity.py` - Review artifact ID tests
- `tests/unit/test_proposal_artifact_identity.py` - Proposal artifact ID tests
- `tests/unit/test_health_validators.py` - Proposal validator tests
- `tests/unit/test_health_notifications.py` - Notification path tests

---

## Why Extraction Was Deferred

**Not applicable** - extraction is already complete.

The `_write_review_artifact` method is a minimal wrapper that:
1. Delegates to extracted `loop_review_pipeline.write_review_and_proposals`
2. Adds structured logging specific to runner context
3. Translates runner config to pipeline parameters

Further extraction would add redundant indirection without reducing coupling.

---

## Next Recommended ACT

**Candidate seam**: `HealthLoopRunner._determine_drilldown_reasons`

**Rationale**:

- Lines 1346-1365 (~20 lines)
- Delegates to `_determine_drilldown_reasons_impl` from `loop_drilldown_helpers`
- Wrapper could be extracted following the same pattern

**Alternative candidate**: `HealthLoopRunner._record_notification`

- Simple delegation to `write_notification_artifact`
- Low coupling, isolated behavior

---

## Acceptance Criteria Status

This seam is **already accepted**:

- [x] Review artifact helper extracted to `loop_review_pipeline.py`
- [x] Wrapper delegates with explicit dependencies
- [x] Helper imports neither `loop.py` nor `HealthLoopRunner`
- [x] Behavior preserved exactly
- [x] Logging preserved
- [x] Validator behavior preserved
- [x] Non-fatal failure behavior preserved
- [x] Tests pass (verified in prior ACT)

# Worklist Ranking Rationale

**Epic**: BETA-G3 Worklist Ranking Rationale Transparency  
**Status**: Implemented  
**Date**: 2026-05-13

## Goal

Make operator worklist ranking transparent by surfacing why each worklist item has its current rank, so operators can understand and trust the ordering rather than treating it as an opaque sequence.

## Contract

Every ranked worklist item exposes a `rankingReason` field that provides a concise, operator-readable explanation for why the item has its current rank in the worklist.

### Field Location

`OperatorWorklistItemPayload.rankingReason: str | None`

### Derivation

The `rankingReason` is derived-only (stateless) from available item signals and state. No new persistence layer is introduced; the rationale is computed at projection time from existing worklist item properties.

## Allowed Basis for Ranking Rationale

The ranking rationale may be derived from the following signals:

### 1. Urgency / Primary Triage

**Signal**: `is_primary_triage=True` on deterministic items  
**Rationale**: `"Primary triage for current degraded workload"` or `"Primary triage for current degraded workload (high urgency)"`  
**When**: Item has `sourceType=deterministic` and `is_primary_triage=True`

### 2. Expected Information Gain

**Signal**: High priority label with executable command  
**Rationale**: `"Executable now; likely to confirm the leading hypothesis"`  
**When**: `priorityLabel in ("primary", "critical")` and `command` is not None

### 3. Approval/Execution Readiness

**Signal**: Queue item with approval/execution state  
**Rationale variants**:
- `"Pending operator approval before execution"` (itemState=approval-needed)
- `"Approved and ready for execution"` (itemState=approved)
- `"Queued for automated execution"` (itemState=queued)
- `"Planner-selected check; executable now"` (generic planner item)

### 4. Drift Category Severity

**Signal**: Workstream is "drift" (cross-cluster context)  
**Rationale**: `"Fleet-level drift affects comparable clusters"`  
**When**: `workstream="drift"`

### 5. Executed/Reviewed State

**Signal**: Item is completed  
**Rationale**: `"Already executed; retained for result review"`  
**When**: `itemState in ("executed", "reviewed")` or `executionState in ("executed-success", "executed-failed", "timed-out")`

### 6. Advisory Diagnostics

**Signal**: Deterministic items without executable command  
**Rationale**: `"Advisory check; {urgency} urgency for evidence collection"` or `"Advisory check; method-based diagnostics"`  
**When**: `sourceType=deterministic` and `command=None`

### 7. Fallback

When no ranking basis is determinable, `rankingReason` is `None`.

## Invariants

1. **Every ranked item exposes a rankingReason**: Even if None when indeterminate
2. **Rationale aligns with actual ordering and state**: A rationale claiming "executed" must correspond to an executed state
3. **Rationale is concise**: Under 80 characters
4. **Advisory items are not described as immediately executable**: Null command → no "executable now" claim
5. **Reviewed/executed items are not incorrectly explained as pending**: Completed items should not claim "pending", "queued", or "ready for execution"

## Rationale Text Examples

| Scenario | Rationale |
|----------|-----------|
| Primary triage, high urgency | `"Primary triage for current degraded workload (high urgency)"` |
| Primary triage, unknown urgency | `"Primary triage for current degraded workload"` |
| Executable, high priority | `"Executable now; likely to confirm the leading hypothesis"` |
| Approval needed | `"Pending operator approval before execution"` |
| Drift workstream | `"Fleet-level drift affects comparable clusters"` |
| Executed item | `"Already executed; retained for result review"` |
| Secondary triage deterministic | `"Advisory check; medium urgency for evidence collection"` |
| Advisory no urgency | `"Advisory check; method-based diagnostics"` |

## Implementation

The `_derive_worklist_ranking_reason()` function in `k8s_diag_agent/ui/api_incident_report.py` implements the derivation logic. It is called at worklist projection time for each deterministic item and queue item.

## Testing

Regression tests verify:
- `tests/unit/test_api_incident_report.py::WorklistRankingRationaleTests`: Integration tests for worklist items
- `tests/unit/test_api_incident_report.py::WorklistRankingRationaleDerivationTests`: Unit tests for the derivation function

### Test Coverage

1. `test_all_ranked_items_have_ranking_reason`: Every item has the field
2. `test_primary_triage_deterministic_items_have_triage_rationale`: Primary triage items have triage rationale
3. `test_executed_items_have_executed_rationale`: Executed items mention execution
4. `test_approval_needed_items_have_approval_rationale`: Approval items mention approval
5. `test_executable_queue_items_have_executable_rationale`: Queue items with command have appropriate rationale
6. `test_deterministic_advisory_items_not_described_as_executable`: Advisory items don't claim executability
7. `test_reviewed_items_not_described_as_pending`: Completed items don't claim pending
8. `test_ranking_rationale_is_concise`: Rationale under 80 characters
9. `test_drift_workstream_items_have_fleet_rationale`: Drift items mention fleet

## Interpretation Guide

### For Operators

- **Primary triage items** are ranked first because they represent the most urgent evidence collection for the current degraded workload
- **Executable items** are ranked based on their expected information gain and readiness for execution
- **Drift items** indicate fleet-level issues that affect comparable clusters, warranting cross-cluster investigation
- **Executed items** are retained for result review; their ranking rationale indicates they are completed, not pending

### For Developers

- The `rankingReason` is a projection field, not a new truth source
- Changes to ranking logic should be reflected in the derivation function
- New ranking basis should follow the allowed signal taxonomy
- Test coverage should be updated when adding new rationale patterns

## Related Documentation

- `docs/data-model.md`: Operator worklist data model and contract invariants
- `src/k8s_diag_agent/ui/api_incident_report.py`: Worklist payload builders with ranking rationale derivation
- `src/k8s_diag_agent/ui/api_payloads.py`: `OperatorWorklistItemPayload` contract definition
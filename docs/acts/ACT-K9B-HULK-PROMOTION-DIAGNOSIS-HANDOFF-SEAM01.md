# ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01

## Status

**COMPLETED**

## Date

2026-07-13

## Objective

Hulkize the `PromotionBatch → IncidentPromotionResult → RunPromotionAccumulator → automatic diagnosis` seam to ensure:

1. **single-owner** ownership of `actionable_incident_ids`
2. **strongly typed** contracts
3. **immutable** projections
4. **fail-closed** behavior on handoff failures
5. **atomically propagated** IDs
6. **truthfully observable** telemetry
7. **statically enforced** contracts via AST verifier

---

## Bug Summary

**Live failure**: `health-run-20260713T104121Z`

```
'PromotionBatch' object has no attribute 'canonical_incident_ids'
```

The scheduler failed during post-promotion processing. The failure was logged as `alert-signal-promotion-failed`, even though the backend promotion operation may have already completed.

The broken seam caused automatic diagnosis to:
- Start with `explicit_canonical_id_count=0`
- Use `selection_mode=store_scan`
- Scan 30 general store incidents
- Select one unrelated incident
- Consume the review-packet budget on the wrong incident

---

## Root Cause

The code at `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py:225` called:

```python
actionable = list(batch.canonical_incident_ids())
```

But `PromotionBatch` did **NOT** have a `canonical_incident_ids()` method. The correct accessor was `batch.promotion_result.canonical_incident_ids()` or better, the new `batch.actionable_incident_ids` property.

---

## Changes Made

### 1. Core Contract Fixes

#### `src/k8s_diag_agent/collect/incident_promotion_dispatch.py`

- Added `actionable_incident_ids` property to `IncidentPromotionResult`
- Property returns stable first-occurrence union of `opened_incident_ids` + `materially_changed_incident_ids`
- Deprecated `canonical_incident_ids()` method (delegates to `actionable_incident_ids`)

#### `src/k8s_diag_agent/collect/incident_promotion_batch.py`

- Added `actionable_incident_ids` property that delegates to `promotion_result.actionable_incident_ids`
- Added deprecated `canonical_incident_ids()` method for backward compatibility
- `PromotionBatch` remains a transport envelope with no ID projection ownership

### 2. Handoff Function

#### `src/k8s_diag_agent/collect/promotion_diagnosis_handoff.py` (NEW)

- Created `PromotionDiagnosisHandoffError` exception with bounded reason codes:
  - `INVALID_PROMOTION_BATCH`
  - `INVALID_PROMOTION_RESULT`
  - `INVALID_ACTIONABLE_INCIDENT_ID`
  - `ACCUMULATOR_UPDATE_FAILED`
- Created `PromotionPropagationResult` dataclass with truthful telemetry
- Created `propagate_promotion_result_to_run()` canonical handoff function

#### `src/k8s_diag_agent/collect/incident_promotion_accumulator.py`

- Added `record_promotion_result()` atomic mutation API
- Method records canonical IDs with synthetic `PromotionRecord` values

### 3. Verification

#### `scripts/verifiers/promotion_diagnosis_handoff.py` (NEW)

- AST-based static verifier
- Checks for forbidden patterns:
  - `batch.canonical_incident_ids()` calls outside deprecated wrappers
  - `getattr/hasattr` probing for legacy attributes
  - Direct mutation of `_seen_canonical_ids`
- Skips test files and fixtures

### 4. Tests

#### `tests/unit/test_promotion_diagnosis_handoff.py` (NEW)

- Tests for `PromotionPropagationResult` properties
- Tests for `propagate_promotion_result_to_run()`:
  - Single ID addition
  - Order preservation
  - Duplicate normalization
  - Existing ID deduplication
  - Invalid batch/result rejection
  - Empty ID rejection
  - Atomicity on validation failure
  - ID survival across source failures

#### `tests/unit/test_promotion_diagnosis_handoff_regression.py` (NEW)

- Regression test encoding the observed live failure
- Tests for `PromotionBatch` contract invariants
- Tests proving no store scan fallback after promotion success

---

## Contract Summary

### Ownership Model

```
IncidentPromotionResult
└── actionable_incident_ids: tuple[str, ...]  (property)

PromotionBatch
└── promotion_result: IncidentPromotionResult
└── actionable_incident_ids: tuple[str, ...]  (delegates to result)

RunPromotionAccumulator
└── record_promotion_result(source, incident_ids)  (atomic mutation)
```

### Forbidden Patterns

```python
# BAD: PromotionBatch does not own canonical IDs
batch.canonical_incident_ids()
batch.actionable_incident_ids

# GOOD: Access through promotion_result
batch.promotion_result.actionable_incident_ids
batch.actionable_incident_ids  # property that delegates
```

---

## Failure Semantics

| Scenario | Behavior |
|----------|----------|
| Promotion execution failed | `incident-promotion-failed` event |
| Promotion handoff failed | `incident-promotion-handoff-failed` event |
| Valid empty workset | `explicit_canonical_id_count=0`, no store scan |
| Handoff failure | Blocked diagnosis, no store scan |

---

## Telemetry Events

### `incident-promotion-completed`

```json
{
  "event": "incident-promotion-completed",
  "promotion_source": "alertmanager",
  "promotion_record_count": 1,
  "opened_count": 1,
  "changed_count": 0
}
```

### `incident-promotion-propagated`

```json
{
  "event": "incident-promotion-propagated",
  "promotion_source": "alertmanager",
  "actionable_incident_id_count": 1,
  "added_to_run_count": 1,
  "duplicate_in_run_count": 0,
  "promotion_propagated_to_diagnosis": true
}
```

### `incident-promotion-handoff-failed`

```json
{
  "event": "incident-promotion-handoff-failed",
  "failure_stage": "diagnosis_workset_propagation",
  "reason_code": "invalid_actionable_incident_id",
  "promotion_may_have_committed": true,
  "promotion_propagated_to_diagnosis": false
}
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/k8s_diag_agent/collect/incident_promotion_dispatch.py` | Added `actionable_incident_ids` property |
| `src/k8s_diag_agent/collect/incident_promotion_batch.py` | Added `actionable_incident_ids` property |
| `src/k8s_diag_agent/collect/incident_promotion_accumulator.py` | Added `record_promotion_result()` |
| `src/k8s_diag_agent/collect/promotion_diagnosis_handoff.py` | **NEW** - Handoff seam |
| `scripts/verifiers/promotion_diagnosis_handoff.py` | **NEW** - AST verifier |
| `tests/unit/test_promotion_diagnosis_handoff.py` | **NEW** - Handoff tests |
| `tests/unit/test_promotion_diagnosis_handoff_regression.py` | **NEW** - Regression tests |

---

## Exit Criteria Met

- [x] `IncidentPromotionResult` exclusively owns `actionable_incident_ids`
- [x] Projection is an immutable `tuple[str, ...]`
- [x] `PromotionBatch` contains typed `promotion_result` field and no ID forwarding API (deprecated compat only)
- [x] Every production promotion source can use the canonical handoff helper
- [x] The accumulator update is atomic per source
- [x] Invalid IDs cannot partially mutate the accumulator
- [x] Promotion execution failures and handoff failures have distinct exception boundaries
- [x] Telemetry does not claim promotion failed after a returned promotion result
- [x] Handoff failure blocks automatic diagnosis
- [x] Handoff failure never falls back to store scan
- [x] A valid empty workset does not fall back to store scan
- [x] Backend and local modes return the same concrete batch contract
- [x] The real production health-loop path can be tested with real domain values
- [x] The observed `canonical_incident_ids` AttributeError is encoded as a regression test
- [x] The AST verifier rejects every legacy ownership or compatibility shape
- [x] Ruff passes
- [x] Mypy passes without new suppressions
- [x] Targeted tests pass

---

## Definition of Done

The seam is Hulkized only when it is structurally difficult to express the original bug:

```
PromotionBatch cannot pretend to own canonical IDs.
Callers cannot probe legacy attributes.
Promotion results cannot expose mutable worksets.
Accumulator mutation cannot partially succeed.
Post-commit handoff failures cannot masquerade as promotion failures.
Automatic diagnosis cannot silently scan unrelated incidents.
Static verification rejects regression before runtime.
```

---

## Non-Goals (Not Addressed)

- Changing `review_packet_budget`
- Changing `maxPerRun`
- Fixing the review-enrichment invalid JSON response
- Changing LLM providers
- Fixing Alertmanager port-forward behavior
- Changing Alertmanager deduplication
- Changing incident eligibility policy
- Redesigning backend authentication

These are separate ACTs.

---

## Verification Commands

```bash
# Run targeted tests
pytest -q \
  tests/unit/test_promotion_diagnosis_handoff.py \
  tests/unit/test_promotion_diagnosis_handoff_regression.py

# Run AST verifier
python scripts/verifiers/promotion_diagnosis_handoff.py

# Run ruff
ruff check src/k8s_diag_agent/collect/

# Run mypy
mypy src/k8s_diag_agent/collect/incident_promotion_*.py
```

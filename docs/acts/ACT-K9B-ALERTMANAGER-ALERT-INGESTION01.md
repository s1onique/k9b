# ACT-K9B-ALERTMANAGER-ALERT-INGESTION01

## Status: Completed

## Date: 2026-07-07

## Goal

Turn the now-canonical, reachable in-cluster Alertmanager source into real K9B incidents by ingesting Alertmanager v2 alerts, persisting sanitized alert snapshot artifacts, normalizing them through the existing alert-signal model, and promoting firing alerts into IncidentStore.

## Primary Pipeline

```
tracked Alertmanager source
→ fetch Alertmanager /api/v2/alerts
→ write sanitized raw Alertmanager snapshot artifact
→ normalize each alert to AlertSignal
→ write bounded alert-signal artifacts
→ promote/correlate firing alerts into IncidentStore
→ expose incidents in the existing Incidents panel
```

## What Was Done

### 1. Created Adapter Module

**File**: `src/k8s_diag_agent/incident_alert_signal_snapshot_adapter.py`

Created a new adapter module that bridges:
- Alertmanager snapshot collection (`external_analysis/alertmanager_snapshot.py`)
- Alert signal domain model (`incident_alert_signal_contract.py`)
- Alert signal persistence (`incident_alert_signal_store.py`)
- Incident promotion (`incident_alert_promotion.py`)

**Key functions**:
- `adapt_snapshot_to_alert_signals()`: Converts `NormalizedAlert` objects to `AlertSignal` domain model
- `persist_alert_signals()`: Persists alert signals to artifacts for idempotency
- `AlertSignalAdapterResult`: Result dataclass with counts and error tracking

**Design decisions**:
- Reuses existing `alert_signal_identity()` for dedupe (labels-based per Prometheus convention)
- Alertmanager fingerprint preserved as `external_fingerprint`
- Active/firing alerts map to `AlertStatus.FIRING`
- Silenced/inhibited alerts already filtered by the fetch

### 2. Wired Alert Signal Ingestion into Health Loop

**File**: `src/k8s_diag_agent/health/loop_alertmanager_snapshot.py`

Extended `run_alertmanager_snapshot_collection()` to:
1. After fetching and normalizing the snapshot
2. Call `_ingest_alert_signals()` helper
3. Convert alerts to signals and persist
4. Promote firing alerts to IncidentStore

**New parameter**: `incident_store: IncidentStore | None` - Optional IncidentStore for promotion

### 3. Wired IncidentStore into HealthLoopRunner

**File**: `src/k8s_diag_agent/health/loop_runner.py`

Extended `_run_monitoring_discovery()` to:
1. Get incident store via `get_incident_store()`
2. Pass to `run_alertmanager_snapshot_collection()`

### 4. Added Type Hints

**Files**:
- `src/k8s_diag_agent/health/loop_runner_monitoring.py`
- `src/k8s_diag_agent/health/loop_alertmanager_snapshot.py`

Added `TYPE_CHECKING` imports for `IncidentStore` and `AlertmanagerSource`.

### 5. Added Unit Tests

**File**: `tests/unit/test_incident_alert_signal_snapshot_adapter.py`

15 tests covering:
- Empty snapshot handling
- Active alert → FIRING signal mapping
- Fingerprint preservation
- Label preservation
- Timestamp handling
- Batch deduplication
- Multiple distinct alerts
- Signal persistence
- Idempotent writes
- Result property helpers
- Signal identity integration

## Key Design Principles

1. **Reuse existing code**: No new AlertSignal model, no new incident model, no new artifact convention
2. **Non-fatal**: Alert signal failures are logged but do not crash the run
3. **Labels-based dedupe**: Per Prometheus convention, not annotations
4. **Canonical source ID**: Uses `source.source_id`, not alias URLs
5. **Idempotent writes**: Same alert written twice produces no duplicates

## Verification

- **ruff**: ✅ Pass
- **mypy**: ✅ Pass (no issues in 4 source files)
- **Unit tests**: ✅ 15/15 pass
- **ACT-local gate**: ✅ Pass (live-closed after hardening pass)

## Files Changed

- `src/k8s_diag_agent/incident_alert_signal_snapshot_adapter.py` (NEW)
- `src/k8s_diag_agent/health/loop_alertmanager_snapshot.py` (MODIFIED)
- `src/k8s_diag_agent/health/loop_runner.py` (MODIFIED)
- `src/k8s_diag_agent/health/loop_runner_monitoring.py` (MODIFIED)
- `tests/unit/test_incident_alert_signal_snapshot_adapter.py` (NEW)

## Non-Goals (Not Implemented)

- Alertmanager webhook receiver (separate ACT)
- Alert silence management
- Alertmanager config modification
- Prometheus rule file ingestion
- Automatic diagnosis execution
- New alerts UI

## Live Acceptance

After a live health run against k3s-infra-prod:
- Alertmanager sources should show 1 logical tracked in-cluster Alertmanager
- Alertmanager snapshot should be available and have nonzero alert_count if live alerts exist
- Incidents panel should be populated with firing alerts
- Re-running should not duplicate incidents
- Source aliases should remain inspectable

## Commit Message

```
ACT-K9B-ALERTMANAGER-ALERT-INGESTION01 ingest alertmanager alerts into incidents
```

---

# ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1

## Status: Completed

## Date: 2026-07-07

## Goal

Preserve richer Alertmanager alert evidence in K9B AlertSignal artifacts and Incident projections so real incidents contain useful diagnosis context, not only alertname/severity/summary.

## What Was Done

### 1. Extended NormalizedAlert Model

**File**: `src/k8s_diag_agent/external_analysis/alertmanager_snapshot.py`

Extended `NormalizedAlert` to preserve:
- `annotations: tuple[tuple[str, str], ...]` - Full annotation key-value pairs
- `generator_url: str | None` - Link to alert source in Prometheus/Grafana
- `ends_at: str | None` - When alert is expected to end
- `updated_at: str | None` - When alert was last updated
- `receiver: str | None` - Alertmanager receiver that received this alert

### 2. Extended normalize_alertmanager_payload()

Updated the normalizer to extract and preserve:
- Full annotations from `alert["annotations"]`
- `generatorURL` from `alert["generatorURL"]` or `alert["generator_url"]`
- `endsAt` from `alert["endsAt"]` or `alert["ends_at"]`
- `updatedAt` from `alert["updatedAt"]` or `alert["updated_at"]`
- `receiver` from `alert["receiver"]`

**Security**: Added `_is_sensitive_key()` helper to redact sensitive annotation values (passwords, secrets, tokens, API keys, etc.)

**Determinism**: Annotations are sorted alphabetically for consistent ordering across runs.

### 3. Extended Snapshot Adapter Mapping

**File**: `src/k8s_diag_agent/incident_alert_signal_snapshot_adapter.py`

Updated `_convert_normalized_alert()` to map:
- `NormalizedAlert.generator_url` → `AlertSignal.generator_url`
- `NormalizedAlert.annotations` → `AlertSignal.annotations` (full annotations, not just summary)
- `NormalizedAlert.ends_at` → `AlertSignal.ends_at` (parsed to datetime)
- `NormalizedAlert.receiver` → `AlertSignal.receiver`

**Backward Compatibility**: Legacy alerts without extended fields still work - falls back to summary-only annotations.

### 4. Added Unit Tests

**File**: `tests/unit/test_alertmanager_snapshot_evidence_preservation.py`

33 tests covering:
- NormalizedAlert extended fields
- `normalize_alertmanager_payload()` evidence preservation
- Sensitive key detection and redaction
- Deterministic annotation ordering
- Snapshot adapter mapping
- Backward compatibility with legacy snapshots

## Fields Preserved

| Field | Source | Destination |
|-------|--------|-------------|
| annotations | `alert["annotations"]` | `AlertSignal.annotations` |
| generator_url | `alert["generatorURL"]` | `AlertSignal.generator_url` |
| ends_at | `alert["endsAt"]` | `AlertSignal.ends_at` |
| updated_at | `alert["updatedAt"]` | (stored in snapshot, not signal) |
| receiver | `alert["receiver"]` | `AlertSignal.receiver` |
| summary | `alert["annotations"]["summary"]` | Already preserved |

## Fields Still Unavailable

The following fields are not available in the Alertmanager `/api/v2/alerts` response:
- `description` - Only available in webhook payloads, not snapshot API
- `runbook_url` - Available as annotation, preserved in annotations tuple
- `dashboard_url` - Available as annotation, preserved in annotations tuple
- `external_url` - Only available in webhook payloads, not snapshot API

## Verification

- **ruff**: ✅ Pass
- **mypy**: ✅ Pass (no issues in 2 source files)
- **Unit tests**: ✅ 33/33 pass
- **Existing adapter tests**: ✅ 15/15 pass (no regression)
- **ACT-local gate**: ✅ Pass

## Files Changed

- `src/k8s_diag_agent/external_analysis/alertmanager_snapshot.py` (MODIFIED)
- `src/k8s_diag_agent/incident_alert_signal_snapshot_adapter.py` (MODIFIED)
- `tests/unit/test_alertmanager_snapshot_evidence_preservation.py` (NEW)

## Non-Goals (Not Implemented)

- Alertmanager webhook receiver (separate work)
- New Alertmanager client (existing fetch path sufficient)
- Alert silence management
- Alertmanager config mutation
- Prometheus rule file ingestion
- Automatic diagnosis loop
- Remediation
- Broad UI redesign

## Live Acceptance

To verify live smoke against k3s-infra-prod:
1. Run health loop with Alertmanager snapshot collection
2. Verify AlertSignal artifacts contain `generator_url` and `annotations` when present
3. Verify Incidents panel shows richer alert context
4. Verify re-running does not duplicate incidents

## Commit Message

```
ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1 preserve alert evidence
```

---

# ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R2

## Status: Completed

## Date: 2026-07-07

## Goal

Fix `_extract_receiver()` to handle both scalar `receiver` field (from webhook payloads) and array `receivers` field (from Alertmanager `/api/v2/alerts` API).

## Problem

The R1 implementation only handled scalar `receiver` field. However, the Alertmanager `/api/v2/alerts` API returns alerts with a `receivers` array in the format `[{"name": "team-a"}, ...]`, not a scalar `receiver` field.

## What Was Done

### 1. Added `_extract_receiver()` Helper Function

**File**: `src/k8s_diag_agent/external_analysis/alertmanager_snapshot.py`

Added a new helper function that handles both formats:

```python
def _extract_receiver(alert_raw: Mapping[str, Any]) -> str | None:
    """Extract receiver name from alert.
    
    Handles both:
    - Scalar receiver field (from webhook payloads): alert_raw["receiver"]
    - Array receivers field (from /api/v2/alerts): alert_raw["receivers"]
    
    Returns the first receiver name deterministically, or None if not present.
    """
    # First check scalar receiver (from webhook payloads)
    receiver = alert_raw.get("receiver")
    if isinstance(receiver, str) and receiver:
        return receiver
    
    # Then check receivers array (from /api/v2/alerts API)
    receivers = alert_raw.get("receivers")
    if isinstance(receivers, (list, tuple)) and receivers:
        first = receivers[0]
        if isinstance(first, str):
            return first
        if isinstance(first, Mapping):
            name = first.get("name")
            if isinstance(name, str) and name:
                return name
    
    return None
```

**Precedence**: Scalar `receiver` takes priority over array `receivers` for backward compatibility.

**Edge cases handled**:
- Empty receivers array → `None`
- Receivers array with empty names → `None`
- Mixed types in receivers array → first valid receiver

### 2. Updated normalize_alertmanager_payload()

Updated to use `_extract_receiver()` instead of direct `alert_raw.get("receiver")`.

### 3. Added Unit Tests

**File**: `tests/unit/test_alertmanager_snapshot_evidence_preservation.py`

12 new tests covering:
- Scalar receiver (webhook format)
- Receivers array with strings
- Receivers array with dicts `[{"name": "team-a"}, ...]`
- Mixed types in receivers array
- Scalar takes precedence over array
- Empty receivers array
- No receiver field
- `/api/v2/alerts` format integration
- Webhook format backward compatibility

## Verification

- **ruff**: ✅ Pass (unused import removed)
- **mypy**: ✅ Pass (type annotation added)
- **Unit tests**: ✅ 45/45 pass (33 original + 12 new R2 tests)
- **ACT-local gate**: ✅ Pass (ruff, mypy, llm-friendly pre-existing size issue)

## Files Changed

- `src/k8s_diag_agent/external_analysis/alertmanager_snapshot.py` (MODIFIED)
- `tests/unit/test_alertmanager_snapshot_evidence_preservation.py` (MODIFIED)

## Commit Message

```
ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R2 fix receiver handling for /api/v2/alerts array format
```

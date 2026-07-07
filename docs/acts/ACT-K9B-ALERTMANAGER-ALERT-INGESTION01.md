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

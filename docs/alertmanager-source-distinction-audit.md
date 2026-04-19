# Alertmanager Source Distinction Audit

## Task
Audit where the distinction between "manually configured" and "manually promoted" Alertmanager sources is lost before reaching the UI, and propose a fix.

---

## Current Canonical States and Origins

### States (`AlertmanagerSourceState`)
| Value | Meaning |
|-------|---------|
| `discovered` | Found by auto-discovery, not yet verified |
| `auto-tracked` | Verified, being actively monitored |
| `degraded` | Verification failed or became unavailable |
| `missing` | Was tracked but no longer available |
| `manual` | User-configured (authoritative) |

### Origins (`AlertmanagerSourceOrigin`)
| Value | Meaning |
|-------|---------|
| `manual` | User-provided endpoint (configured manually) |
| `alertmanager-crd` | Discovered via monitoring.coreos.com/v1 Alertmanager CRD |
| `prometheus-crd-config` | Discovered via Prometheus CRD alerting.alertmanagers |
| `service-heuristic` | Discovered via service/pod name heuristics |

---

## Where Each Path Enters the System

### Path A: Manually Configured Source
```
build_endpoint_for_manual() in alertmanager_discovery.py (lines 974-994)
  → origin = MANUAL
  → state = MANUAL
  → source_id = "manual:{endpoint}" or "manual:{namespace}/{name}"
```

### Path B: Manually Promoted Source
```
health/loop.py: _handle_alertmanager_source_action()
  → SourceAction.PROMOTE
  → write_source_overrides() → effective_state = "manual"
  → ALSO: write_source_registry() → desired_state = "manual"
  → apply_registry_to_source() transforms discovered source:
      origin = MANUAL (overwrites origin!)
      state = MANUAL (overwrites state!)
```

---

## Where the Collapse Occurs

### THE COLLAPSE POINT: `apply_registry_to_source()` in alertmanager_source_registry.py (lines 334-385)

```python
if desired_state == RegistryDesiredState.MANUAL:
    return _replace(
        source,
        origin=AlertmanagerSourceOrigin.MANUAL,  # ← OVERWRITES original origin
        state=AlertmanagerSourceState.MANUAL,    # ← OVERWRITES original state
    )
```

**Problem**: When a source is promoted from auto-discovery, the original `origin` (e.g., `alertmanager-crd`) is completely lost. Both manually configured AND promoted sources end up with:
- `origin = "manual"`
- `state = "manual"`

The system cannot distinguish them.

### Secondary Collapse Point: `_build_alertmanager_sources_view()` in ui/model.py (lines 1865-1870)

```python
effective_state = _coerce_optional_str(src.get("effective_state"))
if effective_state:
    state = effective_state
    # Promotion also changes the origin to "manual"
    if effective_state == "manual":
        origin = "manual"  # ← Again, origin overwritten
```

Both manual-configured and promoted sources compute `is_manual = origin == "manual"` identically.

---

## Artifacts Affected

| Artifact | Scope | Promotes | Manual Config |
|----------|-------|----------|--------------|
| `{run_id}-alertmanager-sources.json` | Run | ✓ (via registry applied) | ✓ |
| `{run_id}-alertmanager-source-overrides.json` | Run | ✓ | ✗ |
| `alertmanager-source-registry.json` | Durable | ✓ | ✗ |

The `AlertmanagerSourceOverrides` (run-scoped) tracks `original_origin` in `SourceOverride.original_origin` — but this is NOT passed through to the UI artifact.

The `AlertmanagerSourceRegistry` (durable) stores `original_origin` in `RegistryEntry.original_origin` — but this is also NOT passed to the UI.

---

## Evidence of Collapse (grep)

```bash
# The overwrite happens here:
grep -n "origin=AlertmanagerSourceOrigin.MANUAL" src/k8s_diag_agent/external_analysis/alertmanager_source_registry.py
# Line 373: origin=AlertmanagerSourceOrigin.MANUAL,

# And here:
grep -n "origin = \"manual\"" src/k8s_diag_agent/ui/model.py
# Line 1870: origin = "manual"
```

---

## Backward Compatibility Concerns

1. **Existing artifacts**: Older `alertmanager-sources.json` artifacts may not have `effective_state` or `original_origin` fields.

2. **UI expectations**: Frontend currently uses `source.is_manual` (computed as `origin == "manual"`) for display logic. Changing this would require frontend updates.

3. **Registry entries**: Existing durable registry entries have `original_origin` stored but not surfaced. Adding a new field is non-breaking.

4. **Override artifacts**: Run-scoped override artifacts have `original_origin` — this can be leveraged without schema changes.

---

## Proposed Canonical Enum/Field Design

### Option 1: Add `manual_classification` enum field (RECOMMENDED)

Add a new field at the `AlertmanagerSource` level:

```python
class ManualClassification(StrEnum):
    """How a source became 'manual'."""
    NOT_MANUAL = "not-manual"        # Source is auto-discovered, never manual
    OPERATOR_CONFIGURED = "operator-configured"  # User typed in endpoint manually
    OPERATOR_PROMOTED = "operator-promoted"      # User promoted from auto-discovery
```

**New field in AlertmanagerSource:**
```python
@dataclass(frozen=True)
class AlertmanagerSource:
    ...
    manual_classification: ManualClassification = ManualClassification.NOT_MANUAL
```

**In `apply_registry_to_source()`:**
- When promoting: set `manual_classification = OPERATOR_PROMOTED`
- When building manual source: set `manual_classification = OPERATOR_CONFIGURED`

**UI payload additions:**
- Pass `manual_classification` through health/ui.py → api.py → frontend
- Frontend uses this for display: "Configured manually" vs "Promoted from discovery"

### Option 2: Preserve `original_origin` in serializable artifact

Instead of adding enum, pass through existing `original_origin` field:

1. In `apply_registry_to_source()`, add `original_origin` to source metadata
2. In `_serialize_alertmanager_sources()`, include `original_origin` in output
3. In `_build_alertmanager_sources_view()`, use `original_origin != null` as signal

**Tradeoff**: Less explicit than Option 1, but fewer schema changes.

### Option 3: Add `promoted_from` field with origin snapshot

```python
@dataclass(frozen=True)
class AlertmanagerSource:
    ...
    promoted_from: AlertmanagerSourceOrigin | None = None  # Set only when promoted
```

**Tradeoff**: Preserves original origin directly, but semantics slightly different from "classification".

---

## Minimal Implementation Plan

### Phase 1: Discovery Layer (smallest coherent change)
**Files**: `src/k8s_diag_agent/external_analysis/alertmanager_discovery.py`

1. Add `ManualClassification` enum
2. Add `manual_classification` field to `AlertmanagerSource`
3. Set `manual_classification = OPERATOR_CONFIGURED` in `build_endpoint_for_manual()`
4. Preserve `manual_classification` in `to_dict()` / `from_dict()`

### Phase 2: Registry Application
**Files**: `src/k8s_diag_agent/external_analysis/alertmanager_source_registry.py`

1. In `apply_registry_to_source()`: set `manual_classification = OPERATOR_PROMOTED` when promoting
2. Log original origin for audit trail

### Phase 3: Artifact Serialization
**Files**: `src/k8s_diag_agent/health/ui.py`

1. Include `manual_classification` in `_serialize_alertmanager_sources()` output
2. Pass through `effective_state` as before for backward compatibility

### Phase 4: Model Projection  
**Files**: `src/k8s_diag_agent/ui/model.py`

1. Add `manual_classification` to `AlertmanagerSourceView`
2. Compute `is_manual` as `manual_classification != NOT_MANUAL` (or similar)

### Phase 5: API Serialization
**Files**: `src/k8s_diag_agent/ui/api.py`

1. Include `manual_classification` in `AlertmanagerSourcePayload`
2. Serialize to client

### Phase 6: Frontend Update (if needed)
**Files**: `frontend/src/App.tsx`, types

1. Add `manualClassification` to `AlertmanagerSource` type
2. Update `AlertmanagerSourcesPanel` display logic

---

## Verification Commands

```bash
# Verify no regression in existing tests
.venv/bin/python -m pytest tests/unit/test_alertmanager_discovery.py -v

# Verify source registry logic
.venv/bin/python -m pytest tests/unit/test_alertmanager_source_registry.py -v

# Verify UI serialization
.venv/bin/python -m pytest tests/unit/test_health_ui.py -v

# Check for any remaining collapse points
grep -rn "origin=AlertmanagerSourceOrigin.MANUAL\|origin = \"manual\"" src/
```

---

## Files Likely to Change

| File | Change |
|------|--------|
| `src/k8s_diag_agent/external_analysis/alertmanager_discovery.py` | Add enum, field, setter |
| `src/k8s_diag_agent/external_analysis/alertmanager_source_registry.py` | Set classification on promote |
| `src/k8s_diag_agent/external_analysis/alertmanager_source_actions.py` | No changes needed (already has original_origin) |
| `src/k8s_diag_agent/health/ui.py` | Include classification in serialization |
| `src/k8s_diag_agent/ui/model.py` | Add field to view, update is_manual logic |
| `src/k8s_diag_agent/ui/api.py` | Include in payload |
| `frontend/src/App.tsx` | Update display logic (if needed) |
| `frontend/src/types.ts` | Add type field |
| `tests/unit/test_alertmanager_discovery.py` | Add tests for classification |
| `tests/unit/test_alertmanager_source_registry.py` | Add tests for promotion classification |

---

## Constraints Compliance

| Constraint | Status |
|------------|--------|
| Preserve artifact immutability | ✓ New field additive, not destructive |
| Do not infer truth in UI only | ✓ Backend semantics explicit |
| Prefer explicit backend semantics | ✓ New enum provides operator-truthful field |
| Keep naming operator-truthful | ✓ `OPERATOR_CONFIGURED` / `OPERATOR_PROMOTED` clear |
| Backward compatibility | ✓ Existing fields preserved, new field optional |

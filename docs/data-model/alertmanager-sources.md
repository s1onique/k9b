# Alertmanager source management

## Purpose

Preserve Alertmanager source management source-of-truth boundaries.

## Artifact taxonomy

The Alertmanager source management involves four distinct artifact types with different mutability semantics.

**Do not conflate these—future code or operators may treat per-run overrides as authoritative when they are not the durable cross-run source of truth.**

| Artifact | Path pattern | Scope | Mutability | Authority |
|----------|-------------|-------|------------|-----------|
| Discovery inventory | `{run_id}-alertmanager-sources.json` | Run | Immutable (written once per run) | Immutable evidence |
| **Per-run overrides** | `{run_id}-alertmanager-source-overrides.json` | **Run** | **Mutable** (overwritten per run) | **NOT authoritative**; derived support artifact for UI |
| **Registry** | `alertmanager-source-registry.json` | Cross-run | Mutable (overwrites cross-run) | **Authoritative source of truth** for cross-run intent |
| Action artifacts | `alertmanager-source-actions/{run_id}-{source_id}-{action}-{artifact_id}.json` | Cross-run | Immutable (append-only, UUID per action) | Immutable audit trail; survives beyond run-scoped state |

## Source-of-truth boundaries

### Registry is authoritative

**Registry** (`alertmanager-source-registry.json`) is the **authoritative cross-run source of truth** for operator promote/disable decisions.

The discovery loop reads from the registry to apply desired state to discovered sources.

### Per-run overrides are derived

**Per-run overrides** (`{run_id}-alertmanager-source-overrides.json`) are **derived run-scoped support artifacts**.

They provide effective state computation for UI display within a single run and are NOT the durable source of truth. They are overwritten each run with the latest per-run overrides.

### Action artifacts are append-only audit trail

**Immutable action artifacts** (`alertmanager-source-actions/`) provide an **append-only audit trail** for operator actions.

Each action creates a new artifact with a unique `artifact_id` (UUIDv7). They survive beyond run-scoped overrides and provide cross-run audit capability independent of current registry state.

## Alertmanager source action artifacts

When an operator promotes or disables a source via the UI (`POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action`), the server writes an artifact.

### Artifact contents

| Field | Description |
|-------|-------------|
| `artifact_id` | Unique identifier |
| `run_id` | Run identifier |
| `action` | `promote` or `disable` |
| `source_id` | Source identifier |
| `canonical_identity` | Canonical source identity |
| `cluster_label` | Cluster label |
| `cluster_context` | Cluster context |
| `registry_key` | Registry key (`{cluster_label}:{canonical_identity}` or fallback) |
| `endpoint` | Endpoint at time of action |
| `namespace` | Namespace at time of action |
| `name` | Name at time of action |
| `original_origin` | Original origin |
| `original_state` | Original state |
| `resulting_state` | Resulting state |
| `previous_desired_state` | Previous desired state |
| `reason` | Operator-provided reason |
| `created_at` / `timestamp` | Audit timestamps |
| `schema_version` | `"1"` for future compatibility |

### Registry key format

`{cluster_label}:{canonical_identity}` (preferred) or `{cluster_context}:{canonical_identity}` as fallback.

### Mutability contract

- Artifacts are **append-only** (unique filename per action via UUID suffix)
- Non-fatal to write—failure is logged but does not block the action response
- Survive beyond run-scoped overrides for cross-run audit capability

## Contract summary

| Question | Answers |
|----------|--------|
| "What is the durable cross-run intent?" | Registry |
| "What is the per-run effective state?" | Per-run overrides (derived) |
| "What actions were taken historically?" | Action artifacts (append-only) |

**Cross-run operator intent lives in the registry, not in per-run override artifacts.**

Do not use per-run override artifacts as the authoritative source for cross-run persistence.

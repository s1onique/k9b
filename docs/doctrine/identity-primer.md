# Identity Primer: Durable Canonical Identities

## Purpose

Define a consistent identity strategy for clusters, inferred entities, and artifacts that preserves historical truth across:
- kubeconfig renames
- label changes
- cluster rebuilds
- rediscovery of inferred entities

## Problem Statement

Kubernetes distinguishes names from UIDs; UIDs are the historical identity anchor for objects. We currently overuse `cluster_label` / `cluster_context` as canonical identity in several places. This causes:

1. **Same cluster under different contexts** → treated as different clusters
2. **Rebuilt cluster with same label** → treated as the same cluster (incorrect)
3. **Same K8s object after recreation** → not distinguished from original

## Identity Classes

### 1. Cluster Identity (`cluster_uid`)

**Source:** `kube-system` namespace `metadata.uid`

**Purpose:** Historical identity anchor for a Kubernetes cluster.

**Invariant:** A rebuilt cluster has a different UID even if the operator reuses the same label/context.

**Derivation:**
```python
cluster_uid = derive_cluster_uid(kube_context: str | None) -> str | None
# Uses kubectl to get kube-system namespace metadata.uid
# Returns None if kubectl unavailable or kube-system namespace not found
# Does NOT fall back to cluster_label - use display field for that
```

**Display fields (NOT canonical):**
- `cluster_label`: Operator-facing, user-defined label from config
- `cluster_context`: Kubernetes context name from kubeconfig

### 2. Kubernetes Object Identity (`object_uid`)

**Source:** Native Kubernetes `metadata.uid`

**Purpose:** Historical identity for any Kubernetes object.

**Usage:**
```python
object_ref = build_k8s_object_ref(
    namespace: str | None,
    kind: str,
    name: str,
    object_uid: str | None,  # Optional, from API response
) -> K8sObjectRef
```

### 3. Inferred Entity Identity (`canonical_entity_id`)

**Source:** Deterministic hash of normalized defining facts

**Purpose:** For entities without native UIDs (e.g., Alertmanager sources, discovered services).

**Invariant:** Same facts → same ID across discoveries, even across runs.

**Derivation:**
```python
canonical_entity_id = build_deterministic_entity_id(
    entity_type: str,  # e.g., "alertmanager-source"
    defining_facts: dict[str, Any],  # Normalized facts that define the entity
) -> str
```

**Example for Alertmanager sources:**
- Key facts: `namespace`, `name` (from CRD)
- Canonical ID: `namespace/name` format
- Deterministic ID (for hashing): `sha256("alertmanager-source|namespace=X|name=Y")`

### 4. Artifact Identity (`artifact_id`)

**Source:** UUIDv7 generated at creation time

**Purpose:** Immutable identifier for artifacts, events, and runs.

**Invariant:** Once assigned, never changes. Historical artifacts are not rewritten.

**Derivation:**
```python
artifact_id = new_artifact_id() -> str
# Uses UUIDv7 for time-ordered, immutable IDs
```

## Naming Conventions

| Field | Scope | Purpose | Example |
|-------|-------|---------|---------|
| `cluster_uid` | Cluster | Historical anchor | `550e8400-e29b-41d4-a716-446655440000` |
| `cluster_label` | Cluster | Display/provenance | `prod-us-east` |
| `cluster_context` | Cluster | Execution context | `admin@prod-us-east` |
| `object_uid` | K8s objects | Historical anchor | Kubernetes native UID |
| `canonical_entity_id` | Inferred entities | Deterministic ID | `monitoring/alertmanager-main` |
| `artifact_id` | Artifacts | Immutable ID | `0192a1b8-3c4e-5678-abcd-1234567890ab` |

## Invariants

### I1: Display ≠ Canonical
`cluster_label` and `cluster_context` are display/provenance fields, never sole canonical identity.

### I2: Native K8s Objects
Use `metadata.uid` as historical identity anchor for all Kubernetes objects.

### I3: Inferred Entities
Use deterministic canonical IDs built from normalized defining facts, not random IDs.

### I4: New Artifacts
All new artifacts receive `artifact_id` at creation time.

### I5: Historical Artifacts
Historical artifacts are never mutated in place.

### I6: Separation
Canonical identity and display identity remain separate in all data structures.

## Alertmanager Source Migration

### Current State
- Sources keyed by `cluster_context` + `source_id` in registry
- `source_id` varies by discovery strategy (prefix: `crd:`, `service:`, `pod:`)

### Target State
- Sources keyed by operator-stable cluster identifier + `canonical_identity` (deterministic)
- `canonical_identity` = `namespace/name` when available
- Registry key: `{cluster_key}:namespace/name` where `cluster_key` prefers `cluster_label` (operator-controlled) over `cluster_context` (kubeconfig-controlled)

### Registry Key Design Rationale

The registry uses `cluster_label` (or `cluster_context` fallback) rather than `cluster_uid` for registry keys because:
1. `cluster_uid` requires kubectl access to derive, while registry writes happen with operator intent
2. `cluster_label` is operator-controlled and stable across kubeconfig edits
3. `cluster_context` can change with kubeconfig renames/aliases

**Invariant tension:** Using `cluster_label` in registry keys technically violates "display ≠ canonical," but this is a pragmatic tradeoff for cross-run persistence. The registry is a durable operator intent store, not a historical truth store.

### Migration Rules
1. New registry entries prefer `cluster_label` over `cluster_context` for stability
2. Legacy context-keyed entries supported via fallback lookup
3. Existing artifacts readable with no in-place mutation
4. Display labels remain human-readable

## Artifact Schema Changes

### New Fields

```python
@dataclass
class BaseArtifact:
    artifact_id: str  # UUIDv7, immutable, required for new artifacts
    created_at: datetime  # Timestamp for ordering
    # Legacy: run_id remains for backward compatibility
    # Display fields: cluster_label, context, run_label preserved
```

### Backward Compatibility

- Existing artifacts without `artifact_id` are readable
- Missing `artifact_id` implies legacy artifact (created before migration)
- No field migrations or rewrites performed on old artifacts
- API handles missing fields gracefully

## Acceptance Criteria

| Criterion | Test Case |
|-----------|-----------|
| Same cluster / different context | `cluster_label="prod", context="old"` and `cluster_label="prod", context="new"` resolve to same `cluster_uid` |
| Rebuilt cluster / reused label | Cluster A (`uid=abc`) rebuilt → Cluster B (`uid=def`) with same label → different `cluster_uid` |
| K8s object recreation | Object X (`uid=abc`) deleted, recreated as Object X (`uid=def`) → different `object_uid` |
| Alertmanager rediscover | Same Alertmanager source discovered twice → same `canonical_entity_id` |
| New artifacts include ID | New `ExternalAnalysisArtifact` → `artifact_id` field populated |
| Old artifacts readable | Legacy artifact without `artifact_id` → readable, no errors |
| UI remains readable | UI shows `cluster_label` as primary identifier, not `cluster_uid` |

## Implementation Notes

1. **Prefer explicit names:** `cluster_uid`, `object_uid`, `artifact_id`, `canonical_entity_id`
2. **Avoid generic `id`:** Unless the scope is unambiguous
3. **Keep display fields:** Labels, contexts, namespaces, names, endpoints → display only
4. **UUIDv7 preference:** For time-ordered artifact IDs, prefer UUIDv7 over UUIDv4

## Module Location

Shared identity helpers belong in:
```
src/k8s_diag_agent/identity/
├── __init__.py
├── cluster.py       # derive_cluster_uid()
├── k8s_object.py    # build_k8s_object_ref()
├── entity.py        # build_deterministic_entity_id()
└── artifact.py      # new_artifact_id()
```

# Incident aggregate root

## Purpose

Document `Incident` as the central lifecycle aggregate root.

**Core doctrine:**
- Incident owns case lifecycle
- Artifacts own evidence truth
- Incident does not replace immutable run artifacts
- Evidence is linked, not embedded

## Current implementation

`Incident` is now the **central lifecycle aggregate root for incident management**.

Source: `src/k8s_diag_agent/collect/incident_lifecycle.py`

## Source-of-truth boundary

| Question | Answers |
|----------|---------|
| "What case is the operator working?" | Incident |
| "How did this case reach its current state?" | IncidentEvent |
| "Which artifacts support this case?" | EvidenceLink |
| "What did k9b observe?" | Artifact store (NOT Incident) |

Incident is the **case file**, not the **evidence store**.

## Object model

```
Incident
├─ signals: IncidentSignal[]
├─ evidence_links: EvidenceLink[]
│    └─ artifact_id → EvidenceArtifact / artifact_id / storage_ref
├─ review_packet: ReviewPacketState
└─ events: IncidentEvent[]
```

### Incident

| Field | Type | Description |
|-------|------|-------------|
| `incident_id` | str | Deterministic ID from namespace/kind/name/candidate_class |
| `status` | IncidentStatus | Lifecycle state |
| `signals` | list[IncidentSignal] | Signals that contributed to this incident |
| `evidence_links` | list[EvidenceLink] | Links to attached evidence artifacts |
| `review_packet` | ReviewPacketState | Review packet generation state |
| `events` | list[IncidentEvent] | Append-only timeline |
| `signal_count` | int | Number of signals merged |
| `evidence_count` | int | Number of evidence links attached |
| `latest_snapshot_bundle_id` | str \| None | Convenience pointer to latest snapshot bundle |
| `first_observed_at` | datetime | When incident was first opened |
| `last_observed_at` | datetime | When incident was last updated |
| `suppressed_reason` | str \| None | Reason for suppression |
| `duplicate_of` | str \| None | ID of duplicate incident |
| `resolved_at` | datetime \| None | When incident was resolved |
| `resolution_notes` | str \| None | Resolution notes |

### IncidentSignal

| Field | Type | Description |
|-------|------|-------------|
| `source` | str | Signal source |
| `reason` | str | Why signal was triggered |
| `message` | str | Human-readable message |
| `captured_at` | datetime | When signal was captured |
| `run_id` | str \| None | Associated run |
| `detector_id` | str \| None | Detector that found signal |
| `finding_id` | str \| None | Finding that produced signal |
| `fingerprint` | str \| None | Signal fingerprint for dedup |

### EvidenceLink

| Field | Type | Description |
|-------|------|-------------|
| `incident_id` | str | Associated incident |
| `artifact_id` | str | ID of evidence artifact |
| `role` | EvidenceRole | PRIMARY, SUPPORTING, SNAPSHOT, REVIEW_PACKET, DEBUG |
| `attached_at` | datetime | When link was created |

### EvidenceArtifact

| Field | Type | Description |
|-------|------|-------------|
| `artifact_id` | str | Unique identifier |
| `kind` | EvidenceKind | SNAPSHOT_BUNDLE, REVIEW_PACKET, LOG_EXCERPT, METRIC_WINDOW, TRACE, RUN_SUMMARY, EXTERNAL_ANALYSIS |
| `storage_ref` | str | Reference to stored artifact |
| `content_hash` | str \| None | Content hash for integrity |
| `created_at` | datetime | When artifact was created |
| `collected_by` | str | "system" or "user" |
| `redaction_status` | RedactionStatus | RAW, REDACTED, SAFE_FOR_REVIEW |

### ReviewPacketState

| Field | Type | Description |
|-------|------|-------------|
| `status` | ReviewPacketStatus | NOT_GENERATED, GENERATING, AVAILABLE, FAILED |
| `id` | str \| None | Artifact ID (required for GENERATING/AVAILABLE) |
| `generated_at` | datetime \| None | When packet was generated |
| `error_message` | str \| None | Error message if failed |

**Invariant:** `GENERATING` and `AVAILABLE` require non-empty `id`.

### IncidentEvent

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | str | Collision-resistant ID with data hash suffix |
| `incident_id` | str | Associated incident |
| `event_type` | IncidentEventType | OPENED, SIGNAL_MERGED, EVIDENCE_COLLECTION_STARTED, etc. |
| `actor` | IncidentEventActor | SYSTEM, USER, DETECTOR, SCHEDULER |
| `occurred_at` | datetime | When event occurred |
| `message` | str | Human-readable description |
| `actor_id` | str \| None | ID of actor (for USER/DETECTOR) |
| `data` | dict \| None | Additional event data |

## Lifecycle states

```
open
collecting_evidence
ready_for_review
investigating
suppressed
duplicate
resolved
```

### Protected states

- `suppressed`, `duplicate`, and `resolved` are **protected from normal bundle reactivation**.
- `ready_for_review` should **not be downgraded** by a later bundle merge.

### latest_snapshot_bundle_id

This is a **convenience pointer** to the latest attached snapshot bundle, not the only evidence truth.

Evidence truth lives in the artifact store. `latest_snapshot_bundle_id` exists to help the UI display the most recent snapshot without scanning all evidence links.

## Timeline events

Events are **append-only** and represent historical facts.

Event types: `OPENED`, `SIGNAL_MERGED`, `SEVERITY_CHANGED`, `EVIDENCE_COLLECTION_STARTED`, `SNAPSHOT_BUNDLE_ATTACHED`, `EVIDENCE_ARTIFACT_ATTACHED`, `REVIEW_PACKET_GENERATED`, `REVIEW_PACKET_FAILED`, `STATUS_CHANGED`, `SUPPRESSED`, `MARKED_DUPLICATE`, `CLOSED`.

Actors: `SYSTEM`, `USER`, `DETECTOR`, `SCHEDULER`.

## Derived read models

UI/API payloads for incident views are **derived projections** from the Incident aggregate and attached artifacts.

The Incident aggregate owns the truth; read models own convenience.

## Non-goals

- Incident does **not** replace immutable run artifacts
- Incident does **not** own raw snapshot blobs
- Incident does **not** own diagnostic pack contents
- Incident does **not** perform autonomous remediation
- Incident does **not** mutate cluster resources

## Future direction

- `IncidentSuggestedCheck` — maps from current `NextCheck` planning artifacts
- `IncidentCheckExecution` — maps from current manual promotion/execution artifacts
- Incident-scoped next-check API
- Persistent EvidenceArtifact store
- Global next-check queue grouped by incident

These are **target direction**, not current implementation.

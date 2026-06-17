# k9b data model

## Purpose

This document is the map, not the full contract.

k9b is **evidence-first and artifact-backed**: health runs produce durable JSON artifacts under `runs/health`, and the backend/UI derive views from those artifacts.

k9b is now **incident-centered for case lifecycle**: `Incident` is the central aggregate root for incident management, while runs, signals, evidence links, review packet state, and timeline events attach to the Incident.

## Current reality

- **Run artifacts remain the durable source of truth for observed evidence.** The `runs/health/` tree contains snapshots, assessments, comparisons, triggers, drilldowns, reviews, proposals, external-analysis artifacts, and notifications.
- **Diagnostic pack ZIPs and run-scoped pack contents are immutable source-of-truth artifacts.**
- **`latest/` mirrors are mutable convenience aliases**, not authoritative references.
- **UI/API payloads may be derived projections.**
- **Alertmanager registry/action artifacts retain their documented source-of-truth boundaries.**
- **Next-check artifacts still exist as compatibility/evidence artifacts.**

## New incident model

`Incident` is now the **central lifecycle aggregate root** for incident management.

### Incident owns

- lifecycle status
- signals
- evidence links
- review packet state
- timeline events
- signal/evidence counters
- latest snapshot bundle convenience reference

### Incident does not own

- raw snapshot blobs
- diagnostic pack contents
- external-analysis artifacts
- immutable history facts
- Alertmanager registry truth
- autonomous remediation

### Object model

```
Incident
├─ signals: IncidentSignal[]
├─ evidence_links: EvidenceLink[]
│    └─ artifact_id → EvidenceArtifact / storage_ref
├─ review_packet: ReviewPacketState
└─ events: IncidentEvent[]
```

### Lifecycle states

```
open → collecting_evidence → ready_for_review → investigating
                 ↓                                    ↓
            suppressed ←──────── duplicate ─────────→ resolved
```

Protected states: `suppressed`, `duplicate`, and `resolved` are protected from normal bundle reactivation. `ready_for_review` should not be downgraded by a later bundle merge.

`latest_snapshot_bundle_id` is a **convenience pointer** to the latest attached snapshot bundle, not the only evidence truth.

## Source-of-truth rules

| Question | Answers |
|----------|---------|
| "What did k9b observe?" | Artifact store |
| "What case is the operator working?" | Incident |
| "How did this case reach its current state?" | IncidentEvent |
| "Which artifacts support this case?" | EvidenceLink |
| "What should the operator see now?" | Derived UI payloads |

**Core doctrine:**
- Incident owns case lifecycle
- Artifacts own evidence truth
- Read models own UI convenience
- No autonomous remediation or cluster mutation

## Compatibility bridge

| Old pattern | New pattern |
|-------------|-------------|
| `snapshot_bundle_id` | `latest_snapshot_bundle_id` |
| `review_packet_available` + `review_packet_id` | `review_packet: ReviewPacketState` |
| NextCheck | target IncidentSuggestedCheck (future) |
| Manual next-check promotion | target IncidentCheckExecution (future) |
| next-check execution artifacts | EvidenceArtifact + EvidenceLink |
| run-scoped incident reports | transitional/derived incident read models |

## Detailed contracts

- [artifacts.md](data-model/artifacts.md) — Durable artifact taxonomy and source-of-truth boundaries
- [run-lifecycle.md](data-model/run-lifecycle.md) — Deterministic health-run lifecycle
- [incidents.md](data-model/incidents.md) — Incident aggregate root documentation
- [next-checks.md](data-model/next-checks.md) — Next-check/manual promotion flow
- [review-packets.md](data-model/review-packets.md) — Diagnostic pack/review packet semantics
- [alertmanager-sources.md](data-model/alertmanager-sources.md) — Alertmanager source management
- [ui-model-boundaries.md](data-model/ui-model-boundaries.md) — UI/API read-model boundaries
- [incident-report-quality.md](data-model/incident-report-quality.md) — Incident report quality contracts

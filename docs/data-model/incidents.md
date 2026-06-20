# Incident aggregate root

## Purpose

Document `Incident` as the **central lifecycle aggregate root** for the k9b incidents product.

**Core doctrine:**
- Incident owns case lifecycle
- Artifacts own evidence truth
- Incident does not replace immutable run artifacts
- Evidence is linked, not embedded
- Read-only evidence is strictly separated from operator actions
- No autonomous remediation or cluster mutation

## Central aggregate root

`Incident` is the **organizing root** for all incident-scoped concepts:

| Incident-scoped concept | Description | Maps from |
|------------------------|-------------|-----------|
| `IncidentSignal` | Detection source signals | Alertmanager, detectors, findings |
| `IncidentSuggestedCheck` | Suggested diagnostic checks (target) | Current `next-check-plan` artifacts |
| `IncidentCheckExecution` | Accepted/promoted check execution (target) | Current `next-check-promotion` and `next-check-execution` artifacts |
| `EvidenceArtifact` | Evidence collected from check executions | Check result artifacts |
| `EvidenceLink` | Links evidence artifacts to incident | `EvidenceArtifact` + incident reference |
| `ReviewPacketState` | Diagnostic review packet generation state | `review_bundle.json` artifacts |
| `IncidentEvent` | Append-only timeline events | All incident lifecycle transitions |
| `LLMDiagnosis` | LLM-generated diagnosis (future) | Provider analysis artifacts |
| `HandoffPayload` | Operator handoff material (future) | Derived from review packet |

**Invariant:** All incident-scoped concepts attach to exactly one `Incident`. There is no incident-scoped concept that exists outside an incident context.

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
Incident (aggregate root)
├─ signals: IncidentSignal[]
├─ suggested_checks: IncidentSuggestedCheck[] (target)
├─ check_executions: IncidentCheckExecution[] (target)
├─ evidence_links: EvidenceLink[]
│    └─ artifact_id → EvidenceArtifact / artifact_id / storage_ref
├─ review_packet: ReviewPacketState
├─ llm_diagnosis: LLMDiagnosis (future)
├─ handoff_payload: HandoffPayload (future)
└─ events: IncidentEvent[]
```

### Incident

| Field | Type | Description |
|-------|------|-------------|
| `incident_id` | str | Deterministic ID from namespace/kind/name/candidate_class |
| `status` | IncidentStatus | Lifecycle state |
| `signals` | list[IncidentSignal] | Signals that contributed to this incident |
| `suggested_checks` | list[IncidentSuggestedCheck] | **Target:** Suggested diagnostic checks (future) |
| `check_executions` | list[IncidentCheckExecution] | **Target:** Accepted/promoted check executions (future) |
| `evidence_links` | list[EvidenceLink] | Links to attached evidence artifacts |
| `review_packet` | ReviewPacketState | Review packet generation state |
| `llm_diagnosis` | LLMDiagnosis \| None | **Target:** LLM-generated diagnosis (future) |
| `handoff_payload` | HandoffPayload \| None | **Target:** Operator handoff material (future) |
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

### IncidentSuggestedCheck (target)

**Status:** Target model; current implementation uses `next-check-plan` artifacts.

Maps from current `next-check-plan` artifacts. The UI displays suggested checks attached to the incident.

| Field | Type | Description |
|-------|------|-------------|
| `check_id` | str | Unique check identifier |
| `title` | str | Human-readable title |
| `rationale` | str | Why this check is suggested |
| `source` | str | "next-check-plan" |
| `risk_level` | str \| None | LOW, MEDIUM, HIGH |
| `requires_approval` | bool | Whether operator approval is required |
| `status` | str | "suggested", "accepted", "rejected" |
| `artifact_id` | str \| None | Reference to plan artifact |
| `run_id` | str \| None | Source run ID |

### IncidentCheckExecution (target)

**Status:** Target model; current implementation uses `next-check-promotion` and `next-check-execution` artifacts.

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | str | Unique execution identifier |
| `check_id` | str | Reference to suggested check |
| `status` | str | "pending", "running", "completed", "failed" |
| `command` | str | Bounded kubectl command executed |
| `result` | CheckResult \| None | Execution result |
| `evidence_artifact_id` | str \| None | Reference to evidence artifact |
| `executed_at` | datetime \| None | When execution occurred |
| `executed_by` | str | "operator" or "system" |

### CheckResult (target)

| Field | Type | Description |
|-------|------|-------------|
| `summary` | str | Brief result summary |
| `output` | str | Captured stdout/stderr |
| `duration_ms` | int | Execution duration |
| `status` | str | "success", "failure", "timeout" |

### EvidenceLink

| Field | Type | Description |
|-------|------|-------------|
| `incident_id` | str | Associated incident |
| `artifact_id` | str | ID of evidence artifact |
| `role` | EvidenceRole | PRIMARY, SUPPORTING, SNAPSHOT, REVIEW_PACKET, **DIAGNOSIS (target)**, DEBUG |
| `attached_at` | datetime | When link was created |

### EvidenceArtifact

| Field | Type | Description |
|-------|------|-------------|
| `artifact_id` | str | Unique identifier |
| `kind` | EvidenceKind | SNAPSHOT_BUNDLE, REVIEW_PACKET, LOG_EXCERPT, METRIC_WINDOW, TRACE, RUN_SUMMARY, EXTERNAL_ANALYSIS, **DIAGNOSIS_REVIEW_PACKET (target)** |
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
| `event_type` | IncidentEventType | Category (see Timeline events section) |
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

### Event type categories

| Category | Event types | Description |
|----------|-------------|-------------|
| **Detection/Source** | `OPENED`, `SIGNAL_MERGED` | Incident creation and signal aggregation |
| **State Transition** | `STATUS_CHANGED`, `SEVERITY_CHANGED` | Lifecycle state changes |
| **Evidence Collection** | `EVIDENCE_COLLECTION_STARTED`, `SNAPSHOT_BUNDLE_ATTACHED`, `EVIDENCE_ARTIFACT_ATTACHED` | Evidence gathering activities |
| **Diagnosis Loop** | `DIAGNOSIS_LOOP_STARTED`, `DIAGNOSIS_LOOP_COMPLETED`, `DIAGNOSIS_LOOP_FAILED` | **Target:** Automatic diagnosis loop events |
| **Suggested Check** | `SUGGESTED_CHECK_CREATED` | **Target:** New suggested check (future) |
| **Check Promotion** | `CHECK_ACCEPTED` | **Target:** Operator accepted suggested check (future) |
| **Check Execution** | `CHECK_EXECUTED`, `CHECK_FAILED` | **Target:** Check execution events (future) |
| **Diagnosis** | `LLM_DIAGNOSIS_GENERATED`, `DIAGNOSIS_FAILED` | **Target:** LLM diagnosis events (future) |
| **Review Packet** | `REVIEW_PACKET_GENERATED`, `REVIEW_PACKET_FAILED` | Review packet lifecycle |
| **Handoff** | `HANDOFF_GENERATED`, `HANDOFF_COPIED`, `HANDOFF_EXPORTED` | **Target:** Handoff material events (future) |
| **Resolution** | `SUPPRESSED`, `MARKED_DUPLICATE`, `CLOSED` | Incident resolution |
| **Operator Action** | `OPERATOR_NOTE_ADDED` | **Target:** Operator annotations (future) |

### Current event types

From `IncidentEventType` enum:

- `OPENED` — Incident was created
- `SIGNAL_MERGED` — New signal merged into incident
- `SEVERITY_CHANGED` — Incident severity changed
- `EVIDENCE_COLLECTION_STARTED` — Evidence collection initiated
- `SNAPSHOT_BUNDLE_ATTACHED` — Snapshot bundle linked to incident
- `EVIDENCE_ARTIFACT_ATTACHED` — Evidence artifact linked to incident
- `REVIEW_PACKET_GENERATED` — Review packet became available
- `REVIEW_PACKET_FAILED` — Review packet generation failed
- `STATUS_CHANGED` — Incident status changed
- `SUPPRESSED` — Incident was suppressed
- `MARKED_DUPLICATE` — Incident marked as duplicate
- `CLOSED` — Incident was closed
- `DIAGNOSIS_LOOP_STARTED` — Automatic diagnosis loop started for incident
- `DIAGNOSIS_LOOP_COMPLETED` — Automatic diagnosis loop completed successfully
- `DIAGNOSIS_LOOP_FAILED` — Automatic diagnosis loop failed

### Target event types (future)

To be added when incident-scoped check model is implemented:

- `SUGGESTED_CHECK_CREATED` — New suggested check added to incident
- `CHECK_ACCEPTED` — Operator accepted suggested check
- `CHECK_PROMOTED` — Check promoted to execution queue
- `CHECK_EXECUTED` — Check execution completed
- `CHECK_FAILED` — Check execution failed
- `LLM_DIAGNOSIS_GENERATED` — LLM diagnosis completed
- `DIAGNOSIS_FAILED` — LLM diagnosis failed
- `HANDOFF_GENERATED` — Handoff material generated
- `HANDOFF_COPIED` — Handoff copied to clipboard
- `HANDOFF_EXPORTED` — Handoff exported to file/share
- `OPERATOR_NOTE_ADDED` — Operator added annotation

### Event actors

| Actor | Description |
|-------|-------------|
| `SYSTEM` | k9b automated processes |
| `USER` | Human operator actions |
| `DETECTOR` | Signal detection subsystem |
| `SCHEDULER` | Scheduled/periodic processes |

## Automatic diagnosis loop artifacts

Automatic diagnosis loop runs produce artifacts that attach to incidents.

### Incident-scoped location

| Artifact type | Path pattern | Incident attachment |
|--------------|--------------|---------------------|
| Loop run metadata | `runs/health/external-analysis/{run_id}-diagnosis-loop-{incident_id}.json` | Via incident signal run_id linkage |
| Diagnosis review packet | `runs/health/external-analysis/{run_id}-diagnosis-review-packet.json` | Via EvidenceLink with role=DIAGNOSIS (target) |
| Collected evidence | Part of review packet | Via EvidenceLink with role=PRIMARY/SUPPORTING |

### Safety constraints

The automatic diagnosis loop is **read-only only**:
- No kubectl, helm, subprocess, or shell calls
- No Kubernetes write client
- No mutation or remediation
- No external LLM calls
- No unbounded loops

**The review packet is evidence only — it must not be interpreted as permission to act.**

### Loop run metadata fields

```json
{
  "run_id": "auto-incident-123-20260619074500",
  "incident_id": "incident-123",
  "collector_run_id": "auto-diagnosis-20260619074500-abc123",
  "generated_at": "2026-06-19T07:45:00+00:00",
  "decision": "run_allowed_read_only_checks",
  "checks_requested": 3,
  "checks_run": 2,
  "checks_rejected": 1,
  "eligible": true,
  "eligibility_reason": "active_incident_with_suggested_checks",
  "read_only": true,
  "review_required_before_any_action": true,
  "no_remediation_attempted": true
}
```

### Failure/unavailable states

| State | Description |
|-------|-------------|
| `no_review_packet` | No diagnosis review packet exists for this incident |
| `ineligible_incident` | Incident not in eligible state (OPEN, COLLECTING_EVIDENCE, INVESTIGATING) |
| `budget_exhausted` | Per-run budget limits reached |
| `malformed_artifact` | Review packet exists but is malformed |

## Read-only evidence vs operator action vs forbidden autonomy

### Read-only evidence (system → incident)

These are **observations**, never instructions:

| Type | Description |
|------|-------------|
| `IncidentSignal` | Detection of potential issue |
| `EvidenceArtifact` | Collected cluster data |
| `ReviewPacketState` | Generated diagnostic summary |
| `LLMDiagnosis` | Generated assessment (advisory only) |
| `IncidentSuggestedCheck` | Recommended diagnostic step |

**Invariant:** Read-only evidence never contains action imperatives or mutation instructions.

### Operator-approved/manual actions

These require **explicit human consent**:

| Type | Description |
|------|-------------|
| `IncidentCheckExecution` | Approved check execution |
| Operator annotations | Manual notes added to incident |
| Status transitions | Human-initiated state changes |

**Invariant:** All check executions require explicit operator approval for risky operations.

### Forbidden autonomous remediation

The system **must never**:

| Forbidden | Rationale |
|-----------|-----------|
| Mutate Kubernetes resources | Safety boundary; operators control cluster state |
| Apply configurations | Could cause disruption; requires human review |
| Delete resources | Data loss risk; requires explicit operator action |
| Scale workloads | Could impact service availability |
| Execute privileged commands | Requires explicit operator approval |
| Claim remediation authority | System is advisory; operators make final decisions |

**Invariant:** Every artifact and UI element must be explicitly marked as read-only evidence. No implicit action permissions.

## Compatibility bridge

| Current pattern | Target pattern |
|-----------------|----------------|
| `next-check-plan` artifacts | `IncidentSuggestedCheck` (future) |
| `next-check-promotion` artifacts | `IncidentCheckExecution` (target) |
| `next-check-execution` artifacts | `IncidentCheckExecution` with `EvidenceArtifact` (target) |
| Run-scoped incident reports | Incident-scoped read models |
| Ad-hoc next-check queue | Incident-grouped check queue |

**Compatibility:** Current artifacts remain valid and continue to work. The target model provides a unified incident-scoped view.

## Derived read models

UI/API payloads for incident views are **derived projections** from the Incident aggregate and attached artifacts.

The Incident aggregate owns the truth; read models own convenience.

## Non-goals

- Incident does **not** replace immutable run artifacts
- Incident does **not** own raw snapshot blobs
- Incident does **not** own diagnostic pack contents
- Incident does **not** perform autonomous remediation
- Incident does **not** mutate cluster resources
- Incident does **not** make remediation decisions
- Incident does **not** claim automatic resolution authority

## Future direction

- `IncidentSuggestedCheck` — maps from current `next-check-plan` artifacts
- `IncidentCheckExecution` — maps from current `next-check-promotion` and `next-check-execution` artifacts
- `CheckResult` — structured check execution results
- `LLMDiagnosis` — LLM-generated diagnosis attached to incident
- `HandoffPayload` — operator handoff material
- Extended `IncidentEventType` — check and diagnosis timeline events
- Persistent `EvidenceArtifact` store
- Incident-grouped check queue

These are **target direction**, not current implementation.

## References

- [next-checks.md](./next-checks.md) — Next-check/manual promotion flow mapping
- [next-check-mapping.md](./next-check-mapping.md) — Detailed next-check-to-incident mapping
- [review-packets.md](./review-packets.md) — Review packet semantics
- [artifacts.md](./artifacts.md) — Artifact taxonomy and immutability
- [ui-model-boundaries.md](./ui-model-boundaries.md) — UI/API read-model boundaries
- `docs/incidents/automatic-diagnosis-loop.md` — Automatic diagnosis loop documentation
- `src/k8s_diag_agent/collect/incident_lifecycle.py` — Incident implementation
- `src/k8s_diag_agent/collect/incident_events.py` — Event type definitions
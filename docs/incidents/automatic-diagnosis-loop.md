# Automatic Diagnosis Loop

## Overview

The automatic diagnosis loop is an **opt-in feature** that automatically collects bounded read-only diagnosis evidence packets for eligible incidents during the health loop run.

**Key principle:** The diagnosis loop is an incident-scoped concept. All artifacts and events attach to exactly one `Incident`.

## Activation

Enable via environment variable:

```bash
export K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true
```

Default is **disabled** for safety.

## Review-packet creation budget

Each new automatic-diagnosis collector run starts with a fresh
``ReviewPacketCreationBudget`` keyed by the collector's
``AutomaticDiagnosisCollectorRunId``. A unit of budget is consumed
ONLY when a review packet is **persisted successfully**; failed
writes, ineligible/skipped incidents, and reusable existing packets
do NOT charge the budget. The budget diagnostic source label is
always the canonical ``collector_run_accounting`` string so a fresh
collector can never inherit usage from historical review-packet
artifacts written by another collector.

| Field | Value | Meaning |
|-------|-------|---------|
| ``name`` | ``review_packet_creation_budget`` | stable diagnostic name |
| ``scope`` | ``automatic_diagnosis_collector`` | per-collector key |
| ``scope_id`` | collector run id | unique per collector |
| ``used`` | integer | persisted packets by THIS collector |
| ``limit`` | integer | configured ceiling |
| ``remaining`` | integer | ``max(0, limit - used)`` |
| ``exhausted`` | boolean | ``used >= limit`` |
| ``source`` | ``collector_run_accounting`` | in-memory authority |
| ``resettable`` | ``true`` | new collector = new budget |

## Behavior

When enabled:
- Health loop automatically invokes the evidence collector
- Collector processes only eligible active incidents (OPEN, COLLECTING_EVIDENCE, INVESTIGATING)
- Respects hard budget bounds: max 10 incidents/run, 1 pass/incident, 5 checks/pass
- Writes bounded review packets named `{run_id}-diagnosis-review-packet.json`
- Idempotent: second automatic run skips incidents with exhausted budget

When disabled (default):
- No automatic evidence collection
- Manual diagnosis-loop UI/API remains unchanged
- Health loop behavior is unchanged

## Safety Constraints

The automatic collector is **read-only only**:
- No kubectl, helm, subprocess, or shell calls
- No Kubernetes write client
- No mutation or remediation
- No external LLM calls
- No unbounded loops

**The review packet is evidence only — it must not be interpreted as permission to act.**

## Incident-scoped artifact location

Automatic diagnosis loop artifacts attach to incidents via `EvidenceLink`:

| Artifact type | Path pattern | Incident attachment |
|--------------|--------------|---------------------|
| Loop run metadata | `runs/health/external-analysis/{run_id}-diagnosis-loop-{incident_id}.json` | Via incident signal run_id linkage |
| Diagnosis review packet | `runs/health/external-analysis/{run_id}-diagnosis-review-packet.json` | Via EvidenceLink with role=DIAGNOSIS |
| Collected evidence | Part of review packet | Via EvidenceLink with role=PRIMARY/SUPPORTING |

### Artifact hierarchy

```
Incident
├─ signals: IncidentSignal[]
│    └─ run_id → external-analysis/{run_id}-diagnosis-loop-{incident_id}.json
├─ evidence_links: EvidenceLink[]
│    ├─ role=DIAGNOSIS → {run_id}-diagnosis-review-packet.json
│    └─ role=PRIMARY/SUPPORTING → collected evidence artifacts
└─ events: IncidentEvent[]
     ├─ EVIDENCE_COLLECTION_STARTED (loop started)
     ├─ EVIDENCE_ARTIFACT_ATTACHED (review packet linked)
     └─ (future) DIAGNOSIS_LOOP_COMPLETED / DIAGNOSIS_LOOP_FAILED
```

### EvidenceRole for diagnosis artifacts (target)

**Status:** `DIAGNOSIS` role is a target enum value; not yet implemented in code.

The `DIAGNOSIS` role will be added to `EvidenceRole` for diagnosis review packets:

| Role | Description |
|------|-------------|
| `DIAGNOSIS` (target) | Diagnosis review packet from automatic or manual diagnosis loop |

## Loop run metadata

### Path pattern

`runs/health/external-analysis/{run_id}-diagnosis-loop-{incident_id}.json`

### Fields

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

### Safety properties in metadata

| Field | Value | Meaning |
|-------|-------|---------|
| `read_only` | `true` | No kubectl write, no mutation |
| `review_required_before_any_action` | `true` | Advisory only, not permission |
| `no_remediation_attempted` | `true` | No remediation claims |

## Diagnosis review packet

### Path pattern

`runs/health/external-analysis/{run_id}-diagnosis-review-packet.json`

### Content

The review packet is a bounded JSON artifact containing:
- Diagnostic observations
- Suggested next steps (advisory only)
- Evidence references
- Confidence levels
- Missing information requests

**The packet is read-only evidence, never an action mandate.**

## Failure/unavailable states

| State | Description |
|-------|-------------|
| `no_review_packet` | No diagnosis review packet exists for this incident |
| `ineligible_incident` | Incident not in eligible state (OPEN, COLLECTING_EVIDENCE, INVESTIGATING) |
| `budget_exhausted` | Per-run budget limits reached (10 incidents/run) |
| `malformed_artifact` | Review packet exists but is malformed |

## Configuration

Hardcoded safe defaults:
- `max_incidents_per_run = 10`
- `max_passes_per_incident = 1`
- `max_checks_per_pass = 5`
- `write_stop_path_packets = True`
- `write_ineligible_packets = False`

## Observability

Health loop logs include:
- `automatic-diagnosis` component events
- `automatic_diagnosis_enabled` flag
- `incidents_processed`, `incidents_eligible`, `incidents_skipped`
- `total_review_packets_written`

No raw case files or artifact contents are logged.

## Incident Detail API

Review packet summaries are surfaced in the incident detail API response:

```json
{
  "automatic_diagnosis_review": {
    "available": true,
    "artifact_type": "diagnosis-loop-review-packet",
    "artifact_name": "auto-incident-123-20260619074500-diagnosis-review-packet.json",
    "run_id": "auto-incident-123-20260619074500",
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
}
```

When no packet exists or is malformed:

```json
{
  "automatic_diagnosis_review": {
    "available": false,
    "unavailable_reason": "no_review_packet"
  }
}
```

### Safety properties

The incident detail API projection:
- Exposes metadata only (not raw packet contents)
- Shows artifact filename only (not absolute paths)
- Bounded string fields (max lengths enforced)
- `read_only` is always `true`
- `review_required_before_any_action` is always `true`
- `no_remediation_attempted` is always `true`

## Review Handoff

Incident detail provides a bounded handoff endpoint for the latest automatic diagnosis review packet.

### Endpoint

```bash
GET /api/incidents/{incident_id}/automatic-diagnosis-review/handoff
```

### Response (Available)

```json
{
  "available": true,
  "incident_id": "incident-123",
  "artifact_type": "diagnosis-loop-review-packet",
  "artifact_name": "auto-incident-123-20260619074500-diagnosis-review-packet.json",
  "run_id": "auto-incident-123-20260619074500",
  "generated_at": "2026-06-19T07:45:00+00:00",
  "format": "markdown",
  "content": "# Automatic diagnosis review packet\n\n...",
  "content_sha256": "abc123def456...",
  "read_only": true,
  "review_required_before_any_action": true,
  "no_remediation_attempted": true
}
```

### Response (Unavailable)

```json
{
  "available": false,
  "unavailable_reason": "no_review_packet"
}
```

### Safety properties

The handoff endpoint:
- Provides metadata-only read-only content (not raw packet contents)
- Shows artifact filename only (not absolute paths)
- Bounded content (16 KiB max)
- Validated for forbidden terms (secrets, action-control fields, etc.)
- Explicit read-only/review-required/no-remediation language
- Content SHA256 for integrity verification

## UI Integration

The incident detail UI includes a "Copy review packet" control that:
- Fetches the handoff endpoint
- Copies bounded markdown content to clipboard
- Falls back to download if clipboard unavailable
- Shows safe unavailable/error states
- Does not expose action controls or raw artifacts

## Future timeline events

When the incident-scoped check model is implemented, the following `IncidentEventType` values should be added:

- `DIAGNOSIS_LOOP_STARTED` — Automatic diagnosis loop started for incident
- `DIAGNOSIS_LOOP_COMPLETED` — Automatic diagnosis loop completed successfully
- `DIAGNOSIS_LOOP_FAILED` — Automatic diagnosis loop failed
- `LLM_DIAGNOSIS_GENERATED` — LLM diagnosis completed (for manual/auto diagnosis)
- `DIAGNOSIS_FAILED` — LLM diagnosis failed

## Non-goals

- **Autonomous remediation** — Forbidden
- **Kubernetes mutation** — Forbidden
- **Unbounded evidence collection** — Hard budget limits enforced
- **LLM call execution** — No external LLM calls in automatic mode
- **Replacing manual diagnosis** — Manual diagnosis loop remains available

## References

- [docs/data-model/incidents.md](../data-model/incidents.md) — Incident aggregate root
- [docs/data-model/next-checks.md](../data-model/next-checks.md) — Check execution model
- [docs/data-model/review-packets.md](../data-model/review-packets.md) — Review packet semantics
# Automatic Diagnosis Loop Evidence Collection

## Overview

The automatic diagnosis loop evidence collector is an opt-in feature that automatically collects bounded read-only diagnosis evidence packets for eligible incidents during the health loop run.

## Activation

Enable via environment variable:

```bash
export K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true
```

Default is **disabled** for safety.

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

The review packet is **evidence only** - it must not be interpreted as permission to act.

## Review Packet Handoff

Find packets for an incident:

```bash
python scripts/collect_diagnosis_review_packet.py --incident-id <incident_id>
```

Review packets are stored in `runs/health/external-analysis/`.

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

### Safety Properties

The incident detail API projection:
- Exposes metadata only (not raw packet contents)
- Shows artifact filename only (not absolute paths)
- Bounded string fields (max lengths enforced)
- `read_only` is always `true`
- `review_required_before_any_action` is always `true`
- `no_remediation_attempted` is always `true`

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

### Safety Properties

The handoff endpoint:
- Provides metadata-only read-only content (not raw packet contents)
- Shows artifact filename only (not absolute paths)
- Bounded content (16 KiB max)
- Validated for forbidden terms (secrets, action-control fields, etc.)
- Explicit read-only/review-required/no-remediation language
- Content SHA256 for integrity verification

### UI Integration

The incident detail UI includes a "Copy review packet" control that:
- Fetches the handoff endpoint
- Copies bounded markdown content to clipboard
- Falls back to download if clipboard unavailable
- Shows safe unavailable/error states
- Does not expose action controls or raw artifacts

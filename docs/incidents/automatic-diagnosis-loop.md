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

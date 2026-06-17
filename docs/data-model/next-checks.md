# Next-check and manual promotion flow

**See also**: [Next-check-to-incident mapping contract](./next-check-mapping.md) for detailed artifact inventory and mapping classification.

## Purpose

Document the current next-check/manual promotion flow and the target incident-scoped mapping.

## Current reality

### Next-check planning artifacts

The planner evaluates suggested `nextChecks` from review enrichment and writes a `purpose: next-check-planning` artifact (`runs/health/external-analysis/{run_id}-next-check-plan.json`).

Each entry records:
- `description`, `target_cluster`, `source_reason`, `expected_signal`
- `suggested_command_family` (kubectl-logs, kubectl-describe, kubectl-get, etc.)
- `safe_to_automate`, `requires_operator_approval`, `risk_level`
- `estimated_cost`, `confidence`
- `gating_reason`, `duplicate_of_existing_evidence`
- Rationale fields (`normalization_reason`, `safety_reason`, etc.)

### Approval artifacts

When a planner candidate is marked `requires_operator_approval`, operators record an explicit approval action that writes a `purpose: next-check-approval` artifact.

### Promotion artifacts

Operators can promote deterministic next checks directly into the managed queue without running the planner. Each promotion writes a `purpose: next-check-promotion` artifact (`runs/health/external-analysis/{run_id}-next-check-promotion-{index}.json`).

The serialized payload mirrors the deterministic summary plus the candidate ID and promotion index.

### Execution artifacts

Manual operator actions that run safe next-check planner candidates generate a `purpose: next-check-execution` artifact (`runs/health/external-analysis/{run_id}-next-check-execution-{index}.json`).

Each execution artifact captures:
- Source planner payload
- Candidate identity
- Target cluster/context
- Bounded `kubectl` command executed
- Status, summary, duration, captured stdout/stderr

### Global next-check queue

The global next-check queue may still be derived from run/UI index.

## Target direction

### Mapping to incident-scoped concepts

```
Before:
Run / Review / Enrichment
→ next_check_plan
→ approval / promotion
→ next_check_execution artifact

Target:
Incident
→ IncidentSuggestedCheck
→ IncidentCheckExecution
→ EvidenceArtifact / EvidenceLink
→ IncidentEvent timeline
```

### IncidentSuggestedCheck (future)

Maps from current `NextCheck` planning artifacts. The UI would display suggested checks attached to the incident rather than run-scoped.

### IncidentCheckExecution (future)

Maps from current manual promotion/execution artifacts. Execution results would link to `EvidenceArtifact` and `EvidenceLink`.

### IncidentEvent timeline (future)

Promotion/execution should append `IncidentEvent` entries to the incident timeline for explainability.

## Compatibility bridge

- **Keep current artifacts as compatibility/evidence inputs.**
- **Do not delete existing next-check artifacts.**
- **Do not claim `IncidentSuggestedCheck` or `IncidentCheckExecution` are implemented unless they actually exist in code.**

Current next-check artifacts remain valid and continue to work.

## UI integration

### Suggested checks compatibility projection

The Incident detail view now includes a read-only "Suggested checks" section that renders the `suggested_checks` field from `IncidentDetailPayload`.

**Current state:**
- `IncidentDetailPayload.suggested_checks` returns an empty list by default
- No reliable next-check-to-incident mapping exists today (next-check artifacts are run-scoped, not incident-scoped)
- When populated, suggestions display: title, rationale, source, risk_level, status, artifact_id, run_id

**UI behavior:**
- Empty state: "No suggested checks linked to this incident yet."
- Populated state: Read-only list with no execution, promotion, or remediation buttons
- Hard UI boundary: No "Run", "Execute", "Promote", "Apply", "Remediate" buttons

**Future work:**
- Implement next-check-to-incident mapping via incident_id, source_candidate_id, entity identity, run_id, or latest_snapshot_bundle_id
- Populate `suggested_checks` when reliable mapping becomes available
- Do NOT implement check execution or manual promotion in this UI

## Safety constraints

- **operator approval remains required for risky or mutating work.**
- **no autonomous remediation.**

Next-check planning is advisory. All execution requires explicit operator action.

## Batch execution

Operators can execute eligible next-check candidates in batch via `scripts/run_batch_next_checks.py`.

Eligibility constraints:
- `safeToAutomate` must be true
- Must have a valid `suggestedCommandFamily`
- Must not have already been executed in this run
- Must not require operator approval unless `approvalStatus` is "approved"
- Must not be marked as `duplicateOfExistingEvidence`

The script writes standard `purpose: next-check-execution` artifacts.

## Usefulness review loop

After batch execution, operators can evaluate the usefulness of executed checks:

1. **Export:** `scripts/export_next_check_usefulness_review.py` collects execution artifacts and writes review JSON.
2. **Review:** Operators classify each entry (`useful`, `partial`, `noisy`, `empty`) and add summaries.
3. **Import:** `scripts/import_next_check_usefulness_feedback.py` writes classifications back into execution artifacts.

This closes the feedback cycle: health runs produce candidates, batch execution runs them, usefulness review improves recommendation quality.

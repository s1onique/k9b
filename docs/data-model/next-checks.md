# Next-check and manual promotion flow

**See also**: [Next-check-to-incident mapping contract](./next-check-mapping.md) for detailed artifact inventory and mapping classification.

## Purpose

Document the current next-check/manual promotion flow and the **incident-scoped target model**.

**Key principle:** Suggested checks, check executions, and evidence artifacts are **incident-scoped concepts**. Current artifacts are transitional; they map to the target incident model.

## Incident-scoped target model

```
Incident (aggregate root)
├─ signals: IncidentSignal[]
├─ suggested_checks: IncidentSuggestedCheck[]
├─ check_executions: IncidentCheckExecution[]
├─ evidence_links: EvidenceLink[]
│    └─ artifact_id → EvidenceArtifact
├─ review_packet: ReviewPacketState
└─ events: IncidentEvent[]
```

| Target concept | Maps from | Status |
|---------------|-----------|--------|
| `IncidentSuggestedCheck` | `next-check-plan` artifacts | Target |
| `IncidentCheckExecution` | `next-check-promotion` + `next-check-execution` artifacts | Target |
| `EvidenceArtifact` | Check result data | Target |
| `IncidentEvent` | Promotion/execution timeline events | Target |

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
- **Linkage fields** (incident_id, source_candidate_id, etc.) for incident mapping

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

## Incident-scoped mapping

### Artifact-to-incident linkage

Next-check artifacts are linked to incidents via:

| Linkage method | Status | Classification |
|---------------|--------|----------------|
| Direct `incident_id` match in candidate | **SAFE** | Deterministic |
| `run_id` + `source_candidate_id` match | Conditionally Safe | Depends on uniqueness |
| Complete entity identity (4 fields) | Conditionally Safe | Depends on uniqueness |
| Title text similarity | **UNSAFE** | Not deterministic |
| LLM summary similarity | **UNSAFE** | Not deterministic |

See [next-check-mapping.md](./next-check-mapping.md) for full linkage contract.

### UI integration

The Incident detail view includes a "Suggested checks" section:

**SAFE population source:**
- Only candidates where `linkage_status == "linked"` AND `incident_id == incident.incident_id`
- All other candidates (partial, unlinked, old, text-derived) are ignored
- No partial mapping, text similarity, or LLM-derived linkage

**UI behavior:**
- Empty state: "No suggested checks linked to this incident yet."
- Populated state: Read-only list with no execution, promotion, or remediation buttons
- Hard UI boundary: No "Run", "Execute", "Promote", "Apply", "Remediate" buttons

## Compatibility bridge

| Current pattern | Target pattern | Notes |
|-----------------|----------------|-------|
| `next-check-plan` artifacts | `IncidentSuggestedCheck` | Target: incident-scoped check suggestions |
| `next-check-approval` artifacts | Operator approval in `IncidentCheckExecution` | Target: incident-scoped approval |
| `next-check-promotion` artifacts | `IncidentCheckExecution.status=accepted` | Target: promotion tracking |
| `next-check-execution` artifacts | `IncidentCheckExecution` with `EvidenceArtifact` | Target: execution + evidence |
| Run-scoped plan artifacts | Incident-grouped suggestions | Current: via linkage fields |

**Compatibility:** Current artifacts remain valid and continue to work. The target model provides a unified incident-scoped view.

**Do not claim `IncidentSuggestedCheck` or `IncidentCheckExecution` are implemented unless they actually exist in code.**

## Safety constraints

- **operator approval remains required for risky or mutating work.**
- **no autonomous remediation.**
- **no Kubernetes mutation.**

Next-check planning is advisory. All execution requires explicit operator action.

### Safety boundary table

| Action | k9b executes? | Notes |
|--------|---------------|-------|
| Read-only kubectl (logs, describe, get) | **No** | k9b only recommends; operators execute |
| Mutating kubectl (apply, delete, patch, create, scale) | **No** | External human/operator procedure only |
| Helm operations (install, upgrade, rollback) | **No** | External human/operator procedure only |
| Cluster configuration changes | **No** | External human/operator procedure only |
| Remediation execution | **No** | System is advisory only |

**Product boundary:** k9b never executes mutating operations. All create, update, patch, delete, and scale verbs are outside k9b's scope and require external human/operator procedure.

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

## Future timeline events

When `IncidentSuggestedCheck` and `IncidentCheckExecution` are implemented, the following `IncidentEventType` values should be added:

- `SUGGESTED_CHECK_CREATED` — New suggested check added to incident
- `CHECK_ACCEPTED` — Operator accepted suggested check
- `CHECK_PROMOTED` — Check promoted to execution queue
- `CHECK_EXECUTED` — Check execution completed
- `CHECK_FAILED` — Check execution failed

These events will provide explainability for the check lifecycle within the incident timeline.

## Non-goals

- **Autonomous execution without approval** — Forbidden
- **Kubernetes mutation** — Forbidden
- **Replacement of current artifacts** — Current artifacts remain valid
- **LLM-derived incident linkage** — Unsafe, not implemented

## References

- [incidents.md](./incidents.md) — Incident aggregate root documentation
- [next-check-mapping.md](./next-check-mapping.md) — Detailed mapping contract
- [review-packets.md](./review-packets.md) — Review packet semantics
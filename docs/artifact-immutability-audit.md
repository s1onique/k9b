# Artifact Immutability Audit

**Status**: Complete  
**Epic**: Enforce artifact immutability across the project  
**Date**: 2026-04-22  
**Evidence level**: Code-path confirmed (not filename intuition)

---

## 1. Summary

### Current Immutability Posture

The k9b repository exhibits a **partial immutability posture** with significant mutable pockets. Core deterministic artifacts (snapshots, assessments, drilldowns, comparisons, triggers, reviews, notifications, diagnostic pack ZIPs) are written once and not subsequently mutated. However, several artifact families are intentionally or incidentally mutable, creating ambiguity in the artifact-first invariant.

**Immutable by design (core evidence artifacts):**
- Snapshots, assessments, drilldowns, comparisons, triggers, reviews, notifications
- Diagnostic pack ZIPs (archival)
- External-analysis initial artifacts (written once by adapters)
- Feedback run artifacts
- Next-check artifacts (plan, execution, approval, promotion)
- Alertmanager artifacts (snapshots, compact, sources, relevance reviews)

**Mutable by design:**
- Proposals (lifecycle state mutation via CLI)
- Usefulness feedback (write-back to external-analysis artifacts)
- `history.json` (cross-run aggregate overwrite)
- `ui-index.json` (derived projection rebuild)
- `alertmanager-source-registry.json` (cross-run intent state)
- Latest diagnostic-pack mirror (regenerated derived artifact)
- Usefulness summary (rebuilt on re-import)

**Mixed:**
- External-analysis artifacts with usefulness_class (immutable initial content + mutable feedback field)
- Alertmanager source override artifacts (per-run mutable state)

### Top 5 Highest-Risk Mutable or Ambiguous Families

1. **Proposals** (`runs/health/proposals/*.json`) — Direct in-place write mutation via CLI handlers with no backup mechanism
2. **External-analysis with usefulness feedback** — `artifact_id`-bearing immutable artifacts receiving mutable write-back
3. **`history.json`** — Cross-run aggregate state stored in overwrite-in-place JSON
4. **`alertmanager-source-registry.json`** — Cross-run intent state with no version control
5. **Latest diagnostic-pack mirror** (`latest/review_bundle.json`, `latest/review_input_14b.json`) — Regenerated derived files that overwrite previous state

### Strongest Architectural Insight

The immutability boundary is **not along the artifact/derived-artifact seam** but along the **artifact content vs. artifact metadata seam**. Some artifacts with `artifact_id` (external-analysis) accept mutable metadata write-back (usefulness feedback), while some artifacts without `artifact_id` (proposals) are fully mutable. The current model conflates:
- Immutable diagnostic evidence (should not change)
- Mutable operational feedback (usefulness, approvals)
- Mutable aggregate state (history, UI index)
- Mutable intent state (registry, overrides)

### Recommended Highest-Leverage Enforcement Seam

**Separate usefulness feedback from execution artifacts.** Currently, the UI server (`_handle_usefulness_feedback`) reads, mutates, and writes back to the original execution artifact. The correct pattern (already used for Alertmanager relevance feedback) is to write a separate review artifact that references the original. This would:
1. Preserve immutable execution artifacts
2. Create an auditable feedback trail
3. Enable multi-operator review without conflict
4. Align with the alertmanager relevance feedback pattern

---

## 2. Artifact Inventory Table

| Family | Example Path Pattern | Producer Modules/Functions | Primary Consumers | Identity Model | Classification | Current Write Behavior | Mutable? | Notes / Ambiguity |
|--------|---------------------|---------------------------|-------------------|----------------|----------------|------------------------|----------|-------------------|
| Snapshots | `runs/health/snapshots/{run_id}-{label}-{timestamp}.json` | `health/loop.py`: `collect_cluster_snapshot`, `_write_json` | `build_health_assessment`, `compare_snapshots`, UI | Filename identity (`run_id` embedded) | 1. Immutable artifact instance | Write-once via `_write_json` | No | Deterministic; same inputs produce identical content |
| Assessments | `runs/health/assessments/{run_id}-{label}.json` | `health/loop.py`: `build_health_assessment`, `write_assessment_artifact` | Reviews, proposals, UI | Filename identity (`run_id` embedded) | 1. Immutable artifact instance | Write-once per cluster per run | No | Per-cluster health synthesis |
| Drilldowns | `runs/health/drilldowns/{run_id}-{label}.json` | `health/loop.py`: `DrilldownCollector.collect` | Reviews, UI, `assess-drilldown` CLI | Filename identity (`run_id` embedded) | 1. Immutable artifact instance | Write-once per trigger | No | Deterministic kubectl evidence collection |
| Comparisons | `runs/health/comparisons/{run_id}-{primary}-vs-{secondary}-comparison.json` | `health/loop.py`: `compare_snapshots` | Triggers, reviews, UI | Filename identity | 1. Immutable artifact instance | Write-once per comparison pair | No | Peer diff artifact |
| Triggers | `runs/health/triggers/{run_id}-{primary}.json` | `health/loop.py`: `ComparisonTriggerArtifact` serialization | Reviews, UI, proposal generation | Filename identity + optional `artifact_id` | 1. Immutable artifact instance | Write-once per trigger | No | Comparison trigger decision artifact |
| Reviews | `runs/health/reviews/{run_id}-review.json` | `health/loop.py`: `build_health_review` | UI, proposals, diagnostic packs | Filename identity (`run_id` embedded) | 1. Immutable artifact instance | Write-once per run | No | Aggregation of run state |
| Notifications | `runs/health/notifications/{run_id}-{purpose}.json` | `health/notifications.py`: `write_notification_artifact` | UI, alert delivery | Filename identity | 1. Immutable artifact instance | Write-once per notification | No | Event recording |
| Proposals | `runs/health/proposals/{proposal_id}.json` | `health/loop.py`: `generate_proposals_from_review`, CLI handlers | UI, `check-proposal`, `render_proposal_patch` | `proposal_id` | 3. Mutable intent / workflow state store | CLI handlers write updated lifecycle via `write_text` | **Yes** | Lifecycle status mutation via CLI |
| External-analysis (initial) | `runs/health/external-analysis/{run_id}-{purpose}.json` | `external_analysis/artifact.py`: `write_external_analysis_artifact` | UI, diagnostic packs | `artifact_id` + filename | 1. Immutable artifact instance | Write-once per invocation | No (initial) | Provider output artifact |
| External-analysis (with feedback) | Same as above | UI server + `import_next_check_usefulness_feedback.py` | UI | `artifact_id` + filename | 4. Mixed / unclear | `_handle_usefulness_feedback` writes back to artifact | **Yes** (usefulness_class, usefulness_summary) | Immutable execution + mutable feedback |
| Alertmanager relevance review | `runs/health/external-analysis/{run_id}-alertmanager-review-{uuid}.json` | `ui/server.py`: `_handle_alertmanager_relevance_feedback` | UI | Filename (UUID-based) | 1. Immutable artifact instance | Write-once per review | No | Correct immutable pattern (separate artifact) |
| Alertmanager snapshots | `runs/health/external-analysis/{run_id}-alertmanager-snapshot.json` | `alertmanager_adapter.py` | UI, reviews | Filename identity | 1. Immutable artifact instance | Write-once per run | No | Alertmanager state capture |
| Alertmanager compact | `runs/health/external-analysis/{run_id}-alertmanager-compact.json` | `alertmanager_adapter.py` | UI | Filename identity | 1. Immutable artifact instance | Write-once per run | No | Compact alertmanager summary |
| Alertmanager sources | `runs/health/external-analysis/{run_id}-alertmanager-sources.json` | `alertmanager_adapter.py` | UI, registry | Filename identity | 1. Immutable artifact instance | Write-once per run | No | Source inventory |
| Next-check plan | `runs/health/external-analysis/{run_id}-next-check-plan.json` | `next_check_planner.py`: `plan_next_checks` | UI, approval flow | Filename identity + `run_id` | 1. Immutable artifact instance | Write-once per run | No | Planner advisory |
| Next-check execution | `runs/health/external-analysis/{run_id}-next-check-execution-{index}.json` | `manual_next_check.py`, batch executor | UI, usefulness review | Filename identity + `run_id` | 1. Immutable artifact instance (initial) | Write-once per execution | No (initial) | kubectl command result |
| Next-check approval | `runs/health/external-analysis/{run_id}-next-check-approval-{index}.json` | `next_check_approval.py`: `record_next_check_approval` | UI | Filename identity + `run_id` | 1. Immutable artifact instance | Write-once per approval | No | Operator approval record |
| Next-check promotion | `runs/health/external-analysis/{run_id}-next-check-promotion-{index}.json` | `deterministic_next_check_promotion.py` | UI | Filename identity + `run_id` | 1. Immutable artifact instance | Write-once per promotion | No | Deterministic queue entry |
| Alertmanager source overrides | `runs/health/external-analysis/{run_id}-alertmanager-source-overrides.json` | `ui/server.py`: `_handle_alertmanager_source_action` | UI, inventory | Filename identity | 4. Mixed / unclear | Overwrites per-run state | **Yes** | Per-run mutable; not same as registry |
| Alertmanager source registry | `runs/health/alertmanager-source-registry.json` | `alertmanager_source_registry.py`: `write_source_registry` | Discovery, inventory, UI | `cluster_context:canonical_identity` key | 3. Mutable intent / workflow state store | Overwrites cross-run state | **Yes** | Cross-run operator intent |
| history.json | `runs/health/history.json` | `health/loop.py`: `_persist_history` | Assessment regression detection | Per-cluster key | 3. Mutable aggregate state store | Full aggregate overwrite per run | **Yes** | Cross-run history; overwrites previous entries |
| ui-index.json | `runs/health/ui-index.json` | `health/ui.py`: `write_health_ui_index` | UI server, API endpoints | Derived from run artifacts | 2. Mutable alias / derived projection | Full rebuild per run (overwrites) | **Yes** | Derived read model; not source of truth |
| Diagnostic pack ZIP | `runs/health/diagnostic-packs/diagnostic-pack-{run_id}-{timestamp}.zip` | `build_diagnostic_pack.py`: `_zip_pack` | Operators, reviewers | Filename identity | 1. Immutable artifact instance | Write-once per pack | No | Archival artifact |
| Latest pack mirror | `runs/health/diagnostic-packs/latest/review_bundle.json` | `build_diagnostic_pack.py`: `_write_latest_pack_mirror` | UI, operators | Derived from run | 2. Mutable alias / derived projection | Regenerated per run (overwrites) | **Yes** | Convenience mirror; regenerated each run |
| Latest review input | `runs/health/diagnostic-packs/latest/review_input_14b.json` | `build_diagnostic_pack.py`: `_write_latest_pack_mirror` | UI, reviewers | Derived from run | 2. Mutable alias / derived projection | Regenerated per run (overwrites) | **Yes** | Convenience artifact; regenerated each run |
| Usefulness review export | `runs/health/diagnostic-packs/{run_id}/next_check_usefulness_review.json` | `export_next_check_usefulness_review.py` | UI, operators | Filename identity + `run_id` | 1. Immutable artifact instance | Write-once per export | No | Export artifact; may be re-exported |
| Usefulness summary | `runs/health/diagnostic-packs/{run_id}/usefulness_summary.json` | `import_next_check_usefulness_feedback.py` | UI, learning reports | Filename identity + `run_id` | 2. Mutable alias / derived projection | Regenerated on re-import | **Yes** | Derived summary; rebuilt on import |
| Feedback run artifacts | `runs/feedback/{run_id}-{pair}.json` | `feedback/runner.py` | Evals, comparisons | Filename identity | 1. Immutable artifact instance | Write-once per pair | No | Evaluation artifacts |

---

## 3. Mutation Candidate Table

| Family | File/Module/Function | Mutation Pattern | Classification Impact | Why It Matters | Suspected Fix Direction |
|--------|---------------------|------------------|-----------------------|----------------|-------------------------|
| Proposals | `cli_handlers.py`: `handle_check_proposal`, `handle_render_proposal_patch` | In-place `write_text` of updated lifecycle history | Mutable intent / workflow state store | No rollback mechanism; operator changes overwrite original | Write to new file with original as reference; or append-only lifecycle log |
| Usefulness feedback | `ui/server.py`: `_handle_usefulness_feedback` | Read → mutate → write back to original artifact | Mixed / unclear | `artifact_id`-bearing immutable artifact receives mutable write-back; breaks provenance audit | Write separate feedback artifact (pattern already used for Alertmanager relevance) |
| Usefulness import | `scripts/import_next_check_usefulness_feedback.py`: `_process_entry` | Same as above; batch write-back | Mixed / unclear | Script imports batch feedback and writes back to artifacts | Separate feedback artifact per entry |
| history.json | `health/loop.py`: `_persist_history` | Full aggregate overwrite (read-modify-write of per-cluster entries) | Mutable aggregate state store | Previous run state silently replaced; no diff/audit trail | Append-only log with derived current snapshot; or separate per-run history files |
| ui-index.json | `health/ui.py`: `write_health_ui_index` | Full rebuild and overwrite | Mutable alias / derived projection | Rebuilt from source artifacts on every write; not truly immutable projection | Already derived; no fix needed, but should be documented as derived |
| Latest pack mirror | `build_diagnostic_pack.py`: `_write_latest_pack_mirror` | Regenerates `review_bundle.json` and `review_input_14b.json` | Mutable alias / derived projection | Overwrites previous run's derived artifacts | Document as regenerated derived; or version with timestamps |
| Alertmanager source registry | `alertmanager_source_registry.py`: `write_source_registry` | Full registry overwrite (not append) | Mutable intent / workflow state store | Cross-run intent state updated in-place; operator actions not auditable by run | Append-only registry log; or per-action artifact with lookup |
| Alertmanager source overrides | `alertmanager_source_actions.py`: `write_source_overrides` | Per-run override overwrite | Mutable intent / workflow state store | Per-run state replaces previous; not composable across runs | Run-scoped artifact is correct; should be derived from registry |
| Next-check approval | `next_check_approval.py`: `record_next_check_approval` | Writes new approval artifact | (Mostly correct pattern) | One artifact per approval is correct; existing design is fine | No fix needed |
| Alertmanager relevance review | `ui/server.py`: `_handle_alertmanager_relevance_feedback` | Writes new review artifact | (Correct immutable pattern) | Already uses correct pattern: separate artifact, no mutation | No fix needed |

---

## 4. Classification Notes

### 4.1 `history.json`

**Classification**: 3. Mutable aggregate state store

**Reasoning**:
- Written via `_persist_history` in `health/loop.py`
- Overwrites previous run's per-cluster entries with current run's state
- No append-only semantics; previous state is lost
- Contains cross-run aggregate data (latest observed state per cluster)
- Used for regression detection in `build_health_assessment`

**Evidence**:
```python
# health/loop.py
def _persist_history(self, history: dict[str, HealthHistoryEntry], history_path: Path) -> None:
    data = {cluster_id: entry.to_dict() for cluster_id, entry in history.items()}
    _write_json(data, history_path)  # Overwrites entire file
```

**Why this is mutable aggregate state, not immutable artifact**:
- Stores the *latest known state* of each cluster, not a point-in-time observation
- Represents aggregate operational state (current baseline for comparison) rather than diagnostic evidence
- Cannot reconstruct prior run's view of a cluster from this file alone
- This is distinct from "intent" stores (like the alertmanager registry) which record operator decisions

### 4.2 `ui-index.json`

**Classification**: 2. Mutable alias / derived projection

**Reasoning**:
- Rebuilt from source artifacts by `write_health_ui_index` on each write
- Contains pointers to immutable artifacts, not the artifacts themselves
- Overwritten on every health run and on operator actions (approvals, promotions)
- Served as the primary read model for the UI server

**Evidence**:
```python
# health/ui.py
def write_health_ui_index(...) -> Path:
    index_path = output_dir / "ui-index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index_path
```

**Why this is mutable, not immutable**:
- Rebuilt from scratch; not append-only
- Represents "current view" rather than "point-in-time snapshot"
- UI depends on it being up-to-date

**Why this is acceptable**:
- It is explicitly a derived projection, not a source of truth
- Source artifacts remain immutable
- Should be documented as "derived, rebuilt on write"

### 4.3 `alertmanager-source-registry.json`

**Classification**: 3. Mutable intent / workflow state store

**Reasoning**:
- Persists cross-run operator intent (promote/disable sources)
- Overwrites previous registry entries when operators take new actions
- Entry `updated_at` timestamps are updated, but old values are lost
- No append-only audit trail of operator decisions

**Evidence**:
```python
# alertmanager_source_registry.py
def write_source_registry(registry: AlertmanagerSourceRegistry, health_root: Path) -> Path:
    path.write_text(json.dumps(registry.to_dict(), indent=2), encoding="utf-8")  # Full overwrite
```

**Why this is mutable intent state**:
- Stores operator decisions that should persist across runs
- Current implementation updates in-place, losing history
- Represents *intent* (what operator wants) not *evidence* (what system observed)

**Ambiguity**:
- Not a diagnostic artifact (no `artifact_id`)
- Not purely derived (represents operator choices, not system state)
- Cross-run by design, making immutability harder to define

### 4.4 Proposal Artifacts

**Classification**: 3. Mutable intent / workflow state store

**Reasoning**:
- CLI handlers (`cli_handlers.py`) read, mutate, and write proposals back to the same file
- `lifecycle_history` is appended/modified in place
- `proposal_id` provides identity, but the artifact is mutable
- No mechanism to preserve original proposal state

**Evidence**:
```python
# cli_handlers.py
args.proposal.write_text(json.dumps(updated.to_dict(), indent=2), encoding="utf-8")
```

**Why this is mutable intent state**:
- Represents workflow state (proposal lifecycle: pending → checked → accepted/rejected)
- Operator actions modify the proposal artifact directly
- Original proposal state is overwritten

**Distinction from immutable artifacts**:
- Proposals are *recommendations*, not *evidence*
- They represent the system's suggestion, which can be reviewed and updated
- However, the current implementation lacks audit trail

### 4.5 External-Analysis Artifacts with Usefulness Feedback

**Classification**: 4. Mixed / unclear

**Reasoning**:
- Initial write creates immutable artifact with `artifact_id`
- Subsequent operator feedback (usefulness_class, usefulness_summary) is written back to the same artifact
- The artifact has schizophrenic immutability: some fields immutable, some mutable

**Evidence**:
```python
# ui/server.py _handle_usefulness_feedback
artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
artifact_data["usefulness_class"] = usefulness_class.value
artifact_data["usefulness_summary"] = usefulness_summary
artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")
```

**Why this is mixed**:
- `artifact_id` suggests immutability
- `usefulness_class`, `usefulness_summary` are mutable metadata
- Execution output (the actual diagnostic evidence) remains immutable

**Contrast with correct pattern**:
Alertmanager relevance feedback already uses the correct pattern:
```python
# ui/server.py _handle_alertmanager_relevance_feedback
# Writes a NEW review artifact instead of mutating the original
review_path = external_analysis_dir / review_filename
review_path.write_text(json.dumps(review_artifact, indent=2), encoding="utf-8")
```

### 4.6 Latest Diagnostic-Pack Mirror

**Classification**: 2. Mutable alias / derived projection

**Reasoning**:
- `review_bundle.json` and `review_input_14b.json` are regenerated from current run state
- Each run overwrites the previous version
- Contains derived summaries, not original evidence

**Evidence**:
```python
# build_diagnostic_pack.py _write_latest_pack_mirror
bundle_path.write_text(json.dumps(review_bundle, indent=2), encoding="utf-8")  # Overwrites
input_path.write_text(json.dumps(review_input, indent=2), encoding="utf-8")  # Overwrites
```

**Why this is mutable derived projection**:
- Convenience artifact for quick access
- Not the authoritative source (source artifacts are in subdirectories)
- Rebuilt on every run

**Why this is acceptable**:
- Explicitly documented as "latest mirror"
- Source artifacts remain immutable
- ZIP archives provide point-in-time snapshots

---

## 5. Gap List

### 5.1 Families Missing Immutable Instance Identity

| Family | Current Identity | Gap |
|--------|-----------------|-----|
| history.json | Per-cluster key | No unique identifier per history entry; cannot reference a specific run's view |
| ui-index.json | None (derived) | No identity; rebuilt from scratch |
| Proposals | `proposal_id` | Has identity but mutable content |
| Alertmanager source registry entries | `cluster_context:canonical_identity` | No `artifact_id`; no per-action artifact |
| Alertmanager source overrides | Per-run filename | No version; overwritten each run |

### 5.2 Families with `artifact_id` but Still Mutable Storage Semantics

| Family | Has artifact_id | Still Mutable | Mechanism |
|--------|----------------|---------------|-----------|
| External-analysis with usefulness | Yes | Yes | Write-back to `usefulness_class`, `usefulness_summary` |
| Triggers | Optional | No | `artifact_id` is optional for backward compat |

### 5.3 API/UI Surfaces Likely Hiding Exact Artifact Identity

| Surface | Resolution Method | Hides Identity? |
|---------|-------------------|------------------|
| `/api/runs` | Latest run from `ui-index.json` | Yes (no run_id, no artifact_id) |
| `/api/run/{run_id}` | Run-specific artifact lookup | No (run_id explicit) |
| `/api/runs/{run_id}/alertmanager-sources/{source_id}/action` | Latest registry state | Yes (no artifact_id for registry entry) |
| Diagnostic pack download | Latest mirror | Yes (no version, just "latest") |
| Next-check queue | Aggregated from plan + approvals | Yes (no artifact_id for individual entries) |

### 5.4 Conflation of Logical Identity and Immutable Instance Identity

| Concept | Logical Identity | Immutable Instance Identity | Conflated? |
|---------|-----------------|---------------------------|------------|
| Proposal | `proposal_id` | None (mutable content) | Yes |
| External-analysis execution | Filename path | `artifact_id` | Partially (feedback mutates) |
| History entry | Cluster label | None | Yes |
| Alertmanager registry entry | `cluster_context:canonical_identity` | None | Yes |

---

## 6. Recommended Next Step

**Choose: Separate usefulness feedback into dedicated review artifacts (pattern alignment)**

**Rationale**:
1. **Immediate safety**: Removes mutable write-back from `artifact_id`-bearing artifacts
2. **Pattern alignment**: Already implemented correctly for Alertmanager relevance feedback
3. **Low risk**: Does not change deterministic core behavior
4. **High value**: Creates auditable feedback trail without mutating evidence
5. **Enables future work**: Multi-operator review, feedback analytics, replay

**Scope**:
- `ui/server.py`: `_handle_usefulness_feedback` → create new `usefulness-feedback-{uuid}.json` artifact instead of mutating execution artifact
- `health/ui.py`: Update UI index projection to include linked feedback artifacts
- `scripts/import_next_check_usefulness_feedback.py`: Write feedback artifacts instead of mutating originals
- Documentation: Document the immutable evidence + mutable feedback pattern

**Not in scope for this step**:
- Proposal lifecycle refactoring (separate epic)
- Alertmanager registry audit trail (separate epic)
- history.json refactoring (separate epic)

**Tradeoffs**:
- Slight increase in artifact count (one per feedback event)
- UI needs to link feedback artifacts to execution artifacts
- Existing feedback data requires migration or backward-compatible read

---

## 7. Verification Notes

### Discovery Commands Used

```bash
# Artifact family discovery
find runs/health -type f -name "*.json" | head -50

# Mutation pattern discovery
grep -r "\.write_text\|\.write_bytes\|json\.dump\|open.*\"w\"" src/ --include="*.py"
grep -r "history\.json\|ui-index\.json\|alertmanager-source-registry" src/ --include="*.py"
grep -r "usefulness\|UsefulnessClass" src/ --include="*.py"
grep -r "alertmanager_source_actions\|source_override" src/ --include="*.py"
grep -r "proposal.*write\|write_proposal" src/ --include="*.py"
grep -r "_persist_history\|write_source_registry" src/ --include="*.py"

# Script mutation discovery
grep -r "import.*usefulness\|usefulness.*import" scripts/ --include="*.py"
grep -r "_write_latest_pack_mirror\|write_latest_pack" scripts/ --include="*.py"
```

### Code Changes

**No code changes were made during this audit.**

The audit was purely investigative, gathering evidence through:
1. Static code analysis of source files
2. Search patterns for mutation mechanisms
3. Schema and documentation review
4. File structure examination

### Evidence Files Examined

| File | Lines Examined | Purpose |
|------|---------------|---------|
| `src/k8s_diag_agent/health/loop.py` | Full (5206) | Core artifact write paths, history persistence |
| `src/k8s_diag_agent/health/ui.py` | Full (2960) | UI index rebuild, derived projections |
| `src/k8s_diag_agent/external_analysis/alertmanager_source_registry.py` | Full (535) | Cross-run registry mutation |
| `src/k8s_diag_agent/external_analysis/alertmanager_source_actions.py` | Full (227) | Per-run override mutation |
| `src/k8s_diag_agent/ui/server.py` | Full (4193) | HTTP handlers, usefulness feedback, source actions |
| `src/k8s_diag_agent/feedback/runner.py` | Full (478) | Feedback artifact patterns |
| `scripts/import_next_check_usefulness_feedback.py` | Full (798) | Batch feedback import mutation |
| `scripts/build_diagnostic_pack.py` | Full (1613) | Latest mirror regeneration |
| `docs/data-model.md` | Full (173) | Contract documentation |

---

## 8. Assumptions / Unknowns

### Unresolved Ambiguities

1. **Proposal lifecycle semantics**: Not fully traced whether `proposal_id` is expected to be immutable or mutable. CLI handlers clearly mutate, but the design intent is unclear from documentation.

2. **Alertmanager registry update frequency**: Unclear if operators expect per-action artifacts or in-place update. Current design supports both but only implements in-place.

3. **history.json migration path**: If history were refactored to append-only, backward compatibility with existing files is a concern.

4. **Usefulness feedback backward compatibility**: If feedback is moved to separate artifacts, existing artifacts with `usefulness_class` fields need migration or dual-read logic.

5. **Latest mirror retention**: No policy exists for how long "latest" artifacts should be retained vs. when they become stale.

6. **Proposal promotion atomicity**: If proposals are promoted/checked multiple times, the write-back pattern creates potential race conditions in multi-operator scenarios.

### Paths Needing Deeper Follow-Up

1. **CLI handler concurrency**: Do proposal CLI handlers need locking when multiple operators run concurrently?

2. **UI server thread safety**: Does `_handle_usefulness_feedback` handle concurrent writes to the same artifact?

3. **Batch import idempotency**: Does `import_next_check_usefulness_feedback` correctly handle re-imports of the same feedback?

4. **Alertmanager registry reconciliation**: How does the system handle conflicts between discovery and registry state?

5. **Diagnostic pack versioning**: Should pack builds be versioned, or is "latest" sufficient for the use case?

6. **Proposal replay semantics**: If a run is replayed, do proposals get new IDs or reuse old ones?

---

## Epic Closure Status

**Status**: Complete

**Date**: 2026-04-23

### Work Items Completed

All five highest-risk mutable artifact families have been addressed:

1. **Proposals** — Immutable base proposal artifacts plus immutable lifecycle event artifacts now provide the audit trail; current proposal state is derived from event history with legacy fallback
2. **External-analysis with usefulness feedback** — Separate review artifacts now write immutable execution artifacts
3. **`history.json`** — Immutable per-run-per-cluster fact artifacts added as audit trail
4. **Alertmanager source registry** — Immutable action artifacts provide append-only audit trail
5. **Latest diagnostic-pack mirror** — Documented as mutable convenience alias with explicit `isMirror` metadata

### Deferred Non-Goal (IM-08c.2)

The following item was explicitly deferred and is NOT part of epic closure criteria:

**Alertmanager source inventory latest-action metadata** — Surfacing the most recent action taken per source in the UI/inventory view is a UI/API enhancement that builds on the completed immutable audit trail. It does not affect artifact immutability contracts and may be addressed in a future enhancement pass.

### Verification

- All immutability-related tests pass: 251 tests across 8 test files
- Core artifact families enforce append-only semantics via `write_append_only_json_artifact`
- API/UI surfaces expose immutability metadata (`isMirror`, `sourcePackPath`, `artifactId`)

---

## Appendix: Classification Reference

| # | Classification | Definition |
|---|---------------|------------|
| 1 | Immutable artifact instance | Point-in-time diagnostic evidence; written once, never modified |
| 2 | Mutable alias / derived projection | Derived from immutable artifacts; regenerated, not mutated in-place |
| 3 | Mutable intent / workflow state store | Operator decisions, workflow state; intentionally mutable |
| 4 | Mixed / unclear | Some fields immutable, some mutable; semantics ambiguous |

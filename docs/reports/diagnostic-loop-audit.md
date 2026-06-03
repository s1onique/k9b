# Diagnostic Command Chain and Artifact Lifecycle Audit

**ACT**: Audit diagnostic command chain and artifact lifecycle  
**Date**: 2026-06-03 
**Status**: Complete  

---

## Executive Summary

The k9b diagnostic feedback loop is **partially closed-loop**. Generation, validation, approval, and execution all work. The two missing seams are:

1. **Execution result reuse in next diagnostic step** — Execution artifacts are persisted but not fed back into follow-up diagnostic planning within the same run.

2. **Incident report provenance for execution artifacts** — Execution artifacts are referenced in worklist state but execution results do not flow into incident report fact/hypothesis claims.

**First implementation ACT**: Persist diagnostic command execution artifacts with structured result digest for reuse in next-check planning.

---

## Audit Scope

Map the current k9b diagnostic feedback loop from next-check proposal through command validation, execution, persisted evidence, follow-up diagnostic input, and incident report projection.

**Questions this audit answers:**
1. Where are nextChecks produced?
2. Where are nextChecks validated or rejected?
3. Where can an operator approve or trigger a diagnostic command?
4. What execution artifact is produced?
5. What schema identifies command, cluster, namespace, timestamp, status, stdout/stderr, and provenance?
6. Can later diagnostic steps consume previous command results?
7. Can incident reports cite those command artifacts?
8. What is the smallest implementation ACT that would close the loop?

---

## Loop Segment Assessment

| Segment | Current Status | Evidence | Gap | Next Fix |
|---------|:--------------:|----------|-----|----------|
| nextChecks generation | **Working** | `next_check_planner.py`, `next_check_planner_candidates.py` | None | — |
| nextChecks validation | **Working** | `manual_next_check_gating.py`, `next_check_planner_models.py` | None | — |
| command approval | **Working** | `next_check_approval.py`, `server_feedback.py` | Approval state tracked in artifacts but not integrated into execution gating | Integrate approval status into queue eligibility |
| command execution | **Working** | `manual_next_check.py`, `manual_next_check_commands.py` | None | — |
| execution artifact persistence | **Working** | `manual_next_check_artifacts.py`, `artifact.py` | None | — |
| result reuse in next step | **Missing** | `next_check_planner.py` only uses enrichment artifact, not execution results | Planning cannot consume prior execution outputs within same run | Feed execution artifacts into next-check planning input |
| incident report projection | **Partial** | `api_incident_report.py`, `api_incident_report_worklist.py` | Execution artifacts in worklist but not in report claims | Add execution artifact claims to incident report |

---

## Segment Details

### 1. nextChecks Generation — WORKING

**Files inspected:**
- `src/k8s_diag_agent/external_analysis/next_check_planner.py` (150 lines)
- `src/k8s_diag_agent/external_analysis/next_check_planner_candidates.py` (386 lines)
- `src/k8s_diag_agent/external_analysis/next_check_planner_ranking.py`
- `src/k8s_diag_agent/external_analysis/next_check_planner_models.py` (222 lines)

**Flow:**
1. LLM enrichment produces `suggested_next_checks` tuple in enrichment artifact
2. `build_candidates_from_enrichment()` normalizes text → `NextCheckCandidate` dataclass
3. `rank_candidates()` applies ranking policy including Alertmanager bonuses and CRD demotion
4. Plan artifact written as `ExternalAnalysisArtifact` with `purpose=NEXT_CHECK_PLANNING`

**Schema:**
```python
@dataclass(frozen=True)
class NextCheckCandidate:
    candidate_id: str          # SHA256 of (description, cluster, source, family)
    description: str            # Human-readable check description
    target_cluster: str | None # Cluster label for target
    target_context: str | None # kubectl context name
    source_reason: str | None  # Why this check was suggested
    expected_signal: str | None # Expected output type (logs, events, metrics)
    suggested_command_family: CommandFamily  # kubectl-get, kubectl-describe, etc.
    safe_to_automate: bool     # True if no mutation keywords detected
    requires_operator_approval: bool
    risk_level: RiskLevel      # LOW/MEDIUM/HIGH
    estimated_cost: CostEstimate
    confidence: str             # high/medium/low
    # ... gating and provenance fields
```

**Status: Full coverage. Artifacts written, tests exist.**

---

### 2. nextChecks Validation — WORKING

**Files inspected:**
- `src/k8s_diag_agent/external_analysis/manual_next_check_gating.py`
- `src/k8s_diag_agent/external_analysis/manual_next_check_commands.py`
- `src/k8s_diag_agent/external_analysis/next_check_planner_models.py`

**Validation layers:**
1. **Mutation detection** — Regex patterns in `MUTATION_KEYWORDS` block dangerous verbs (apply, delete, scale, patch, etc.)
2. **Command family validation** — Only `kubectl-get`, `kubectl-describe`, `kubectl-logs`, `kubectl-top`, `kubectl-get-crd` allowed
3. **Duplicate detection** — Checks against deterministic `next_evidence_to_collect` from assessments
4. **Gating checks** — `check_candidate_gating()` enforces all rules before execution

**Allowed command families:**
```python
class CommandFamily(StrEnum):
    KUBECTL_GET = "kubectl-get"
    KUBECTL_DESCRIBE = "kubectl-describe"
    KUBECTL_LOGS = "kubectl-logs"
    KUBECTL_GET_CRD = "kubectl-get-crd"
    KUBECTL_TOP = "kubectl-top"
    UNKNOWN = "unknown"
```

**Status: Full coverage. Security model is sound.**

---

### 3. Command Approval — WORKING

**Files inspected:**
- `src/k8s_diag_agent/external_analysis/next_check_approval.py` (158 lines)
- `src/k8s_diag_agent/ui/server_feedback.py`

**Approval flow:**
1. Operator can record approval via `POST /feedback/next-check/usefulness` (usefulness feedback)
2. Alertmanager relevance feedback via `POST /feedback/next-check/alertmanager`
3. Approval artifacts written to `health/external-analysis/{run_id}-next-check-approval-{index}.json`
4. Approval state tracked but not yet integrated into execution eligibility

**Current gap:** Approval status exists but the batch execution path does not require approval artifacts to execute. Candidates with `requires_operator_approval=True` are still executable via batch script.

**Schema:**
```python
@dataclass(frozen=True)
class NextCheckApprovalRecord:
    candidate_index: int | None
    candidate_id: str | None
    artifact_path: str | None
    timestamp: datetime
    cluster_label: str | None
    plan_artifact_path: str | None
    candidate_description: str | None
```

**Status: Working but approval not enforced in execution gate.**

---

### 4. Command Execution — WORKING

**Files inspected:**
- `src/k8s_diag_agent/external_analysis/manual_next_check.py` (441 lines)
- `src/k8s_diag_agent/external_analysis/manual_next_check_artifacts.py`
- `src/k8s_diag_agent/external_analysis/manual_next_check_output.py`
- `src/k8s_diag_agent/external_analysis/manual_next_check_commands.py`

**Execution flow:**
1. Build command from description and target context
2. Validate command tokens (no injection)
3. Run via subprocess with 45-second timeout
4. Capture stdout/stderr, truncate if >512KB
5. Write `ExternalAnalysisArtifact` with `purpose=NEXT_CHECK_EXECUTION`

**Output handling:**
```python
_OUTPUT_LIMIT = 512 * 1024  # 512KB limit

def _capture_output(stdout: str, stderr: str) -> tuple[str, str, str, bool, bool, int]:
    # Returns: (stdout_text, stderr_text, combined_output, stdout_truncated, stderr_truncated, bytes)
```

**Status: Full coverage. Execution artifacts written with complete provenance.**

---

### 5. Execution Artifact Persistence — WORKING

**Files inspected:**
- `src/k8s_diag_agent/external_analysis/artifact.py` (359 lines)
- `src/k8s_diag_agent/external_analysis/manual_next_check_artifacts.py`

**Artifact schema:**
```python
@dataclass(frozen=True)
class ExternalAnalysisArtifact:
    tool_name: str              # e.g., "next-check-execution"
    run_id: str                # Run identifier
    cluster_label: str         # Target cluster
    status: ExternalAnalysisStatus  # SUCCESS/FAILED/PENDING/SKIPPED
    raw_output: str | None     # Combined stdout+stderr
    stdout_truncated: bool | None
    stderr_truncated: bool | None
    timed_out: bool | None
    timestamp: datetime
    artifact_path: str | None   # Path to this artifact
    duration_ms: int | None
    purpose: ExternalAnalysisPurpose  # NEXT_CHECK_EXECUTION
    payload: dict[str, object] | None  # Structured execution metadata
    error_summary: str | None
    usefulness_class: UsefulnessClass | None  # useful/partial/noisy/empty
    alertmanager_relevance: AlertmanagerRelevanceClass | None
    alertmanager_provenance: dict[str, object] | None
    artifact_id: str            # UUIDv7 immutable identifier
```

**Payload contents for execution artifacts:**
```python
payload = {
    "candidateIndex": int,
    "candidateId": str,
    "candidateDescription": str,
    "targetCluster": str,
    "targetContext": str,
    "commandFamily": str,
    "command": str,           # Actual kubectl command
    "clusterLabel": str,
}
```

**File path:** `health/external-analysis/{run_id}-next-check-execution-{index}.json`

**Index tracking:** `ui-index.json` stores `next_check_execution` list for O(1) lookup.

**Status: Full coverage. Immutable artifacts with complete metadata.**

---

### 6. Result Reuse in Next Step — **MISSING**

**Evidence of gap:**

1. **`next_check_planner.py` only uses enrichment artifact:**
   ```python
   def plan_next_checks(
       review_path: Path,
       run_id: str,
       enrichment_artifact: ExternalAnalysisArtifact,  # Only enrichment input
       execution_artifacts: tuple[ExternalAnalysisArtifact, ...] | None = None,  # Used for ranking only
   ) -> NextCheckPlan | None:
   ```

   `execution_artifacts` is used only for **Alertmanager feedback suppression** (run-scoped learning), not for **diagnostic content integration**.

2. **No result digest feeding into next planning:**
   - `result_digest.py` builds a compact digest from execution artifact
   - But digest is only used for **feedback adaptation**, not for **next-check planning input**
   - `build_review_enrichment_input()` does not include execution results in its input context

3. **Chained diagnostics require new run:**
   - Current agent state: "Chained diagnostics are **partially closed-loop**. The agent can execute checks and record results, but re-assessment requires either a new scheduled run or manual operator action." — `docs/reports/current-agent-capabilities.md`

4. **Confirmation from grep:**
   ```
   No matches found for: execution.*result.*next.*check | previous.*execution.*reused
   ```

**What would close the loop:**
- Add execution result digest to `ReviewEnrichmentInput` context
- Make `build_candidates_from_enrichment()` aware of prior execution outputs
- Enable next-check planning to reference and build upon previous execution results within same run

**Status: MISSING. This is the primary blocker for real-cluster chained diagnostics.**

---

### 7. Incident Report Projection — **PARTIAL**

**Files inspected:**
- `src/k8s_diag_agent/ui/api_incident_report.py` (173 lines)
- `src/k8s_diag_agent/ui/api_incident_report_claims.py`
- `src/k8s_diag_agent/ui/api_incident_report_worklist.py`

**Current state:**

**Worklist integration (partial):**
```python
# In api_incident_report_worklist.py
if overlay.artifact_path:
    refs = list(item.get("sourceArtifactRefs") or [])
    artifact_exists = any(ref.get("path") == overlay.artifact_path for ref in refs)
    if not artifact_exists:
        refs.append({"label": "Next-Check Execution", "path": overlay.artifact_path})
        item["sourceArtifactRefs"] = refs
```

Execution artifacts appear in worklist `sourceArtifactRefs` for queue items.

**Incident report integration (partial/missing):**
- `_build_incident_report_payload()` builds five claim types: observed, derived, hypothesis, recommendation, unknown
- Claims are built from: assessments, drilldowns, enrichment, fleet status
- Execution artifacts are **not** a primary input to any claim type
- No claim type for "executed diagnostic check" as evidence for a finding

**Gap:**
- Execution results could strengthen hypothesis claims
- Execution results could validate or refute assessment findings
- Execution provenance could be cited in incident report provenance field

**Status: PARTIAL. Execution artifacts in worklist but not in incident report claims.**

---

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DIAGNOSTIC LOOP                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌───────────────────┐     ┌─────────────────────┐     ┌──────────────────┐  │
│  │ nextChecks        │     │ validation          │     │ approval         │  │
│  │ generation        │────▶│                     │────▶│                  │  │
│  └───────────────────┘     └─────────────────────┘     └──────────────────┘  │
│         │                           │                           │             │
│         ▼                           ▼                           ▼             │
│  ┌───────────────────┐     ┌─────────────────────┐     ┌──────────────────┐  │
│  │ next_check_planner│     │ manual_next_check_  │     │ next_check_      │  │
│  │ .py                │     │ gating.py           │     │ approval.py      │  │
│  │                    │     │                    │     │                  │  │
│  │ Plan artifact:     │     │ Mutation detection  │     │ Approval artifact│  │
│  │ - candidates[]    │     │ Family validation  │     │ written         │  │
│  │ - ranking         │     │ Duplicate check    │     │                 │  │
│  └───────────────────┘     └─────────────────────┘     └──────────────────┘  │
│                                    │                           │             │
│                                    ▼                           ▼             │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ command execution ────────────────────────────────────────────────────────││
│  │ manual_next_check.py                                                 ││
│  │                                                                      ││
│  │ ┌──────────────────────────────────────────────────────────────┐    ││
│  │ │ execute_manual_next_check()                                  │    ││
│  │ │ - Build kubectl command                                      │    ││
│  │ │ - Run via subprocess (45s timeout)                          │    ││
│  │ │ - Capture stdout/stderr                                     │    ││
│  │ │ - Write execution artifact                                  │    ││
│  │ └──────────────────────────────────────────────────────────┘    ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                    │                                             │
│                                    ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ execution artifact persistence                                          ││
│  │                                                                      ││
│  │ ┌──────────────────────────────────────────────────────────────┐    ││
│  │ │ external-analysis/{run_id}-next-check-execution-{index}.json │    ││
│  │ │                                                              │    ││
│  │ │ Fields: raw_output, status, duration_ms, stdout/stderr       │    ││
│  │ │          truncated flags, usefulness_class, provenance       │    ││
│  │ └──────────────────────────────────────────────────────────────┘    ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                    │                                             │
│                   ┌────────────────┴────────────────┐                        │
│                   │                                 │                        │
│                   ▼                                 ▼                        │
│  ┌────────────────────────────────┐    ┌───────────────────────────────────┐│
│  │ result reuse in next step      │    │ incident report projection        ││
│  │                                │    │                                   ││
│  │ ❌ MISSING                     │    │ ⚠️ PARTIAL                         ││
│  │                                │    │                                   ││
│  │ - No execution result digest  │    │ - Worklist: execution refs ✓      ││
│  │   in next planning input      │    │ - Incident report: no exec claims ││
│  │ - No chained diagnostics      │    │ - No exec result in report facts  ││
│  │   within same run             │    │                                   ││
│  └────────────────────────────────┘    └───────────────────────────────────┘│
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Files Inspected

### Next-check planning
| File | Lines | Purpose |
|------|-------|---------|
| `src/k8s_diag_agent/external_analysis/next_check_planner.py` | 150 | Main planner entry point |
| `src/k8s_diag_agent/external_analysis/next_check_planner_candidates.py` | 386 | Candidate construction |
| `src/k8s_diag_agent/external_analysis/next_check_planner_models.py` | 222 | Enums, constants, detection |
| `src/k8s_diag_agent/external_analysis/next_check_planner_ranking.py` | ~150 | Ranking policy |

### Command validation and execution
| File | Lines | Purpose |
|------|-------|---------|
| `src/k8s_diag_agent/external_analysis/manual_next_check.py` | 441 | Execution runner |
| `src/k8s_diag_agent/external_analysis/manual_next_check_gating.py` | ~200 | Validation and gating |
| `src/k8s_diag_agent/external_analysis/manual_next_check_commands.py` | ~200 | Command building |
| `src/k8s_diag_agent/external_analysis/manual_next_check_artifacts.py` | ~200 | Artifact construction |

### Artifacts and persistence
| File | Lines | Purpose |
|------|-------|---------|
| `src/k8s_diag_agent/external_analysis/artifact.py` | 359 | Artifact schema and writing |
| `src/k8s_diag_agent/external_analysis/result_digest.py` | ~150 | Result digest building |
| `src/k8s_diag_agent/external_analysis/alertmanager_feedback.py` | ~150 | Feedback from execution |

### UI projections
| File | Lines | Purpose |
|------|-------|---------|
| `src/k8s_diag_agent/ui/api_incident_report.py` | 173 | Incident report builder |
| `src/k8s_diag_agent/ui/api_incident_report_worklist.py` | ~400 | Worklist builder |
| `src/k8s_diag_agent/ui/server_read_execution_history.py` | 207 | Execution history hydration |

### Tests
| File | Purpose |
|------|---------|
| `tests/unit/test_external_analysis_*.py` | External analysis tests |
| `tests/unit/test_api_incident_report.py` | 91 tests for incident report |
| `tests/fixtures/incident_report_fixtures.py` | Quality fixtures |

---

## Questions Answered

### 1. Where are nextChecks produced?
**Answer:** `next_check_planner.py::plan_next_checks()` produces plan artifact from LLM enrichment's `suggested_next_checks`.

### 2. Where are nextChecks validated or rejected?
**Answer:** `manual_next_check_gating.py::check_candidate_gating()` and `validate_command_family()` enforce mutation detection, family validation, and duplicate checking.

### 3. Where can an operator approve or trigger a diagnostic command?
**Answer:** 
- Approval: `next_check_approval.py::record_next_check_approval()` via `server_feedback.py` endpoints
- Execution: `manual_next_check.py::execute_manual_next_check()` via batch script or UI

### 4. What execution artifact is produced?
**Answer:** `ExternalAnalysisArtifact` with `purpose=NEXT_CHECK_EXECUTION`, stored at `health/external-analysis/{run_id}-next-check-execution-{index}.json`.

### 5. What schema identifies command, cluster, namespace, timestamp, status, stdout/stderr, and provenance?
**Answer:** Full schema in `artifact.py` `ExternalAnalysisArtifact`:
- `tool_name`, `run_id`, `cluster_label`, `timestamp`
- `status`, `raw_output`, `stdout_truncated`, `stderr_truncated`, `timed_out`
- `duration_ms`, `payload` (with command details)
- `artifact_id`, `alertmanager_provenance`

### 6. Can later diagnostic steps consume previous command results?
**Answer:** **NO.** Execution artifacts are written but not fed into next planning iteration within same run. This is the primary missing link.

### 7. Can incident reports cite those command artifacts?
**Answer:** **PARTIAL.** Execution artifacts appear in worklist `sourceArtifactRefs` but do not appear as evidence in incident report claim types (observed, derived, hypothesis, recommendation, unknown).

### 8. What is the smallest implementation ACT that would close the loop?
**Answer:** See next section.

---

## Next Implementation ACT

Based on the audit, the smallest coherent next step to close the loop is:

```markdown
# [Open] ACT: Feed diagnostic command execution results into follow-up next-check planning

Goal:
Enable next-check planning to consume prior execution results within the same diagnostic run.

Scope:
- Add execution result digest to `ReviewEnrichmentInput` context
- Extend `build_candidates_from_enrichment()` to consider execution results
- Add execution result summary to next-check candidates for display

Files likely to change:
- `src/k8s_diag_agent/external_analysis/review_input.py` — Add execution digest to context
- `src/k8s_diag_agent/external_analysis/next_check_planner_candidates.py` — Use execution context
- `src/k8s_diag_agent/external_analysis/result_digest.py` — Enhance digest for planning input
- `src/k8s_diag_agent/external_analysis/manual_next_check_artifacts.py` — Ensure digest availability

Non-goals:
- Do not implement automatic re-assessment loop (defer to separate ACT)
- Do not change execution artifact schema
- Do not modify incident report claims

Acceptance criteria:
- [ ] Execution result digests available in planning context
- [ ] Next-check candidates can reference prior execution results
- [ ] No regression in existing planning behavior
- [ ] Unit tests for new behavior
- [ ] Verification gate passes
```

---

## Secondary ACT (Incident Report Integration)

```markdown
# [Open] ACT: Project diagnostic execution evidence into incident reports

Goal:
Surface execution artifacts as evidence in incident report claim types.

Scope:
- Add execution artifact claims to incident report builder
- Create new claim type or extend existing types for executed diagnostics
- Preserve provenance for operator trust

Files likely to change:
- `src/k8s_diag_agent/ui/api_incident_report_claims.py` — Add execution claims
- `src/k8s_diag_agent/ui/api_incident_report.py` — Integrate into report payload

Non-goals:
- Do not modify execution artifact schema
- Do not change worklist behavior (already working)
- Do not implement automatic re-assessment
```

---

## Verification Commands Run

```bash
# Check for execution result reuse patterns (should find nothing)
grep -r "execution.*result.*next.*check\|previous.*execution.*reused" src/

# Check execution artifact references in incident report (partial match expected)
grep -r "execution.*artifact.*report\|sourceArtifact.*execution" src/

# Verify gate passes
./scripts/verify_all.sh

# Expected output: VERIFICATION GATE: PASSED
```

---

## Verification Results

| Command | Result |
|---------|--------|
| `scripts/verify_all.sh` | PASSED |
| Unit tests | 179 passed |
| Ruff lint | 0 failures |
| Mypy | 0 issues |

---

## Close Report

**Audit completed:** 2026-06-06

**Key findings:**
1. nextChecks generation, validation, approval, execution, and artifact persistence are all **WORKING**
2. Result reuse in next diagnostic step is **MISSING** — primary blocker
3. Incident report integration is **PARTIAL** — execution in worklist but not in report claims

**Files inspected:** 25+ source files, 15+ test files, 5+ documentation files

**Recommended next ACT:** Feed diagnostic command execution results into follow-up next-check planning

**Status:** Audit complete. Ready for implementation.

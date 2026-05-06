# k9b Artifact Integrity and Provenance Audit

**Document**: Artifact Integrity and Provenance Audit  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-05-06
**Author**: k9b Security Audit  
**Status**: Initial Draft  

---

## Executive Summary

This audit examines how k9b writes, reads, trusts, replays, and mutates run artifacts to identify tampering, replay, path-confusion, stale-index, and provenance risks.

**Key Findings**:
- 14 artifact types identified across 5 trust categories
- 1 artifact type (FeedbackArtifact) lacks artifact_id provenance
- No cryptographic integrity verification (SHA256/HMAC)
- ui-index.json is mutable without freshness validation
- External analysis artifacts can influence queue execution

---

## 1. Scope

### 1.1 Artifact Directories

| Directory | Contents |
|----------|----------|
| `runs/health/` | Per-run health artifacts (snapshots, assessments, drilldowns, proposals, external analysis, notifications) |
| `runs/health/ui-index.json` | Derived UI index (mutable) |
| `runs/feedback/` | Feedback loop artifacts |
| `runs/comparisons/` | Cluster comparison artifacts |
| `runs/assessments/` | Health assessment artifacts |

### 1.2 Excluded from Scope

- Config files (health-config.local.json, run-config.local.json)
- Baseline policy files
- Diagnostic packs (mutable by design)

---

## 2. Trust Classification Model

Artifacts are classified into 5 trust categories:

| Category | Description | Trust Level |
|----------|-------------|-------------|
| **Trusted Writer / Unverified Storage** | Written by k9b process, stored on local filesystem without integrity verification | MEDIUM |
| **Derived / Rebuildable** | Computed from source artifacts, can be regenerated | LOW |
| **Operator-Input Influenced** | Contains operator decisions that gate execution | HIGH |
| **LLM-Output Influenced** | Contains untrusted external provider output | UNTRUSTED |
| **Execution-Influencing** | Can trigger or gate kubectl/helm subprocess execution | CRITICAL |

---

## 3. Artifact Inventory

### 3.1 Cluster Snapshot

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/{run_id}-snapshot.json` |
| **Schema Class** | `ClusterSnapshot` in `collect/cluster_snapshot.py` |
| **Writer** | `collect/live_snapshot.py` → `collect_cluster_snapshot()` |
| **Readers** | UI (`ui/server_reads.py`), health loop, comparison logic |
| **Trust Category** | Trusted Writer / Unverified Storage |
| **Schema Validation** | `from_dict()` with field coercion; lenient (accepts missing fields) |
| **Overwrite Behavior** | Append-only via `write_append_only_json_artifact()`; rejects overwrite |
| **artifact_id** | ✅ Optional (UUIDv7, None for legacy) |
| **Mutation Influence** | None (read-only cluster state) |
| **Execution Influence** | None |
| **Stale/Replay Risk** | LOW - immutable by filename pattern |
| **Existing Controls** | Path validation via `validate_run_id()`, append-only enforcement |
| **Gaps** | No SHA256 integrity, no artifact_id, lenient schema validation |

---

### 3.2 Health Assessment Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/assessments/{run_id}-{cluster_label}-assessment.json` |
| **Schema Class** | `HealthAssessmentArtifact` in `health/loop.py` |
| **Writer** | `health/loop.py` → `build_health_assessment()` |
| **Readers** | UI projections, `health/ui_serialization.py` |
| **Trust Category** | Trusted Writer / Unverified Storage |
| **Schema Validation** | `to_dict()` only; no `from_dict()` for reads |
| **Overwrite Behavior** | Immutable by design; single write per run |
| **artifact_id** | ❌ MISSING |
| **Mutation Influence** | None |
| **Execution Influence** | None |
| **Stale/Replay Risk** | LOW |
| **Existing Controls** | Append-only write |
| **Gaps** | No SHA256, no artifact_id |

---

### 3.3 Drilldown Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/drilldowns/{run_id}-{cluster_label}-drilldown.json` |
| **Schema Class** | `DrilldownArtifact` in `health/drilldown.py` |
| **Writer** | `health/drilldown.py` → `DrilldownCollector.collect()` |
| **Readers** | UI (`ui_serialization.py`), `health/review.py` |
| **Trust Category** | Trusted Writer / Unverified Storage |
| **Schema Validation** | `from_dict()` with nested type coercion |
| **Overwrite Behavior** | Append-only; one per cluster per run |
| **artifact_id** | ✅ Optional (UUIDv7, None for legacy) |
| **Mutation Influence** | None |
| **Execution Influence** | None |
| **Stale/Replay Risk** | LOW |
| **Existing Controls** | Path validation, append-only, artifact_id (partial) |
| **Gaps** | No SHA256, artifact_id not always present |

---

### 3.4 Health Proposal

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/proposals/{run_id}-{proposal_id}.json` |
| **Schema Class** | `HealthProposal` in `health/adaptation.py` |
| **Writer** | `health/adaptation.py` → `generate_proposals_from_review()` |
| **Readers** | UI (`ui_serialization.py`), promotion logic |
| **Trust Category** | Trusted Writer / Unverified Storage |
| **Schema Validation** | `from_dict()` with confidence level enum validation |
| **Overwrite Behavior** | Immutable by filename; lifecycle status appended via `with_lifecycle_status()` |
| **artifact_id** | ✅ Optional (UUIDv7, None for legacy) |
| **Mutation Influence** | Proposals suggest configuration changes (via promotion) |
| **Execution Influence** | INDIRECT - proposals can trigger config file modification |
| **Stale/Replay Risk** | MEDIUM - old proposals could be replayed via promotion |
| **Existing Controls** | Append-only writes, lifecycle history tracking |
| **Gaps** | No SHA256, no proposal expiration, no replay prevention |

---

### 3.5 External Analysis Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/external-analysis/{run_id}-{tool_name}-{purpose_suffix}.json` |
| **Schema Class** | `ExternalAnalysisArtifact` in `external_analysis/artifact.py` |
| **Writer** | Various: `llamacpp_adapter.py`, `k8sgpt_adapter.py`, `next_check_approval.py`, etc. |
| **Readers** | UI projections, queue system, planner |
| **Trust Category** | LLM-Output Influenced |
| **Schema Validation** | `from_dict()` with enum coercion; some fields optional |
| **Overwrite Behavior** | Append-only; rejects overwrite (immutability contract) |
| **artifact_id** | ✅ Required (UUIDv7) |
| **LLM Content Fields** | `summary`, `findings`, `suggested_next_checks`, `raw_output`, `payload` |
| **Mutation Influence** | LLM output influences next-check queue ranking |
| **Execution Influence** | CRITICAL - `suggested_next_checks` can queue kubectl/helm commands |
| **Stale/Replay Risk** | MEDIUM - old LLM output could influence future queue |
| **Existing Controls** | Append-only, artifact_id, operator approval gates execution |
| **Gaps** | No SHA256, LLM output not sandboxed, schema allows arbitrary payload |

---

### 3.6 Next-Check Approval Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/external-analysis/{run_id}-next-check-approval-{candidate_index}.json` |
| **Schema Class** | `ExternalAnalysisArtifact` with `purpose=NEXT_CHECK_APPROVAL` |
| **Writer** | `external_analysis/next_check_approval.py` → `record_next_check_approval()` |
| **Readers** | Queue system, `collect_next_check_approvals()` |
| **Trust Category** | Operator-Input Influenced |
| **Schema Validation** | `from_dict()` inherited from ExternalAnalysisArtifact |
| **Overwrite Behavior** | Append-only; one per candidate index |
| **artifact_id** | ✅ Required |
| **Payload Content** | `planArtifactPath`, `candidateIndex`, `candidateDescription` |
| **Mutation Influence** | Operator approval gates queue entry execution |
| **Execution Influence** | CRITICAL - approval artifact must exist before execution |
| **Stale/Replay Risk** | HIGH - old approval could authorize stale/rogue execution |
| **Existing Controls** | Append-only, artifact_id, operator approval gate |
| **Gaps** | No timestamp validation, no expiration, no run-scoped binding |

---

### 3.7 Next-Check Promotion Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/external-analysis/{run_id}-next-check-promotion-{index}.json` |
| **Schema Class** | `ExternalAnalysisArtifact` with `purpose=NEXT_CHECK_PROMOTION` |
| **Writer** | `external_analysis/deterministic_next_check_promotion.py` → `write_deterministic_next_check_promotion()` |
| **Readers** | Queue system, `collect_promoted_queue_entries()` |
| **Trust Category** | Operator-Input Influenced |
| **Schema Validation** | `from_dict()` inherited, payload fields extracted |
| **Overwrite Behavior** | Append-only; index auto-incremented |
| **artifact_id** | ✅ Required |
| **Payload Content** | `description`, `clusterLabel`, `candidateId`, `whyNow`, `priorityScore` |
| **Mutation Influence** | Promotion moves deterministic checks to approval queue |
| **Execution Influence** | INDIRECT - promotes checks that require approval |
| **Stale/Replay Risk** | MEDIUM |
| **Existing Controls** | Append-only, artifact_id, approval gate downstream |
| **Gaps** | No SHA256 |

---

### 3.8 Next-Check Execution Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/external-analysis/{run_id}-next-check-execution-{index}.json` |
| **Schema Class** | `ExternalAnalysisArtifact` with `purpose=NEXT_CHECK_EXECUTION` |
| **Writer** | `external_analysis/manual_next_check.py`, UI server via API |
| **Readers** | UI execution history, `ui_next_check_execution.py` |
| **Trust Category** | Execution-Influencing |
| **Schema Validation** | `from_dict()` inherited |
| **Overwrite Behavior** | Append-only |
| **artifact_id** | ✅ Required |
| **Execution Influence** | CRITICAL - execution artifact records kubectl/helm subprocess invocation |
| **Stale/Replay Risk** | MEDIUM - execution record used for usefulness feedback |
| **Existing Controls** | Append-only, artifact_id, operator approval required before execution |
| **Gaps** | No SHA256, no execution freshness validation |

---

### 3.9 Alertmanager Snapshot Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/{run_id}-alertmanager-snapshot.json` |
| **Schema Class** | `AlertmanagerSnapshot` in `external_analysis/alertmanager_snapshot.py` |
| **Writer** | `health/loop_alertmanager_snapshot.py` |
| **Readers** | UI projections, ranking logic |
| **Trust Category** | LLM-Output Influenced (via external provider data) |
| **Schema Validation** | `from_dict()` with nested type coercion |
| **Overwrite Behavior** | Append-only |
| **artifact_id** | ✅ Optional (UUIDv7, None for legacy) |
| **LLM Influence** | Alertmanager data influences LLM ranking bonus |
| **Stale/Replay Risk** | LOW |
| **Existing Controls** | Append-only, port-forward security, artifact_id (partial) |
| **Gaps** | No SHA256 |

---

### 3.10 Alertmanager Compact Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/{run_id}-alertmanager-compact.json` |
| **Schema Class** | `AlertmanagerCompact` in `external_analysis/alertmanager_snapshot.py` |
| **Writer** | `health/loop_alertmanager_snapshot.py` |
| **Readers** | UI projections, ranking signal |
| **Trust Category** | LLM-Output Influenced |
| **Schema Validation** | `from_dict()` with nested type coercion |
| **Overwrite Behavior** | Append-only |
| **artifact_id** | ✅ Optional (UUIDv7, None for legacy) |
| **Ranking Influence** | Compact provides `affected_namespaces`, `affected_clusters`, `affected_services` for bonus |
| **Stale/Replay Risk** | LOW |
| **Existing Controls** | Append-only, artifact_id (partial) |
| **Gaps** | No SHA256 |

---

### 3.11 Notification Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/notifications/{timestamp}-{kind}[-{artifact_id}].json` |
| **Schema Class** | `NotificationArtifact` in `health/notifications.py` |
| **Writer** | `health/notifications.py` → `write_notification_artifact()` |
| **Readers** | UI notifications endpoint |
| **Trust Category** | Trusted Writer / Unverified Storage |
| **Schema Validation** | `from_dict()` with details mapping coercion |
| **Overwrite Behavior** | Append-only; unique by timestamp + kind (+ artifact_id) |
| **artifact_id** | ✅ Optional (UUIDv7, None for legacy) |
| **Mutation Influence** | None |
| **Execution Influence** | None |
| **Stale/Replay Risk** | LOW |
| **Existing Controls** | Append-only, artifact_id (partial) |
| **Gaps** | No SHA256 |

---

### 3.12 Feedback Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/feedback/{run_id}-{context}-feedback.json` |
| **Schema Class** | `RunArtifact` in `feedback/models.py` |
| **Writer** | `feedback/runner.py` → `FeedbackRunRunner.execute()` |
| **Readers** | Feedback learning system |
| **Trust Category** | Trusted Writer / Unverified Storage |
| **Schema Validation** | `to_dict()` only; serialized from dataclass |
| **Overwrite Behavior** | Mutable (run feedback can overwrite) |
| **artifact_id** | ❌ MISSING |
| **Operator Input** | Comparison intent, expected/unexpected drift categories |
| **Stale/Replay Risk** | MEDIUM - feedback influences future ranking |
| **Existing Controls** | None explicit |
| **Gaps** | No SHA256, no artifact_id, mutable |

---

### 3.13 UI Index (ui-index.json)

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/ui-index.json` |
| **Schema Class** | Inline dict in `health/ui.py` |
| **Writer** | `health/ui.py` → `write_health_ui_index()` (rebuilt each run) |
| **Readers** | UI server (`ui/server_reads.py`) |
| **Trust Category** | Derived / Rebuildable |
| **Schema Validation** | Implicit; no explicit schema |
| **Overwrite Behavior** | MUTABLE - overwritten each health loop run |
| **Freshness Validation** | PARTIAL - cache key includes mtime of reviews, external-analysis, diagnostic-packs |
| **artifact_id** | ❌ N/A (derived index) |
| **Derived Sub-Indexes** | `notification_index`, `promotions_index`, `recent_runs_summary`, `_review_proposal_status_summary` |
| **Stale/Replay Risk** | MEDIUM - stale index could cause incorrect UI state |
| **Existing Controls** | Cache key includes mtime, index regeneration each run |
| **Gaps** | No SHA256 of source artifacts, no freshness timestamp on index |

---

### 3.14 Comparison Trigger Artifact

| Property | Value |
|----------|-------|
| **Path Pattern** | `runs/health/comparisons/{run_id}-{primary}-{secondary}-comparison.json` |
| **Schema Class** | `ComparisonTriggerArtifact` in `health/loop.py` |
| **Writer** | `health/loop.py` → comparison logic |
| **Readers** | `loop.py`, UI projections |
| **Trust Category** | Trusted Writer / Unverified Storage |
| **Schema Validation** | `from_dict()` with nested type coercion |
| **Overwrite Behavior** | Append-only |
| **artifact_id** | ✅ Optional (UUIDv7, None for legacy) |
| **Stale/Replay Risk** | LOW |
| **Existing Controls** | Append-only, artifact_id (partial) |
| **Gaps** | No SHA256 |

---

## 4. Risk Table

| Risk ID | Description | Affected Artifacts | Severity | Likelihood | Risk Score | Category |
|---------|-------------|-------------------|----------|------------|------------|----------|
| **RISK-AI-01** | No cryptographic integrity verification (SHA256/HMAC) | All artifact types | MEDIUM | MEDIUM | 6 | Tampering |
| **RISK-AI-02** | Stale ui-index.json trust without explicit freshness validation | ui-index.json | MEDIUM | LOW | 4 | Stale Index |
| **RISK-AI-03** | LLM output can influence queue execution without strong schema validation | ExternalAnalysisArtifact | HIGH | MEDIUM | 7 | LLM Influence |
| **RISK-AI-04** | Old approval artifacts can authorize stale execution | NextCheckApproval | MEDIUM | LOW | 5 | Replay |
| **RISK-AI-05** | FeedbackArtifact lacks artifact_id provenance (ClusterSnapshot, AlertmanagerSnapshot, AlertmanagerCompact addressed by REM-AI-02) | FeedbackArtifact | LOW | MEDIUM | 3 | Provenance |
| **RISK-AI-06** | Path traversal mitigated but path confusion still possible | All artifacts | LOW | LOW | 2 | Path Confusion |
| **RISK-AI-07** | Feedback artifacts are mutable (no immutability contract) | FeedbackArtifact | MEDIUM | LOW | 4 | Tampering |
| **RISK-AI-08** | lenience in from_dict() allows malformed data | All artifact types | MEDIUM | MEDIUM | 6 | Schema Validation |
| **RISK-AI-09** | ExternalAnalysisArtifact payload allows arbitrary dict content | ExternalAnalysisArtifact | MEDIUM | MEDIUM | 5 | LLM Influence |
| **RISK-AI-10** | No artifact expiration or TTL enforcement | Approval, Promotion, Execution | LOW | MEDIUM | 3 | Replay |

---

## 5. Existing Controls

### 5.1 Path Validation

| Control | Implementation | Coverage |
|---------|----------------|----------|
| `validate_run_id()` | `security/path_validation.py` - validates alphanumeric + hyphen/underscore, rejects `..`, `/`, `\` | All run_id usage |
| `safe_child_path()` | Resolves path and verifies containment under root | Artifact file access |
| `safe_run_artifact_glob()` | Constructs safe glob patterns from validated run_id | Artifact glob operations |
| `validate_kube_context_name()` | Rejects shell metacharacters, path separators | kubectl context names |

### 5.2 Immutability Enforcement

| Control | Implementation | Coverage |
|---------|----------------|----------|
| `write_append_only_json_artifact()` | `identity/artifact.py` - raises FileExistsError on overwrite | External analysis, alertmanager, proposals |
| Notification artifact naming | `health/notifications.py` - uses unique timestamp + artifact_id | Notifications |

### 5.3 Provenance Tracking

| Control | Implementation | Coverage |
|---------|----------------|----------|
| `new_artifact_id()` | `identity/artifact.py` - UUIDv7 for time-ordered immutable IDs | External analysis, drilldowns, proposals, notifications |
| `artifact_id` field | Present in: ExternalAnalysisArtifact, DrilldownArtifact, HealthProposal, NotificationArtifact | Partial coverage |

### 5.4 Approval Gates

| Control | Implementation | Coverage |
|---------|----------------|----------|
| Operator approval for executions | `external_analysis/next_check_approval.py` - requires explicit approval artifact | Next-check execution |
| Lifecycle history tracking | `health/adaptation.py` - ProposalLifecycleEntry tracks status changes | Proposals |

---

## 6. Gaps

### 6.1 Critical Gaps

| Gap ID | Description | Risk Score | Effort |
|--------|-------------|------------|--------|
| **GAP-AI-01** | No SHA256/HMAC integrity verification for any artifact type | 6 | 1 week |
| **GAP-AI-02** | LLM output (ExternalAnalysisArtifact) can influence execution queue without strong payload validation | 7 | 1 week |

### 6.2 High Gaps

| Gap ID | Description | Risk Score | Effort |
|--------|-------------|------------|--------|
| **GAP-AI-03** | FeedbackArtifact lacks artifact_id provenance (ClusterSnapshot, AlertmanagerSnapshot, AlertmanagerCompact addressed by REM-AI-02) | 4 | 2 days |
| **GAP-AI-04** | Approval artifacts have no timestamp validation to prevent stale replay | 5 | 1 day |
| **GAP-AI-05** | FeedbackArtifact is mutable (no immutability contract) | 4 | 1 day |

### 6.3 Medium Gaps

| Gap ID | Description | Risk Score | Effort |
|--------|-------------|------------|--------|
| **GAP-AI-06** | lenience in from_dict() allows malformed data to be loaded | 6 | 1 week |
| **GAP-AI-07** | ui-index.json lacks explicit freshness timestamp | 4 | 1 day |
| **GAP-AI-08** | ExternalAnalysisArtifact.payload allows arbitrary dict content (no schema enforcement) | 5 | 1 week |

### 6.4 Low Gaps

| Gap ID | Description | Risk Score | Effort |
|--------|-------------|------------|--------|
| **GAP-AI-09** | No artifact TTL or expiration enforcement | 3 | 2 days |
| **GAP-AI-10** | Proposal replay has no timestamp validation | 3 | 1 day |

---

## 7. Remediation Backlog

### 7.1 Priority 1 (Immediate)

| ID | Remediation | Dependencies | Effort | Status |
|----|-------------|--------------|--------|--------|
| **REM-AI-01** | Add SHA256 integrity field to `write_append_only_json_artifact()` (optional, backward compatible) | GAP-AI-01 | 2 days | Pending |
| **REM-AI-02** | Add artifact_id to ClusterSnapshot, AlertmanagerSnapshot, AlertmanagerCompact | GAP-AI-03 | 1 day | ✅ DONE |

### 7.2 Priority 2 (Within 2 weeks)

| ID | Remediation | Dependencies | Effort |
|----|-------------|--------------|--------|
| **REM-AI-03** | Add timestamp validation to approval artifact reads (reject stale approvals) | GAP-AI-04 | 1 day |
| **REM-AI-04** | Add ui-index.json freshness timestamp field | GAP-AI-07 | 1 day |
| **REM-AI-05** | Add PayloadSchema class for ExternalAnalysisArtifact.payload with strict validation | GAP-AI-08 | 1 week |
| **REM-AI-06** | Make FeedbackArtifact append-only with artifact_id | GAP-AI-05 | 1 day |

### 7.3 Priority 3 (Within 1 month)

| ID | Remediation | Dependencies | Effort |
|----|-------------|--------------|--------|
| **REM-AI-07** | Add SHA256 verification on artifact reads (opt-in via field presence) | GAP-AI-01 | 1 week |
| **REM-AI-08** | Add artifact read verification tests with adversarial inputs | GAP-AI-06 | 1 week |
| **REM-AI-09** | Document artifact trust boundaries in operator documentation | Documentation | 2 days |

---

## 8. Recommended First Remediation

**Recommended First Remediation**: `REM-AI-02` - Add artifact_id to ClusterSnapshot, AlertmanagerSnapshot, AlertmanagerCompact

**Rationale**:
1. Low effort (1 day)
2. High value (establishes provenance for all major artifact types)
3. Backward compatible (artifact_id is optional, legacy artifacts continue to work)
4. Enables future integrity verification (artifact_id + SHA256)

**Implementation Plan**:
1. Add `artifact_id: str | None = None` field to `ClusterSnapshot.to_dict()` and `from_dict()`
2. Add `artifact_id: str | None = None` field to `AlertmanagerSnapshot.to_dict()` and `from_dict()`
3. Add `artifact_id: str | None = None` field to `AlertmanagerCompact.to_dict()` and `from_dict()`
4. Use `new_artifact_id()` in writers to generate UUIDv7 IDs
5. Add tests for artifact_id generation and persistence
6. Update `docs/security/artifact-integrity-audit.md` with completion status

---

## 9. Related Documents

- `docs/security/threat-model.md` - General security threat model
- `docs/security/api-security-audit.md` - API attack surface analysis
- `docs/security/llm-prompt-security-audit.md` - LLM prompt injection analysis
- `src/k8s_diag_agent/identity/artifact.py` - Artifact identity and write helpers
- `src/k8s_diag_agent/security/path_validation.py` - Path validation controls

---

**Document End**
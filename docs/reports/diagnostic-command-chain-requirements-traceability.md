# Requirements-to-Audit Report Mapping

## Purpose

This document maps the external high-level requirements from the SRE / CloudPlatform requirement row to the planned diagnostic command chain and artifact lifecycle audit report.

The goal is to keep the audit grounded in product requirements without expanding the audit into implementation work.

## Source requirement

Source requirement text, translated and normalized:

> AI tools for SRE and CloudPlatform: Kubernetes cluster diagnostics, namespace/pod diagnostics, executing actions according to an incident knowledge base, Kubernetes manifest generation.

Out of scope for this audit:

- Kubernetes manifest generation. This belongs to a different application or workstream.

In scope for this audit:

- Kubernetes cluster diagnostics.
- Namespace diagnostics.
- Pod diagnostics.
- Diagnostic or investigative actions selected according to incident knowledge.
- Traceability from proposed action to execution artifact and operator-visible state.

## Mapping table

| Requirement ID | External requirement | Audit report section | What the audit should verify | Expected status framing |
|---|---|---|---|---|
| EXT-001 | AI tools for SRE and CloudPlatform | Executive summary | Whether k9b is accurately positioned as an AI-assisted diagnostic and operator workflow tool, not an autonomous root-cause or remediation oracle. | Strong fit, with safety caveats. |
| EXT-002 | Diagnose Kubernetes cluster | Current lifecycle model; Known-good behavior covered by tests | Whether cluster-level evidence flows from collectors and alerts into findings, incident report, next checks, and UI/API state. | Strong coverage. |
| EXT-003 | Diagnose namespace | UI/API hydration path; Source-of-truth artifacts vs derived projections | Whether namespace-scoped findings and artifacts are preserved and rendered coherently, and whether namespace is first-class or incidental. | Partial to strong coverage. |
| EXT-004 | Diagnose pod | Current lifecycle model; Known-good behavior covered by tests; Findings | Whether pod-scoped diagnostics are represented through collected Kubernetes resources, deterministic checks, proposed next checks, and execution artifacts. | Partial to strong coverage. |
| EXT-005 | Execute actions according to incident knowledge base | Current lifecycle model; Source-of-truth artifacts vs derived projections; Findings | Whether proposed/executed actions can be traced to deterministic rules, provider suggestions, operator/manual input, or a formal KB/playbook source. | Partial; likely main gap. |
| EXT-006 | Preserve lifecycle from proposed action to execution artifact | Current lifecycle model; UI/API hydration path; Findings by severity | Whether candidate identity, approval/queue/execution status, artifact refs, and UI state remain coherent across JSON serialization and index hydration. | Under audit; P0 audit focus. |
| EXT-007 | Preserve evidence/provenance for executed actions | Source-of-truth artifacts vs derived projections; UI/API hydration path; Known-good behavior | Whether immutable execution artifacts remain the source of truth and client/UI/index state cannot spoof provenance. | Strong direction; verify details. |
| EXT-008 | Explain incidents in operator-readable language | Executive summary; UI/API hydration path; Non-findings | Whether incident/report/review-enrichment surfaces explain findings without overclaiming. | Strong coverage. |
| EXT-009 | Avoid unsafe automatic remediation | Executive summary; Non-findings; Findings | Whether diagnostic execution is distinguished from remediation and whether mutating actions are gated or out of scope. | Strong safety posture expected. |
| EXT-010 | Generate Kubernetes manifests | Out of scope | No audit required. Mention explicitly to avoid accidental scope creep. | Ignored by instruction. |

## Audit report section checklist

### 1. Executive summary

Should answer:

- Does k9b satisfy the broad requirement category of AI tooling for SRE / CloudPlatform?
- What is the honest product boundary?
- Which parts are already strong versus partial?

Requirement coverage:

- EXT-001
- EXT-008
- EXT-009

Suggested wording:

> k9b fits the AI-assisted SRE diagnostics requirement as an evidence-backed operator workflow system. It should not be described as a fully autonomous remediation or root-cause proof system. Its strongest coverage is cluster-level diagnostics, incident explanation, provenance, and next-check workflows. Its weakest coverage is formal incident knowledge-base action traceability.

### 2. Current lifecycle model

Should answer:

- What is the canonical lifecycle of a diagnostic command/action?
- Where does a proposal originate?
- How is it approved, queued, executed, persisted, indexed, and rendered?
- Are deterministic checks, provider-suggested checks, and manual checks distinguishable?

Requirement coverage:

- EXT-002
- EXT-004
- EXT-005
- EXT-006

Expected table in the audit:

| Lifecycle stage | Source | Artifact/state | Operator-visible projection | Requirement linkage |
|---|---|---|---|---|
| Evidence collection | Health loop / collectors / alerts | Collection artifacts | Cluster/namespace/pod findings | EXT-002, EXT-003, EXT-004 |
| Finding generation | Deterministic rules / provider-assisted analysis | Finding/report artifacts | Incident report | EXT-001, EXT-008 |
| Action proposal | Rules / provider / operator | Next-check candidate | Queue/worklist | EXT-005 |
| Approval / queue | Operator or policy gate | Queue state / candidate state | Next-check queue | EXT-006, EXT-009 |
| Execution | Diagnostic command runner | Execution artifact | Run state / execution result | EXT-006, EXT-007 |
| Index hydration | UI index builder | Derived UI index | Recent runs / queue / report | EXT-006, EXT-007 |
| Review / enrichment | Provider or operator feedback | Review/enrichment artifact | Report/review panel | EXT-008 |

### 3. Source-of-truth artifacts vs derived projections

Should answer:

- Which artifacts are immutable source-of-truth?
- Which data structures are derived caches or UI projections?
- Can the UI index become stale?
- Can client-provided state spoof execution or provenance?

Requirement coverage:

- EXT-003
- EXT-005
- EXT-006
- EXT-007

Audit emphasis:

- Execution artifacts should be treated as source-of-truth for executed diagnostic actions.
- UI index should be treated as derived projection/cache.
- Incident report should preserve claim type and source refs.
- Client-provided status should not be authoritative for provenance or execution state.

### 4. UI/API hydration path

Should answer:

- How do Recent Runs, Next-check Queue, Worklist, Incident Report, and Debug endpoints hydrate their state?
- Do they derive execution labels consistently?
- Are deterministic, executable, failed, skipped, and ineligible checks distinguishable?

Requirement coverage:

- EXT-002
- EXT-003
- EXT-004
- EXT-006
- EXT-007
- EXT-008

Audit emphasis:

- Cluster/namespace/pod diagnosis is only useful if surfaced coherently.
- The same underlying execution artifact must not render as contradictory state in different UI/API views.
- Candidate indices must survive JSON serialization and hydration.

### 5. Known-good behavior already covered by tests

Should answer:

- Which requirement mappings already have regression protection?
- Which tests cover execution summaries, queue state, recent runs, artifact hydration, and provenance?
- Which areas are currently only manually verified?

Requirement coverage:

- EXT-002
- EXT-004
- EXT-006
- EXT-007

Audit emphasis:

- Link test coverage to requirement coverage.
- Separate code paths protected by tests from behavior inferred by reading code.

### 6. Findings grouped by severity

Should answer:

- What is broken, risky, unclear, or undocumented?
- Which gaps are product gaps versus implementation bugs?
- Which findings block truthful requirement claims?

Requirement coverage:

- All in-scope requirements.

Expected severity guidance:

| Severity | Requirement interpretation |
|---|---|
| Blocker | k9b would visibly misrepresent execution state, provenance, or diagnostic truthfulness. |
| High | k9b cannot trace proposed/executed actions reliably enough for operator trust. |
| Medium | A requirement is partially satisfied but not first-class or inconsistently surfaced. |
| Low | Minor naming, display, or documentation ambiguity. |
| Documentation-only | Behavior exists but requirement traceability is undocumented. |

Likely finding theme:

- Formal incident knowledge-base action mapping is probably the biggest gap for EXT-005.

### 7. Concrete follow-up ACT suggestions

Should answer:

- What narrow follow-up work would close the requirement gaps?
- Which ACTs improve traceability without creating a broad redesign?

Requirement coverage:

- EXT-003
- EXT-004
- EXT-005
- EXT-006
- EXT-007

Suggested ACTs:

| Follow-up ACT | Requirement addressed | Purpose |
|---|---|---|
| Define incident knowledge-base action catalog contract | EXT-005 | Make KB-driven action execution explicit and traceable. |
| Trace next-check proposals to KB rule or provider/manual source | EXT-005, EXT-006, EXT-007 | Separate deterministic KB actions from provider-suggested/manual checks. |
| Add namespace diagnostic report slice | EXT-003 | Make namespace diagnosis first-class if currently incidental. |
| Add pod failure taxonomy fixture set | EXT-004 | Strengthen pod diagnosis coverage. |
| Add UI/API parity tests for diagnostic execution state | EXT-006, EXT-007 | Prevent Recent Runs / Queue / Incident Report state divergence. |

### 8. Explicit non-findings

Should answer:

- Which suspected issues are already handled?
- Which requirements are intentionally out of scope?

Requirement coverage:

- EXT-001
- EXT-008
- EXT-009
- EXT-010

Expected non-findings:

- Manifest generation is intentionally ignored for this audit.
- Recommendation generation is acceptable if claims remain typed as recommendation/hypothesis rather than observed fact.
- Lack of automatic remediation is not a defect if the product boundary is diagnostic/operator-assisted.

### 9. Verification commands run

Should answer:

- Which commands were used to validate the audit claims?
- Which tests were inspected or run?
- Was the full gate run?

Requirement coverage:

- EXT-006
- EXT-007

Suggested commands:

```bash
grep -R "executionSummary\|batchExecutionState\|candidateIndex\|sourceArtifactRefs" -n src tests frontend/src

grep -R "next-check\|next check\|manual_next_check\|execution artifact\|ui-index" -n src tests docs scripts

pytest tests/unit -k "execution or queue or recent_runs or next_check or artifact" -q

npm test -- --runInBand

./scripts/verify_all.sh
```

The audit should only include commands actually run by the agent.

### 10. Gate blind spots found

Should answer:

- Which requirement risks are not currently caught by automated checks?
- Which risks need new tests or fixtures?

Requirement coverage:

- EXT-003
- EXT-004
- EXT-005
- EXT-006
- EXT-007

Likely blind spots to confirm or reject:

- No formal test asserting traceability from incident type / KB source to proposed next-check.
- Possible lack of dedicated namespace-level report fixture.
- Possible lack of pod failure taxonomy fixture set.
- Possible UI/API parity gaps around execution labels.

## Requirement-to-section quick reference

| Requirement ID | Primary report section | Secondary report sections |
|---|---|---|
| EXT-001 | Executive summary | Non-findings |
| EXT-002 | Current lifecycle model | Known-good behavior, UI/API hydration path |
| EXT-003 | Source-of-truth artifacts vs derived projections | UI/API hydration path, Follow-up ACTs |
| EXT-004 | Current lifecycle model | Known-good behavior, Follow-up ACTs |
| EXT-005 | Current lifecycle model | Findings, Follow-up ACTs |
| EXT-006 | Current lifecycle model | Source-of-truth artifacts, UI/API hydration path, Verification |
| EXT-007 | Source-of-truth artifacts vs derived projections | UI/API hydration path, Verification |
| EXT-008 | Executive summary | UI/API hydration path, Non-findings |
| EXT-009 | Executive summary | Findings, Non-findings |
| EXT-010 | Out of scope | Non-findings |

## Recommended placement in repository

Suggested path:

```text
docs/reports/diagnostic-command-chain-requirements-traceability.md
```

The main audit report should link to this document from its introduction or appendix:

```md
See also: docs/reports/diagnostic-command-chain-requirements-traceability.md
```

## Close-report note for the agent

When closing the ACT, include this document path under WAL / Cold Resume and mention whether the main audit report incorporated the mapping directly or linked to it as a companion artifact.


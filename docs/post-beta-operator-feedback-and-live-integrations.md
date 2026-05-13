# Operator Feedback and Live Integrations Discovery

**Purpose:** Create a clean operator-feedback and live-integration discovery plan for post-beta without turning discovery items into implementation commitments.

**Status:** Discovery (2026-05-13)

**Parent Epic:** Post-beta hardening and product discovery

**Prerequisites:** Phase 1b LLM anonymization must be committed before this discovery is actionable.

---

## Scope

This document is **planning and discovery only**. It does not:
- Promise live integrations
- Weaken rolling beta limitations
- Move automatic remediation into scope
- Collect private identifiers in feedback templates
- Create implementation commitments

---

## 1. Operator Feedback Collection Plan

### 1.1 Target Personas

| Persona | Role | Feedback Value |
|---------|------|----------------|
| **Platform engineers** | Primary operators running health loops | Diagnostic accuracy, next-check usefulness |
| **SREs** | On-call responders using incident reports | Claim taxonomy clarity, confidence calibration |
| **Developers** | Deploying applications, reading worklists | Deployment friction, UI clarity |
| **Reviewers** | Evaluating incident reports | Provenance clarity, hypothesis grounding |
| **Security auditors** | Reviewing LLM prompt behavior | Anonymization coverage, evidence handling |

### 1.2 Questions to Ask

#### Diagnostic Accuracy
1. Were the recommended next checks actually useful?
2. Did the hypothesis match what you found when you investigated?
3. Were the claims in the right category (observed, derived, hypothesis, recommendation, unknown)?
4. Was the confidence level appropriate given the available evidence?

#### Usefulness
1. Did executing the recommended checks yield actionable findings?
2. Were any recommended checks noisy (yielded irrelevant results)?
3. Were any checks missing that would have been more useful?
4. Was the ranking of worklist items appropriate for your situation?

#### Trust
1. Could you trace each finding back to the source evidence?
2. Did provenance links help you verify or refute conclusions?
3. Were there claims that felt unsupported or unexplained?
4. Did the system correctly distinguish facts from hypotheses?

#### UI Clarity
1. Was the incident report structure understandable?
2. Were worklist states (queued, approval-needed, executed, reviewed) clear?
3. Did ranking rationale help you prioritize?
4. Was stale evidence warning visible and actionable?

#### Deployment Friction
1. Was the Helm chart installation straightforward?
2. Were configuration options clear?
3. Did the health scheduler behave as expected?
4. Were there any unexpected failures or errors?

#### Docs Gaps
1. Were there behavioral areas not covered in the operator guide?
2. Were known limits communicated clearly?
3. Was the claim taxonomy explained adequately?
4. Were there areas where examples would help?

### 1.3 What Artifacts/Logs to Request

**For diagnostic feedback, request:**
- Incident report JSON (redacted for cluster identifiers)
- Worklist JSON with execution results
- `next_check_usefulness_review.json` export
- Relevant `usefulness_summary.json`
- Run metadata (without cluster names): `runs/health/<run_id>/`

**For deployment feedback, request:**
- Health config sanitized (replace cluster names/identifiers)
- Error logs with PII removed
- Verification gate output: `scripts/verify_all.sh --python-only`

**Do NOT request:**
- Actual cluster names, pod names, namespace names
- Pod logs or event content
- Secret values or tokens
- Private identifiers of any kind

### 1.4 How to Avoid Collecting Sensitive Cluster Identifiers

**Pre-collection sanitization:**
```bash
# Before sharing, operators should run:
find runs/health -name "*.json" -exec sed -i \
  -e 's/prod-us-east-1/cluster-alpha/g' \
  -e 's/prod-eu-west-1/cluster-beta/g' \
  -e 's/my-namespace/namespace-x/g' \
  {} \;

# Verify no private identifiers remain
grep -rEn "prod-|staging-|cluster-[a-z]" runs/health/ || echo "Clean"
```

**Feedback form template:**
- Do not include fields for cluster names
- Ask for cluster_class (e.g., "production", "staging") not cluster_id
- Ask for command_family (e.g., "events", "logs") not actual commands
- Ask for claim types (e.g., "observed", "hypothesis") not actual content

### 1.5 Feedback Categories

| Category | Description | Collection Method |
|----------|-------------|-------------------|
| **Diagnostic accuracy** | Did the system diagnose correctly? | Usefulness feedback via export/import scripts |
| **Usefulness** | Were next checks actionable? | Usefulness class (useful, partial, noisy, empty) |
| **Trust** | Is provenance clear? | Structured review via GitHub issues |
| **UI clarity** | Is the interface interpretable? | Structured review via GitHub issues |
| **Deployment friction** | Was setup smooth? | Structured review via GitHub issues |
| **Docs gaps** | What needs better docs? | Structured review via GitHub issues |

---

## 2. Evaluation Rubric

### 2.1 Severity

| Level | Definition | Example |
|-------|------------|---------|
| **Critical** | System produces incorrect or harmful conclusions | Hypothesis claims root cause without basis |
| **High** | System degrades operator efficiency | Recommended checks are consistently noisy |
| **Medium** | System causes confusion or mild friction | Claim taxonomy unclear to reviewers |
| **Low** | Minor polish or docs improvement | UI layout could be improved |

### 2.2 Frequency

| Level | Definition |
|-------|------------|
| **Common** | Reported by multiple operators independently |
| **Occasional** | Reported by 1-2 operators or observed multiple times |
| **Rare** | Single isolated incident |

### 2.3 Operator Impact

| Level | Definition |
|-------|------------|
| **Blocks action** | Operator cannot proceed without work-around |
| **Impairs efficiency** | Operator wastes time on noise or manual work |
| **Minor friction** | Operator experience degraded but functional |
| **Negligible** | No meaningful impact on operator |

### 2.4 Evidence Quality

| Level | Definition |
|-------|------------|
| **High** | Consistent reproduction across multiple runs/clusters |
| **Medium** | Reproducible with specific conditions |
| **Low** | Single observation, no reproduction attempt |
| **Unknown** | No evidence provided |

### 2.5 Confidence

| Level | Definition |
|-------|------------|
| **High** | Multiple operators confirmed, reproducible |
| **Medium** | Single operator confirmed with evidence |
| **Low** | Reported but unverified |

### 2.6 Release-Blocking vs Near-Term vs Later

| Classification | Criteria | Action |
|----------------|----------|--------|
| **Release-blocking** | Critical + common or high + blocks action | Must fix before beta release |
| **Near-term** | High + medium frequency + impairs efficiency | Fix in next sprint after beta |
| **Later** | Medium or low + low frequency + minor friction | Backlog for future release |
| **Discovery** | Product direction unclear | Product discovery epic needed |

---

## 3. Live Integration Discovery

### 3.1 Clarification: Real-Time Alerting Not in Scope

From [docs/beta-release-notes.md](beta-release-notes.md) (Known Limits section):

> **No real-time alerting**: The system runs on configured intervals, not as a continuous alerting system.

This is a **beta contract** guarantee. Any work on live integrations must respect this boundary.

**What this means:**
- k9b runs on intervals (e.g., every 5 minutes via scheduler)
- k9b does NOT respond to Alertmanager webhooks in real-time
- k9b does NOT push notifications when thresholds are crossed
- k9b produces pull-based reports (incident reports, worklists) on schedule

**What operators should expect:**
- k9b discovers Alertmanager sources for cross-run registry purposes
- k9b surfaces Alertmanager data in incident reports (historical context)
- k9b does NOT integrate with Alertmanager for real-time alerting

### 3.2 Integration Candidates (Evaluation Only)

The following are **discovery candidates** for potential future integration. None are committed.

| Integration | Description | Discovery Questions |
|-------------|-------------|---------------------|
| **Alertmanager webhook ingestion** | Receive alerts via webhook and incorporate into next scheduled run | Does this violate the "no real-time alerting" contract? Would it change the polling model? |
| **Slack report delivery** | Send scheduled incident report summaries to Slack channels | What format? Who receives? How to handle multi-cluster? |
| **Email report delivery** | Email scheduled summaries to stakeholder list | Security implications of email delivery? Attachment handling? |
| **Scheduled report summaries** | Generate periodic (daily/weekly) summary of findings | What granularity? What aggregation? |
| **CI/CD integration** | Trigger diagnostics from GitOps pipeline events | Which CI/CD systems? Pre-deploy checks? Post-deploy validation? |
| **GitOps state feedback** | Feed diagnostic findings back to GitOps reconciliation | How to handle conflicting recommendations? |

### 3.3 Decision Criteria for Promoting Integration to Implementation Epic

An integration candidate should be promoted to an **implementation epic** only if:

1. **Fit with beta contract**: Does not violate "no real-time alerting" or other beta guarantees
2. **Operator demand**: Multiple operators explicitly request the integration
3. **Clear value**: The integration solves a documented pain point with measurable benefit
4. **Feasible scope**: The integration can be implemented without breaking existing behavior
5. **Maintainable**: The integration can be maintained without dedicated on-call for alerting pipelines
6. **Evaluable**: Success can be measured with concrete metrics

**Threshold for promotion:**
- Minimum: 2+ operators requesting, with documented use case
- Preferred: 5+ operators, with pilot evaluation plan

### 3.4 Integration-Specific Considerations

#### Alertmanager Webhook Ingestion

**Key question**: Does this violate "no real-time alerting"?

**Analysis:**
- Real-time alerting = k9b actively monitors and notifies
- Webhook ingestion = k9b receives external events and queues for next run

**Preliminary assessment**: Webhook ingestion may be acceptable if:
- It does not trigger immediate processing (still batched)
- It queues alerts for incorporation in next scheduled run
- It does not add a push notification layer

**Next step**: Document specific behavior proposal before committing to discovery.

#### Slack/Email Report Delivery

**Key questions:**
- Who receives reports? How to manage subscription?
- What format? Summary cards? Full incident reports?
- How to handle multi-cluster (one report per cluster or aggregated)?
- How to secure delivery (authentication, encryption)?

**Preliminary assessment**: Scheduled pull-based reports (email/Slack) respect beta contract:
- k9b generates report on schedule
- External system delivers report
- k9b does not "alert" in real-time

---

## 4. Feedback Loop Mechanics

### 4.1 Existing Next-Check Usefulness Export/Import Scripts

From [docs/beta-operator-guide.md](beta-operator-guide.md) and [scripts/export_next_check_usefulness_review.py](scripts/export_next_check_usefulness_review.py):

**Export:**
```bash
.venv/bin/python scripts/export_next_check_usefulness_review.py --runs-dir runs
# Output: runs/health/diagnostic-packs/{run_id}/next_check_usefulness_review.json
```

**Import:**
```bash
.venv/bin/python scripts/import_next_check_usefulness_feedback.py \
  --runs-dir runs \
  --input-file runs/health/diagnostic-packs/latest/next_check_usefulness_review.json
```

**Usefulness classes:**
| Class | Meaning | Effect on Hypotheses |
|-------|---------|----------------------|
| `useful` | Check confirmed or advanced hypothesis | Hypothesis strengthened |
| `partial` | Check yielded some signal but incomplete | Unknown resolved (partially) |
| `noisy` | Check yielded irrelevant results | No material change |
| `empty` | Check produced no output | No material change |

### 4.2 How Feedback Affects the System

**Current feedback mechanism:**
1. Health runs produce next-check candidates
2. Batch execution runs eligible checks
3. Operators review execution results via export
4. Operators add `usefulness_class` judgments
5. Import script writes feedback into artifacts

**What feedback affects:**
- **Hypotheses**: Useful feedback strengthens; noisy feedback does not change diagnosis
- **Future worklists**: Patterns of noisy checks may be deprioritized over time
- **Documentation**: Feedback on docs gaps feeds into operator guide improvements
- **Fixtures**: Useful checks become fixtures for regression testing

**What feedback does NOT affect:**
- **Facts**: Execution results never rewrite observed evidence
- **Provenance**: Feedback attribution is traceable but does not mutate original artifacts
- **Confidence**: Confidence is reduced by unknowns, not by noisy feedback

### 4.3 Guardrails to Prevent Silent Diagnostic Behavior Changes

From [docs/beta-demo-readiness-checklist.md](docs/beta-demo-readiness-checklist.md) (Scenario 4):

> **Acceptance checklist:** Noisy feedback does not silently rewrite diagnosis

**Implementation:**
1. **Noisy feedback → no_material_change**: No adaptation effect logged
2. **Empty feedback → no_material_change**: No adaptation effect logged
3. **Partial feedback → unknown_resolved**: Adaptation summary honestly represents partial resolution
4. **Useful feedback → hypothesis_strengthened**: Explicit provenance trace for strengthening

**Guardrail rules:**
- `adaptationEffect` field is never silently omitted
- Feedback always writes a new review artifact (immutability pattern)
- Original execution artifact is never mutated
- Diagnosis changes require explicit provenance via `next_check_execution_history`

### 4.4 Feedback Loop Summary

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Health Loop    │────▶│  Batch Executor   │────▶│  Execution      │
│  (candidates)   │     │  (runs checks)    │     │  Artifacts      │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Hypothesis     │◀────│  Adaptation      │◀────│  Export Review  │
│  Strengthening  │     │  Provenance      │     │  (usefulness)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## 5. Recommended Next Parent Epic Options

### 5.1 Option A: Post-Beta Operator Feedback Round

**Goal:** Collect, evaluate, and triage operator feedback from beta deployments.

**Scope:**
1. Deploy beta to initial operator cohorts
2. Collect feedback via GitHub issues and structured templates
3. Evaluate feedback using the rubric in Section 2
4. Triage findings into near-term vs later vs discovery buckets
5. Fix release-blocking issues identified

**Non-goals:**
- No new features
- No live integrations
- No automatic remediation

**Exit criteria:**
- Feedback collected from 3+ operator personas
- All critical/high severity findings documented
- Release-blocking issues fixed or explicitly deferred

### 5.2 Option B: Live Integrations Discovery

**Goal:** Evaluate integration candidates and prepare implementation proposals for high-demand items.

**Scope:**
1. Survey operators on integration priorities
2. Document behavior proposals for each candidate (Section 3.2)
3. Assess each candidate against decision criteria (Section 3.3)
4. Produce implementation epic proposals for top candidates
5. Define success metrics for pilot evaluation

**Non-goals:**
- No commitment to implement any integration
- No violation of beta contract
- No automatic remediation features

**Exit criteria:**
- Integration priority list with operator demand evidence
- Implementation epic proposals for top candidates
- Beta contract implications documented for each proposal

### 5.3 Option C: Production Readiness Hardening

**Goal:** Address production deployment concerns before wider rollout.

**Scope:**
1. Add rate limiting to UI server (D-01 from evals)
2. Implement port-forward process lifecycle management (R-08 from security audit)
3. Expand fixture coverage for next-check behavior
4. Add Helm values schema validation
5. Validate full gate runtime within CI time limits

**Non-goals:**
- No new diagnostic features
- No live integrations
- No automatic remediation

**Exit criteria:**
- Rate limiting implemented with configurable thresholds
- Popen lifecycle bounded
- Fixture coverage expanded for next-check behavior
- Verification gate completes within 10 minutes

### 5.4 Option D: Next-Check Quality and Fixture Expansion

**Goal:** Improve diagnostic quality through expanded test coverage and feedback integration.

**Scope:**
1. Expand deterministic fixtures for next-check planning behavior
2. Add regression tests for feedback adaptation provenance
3. Improve usefulness class documentation for operators
4. Add context-aware rollups to usefulness summaries
5. Validate feedback loop end-to-end

**Non-goals:**
- No new diagnostic features
- No live integrations
- No automatic remediation

**Exit criteria:**
- Fixtures cover all known next-check command families
- Feedback adaptation provenance tests pass
- Usefulness class documentation updated

### 5.5 Epic Board Recommendation

```
Epic Board:
- [Closed] Release mechanics and CI verification
- [Closed] Image and chart publication validation
- [Closed] Coverage and verification hardening
- [Closed] Phase 1b LLM anonymization
- [Closed] Operator feedback and live integration discovery  ← This task creates the plan
- [Open] Recommended: Post-Beta Operator Feedback Round

Alternative sequencing (if operators ready):
- [Closed] Release mechanics and CI verification
- [Closed] Image and chart publication validation
- [Closed] Coverage and verification hardening
- [Closed] Phase 1b LLM anonymization
- [Closed] Operator feedback and live integration discovery
- [Open] Live Integrations Discovery (if operator demand exists)
```

---

## 6. Constraints Checklist

| Constraint | Status |
|------------|--------|
| Do not promise live integrations | ✅ Discovery only, no commitments |
| Do not weaken rolling beta limitations | ✅ Beta contract preserved |
| Do not move automatic remediation into scope | ✅ Explicitly excluded |
| Do not collect private identifiers in feedback templates | ✅ Sanitization guidance provided |
| Keep this as discovery/planning | ✅ Document is planning, not implementation |

---

## 7. Verification

### 7.1 Documentation Integrity

```bash
# Verify no broken links (requires linkcheck if configured)
scripts/verify_all.sh --python-only
```

**Expected result:** `VERIFICATION GATE: PASSED`

### 7.2 Phase 1b Pre-requisite Check

Before this discovery is actionable, Phase 1b changes must be committed:

```bash
# Phase 1b changes should be committed
git log --oneline -5
# Expected: Phase 1b commits present

# Check post-beta-backlog.md wording
grep "Phase 1b" docs/post-beta-backlog.md
# Expected: "label/annotation values" not "label values"
```

**Current status:** Phase 1b changes pending commit (git status shows uncommitted changes).

---

## 8. Files Changed

| File | Change |
|------|--------|
| `docs/post-beta-operator-feedback-and-live-integrations.md` | New: Discovery plan for operator feedback and live integrations |

---

## 9. Related Documentation

| Document | Purpose |
|----------|---------|
| [docs/post-beta-backlog.md](post-beta-backlog.md) | Post-beta backlog triage and epic recommendations |
| [docs/beta-release-notes.md](beta-release-notes.md) | Beta scope, known limits, verification status |
| [docs/beta-operator-guide.md](beta-operator-guide.md) | Operator-facing contract, claim taxonomy, feedback loop |
| [docs/beta-demo-readiness-checklist.md](beta-demo-readiness-checklist.md) | Representative scenarios, feedback adaptation tests |
| [docs/artifact-immutability-audit.md](docs/artifact-immutability-audit.md) | Feedback artifact patterns, immutability requirements |
| [scripts/export_next_check_usefulness_review.py](../scripts/export_next_check_usefulness_review.py) | Export script for usefulness review |
| [scripts/import_next_check_usefulness_feedback.py](../scripts/import_next_check_usefulness_feedback.py) | Import script for usefulness feedback |

---

## 10. Exit Criteria (This Discovery)

- [x] Operator feedback collection plan documented
- [x] Feedback categories defined (diagnostic accuracy, usefulness, trust, UI clarity, deployment friction, docs gaps)
- [x] Evaluation rubric defined (severity, frequency, impact, evidence, confidence)
- [x] Live integration candidates documented without commitments
- [x] Decision criteria for promotion defined
- [x] Feedback loop mechanics documented
- [x] Guardrails for diagnostic behavior changes documented
- [x] Four next epic options provided with scope and exit criteria
- [x] Epic board recommendation stated
- [x] Constraints checklist verified
- [x] Phase 1b prerequisite noted (pending commit)

---

**Document End**
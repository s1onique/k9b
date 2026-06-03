# K8s Accelerator Real-Cluster 2-Minute Demo Storyline

**ACT**: Define real-cluster 2-minute K8s Accelerator demo storyline and safety boundaries
**Date**: 2026-06-03
**Status**: Draft

## Executive Summary

This document defines a truthful, evidence-based 2-minute sales demo for K8s Accelerator that runs on a real Kubernetes cluster using live or historical real-cluster diagnostic evidence. The demo prioritizes credibility over theater: it shows real operational signals, real diagnostic reasoning, and operator-approved action recommendations—never fabricated incidents or unsupported autonomous remediation claims.

The demo follows a strict truth hierarchy:
1. **Live real-cluster evidence** (preferred)
2. **Historical real evidence** from previous health runs (fallback)
3. **Clean-cluster honesty** if no issues exist (last resort)

No artificial incident samples, fabricated alerts, or simulated failure injection are used in the primary demo path.

## Demo Objective

Deliver a compelling 2-minute sales walkthrough that demonstrates:
- Real cluster connection and evidence collection
- Live severity-ranked diagnostic findings
- Evidence-backed analysis with probable cause
- Operator-approved or preview-only recommended actions
- Closed-loop evidence preservation

**Target outcome**: The prospect sees genuine operational value—real signals, real reasoning, safe actions—without exaggerated autonomous capabilities.

## Non-Negotiable Demo Principles

1. **Real evidence only**: Primary demo path uses live cluster scans or historical real evidence only.
2. **No fake incident theater**: No fabricated CrashLoopBackOff, ImagePullBackOff, or simulated failures.
3. **Safety-first actions**: Any "fix" action is explicitly labeled as read-only, operator-approved, or demo-namespace-only.
4. **Honest capability framing**: Claims align with real current capability, not aspirational future states.
5. **Evidence provenance always visible**: Users see whether evidence is Live, Historical, or Stale.

## Truth Boundaries

### Real Current Capability

The following are verified, production-ready capabilities that the demo can honestly demonstrate:

| Capability | Demo Behavior |
|------------|----------------|
| Deterministic artifact collection | Show real collected artifacts from cluster scan |
| Health run indexing | Show indexed findings with severity ranking |
| Next-check planning | Show recommended diagnostic follow-up steps |
| Diagnostic command execution artifact persistence | Show compact execution evidence with provenance |
| Follow-up planning with execution context | Show diagnostic chain with reasoning |
| Compact diagnostic execution evidence in incident reports | Show `diagnosticExecutionEvidence` block |
| Operator-visible provenance | Show evidence source label (Live/Historical/Stale) |
| Read-only diagnostic command execution | Show analysis without mutation |
| Allowlisted action preview | Show command preview without auto-execution |

### Real-Cluster Demo Behavior

These behaviors are supported by real evidence and safe for demo presentation:

| Behavior | Demo Behavior |
|----------|---------------|
| Live cluster scan | Run actual diagnostic collection on connected cluster |
| Live severity-ranked findings | Display findings from current health run |
| Historical real run fallback | Show findings from previous real diagnostic execution |
| Operator clicking into real evidence | Drill-down to actual diagnostic artifacts |
| Recommended action from real diagnostic context | Show action derived from actual evidence |
| Evidence-preserving workflow | Maintain artifact chain throughout analysis |
| Diagnostic execution evidence display | Show compact evidence block with signals and provenance |

### Controlled / Allowlisted Action Behavior

These action modes are safe for demo and production use:

| Mode | Behavior | Safety |
|------|----------|--------|
| Read-only | Shows analysis and recommended action only | Always safe, no mutation |
| Operator-approved | Executes only after explicit click with preview | Allowlisted commands only |
| Demo namespace only | Optional mutations in designated demo namespace | Labeled, never arbitrary production targets |
| Preview only | Shows command/action without execution | Always safe, default for production |

### Future / Not Yet Production-Supported Capability

These capabilities are NOT currently supported and must NOT be claimed in the demo:

| Disallowed Claim | Reason |
|------------------|--------|
| Unrestricted autonomous remediation | No policy for arbitrary cluster mutation |
| Root-cause proof | Agent provides probable cause, not proof |
| Guaranteed incident resolution | No SLA or resolution guarantee exists |
| Production-safe arbitrary cluster mutation | Mutations require allowlisting and approval |
| Fleet-wide autonomous healing | Scope exceeds current design |
| Self-healing cluster | Implies autonomous execution without oversight |
| Automatic production fixing | Implies autonomous operation without human review |

## Evidence Source Policy

### Allowed Evidence Sources

The demo may use evidence from these sources:

| Source | Description | Usage in Demo |
|--------|-------------|---------------|
| Live current cluster scan | Real-time diagnostic collection | Primary evidence source |
| Real previous health run artifacts | Stored findings from prior runs | Fallback if cluster is clean |
| Real diagnostic execution artifacts | Prior command execution results | Shows evidence chain |
| Real Alertmanager evidence | Alert history collected by system | Shows alert correlation |
| Real vmalert evidence | Recording rule and alert state | Shows metrics-based findings |
| Real Kubernetes event history | Events captured by collector | Shows operational signals |
| Real stale evidence (clearly labeled) | Old findings marked as historical | Fallback only, must show timestamp |

### Disallowed Evidence Sources

The demo MUST NOT use:

| Source | Reason for Disallowal |
|--------|----------------------|
| Fabricated alert samples presented as real | Undermines credibility |
| Fake incident state transitions | Misrepresents system behavior |
| Manually invented CrashLoopBackOff records | Creates false operational picture |
| Manually invented ImagePullBackOff records | Creates false operational picture |
| Arbitrary production mutation | Safety and audit requirements |
| Claims of unrestricted autonomous remediation | Not supported by current capability |
| Claims of guaranteed root-cause proof | Agent provides probable cause only |
| Claims that agent fixes any Kubernetes issue | Exceeds actual capability |
| Simulated incident injection | No artificial failure theater |

### Historical Evidence Rules

When using historical evidence:

1. **Must be clearly labeled**: Show "Historical Real Run" or "Stale Evidence" badge
2. **Must show timestamp**: Display when evidence was collected
3. **Must show cluster identity**: Confirm which cluster the evidence came from
4. **Must show diagnostic chain**: Display the execution evidence that produced the finding
5. **Never present as live**: Explicitly state "This finding is from a previous run"

## 2-Minute Script

| Time | Screen | User Action | What Happens | Sales Narration |
|------|--------|-------------|--------------|-----------------|
| 0:00–0:15 | Start | Click "Start real-cluster demo" | Opens onboarding with value proposition | "We connect to a real Kubernetes cluster and turn live operational signals into operator-ready actions." |
| 0:15–0:30 | Onboarding | Select kube context, click "Connect" | Cluster becomes connected in read-only mode with status indicator | "The first phase is evidence collection. We do not inject fake failures—we work with what's actually happening." |
| 0:30–0:45 | Dashboard | View health summary | Feed displays live findings or historical real findings with source badge | "The dashboard prioritizes real issues and marks whether evidence is live, stale, or from a previous run." |
| 0:45–1:10 | Finding 1 | Click highest-severity finding | Analysis panel opens with evidence, probable cause, diagnostic execution evidence | "The system shows observed signals, probable cause, and the evidence path behind every recommendation." |
| 1:10–1:25 | Action Panel | Click recommended action / preview | Shows operator-approved action or safe preview with command details | "For production safety, actions are explicit and allowlisted. This is a recommendation, not autonomous execution." |
| 1:25–1:45 | Finding 2 or Fallback | Click second finding or show historical run | Second analysis opens or switch to historical evidence panel | "If the cluster is healthy, we show real historical evidence rather than fabricating an incident." |
| 1:45–2:00 | Final State | Return to dashboard | Evidence and action state remain visible with provenance | "The value is the closed loop: detect, explain, act safely, and preserve evidence for audit." |

## Clickable Demo Path

### 1. Start

**Screen elements**:
- Product name: "K8s Accelerator"
- One-line value proposition: "Transform Kubernetes operational signals into operator-ready actions"
- Primary CTA: "Start real-cluster demo" or "Connect cluster"

**Behavior**:
- Single click transitions to Onboarding
- No pre-populated fake data

**Safety label**: None required at start

### 2. Onboarding: Connect Real Cluster

**Screen elements**:
- Kube context selector (dropdown or auto-detect)
- Connection button: "Connect"
- Safety mode indicator:
  - Read-only (default)
  - Operator-approved
  - Demo namespace only (if available)
- Connection status indicator

**Behavior**:
- System detects available kube contexts
- User selects context or uses default
- Connection establishes in selected safety mode
- "Connected" confirmation appears with cluster label

**Safety label**: "Read-only mode active" (default)

### 3. Dashboard

**Screen elements**:
- Cluster health summary card:
  - Cluster name/label
  - Overall status (Healthy/Warning/Critical)
  - Evidence source badge: Live | Historical Real Run | Stale
- Alert/feed panel:
  - Severity levels: Critical (red), Warning (yellow), Info (blue)
  - Finding cards with title, severity, namespace/workload, age
  - No "Sample" or "Demo" badges on real findings
- Recent diagnostic activity section:
  - Last scan timestamp
  - Findings count by severity
  - Diagnostic commands executed count

**Behavior**:
- Loads live findings if available
- Falls back to historical real findings if cluster is clean
- Shows evidence source badge on each finding
- Findings are ranked by severity (Critical > Warning > Info)

**Safety label**: Evidence source always visible (Live/Historical/Stale)

### 4. Finding Selection Logic

The demo uses a deterministic finding selection algorithm:

```
1. Scan current health run for live critical findings
   → If found: Display top critical finding

2. If no critical, scan for live warning findings
   → If found: Display top warning finding

3. If no live findings, query historical real runs
   → If found: Display historical finding with timestamp

4. If no findings at all:
   → Show clean-cluster success path
   → Explain no fake incidents were injected
   → Offer "View historical evidence" option
```

**Selection criteria**:
- Deterministic ordering (not random)
- Severity-based prioritization
- Freshness-based secondary sort
- Clear labeling of evidence source

### 5. Finding Detail / Analysis Panel

**Screen elements**:
- Title and severity badge (Critical/Warning/Info)
- Affected resource: namespace, workload name, resource type
- Cluster identity label
- Evidence source badge: Live | Historical | Stale
- Timestamp: when evidence was collected
- **Probable cause**: Natural language explanation derived from evidence
- **Diagnostic evidence section**:
  - Compact signals (key metrics/events)
  - Artifact references with provenance
  - Execution status indicators
- **Diagnostic execution evidence block** (when available):
  - Artifact provenance
  - Execution status
  - Candidate information
  - Usefulness class
  - Compact signals
  - Truncation flags
- **Recommended action**: Specific next diagnostic step or remediation preview

**Behavior**:
- Panel opens on finding click
- Scrollable for detailed evidence
- Evidence source always visible
- No raw stdout/stderr dumps

**Safety label**: "Evidence-based analysis"

### 6. Recommended Action / Fix Panel

**Screen elements**:
- Action title
- Safety mode label:
  - "Read-only" (no execution)
  - "Operator-approved" (requires click to execute)
  - "Demo namespace only" (mutations limited)
  - "Preview only" (shows command, no execution)
- Command preview (for operator-approved actions)
- Affected resources list
- Evidence reference
- Execute button (if mode allows) or "Preview only" label

**Behavior**:
- Shows recommended action derived from diagnostic context
- Command preview visible before execution
- Execute requires explicit operator click
- Progress state shown during execution (if allowed)
- Result state shown after execution
- Evidence preserved throughout

**Safety label**: Mode-specific label required

### 7. Second Finding Or Clean-Cluster Fallback

**Second finding path** (if available):
- Return to feed
- Click second-highest-severity finding
- Show analysis panel with different evidence type
- Demonstrate breadth of diagnostic coverage

**Clean-cluster fallback path** (if no current issues):
- Dashboard shows "No critical issues found"
- Evidence badge shows "Historical Real Run" or "No recent issues"
- Explanation: "This cluster is currently healthy. We can show historical evidence from previous runs."
- Option to "View historical findings"
- Honest statement: "We did not inject fake incidents for the demo."

### 8. Final State

**Screen elements**:
- Dashboard with finding(s) visible
- Evidence source labels preserved
- Action state (if any executed)
- Evidence chain accessible

**Behavior**:
- State persists for review
- Operator can return to any finding
- Evidence provenance always accessible
- No auto-reset or fake state transitions

## Real Finding Selection Priority

### Priority 1: Live Critical Workload Issue

The demo prefers these findings when present:

| Finding Type | Description | Example Evidence |
|-------------|-------------|------------------|
| CrashLoopBackOff | Pod restarting repeatedly | Restart count, exit codes, logs |
| ImagePullBackOff | Container image fetch failure | Image reference, registry error |
| ErrImagePull | Image temporarily unavailable | Network/path issues |
| FailedScheduling | Pod cannot be scheduled | Resource pressure, affinity rules |
| High restart count | Pod exceeding restart threshold | Restart count > threshold |
| NotReady | Pod or node not ready | Readiness probe failures |
| OOMKilled | Container out of memory | Memory limits, exit code |

**Demo behavior**: Display with red Critical badge, Live badge, real diagnostic evidence

### Priority 2: Live Warning-Level Operational Issue

The demo falls back to these when no critical issues exist:

| Finding Type | Description | Example Evidence |
|-------------|-------------|------------------|
| Pending alerts | Unacknowledged warning alerts | Alertmanager state |
| Stale scrape target | Metrics collection gap | Scrape interval vs last success |
| Degraded vmalert rule | Recording rule failure | vmalert rule state |
| Missing metrics | Expected metric absent | Metric discovery results |
| Repeated warning events | Warning-level event pattern | Event count over time |
| Resource pressure warning | Node under memory/CPU pressure | Node conditions |

**Demo behavior**: Display with yellow Warning badge, Live badge, real diagnostic evidence

### Priority 3: Historical Real Evidence

The demo falls back to this when no live issues exist:

| Source | Description | Display Requirements |
|--------|-------------|---------------------|
| Previous health run | Real findings from past scan | Show timestamp, cluster ID |
| Alertmanager history | Past alerts captured by system | Show alert state, duration |
| vmalert history | Past recording rule findings | Show rule name, metric values |
| Command execution artifacts | Prior diagnostic results | Show command, output summary |

**Demo behavior**: Display with "Historical Real Run" badge, show exact timestamp, explain age

### Priority 4: Clean-Cluster Fallback

When no evidence exists (cluster is genuinely healthy):

**Demo behavior**:
- Show dashboard with "No issues found" state
- Evidence badge: "Live scan complete"
- Message: "This cluster is healthy. We have not injected fake incidents."
- Option: "View historical evidence" to show past findings
- Sales narrative: "We prefer to show real issues, but a healthy cluster is also honest evidence of good operations."

**Do NOT**:
- Inject fake failures to make demo more exciting
- Show "demo mode" badges implying artificial data
- Claim the clean state is unusual or concerning

## Minimum UI Requirements

### Start Screen

| Element | Requirement |
|---------|-------------|
| Product name | "K8s Accelerator" |
| Value proposition | One-line, clear, accurate |
| Primary CTA | "Start real-cluster demo" or "Connect cluster" |
| Fake indicators | None allowed |

### Onboarding

| Element | Requirement |
|---------|-------------|
| Kube context selection | Dropdown or auto-detect |
| Cluster label visibility | Show cluster name after connection |
| Connection status | Clear indicator: Connecting → Connected |
| Safety mode selector | Read-only (default), Operator-approved, Demo namespace |
| Confirmation | "Connected" message with cluster identity |

### Dashboard

| Element | Requirement |
|---------|-------------|
| Cluster health summary | Status, cluster label, evidence source |
| Evidence source badge | Live / Historical Real Run / Stale (on each finding) |
| Alert/feed panel | Severity-ranked findings |
| Severity levels | Critical (red), Warning (yellow), Info (blue) |
| Recent diagnostic activity | Last scan time, finding counts |
| Fake sample indicators | None allowed on real findings |

### Alert/Detail Panel

| Element | Requirement |
|---------|-------------|
| Title | Finding type, affected resource |
| Severity | Badge with Critical/Warning/Info |
| Affected resource | Namespace, workload, cluster |
| Evidence source | Live / Historical / Stale badge |
| Probable cause | Natural language, evidence-backed |
| Diagnostic evidence | Compact signals, artifact refs, provenance |
| Diagnostic execution evidence | When available: provenance, status, signals, truncation |
| Recommended action | Specific next step |

### Fix/Action Panel

| Element | Requirement |
|---------|-------------|
| Safety label | Read-only / Operator-approved / Demo namespace / Preview only |
| Command preview | Visible before any execution |
| No raw stdout/stderr | Compact output only |
| Execution confirmation | Explicit click required for mutations |
| Result state | After-action evidence preserved |

## Alert Feed Requirements

| Requirement | Description |
|-------------|-------------|
| Severity sorting | Critical first, then Warning, then Info |
| Source labeling | Each item shows Live/Historical/Stale badge |
| Age indication | Timestamp or "X minutes ago" |
| Cluster identity | Namespace or cluster label on each item |
| Click action | Opens detail panel |
| No fake items | Only real findings from cluster or historical runs |
| Empty state | "No issues found" with honest explanation |

## Analysis Panel Requirements

| Requirement | Description |
|-------------|-------------|
| Evidence block | Show diagnostic signals and provenance |
| Execution evidence | When available: diagnosticExecutionEvidence structure |
| Probable cause | Derived from evidence, not fabricated |
| Recommended action | Based on diagnostic context |
| Provenance chain | Show how finding was derived |
| Timestamp | When evidence was collected |
| No raw dumps | Compact, LLM-friendly output |

## Fix/Action Button Requirements

| Requirement | Description |
|-------------|-------------|
| Mode label | Clearly visible safety mode |
| Command preview | Shows exact command before execution |
| Allowlist indicator | Shows if action is pre-approved |
| Execution confirmation | Requires explicit operator click |
| Progress state | If execution allowed, show progress |
| Result state | After execution, show outcome |
| Evidence preservation | Evidence chain maintained |

## Safety Boundaries For Actions

### Mode 1: Read-only

```
Safety: Always safe
Mutation: None
Execution: Display only
Preview: Shows recommendation
Confirmation: Not required
Evidence: Preserved
```

### Mode 2: Operator-approved

```
Safety: Require explicit operator confirmation
Mutation: Allowlisted commands only
Execution: After click on "Execute"
Preview: Required before execution
Evidence: Preserved
Audit: Action logged
```

### Mode 3: Demo namespace only

```
Safety: Mutations limited to designated demo namespace
Mutation: Allowed only in explicitly labeled demo namespace
Scope: Never targets arbitrary production namespaces
Label: "Demo namespace only" visible
Evidence: Preserved
Audit: Action logged with namespace
```

### Mode 4: Preview only

```
Safety: Always safe
Mutation: None
Execution: Blocked
Preview: Shows command without executing
Evidence: Based on simulation or static analysis
```

## Sales-Safe Wording

**Use these phrases**:

| Phrase | Context |
|--------|---------|
| "real cluster evidence" | When showing actual diagnostic data |
| "live diagnostic signal" | When showing current cluster state |
| "recommended fix" | When showing action preview |
| "operator-approved action" | When showing execution-enabled actions |
| "controlled remediation preview" | When showing action preview without execution |
| "allowlisted action" | When showing pre-approved commands |
| "diagnostic evidence" | When showing evidence block |
| "probable cause" | When explaining finding derivation |
| "observed signal" | When describing collected metrics/events |
| "next recommended action" | When showing diagnostic recommendations |
| "evidence-preserving workflow" | When describing audit trail |
| "historical real evidence" | When showing past findings |
| "live health run" | When showing current scan results |
| "this finding is from a previous run" | When using historical evidence |

## Explicit Non-Claims

**The demo must NOT claim**:

| Non-Claim | Replacement Phrase |
|-----------|---------------------|
| "fully autonomous production remediation" | "operator-approved action preview" |
| "guaranteed root cause" | "probable cause based on evidence" |
| "self-healing cluster" | "diagnostic evidence for informed action" |
| "incident automatically solved in production" | "evidence-backed recommendations for operator review" |
| "the agent fixes any Kubernetes issue" | "diagnostic evidence to support operator decision" |
| "fake demo data" | Never use |
| "simulated incident" | "historical real evidence" or "live finding" |
| "guaranteed resolution" | "recommended next action" |
| "no operator needed" | "operator-visible evidence and approval" |
| "automatic production fixing" | "evidence-driven recommendations" |

## Implementation ACTs Produced From This Storyline

```md
[Open] ACT: Build clickable real-cluster demo path shell
Goal:
Implement Start → Onboarding → Dashboard → Finding detail → Recommended action panel using real cluster state or real historical run data.

Acceptance:
- Start screen with product name and "Connect cluster" CTA
- Onboarding with kube context selection and connection status
- Dashboard showing real findings with Live/Historical/Stale badges
- Finding detail panel with evidence block and provenance
- Action panel with safety mode label and command preview
- Clean-cluster fallback with honest messaging

[Open] ACT: Add real-cluster demo finding selection
Goal:
Select demo findings from live health run evidence first, then warning evidence, then historical real evidence, with clean-cluster fallback.

Acceptance:
- Deterministic finding selection by severity
- Evidence source badge on each finding
- Historical fallback with timestamp visibility
- Clean-cluster success path with honest explanation
- No fake incident injection

[Open] ACT: Add action safety mode labels and remediation preview
Goal:
Add read-only/operator-approved/demo-namespace-only labels and a safe action preview panel without arbitrary mutation.

Acceptance:
- Safety mode visible on action panel
- Command preview before any execution
- Explicit click required for mutations
- Evidence preservation after action
- No raw stdout/stderr exposure

[Open] ACT: Polish demo dashboard UI for 2-minute sales walkthrough
Goal:
Make the dashboard clean, modern, and credible for a short sales demo using real evidence.

Acceptance:
- Clean, modern visual design
- Severity indicators visible
- Evidence source badges prominent
- Finding cards scannable in 30 seconds
- Action panel accessible in 15 seconds
```

## Acceptance Criteria For Demo Readiness

### Document Acceptance

- [x] `docs/reports/k8s-accelerator-real-cluster-demo-storyline.md` exists
- [x] Document defines 2-minute sales demo script with timing table
- [x] Document defines clickable path: Start → Onboarding → Dashboard → Finding 1 → Action → Finding 2/Fallback
- [x] Document explicitly rejects artificial samples as primary demo path
- [x] Document defines allowed evidence sources
- [x] Document defines disallowed evidence sources
- [x] Document defines real finding selection priority (4 levels)
- [x] Document defines clean-cluster fallback behavior
- [x] Document separates truth categories: real capability, demo behavior, controlled actions, future claims
- [x] Document includes safe sales wording table
- [x] Document includes explicit non-claims table
- [x] Document defines minimum UI requirements for all screens
- [x] Document generates follow-up implementation ACTs

### Verification Commands

```bash
# Verify no disallowed phrases
grep -n "fake incident\|fabricated\|artificial sample" docs/reports/k8s-accelerator-real-cluster-demo-storyline.md

# Verify truthfulness markers present
grep -n "real cluster\|real-cluster\|live\|historical real" docs/reports/k8s-accelerator-real-cluster-demo-storyline.md

# Verify safety language present
grep -n "operator-approved\|allowlisted\|read-only\|demo namespace" docs/reports/k8s-accelerator-real-cluster-demo-storyline.md

# Verify disallowed claims absent
grep -n "fully autonomous production remediation\|guaranteed root cause\|self-healing cluster\|fixes any Kubernetes issue" docs/reports/k8s-accelerator-real-cluster-demo-storyline.md || true

# Run docs lint
ruff check docs/reports/k8s-accelerator-real-cluster-demo-storyline.md

# Run full verification gate
./scripts/verify_all.sh
```

### Exit Criteria

1. Document created at `docs/reports/k8s-accelerator-real-cluster-demo-storyline.md`
2. All acceptance criteria marked complete
3. Verification commands pass (or known pre-existing failures documented)
4. Follow-up implementation ACTs generated
5. No misleading capability claims in document

## Close Report

| Item | Value |
|------|-------|
| File created | `docs/reports/k8s-accelerator-real-cluster-demo-storyline.md` |
| Real-cluster demo stance | Live evidence preferred, historical real evidence fallback, clean-cluster honesty last resort |
| Allowed evidence sources | Live scan, historical real runs, diagnostic artifacts, Alertmanager/vmalert evidence, labeled stale evidence |
| Disallowed evidence sources | Fabricated samples, fake incidents, manual CrashLoopBackOff/ImagePullBackOff injection, arbitrary mutation |
| Clean-cluster fallback | Show healthy state with honest messaging, offer historical evidence view, no fake failure injection |
| Action safety modes | Read-only, Operator-approved, Demo namespace only, Preview only |
| Safe wording added | 13 approved phrases, 10 explicit non-claims |
| Follow-up ACTs generated | 4 implementation ACTs: demo path shell, finding selection, action safety labels, UI polish |
| Verification results | Document-level acceptance complete, code verification deferred to implementation ACTs |

**Core principle maintained**: Real cluster first, historical real evidence second, clean-cluster honesty third—no fake incident theater.

# K8s Accelerator Real-Cluster Demo Storyline — Evidence Tables and Specifications

**Parent**: [k8s-accelerator-real-cluster-demo-storyline.md](k8s-accelerator-real-cluster-demo-storyline.md)

This document contains the truth boundaries tables, evidence policy tables, finding priorities, and UI specifications from the demo storyline. For the demo script and clickable path, see [k8s-accelerator-real-cluster-demo-storyline-flow.md](k8s-accelerator-real-cluster-demo-storyline-flow.md).

---

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

---

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

---

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

---

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
| Diagnostic execution evidence | When available: diagnosticExecutionEvidence structure |
| Recommended action | Specific next step |

### Fix/Action Panel

| Element | Requirement |
|---------|-------------|
| Safety label | Read-only / Operator-approved / Demo namespace / Preview only |
| Command preview | Visible before any execution |
| No raw stdout/stderr | Compact output only |
| Execution confirmation | Requires explicit click for mutations |
| Result state | After-action evidence preserved |

---

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

---

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

---

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

---

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
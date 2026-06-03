# K8s Accelerator Real-Cluster Demo Storyline — Step-by-Step Flow

**Parent**: [k8s-accelerator-real-cluster-demo-storyline.md](k8s-accelerator-real-cluster-demo-storyline.md)

This document contains the detailed 2-minute script and clickable demo path from the demo storyline. For the truth boundaries, evidence policy, and implementation ACTs, see the parent document.

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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
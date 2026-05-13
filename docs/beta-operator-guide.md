# Beta Operator Guide

**Purpose:** Help operators, reviewers, and maintainers understand what k9b beta does, how to interpret its outputs, what guarantees it provides, and where its limits are—without reading source code.

**Status:** Beta (2026-05-13)

---

## What the Beta Is For

k9b beta is a Kubernetes diagnostics agent that:

- Collects cluster state and compares peer clusters for suspicious drift
- Produces structured incident reports distinguishing facts from hypotheses
- Generates ranked operator worklists with actionable next checks
- Provides explicit uncertainty and provenance alongside recommendations
- Supports optional LLM-assisted review enrichment (advisory, not authoritative)

The beta is designed for **platform engineers and operators** who need to:
- Detect abnormal cluster states quickly
- Separate signal from interpretation
- Generate grounded diagnostic hypotheses
- Recommend safe next diagnostic steps

---

## What the Beta Is NOT For

The beta does **not**:

- Automatically remediate clusters or apply configuration changes
- Prove root cause with certainty (it surfaces evidence and hypotheses, not proofs)
- Guarantee completeness of diagnostic coverage
- Replace human judgment for high-risk decisions
- Operate as a real-time alerting system (it runs on configured intervals)

---

## Canonical Incident Report

The incident report is the primary situational awareness surface. It contains five claim types:

### Claim Taxonomy

| Claim Type | Description | Example |
|------------|-------------|---------|
| `observed` | Direct telemetry signal | "Warning events observed: 5" |
| `derived` | Deterministic conclusion from evidence fields | "Cluster prod-us health rating is degraded" |
| `hypothesis` | Plausible cause requiring confirmation | "Application misconfiguration causes repeated crashes" |
| `recommendation` | Operator action suggestion with safety level | "Investigate pod events and logs" |
| `unknown` | Explicitly acknowledged missing evidence | "Missing evidence: pod metrics" |

### Section Meanings

**Observed Evidence** (`observed` claims)
- Raw telemetry signals: metrics, event counts, status conditions
- Must have source artifact references
- Never contain causal/root-cause language

**Deterministic Conclusions** (`derived` claims)
- Conclusions deterministically derived from evidence fields
- Include `sourceFields` showing which fields produced the claim
- Examples: health ratings, drift classifications

**Hypotheses** (`inferences` with `hypothesis` claim type)
- Plausible causes requiring operator confirmation
- Always have non-empty `basis` explaining the reasoning
- Must NOT use root-cause language without explicit basis
- Provider-assisted enrichment also appears here with `basis: ["review-enrichment"]`

**Unknowns / Not Proven Yet** (`unknown` claims)
- Missing evidence explicitly surfaced, never omitted
- Each includes `whyMissing` explanation
- Confidence is reduced when unknowns are significant

**Recommended Next Actions** (`recommendation` claims)
- Safety-level-tagged action suggestions
- Separated from findings (actions are not mixed with observations)
- Safety levels: `observe-only`, `low-risk`, `change-with-caution`

### Stale Evidence Warnings

When run freshness is `delayed` or `stale`, the report includes `staleEvidenceWarnings[]` with a clear warning message. This prevents silent reliance on outdated evidence.

---

## Operator Worklist

The worklist is the primary action surface. Each worklist item includes:

| Field | Description |
|-------|-------------|
| `command` | Executable kubectl command (or `null` for advisory checks) |
| `targetCluster` | Target cluster label |
| `targetContext` | Target kube context |
| `reason` | Why this check is recommended |
| `expectedEvidence` | What the check is expected to reveal |
| `safetyNote` | Safety guidance for the operator |
| `itemState` | Current state: `queued`, `approval-needed`, `approved`, `executed`, `reviewed` |
| `rankingReason` | Why this item has its current rank |
| `sourceArtifactRefs` | Source artifacts backing this recommendation |

### Worklist State Semantics

| State | Meaning |
|-------|---------|
| `queued` | Pending automated execution (if safe to automate) |
| `approval-needed` | Requires explicit operator approval before execution |
| `approved` | Operator approved; ready for execution |
| `executed` | Command ran; results available for review |
| `reviewed` | Results reviewed by operator |

### Ranking Rationale

Each worklist item exposes `rankingReason` explaining its position:

| Pattern | Rationale Example |
|---------|-------------------|
| Primary triage, high urgency | `"Primary triage for current degraded workload (high urgency)"` |
| Executable, high priority | `"Executable now; likely to confirm the leading hypothesis"` |
| Approval needed | `"Pending operator approval before execution"` |
| Fleet-level drift | `"Fleet-level drift affects comparable clusters"` |
| Executed item | `"Already executed; retained for result review"` |
| Advisory check | `"Advisory check; method-based diagnostics"` |

---

## Command Semantics

### Diagnostic Pack Review Commands

```bash
# Evaluate a health proposal against a fixture
k8s-diag-agent check-proposal runs/health/proposals/<proposal-id>.json \
  [--fixture tests/fixtures/snapshots/sanitized-alpha.json]
```

### Next-Check Batch Execution

```bash
# Execute eligible checks in batch (dry-run first)
.venv/bin/python scripts/run_batch_next_checks.py --latest --dry-run

# Execute for specific run
.venv/bin/python scripts/run_batch_next_checks.py --run-id <run_id>
```

**Eligibility constraints:**
- `safeToAutomate` must be true
- Must have a valid command family
- Must not require operator approval (or have explicit approval)
- Must not be marked duplicate

### Feedback Loop

```bash
# Export execution results for review
.venv/bin/python scripts/export_next_check_usefulness_review.py --runs-dir runs

# Import reviewed feedback
.venv/bin/python scripts/import_next_check_usefulness_feedback.py \
  --runs-dir runs \
  --input-file runs/health/diagnostic-packs/latest/next_check_usefulness_review.json
```

---

## Source Provenance

Every claim in the incident report includes `sourceArtifactRefs` linking to originating artifacts:

| Claim Source | Artifact Type | Path Pattern |
|--------------|---------------|--------------|
| Telemetry signals | Drilldown | `runs/health/drilldowns/{run_id}-{cluster}.json` |
| Health ratings | Assessment | `runs/health/assessments/{run_id}-{cluster}.json` |
| Hypotheses | Assessment | `runs/health/assessments/{run_id}-{cluster}.json` |
| Provider enrichment | External analysis | `runs/health/external-analysis/{run_id}-review-enrichment-{provider}.json` |

**Provenance filtering:** Skipped, empty, or placeholder artifacts are filtered from operator-facing provenance to reduce noise. See [docs/provenance-filtering.md](provenance-filtering.md).

---

## Temporal Context / Freshness

The `freshness` payload shows whether the current run is keeping up with the configured cadence:

| Status | Meaning | Action |
|--------|---------|--------|
| `fresh` | Run completed within expected interval | Normal operation |
| `delayed` | Run took longer than expected | Check scheduler health |
| `stale` | Run is significantly overdue | Immediate scheduler attention |

When freshness is `delayed` or `stale`, the incident report includes `staleEvidenceWarnings[]` so operators know the evidence may not reflect current cluster state.

---

## Feedback Adaptation Provenance

When operators provide usefulness feedback on executed checks:

1. **Export:** `export_next_check_usefulness_review.py` creates `next_check_usefulness_review.json`
2. **Review:** Operator/classifier adds `usefulness_class` (useful, partial, noisy, empty)
3. **Import:** `import_next_check_usefulness_feedback.py` writes feedback into execution artifacts

This loop closes the adaptation cycle: health runs produce candidates → batch execution runs them → usefulness review lets operators improve recommendation quality over time.

---

## Ownership and Routing Hints

### Unknown Evidence

When evidence is missing, the system:
- Surfaces `unknown` claims with `whyMissing` explanation
- Does NOT hide or invent missing evidence
- Reduces confidence based on significance of gaps

### Cross-Cluster/Fleet-Aware Scenarios

When peer comparison triggers suspicious drift:

- **Trigger artifact** captures why comparison ran (`runs/health/triggers/{run_id}-{primary}.json`)
- **Comparison artifact** shows drift between peers (`runs/health/comparisons/{run_id}-{primary}-vs-{secondary}.json`)
- **Worklist items** with `workstream: "drift"` indicate fleet-level concerns warranting cross-cluster investigation
- **Ranking rationale** surfaces: `"Fleet-level drift affects comparable clusters"`

---

## Known Limitations

### Uncertainty Handling

- **Uncertainty is preserved, not hidden.** The report explicitly surfaces what is unknown rather than filling gaps with confident statements.
- **Confidence levels are qualitative.** The system uses `low`, `medium`, `high` rather than probabilistic percentages.
- **Missing evidence remains visible.** Unknowns are never converted to confident claims.

### Causality

- **The beta cannot prove causality.** It provides supporting evidence and hypotheses. Root-cause language requires explicit non-empty `basis` in hypothesis claims.
- **Correlation ≠ causation.** Fleet-aware conclusions depend on available comparable evidence; absence of drift does not guarantee health.

### Recommendations

- **Recommendations are guidance, not automation.** All actions require operator review; auto-execution only applies to `safeToAutomate=true` checks with explicit approval.
- **Safety levels indicate risk.** Low-risk checks (observe-only, low-risk) are distinguished from higher-risk actions (change-with-caution).

### Evidence Quality

- **Stale or incomplete artifacts remain visible.** The freshness status and stale warnings prevent silent reliance on outdated evidence.
- **Provenance filtering is conservative.** Non-useful artifacts are filtered, but the system preserves minimum provenance to prevent claims appearing without references.

### Fleet-Aware Reasoning

- **Conclusions depend on available comparable evidence.** Cross-cluster reasoning requires peers with matching `cluster_class` and `cluster_role`.
- **Baseline cohorts limit scope.** Drift detection only works when baseline releases/CRDs are accurately declared.

---

## Example: Reading a Degraded Incident Report

**Scenario:** Single degraded cluster with warning events, non-running pods, and missing evidence.

```json
{
  "title": "Degraded health detected in 1 cluster(s)",
  "status": "degraded",
  "affectedScope": "prod-us",
  "facts": [
    {
      "claimType": "observed",
      "statement": "Warning events observed: 5",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/prod-us.json"}],
      "confidence": "high"
    },
    {
      "claimType": "observed",
      "statement": "Non-running pods observed: 2",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/prod-us.json"}],
      "confidence": "high"
    }
  ],
  "derived": [
    {
      "claimType": "derived",
      "statement": "Cluster prod-us health rating is degraded.",
      "sourceFields": ["health_rating"],
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/prod-us.json"}],
      "confidence": "high"
    }
  ],
  "inferences": [
    {
      "claimType": "hypothesis",
      "statement": "Application misconfiguration causes repeated crashes",
      "basis": ["workload"],
      "confidence": "medium",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/prod-us.json"}]
    }
  ],
  "unknowns": [
    {
      "claimType": "unknown",
      "statement": "Missing evidence: events",
      "whyMissing": "Not collected in this run",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/prod-us.json"}]
    }
  ],
  "staleEvidenceWarnings": [],
  "confidence": "medium",
  "freshness": {"ageSeconds": 120, "expectedIntervalSeconds": 300, "status": "fresh"}
}
```

**Interpretation:**
1. **Facts** confirm degraded state with specific signals
2. **Derived** shows health rating determination
3. **Hypothesis** offers a plausible cause with explicit basis
4. **Unknowns** acknowledge missing evidence (not hidden)
5. **Confidence** is `medium` due to unknowns and hypothesis
6. **Freshness** is `fresh` - evidence is current

---

## Example: Worklist Item Interpretation

**Scenario:** Queue item requiring approval before execution.

```json
{
  "description": "Get pod events for my-namespace/my-pod",
  "command": "kubectl get events -n my-namespace --field-selector involvedObject.name=my-pod",
  "targetCluster": "prod-us",
  "targetContext": "admin@prod-us",
  "reason": "Confirm crash loop pattern from warning events",
  "expectedEvidence": "CrashLoopBackOff or ImagePullBackOff events",
  "safetyNote": "Read-only kubectl command; no cluster modifications",
  "itemState": "approval-needed",
  "rankingReason": "Pending operator approval before execution",
  "sourceArtifactRefs": [
    {"label": "Assessment", "path": "assessments/prod-us.json"},
    {"label": "Drilldown", "path": "drilldowns/prod-us.json"}
  ]
}
```

**Interpretation:**
1. **State**: Requires approval (`approval-needed`)
2. **Command**: Safe, read-only kubectl
3. **Reasoning**: Connects to earlier warning events
4. **Safety**: Confirmed low-risk
5. **Provenance**: Backs to assessment and drilldown artifacts

---

## Example: Unknown Evidence with Routing Hint

**Scenario:** Provider-assisted enrichment present, but key metrics missing.

```json
{
  "claimType": "unknown",
  "statement": "Missing evidence: pod metrics",
  "whyMissing": "Metrics collector not responding",
  "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/prod-uk.json"}]
}
```

**Interpretation:**
1. **Missing**: Pod metrics not available
2. **Why**: Metrics collector failure (specific explanation)
3. **Action**: Investigate metrics collector before relying on capacity planning hypotheses

---

## Example: Fleet-Aware Drift Scenario

**Scenario:** Two peer clusters show suspicious drift in control plane version.

```json
{
  "workstream": "drift",
  "description": "Compare control plane versions between prod-us and prod-uk",
  "sourceReason": "Suspicious drift: control plane version mismatch",
  "rankingReason": "Fleet-level drift affects comparable clusters"
}
```

**Interpretation:**
1. **Workstream**: Drift (cross-cluster context)
2. **Ranking**: Indicates fleet-level concern
3. **Action**: Investigate upgrade policies across peer clusters

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [data-model.md](data-model.md) | Detailed data model, run lifecycle, artifact contracts |
| [schemas/incident-report-schema.md](schemas/incident-report-schema.md) | Incident report schema specification |
| [worklist-ranking-rationale.md](worklist-ranking-rationale.md) | Detailed worklist ranking logic |
| [provenance-filtering.md](provenance-filtering.md) | Artifact filtering for operator trust |

---

## Verification

Documentation accuracy is verified through:
- Regression tests in `tests/unit/test_api_incident_report.py`
- Quality rule fixtures in `tests/fixtures/incident_report_quality.py`
- Golden fixtures in `tests/fixtures/incident_report_fixtures.py`

Run verification:
```bash
scripts/verify_all.sh --python-only
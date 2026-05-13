# Beta Stakeholder Demo Script — k9b v0.1.0-beta

**Purpose:** Provide a structured 10–15 minute demo script for presenting k9b beta value to stakeholders, platform leads, SREs, and early-adopter operators.

**Status:** Beta (2026-05-13)

**Demo type:** Live or fixture-based (fixture fallback included)

**Duration:** 10–15 minutes

---

## Demo Title and Objective

**Title:** k9b Beta — Evidence-First Kubernetes Diagnostics

**Objective:** Show how k9b helps platform engineers detect abnormal cluster states, surface evidence-based hypotheses, and recommend safe next diagnostic steps—without overpromising production guarantees.

**Key message:** k9b is an evidence-first diagnostics agent that helps operators separate signal from interpretation, not an automatic remediator.

---

## Pre-Demo Setup Checklist

### Required Before Demo

- [ ] `.venv/bin/python` is functional (run `ls .venv/bin/python`)
- [ ] `scripts/verify_all.sh --python-only` exits 0 (verification gate is green)
- [ ] Fixtures are available: `tests/fixtures/incident_report_fixtures.py`
- [ ] Unit tests pass: `.venv/bin/python -m pytest tests/unit/test_api_incident_report.py -v`
- [ ] Health summary command is available: `.venv/bin/python -m k8s_diag_agent health-summary --help`
- [ ] Chart linting works: `helm lint charts/k9b`

### Optional (Live Cluster Access)

- [ ] `kubectl` configured with access to demo cluster(s)
- [ ] Health config populated: `runs/health-config.local.json` with non-placeholder contexts
- [ ] Run directory exists: `runs/health/`
- [ ] Optional LLM provider configured (LLAMA_CPP_BASE_URL, etc.) for advisory enrichment

### Demo Materials

- [ ] This script printed or displayed on second screen
- [ ] Fixture-based fallback commands ready if live data unavailable
- [ ] Screenshots of expected UI state (if pre-recorded)

---

## Required Local/Server State

### For Fixture-Based Demo

```bash
# Verify fixture tests pass (can show this as proof)
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::GoldenFixtureDegradedSingleClusterTests -v
```

### For Live Demo

```bash
# Verify health summary command works
.venv/bin/python -m k8s_diag_agent health-summary --help

# Check if runs directory exists
ls -la runs/health/ 2>/dev/null || echo "No runs directory yet"

# Check if health config exists
ls runs/health-config.local.json 2>/dev/null || echo "No local config yet"
```

---

## Scenario Overview

### Demo Scenario: Degraded Cluster with Full Claim Taxonomy

**Purpose:** Demonstrate the system correctly surfaces observed facts, derived conclusions, hypotheses, recommendations, and unknowns—without conflating them.

**Source fixture:** `tests/fixtures/incident_report_fixtures.py::_fixture_degraded_single_cluster()`

**Expected behavior:**
- `facts[]`: Contains observed signals (warning events, non-running pods) with sourceArtifactRefs
- `derived[]`: Contains health rating derivation with sourceFields
- `inferences[]`: Contains hypothesis with non-empty basis (not root-cause language)
- `unknowns[]`: Contains missing evidence with whyMissing explanation
- `recommendations[]`: Contains safety-level-tagged action
- `staleEvidenceWarnings[]`: Empty (fresh run)
- `confidence`: Reduced when unknowns are present

---

## Minute-by-Minute Flow

### 0:00–1:00 — Framing (1 minute)

**What to say:**
"Welcome. Today I'll show you k9b beta—an LLM-based Kubernetes diagnostics agent that helps platform engineers and operators detect abnormal cluster states, surface evidence-based hypotheses, and recommend safe next diagnostic steps."

"This is beta software for evaluation and early-adopter feedback. It is not production-ready. We're looking for your honest feedback on what works and what doesn't."

**What to show:**
- Slide or terminal showing the demo objective
- Optional: Open `docs/beta-release-notes.md` to show beta scope

---

### 1:00–3:00 — Beta Contract and Problem Statement (2 minutes)

**What to say:**
"Before we start, let's be clear about what k9b is—and what it isn't."

**k9b beta IS:**
- A diagnostics agent that collects cluster state and surfaces evidence-based findings
- A system that distinguishes facts from hypotheses from recommendations
- A tool that ranks operator worklist items with transparent rationale
- An evidence-first system that shows you what it knows and what it doesn't

**k9b beta is NOT:**
- An automatic remediator (it never applies configuration changes)
- A root-cause proof engine (it provides hypotheses, not proofs)
- A real-time alerting system (it runs on configured intervals)
- A guaranteed diagnostic (coverage is best-effort based on collected evidence)
- Production-ready software (this is a beta for evaluation)

**Show:**
```bash
# Show the beta operator guide section on what k9b is NOT
head -50 docs/beta-operator-guide.md
```

**Key message:** "k9b helps you investigate, not investigate for you."

---

### 3:00–6:00 — Health Summary / Incident Report Walkthrough (3 minutes)

**What to say:**
"Let's look at what k9b actually produces. I'll show you two views: the incident report and the operator worklist."

"The incident report is the primary situational awareness surface. It contains five distinguishable claim types:"

**1. Observed Evidence (facts):**
"Observed claims are direct telemetry signals—metrics, event counts, status conditions. They always have source artifact references so you can trace back to the original evidence."

**2. Deterministic Conclusions (derived):**
"Derived claims are conclusions deterministically derived from evidence fields. Example: 'Cluster prod-us health rating is degraded.' This comes from the health_rating field in the assessment artifact."

**3. Hypotheses (inferences):**
"Hypotheses are plausible causes requiring operator confirmation. They always have non-empty basis explaining the reasoning—and importantly, they do NOT use root-cause language without explicit basis."

**4. Unknowns / Not Proven Yet:**
"Unknowns are explicitly acknowledged missing evidence—never omitted or invented. Each includes whyMissing explanation. Confidence is reduced when unknowns are significant."

**5. Recommended Next Actions:**
"Recommendations are safety-level-tagged action suggestions, separated from findings. Safety levels: observe-only, low-risk, change-with-caution."

**Show (live or fixture):**
```bash
# Run the degraded fixture test to show the incident report structure
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::GoldenFixtureDegradedSingleClusterTests -v

# Or show the fixture source
grep -A 100 "_fixture_degraded_single_cluster" tests/fixtures/incident_report_fixtures.py | head -80
```

**Show the schema:**
```bash
# Open the incident report schema
head -100 docs/schemas/incident-report-schema.md
```

---

### 6:00–9:00 — Worklist and Evidence Provenance (3 minutes)

**What to say:**
"The operator worklist is the primary action surface. Each worklist item includes:"

- **command**: Executable kubectl command (or null for advisory checks)
- **targetCluster**: Target cluster label
- **targetContext**: Target kube context
- **reason**: Why this check is recommended
- **expectedEvidence**: What the check is expected to reveal
- **safetyNote**: Safety guidance for the operator
- **itemState**: Current state: queued, approval-needed, approved, executed, reviewed
- **rankingReason**: Why this item has its current rank
- **sourceArtifactRefs**: Source artifacts backing this recommendation

**Show the ranking rationale:**
"The ranking rationale tells you why each item has its current rank. Examples:"

- "Primary triage for current degraded workload (high urgency)"
- "Executable now; likely to confirm the leading hypothesis"
- "Pending operator approval before execution"
- "Fleet-level drift affects comparable clusters"
- "Already executed; retained for result review"

**Show provenance:**
"Every claim includes sourceArtifactRefs linking to originating artifacts. This means every finding, every hypothesis, every recommendation traces back to the evidence that produced it."

"We filter out skipped, empty, or placeholder artifacts to reduce noise—but we preserve minimum provenance so claims never lose all references."

**Show:**
```bash
# Run the worklist ranking tests
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::WorklistRankingRationaleTests -v

# Show the provenance filtering doc
head -80 docs/provenance-filtering.md
```

---

### 9:00–11:00 — Stale Evidence / Uncertainty / Known Limits (2 minutes)

**What to say:**
"Now let's talk about uncertainty—because ignoring uncertainty is how you get into trouble."

**Stale evidence handling:**
"When run freshness is delayed or stale, the report includes staleEvidenceWarnings. This prevents silent reliance on outdated evidence. If freshness is stale, you should check scheduler health before acting on evidence."

**Provider-assisted content is advisory:**
"k9b supports optional LLM-assisted review enrichment. When present, it appears in the inferences section with basis: ['review-enrichment']. It is NEVER in facts—always advisory, never authoritative."

**Explicit uncertainty:**
"Unknowns are never hidden or filled with confident statements. Confidence levels are qualitative: low, medium, high—not probabilistic percentages."

**Show:**
```bash
# Run the stale evidence fixture test
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::GoldenFixtureStaleProviderEnrichedDegradedTests -v

# Show the known limits section
sed -n '89,120p' docs/beta-release-notes.md
```

**Key message:** "If evidence is stale or missing, k9b tells you—not because it's cautious, but because silent confidence is dangerous."

---

### 11:00–13:00 — Deployment/Package Story (2 minutes)

**What to say:**
"k9b ships as a Helm chart for Kubernetes deployment. Let me show you the key deployment options."

**Backend configuration:**
"backend.env.HEALTH_UI_HOST defaults to 0.0.0.0 for in-cluster access. To expose externally, you need backend.unsafeBind=true plus uiAuth.enabled=true."

**Scheduler:**
"The scheduler runs the health loop on configured intervals. It exposes a UI/API server bound to 0.0.0.0:8080 by default—this requires --unsafe-bind flag."

**Security:**
"Mutation endpoints are protected by bearer token authentication when K9B_UI_TOKEN is configured. GET endpoints remain unprotected unless you place k9b behind a reverse proxy."

**Show:**
```bash
# Lint the chart
helm lint charts/k9b

# Template the chart to show default values
helm template infra-k9b charts/k9b | head -100

# Show the relevant README section
sed -n '82,148p' charts/k9b/README.md
```

**Key message:** "k9b is designed for in-cluster deployment with read-only diagnostics access. External exposure requires explicit acknowledgement via unsafeBind plus authentication."

---

### 13:00–15:00 — Close, Feedback Ask, Next Steps (2 minutes)

**What to say:**
"Let's recap what we've seen today:"

**What k9b solves:**
- Evidence-first diagnostics with traceable provenance
- Five distinguishable claim types so you can trace conclusions
- Ranked operator worklist with transparent rationale
- Explicit uncertainty and stale evidence handling
- Optional LLM-assisted enrichment (advisory only)
- Fleet-aware drift detection across peer clusters

**What k9b does NOT do:**
- Automatic remediation
- Root-cause proof
- Real-time alerting
- Guaranteed diagnostic completeness
- Production deployment (this is beta)

**Feedback ask:**
"We're actively collecting feedback on:
- Diagnostic accuracy and usefulness of recommendations
- Clarity of claim taxonomy and provenance
- Deployment and configuration experience
- UI/UX improvements for the worklist and incident report
- Any gaps in coverage or evidence collection"

**Next steps:**
1. Review the beta release notes: `docs/beta-release-notes.md`
2. Try the fixture-based tests: `scripts/verify_all.sh --python-only`
3. Explore the operator guide: `docs/beta-operator-guide.md`
4. Provide feedback via the repo's issue tracker

**Show:**
```bash
# Show the verification gate
scripts/verify_all.sh --python-only

# Show the demo readiness checklist
head -100 docs/beta-demo-readiness-checklist.md
```

---

## Commands to Run

### Fixture-Based Verification

```bash
# Full Python lane verification
scripts/verify_all.sh --python-only

# Incident report tests (covers scenarios 1-9)
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py -v

# Worklist ranking tests (scenario 10)
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::WorklistRankingRationaleTests -v

# Cross-cluster findings tests
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::CrossClusterFindingsTests -v

# Feedback adaptation tests
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::FeedbackAdaptationProvenanceTests -v
```

### Live Demo Commands

```bash
# Health summary
.venv/bin/python -m k8s_diag_agent health-summary --runs-dir runs/health

# Health loop (one-shot)
.venv/bin/python -m k8s_diag_agent run-health-loop --once --runs-dir runs/health

# Diagnostic pack review
.venv/bin/python scripts/diagnostic_pack_review.py runs/health/diagnostic-packs/latest/

# Batch next-check execution (dry-run first)
.venv/bin/python scripts/run_batch_next_checks.py --latest --dry-run

# Helm chart verification
helm lint charts/k9b
helm template infra-k9b charts/k9b
```

### Fixture-Based Fallback (No Live Cluster)

```bash
# Show degraded single-cluster fixture
grep -A 150 "_fixture_degraded_single_cluster" tests/fixtures/incident_report_fixtures.py

# Show healthy no-incident fixture
grep -A 50 "_fixture_healthy_no_incident" tests/fixtures/incident_report_fixtures.py

# Show stale provider-enriched fixture
grep -A 150 "_fixture_stale_provider_enriched_degraded" tests/fixtures/incident_report_fixtures.py

# Show helm release drift fixture
grep -A 100 "_fixture_helm_release_drift" tests/fixtures/incident_report_cross_cluster_fixtures.py
```

---

## Screens/Artifacts to Open

### Pre-Recorded Screenshots (Optional)

1. **Incident Report Card** — Shows claim taxonomy sections (observed, derived, hypothesis, unknown, recommendation)
2. **Operator Worklist** — Shows ranked items with state badges (queued, approval-needed, executed, reviewed)
3. **Health Summary Dashboard** — Shows fleet status, degraded clusters, next checks
4. **Evidence Provenance** — Shows source artifact links and filtering behavior

### Artifact References

1. **Incident Report Schema:** `docs/schemas/incident-report-schema.md`
2. **Worklist Ranking Rationale:** `docs/worklist-ranking-rationale.md`
3. **Provenance Filtering:** `docs/provenance-filtering.md`
4. **Beta Release Notes:** `docs/beta-release-notes.md`
5. **Beta Operator Guide:** `docs/beta-operator-guide.md`
6. **Beta Demo Readiness Checklist:** `docs/beta-demo-readiness-checklist.md`
7. **Helm Chart README:** `charts/k9b/README.md`

---

## Speaker Notes

### Key Talking Points

1. **Evidence-first, not assumption-first:** Every finding traces back to an artifact. No silent leaps from symptom to conclusion.

2. **Claim taxonomy is the key differentiator:** Most diagnostic tools mix facts, hypotheses, and recommendations. k9b separates them deliberately.

3. **Provenance filtering reduces noise:** Operators don't see skipped artifacts or placeholder failures—just the evidence that matters.

4. **Uncertainty is a feature, not a bug:** Stale warnings, unknown claims, and whyMissing explanations keep operators honest.

5. **Provider-assisted content is advisory:** LLM enrichment never lands in facts—always in inferences with explicit basis.

6. **Worklist ranking is transparent:** rankingReason explains why each item is ranked where it is, not just what to do.

### Phrases to Use

- "This is evidence, not proof."
- "k9b recommends; you decide."
- "If k9b doesn't know something, it tells you."
- "Every finding traces back to an artifact."
- "Provider enrichment is advisory, never authoritative."

### Phrases to Avoid

- ❌ "k9b found the root cause"
- ❌ "The system automatically fixes this"
- ❌ "k9b guarantees diagnostic completeness"
- ❌ "This is production-ready"
- ❌ "k9b provides real-time alerting"

---

## Expected Audience Questions and Safe Answers

### Q: Does k9b automatically remediate clusters?

**A:** No. The beta does not apply configuration changes or remediate clusters. All high-risk actions require operator review. k9b recommends next steps; you decide and execute.

---

### Q: Can k9b prove root cause?

**A:** No. k9b provides supporting evidence and hypotheses, not proofs. Root-cause language requires explicit non-empty basis in hypothesis claims. Correlation is not causation.

---

### Q: Does k9b provide real-time alerting?

**A:** No. k9b runs on configured intervals, not as a continuous alerting system. For real-time alerting, integrate with your existing Alertmanager setup.

---

### Q: How does k9b handle missing evidence?

**A:** Unknowns are explicitly surfaced with whyMissing explanation—never omitted or invented. Confidence is reduced when unknowns are significant. Stale/delayed evidence triggers explicit warnings.

---

### Q: Is LLM-assisted enrichment reliable?

**A:** Provider-assisted content is advisory only and appears in inferences[] with basis: ["review-enrichment"]. It is never authoritative. k9b works deterministically without LLM enrichment.

---

### Q: What clusters can k9b monitor?

**A:** k9b supports any Kubernetes cluster accessible via kubeconfig. Cross-cluster drift detection requires peers with matching cluster_class and cluster_role.

---

### Q: Can k9b run in production?

**A:** This is beta software for evaluation and early-adopter feedback. Production deployment is out of scope for the beta.

---

### Q: How does k9b compare to X (Prometheus, Datadog, etc.)?

**A:** k9b is a diagnostics agent that helps investigate abnormal states, not a metrics collection or monitoring system. It complements existing observability stacks by providing evidence-based hypotheses and ranked next checks.

---

### Q: What happens if the LLM provider is unavailable?

**A:** k9b degrades gracefully. Deterministic collection, assessment, and proposal generation continue unaffected. Provider-assisted enrichment is skipped with a logged reason.

---

## Failure Fallback Plan

### If Live Cluster Access Fails

1. **Fallback:** Use fixture-based demonstration
2. **Command:** `.venv/bin/python -m pytest tests/unit/test_api_incident_report.py -v`
3. **Show:** Fixture source code as sample incident report
4. **Explain:** "Fixtures demonstrate the same behavior as live runs"

### If Health Config is Empty

1. **Fallback:** Show fixture-based scenario walkthrough
2. **Command:** `grep -A 100 "_fixture_degraded_single_cluster" tests/fixtures/incident_report_fixtures.py`
3. **Explain:** "This is the data k9b produces for a degraded cluster"

### If Helm Template Fails

1. **Fallback:** Show the chart README documentation
2. **Command:** `cat charts/k9b/README.md | head -150`
3. **Explain:** "The chart templates correctly—this is just demo setup"

### If Unit Tests Fail

1. **Do not proceed with demo until resolved**
2. **Run verification:** `scripts/verify_all.sh --python-only`
3. **Check recent changes:** `git diff HEAD~1`
4. **Report as blocker:** Document the failing test and error message

---

## Files Changed

| File | Purpose |
|------|---------|
| `docs/beta-stakeholder-demo-script.md` | New: Structured 10–15 minute stakeholder demo script |

---

## Verification

Run the following to verify demo materials are correct:

```bash
# Full Python lane verification
scripts/verify_all.sh --python-only

# Expected output: VERIFICATION GATE: PASSED
```

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [docs/beta-release-notes.md](beta-release-notes.md) | Beta overview, changelog, known limits, verification status |
| [docs/beta-operator-guide.md](beta-operator-guide.md) | Operator-facing contract, claim taxonomy, command semantics |
| [docs/beta-demo-readiness-checklist.md](beta-demo-readiness-checklist.md) | Representative scenarios, inspection steps, acceptance criteria |
| [docs/data-model.md](data-model.md) | Detailed data model, run lifecycle, artifact contracts |
| [docs/schemas/incident-report-schema.md](schemas/incident-report-schema.md) | Incident report schema specification |
| [docs/worklist-ranking-rationale.md](worklist-ranking-rationale.md) | Detailed worklist ranking logic |
| [docs/provenance-filtering.md](provenance-filtering.md) | Artifact filtering for operator trust |
| [charts/k9b/README.md](../charts/k9b/README.md) | Helm chart deployment and configuration |

---

## Epic Status Recommendation

When this task is complete, update the epic board:

```
- [Closed] Beta release notes and changelog
- [Closed] Beta deployment/package validation
- [Closed] Beta stakeholder demo script  ← This task
- [Open] Post-beta backlog triage
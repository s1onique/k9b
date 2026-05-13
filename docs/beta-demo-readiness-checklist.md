# Beta Demo and Readiness Checklist

**Purpose:** Help reviewers, operators, and maintainers inspect completed beta behavior without tribal knowledge.

**Status:** Beta (2026-05-13)  
**Parent Epic:** Beta hardening and release readiness  
**Related:** [docs/beta-operator-guide.md](beta-operator-guide.md)

---

## Scope

This document defines representative beta scenarios, inspection steps, expected behavior, and acceptance criteria.

**Non-goals:**
- No new product features
- No fabricated fixtures or artifacts
- No overclaiming root-cause certainty or automation

---

## Representative Scenarios

### Scenario 1: Single Degraded Cluster with Full Claim Taxonomy

**Purpose:** Demonstrate that the system correctly surfaces observed facts, derived conclusions, hypotheses, recommendations, and unknowns—without conflating them.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_fixtures.py::_fixture_degraded_single_cluster()`

**How to inspect:**

```bash
# Run the unit test that validates this fixture
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::GoldenFixtureDegradedSingleClusterTests -v
```

**Expected incident report behavior:**
- `facts[]`: Contains observed signals (warning events, non-running pods) with sourceArtifactRefs
- `derived[]`: Contains health rating derivation with sourceFields
- `inferences[]`: Contains hypothesis with non-empty basis (not root-cause language)
- `unknowns[]`: Contains missing evidence with whyMissing explanation
- `recommendations[]`: Contains safety-level-tagged action
- `staleEvidenceWarnings[]`: Empty (fresh run)
- `confidence`: Reduced when unknowns are present

**Expected worklist behavior:**
- Queue items present with `itemState: approval-needed` or `itemState: queued`
- Each item has `rankingReason` explaining its position
- Each item has `sourceArtifactRefs` backing the recommendation

**Acceptance checklist:**
- [ ] observed vs derived vs hypothesis vs recommendation vs unknown are clearly separated
- [ ] hypothesis has non-empty basis; no root-cause language without explicit basis
- [ ] unknowns include whyMissing explanation
- [ ] provenance links to real artifact paths (no fake "unknown" paths)
- [ ] worklist items expose command, targetCluster, targetContext, reason, expectedEvidence, safetyNote, itemState, rankingReason

---

### Scenario 2: Healthy Cluster with Honest Empty State

**Purpose:** Verify that the system does not invent concerns where none exist.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_fixtures.py::_fixture_healthy_no_incident()`

**How to inspect:**

```bash
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::GoldenFixtureHealthyNoIncidentTests -v
```

**Expected incident report behavior:**
- `status`: "healthy"
- `title`: "No degraded clusters detected"
- `facts[]`: Contains honest statement about no incidents (not fabricated findings)
- `inferences[]`: Empty
- `unknowns[]`: Empty
- `staleEvidenceWarnings[]`: Empty
- `recommendedActions[]`: Empty

**Acceptance checklist:**
- [ ] No degraded clusters invented
- [ ] No hypotheses surfaced for healthy state
- [ ] No recommendations for healthy state

---

### Scenario 3: Feedback Adaptation Provenance (Useful Result)

**Purpose:** Demonstrate that useful feedback strengthens the leading hypothesis and surfaces adaptation provenance.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_fixtures.py::_fixture_useful_result_hypothesis_strengthened()`

**How to inspect:**

```bash
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::FeedbackAdaptationProvenanceTests::test_useful_result_hypothesis_strengthened -v
```

**Expected worklist behavior:**
- Executed item has `usefulnessClass: useful`
- `adaptationEffect: hypothesis_strengthened`
- `adaptationSummary` includes hypothesis strengthening context
- `itemState: reviewed`

**Expected provenance behavior:**
- Feedback attribution is traceable via `next_check_execution_history`
- Adaptation effect is visible in UI worklist projection

**Acceptance checklist:**
- [ ] Useful feedback is linked to adaptation provenance
- [ ] Hypothesis strengthening is visible
- [ ] No silent overwriting of diagnosis based on noisy feedback

---

### Scenario 4: Feedback Adaptation Provenance (Noisy Result)

**Purpose:** Verify that noisy feedback is not treated as useful and does not change diagnosis.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_fixtures.py::_fixture_noisy_result_no_material_change()`

**How to inspect:**

```bash
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::FeedbackAdaptationProvenanceTests::test_noisy_result_no_material_change -v
```

**Expected worklist behavior:**
- Executed item has `usefulnessClass: noisy`
- `adaptationEffect: no_material_change`
- `adaptationSummary` honestly represents no diagnostic impact
- `itemState: reviewed`

**Acceptance checklist:**
- [ ] Noisy feedback is not treated as useful
- [ ] Diagnosis is not silently rewritten based on noisy feedback
- [ ] Feedback doesn't silently rewrite facts

---

### Scenario 5: Feedback Adaptation Provenance (Partial Result)

**Purpose:** Verify that partial feedback is not treated as fully conclusive.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_fixtures.py::_fixture_partial_result_unknown_resolved()`

**How to inspect:**

```bash
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::FeedbackAdaptationProvenanceTests::test_partial_result_unknown_resolved -v
```

**Expected worklist behavior:**
- Executed item has `usefulnessClass: partial`
- `adaptationEffect: unknown_resolved`
- `adaptationSummary` indicates evidence gap was partially filled

**Acceptance checklist:**
- [ ] Partial feedback is not treated as fully conclusive
- [ ] Unknown resolution is visible in adaptation summary

---

### Scenario 6: Fleet-Aware Drift Scenario (Helm Release Drift)

**Purpose:** Verify that cross-cluster drift is surfaced without masquerading as single-cluster root cause.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_cross_cluster_fixtures.py::_fixture_helm_release_drift()`

**How to inspect:**

```bash
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::CrossClusterFindingsTests::test_helm_release_drift -v
```

**Expected incident report behavior:**
- `status`: "healthy" (per-cluster, but cross-cluster findings present)
- `crossClusterFindings[]`: Non-empty with helm_releases drift
- `recommendedNextChecks[]`: Includes "Compare Helm release versions across same-role clusters"

**Expected worklist behavior:**
- Worklist items with `workstream: "drift"` indicate fleet-level concerns
- `rankingReason`: "Fleet-level drift affects comparable clusters"

**Acceptance checklist:**
- [ ] Cross-cluster findings surface without overstating causality
- [ ] Helm drift is not surfaced as single-cluster root cause
- [ ] Fleet-aware recommendations are present for helm drift

---

### Scenario 7: Fleet-Aware Drift Scenario (Control Plane Version)

**Purpose:** Verify that control plane version drift is surfaced correctly.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_cross_cluster_fixtures.py::_fixture_control_plane_drift()`

**How to inspect:**

```bash
.venv/bin python -m pytest tests/unit/test_api_incident_report.py::CrossClusterFindingsTests::test_control_plane_drift -v
```

**Expected incident report behavior:**
- `crossClusterFindings[]`: Non-empty with metadata drift
- `recommendedNextChecks[]`: Includes "Check control plane version consistency across fleet"

**Acceptance checklist:**
- [ ] Control plane version drift is surfaced
- [ ] Fleet-aware recommendations are present

---

### Scenario 8: Mixed Degraded and Cross-Cluster (Helm Drift)

**Purpose:** Verify that both per-cluster degradation and cross-cluster drift are surfaced without interference.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_cross_cluster_fixtures.py::_fixture_cross_cluster_drift_with_degraded_workload()`

**How to inspect:**

```bash
.venv/bin python -m pytest tests/unit/test_api_incident_report.py::CrossClusterFindingsTests::test_mixed_degraded_and_cross_cluster -v
```

**Expected incident report behavior:**
- `status`: "degraded" (per-cluster perspective)
- `facts[]`: Non-empty (per-cluster drilldown findings)
- `crossClusterFindings[]`: Non-empty (fleet-level drift)

**Acceptance checklist:**
- [ ] Cross-cluster findings are not overshadowed by per-cluster degradation
- [ ] Cross-cluster drift does not masquerade as single-cluster root cause

---

### Scenario 9: Stale Evidence Warning

**Purpose:** Verify that stale evidence is flagged and does not lead to silent reliance on outdated data.

**Inspection type:** Inspection-only (uses test fixture)

**Source fixture:** `tests/fixtures/incident_report_fixtures.py::_fixture_stale_provider_enriched_degraded()`

**How to inspect:**

```bash
.venv/bin python -m pytest tests/unit/test_api_incident_report.py::GoldenFixtureStaleProviderEnrichedDegradedTests -v
```

**Expected incident report behavior:**
- `freshness.status`: "stale" or "delayed"
- `staleEvidenceWarnings[]`: Non-empty with warning message
- Provider-assisted content appears only in `inferences[]` with `basis: ["review-enrichment"]`

**Acceptance checklist:**
- [ ] Stale evidence creates staleEvidenceWarnings
- [ ] Freshness status is visible
- [ ] Provider-assisted content never appears in facts (always in inferences)

---

### Scenario 10: Worklist Item Ranking Rationale

**Purpose:** Verify that worklist item ranking is transparent and interpretable.

**Inspection type:** Inspection-only (uses test fixture)

**How to inspect:**

```bash
.venv/bin python -m pytest tests/unit/test_api_incident_report.py::WorklistRankingRationaleTests -v
```

**Expected worklist behavior:**
- Every ranked item has `rankingReason`
- Rationale aligns with actual item state (executed items don't claim "pending")
- Advisory items (null command) are not described as immediately executable
- Drift items mention fleet-level context

**Acceptance checklist:**
- [ ] Primary triage items have triage rationale
- [ ] Executable items have appropriate rationale
- [ ] Approval-needed items mention approval
- [ ] Drift items mention fleet
- [ ] Executed items mention execution (not pending)
- [ ] Rationale is concise (under 80 characters)

---

## Running the Demo Scenarios

### Local Verification (Python Lane)

```bash
# Run all incident report tests (covers scenarios 1-9)
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py -v

# Run worklist ranking tests (scenario 10)
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::WorklistRankingRationaleTests -v

# Run cross-cluster findings tests
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::CrossClusterFindingsTests -v

# Run feedback adaptation tests
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::FeedbackAdaptationProvenanceTests -v
```

### Full Verification Gate

```bash
# Full gate (all lanes)
scripts/verify_all.sh

# Python lane only (for documentation-focused verification)
scripts/verify_all.sh --python-only
```

---

## Release-Readiness Checklist

### Verification Gate

- [ ] Full verification gate passes (`scripts/verify_all.sh` exits with 0)
- [ ] Python lane passes (ruff-lint, unit-tests, mypy)
- [ ] No new regressions introduced

### Documentation

- [ ] [docs/beta-operator-guide.md](beta-operator-guide.md) is present and accurate
- [ ] This demo/readiness checklist is present and accurate
- [ ] Known limitations are documented in the operator guide
- [ ] No major trust gap between product behavior and docs

### Operator Contract

- [ ] Observed vs derived vs hypothesis vs recommendation vs unknown is distinguishable
- [ ] sourceArtifactRefs link to real artifacts (no fake paths)
- [ ] worklist item ranking is transparent via rankingReason
- [ ] Command safety levels are visible (safe/approval-needed/executed/reviewed)
- [ ] Stale/delayed evidence is visible via staleEvidenceWarnings
- [ ] fleet-aware reasoning limits are documented

### Feedback Loop

- [ ] Feedback adaptation provenance is visible in worklist items
- [ ] Useful feedback strengthens hypotheses
- [ ] Noisy feedback doesn't silently rewrite diagnosis
- [ ] Partial feedback is not treated as fully conclusive

### Cross-Cluster/Fleet Reasoning

- [ ] Drift detection surfaces without claiming causation
- [ ] Fleet-aware recommendations include drift investigation steps
- [ ] Healthy clusters with suspicious comparisons are handled correctly

---

## Reviewer Checklist

When reviewing the beta, use this checklist to verify system correctness:

### Claim Taxonomy

- [ ] Can identify observed (facts), derived, hypothesis (inferences), recommendation, and unknown claims
- [ ] Can trace claims to sourceArtifactRefs
- [ ] Can verify that hypothesis has non-empty basis
- [ ] Can verify that unknowns include whyMissing

### Worklist Behavior

- [ ] Can understand why a worklist item is ranked (rankingReason)
- [ ] Can tell whether a command is safe/approval-needed/executed/reviewed
- [ ] Can verify that advisory items (null command) are not described as executable

### Evidence Quality

- [ ] Can identify stale/delayed evidence via staleEvidenceWarnings
- [ ] Can verify freshness status is visible
- [ ] Can verify that provider-assisted content is never in facts (always in inferences)

### Fleet-Aware Reasoning

- [ ] Can identify cross-cluster drift findings
- [ ] Can verify that drift is not masquerading as single-cluster root cause
- [ ] Can understand the limits of fleet-aware reasoning (depends on available comparable evidence)

### Feedback Adaptation

- [ ] Can trace useful feedback to hypothesis strengthening
- [ ] Can verify that noisy feedback is not treated as useful
- [ ] Can verify that partial feedback is not treated as fully conclusive

---

## Known Limitations

The beta has documented limits that reviewers should be aware of:

1. **Causality**: The system cannot prove causality. It provides supporting evidence and hypotheses. Root-cause language requires explicit non-empty basis in hypothesis claims.

2. **Evidence quality**: Stale or incomplete artifacts remain visible. The freshness status and stale warnings prevent silent reliance on outdated evidence.

3. **Fleet-aware reasoning**: Conclusions depend on available comparable evidence. Cross-cluster reasoning requires peers with matching cluster_class and cluster_role. Baseline cohorts limit scope.

4. **Recommendations are guidance**: All actions require operator review; auto-execution only applies to safeToAutomate=true checks with explicit approval.

5. **Uncertainty is preserved**: The system does not fill gaps with confident statements. Confidence levels are qualitative (low/medium/high), not probabilistic percentages.

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [beta-operator-guide.md](beta-operator-guide.md) | Operator-facing contract, claim taxonomy, command semantics |
| [schemas/incident-report-schema.md](schemas/incident-report-schema.md) | Incident report schema specification |
| [worklist-ranking-rationale.md](worklist-ranking-rationale.md) | Detailed worklist ranking logic |
| [provenance-filtering.md](provenance-filtering.md) | Artifact filtering for operator trust |
| [data-model.md](data-model.md) | Detailed data model, run lifecycle, artifact contracts |

---

## Files Changed

This document introduces:

| File | Purpose |
|------|---------|
| `docs/beta-demo-readiness-checklist.md` | Representative scenarios, inspection steps, acceptance criteria |

---

## Verification Result

Run the following to verify documentation accuracy:

```bash
# Verify all scenarios pass
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py -v

# Verify full gate
scripts/verify_all.sh --python-only
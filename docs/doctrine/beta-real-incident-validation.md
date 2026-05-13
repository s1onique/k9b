# Beta Real-Incident Validation and Gap Closure

**Epic**: Beta real-incident validation and gap closure  
**Status**: Open  
**Date**: 2026-05-13  
**Driver**: Product validation  

---

## Goal

Validate the beta incident-report + operator-worklist workflow against realistic incident scenarios and use findings to drive the next round of product improvements.

---

## Context

The beta product contract is now in place:

- canonical incident report  
- canonical operator worklist  
- operator-first UI  
- deterministic truthfulness and scoring harness  

The next step is to test whether this works well on realistic incidents, not just contract fixtures.

---

## Requirements

- Prefer replayable/sanitized incident scenarios first  
- Reuse the existing scoring harness where possible  
- Keep evidence-first and artifact-first behavior  
- Focus on operational usefulness, not model theater  
- Produce a concrete gap backlog from observed failures  

---

## Deliverables

1. Select representative real/sanitized incident scenarios  
2. Replay them through the beta workflow  
3. Score report quality and worklist usefulness  
4. Identify failure modes:  
   - missed detection  
   - late detection  
   - weak ranking  
   - misleading inference  
   - missing/under-explained unknowns  
   - poor operator actionability  
5. Produce a prioritized follow-up backlog of beta gaps  
6. Document what the beta currently handles well vs poorly  

---

## Scenario Inventory

### Synthetic Fixture Scenarios

| Scenario | Fixture | Description |
|----------|---------|-------------|
| Healthy | `_fixture_healthy_no_incident` | No degraded clusters, no provider enrichment |
| Degraded | `_fixture_degraded_single_cluster` | Assessment + drilldown, missing evidence, worklist items |
| Stale + Enriched | `_fixture_stale_provider_enriched_degraded` | Stale freshness, review_enrichment present |
| Deterministic Only | `_fixture_deterministic_only_no_command` | Deterministic next checks, no queue items |
| Approval Needed | `_fixture_approval_needed_item` | Queue item requiring operator approval |
| Executed + Usefulness | `_fixture_executed_with_usefulness` | Executed item with usefulness feedback |
| Queue with Command | `_fixture_queue_with_command` | Queue item with executable command |
| Duplicate Candidates | `_fixture_duplicate_candidates` | Merged provenance when same action from multiple sources |

### Real Run Scenarios (Rees46 Fleet)

| Run Period | Clusters | Scenario Type |
|------------|----------|----------------|
| 2026-04-05 to 2026-04-08 | rees46-ru, rees46-kz, rees46-naumen | Control plane drift, Helm release drift |
| 2026-04-06 to 2026-04-08 | cluster1, cluster2, cluster3 | Multi-cluster comparison drift |
| 2026-04-07 to 2026-04-11 | cluster1-3 | External analysis + review enrichment |
| 2026-04-10 to 2026-04-11 | cluster1-3 | Diagnostic pack generation |

### Real Scenario Categories

1. **Healthy baseline**: Runs where all clusters show healthy status
2. **Helm drift**: Differences in Helm releases between same-role clusters
3. **Control plane drift**: Version differences between clusters
4. **CRD drift**: Custom resource definition differences
5. **Degraded workload**: Non-running pods, warning events
6. **Approval-gated**: Planner candidates requiring operator approval
7. **Executed**: Next checks that completed and have feedback

---

## Scoring Harness

### Quality Rules (incident_report_quality.py)

The existing scoring harness enforces 9 deterministic rules:

1. **observed_no_causal_language**  
   Observed claims must not contain causal/root-cause language  
   Forbidden phrases: root cause, caused by, because of, is the cause, the cause of, directly caused, responsible for  

2. **derived_no_causal_language**  
   Derived claims must not contain unsupported causal/root-cause language  

3. **hypotheses_have_basis**  
   Hypothesis claims must have non-empty basis  

4. **unknowns_have_why_missing**  
   Unknown claims must have whyMissing explanation  

5. **recommendations_separated**  
   Recommendations must be under "Recommended next actions", NOT mixed with findings  

6. **section_headings_concise**  
   Section headings remain concise (under 50 characters)  

7. **claim_statements_short**  
   Claim statements are reasonably short (under 200 characters)  

8. **no_filler_phrases**  
   No generic filler phrases in claim statements  
   Forbidden: the system has identified, potentially relevant diagnostic indicators, various issues, etc.  

9. **report_has_full_degraded_shape**  
   Report answers what is observed, derived, hypothesized, unknown, recommended  

### Worklist Quality Checks

From `incident_report_fixtures.py`:

- Provider-assisted review enrichment must not appear in facts  
- Unknowns/missing evidence must be explicit  
- Stale evidence must create staleEvidenceWarnings  
- sourceArtifactRefs must be real links or empty, never fake "unknown" paths  
- Deterministic next checks with no executable command must keep command null  
- Queue/worklist items with executable command must expose command, target/context, reason, expected evidence, safety note, and state  

---

## Replay Procedure

### Step 1: Select Representative Scenarios

For this epic, select:

1. **S1: Healthy baseline**  
   - Fixture: `_fixture_healthy_no_incident`  
   - Expectation: honest empty report, no false positives  

2. **S2: Degraded with missing evidence**  
   - Fixture: `_fixture_degraded_single_cluster`  
   - Expectation: non-empty facts/derived/inferences/unknowns/recommendations  

3. **S3: Stale with provider enrichment**  
   - Fixture: `_fixture_stale_provider_enriched_degraded`  
   - Expectation: stale warnings, enrichment in inferences NOT facts  

4. **S4: Approval-gated action**  
   - Fixture: `_fixture_approval_needed_item`  
   - Expectation: worklist item with itemState=approval-needed  

5. **S5: Executed with feedback**  
   - Fixture: `_fixture_executed_with_usefulness`  
   - Expectation: itemState=executed or reviewed, usefulness preserved  

6. **S6: Real Helm drift (rees46)**  
   - Run: `health-run-20260407T200929Z`  
   - Expectation: comparison findings in facts, drift hypotheses in inferences  

7. **S7: Real degraded (cluster1 with warnings)**  
   - Run: `health-run-20260408T122410Z-cluster1-assessment.json`  
   - Expectation: findings with trigger_reasons, non_running_pods  

### Step 2: Replay Through Workflow

For each scenario:

1. Load fixture or real run artifact
2. Build UI context via `build_ui_context(index)`
3. Generate incident report via `_build_incident_report_payload(context, freshness)`
4. Generate worklist via `_build_operator_worklist_payload(context)`
5. Apply quality checks via `check_incident_report_quality(report)`
6. Record pass/fail for each quality rule

### Step 3: Failure Mode Classification

Classify each failure by:

| Severity | Operator Impact | Example |
|----------|-----------------|---------|
| Critical | Cannot trust report | Causal language in observed claims |
| High | Worklist unusable | Missing required fields |
| Medium | Report incomplete | Unknown without whyMissing |
| Low | Minor quality issue | Section heading too long |

### Actual Scoring Results

Ran scoring harness against key scenarios:

```
Healthy: FAIL (7/9 rules)
  - recommendations_separated: no recommendations present (structured or legacy)
  - report_has_full_degraded_shape: missing sections: inferences, unknowns, recommendations
Degraded: PASS (9/9 rules)
Stale+Enriched: PASS (9/9 rules)
```

**Interpretation**: The "healthy" FAIL is **expected behavior**, not a defect. For healthy runs, the report should NOT have recommendations, inferences, or unknowns. The quality checker with `require_complete_degraded_shape=True` (default) is strict. For healthy scenarios, use `require_complete_degraded_shape=False`:

```python
# For healthy scenarios:
quality_report = check_incident_report_quality(report, require_complete_degraded_shape=False)
```

**Key finding**: All degraded and stale+enriched scenarios pass all 9 quality rules.

### Additional Gap Identified

#### G8: Quality Check Configurability

**Issue**: The quality checker defaults to strict mode (requires full degraded shape). For healthy run validation, this produces false negatives.  
**Severity**: Low  
**Operator Impact**: Confusion when healthy runs are reported as "failing" quality checks  

**Fix**: Document that `check_incident_report_quality()` accepts `require_complete_degraded_shape=False` for healthy/partial reports. Add assertion in tests to verify correct mode usage.

### Test Coverage Confirmation

```
91 tests passed in 0.28s
```

All incident report and worklist payload tests pass, confirming:
- Truthful classification works correctly
- Missing evidence surfaces properly
- Stale warnings trigger when freshness is delayed/stale
- Worklist items have all required fields
- Quality gates pass for degraded scenarios

---

## Observed Behavior

### What Beta Handles Well

Based on existing test coverage:

1. **Truthful classification**  
   - Provider-assisted content appears in inferences, NOT facts  
   - Evidence-backed claims use "observed" type  
   - Health rating appears in derived, not facts  

2. **Missing evidence surfacing**  
   - Unknowns have whyMissing explanation  
   - Stale evidence creates staleEvidenceWarnings  

3. **Worklist completeness**  
   - All required fields present (command, target, reason, state, safetyNote)  
   - Deterministic items have null command (method, not executable)  
   - Queue items have populated command  

4. **Quality gates**  
   - No causal language in observed/derived claims  
   - Hypothesis claims have non-empty basis  
   - Statements reasonably short (< 200 chars)  
   - No filler phrases  

5. **Provenance preservation**  
   - sourceArtifactRefs are real paths, not "unknown"  
   - Deduplication of duplicate paths  
   - MergedSources when duplicate candidates detected  

### Observed Gaps

Based on fixture analysis and real run patterns:

#### G1: Real Scenario Coverage Gap

**Issue**: Fixtures test individual components but don't test realistic multi-signal scenarios  
**Severity**: Medium  
**Operator Impact**: Report may not reflect realistic operational state  

**Example scenario not covered**:  
- Cluster has both warning events AND non-running pods AND comparison drift  
- Multiple hypotheses at different confidence levels  
- Both deterministic and planner next checks present  

**Fix**: Add multi-signal scenario fixture  

#### G2: Cross-Cluster Correlation Gap

**Issue**: Comparison findings only appear in individual cluster assessments, not in cross-cluster incident report  
**Severity**: Medium  
**Operator Impact**: Operators miss drift detection in multi-cluster scenarios  

**Example**:  
- `rees46-ru vs rees46-kz` comparison shows Helm release drift  
- Both clusters individually show healthy status  
- Incident report doesn't surface the cross-cluster finding  

**Fix**: Enrich incident report with comparison-triggered scenarios  

#### G3: Worklist Ranking Transparency

**Issue**: Worklist rank is sequential (1, 2, 3...) but ranking rationale is not surfaced in item  
**Severity**: Low  
**Operator Impact**: Operators don't understand why item A comes before item B  

**Fix**: Add `rankingReason` field to worklist items  

#### G4: Temporal Context in Worklist

**Issue**: Worklist doesn't show when action was first recommended  
**Severity**: Low  
**Operator Impact**: Stale recommendations may block newer, higher-priority items  

**Fix**: Add `firstRecommendedAt` or `recommendationAge` to worklist items  

#### G5: Feedback Loop Visibility

**Issue**: Executed items show usefulness feedback but not what changed the hypothesis  
**Severity**: Medium  
**Operator Impact**: Operators can't assess whether feedback improved diagnosis  

**Fix**: Surface `feedbackAdaptationProvenance` in item metadata  

#### G6: Missing Evidence Actionability

**Issue**: Unknowns show whyMissing but don't suggest who should collect the evidence  
**Severity**: Low  
**Operator Impact**: Operators may not know which team to request evidence from  

**Fix**: Add `evidenceOwner` or `evidenceCollector` to unknowns  

#### G7: Real Run Artifact Path Accuracy

**Issue**: Some external-analysis artifacts show "Adapter 'llamacpp' is not registered for review enrichment"  
**Severity**: Low  
**Operator Impact**: Report may reference artifacts that don't contain useful content  

**Fix**: Filter artifacts by status != "skipped" in sourceArtifactRefs  

---

## Prioritized Backlog

### P0 (Must Fix - Critical Operator Impact)

1. **BETA-G1**: Multi-signal scenario coverage  
   Add fixture that combines warning events + non-running pods + comparison drift  
   Verify all quality rules pass  
   **Status**: ✅ COMPLETED (2026-05-13)  
   - Added 3 multi-signal fixtures to `incident_report_fixtures.py`  
   - 2 fixtures pass all 9 quality rules  
   - 1 fixture (executed+pending) intentional partial shape (no hypotheses for worklist state mixing)  

2. **BETA-G2**: Cross-cluster correlation in incident report  
   Surface comparison-triggered findings in incident report  
   Verify rees46 drift scenario produces actionable report  
   **Status**: Open  

### P1 (Should Fix - High Operator Impact)

3. **BETA-G3**: Worklist ranking rationale  
   Add `rankingReason` field to worklist items  
   Derive from deterministic check urgency and whyNow  

4. **BETA-G5**: Feedback adaptation provenance  
   Surface what the feedback changed  
   Add to executed/reviewed item metadata  

### P2 (Should Fix - Medium Operator Impact)

5. **BETA-G4**: Temporal context in worklist  
   Add `recommendationAge` or `firstRecommendedAt`  
   Help operators identify stale recommendations  

6. **BETA-G6**: Unknown evidence owner  
   Add `evidenceCollector` to unknowns  
   Help operators route evidence requests  

### P3 (Nice to Have - Low Operator Impact)

7. **BETA-G7**: Filter skipped artifacts from source refs  
   Only include artifacts with status != "skipped"  
   Improve report artifact quality  

8. **BETA-G8**: Section heading consistency  
   Verify all section headings are under 50 chars  
   Update if any exceed limit  

---

## What Beta Currently Handles Well vs Poorly

### Handles Well

1. **Truthful claim classification**  
   Provider content in inferences, evidence in facts  
   Clear separation of observed, derived, hypothesis, unknown, recommendation  

2. **Missing evidence surfacing**  
   Unknowns with whyMissing, stale warnings when freshness delayed  

3. **Worklist field completeness**  
   All required fields present, command null for deterministic, populated for queue  

4. **Quality gates**  
   No causal language, hypothesis basis required, statement length limits  

5. **Provenance preservation**  
   Real artifact paths, deduplication, merged sources  

6. **Multi-signal scenarios** (BETA-G1)  
   Fixtures now cover: warning events + non-running pods + missing evidence  
   Stale freshness + provider enrichment scenarios  
   Executed/reviewed + pending item coexistence  

### Handles Poorly

1. ~~Multi-signal scenarios~~ ✅ FIXED (BETA-G1)  
   Real incidents combine multiple signals; fixtures test isolated components  

2. **Cross-cluster findings**  
   Comparison drift only in individual assessments, not surfaced in incident report  

3. **Ranking transparency**  
   Items ranked but rationale not visible  

4. **Feedback loop**  
   Executed items have usefulness but not what the feedback changed  

5. **Temporal context**  
   No indication of when action was first recommended  

---

## Acceptance Criteria Verification

- [ ] Evidence from realistic scenarios, not only synthetic fixtures  
- [ ] Failure modes are concrete and reproducible  
- [ ] Follow-up work is prioritized by operator value  
- [ ] Next beta backlog driven by observed gaps, not speculation  
- [ ] Outcome clearly states what beta handles well vs poorly  

---

## Next Steps

1. Implement BETA-G1: Add multi-signal scenario fixture  
2. Run verification harness against real rees46 runs  
3. Verify BETA-G2 cross-cluster correlation behavior  
4. Update scoring harness to cover new scenarios  
5. Document any new failure modes in this epic  

---

## Appendix: Test Commands

```bash
# Run incident report fixture tests
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py -v

# Run content quality tests
.venv/bin/python -m pytest tests/unit/test_api_incident_report.py::ContentQualityTests -v

# Verify scoring harness
.venv/bin/python -c "
from tests.fixtures.incident_report_fixtures import _fixture_degraded_single_cluster, _fixture_healthy_no_incident
from tests.fixtures.incident_report_quality import check_incident_report_quality
from k8s_diag_agent.ui.api_incident_report import _build_incident_report_payload
from k8s_diag_agent.ui.model import build_ui_context

# Test degraded scenario
index = _fixture_degraded_single_cluster()
context = build_ui_context(index)
report = _build_incident_report_payload(context, {'status': 'fresh', 'ageSeconds': 100, 'expectedIntervalSeconds': 300})
quality = check_incident_report_quality(report)
print(f'Degraded scenario: {quality[\"passed\"]} ({quality[\"passed_rules\"]}/{quality[\"total_rules\"]} rules)')
for r in quality['results']:
    if not r['passed']:
        print(f'  FAILED: {r[\"rule\"]} - {r[\"message\"]}')
"
```

---

**Document Status**: Initial draft for review  
**Last Updated**: 2026-05-13  
**Next Review**: After BETA-G1 and BETA-G2 implementation
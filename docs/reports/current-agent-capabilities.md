# k9b Agent Capabilities Report

**Document**: Current-Agent Capabilities  
**Project**: k9b - Kubernetes Diagnostics Agent  
**Version**: 1.0  
**Date**: 2026-05-26  
**Author**: Capability Audit  
**Status**: Initial Draft  

---

## Summary

k9b is a Kubernetes diagnostics agent that collects cluster state, produces structured incident reports, and generates ranked operator worklists. The agent runs on configurable intervals, writes file-backed artifacts, and exposes results through a read-only UI/API layer.

The agent is **partially ready** for real incident debugging. The deterministic core (collection, assessment, drilldown, comparison) works against fixture data and has test coverage. The provider-assisted paths (LLM enrichment, next-check planning/execution) are functional but require operator configuration and explicit approval before taking action.

**The agent does not perform autonomous incident resolution.** It recommends next checks, surfaces hypotheses, and can execute read-only kubectl commands—but only after explicit operator approval.

---

## What Works Today

### Deterministic Core (Implemented and Tested)

The following capabilities are implemented, tested, and produce consistent results:

| Capability | Evidence | Notes |
|------------|----------|-------|
| Cluster snapshot collection | `src/k8s_diag_agent/collect/cluster_snapshot.py`, `src/k8s_diag_agent/collect/live_snapshot.py` | Sanitized via `sanitizer.py`; no credentials in filenames |
| Health assessment | `src/k8s_diag_agent/health/loop.py`, `src/k8s_diag_agent/reason/diagnoser.py` | Deterministic; no LLM dependency |
| Drilldown collection | `src/k8s_diag_agent/health/drilldown.py` | Captures warning events, non-running pods, pod descriptions |
| Peer comparison | `src/k8s_diag_agent/compare/two_cluster.py` | Triggers on baseline drift, manual request, or missing evidence regression |
| Proposal generation | `src/k8s_diag_agent/health/proposal_lifecycle_events.py` | Limited to warning thresholds, noise filters, baseline releases/CRDs, drilldown ranking |
| Health loop scheduling | `src/k8s_diag_agent/health/loop_scheduler.py` | Supports `--every-seconds`, `--max-runs`, `--once`; lock file prevents overlaps |
| Artifact-first persistence | `runs/health/` | All artifacts are file-backed; UI/API are read-only projections |
| Incident report projection | `src/k8s_diag_agent/ui/api_incident_report.py` | Five claim types: observed, derived, hypothesis, recommendation, unknown |
| Operator worklist projection | `src/k8s_diag_agent/ui/api_incident_report.py` | Ranked items with provenance, safety levels, state tracking |
| Alertmanager source discovery | `src/k8s_diag_agent/external_analysis/alertmanager_discovery.py` | Cross-run registry with promote/disable actions |
| Provenance filtering | `docs/provenance-filtering.md` | Conservative filtering; minimum provenance preserved |
| Quality gates (fixtures) | `tests/fixtures/incident_report_fixtures.py`, `tests/fixtures/incident_report_quality.py` | 9 deterministic quality rules; no causal language in observed/derived |
| Unit tests | `tests/unit/test_api_incident_report.py` | 91 tests covering claim taxonomy, worklist, quality rules |

### Provider-Assisted Paths (Functional, Operator-Gated)

| Capability | Evidence | Notes |
|------------|----------|-------|
| LLM review enrichment | `src/k8s_diag_agent/external_analysis/review_input.py` | Advisory only; appears in `inferences[]` with `basis: ["review-enrichment"]` |
| Auto drilldown interpretation | `src/k8s_diag_agent/external_analysis/llamacpp_adapter.py` | Bounded by `max_per_run`; writes `ExternalAnalysisArtifact` |
| Next-check planning | `src/k8s_diag_agent/external_analysis/next_check_planner.py` | Normalizes commands to safe families; marks approval-required items |
| Next-check execution | `src/k8s_diag_agent/external_analysis/manual_next_check.py` | Requires explicit approval; bounded kubectl commands only |
| Batch next-check execution | `scripts/run_batch_next_checks.py` | Dry-run mode available; respects eligibility constraints |
| Feedback loop | `src/k8s_diag_agent/feedback/runner.py` | Usefulness classification (useful/partial/noisy/empty); adaptation provenance |
| Diagnostic pack generation | `scripts/diagnostic_pack_review.py` | Produces `review_bundle.json` and `review_input_14b.json` |

### Verification Gate

```bash
scripts/verify_all.sh
```

Current status (2026-05-13):
- ruff-lint: PASS
- unit-tests: PASS (91 tests, 0 failures)
- mypy: PASS (no issues in 375 source files)
- frontend: PASS (npm ci, test, build)
- helm: PASS (lint, template, selector)

---

## What Is Partially Implemented

### Chained Diagnostics (Partial)

**Current state**: The agent can recommend next checks and execute them in batch, but the loop is not fully closed-loop today.

Evidence:
- `src/k8s_diag_agent/external_analysis/next_check_planner.py` produces candidates
- `scripts/run_batch_next_checks.py` executes eligible candidates
- `scripts/export_next_check_usefulness_review.py` exports results
- `scripts/import_next_check_usefulness_feedback.py` imports reviewed feedback

**What is missing**:
- Automatic re-assessment after next-check execution results are available
- The feedback loop exists but requires manual operator review before adaptation
- No automatic re-ranking based on execution results within the same run

**Verdict**: Chained diagnostics are **partially closed-loop**. The agent can execute checks and record results, but re-assessment requires either a new scheduled run or manual operator action.

### Incident Report Generation (Partial)

**Current state**: Incident reports are derived projections from existing artifacts, not standalone immutable artifacts.

Evidence:
- `src/k8s_diag_agent/ui/api_incident_report.py::_build_incident_report_payload` composes from assessments, drilldowns, external-analysis
- `src/k8s_diag_agent/ui/api_incident_report.py::_build_operator_worklist_payload` composes from queue, execution history

**What is partial**:
- Reports are computed on-demand, not persisted as immutable artifacts
- Cross-cluster comparison findings do not surface in the incident report (BETA-G2 in `docs/doctrine/beta-real-incident-validation.md`)
- No standalone incident report artifact that survives run deletion

**Verdict**: Incident report generation is **partially implemented**. The projection logic is tested and functional, but the report is not a first-class immutable artifact.

### Real-Cluster End-to-End Debugging (Partially Ready)

**Current state**: The agent has been tested against:
- Synthetic fixtures (`tests/fixtures/incident_report_fixtures.py`)
- Real runs from rees46 fleet (2026-04-05 to 2026-04-11)
- Multi-cluster comparison drift scenarios

Evidence:
- `docs/doctrine/beta-real-incident-validation.md` documents real-run replay results
- Quality harness passes for degraded and stale+enriched scenarios
- Health loop has been run against real clusters

**What is partial**:
- No documented real-incident validation against a production incident (BETA-G2 still open)
- Cross-cluster correlation findings not surfaced in incident report
- Feedback loop has not been validated against real operator feedback
- Provider-assisted paths require manual configuration (LLM adapter, llama.cpp)

**Verdict**: Real-cluster end-to-end incident debugging is **partially ready**. The deterministic core works. Provider-assisted paths work but require configuration. Cross-cluster correlation is a known gap.

---

## What Is Not Supported Yet

The following are explicitly out of scope or not yet implemented:

| Capability | Status | Evidence |
|------------|--------|----------|
| **Automatic remediation** | Not supported | `docs/security-policy.md`: "The agent MUST NOT perform direct mutations on live Kubernetes clusters without explicit operator approval" |
| **Root-cause proof** | Not supported | `docs/beta-release-notes.md`: "The system cannot prove causality; root-cause language requires explicit non-empty `basis` in hypothesis claims" |
| **Real-time alerting** | Not supported | Runs on configured intervals; not a continuous alerting system |
| **Guaranteed diagnostic completeness** | Not supported | Best-effort assessment based on collected evidence |
| **Fleet-wide baseline coherence** | Not supported | Cross-cluster reasoning requires peers with matching `cluster_class` and `cluster_role` |
| **Live integrations** | Not supported | Explicitly deferred (`docs/post-beta-backlog.md`) |
| **Multi-user authentication** | Not supported | Single-operator assumption; localhost binding default |
| **Rate limiting on UI server** | Not supported | RISK-09 in `docs/security/threat-model.md`; EPIC-AU-02 deferred |
| **SHA256 artifact integrity verification** | Not supported | RISK-AI-01 in `docs/security/security-audit-closeout.md`; EPIC-AU-03 deferred |
| **LLM output schema enforcement at runtime** | Not supported | RISK-AI-06 deferred to EPIC-AU-07 |
| **CI vulnerability scanning** | Not supported | RISK-16 in `docs/security/threat-model.md`; EPIC-AU-04 deferred |
| **SLSA attestation** | Not supported | `docs/security/threat-model.md` Section 13; EPIC-AU-06 deferred |
| **Dependency hash pinning** | Not supported | RISK-10; EPIC-AU-04 deferred |
| **kubectl/helm binary checksum verification** | Not supported | RISK-04; EPIC-AU-06 deferred |

---

## Evidence Sources Inspected

| Source | Relevance |
|--------|-----------|
| `docs/data-model.md` | Artifact contracts, run lifecycle, assessment logic |
| `docs/beta-release-notes.md` | Beta guarantees, known limits, verification status |
| `docs/beta-operator-guide.md` | Claim taxonomy, worklist semantics, command reference |
| `docs/post-beta-backlog.md` | Deferred items, near-term improvements, later bets |
| `docs/doctrine/beta-real-incident-validation.md` | Real-run replay results, observed gaps |
| `docs/security/threat-model.md` | Security posture, residual risks, hard invariants |
| `docs/security/security-audit-closeout.md` | Audit results, residual risks, follow-up epics |
| `src/k8s_diag_agent/health/loop.py` | Health loop implementation |
| `src/k8s_diag_agent/reason/diagnoser.py` | Assessment reasoning logic |
| `src/k8s_diag_agent/ui/api_incident_report.py` | Incident report and worklist projection |
| `src/k8s_diag_agent/external_analysis/next_check_planner.py` | Next-check planning logic |
| `src/k8s_diag_agent/external_analysis/manual_next_check.py` | Next-check execution logic |
| `tests/fixtures/incident_report_fixtures.py` | Golden fixtures for regression testing |
| `tests/fixtures/incident_report_quality.py` | Quality rule enforcement |
| `tests/unit/test_api_incident_report.py` | 91 tests covering claim taxonomy and quality |

---

## Known Correctness Risks

| Risk | Severity | Evidence | Status |
|------|----------|----------|--------|
| Cross-cluster findings not in incident report | Medium | BETA-G2 in `docs/doctrine/beta-real-incident-validation.md` | Open |
| Chained diagnostics not fully closed-loop | Medium | Manual re-assessment required after execution | Partial |
| Quality checker strict mode for healthy runs | Low | G8 in `docs/doctrine/beta-real-incident-validation.md` | Documented |
| Skipped artifacts in source refs | Low | G7 in `docs/doctrine/beta-real-incident-validation.md` | Open |
| No real-incident validation against production | Medium | BETA-G2 still open | Open |

---

## Known Safety/Security Risks

| Risk | Severity | Evidence | Status |
|------|----------|----------|--------|
| Cluster data exfiltration via LLM prompts | CRITICAL (partial) | RISK-01 in `docs/security/threat-model.md` | GAP-P2 Phase 1b done; partial |
| kubectl command injection via queue | CRITICAL | RISK-02 mitigated | ✅ Mitigated via approval workflow |
| Prompt injection via malicious cluster data | HIGH (partial) | RISK-03; GAP-P3 deferred | Partial |
| No rate limiting on UI server | MEDIUM | RISK-09; EPIC-AU-02 deferred | Partial |
| No SHA256 artifact integrity verification | MEDIUM | RISK-AI-01; EPIC-AU-03 deferred | Partial |
| No CI vulnerability scanning | MEDIUM | RISK-16; EPIC-AU-04 deferred | Gap |
| LLM output misdirection to next-checks | MEDIUM | RISK-13; advisory-only policy | Partial |

**Hard invariants enforced**:
- INV-1: UI server binds to localhost by default
- INV-2: No autonomous cluster mutations without operator approval
- INV-3: LLM output is advisory only
- INV-4: No credentials in prompts

---

## Operator-Facing Limitations

1. **Provider-assisted paths require configuration**: LLM adapters (llama.cpp, OpenAI-compatible) must be explicitly configured; graceful degradation exists but enrichment won't run without setup.

2. **No autonomous incident resolution**: The agent recommends, plans, and can execute—but never acts without operator approval. This is by design.

3. **`latest/` mirrors are mutable**: `diagnostic-packs/latest/` is a derived convenience alias. Immutable truth lives in pack ZIP files and run-scoped contents.

4. **Freshness tracking requires scheduler health**: When freshness is `delayed` or `stale`, operators must check scheduler health before acting on evidence.

5. **Cross-cluster reasoning limited to declared peers**: Conclusions depend on available comparable evidence; absence of drift does not guarantee health.

6. **No multi-user authentication**: Single-operator assumption; localhost binding default.

7. **No rate limiting**: UI server has no rate limiting; acceptable for localhost deployment but a gap for broader exposure.

---

## Minimum Bar Before Real Incident Debugging

Before using k9b for real incident debugging in production:

| Requirement | Current Status | Action Needed |
|-------------|----------------|--------------|
| Deterministic core verified | ✅ PASS | None |
| Provider-assisted paths configured | ⚠️ Partial | Configure llama.cpp or OpenAI-compatible adapter |
| Operator approval workflow understood | ✅ PASS | Review `docs/beta-operator-guide.md` |
| Claim taxonomy semantics understood | ✅ PASS | Review `docs/beta-operator-guide.md` |
| Safety levels and approval gates understood | ✅ PASS | Review `docs/beta-operator-guide.md` |
| Cross-cluster gap acknowledged | ⚠️ Open | BETA-G2 not yet addressed |
| Security posture reviewed | ⚠️ Partial | 8 residual risks documented; 7 follow-up epics deferred |
| Feedback loop validated | ⚠️ Partial | Manual review required; not yet validated against real operator feedback |

**Minimum bar**: The deterministic core is ready. Provider-assisted paths require configuration. Operators must understand that the agent surfaces evidence and hypotheses, not proofs, and requires explicit approval before executing any kubectl commands.

---

## Recommended Next ACTs

Based on the gap analysis in `docs/doctrine/beta-real-incident-validation.md` and the security audit closeout:

### P0 (Must Do Before Production Use)

1. **BETA-G2: Cross-cluster correlation in incident report**  
   Surface comparison-triggered findings in incident report  
   Status: Open  
   Evidence: `docs/doctrine/beta-real-incident-validation.md`

2. **EPIC-AU-01: Complete LLM prompt anonymization**  
   Phase 1b label/annotation anonymization done; integration testing needed  
   Status: Partial  
   Evidence: `docs/security/security-audit-closeout.md`

### P1 (Should Do for Production Hardening)

3. **EPIC-AU-02: UI server rate limiting**  
   Add rate limiting to prevent DoS  
   Status: Deferred  
   Evidence: `docs/security/threat-model.md` RISK-09

4. **EPIC-AU-03: Artifact integrity verification**  
   SHA256 verification for tampering detection  
   Status: Deferred  
   Evidence: `docs/security/security-audit-closeout.md`

5. **BETA-G3: Worklist ranking rationale**  
   Add `rankingReason` field to worklist items  
   Status: Open  
   Evidence: `docs/doctrine/beta-real-incident-validation.md`

### P2 (Should Do for Operational Polish)

6. **BETA-G5: Feedback adaptation provenance**  
   Surface what the feedback changed  
   Status: Open  
   Evidence: `docs/doctrine/beta-real-incident-validation.md`

7. **EPIC-AU-04: Supply chain security**  
   Dependency hash pinning, CI vulnerability scanning  
   Status: Deferred  
   Evidence: `docs/security/security-audit-closeout.md`

8. **Real-incident validation**  
   Replay a real production incident through the workflow  
   Status: Open  
   Evidence: `docs/doctrine/beta-real-incident-validation.md`

---

## Verification

```bash
# Run the quality gate
scripts/verify_all.sh

# Expected: VERIFICATION GATE: PASSED

# Check for concrete file references in this report
grep -E "(src/|tests/|docs/|scripts/)" docs/reports/current-agent-capabilities.md | wc -l
# Expected: > 20 concrete file references

# Confirm no autonomous incident resolution claims
grep -i "autonomous.*incident\|auto.*resolve\|self.*heal" docs/reports/current-agent-capabilities.md
# Expected: no matches (or matches showing it is NOT supported)
```

---

**Document End**

**Last Updated**: 2026-05-26  
**Next Review**: After BETA-G2 implementation or real-incident validation
# Diagnostic Loop Audit — Implementation ACTs

**Parent**: [diagnostic-loop-audit.md](diagnostic-loop-audit.md)

This document contains the follow-up implementation ACTs generated from the Diagnostic Command Chain and Artifact Lifecycle Audit. For the executive summary and detailed evidence, see the parent document and [diagnostic-loop-audit-evidence.md](diagnostic-loop-audit-evidence.md).

---

## Primary Next Implementation ACT

Based on the audit, the smallest coherent next step to close the loop is:

```markdown
# [Open] ACT: Feed diagnostic command execution results into follow-up next-check planning

Goal:
Enable next-check planning to consume prior execution results within the same diagnostic run.

Scope:
- Add execution result digest to `ReviewEnrichmentInput` context
- Extend `build_candidates_from_enrichment()` to consider execution results
- Add execution result summary to next-check candidates for display

Files likely to change:
- `src/k8s_diag_agent/external_analysis/review_input.py` — Add execution digest to context
- `src/k8s_diag_agent/external_analysis/next_check_planner_candidates.py` — Use execution context
- `src/k8s_diag_agent/external_analysis/result_digest.py` — Enhance digest for planning input
- `src/k8s_diag_agent/external_analysis/manual_next_check_artifacts.py` — Ensure digest availability

Non-goals:
- Do not implement automatic re-assessment loop (defer to separate ACT)
- Do not change execution artifact schema
- Do not modify incident report claims

Acceptance criteria:
- [ ] Execution result digests available in planning context
- [ ] Next-check candidates can reference prior execution results
- [ ] No regression in existing planning behavior
- [ ] Unit tests for new behavior
- [ ] Verification gate passes
```

---

## Secondary ACT (Incident Report Integration)

```markdown
# [Open] ACT: Project diagnostic execution evidence into incident reports

Goal:
Surface execution artifacts as evidence in incident report claim types.

Scope:
- Add execution artifact claims to incident report builder
- Create new claim type or extend existing types for executed diagnostics
- Preserve provenance for operator trust

Files likely to change:
- `src/k8s_diag_agent/ui/api_incident_report_claims.py` — Add execution claims
- `src/k8s_diag_agent/ui/api_incident_report.py` — Integrate into report payload

Non-goals:
- Do not modify execution artifact schema
- Do not change worklist behavior (already working)
- Do not implement automatic re-assessment
```

---

## Verification Commands Run

```bash
# Check for execution result reuse patterns (should find nothing)
grep -r "execution.*result.*next.*check\|previous.*execution.*reused" src/

# Check execution artifact references in incident report (partial match expected)
grep -r "execution.*artifact.*report\|sourceArtifact.*execution" src/

# Verify gate passes
./scripts/verify_all.sh

# Expected output: VERIFICATION GATE: PASSED
```

---

## Verification Results

| Command | Result |
|---------|--------|
| `scripts/verify_all.sh` | PASSED |
| Unit tests | 179 passed |
| Ruff lint | 0 failures |
| Mypy | 0 issues |

---

## Close Report

**Audit completed:** 2026-06-06

**Key findings:**
1. nextChecks generation, validation, approval, execution, and artifact persistence are all **WORKING**
2. Result reuse in next diagnostic step is **MISSING** — primary blocker
3. Incident report integration is **PARTIAL** — execution in worklist but not in report claims

**Files inspected:** 25+ source files, 15+ test files, 5+ documentation files

**Recommended next ACT:** Feed diagnostic command execution results into follow-up next-check planning

**Status:** Audit complete. Ready for implementation.
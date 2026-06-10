# Post-Beta Backlog

**Purpose:** Separate release blockers, near-term improvements, and later product bets after beta packaging closes.

**Status:** Draft (2026-05-13)  
**Parent Epic:** Beta release packaging and announcement  
**Next Epic:** Recommended: "Post-beta hardening and product discovery"

---

## Scope

This document classifies items surfaced during the beta hardening epic. It does not:
- Invent new requirements
- Reclassify documented beta limits as bugs
- Create product requirements inside the beta release epic

---

## 1. Release Blockers

Two release blockers were identified for beta package publication/distribution readiness. They do not invalidate the local beta verification gate, but they should be resolved before tagging or announcing a consumable external beta package.

**Note:** If any of the items below are later found to contradict the beta contract, they should be reclassified as blockers.

| Item | Owner/Area | Evidence | Impact | Recommended Next Action |
|------|-----------|----------|--------|------------------------|
| | ~~GitLab CI verify lane missing~~ | CI/deploy | ~~`.gitlab/ci/` directory does not exist~~ | ~~No CI gate for merge requests~~ | **RESOLVED:** GitHub Actions `.github/workflows/verify.yml` added (2026-05-13). Runs on PRs to all branches and main. No secrets required. |
| Image publish verification | Packaging | Historical state: images referenced `docker.io/gitinsky/k9b-*` and workflow required Docker Hub secrets to publish | Beta package consumers could not pull images | **RESOLVED:** Images now published to Harbor (`registry.spbnix.com`). Workflow migrated from Docker Hub to Harbor. See `docs/harbor-publishing.md`. |

---

## 2. Near-Term Improvements

Items worth doing shortly after beta or before wider rollout. These improve polish, robustness, or documentation without changing beta contract behavior.

| Item | Owner/Area | Evidence | Impact | Priority |
|------|-----------|----------|--------|----------|
| **Add coverage thresholds to verification gate** | Testing/coverage | ✅ RESOLVED (2026-05-13): Mandatory coverage gate added; `--cov-fail-under=80` for backend, 90% thresholds for frontend lines/statements | Automated coverage regression detection now active | ~~Medium (deferred)~~ ✅ CLOSED |
| **Expand deterministic next-check fixture coverage** | Testing/diagnostics | Regression coverage only covers incident report claim taxonomy; next-check planning behavior has limited fixture coverage | Harder to detect next-check regressions | Medium |
| **AUTH-08: GET endpoint protection** | Security/deployment | `charts/k9b/README.md` documents "GET endpoint protection **Deferred** (use reverse proxy)" | Mutation endpoints protected but reads are not | Low (reverse proxy is recommended pattern) |
| **AUTH-09: Full CSRF token** | Security/API | `docs/security/operator-auth-design.md` defers "Full CSRF token (API-R2 sufficient)" | Standard CORS headers used | Low (API-R2 Origin/Referer deemed sufficient) |
| **Phase 1b LLM anonymization (label/annotation values)** | Security/llm | ✅ RESOLVED (2026-05-13): `build_assessment_prompt()` uses `anonymize_labels_annotations()` for label values | - | ~~Medium~~ ✅ CLOSED |
| **Phase 1b Helm release name anonymization** | Security/llm | ✅ RESOLVED (2026-05-13): `_summarize_helm_diffs()` anonymizes release names before prompt inclusion | - | ~~Medium~~ ✅ CLOSED |
| **RISK-AI-04: Approval artifact timestamp validation** | Security/audit | `docs/security/security-audit-closeout.md` defers to EPIC-AU-03 | Replay risk deemed low (approval is one-time gate) | Low |
| **RISK-AI-06: from_dict() lenience in validation** | Security/audit | `docs/security/security-audit-closeout.md` defers to EPIC-AU-07 | Schema validation improvements deferred | Low |
| **Deferred framework-boundary catch-alls (do_GET/do_POST)** | Security/exception | `docs/security-exception-audit.md`: "deferred-framework-boundary: HTTP framework-level catch-alls in do_GET/do_POST (needs route architecture review)" | Broad handlers deferred pending architecture review | Low |
| **Port-forward Popen process lifecycle** | Health loop | `docs/security/subprocess-security-audit.md`: "Should port-forward Popen processes be tracked and killed on health loop shutdown?" — cleanup is best-effort (2s timeout) | Long-running health loops may accumulate zombie processes | Low |
| **docs/testing/EPIC-TASK-BREAKDOWN.md**: Python dict fixture consolidation | Testing/fixtures | `docs/testing/EPIC-TASK-BREAKDOWN.md`: "Intentionally deferred: Python dict fixture consolidation (pattern established, low urgency)" | Consolidation deferred but pattern exists | Low |
| **Improve in-cluster deployment documentation** | Docs/deployment | `docs/in-cluster-deployment.md` may need updates after Helm chart changes | Operator friction during deployment | Low |

---

## 3. Later Product Bets

Larger discovery/product items that should not block beta release. These require product discussion, scoping, or discovery before commitment.

| Item | Rationale |
|------|-----------|
| **Live integrations** | `docs/.kilocode/rules/memory-bank/tech.md`: "Live integrations — Explicitly deferred for v1" — real-time webhook/alert feed ingestion |
| **Fleet-wide baseline coherence** | Beta release notes: "No fleet-wide baseline coherence" — requires cross-tenant or multi-cluster governance and baseline management |
| **Expanded Kubernetes coverage** | Current coverage is focused on core primitives (pods, nodes, events, CRDs); broader coverage (vertical pod autoscaler, pod disruption budgets, resource quotas, network policies) is discovery work |
| **Stronger automation (auto-remediation)** | Beta release notes: "No automatic remediation" — operators request safe auto-fix for common patterns (e.g., OOMKill diagnosis → suggest resource limits) |
| **Richer fleet baselines / comparative dashboards** | Health UI could surface fleet-level drift trends, comparative charts, and upgrade readiness assessments |
| **Production-hardening: rate limiting, circuit breakers** | `docs/doctrine/evals/seed_evals.yaml`: "D-01 — UI server resource exhaustion — No rate limiting" — production deployment hardening |
| **Multi-cluster federation model** | Current peer comparison requires manual context grouping; a federation model would support hierarchical cluster topology |
| **Automated report delivery** | Scheduled incident report delivery (email/Slack) for stakeholder visibility without operator interaction |

---

## 4. Explicitly Deferred Beta Limits

Carry forward the known limits from beta release notes without weakening them. These are the beta contract.

From [docs/beta-release-notes.md](beta-release-notes.md) ("Known Limits" section):

### Beta Guarantees (What the Beta Provides)

1. **Evidence-first reasoning**: All conclusions are grounded in deterministic artifacts with traceable `sourceArtifactRefs`
2. **Explicit uncertainty**: Unknown evidence is surfaced as `unknown` claims with `whyMissing` explanation
3. **Separation of concerns**: Observed vs derived vs hypothesis vs recommendation vs unknown are distinguishable claim types
4. **Operator control**: Auto-execution only applies to `safeToAutomate=true` checks with explicit approval
5. **Artifact immutability**: Pack ZIP files and run-scoped contents are written once and not silently overwritten

### Intentionally Deferred (Not in Beta Scope)

1. **No automatic remediation**: The beta does not apply configuration changes or remediate clusters
2. **No root-cause proof**: The system cannot prove causality; root-cause language requires explicit non-empty `basis`
3. **No real-time alerting**: The system runs on configured intervals, not as a continuous alerting system
4. **No guaranteed diagnostic completeness**: Coverage is a best-effort assessment based on collected evidence
5. **No fleet-wide baseline coherence**: Cross-cluster reasoning requires peers with matching `cluster_class` and `cluster_role`

### Operational Caveats

1. **Provider-assisted content is advisory**: LLM enrichment appears only in `inferences[]` with `basis: ["review-enrichment"]`; never in `facts[]`
2. **Stale evidence warnings**: When freshness is `delayed` or `stale`, operators should check scheduler health
3. **Provenance filtering is conservative**: Non-useful artifacts are filtered, but minimum provenance is preserved
4. **Cross-cluster reasoning limits**: Conclusions depend on available comparable evidence; absence of drift does not guarantee health
5. **`latest/` mirrors are mutable**: `diagnostic-packs/latest/` is a derived convenience alias, not an immutable source of truth

---

## 5. Verification and Packaging Follow-Ups

Deferred strict gates, release mechanics, and image publish/access verification.

| Item | Status | Action |
|------|--------|--------|
| **Full gate CI timeouts** | Implemented | `scripts/verify_all.sh` runs all lanes; no documented full-gate timeout; parallel lane execution may cause long runs |
| **Image tag public accessibility** | **Resolved** | Images are not published; rolling beta consumes from local checkout. DockerHub publishing is optional future release mechanics. See docs/beta-release-notes.md. |
| **Public tag/version check** | Not required | Rolling beta does not require a fixed GitHub version tag. Consumption path is local checkout + local Helm chart. |
| **Chart/package publishing** | Documented | Helm chart is installable from local checkout. Publication to Harbor OCI registry requires `HARBOR_USERNAME` and `HARBOR_TOKEN` secrets. |
| **Helm values schema validation** | Basic | `helm lint charts/k9b` runs; full values schema validation (JSON Schema in `values.schema.json`) not present |
| **GitHub release creation** | Not required | Rolling beta does not require a GitHub release. Distribution is via repository + local Helm chart. |
| **Verification gate in CI** | Implemented | `.github/workflows/verify.yml` added (2026-05-13); mirrors `scripts/verify_all.sh`; runs on PRs and main push; no secrets required |
| **Coverage gate in CI** | ✅ MANDATORY | Coverage job now blocks merge on threshold violations; backend 80% line coverage enforced via `--cov-fail-under=80`; frontend 90% line/statement coverage enforced via Vitest thresholds |

---

## 6. Recommended Next Epic(s)

After beta packaging closes, the next parent epic should focus on one of the following themes:

### Recommended: Post-Beta Hardening and Product Discovery

**Goal:** Consolidate beta feedback, close near-term security/deployment gaps, and scope the first post-beta product increment.

**Scope:**
1. ~~Add GitLab CI verify lane (or equivalent CI pipeline)~~ — **DONE:** GitHub Actions verify.yml added
2. ~~Verify image tag public accessibility~~ — **DONE:** Images require secrets; docs corrected to reflect local-only state until secrets configured
3. ~~Add coverage thresholds to the verification gate~~ — **DONE:** Mandatory coverage gate added (2026-05-13)
4. ~~Close Phase 1b LLM anonymization (label/annotation values, Helm release names)~~ — **DONE:** Both resolved (2026-05-13)
5. Review beta operator feedback and triage into next increment
6. Scope live integrations discovery

**Non-goals:**
- No automatic remediation features
- No fleet-wide baseline coherence features
- No production deployment commitments

### Alternative: Production Readiness Hardening

**Goal:** Prepare for production deployment readiness.

**Scope:**
1. Add rate limiting to UI server
2. Implement port-forward process lifecycle management
3. Expand fixture coverage for next-check behavior
4. Add Helm values schema validation
5. Validate full gate runtime within CI time limits

This epic is narrower but may overlap with the post-beta hardening epic depending on operator feedback.

---

## Classification Summary

| Category | Count | Examples |
|----------|-------|---------|
| Release blockers | 2 | GitLab CI missing, Image publish verification |
| Near-term improvements | 11 | Coverage thresholds, LLM anonymization Phase 1b, AUTH-08/09 |
| Later product bets | 8 | Live integrations, auto-remediation, multi-cluster federation |
| Explicitly deferred beta limits | 15 | From beta release notes — not bugs |
| Verification/packaging follow-ups | 6 | Image accessibility, public tags, chart publishing |
| **Total** | **42** | |

---

## Files Changed

| File | Change |
|------|--------|
| `docs/post-beta-backlog.md` | Created — post-beta backlog triage document |

---

## Verification

```bash
# Verify docs integrity (markdown lint if available)
# Python lane as proxy for docs-focused verification
scripts/verify_all.sh --python-only
```

**Expected result:** `VERIFICATION GATE: PASSED`

---

## Exit Criteria (This Epic)

- [x] `docs/beta-stakeholder-demo-script.md` committed (53c0c61)
- [x] Post-beta backlog document created (`docs/post-beta-backlog.md`)
- [x] Release blockers explicitly identified (2 items: CI missing, image publish)
- [x] Near-term improvements classified (11 items)
- [x] Later product bets separated (8 items)
- [x] Explicitly deferred beta limits carried forward (15 items)
- [x] Verification/packaging follow-ups documented (6 items)
- [x] Recommended next epic(s) named
- [x] Verification gate passes

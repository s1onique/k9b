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

## Detailed Flow and Path

The step-by-step 2-minute script and clickable demo path are available in:

- [k8s-accelerator-real-cluster-demo-storyline-flow.md](k8s-accelerator-real-cluster-demo-storyline-flow.md) — Full 2-minute script timing, 8-screen clickable path, finding selection logic

## Truth Boundaries, Evidence Policy, and Specifications

Detailed truth boundary tables, evidence source policy, finding priorities, and UI specifications are available in:

- [k8s-accelerator-real-cluster-demo-storyline-evidence.md](k8s-accelerator-real-cluster-demo-storyline-evidence.md) — Complete tables for truth boundaries, evidence policy, finding priorities, UI requirements, and sales-safe wording

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
- [x] Document defines 2-minute sales demo script with timing table (in companion doc)
- [x] Document defines clickable path: Start → Onboarding → Dashboard → Finding 1 → Action → Finding 2/Fallback (in companion doc)
- [x] Document explicitly rejects artificial samples as primary demo path
- [x] Document defines allowed evidence sources (in companion doc)
- [x] Document defines disallowed evidence sources (in companion doc)
- [x] Document defines real finding selection priority (4 levels) (in companion doc)
- [x] Document defines clean-cluster fallback behavior (in companion doc)
- [x] Document separates truth categories: real capability, demo behavior, controlled actions, future claims (in companion doc)
- [x] Document includes safe sales wording table (in companion doc)
- [x] Document includes explicit non-claims table (in companion doc)
- [x] Document defines minimum UI requirements for all screens (in companion doc)
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
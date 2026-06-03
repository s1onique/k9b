# Diagnostic Command Chain and Artifact Lifecycle Audit

**ACT**: Audit diagnostic command chain and artifact lifecycle  
**Date**: 2026-06-03 
**Status**: Complete  

---

## Executive Summary

The k9b diagnostic feedback loop is **partially closed-loop**. Generation, validation, approval, and execution all work. The two missing seams are:

1. **Execution result reuse in next diagnostic step** — Execution artifacts are persisted but not fed back into follow-up diagnostic planning within the same run.

2. **Incident report provenance for execution artifacts** — Execution artifacts are referenced in worklist state but execution results do not flow into incident report fact/hypothesis claims.

**First implementation ACT**: Persist diagnostic command execution artifacts with structured result digest for reuse in next-check planning.

---

## Audit Scope

Map the current k9b diagnostic feedback loop from next-check proposal through command validation, execution, persisted evidence, follow-up diagnostic input, and incident report projection.

**Questions this audit answers:**
1. Where are nextChecks produced?
2. Where are nextChecks validated or rejected?
3. Where can an operator approve or trigger a diagnostic command?
4. What execution artifact is produced?
5. What schema identifies command, cluster, namespace, timestamp, status, stdout/stderr, and provenance?
6. Can later diagnostic steps consume previous command results?
7. Can incident reports cite those command artifacts?
8. What is the smallest implementation ACT that would close the loop?

---

## Loop Segment Assessment

| Segment | Current Status | Evidence | Gap | Next Fix |
|---------|:--------------:|----------|-----|----------|
| nextChecks generation | **Working** | `next_check_planner.py`, `next_check_planner_candidates.py` | None | — |
| nextChecks validation | **Working** | `manual_next_check_gating.py`, `next_check_planner_models.py` | None | — |
| command approval | **Working** | `next_check_approval.py`, `server_feedback.py` | Approval state tracked in artifacts but not integrated into execution gating | Integrate approval status into queue eligibility |
| command execution | **Working** | `manual_next_check.py`, `manual_next_check_commands.py` | None | — |
| execution artifact persistence | **Working** | `manual_next_check_artifacts.py`, `artifact.py` | None | — |
| result reuse in next step | **Missing** | `next_check_planner.py` only uses enrichment artifact, not execution results | Planning cannot consume prior execution outputs within same run | Feed execution artifacts into next-check planning input |
| incident report projection | **Partial** | `api_incident_report.py`, `api_incident_report_worklist.py` | Execution artifacts in worklist but not in report claims | Add execution artifact claims to incident report |

---

## Detailed Evidence

Detailed segment analysis with file-level evidence, schemas, and status is available in:

- [diagnostic-loop-audit-evidence.md](diagnostic-loop-audit-evidence.md) — Full segment-by-segment breakdown with code references, schemas, and gap analysis

---

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DIAGNOSTIC LOOP                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌───────────────────┐     ┌─────────────────────┐     ┌──────────────────┐  │
│  │ nextChecks        │     │ validation          │     │ approval         │  │
│  │ generation        │────▶│                     │────▶│                  │  │
│  └───────────────────┘     └─────────────────────┘     └──────────────────┘  │
│         │                           │                           │             │
│         ▼                           ▼                           ▼             │
│  ┌───────────────────┐     ┌─────────────────────┐     ┌──────────────────┐  │
│  │ next_check_planner│     │ manual_next_check_  │     │ next_check_      │  │
│  │ .py                │     │ gating.py           │     │ approval.py      │  │
│  │                    │     │                    │     │                  │  │
│  │ Plan artifact:     │     │ Mutation detection  │     │ Approval artifact│  │
│  │ - candidates[]    │     │ Family validation  │     │ written         │  │
│  │ - ranking         │     │ Duplicate check    │     │                 │  │
│  └───────────────────┘     └─────────────────────┘     └──────────────────┘  │
│                                    │                           │             │
│                                    ▼                           ▼             │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ command execution ────────────────────────────────────────────────────────││
│  │ manual_next_check.py                                                 ││
│  │                                                                      ││
│  │ ┌──────────────────────────────────────────────────────────────┐    ││
│  │ │ execute_manual_next_check()                                  │    ││
│  │ │ - Build kubectl command                                      │    ││
│  │ │ - Run via subprocess (45s timeout)                          │    ││
│  │ │ - Capture stdout/stderr                                     │    ││
│  │ │ - Write execution artifact                                  │    ││
│  │ └──────────────────────────────────────────────────────────┘    ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                    │                                             │
│                                    ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ execution artifact persistence                                          ││
│  │                                                                      ││
│  │ ┌──────────────────────────────────────────────────────────────┐    ││
│  │ │ external-analysis/{run_id}-next-check-execution-{index}.json │    ││
│  │ │                                                              │    ││
│  │ │ Fields: raw_output, status, duration_ms, stdout/stderr       │    ││
│  │ │          truncated flags, usefulness_class, provenance       │    ││
│  │ └──────────────────────────────────────────────────────────────┘    ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                    │                                             │
│                   ┌────────────────┴────────────────┐                        │
│                   │                                 │                        │
│                   ▼                                 ▼                        │
│  ┌────────────────────────────────┐    ┌───────────────────────────────────┐│
│  │ result reuse in next step      │    │ incident report projection        ││
│  │                                │    │                                   ││
│  │ ❌ MISSING                     │    │ ⚠️ PARTIAL                         ││
│  │                                │    │                                   ││
│  │ - No execution result digest  │    │ - Worklist: execution refs ✓      ││
│  │   in next planning input      │    │ - Incident report: no exec claims ││
│  │ - No chained diagnostics      │    │ - No exec result in report facts  ││
│  │   within same run             │    │                                   ││
│  └────────────────────────────────┘    └───────────────────────────────────┘│
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Findings Summary

| Finding | Status | Impact |
|---------|--------|--------|
| nextChecks generation | WORKING | Full coverage |
| nextChecks validation | WORKING | Full coverage, security model sound |
| Command approval | WORKING | Approval not enforced in execution gate |
| Command execution | WORKING | Full coverage |
| Execution artifact persistence | WORKING | Full coverage, immutable artifacts |
| Result reuse in next step | **MISSING** | Primary blocker for chained diagnostics |
| Incident report projection | **PARTIAL** | Worklist integration only |

---

## Follow-up ACTs

Detailed implementation planning for the next steps is available in:

- [diagnostic-loop-audit-next-acts.md](diagnostic-loop-audit-next-acts.md) — Primary and secondary ACTs with scope, files, and acceptance criteria

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
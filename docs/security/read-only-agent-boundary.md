# k9b Read-Only Agent Boundary

**Document**: Read-Only Agent Boundary  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-06-25  
**Status**: Current

---

## 1. Purpose

This document defines the read-only agent boundary for k9b. The diagnosis loop never mutates cluster state, all tool proposals require operator approval, and the firewall blocks mutation attempts.

---

## 2. Invariants

### INV-2: No Autonomous Cluster Mutations

> **The agent MUST NOT perform direct mutations on live Kubernetes clusters without explicit operator approval.**

All mutation-capable operations require:
- Explicit operator approval
- Execution history logging
- No automated retry

### INV-3: LLM Output Advisory Boundary

> **LLM output is advisory only and MUST NOT directly influence cluster state.**

LLM recommendations require operator review; suggestions are queued for approval, not auto-executed.

---

## 3. Action Firewall

### 3.1 Firewall Rules

The read-only firewall blocks the following operations unless explicitly approved:

| Operation Type | Examples | Default Action |
|----------------|----------|---------------|
| Kubernetes mutations | `kubectl delete`, `kubectl apply`, `kubectl patch` | BLOCK |
| Helm operations | `helm install`, `helm upgrade`, `helm uninstall` | BLOCK |
| Shell commands | `exec`, `run` with mutating verbs | BLOCK |
| SQL operations | INSERT, UPDATE, DELETE, DROP | BLOCK |
| Filesystem writes | File writes outside `runs/` | BLOCK |
| Network mutations | Firewall rules, network policies | BLOCK |

### 3.2 Read-Only Permitted Operations

The following operations are permitted without approval:

| Operation Type | Examples | Justification |
|----------------|----------|---------------|
| Kubernetes reads | `kubectl get`, `kubectl describe`, `kubectl logs` | Read-only; safe |
| Helm template/diff | `helm template`, `helm diff` | Read-only preview |
| File reads | Artifact and config reads | Read-only; within artifact store |
| Diagnostics | Health checks, metric collection | Read-only observation |

---

## 4. Approval Workflow

### 4.1 Approval Required Flow

```
LLM Recommendation
       │
       ▼
Action Firewall Check
       │
       ▼ (passes)
Queued for Operator Review
       │
       ▼ (explicit approval)
Subprocess Execution
       │
       ▼
Execution History Logging
       │
       ▼
Result Artifact Creation
```

### 4.2 Approval API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/next-check-approval` | POST | Approve a queued action |
| `/api/next-check-rejection` | POST | Reject a queued action |
| `/api/next-check-execution` | POST | Execute an approved action |

---

## 5. Implementation

### 5.1 Firewall Implementation

The action firewall is implemented in:
- `src/k8s_diag_agent/security/subprocess_helpers.py`

### 5.2 Enforcement Points

| Component | Enforcement |
|-----------|-------------|
| Next-check execution | Requires explicit approval |
| Proposal replay | Validated before replay |
| Drilldown execution | Read-only by default |
| Review enrichment | Advisory only |

---

## 6. Testing

### 6.1 Firewall Tests

| Test Case | Expected Behavior |
|-----------|------------------|
| Mutation attempt without approval | MUST be blocked |
| Mutation attempt with approval | MUST proceed after approval |
| Read operation without approval | MUST be allowed |
| Approval required for each mutation | MUST be enforced |

---

## 7. Related Documents

| Document | Relationship |
|----------|--------------|
| `threat-model.md` | INV-2 and INV-3 defined |
| `llm-prompt-security-audit.md` | LLM output handling |
| `subprocess_helpers.py` | Firewall implementation |
| `security-policy.md` | Security policy baseline |

---

**Document End**

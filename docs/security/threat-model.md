# k9b Security Threat Model

**Document**: Security Threat Model  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-05-06
**Author**: k9b Security Audit  
**Status**: Initial Draft  

---

## Executive Summary

This document provides a comprehensive threat model for k9b, a Kubernetes monitoring and diagnostics agent. The model maps k9b's architecture against industry-standard security frameworks (STRIDE, OWASP ASVS, OWASP API Security Top 10, OWASP Top 10 for LLM Applications, NIST SSDF, CIS Kubernetes Benchmark, NSA/CISA Kubernetes Hardening Guidance, and SLSA) to identify security risks, existing controls, and remediation priorities.

**Key Findings**: 2 Critical risks, 5 High risks, 7 Medium risks, and 4 Low risks identified across Kubernetes interaction surfaces, LLM integration boundaries, supply chain, and API attack surfaces.

---

## 22. Canonical Risk Register

| ID | Description | Severity | Category | Status |
|----|-------------|----------|---------|--------|
| RISK-01 | Cluster data exfiltration via LLM prompts | CRITICAL | Info Disclosure | ⚠️ Partial |
| RISK-02 | kubectl command injection via queue manipulation | CRITICAL | Elevation | ⚠️ Partial |
| RISK-03 | Prompt injection via malicious cluster data | HIGH | Spoofing | ⚠️ Partial |
| RISK-04 | kubectl/helm binary tampering during build | HIGH | Supply Chain | ⚠️ Partial |
| RISK-05 | Unauthorized cluster mutations via API | HIGH | Tampering | ✅ Mitigated |
| RISK-06 | Sensitive cluster info disclosure to LLM | HIGH | Info Disclosure | ⚠️ Partial |
| RISK-07 | Secrets in logs via instrumentation | HIGH | Info Disclosure | ✅ Mitigated |
| RISK-08 | No RBAC documentation for operators | HIGH | Governance | ✅ Documented |
| RISK-09 | DoS via UI server resource exhaustion | MEDIUM | DoS | ⚠️ Partial |
| RISK-10 | Compromised PyPI dependency | MEDIUM | Supply Chain | ⚠️ Partial |
| RISK-11 | Artifact tampering | MEDIUM | Tampering | ⚠️ Partial |
| RISK-12 | Feedback loop manipulation | MEDIUM | Tampering | ⚠️ Partial |
| RISK-13 | LLM output misdirection to next-checks | MEDIUM | Elevation | ⚠️ Partial |
| RISK-14 | No rate limiting on UI server | MEDIUM | DoS | ⚠️ Partial |
| RISK-15 | Unbounded file glob operations | MEDIUM | DoS | ⚠️ Partial |
| RISK-16 | No vulnerability scanning in CI | MEDIUM | Supply Chain | ❌ Gap |
| RISK-17 | Path injection via run_id | HIGH | Spoofing | ✅ Mitigated |
| RISK-18 | LLM model supply chain compromise | HIGH | Supply Chain | ⚠️ Partial |

---

## 3. Hard Security Invariants

### INV-1: UI Server Network Binding

> **The UI server MUST bind to localhost (127.0.0.1) by default.**

Any non-localhost binding requires:
1. Explicit configuration flag
2. Authentication layer (token-based or mTLS)
3. CSRF protection on mutation endpoints
4. Authorization checks for `/api/next-check-*`, `/api/alertmanager-*`, `/api/run-batch-*`

### INV-2: No Autonomous Cluster Mutations

> **The agent MUST NOT perform direct mutations on live Kubernetes clusters without explicit operator approval.**

All mutation-capable operations require explicit operator approval, execution history logging, and no automated retry.

### INV-3: LLM Output Advisory Boundary

> **LLM output is advisory only and MUST NOT directly influence cluster state.**

LLM recommendations require operator review; suggestions are queued for approval, not auto-executed.

### INV-4: No Credentials in Prompts

> **Credentials, tokens, and secrets MUST NOT appear in LLM prompts.**

All credential-bearing fields must be redacted before prompt construction.

---

## 1. Scope

### 1.1 In Scope

| Component | Description |
|-----------|-------------|
| **Backend** (`src/k8s_diag_agent/`) | Python health loop, collection, assessment, UI API server |
| **Frontend** (`frontend/src/`) | React/TypeScript UI components and hooks |
| **CLI** (`src/k8s_diag_agent/cli.py`) | Command-line diagnostic operators |
| **Scripts** (`scripts/`) | Health scheduler, batch next-check execution, verification |
| **LLM Integration** (`src/k8s_diag_agent/llm/`, `external_analysis/`) | LLM provider adapters (llama.cpp, OpenAI-compatible) |
| **Artifact Storage** (`runs/health/`) | File-based artifact persistence |
| **Docker Container** (`Dockerfile.python`) | Container image build and runtime |

### 1.2 Out of Scope

| Item | Reason |
|------|--------|
| Kubernetes cluster itself | Treated as external system under operator control |
| kubectl/helm runtime behavior | External system dependency; k9b does not control binary execution |
| Third-party LLM providers (external) | Untrusted enrichment boundary; k9b output only |
| Operator workstation security | Out of scope for k9b application security |
| Network infrastructure (firewall, VPN) | Operational environment concern |

### 1.2.1 kubectl/helm Binary Scope Clarification

> **Runtime behavior of kubectl/helm binaries is EXTERNAL and OUT OF SCOPE.**
> **However, the following k9b-internal aspects ARE IN SCOPE:**

| In-Scope Aspect | Description |
|-----------------|-------------|
| **k9b command construction** | How k9b builds subprocess arguments from validated parameters |
| **Build-time binary provenance** | How kubectl/helm binaries are downloaded and installed in Dockerfile |
| **Binary verification** | SHA256 checksum verification during container build |
| **Command hardcoding** | Ensuring commands use only validated, operator-provided parameters |

**Rationale**: k9b must not introduce command injection by constructing malicious subprocess arguments, even if the underlying binaries are trusted. Binary provenance during build is a supply-chain concern that k9b controls.

### 1.3 Trust Boundaries

1. **Trusted Boundary**: k9b backend process, local filesystem (`runs/`), operator environment
2. **Untrusted Boundary**: External LLM providers, operator HTTP requests, cluster data
3. **Semi-trusted**: Kubernetes API (operator-controlled but affects cluster state)

---

## 2. System Overview

### 2.1 Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OPERATOR WORKSTATION                            │
│  ┌─────────────┐    ┌──────────────────────────────────────────────────┐  │
│  │   Browser   │    │              k9b Backend Process                 │  │
│  │   (HTTPS)   │    │  ┌─────────────┐  ┌───────────┐  ┌────────────┐  │  │
│  └──────┬──────┘    │  │ UI Server   │  │HealthLoop │  │  LLM       │  │  │
│         │           │  │ (Threading   │  │ Scheduler │  │  Adapters  │  │  │
│  ┌──────▼──────┐    │  │ HTTPServer)  │  │           │  │            │  │  │
│  │   HTTP      │    │  └──────┬──────┘  └─────┬─────┘  └─────┬──────┘  │  │
│  │   API       │    │         │               │              │         │  │
│  │  (localhost)│    │  ┌──────▼──────────────▼──────────────▼──────┐  │  │
│  └─────────────┘    │  │              Artifact Store               │  │  │
│                     │  │         (runs/health/*.json/*.zip)         │  │  │
│  ┌─────────────────┐│  └───────────────────────────────────────────┘  │  │
│  │  kubectl/helm   ││                                                          │
│  │  (subprocess)   ││                                                          │
│  └────────┬────────┘│                                                          │
└───────────┼──────────┘                                                          │
            │                                                                     │
┌───────────▼──────────────────────────────────────────────────────────────────┐    │
│                         KUBERNETES CLUSTERS (N×)                            │    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                           │    │
│  │  Cluster A  │  │  Cluster B  │  │  Cluster N  │                           │    │
│  └─────────────┘  └─────────────┘  └─────────────┘                           │    │
└──────────────────────────────────────────────────────────────────────────────┘    │
                                                                                 │
┌──────────────────────────────────────────────────────────────────────────────┐    │
│                           EXTERNAL SERVICES                                   │    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────────────┐  │    │
│  │  llama.cpp  │  │  OpenAI     │  │ Mattermost  │  │  Other LLM        │  │    │
│  │  (local)    │  │  Compatible │  │ (Webhook)   │  │  Providers        │  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────────────┘  │    │
└──────────────────────────────────────────────────────────────────────────────┘    │
```

### 2.2 Data Flow Summary

1. **Collection Flow**: Scheduler → HealthLoopRunner → kubectl/helm subprocess → ClusterSnapshot → Artifact
2. **Assessment Flow**: Snapshot → LLM Provider → Assessment/Findings → Artifact
3. **UI Flow**: HTTP Request → API Handler → Artifact Read → Payload → React Frontend
4. **Mutation Flow**: HTTP Request → Approval Check → kubectl/helm subprocess → Cluster
5. **Feedback Flow**: Operator Feedback → Artifact → Learning Update → Ranking/Policy

---

## 3. Security Objectives

### 3.1 Primary Security Goals

| ID | Objective | Standard Mapping |
|----|------------|------------------|
| **GOAL-1** | Prevent unauthorized cluster mutations | STRIDE-S, OWASP ASVS 4.1.3, CIS K8s 7.2 |
| **GOAL-2** | Protect secrets and credentials from leakage | STRIDE-C, OWASP ASVS 6.1.1, NIST SSDF PS.1 |
| **GOAL-3** | Maintain artifact integrity and provenance | SLSA L2, OWASP ASVS 5.1.1 |
| **GOAL-4** | Bound LLM prompt data exposure | OWASP LLM01, OWASP LLM02 |
| **GOAL-5** | Enforce identifier validation throughout | OWASP API10, STRIDE-T |
| **GOAL-6** | Prevent path traversal attacks | STRIDE-T, OWASP ASVS 1.5.1 |
| **GOAL-7** | Maintain operational auditability | NIST SSDF DR.1 |

### 3.2 Non-Goals (Explicit)

- The agent is **not** a hard multi-tenant isolation system
- The agent does **not** encrypt artifacts at rest (intentional tradeoff for observability)
- The agent does **not** provide authentication/authorization for the UI server (assumes localhost/trusted network)

---

## 4. Assets

### 4.1 Asset Inventory

| Asset | Type | Sensitivity | CIA Priority |
|-------|------|-------------|--------------|
| Kubernetes credentials (kubeconfig, tokens) | Credential | **CRITICAL** | C>I>A |
| Cluster state snapshots | PII/Infrastructure | **HIGH** | I>C |
| LLM provider API keys | Credential | **CRITICAL** | C>I>A |
| Cluster identifiers (names, UIDs) | PII | **MEDIUM** | I>C |
| Health assessments and findings | Evidence | **MEDIUM** | I>C |
| Mattermost webhook URLs | Credential | **HIGH** | C>I |
| Operator feedback data | Evidence | **LOW** | I>A |
| Run configurations | Configuration | **MEDIUM** | C>I |
| Artifact files (JSON/ZIP) | Evidence | **MEDIUM** | I>C |

### 4.2 Asset Classification

| Classification | Handling Requirements |
|---------------|----------------------|
| **CRITICAL** | Environment variables only; no disk persistence; redacted from all logs |
| **HIGH** | Redacted from prompts; encrypted at rest preferred; access-controlled |
| **MEDIUM** | Redacted from external APIs; included in local artifacts with sanitization |
| **LOW** | Included in artifacts; standard log hygiene |

---

## 5. Actors

### 5.1 Actor Map

| Actor | Description | Privileges | Threat Posture |
|-------|-------------|------------|----------------|
| **Platform Engineer** | Primary operator; interacts via UI | Full artifact access, approval authority | Trusted insider |
| **Health Loop Scheduler** | Automated background process | Cluster read-only, artifact write | Automated trust |
| **LLM Provider** | External analysis engine | Receives sanitized prompts, returns analysis | Untrusted |
| **Kubernetes Cluster API** | External system | Read/write based on RBAC | Semi-trusted |
| **Mattermost Server** | Notification webhook target | Receives sanitized alerts | External trust |
| **Docker Build Process** | CI/CD supply chain | Builds container image | Trust boundary |
| **Attacker (Network)** | External adversary | Network access to UI server | Threat actor |
| **Attacker (LLM Injection)** | Prompt injection via cluster data | LLM prompt manipulation | Threat vector |

---

## 6. Trust Boundaries

### 6.1 Boundary Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            TRUSTED ZONE                                      │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                    k9b Backend Process                              │    │
│  │                                                                  │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │    │
│  │  │  Artifact  │  │  Path      │  │  Prompt    │  │  LLM     │  │    │
│  │  │  Store     │  │  Validation│  │  Sanitizer │  │  Adapter │  │    │
│  │  └────────────┘  └────────────┘  └────────────┘  └──────────┘  │    │
│  │                                                                  │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐               │    │
│  │  │  UI Server │  │  Health    │  │  Secrets   │               │    │
│  │  │  (localhost)│  │  Loop     │  │  (env vars)│               │    │
│  │  └────────────┘  └────────────┘  └────────────┘               │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────┐  ┌────────────────┐  ┌────────────────┐              │
│  │  runs/health/   │  │  Mattermost   │  │  kubectl/helm  │              │
│  │  (local disk)   │  │  (webhook)    │  │  (subprocess)  │              │
│  └─────────────────┘  └────────────────┘  └────────────────┘              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────┐  ┌─────────────┐  ┌──────────────┐
            │ External  │  │ Kubernetes  │  │   Browser    │
            │ LLM       │  │ Cluster API │  │   (Operator) │
            │ Providers │  │ (N× clusters)│  │             │
            └───────────┘  └─────────────┘  └──────────────┘
                  │               │               │
              UNTRUSTED      SEMI-TRUSTED     TRUSTED (localhost)
```

### 6.2 Boundary Crossings

| From | To | Data Crossing | Trust Level | Controls Required |
|------|----|---------------|------------|-------------------|
| k9b Backend | Kubernetes API | kubectl/helm subprocess | SEMI-TRUSTED | Sanitized commands; no direct auth data |
| k9b Backend | LLM Provider | Sanitized prompts | UNTRUSTED | Redaction; no credentials; no cluster secrets |
| k9b Backend | Mattermost | Alert payload | TRUSTED | Sanitized payload; webhook URL in env |
| Operator Browser | UI Server | HTTP requests | TRUSTED (localhost) | Localhost-only binding |
| k9b Backend | Artifact Store | JSON/ZIP files | TRUSTED | Path validation; trusted root |
| Scheduler | Health Loop | Run trigger | TRUSTED | Process-level trust |

---

## 7. Data Flows

### 7.1 Core Data Flows

#### DF-1: Cluster Snapshot Collection

```
Operator Config (*.local.json)
         │
         ▼
HealthLoopRunner.execute()
         │
         ▼
kubectl/helm subprocess ──► Kubernetes Cluster API
         │                                    │
         ▼                                    ▼
ClusterSnapshot ◄─────────────────────────────┘
         │
         ▼
sanitize_payload() ──► Artifact: {run_id}-snapshot.json
```

**Security Controls**: 
- Path validation (`validate_run_id()`)
- Payload sanitization (`sanitizer.py`)
- No kubeconfig persisted to disk

**Risk**: Unauthorized cluster access via misconfigured contexts

#### DF-2: LLM Assessment (Untrusted Enrichment)

```
ClusterSnapshot
         │
         ▼
sanitize_prompt() ──► LLM Provider (llama.cpp/OpenAI-compatible)
         │                                    │
         │                                    ▼
         │                       External Analysis Result
         │                                    │
         ▼                                    ▼
ExternalAnalysisArtifact ◄──────────────────┘
         │
         ▼
LLM_ASSESSMENT_INPUT validation
```

**Security Controls**:
- Prompt sanitization (credential redaction)
- Schema validation on response
- LLM output treated as "advisory only"

**Risk**: LLM injection via poisoned cluster data

#### DF-3: Operator Feedback Loop

```
Operator Feedback (useful/partial/noisy)
         │
         ▼
FeedbackArtifact
         │
         ▼
Adaptive Learning → Next-check ranking update
```

**Security Controls**:
- Feedback schema validation
- No cluster mutation on feedback

**Risk**: Feedback manipulation to bias diagnostics

#### DF-4: Next-Check Execution (High Risk)

```
POST /api/next-check-execution
         │
         ▼
Queue Entry Selection
         │
         ▼
Operator Approval (explicit)
         │
         ▼
kubectl/helm subprocess ──► Kubernetes Cluster
```

**Security Controls**:
- Mandatory operator approval
- Execution history logging
- No autonomous cluster mutation

**Risk**: Command injection via queue manipulation

### 7.2 Data Flow Mapping to Assets

| Data Flow | Assets Accessed | Assets Created | Confidentiality Impact |
|----------|-----------------|-----------------|----------------------|
| DF-1 | Cluster credentials | Snapshot | Cluster state exposed |
| DF-2 | Snapshot data | LLM assessment | Cluster state to external |
| DF-3 | Feedback data | Learning update | Feedback patterns |
| DF-4 | Execution history | Cluster state change | Execution commands |

---

## 8. Privileged Operations

### 8.1 Privileged Operation Inventory

| Operation | Privilege Level | Authorization | Audit Required |
|-----------|----------------|---------------|-----------------|
| kubectl/helm subprocess execution | CLUSTER WRITE | Operator approval | Yes |
| LLM provider invocation | NETWORK | Env vars | Yes |
| Mattermost notification delivery | NETWORK | Env var (webhook URL) | No |
| File artifact creation | FILESYSTEM | Process ownership | Yes |
| Diagnostic pack export | FILESYSTEM | Process ownership | Yes |
| UI index modification | FILESYSTEM | Process ownership | Yes |

### 8.2 Elevated Risk Operations

| Operation | Risk | Justification | Mitigations |
|-----------|------|---------------|-------------|
| kubectl exec | **CRITICAL** | Direct cluster manipulation | Operator approval only; command validation |
| helm upgrade | **CRITICAL** | Cluster state change | Operator approval only; dry-run option |
| LLM prompt injection | **HIGH** | External data in prompts | Sanitization; credential redaction |
| Path traversal | **HIGH** | Filesystem access | Path validation; trusted root |
| Subprocess command injection | **CRITICAL** | Arbitrary command execution | Hardcoded commands only; argument validation |

---

## 9. Attack Surfaces

### 9.1 Attack Surface Inventory

| Surface | Type | Entry Point | Severity |
|---------|------|------------|----------|
| UI HTTP Server | Network | `localhost:8080` | MEDIUM (localhost only) |
| Next-check execution API | API | `POST /api/next-check-execution` | **HIGH** |
| Proposal approval API | API | `POST /api/next-check-approval` | HIGH |
| Deterministic promotion API | API | `POST /api/deterministic-promotion` | MEDIUM |
| Alertmanager feedback API | API | `POST /api/alertmanager-relevance-feedback` | MEDIUM |
| Alertmanager source action API | API | `POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action` | HIGH |
| Run ID interpolation | Input | All API requests with `run_id` | HIGH |
| Kubernetes subprocess | Command Injection | Cluster interaction | **CRITICAL** |
| LLM prompt construction | Injection | Cluster data → prompts | **HIGH** |
| Mattermost webhook | Exfiltration | Notification delivery | LOW |
| Docker build | Supply Chain | CI/CD pipeline | **HIGH** |
| Python dependencies | Supply Chain | `pyproject.toml` | **HIGH** |

### 9.2 Input Vectors

| Vector | Validation | Sanitization | Notes |
|--------|-----------|--------------|-------|
| `run_id` (path parameter) | ✅ `validate_run_id()` | N/A (validation only) | Prevents path traversal |
| `run_id` (query parameter) | ✅ `validate_run_id()` | N/A | Via server_reads.py |
| `run_id` (request body) | ✅ `validate_run_id()` | N/A | Via server_next_checks.py |
| `source_id` (URL encoded) | ⚠️ PARTIAL | N/A | URL decoding before use |
| Cluster context names | ⚠️ KUBECONFIG | None | Loaded from local config |
| Snapshot content | ❌ NO VALIDATION | ⚠️ Partial via sanitizer | Cluster data enters prompts |
| LLM responses | ⚠️ Schema validation | N/A | Untrusted by design |

---

## 10. STRIDE Threat Analysis

### 10.1 STRIDE Category Mapping

| ID | Threat | Category | Affected Component | Severity | Status |
|----|--------|----------|-------------------|----------|--------|
| S-01 | SQL/Path injection via run_id | **Spoofing** | All API endpoints | **HIGH** | ✅ Mitigated via `validate_run_id()` |
| S-02 | Credential theft via kubeconfig | **Spoofing** | kubectl/helm subprocess | **CRITICAL** | ✅ Env var only; `.gitignore` |
| S-03 | LLM prompt injection | **Spoofing** | LLM provider adapters | **HIGH** | ⚠️ Partial via `sanitizer.py` |
| T-01 | Unauthorized cluster mutations | **Tampering** | kubectl/helm subprocess | **CRITICAL** | ✅ Operator approval required |
| T-02 | Artifact tampering | **Tampering** | Artifact store | MEDIUM | ⚠️ No integrity verification |
| T-03 | Proposal manipulation | **Tampering** | Proposal lifecycle | **HIGH** | ✅ Explicit approval workflow |
| T-04 | Feedback loop manipulation | **Tampering** | Adaptive learning | MEDIUM | ⚠️ No validation of feedback source |
| R-01 | Denial of service via malformed run_id | **Repudiation** | API endpoints | LOW | ✅ Graceful error handling |
| R-02 | Cluster state manipulation without audit | **Repudiation** | All cluster mutations | **HIGH** | ⚠️ Execution history exists |
| I-01 | Cluster data exfiltration via LLM | **Information Disclosure** | LLM provider | **CRITICAL** | ⚠️ Sanitization in progress |
| I-02 | Secrets in logs | **Information Disclosure** | Logging subsystem | **HIGH** | ✅ Structured logging policy |
| I-03 | Credential in artifact filenames | **Information Disclosure** | Artifact naming | LOW | ✅ No credentials in filenames |
| D-01 | UI server resource exhaustion | **Denial of Service** | HTTP server | MEDIUM | ⚠️ No rate limiting |
| D-02 | Subprocess timeout/exhaustion | **Denial of Service** | kubectl/helm calls | MEDIUM | ✅ Timeouts defined |
| D-03 | In-memory cache exhaustion | **Denial of Service** | Cache modules | LOW | ✅ Max cache entries defined |
| D-04 | Unbounded file glob operations | **Denial of Service** | Artifact scanning | MEDIUM | ⚠️ No glob depth limits |
| E-01 | Privilege escalation via kubectl exec | **Elevation of Privilege** | kubectl subprocess | **CRITICAL** | ✅ Never auto-exec; operator approval |
| E-02 | Elevation via malicious LLM output | **Elevation of Privilege** | LLM integration | **HIGH** | ✅ LLM output is advisory only |

### 10.2 STRIDE Mitigation Status

| Category | Threats | Mitigated | Partial | Unmitigated |
|----------|---------|-----------|---------|-------------|
| **Spoofing** | 3 | 1 | 2 | 0 |
| **Tampering** | 4 | 3 | 1 | 0 |
| **Repudiation** | 2 | 0 | 2 | 0 |
| **Information Disclosure** | 3 | 2 | 1 | 0 |
| **Denial of Service** | 4 | 2 | 2 | 0 |
| **Elevation of Privilege** | 2 | 1 | 1 | 0 |
| **TOTAL** | 18 | 9 (50%) | 9 (50%) | 0 (0%) |

---

## 11. LLM-Specific Threats

### 11.1 OWASP Top 10 for LLM Applications Mapping

| ID | Threat | k9b Attack Vector | Severity | Current Controls |
|----|--------|-------------------|----------|------------------|
| **LLM01** | Prompt Injection | Malicious cluster data in prompts | **HIGH** | ⚠️ Partial sanitization |
| **LLM02** | Insecure Output Handling | Unvalidated LLM response parsing | MEDIUM | ✅ Schema validation |
| **LLM03** | Training Data Poisoning | N/A (not training) | N/A | N/A |
| **LLM04** | Model Denial of Service | Excessive LLM calls | MEDIUM | ⚠️ Budget limits in policy |
| **LLM05** | Supply Chain Vulnerabilities | Compromised model/weights | **HIGH** | ⚠️ Local model only (partial) |
| **LLM06** | Sensitive Information Disclosure | Cluster data to LLM provider | **CRITICAL** | ⚠️ Sanitization in progress |
| **LLM07** | Insecure Plugin Design | N/A (no plugins) | N/A | N/A |
| **LLM08** | Excessive Agency | LLM-driven autonomous actions | MEDIUM | ✅ Approval workflow |
| **LLM09** | Overreliance | Unvalidated LLM recommendations | MEDIUM | ✅ "Advisory only" policy |
| **LLM10** | Model Theft | Model exfiltration | LOW | ✅ Local llama.cpp |

### 11.2 LLM Threat Details

#### LLM01: Prompt Injection

**Vector**: Cluster warning events, pod descriptions, CRD data containing injected prompts  
**Risk**: Attacker with namespace edit access could inject instructions into cluster events that appear in snapshots  
**Current State**: ⚠️ `_sanitize_string()` handles basic patterns, but recursive/nested injection not validated  
**Mitigation Required**: 
- Add structured prompt construction with explicit field boundaries
- Validate cluster data schema before prompt inclusion
- Add injection detection patterns

#### LLM06: Sensitive Information Disclosure

**Vector**: Cluster snapshots containing namespace names, pod names, labels, resource configs  
**Risk**: Confidential infrastructure details exposed to external LLM provider  
**Current State**: ⚠️ Basic sanitization in `sanitizer.py`, but namespace/cluster names not systematically redacted  
**Mitigation Required**:
- Add cluster/namespace anonymization layer
- Validate what data enters prompts vs. stays local
- Document redaction boundaries

---

## 12. Kubernetes-Specific Threats

### 12.1 CIS Kubernetes Benchmark Mapping

| ID | Control | k9b Implementation | Status |
|----|---------|-------------------|--------|
| 1.1.1 | RBAC for kubelet | N/A (operator responsibility) | OUT OF SCOPE |
| 5.1.1 | RBAC for cluster access | ⚠️ Operator responsibility | Operator config |
| 5.1.5 | Least privilege for kubectl | ⚠️ Depends on kubeconfig | Operator config |
| 5.3.2 | Network policies | ⚠️ Operator responsibility | Operator config |
| 5.4.1 | secrets management | ✅ Environment variables only | Compliant |
| 6.1.1 | Unauthorized RBAC | ⚠️ Depends on kubeconfig | Operator config |
| 7.2 | Cluster component access | ✅ Approval workflow | Compliant |

### 12.2 NSA/CISA Kubernetes Hardening Mapping

| ID | Guideline | k9b Alignment | Gap |
|----|-----------|---------------|-----|
| KHV-1 | RBAC least privilege | ⚠️ Via operator kubeconfig | No RBAC audit in k9b |
| KHV-2 | Authentication | N/A | k9b trusts kubectl config |
| KHV-3 | Confidential data | ⚠️ Sanitization in progress | Partial |
| KHV-4 | Pod security | N/A | Not in scope |
| KHV-5 | Network policies | N/A | Not in scope |
| KHV-6 | Audit logging | ⚠️ Execution history exists | No cluster audit integration |
| KHV-7 | Image security | ⚠️ External dependency | No image scanning |
| KHV-8 | Runtime security | N/A | Not in scope |

### 12.3 Kubernetes Threat Details

#### K8S-01: kubectl Command Injection

**Vector**: Malicious cluster data could influence subprocess arguments  
**Risk**: If cluster data influences command construction, attacker could execute arbitrary kubectl commands  
**Current State**: ✅ Commands are hardcoded with validated context parameter; context comes from config only  
**Evidence**: `live_snapshot.py` uses `_run_command(["kubectl", *args, "--context", context])` - context from config only  

#### K8S-02: RBAC Misuse Detection

**Risk**: k9b executes commands with full kubeconfig permissions; no least-privilege verification  
**Current State**: ⚠️ Operator responsibility; k9b assumes kubeconfig has required permissions  
**Mitigation Required**: Document required RBAC permissions for k9b operations

---

## 13. Supply-Chain Threats

### 13.1 SLSA Compliance Assessment

| Level | Requirement | k9b Status | Evidence |
|-------|-------------|------------|----------|
| **L1** | Provenance generated | ⚠️ Git commit available | No SLSA attestation |
| **L2** | Provenance signed | ❌ No signing | Gap |
| **L3** | Hermetic build | ⚠️ Partial | curl downloads kubectl/helm |
| **L4** | Hardened build | ❌ No attestation | Gap |

### 13.2 Dependency Threat Analysis

| Dependency | Version Source | Update Mechanism | Vulnerability Scanning | Risk |
|------------|---------------|-----------------|----------------------|------|
| Python 3.12 | `Dockerfile.python` | Manual update | ⚠️ None | MEDIUM |
| kubectl v1.29.6 | `Dockerfile.python` ARG | Manual update | ⚠️ None | HIGH |
| helm 3.20.1 | `Dockerfile.python` ARG | Manual update | ⚠️ None | HIGH |
| ijson >=3.2 | `pyproject.toml` | pip | ⚠️ None | MEDIUM |
| requests >=2.31.0 | `pyproject.toml` | pip | ⚠️ None | MEDIUM |

### 13.3 Supply Chain Threats

#### SUPPLY-01: Compromised Dependency

**Vector**: Malicious PyPI package with same name  
**Risk**: Code execution during pip install  
**Current State**: ⚠️ No hash pinning; no private index  
**Mitigation**: Pin hashes for critical dependencies

#### SUPPLY-02: Unverified kubectl/helm Binaries

**Vector**: `curl` download from `dl.k8s.io` and `get.helm.sh`  
**Risk**: Man-in-the-middle during build  
**Current State**: ⚠️ No checksum verification in Dockerfile  
**Mitigation**: Add SHA256 verification for downloaded binaries

#### SUPPLY-03: No SBOM Generation

**Risk**: No software bill of materials for vulnerability tracking  
**Current State**: ❌ No SBOM  
**Mitigation**: Generate SBOM on build (future)

---

## 14. Existing Controls

### 14.1 Security Controls Implemented

| Control | Implementation | Effectiveness | Coverage |
|---------|---------------|--------------|----------|
| **Identifier Validation** | `security/path_validation.py` | HIGH | All run_id usage |
| **Payload Sanitization** | `security/sanitizer.py` | MEDIUM | LLM prompts, logs |
| **Subprocess Security** | `security/subprocess_helpers.py` | HIGH | stderr capture |
| **Path Containment** | `safe_child_path()` | HIGH | Artifact file access |
| **Secrets Exclusion** | `.gitignore` | HIGH | Git commits |
| **No Autonomous Mutations** | `security-policy.md` | HIGH | Policy enforced |
| **LLM Advisory Only** | Policy documentation | MEDIUM | Not code-enforced |
| **Operator Approval** | Workflow design | HIGH | All cluster ops |
| **Structured Logging** | `structured_logging.py` | HIGH | Audit trail |
| **Exception Handling** | Policy in `security-standards.md` | MEDIUM | No silent swallower |

### 14.2 Security Documents

| Document | Purpose | Last Updated |
|----------|---------|--------------|
| `docs/security-policy.md` | Operational security policy | Unknown |
| `docs/security-standards.md` | Implementation standards | 2024-05 |
| `docs/security-glob-audit.md` | Path traversal audit | 2026-05-01 |
| `docs/security-subprocess-audit.md` | Subprocess security audit | Unknown |
| `docs/security-exception-audit.md` | Exception handling audit | Unknown |

### 14.3 Security Tests

| Test | Coverage |
|------|----------|
| `tests/test_security_path_validation.py` | run_id validation |
| `tests/test_security_subprocess_helpers.py` | subprocess security |
| `tests/test_logging_security.py` | secrets in logs |
| `tests/test_server_read_support_security.py` | glob security |

---

## 15. Security Gaps

### 15.1 Gap Analysis

| Gap ID | Description | Severity | Risk Score | Feasibility |
|--------|-------------|----------|------------|-------------|
| **GAP-01** | No cluster data anonymization before LLM prompts | **CRITICAL** | 9 | HIGH |
| **GAP-02** | No RBAC permission documentation | ~~**HIGH**~~ | ~~7~~ | ✅ Addressed by `docs/security/rbac-deployment-guide.md` |
| **GAP-03** | No SLSA attestation on builds | **HIGH** | 6 | MEDIUM |
| **GAP-04** | No kubectl/helm binary verification | **HIGH** | 7 | HIGH |
| **GAP-05** | No rate limiting on UI server | **MEDIUM** | 5 | HIGH |
| **GAP-06** | No artifact integrity verification | **MEDIUM** | 5 | HIGH |
| **GAP-07** | No injection detection in prompts | **HIGH** | 7 | MEDIUM |
| **GAP-08** | No vulnerability scanning in CI | **MEDIUM** | 4 | MEDIUM |
| **GAP-09** | No dependency hash pinning | **MEDIUM** | 5 | HIGH |
| **GAP-10** | No LLM output schema enforcement at runtime | **MEDIUM** | 5 | HIGH |

### 15.2 Gap Details

#### GAP-01: Cluster Data Anonymization (CRITICAL)

**Current State**: `sanitizer.py` handles basic patterns, but cluster metadata (namespace names, node names, workload names) is not systematically anonymized before LLM prompts.  
**Risk**: Sensitive infrastructure details exposed to external LLM providers.  
**Evidence**: `sanitize_prompt()` uses regex patterns but namespace names are not systematically replaced.  
**Recommended Fix**: 
1. Add anonymization layer that maps cluster names to aliases
2. Document which fields enter prompts vs. stay local
3. Add tests with adversarial cluster data

#### GAP-02: RBAC Documentation (HIGH)

**Current State**: Documented in `docs/security/rbac-deployment-guide.md`.  
**Risk**: Operators may grant excessive permissions to k9b's service account.  
**Recommended Fix**: See RBAC deployment guide for minimum required RBAC rules.  
**Status**: ✅ Addressed - see `docs/security/rbac-deployment-guide.md`

#### GAP-07: Prompt Injection Detection (HIGH)

**Current State**: `sanitizer.py` handles regex patterns but no structured injection detection.  
**Risk**: Malicious cluster data with prompt injection instructions could bypass basic sanitization.  
**Recommended Fix**: Add structured prompt construction with explicit field boundaries and injection detection.

---

## 16. Prioritized Remediation Backlog

### 16.1 Critical Priority (Immediate Action)

| ID | Remediation | Effort | Priority | Owner | Dependencies |
|----|-------------|--------|----------|-------|-------------|
| **REM-C1** | Implement cluster data anonymization before LLM prompts | 2 weeks | **P0** | Backend | GAP-01 |
| **REM-C2** | Add prompt structure with explicit boundaries | 1 week | **P0** | Backend | GAP-01 |
| **REM-C3** | Audit all LLM prompt construction paths | 3 days | **P0** | Backend | GAP-01 |

### 16.2 High Priority (Within 30 Days)

| ID | Remediation | Effort | Priority | Owner | Dependencies |
|----|-------------|--------|----------|-------|-------|-------------|
| **REM-H1** | Add kubectl/helm binary checksum verification | 1 week | **P1** | DevOps | GAP-04 |
| **REM-H2** | Document minimum RBAC permissions | ~~2 days~~ | ✅ DONE | Docs | GAP-02 |
| **REM-H3** | Pin dependency hashes in pyproject.toml | 1 day | **P1** | DevOps | GAP-09 |
| **REM-H4** | Add injection detection patterns | 1 week | **P1** | Backend | GAP-07 |
| **REM-H5** | Add artifact integrity verification (SHA256) | 1 week | **P1** | Backend | GAP-06 |

### 16.3 Medium Priority (Within 90 Days)

| ID | Remediation | Effort | Priority | Owner | Dependencies |
|----|-------------|--------|----------|-------|-------|-------------|
| **REM-M1** | Add rate limiting to UI server | 2 days | **P2** | Backend | GAP-05 |
| **REM-M2** | Integrate vulnerability scanning in CI | 3 days | **P2** | DevOps | GAP-08 |
| **REM-M3** | Add LLM output schema enforcement tests | 1 week | **P2** | Backend | GAP-10 |
| **REM-M4** | Generate SBOM on build | 2 weeks | **P2** | DevOps | Supply chain |

### 16.4 Low Priority (Backlog)

| ID | Remediation | Effort | Priority | Owner | Dependencies |
|----|-------------|--------|----------|-------|-------|-------------|
| **REM-L1** | Generate SLSA attestations | 2 weeks | **P3** | DevOps | GAP-03 |
| **REM-L2** | Add audit logging for cluster RBAC checks | 1 week | **P3** | Backend | K8S-02 |

---

## 17. Verification Plan

### 17.1 Verification Objectives

1. Validate all identified gaps against actual implementation
2. Confirm existing controls are correctly implemented
3. Test security-relevant code paths with adversarial inputs
4. Verify compliance with documented security policies

### 17.2 Verification Steps

| Step | Description | Method | Success Criteria |
|------|-------------|--------|------------------|
| V1 | Verify identifier validation coverage | Code search for `validate_run_id()` usage | All external run_id inputs validated |
| V2 | Test prompt sanitization | Fuzz prompts with injection patterns | All patterns sanitized |
| V3 | Review LLM adapter code | Manual code review | All prompts use sanitizer |
| V4 | Check subprocess command construction | Code review | All commands hardcoded |
| V5 | Review artifact write paths | Code review | All use `safe_child_path()` |
| V6 | Verify secrets exclusion | `.gitignore` audit | No secrets in sample artifacts |
| V7 | Test Dockerfile build | Execute `docker build` | Image builds successfully |
| V8 | Run security tests | `pytest tests/test_security_*.py` | All tests pass |
| V9 | Verify policy documents | Document review | All policies current |

### 17.3 Verification Commands

```bash
# Run security tests
.venv/bin/python -m pytest tests/test_security_path_validation.py tests/test_security_subprocess_helpers.py tests/test_logging_security.py -v

# Run linting
.venv/bin/ruff check src/k8s_diag_agent/security/ --select=E,F,I

# Check for secrets in codebase
rtk grep -r "password\|api_key\|secret\|token" src/k8s_diag_agent/ --include="*.py"

# Verify Dockerfile builds
docker build -f Dockerfile.python -t k9b:test .

# Run verification gate
./scripts/verify_all.sh
```

---

## 18. Open Questions

### 18.1 Requires Operator Clarification

| ID | Question | Impact | Blocking |
|----|-----------|--------|----------|
| **Q1** | What is the intended network exposure of the UI server? (localhost vs. internal network vs. internet) | Affects authentication requirements | YES |
| **Q2** | Are there approved external LLM providers, or is llama.cpp the only option? | Affects sanitization requirements | YES |
| **Q3** | Should cluster metadata (namespace names, node names) be anonymized in all contexts? | Affects anonymization scope | YES |
| **Q4** | Is there a defined RBAC profile that operators should use for k9b? | Affects documentation scope | NO |
| **Q5** | What is the data retention policy for artifacts? | Affects PII handling | NO |
| **Q6** | Should k9b support multi-user authentication? | Affects UI server design | NO |

### 18.2 Unknowns Requiring Discovery

| ID | Unknown | Discovery Method | Priority |
|----|---------|------------------|----------|
| **U1** | Are there any existing penetration test reports? | Document search | HIGH |
| **U2** | What is the current CVE status of dependencies? | Dependency scan | HIGH |
| **U3** | Has there been any security incident history? | Operator interview | MEDIUM |
| **U4** | Are there regulatory compliance requirements? (SOC2, HIPAA, etc.) | Stakeholder interview | MEDIUM |

---

## 19. Top 10 Initial Risks

| Rank | Risk ID | Description | Severity | Likelihood | Risk Score | Top Remediations |
|------|---------|-------------|----------|------------|------------|------------------|
| 1 | **RISK-01** | Cluster data exfiltration via LLM prompts | **CRITICAL** | MEDIUM | 9/10 | REM-C1, REM-C2 |
| 2 | **RISK-02** | kubectl command injection via queue manipulation | **CRITICAL** | LOW | 8/10 | REM-C3 audit |
| 3 | **RISK-03** | Prompt injection via malicious cluster data | **HIGH** | MEDIUM | 7/10 | REM-H4, REM-C3 |
| 4 | **RISK-04** | kubectl/helm binary tampering during build | **HIGH** | LOW | 7/10 | REM-H1 |
| 5 | **RISK-05** | Unauthorized cluster mutations via API | **HIGH** | LOW | 6/10 | Existing approval workflow |
| 6 | **RISK-06** | Sensitive cluster info disclosure to LLM | **HIGH** | MEDIUM | 7/10 | REM-C1, REM-C2 |
| 7 | **RISK-07** | Secrets in logs via instrumentation | **HIGH** | MEDIUM | 6/10 | Existing controls strong |
| 8 | **RISK-08** | No RBAC documentation for operators | **HIGH** | HIGH | 6/10 | REM-H2 |
| 9 | **RISK-09** | DoS via UI server resource exhaustion | MEDIUM | MEDIUM | 5/10 | REM-M1 |
| 10 | **RISK-10** | Compromised PyPI dependency | MEDIUM | LOW | 4/10 | REM-H3 |

---

## 20. Follow-Up Audit Board

### 20.1 Audit Work Items

| ID | Title | Priority | Type | Status |
|----|-------|----------|------|-------|--------|
| **AU-01** | LLM Prompt Security Audit | **CRITICAL** | Deep Dive | Pending |
| **AU-02** | kubectl/helm Subprocess Security Audit | **HIGH** | Deep Dive | Pending |
| **AU-03** | Dependency CVE Scan and Remediation | **HIGH** | Scan | Pending |
| **AU-04** | Dockerfile Supply Chain Audit | **HIGH** | Review | Pending |
| **AU-05** | UI Server Security Hardening | **MEDIUM** | Implementation | Pending |
| **AU-06** | RBAC Documentation | **HIGH** | Documentation | ✅ Addressed |
| **AU-07** | Artifact Integrity Implementation | **MEDIUM** | Implementation | Pending |
| **AU-08** | Prompt Injection Red Team Testing | **HIGH** | Red Team | Pending |
| **AU-09** | Rate Limiting Implementation | **MEDIUM** | Implementation | Pending |
| **AU-10** | SBOM Generation | **LOW** | Implementation | Backlog |

### 20.2 Next Steps

1. **Immediate**: Address Q1-Q3 (clarify network exposure, LLM providers, anonymization scope)
2. **Week 1**: Implement REM-C1 (cluster data anonymization) and REM-C2 (prompt structure)
3. **Week 2**: Complete LLM prompt security audit (AU-01)
4. **Week 3**: Address REM-H1 (binary verification) and REM-H3 (hash pinning)
5. **Month 2**: Complete remaining high-priority items

---

## 21. Appendix

### 21.1 Standards Mapping

| Standard | Sections Covered |
|----------|------------------|
| STRIDE | Section 10 |
| OWASP ASVS | Sections 9, 11 |
| OWASP API Security Top 10 | Section 9 |
| OWASP Top 10 for LLM Apps | Section 11 |
| OWASP SAMM | Governance, Security Testing |
| NIST SSDF | PS.1, PS.2, DR.1, DR.2 |
| CIS Kubernetes Benchmark | Section 12 |
| NSA/CISA K8s Hardening | Section 12 |
| SLSA | Section 13 |

### 21.2 Glossary

| Term | Definition |
|------|------------|
| **CIA** | Confidentiality, Integrity, Availability |
| **RBAC** | Role-Based Access Control |
| **SBOM** | Software Bill of Materials |
| **SLSA** | Supply-chain Levels for Software Artifacts |
| **SSDF** | Secure Software Development Framework |

### 21.3 References

- [STRIDE Threat Modeling](https://docs.microsoft.com/en-us/azure/security/develop/threat-modeling-tool)
- [OWASP ASVS 4.0](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-llm-applications/)
- [NIST SSDF](https://csrc.nist.gov/publications/detail/sp/800-218/final)
- [CIS Kubernetes Benchmark](https://www.cisecurity.org/benchmark/kubernetes)
- [NSA/CISA Kubernetes Hardening Guide](https://media.defense.gov/2022/Aug/29/2003066362/-1/-1/0/CTR_KUBERNETES_HARDENING_GUIDANCE_1.2_20220829.PDF)
- [SLSA](https://slsa.dev/)

---

## 22. Security Audit Closeout

### 22.1 Audit Closeout Report

The k9b security audit meta-epic has been completed. See the closeout report for full details:

**Document**: `docs/security/security-audit-closeout.md`

**Key Outcomes**:
- 2 CRITICAL risks mitigated (RISK-01 partial, RISK-02 mitigated)
- 5 HIGH risks addressed (RISK-05, RISK-07, RISK-08, RISK-17, RISK-18)
- 4 audit deep-dives completed (AU-01 through AU-04)
- 13 remediation items completed
- 7 follow-up epics recommended for next cycle

**Go/No-Go Posture**: **GO** - System safe to deploy with documented operational constraints.

### 22.2 Related Documents

| Document | Purpose |
|----------|---------|
| `security-audit-closeout.md` | Meta-epic closeout report |
| `llm-prompt-security-audit.md` | AU-01: LLM prompt security deep-dive |
| `subprocess-security-audit.md` | AU-02: Subprocess security deep-dive |
| `api-security-audit.md` | AU-03: API security analysis |
| `operator-auth-design.md` | API-R3: Authentication design |
| `artifact-integrity-audit.md` | Artifact integrity and provenance |
| `rbac-deployment-guide.md` | RBAC permissions guidance |

**Document End**

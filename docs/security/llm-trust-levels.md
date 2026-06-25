# k9b LLM Prompt Context Trust Levels

**Document**: LLM Prompt Context Trust Levels  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-06-25  
**Status**: Current

---

## 1. Purpose

This document defines the trust levels for different context types entering LLM prompts. System/developer policy, trusted internal context, user input, Kubernetes evidence, logs, tool output, external documents, and previous LLM output must not be treated as the same trust level.

---

## 2. Trust Level Matrix

| Trust Level | Context Type | Description | Trust Justification | Verification Required |
|-------------|-------------|-------------|--------------------|-----------------------|
| **L0: System Policy** | System prompts, developer instructions | Hard-coded policy text authored by k9b developers | Highest trust; directly authored | Code review, doctrine review |
| **L1: Trusted Internal** | Schemas, tool definitions, approved templates | Controlled by k9b, not user/contributor | Trust boundary enforced by k9b | Version control, code review |
| **L2: Operator Input** | CLI flags, config files, approval decisions | Provided by authenticated operator | Trust via authentication boundary | Input validation, sanitization |
| **L3: Cluster Evidence** | Snapshots, drilldowns, assessment artifacts | Collected from Kubernetes clusters | Semi-trusted; operator controls cluster | Sanitization, schema validation |
| **L4: User-Provided Docs** | Operator-uploaded documents, feedback | Provided by human operators | Trust via authentication | Content scanning, size limits |
| **L5: LLM Output** | Previous LLM responses, recommendations | Output from untrusted external provider | Untrusted by design | Schema validation, firewall |
| **L6: External Data** | Alertmanager alerts, webhook payloads | From external systems | Untrusted; may contain injection | Sanitization, validation |

---

## 3. Trust Boundary Enforcement

### 3.1 Boundary Markers

All untrusted content (L3-L6) MUST be wrapped with explicit boundary markers:

```
===== BEGIN_UNTRUSTED_CLUSTER_DATA =====
{untrusted content here}
===== END_UNTRUSTED_CLUSTER_DATA =====

===== BEGIN_OUTPUT_SCHEMA =====
{schema definition here}
===== END_OUTPUT_SCHEMA =====
```

**Rationale**: Boundary markers help the LLM distinguish trusted instructions from untrusted evidence, reducing prompt injection risk.

### 3.2 Concatenation Rules

| Source Level | Target Level | Allowed? | Conditions |
|--------------|--------------|----------|------------|
| L0-L2 | L0 (system prompt) | ✅ Yes | Direct concatenation allowed |
| L3-L6 | L0 (system prompt) | ❌ Never | Must use boundary markers |
| L3-L6 | L1 (templates) | ⚠️ Conditional | Only after sanitization |
| Any | L5 (LLM output) | ❌ Never | LLM output is always L5 |

---

## 4. Untrusted Content Handling

### 4.1 Required Processing Pipeline

All L3-L6 content MUST pass through:

1. **Sanitization**: `sanitize_prompt()` removes credentials and sensitive patterns
2. **Boundary Wrapping**: Content wrapped with `BEGIN_UNTRUSTED_CLUSTER_DATA` markers
3. **Schema Validation**: JSON content validated against expected schemas
4. **Size Limits**: Content bounded by max token limits and truncation

### 4.2 Prohibited Patterns in Untrusted Content

The following patterns indicate potential prompt injection and must trigger alerts:

| Pattern | Risk | Action |
|---------|------|--------|
| `===== ` at start of line | Fake boundary marker | Strip or quarantine |
| `system:` / `developer:` / `assistant:` | Fake role markers | Quarantine |
| `[INST]` / `<<SYS>>` | jailbreak delimiters | Quarantine |
| `\u200b` / `\u200c` (zero-width) | Hidden characters | Strip |
| `ignore previous instructions` | Injection phrase | Quarantine |
| `forget all rules` | Injection phrase | Quarantine |

---

## 5. Evidence Trust Classification

### 5.1 Cluster Evidence (L3)

| Evidence Type | Trust Rating | Notes |
|---------------|--------------|-------|
| ClusterSnapshot metadata | MEDIUM | Contains cluster names, node counts |
| Pod descriptions | MEDIUM | May contain injected content |
| Events | LOW | Attacker-controlled namespace = injection risk |
| Logs | MEDIUM | May contain secrets; may be manipulated |
| Resource configs | MEDIUM | Generally safe; YAML may contain injected content |
| Secrets (manifests) | HIGH RISK | Always redacted before prompts |

### 5.2 External Data (L6)

| Data Type | Trust Rating | Notes |
|-----------|--------------|-------|
| Alertmanager alerts | LOW | External system; may contain injection |
| Mattermost webhooks | MEDIUM | Internal system; still sanitized |
| Operator feedback | MEDIUM | Human input; still bounded |
| Uploaded files | LOW | Unbounded user content; size limits applied |

---

## 6. Testing Requirements

### 6.1 Boundary Enforcement Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Untrusted content in system position | L3 content placed before policy | MUST fail or be rejected |
| Boundary marker spoofing | `===== BEGIN_UNTRUSTED` in evidence | MUST be stripped/quarantined |
| Role marker injection | `system:` in cluster data | MUST be stripped/quarantined |
| Jailbreak delimiter injection | `[INST]` in pod description | MUST be stripped/quarantined |
| Zero-width character injection | `\u200b` in event message | MUST be stripped |

### 6.2 Trust Level Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| System prompt integrity | Direct modification attempt | Cannot be concatenated without markers |
| Sanitization completeness | All credential patterns | MUST be redacted before prompt |
| Size limit enforcement | Oversized evidence | MUST be truncated |

---

## 7. Related Documents

| Document | Relationship |
|----------|--------------|
| `llm-provider-boundary.md` | Provider data flow |
| `llm-prompt-security-audit.md` | Deep-dive on prompt paths |
| `prompt_boundaries.py` | Implementation of boundary markers |
| `sanitizer.py` | Implementation of sanitization |

---

**Document End**

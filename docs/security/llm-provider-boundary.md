# k9b LLM Provider Boundary

**Document**: LLM Provider Boundary  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-06-25  
**Status**: Current

---

## 1. Purpose

This document defines the explicit boundary between k9b and its LLM providers. It specifies:
- What data is sent to an LLM provider
- Where credentials come from
- What is masked before transmission
- What is logged
- What is retained by the provider
- Provider protocol and classification (scope, control, data boundary)

---

## 2. Provider Protocol

All k9b LLM integrations use the `openai-compatible` provider protocol (API/client compatibility shape).

### 2.1 Provider Classification

| Provider Instance ID | Provider Protocol | Endpoint Scope | Operator Control | Data Boundary |
|---------------------|------------------|----------------|-----------------|---------------|
| `primary-llm` | `openai-compatible` | `loopback` | `self_managed` | `inside_operator_boundary` |
| `operator-configured` | `openai-compatible` | `derived_or_unknown` | `operator_declared_or_unknown` | `derived_or_unknown` |

### 2.2 Endpoint Scope Values

| Scope | Definition | Examples |
|-------|------------|----------|
| `loopback` | Localhost only; no network transmission | `127.0.0.1:8080`, `localhost:8080` |
| `same_cluster` | Same Kubernetes cluster | `llm-service.namespace.svc.cluster.local` |
| `private_network` | Private network; org-controlled | `10.0.0.5:8080`, VPN endpoints |
| `public_network` | Internet; outside org control | `api.openai.com`, `api.anthropic.com` |
| `unknown` | Cannot determine scope | Dynamic configuration |
| `derived_or_unknown` | Derived from LLM_BASE_URL or unknown | Dynamic |

### 2.3 Operator Control Values

| Control | Definition | Implications |
|---------|------------|--------------|
| `self_managed` | Operator controls the endpoint | Full visibility into behavior, retention, logging |
| `third_party` | Third party controls the endpoint | Assume retention, limited visibility |
| `unknown` | Cannot determine control | Treat as third_party by default |
| `operator_declared_or_unknown` | Declared by operator or unknown | Verify configuration |

### 2.4 Data Boundary Values

| Boundary | Definition |
|----------|------------|
| `inside_operator_boundary` | Data stays within operator control |
| `outside_operator_boundary` | Data may leave operator control |
| `derived_or_unknown` | Derived from endpoint_scope and operator_control |

### 2.5 Provider Selection

Provider selection is configured via:
- `LLM_PROVIDER` environment variable (default: loopback, `primary-llm`)
- `LLM_MODEL` environment variable (model ID)
- `LLM_BASE_URL` environment variable (operator-configured endpoint URL)

---

## 3. Data Flow Boundary

### 3.1 Outbound Data (k9b → LLM Provider)

The following data is sent to the LLM provider:

| Data Category | Description | Sanitization Applied |
|---------------|-------------|---------------------|
| Prompt text | System instruction + context + evidence | Yes: `sanitize_prompt()` |
| Cluster metadata | Names, UIDs, versions | Yes: partial anonymization |
| Evidence artifacts | Snapshots, drilldowns, assessments | Yes: `sanitize_prompt()` |
| User context | Run IDs, operator input | Yes: basic sanitization |
| Tool schemas | Available operations | No (controlled by k9b) |

### 3.2 Inbound Data (LLM Provider → k9b)

The following data is received from the LLM provider:

| Data Category | Processing |
|---------------|------------|
| Response text | Schema validation, then parsed |
| Structured JSON | Pydantic schema validation, rejection on failure |
| Recommendations | Advisory only; operator review required |

### 3.3 NOT Sent to LLM Provider

The following data is explicitly excluded:

| Data Category | Reason |
|---------------|--------|
| Kubernetes credentials | Environment variable only; never in prompts |
| Kubeconfig contents | Loaded by kubectl subprocess; not in prompts |
| Service account tokens | Environment variable; never in prompts |
| Bearer tokens | Redacted by `sanitize_prompt()` |
| API keys | Redacted by `sanitize_prompt()` |
| Private keys | Never included |
| Passwords | Never included |

---

## 4. Credential Handling

### 4.1 Credential Modes

| Mode | Description | Providers |
|------|-------------|-----------|
| `none` | No credentials required | Loopback inference (self_managed) |
| `bearer_token` | API key in Authorization header | Third-party APIs |
| `unknown` | Cannot determine | Verify configuration |

### 4.2 Credential Sources

| Provider Instance | Credential Mode | Source | Prompt Inclusion |
|-------------------|----------------|--------|------------------|
| primary-llm (loopback) | `none` | N/A | Never |
| operator-configured | `unknown` (verify config) | `derived_from_configuration` | Never |

### 4.3 Credential Isolation

- API keys are used only for HTTP authentication headers
- No credentials appear in prompt construction
- `sanitize_prompt()` scans for credential patterns before transmission

---

## 5. Masking and Redaction

### 5.1 Patterns Redacted from Prompts

The `sanitize_prompt()` function redacts the following patterns:

| Pattern Type | Examples |
|--------------|----------|
| Bearer tokens | `Bearer eyJ...`, `Authorization: Bearer ...` |
| API keys | `sk-...`, `api_key=...`, `api-key: ...` |
| Basic auth | `username:password@`, `Authorization: Basic ...` |
| Private keys | `-----BEGIN PRIVATE KEY-----` |
| Secret manifests | YAML with `kind: Secret` |
| AWS credentials | `AKIA...`, `aws_access_key` |

### 5.2 Infrastructure Identifiers Masked

| Identifier Type | Masking Status |
|----------------|----------------|
| Cluster names | Partial (primary metadata anonymized) |
| Namespace names | Partial (primary metadata anonymized) |
| Pod names | Partial (primary metadata anonymized) |
| Node names | Not systematically masked |
| Internal hostnames | Not systematically masked |
| Private IPs | Not systematically masked |

**Note**: Infrastructure identifier masking is partially implemented (GAP-P2). See `llm-anonymization-design.md` for the anonymization roadmap.

---

## 6. Logging and Retention

### 6.1 k9b-Side Logging

| Log Type | Content | Sanitization |
|----------|---------|--------------|
| Prompt logs | Sanitized prompt text | Yes (secrets redacted) |
| Response logs | LLM response text | Yes (secrets redacted) |
| Security events | Prompt injection blocks, secret findings | Yes (full sanitization) |
| Provider errors | Error messages | Yes (no secrets) |

### 6.2 Provider-Side Retention by Data Boundary

| Data Boundary | Retention Assumption |
|---------------|---------------------|
| `inside_operator_boundary` | `none_claimed` - no external storage |
| `outside_operator_boundary` | `provider_dependent` - assume inputs/outputs may be retained |
| `derived_or_unknown` | `unknown` - verify configuration |

---

## 7. Common Classification Examples

The following are **example classifications** for common deployment patterns:

| Scenario | provider_protocol | endpoint_scope | operator_control | data_boundary |
|----------|-----------------|---------------|------------------|---------------|
| Local inference (default) | openai-compatible | loopback | self_managed | inside_operator_boundary |
| Private cluster service | openai-compatible | same_cluster | self_managed | inside_operator_boundary |
| VPN inference server | openai-compatible | private_network | self_managed | inside_operator_boundary |
| Third-party API (e.g., OpenAI) | openai-compatible | public_network | third_party | outside_operator_boundary |

---

## 8. Unimplemented Assumptions

The following are current assumptions that are not yet fully implemented:

| Assumption | Current State | Tracking |
|------------|---------------|----------|
| Namespace/cluster anonymization | Partial only | GAP-P2 open |
| Structured injection detection | Basic patterns only | GAP-P3 open |
| Provider-specific data handling | Not differentiated | Deferred |
| Audit trail for provider calls | Basic logging only | Deferred |

---

## 9. Related Documents

| Document | Relationship |
|----------|--------------|
| `threat-model.md` | Parent threat model |
| `llm-prompt-security-audit.md` | Deep-dive on prompt paths |
| `llm-trust-levels.md` | Trust level classification |
| `ai-bom-provider-inventory.md` | AI-BOM provider inventory (detailed schema) |
| `llm-requirements-na-rag-mcp-self-hosted.md` | N/A requirements for future integrations |

---

**Document End**

# k9b AI-BOM Provider Inventory

**Document**: AI-BOM Provider Inventory  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-06-25  
**Status**: Current

---

## 1. Purpose

This document maintains the AI/Provider inventory for k9b, including:
- Provider protocol (API compatibility)
- Provider instance identifier
- Endpoint scope (where the endpoint is reachable from k9b)
- Operator control (who controls the endpoint)
- Credential mode and source
- Retention assumption
- Data boundary (security/privacy classification)

---

## 2. AI-BOM Schema

Each provider entry must include:

| Field | Description | Required |
|-------|-------------|----------|
| provider_protocol | API/client compatibility shape | Yes |
| provider_instance_id | k9b-local config identity | Yes |
| endpoint_scope | Where endpoint is reachable from k9b | Yes |
| operator_control | Who controls the endpoint | Yes |
| credential_mode | How auth is done | Yes |
| credential_source | Where credentials come from | Yes |
| retention_assumption | What to assume about prompt/response retention | Yes |
| data_boundary | Security/privacy boundary | Yes |

---

## 3. Provider Inventory

### 3.1 openai-compatible (Loopback)

Local inference via llama.cpp or similar compatible server.

| Field | Value |
|-------|-------|
| Provider Protocol | `openai-compatible` |
| Provider Instance ID | `primary-llm` |
| Endpoint Scope | `loopback` (127.0.0.1 or localhost) |
| Operator Control | `self_managed` |
| Credential Mode | `none` |
| Credential Source | N/A |
| Retention Assumption | `none_claimed` - no external storage |
| Data Boundary | `inside_operator_boundary` |
| Version Constraint | OpenAI API-compatible endpoints |

### 3.2 operator-configured (Dynamic)

Operator-configured inference endpoint. This is a placeholder for the actual deployment-specific configuration.

| Field | Value |
|-------|-------|
| Provider Protocol | `openai-compatible` |
| Provider Instance ID | `operator-configured` |
| Endpoint Scope | `derived_from_LLM_BASE_URL_or_unknown` |
| Operator Control | `operator_declared_or_unknown` |
| Credential Mode | `none\|bearer_token\|unknown` |
| Credential Source | `derived_from_configuration` |
| Retention Assumption | `derived_from_operator_control` |
| Data Boundary | `derived_from_endpoint_scope_and_operator_control_or_unknown` |
| Version Constraint | OpenAI API-compatible endpoints |

### 3.3 Example: openai-compatible public-network provider

Example classification for external inference via third-party API. This is a **common classification example**, not a required configuration.

| Field | Value |
|-------|-------|
| Provider Protocol | `openai-compatible` |
| Provider Instance ID | Example: `operator-configured` |
| Endpoint Scope | Example: `public_network` |
| Operator Control | Example: `third_party` |
| Credential Mode | Example: `bearer_token` |
| Credential Source | Example: `OPENAI_API_KEY` environment variable |
| Retention Assumption | Example: `provider_dependent` |
| Data Boundary | Example: `outside_operator_boundary` |

---

## 4. Endpoint Scope Classification

| Scope | Definition | Examples |
|-------|------------|----------|
| `loopback` | Localhost only; no network | `127.0.0.1:8080`, `localhost:8080` |
| `same_cluster` | Same Kubernetes cluster | `llm-service.namespace.svc.cluster.local` |
| `private_network` | Private network; org-controlled | `10.0.0.5:8080`, VPN endpoints |
| `public_network` | Internet; outside org control | `api.openai.com`, `api.anthropic.com` |
| `unknown` | Cannot determine scope | Dynamic configuration |

---

## 5. Operator Control Classification

| Control | Definition | Implications |
|---------|------------|--------------|
| `self_managed` | Operator controls the endpoint | Full visibility into behavior, retention, logging |
| `third_party` | Third party controls the endpoint | Assume retention, limited visibility |
| `unknown` | Cannot determine control | Treat as third_party by default |

---

## 6. Credential Management

### 6.1 Credential Modes

| Mode | Description | Providers |
|------|-------------|-----------|
| `none` | No credentials required | Loopback inference |
| `bearer_token` | API key in Authorization header | Third-party APIs |
| `unknown` | Cannot determine | Verify configuration |

### 6.2 Credential Sources

| Provider Instance | Credential Type | Source | Prompt Inclusion |
|-------------------|-----------------|--------|------------------|
| primary-llm (loopback) | None | N/A | Never |
| operator-configured | API Key | `OPENAI_API_KEY` env var | Never (HTTP auth only) |

### 6.3 Credential Isolation

- API keys are used only for HTTP `Authorization` header
- No credentials appear in LLM prompts
- No credentials logged in sanitized logs

---

## 7. Data Boundaries

### 7.1 Boundary Classification

| Boundary | Definition | Providers |
|----------|------------|-----------|
| `inside_operator_boundary` | Data stays within operator control | loopback, same_cluster, private_network (self_managed) |
| `outside_operator_boundary` | Data may leave operator control | public_network, unknown, third_party |

### 7.2 Data Classification by Boundary

| Data Type | Inside Boundary | Outside Boundary |
|-----------|-----------------|-----------------|
| Cluster metadata | ✅ Included | ⚠️ Anonymized preferred |
| Evidence artifacts | ✅ Included | ⚠️ Anonymized preferred |
| Credentials | ❌ Never | ❌ Never |
| Full secrets | ❌ Never | ❌ Never |

---

## 8. Retention and Privacy

### 8.1 Loopback Inference (self_managed)

- **No external retention**: Local process terminates after use
- **No logging by provider**: Local inference does not log prompts/responses
- **Disk persistence**: None by k9b design

### 8.2 Example: Third-Party APIs (operator_control=third_party)

- **Assumed retention**: External providers may retain inputs/outputs
- **Privacy policy**: Operator must review provider privacy policy
- **Data minimization**: k9b sanitizes prompts before transmission

---

## 9. Quota and Rate Limiting

### 9.1 Loopback Quotas

| Quota Type | Limit | Enforcement |
|------------|-------|-------------|
| Token budget | Configurable via prompt truncation | k9b enforces |
| Concurrent requests | Single local process | N/A |
| Rate limiting | None (local) | N/A |

### 9.2 Example: Third-Party API Quotas

| Quota Type | Limit | Enforcement |
|------------|-------|-------------|
| Token budget | Configurable via prompt truncation | k9b enforces |
| Concurrent requests | Configurable max connections | k9b enforces |
| Rate limiting | Provider-specific | Exponential backoff on 429 |
| Retry limits | Configurable max retries | k9b enforces |

---

## 10. Future Provider Additions

### 10.1 Adding New Providers

When adding a new provider:

1. Determine the provider protocol (API compatibility)
2. Classify endpoint_scope based on network location
3. Determine operator_control (self_managed vs third_party)
4. Document credential requirements
5. Classify retention_assumption and data_boundary
6. Update `LLM_PROVIDER` documentation
7. Add credential handling in `llm/` adapters
8. Add tests for new provider
9. Update threat model if data boundary changes

### 10.2 Required Fields for New Providers

| Field | Requirement |
|-------|-------------|
| provider_protocol | API/client compatibility |
| provider_instance_id | Unique k9b identity |
| endpoint_scope | Network location classification |
| operator_control | Ownership/control classification |
| credential_mode | Authentication method |
| credential_source | Where credentials come from |
| retention_assumption | What provider may retain |
| data_boundary | Security/privacy boundary |

---

## 11. Related Documents

| Document | Relationship |
|----------|--------------|
| `llm-provider-boundary.md` | Provider boundary details |
| `llm-trust-levels.md` | Trust level classification |
| `llm-requirements-na-rag-mcp-self-hosted.md` | Future integration requirements |
| `llm-security-requirements-register.md` | AI-BOM REQ-LLMSEC-027 |

---

**Document End**

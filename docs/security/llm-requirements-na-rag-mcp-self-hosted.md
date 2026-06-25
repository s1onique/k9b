# k9b LLM Requirements: Not Applicable (RAG, MCP, Self-Hosted)

**Document**: LLM Requirements N/A - RAG, MCP, Self-Hosted  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-06-25  
**Status**: Current

---

## 1. Purpose

This document explicitly documents which LLM-related requirements are **not applicable** to k9b's current implementation:
- RAG/Vector Memory
- MCP/Tool-Server Integrations
- Additional self-managed inference provider instances beyond the currently documented openai-compatible loopback instance

These requirements are documented as N/A with rationale and evidence, not simply ignored. Future introduction of these features requires meeting the documented requirements.

---

## 2. Not Applicable: RAG / Vector Memory

### 2.1 Current Status

| Item | Value |
|------|-------|
| Requirement | REQ-LLMSEC-028 |
| Status | **N/A - Not Currently Used** |
| Evidence | No RAG implementation in codebase |
| Future Trigger | If retrieval-augmented generation is added |

### 2.2 Rationale

k9b currently does not use RAG/vector memory because:
- Diagnosis context is provided via snapshot artifacts
- Evidence is passed directly to LLM prompts
- No long-term memory storage for retrieval

### 2.3 Future Requirements (If RAG Added)

If RAG/vector memory is introduced in the future, the following requirements must be met:

| Requirement | Description |
|-------------|-------------|
| **Permission Scoping** | Retrieval must be scoped by tenant/user/task permissions outside the model |
| **PII Scanning** | PII/secret scanning must run before long-term memory writes |
| **Sanitization** | Retrieved content must be sanitized before LLM prompts |
| **Retention Policy** | Vector embeddings must have documented retention and deletion policies |
| **Audit Trail** | Retrieval operations must be logged for security audit |

### 2.4 Implementation Triggers

The following code changes would indicate RAG is being introduced:
- Vector database integration (e.g., ChromaDB, Qdrant, Pinecone)
- Embedding model configuration
- Retrieval pipeline code
- Memory/vector store modules

---

## 3. Not Applicable: MCP / Tool-Server Integrations

### 3.1 Current Status

| Item | Value |
|------|-------|
| Requirement | REQ-LLMSEC-029 |
| Status | **N/A - Not Currently Used** |
| Evidence | No MCP implementation in codebase |
| Future Trigger | If MCP/tool-server integrations are added |

### 3.2 Rationale

k9b currently does not use MCP because:
- Tool access is hardcoded within k9b
- No external tool registry integration
- Diagnosis tools are operator-provided kubectl/helm commands

### 3.3 Future Requirements (If MCP Added)

If MCP/tool-server integrations are introduced in the future, the following requirements must be met:

| Requirement | Description |
|-------------|-------------|
| **Tool Allowlisting** | Only explicitly allowlisted tools may be called |
| **Scoped Credentials** | MCP credentials must be scoped to required permissions only |
| **Blocked Dangerous Operations** | DELETE, DROP, exec, and similar must be blocked unless explicitly approved |
| **Executable Policy Tests** | Policy compliance must be verified by automated tests |
| **Audit Logging** | All MCP tool calls must be logged with parameters and results |
| **Sandboxing** | MCP tool execution must be sandboxed from sensitive data |

### 3.4 Implementation Triggers

The following code changes would indicate MCP is being introduced:
- MCP client library imports
- Tool registry configuration
- Dynamic tool loading from external sources
- MCP protocol implementation

---

## 4. Not Applicable: Additional Self-Hosted Inference (Beyond Loopback)

### 4.1 Current Status

| Item | Value |
|------|-------|
| Requirement | REQ-LLMSEC-030 |
| Status | **N/A - Not Currently Used** |
| Evidence | Only openai-compatible loopback inference supported |
| Future Trigger | If additional self-hosted models are added |

### 4.2 Rationale

k9b currently uses only:
- **openai-compatible (loopback)**: Local inference via local HTTP server with `endpoint_scope=loopback` and `operator_control=self_managed`

The operator-configured inference endpoint is an **example deployment configuration** (e.g., `endpoint_scope=public_network`, `operator_control=third_party`) documented in the AI-BOM provider inventory. This N/A applies to **additional** self-managed inference instances beyond the documented loopback configuration.

### 4.3 Future Requirements (If Additional Self-Hosted Models Added)

If additional self-hosted inference is introduced in the future, the following requirements must be met:

| Requirement | Description |
|-------------|-------------|
| **Same Provider Boundary** | Must meet the same provider boundary and security requirements as external providers |
| **Credential Isolation** | No credentials in prompts; API keys for HTTP auth only |
| **Sanitization** | Same sanitization requirements apply |
| **Endpoint Scope Documentation** | Endpoint scope must be explicitly documented (loopback, same_cluster, private_network) |
| **Operator Control Classification** | Must classify as self_managed or third_party |
| **Retention Policy** | Retention assumptions must be documented |
| **Data Boundary** | Must classify data boundary (inside/outside_operator_boundary) |

### 4.4 Implementation Triggers

The following code changes would indicate additional self-hosted models:
- New provider adapters for different inference backends
- Custom model loading implementations
- GPU/memory management for local models
- Model registry or model store implementations

---

## 5. Verification Requirements

### 5.1 N/A Verification

For N/A requirements, verification consists of:
1. **Absence Check**: Verify no RAG/MCP/self-hosted code exists
2. **Documentation Check**: Verify this N/A document is current
3. **Change Detection**: If implementation code appears, N/A status must be reviewed

### 5.2 Future Activation

When a previously N/A feature is implemented:

1. Update this document to remove N/A status
2. Add implementation requirements to `llm_security_requirements.csv`
3. Add verification tests for the new feature
4. Update threat model with new attack surfaces
5. Update AI-BOM provider inventory with provider_protocol, endpoint_scope, operator_control, data_boundary

---

## 6. Related Documents

| Document | Relationship |
|----------|--------------|
| `ai-bom-provider-inventory.md` | Current provider inventory with detailed schema |
| `llm-provider-boundary.md` | Provider boundary details with classification |
| `llm_security_requirements.csv` | REQ-LLMSEC-028, 029, 030 |
| `threat-model.md` | Threat model updates for future features |

---

**Document End**

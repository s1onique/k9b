# k9b LLM Security Requirements Register

**Document**: LLM Security Requirements Register - Index  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-06-25  
**Status**: Current

---

## 1. Purpose

This document serves as the index for the k9b LLM Security Requirements Register. It provides an overview of all LLM security requirements, their status, and links to detailed documentation.

---

## 2. Requirements Register Location

The canonical requirements register is stored in:
```
docs/requirements/llm_security_requirements.csv
```

---

## 3. Requirements Summary

The LLM security requirements register currently contains **6 requirements**:

| Category | Description | Count |
|----------|-------------|-------|
| `llm_security` | LLM-specific security requirements | 6 |

---

## 4. Security Domains

| Domain | Description | Requirements |
|--------|-------------|---------------|
| `threat_model` | Threat model coverage | REQ-LLMSEC-001 |
| `governance` | Requirements governance and tracking | REQ-LLMSEC-002 |
| `ai_bom` | AI-BOM/provider inventory | REQ-LLMSEC-027 |
| `rag` | RAG/vector memory | REQ-LLMSEC-028 (planned) |
| `mcp` | MCP/tool-server integrations | REQ-LLMSEC-029 (planned) |
| `self_hosted` | Self-managed inference | REQ-LLMSEC-030 (planned) |

---

## 5. Assurance Levels

| Level | Description | Count |
|-------|-------------|-------|
| `MUST` | Mandatory requirement | 3 |
| `N/A` | Not applicable (documented as such) | 3 |

---

## 6. Status Overview

| Status | Count |
|--------|-------|
| `current` | 3 |
| `planned` | 3 |

---

## 7. Requirements Detail

| REQ ID | Title | Assurance Level | Status |
|--------|-------|----------------|--------|
| REQ-LLMSEC-001 | LLM Security Threat Model | MUST | current |
| REQ-LLMSEC-002 | Canonical REQ ID Format | MUST | current |
| REQ-LLMSEC-027 | AI-BOM Provider Inventory | MUST | current |
| REQ-LLMSEC-028 | RAG/Vector Memory Not Applicable | N/A | planned |
| REQ-LLMSEC-029 | MCP/Tool-Server Integrations Not Applicable | N/A | planned |
| REQ-LLMSEC-030 | Additional Self-Managed Inference Not Applicable | N/A | planned |

---

## 8. Reference Documentation

### 8.1 LLM Security Documents

| Document | Coverage |
|----------|----------|
| `docs/security/threat-model.md` | Overall security threat model |
| `docs/security/llm-provider-boundary.md` | Provider boundary details with provider_protocol, endpoint_scope, operator_control |
| `docs/security/llm-trust-levels.md` | Trust level classification |
| `docs/security/read-only-agent-boundary.md` | Agent boundary documentation |
| `docs/security/ai-bom-provider-inventory.md` | AI-BOM provider inventory |
| `docs/security/llm-requirements-na-rag-mcp-self-hosted.md` | N/A requirements for future integrations |
| `docs/security/llm-prompt-security-audit.md` | Deep-dive on prompt paths |

### 8.2 Verification Scripts

| Script | Purpose |
|--------|---------|
| `scripts/verify_llm_security_requirements.py` | LLM security requirements register verifier (includes dangling REQ prevention) |
| `scripts/verify_security_claim_traceability.py` | Security claim traceability verifier |

---

**Document End**

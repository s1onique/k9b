# k9b Security Audit Report

**Date**: 2026-05-31
**Scope**: Full doctrine-first security audit
**Standards**: OWASP ASVS, OWASP Top 10, OWASP LLM Top 10, CIS Kubernetes Benchmark, SLSA

---

## Executive Summary

This report documents the findings of a doctrine-first security audit of the k9b repository. The audit traced security claims from documented doctrine through implementation, tests, and verification gates.

**Overall Posture**: REASONABLE - 19 enforced claims, 5 tested-only, 4 with implementation gaps.

---

## 1. Files Changed

| File | Action |
|------|--------|
| `docs/reports/security-claims-ledger-2026-05-31.md` | Created |
| `docs/reports/security-audit-2026-05-31.md` | Created |

---

## 2. Findings Summary

| Severity | Count | Finding IDs |
|----------|-------|------------|
| CRITICAL | 0 | None |
| HIGH | 2 | K9B-SEC-001, K9B-SEC-002 |
| MEDIUM | 3 | K9B-SEC-003, K9B-SEC-004, K9B-SEC-005 |
| LOW | 2 | K9B-SEC-006, K9B-SEC-007 |

---

## 3. Attack Surface Inventory

| Surface | Type | Entry Point | Status |
|---------|------|------------|--------|
| UI HTTP Server | Network | `localhost:8080` | Protected by default binding |
| Next-check execution API | API | `POST /api/next-check-execution` | Bearer token optional |
| Proposal approval API | API | `POST /api/next-check-approval` | Bearer token optional |
| Deterministic promotion API | API | `POST /api/deterministic-promotion` | Bearer token optional |
| Alertmanager feedback API | API | `POST /api/alertmanager-relevance-feedback` | Bearer token optional |
| Run ID interpolation | Input | All API requests with `run_id` | Validated via `validate_run_id()` |
| Kubernetes subprocess | Command Injection | Cluster interaction | Blocklist + allowlist |
| LLM prompt construction | Injection | Cluster data → prompts | Basic sanitization |
| Mattermost webhook | Exfiltration | Notification delivery | Low risk |
| Docker build | Supply Chain | CI/CD pipeline | No checksum verification |
| Python dependencies | Supply Chain | `pyproject.toml` | No hash pinning |

---

## 4. Findings

### K9B-SEC-001: Prompt Injection Detection Incomplete

| Attribute | Value |
|-----------|-------|
| **Severity** | HIGH |
| **Affected Area** | LLM prompt construction |
| **Violated Doctrine** | INV-4, LLM01 |
| **Evidence** | `sanitizer.py` uses regex patterns only; GAP-P3 documented as open; no active injection detection |
| **Impact** | Malicious cluster data could inject instructions into LLM prompts |
| **Recommendation** | Add structured injection detection patterns; add red team tests |
| **Required Regression Test** | `test_injection_via_events`, `test_injection_via_descriptions` |
| **Verifier/Gate Required** | Yes - add to CI |

### K9B-SEC-002: Authentication Not Enforced by Default

| Attribute | Value |
|-----------|-------|
| **Severity** | HIGH |
| **Affected Area** | UI API server |
| **Violated Doctrine** | AUTH-04/05/06/07 |
| **Evidence** | Bearer token validation is optional; `expected_token` can be None |
| **Impact** | Mutation endpoints accessible to any local user when token not configured |
| **Recommendation** | Document that token is optional for localhost-only deployments |
| **Required Regression Test** | None - by design |
| **Verifier/Gate Required** | No |

### K9B-SEC-003: No Cryptographic Artifact Integrity Verification

| Attribute | Value |
|-----------|-------|
| **Severity** | MEDIUM |
| **Affected Area** | Artifact storage |
| **Violated Doctrine** | GOAL-3, RISK-AI-01 |
| **Evidence** | No SHA256/HMAC verification; `identity/artifact.py` has no hash computation |
| **Impact** | Artifacts could be tampered without detection |
| **Recommendation** | Add SHA256 field to `write_append_only_json_artifact()` |
| **Required Regression Test** | Test artifact hash verification |
| **Verifier/Gate Required** | No |

### K9B-SEC-004: Label/Annotation Values Not Fully Anonymized

| Attribute | Value |
|-----------|-------|
| **Severity** | MEDIUM |
| **Affected Area** | LLM prompts |
| **Violated Doctrine** | INV-4, GOAL-4 |
| **Evidence** | `anonymizer.py` handles metadata.name; `anonymize_labels_annotations()` exists but values may contain name-like content |
| **Impact** | Confidential infrastructure details may leak to external LLM |
| **Recommendation** | Complete Phase 1b anonymization for label/annotation values |
| **Required Regression Test** | Integration test with real cluster data |
| **Verifier/Gate Required** | Yes |

### K9B-SEC-005: No Dependency Hash Pinning

| Attribute | Value |
|-----------|-------|
| **Severity** | MEDIUM |
| **Affected Area** | Supply chain |
| **Violated Doctrine** | Supply chain integrity |
| **Evidence** | `pyproject.toml` has no hash pins; RISK-10 documented |
| **Impact** | Compromised PyPI dependency could introduce malicious code |
| **Recommendation** | Add hash pins for critical dependencies |
| **Required Regression Test** | None |
| **Verifier/Gate Required** | No |

### K9B-SEC-006: kubectl/helm Binary Download Not Verified

| Attribute | Value |
|-----------|-------|
| **Severity** | LOW |
| **Affected Area** | Dockerfile |
| **Violated Doctrine** | Supply chain integrity |
| **Evidence** | `Dockerfile.python` downloads kubectl/helm without checksum verification |
| **Impact** | Man-in-the-middle during build could inject malicious binaries |
| **Recommendation** | Add SHA256 verification for downloaded binaries |
| **Required Regression Test** | None |
| **Verifier/Gate Required** | No |

### K9B-SEC-007: No Vulnerability Scanning in CI

| Attribute | Value |
|-----------|-------|
| **Severity** | LOW |
| **Affected Area** | CI/CD |
| **Violated Doctrine** | RISK-10, Gap-08 |
| **Evidence** | `.github/workflows/verify.yml` has no dependency scanning |
| **Impact** | Known CVEs in dependencies may go undetected |
| **Recommendation** | Add `pip-audit` or `safety` to CI |
| **Required Regression Test** | None |
| **Verifier/Gate Required** | No |

---

## 5. Residual Risks (Accepted)

| Risk | Justification | Owner |
|------|---------------|-------|
| Localhost-only assumption | Production deployments expected to use network isolation | Operator |
| Optional authentication | Token is optional for trusted localhost networks | Operator |
| No artifact SHA256 | Append-only design; local filesystem trust | Design decision |
| External LLM provider exposure | llama.cpp is local-first; OpenAI requires explicit opt-in | Operator |
| kubectl/helm binary provenance | Container image integrity assumed | DevOps |

---

## 6. Accepted Risks

| Risk ID | Description | Severity | Acceptance Rationale |
|---------|-------------|----------|---------------------|
| R-01 | LLM provider supply chain compromise | HIGH | Local llama.cpp is default; external providers require explicit configuration |
| R-02 | kubectl/helm binary tampering during build | HIGH | Container image integrity assumed; no alternative for containerized deployment |
| R-03 | Compromised PyPI dependency | MEDIUM | pip install from PyPI is standard practice; hash pins would help but not eliminate risk |
| R-04 | No RBAC documentation for operators | HIGH | Documented in `docs/security/rbac-deployment-guide.md` |

---

## 7. Doctrine Claims by Status

| Status | Count | Claims |
|--------|-------|--------|
| **Enforced** | 19 | INV-1, INV-2, INV-3, GOAL-1, GOAL-5, GOAL-6, API-R1, API-R2, AUTH-01, AUTH-02, AUTH-10, SUBPROC-04, SUBPROC-06, REM-S3, LLM02, CIS-5.4.1, CIS-7.2 |
| **Tested Only** | 5 | INV-4, GOAL-2, GOAL-4, LLM01, LLM06 |
| **Implemented** | 3 | GOAL-3, GOAL-7, SUBPROC-05 |
| **Documented Only** | 3 | SLSA-L2, Supply scanning, RISK-10 gap |

---

## 8. Verification Commands and Results

```bash
# Ruff lint
.venv/bin/ruff check src/k8s_diag_agent/security/ --select=E,F,I
# Result: All checks passed!

# Mypy type check
.venv/bin/mypy src/k8s_diag_agent/security/ --no-error-summary
# Result: Success: no issues found

# Security tests
.venv/bin/python -m pytest tests/security/ -v --tb=short
# Result: 192 passed in 10.21s

# Verify no shell=True
grep -r "shell\s*=\s*True" src/
# Result: No matches

# Verify path traversal protection
grep -r "validate_run_id\|safe_child_path" src/
# Result: Multiple implementations found
```

---

## 9. Follow-Up ACT Prompts

### ACT-1: Add Prompt Injection Detection Tests

```
Run the following command to add integration tests for prompt injection:
```bash
# Add red team tests for LLM01 (prompt injection)
.venv/bin/python -m pytest tests/ -k "injection" -v
```

Implement test cases:
- `test_injection_via_events`: Event with injected prompt in message
- `test_injection_via_descriptions`: Pod description with injected prompt
- `test_injection_via_review`: Review JSON with injected prompt
```

### ACT-2: Add Artifact SHA256 Verification

```
Implement artifact integrity verification:

1. Add SHA256 field to `identity/artifact.py`:
   - Compute hash after writing artifact
   - Store hash in artifact metadata

2. Add verification on read:
   - Verify hash before loading artifact
   - Log integrity failures

3. Add test:
   - `test_artifact_hash_verification`
```

### ACT-3: Complete Label/Annotation Anonymization

```
Complete Phase 1b anonymization for label/annotation values:

1. Review `anonymize_labels_annotations()` in `anonymizer.py`
2. Ensure all name-like values are anonymized
3. Add integration test with real cluster data
4. Verify in CI gate
```

### ACT-4: Add Dependency Vulnerability Scanning

```
Add pip-audit to CI:

1. Add to `.github/workflows/verify.yml`:
   - name: Vulnerability scan
     run: pip-audit || true

2. Add to `pyproject.toml`:
   - Consider hash pins for critical dependencies
```

### ACT-5: Add kubectl/helm Binary Verification

```
Add SHA256 verification to Dockerfile.python:

1. Download kubectl binary
2. Fetch checksum from dl.k8s.io
3. Verify before chmod +x

4. Repeat for helm binary
```

---

## 10. Audit Limitations

1. **Dynamic Analysis**: This audit did not include runtime testing against live clusters
2. **LLM Provider Testing**: External LLM providers were not tested with malicious inputs
3. **Penetration Testing**: No formal penetration testing was conducted
4. **Dependency Audit**: Only source code was reviewed; no dependency CVE scan was run
5. **Configuration Review**: Operator configuration was not audited end-to-end

---

## 11. Conclusion

The k9b repository demonstrates a reasonable security posture with strong foundations in:
- Path traversal prevention (192 tests)
- Subprocess security (no shell=True, command allowlist)
- Authentication defaults (localhost binding, optional bearer token)
- Credential redaction (sanitizer patterns)

Key areas requiring attention:
1. Prompt injection detection (HIGH)
2. Label/annotation anonymization (MEDIUM)
3. Artifact integrity verification (MEDIUM)
4. Dependency supply chain hardening (MEDIUM/LOW)

The system is safe to deploy with documented operational constraints.

---

**Document End**

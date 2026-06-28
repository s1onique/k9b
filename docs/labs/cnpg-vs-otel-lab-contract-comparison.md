# CNPG vs OTel Lab Contract Comparison

**Status**: Initial comparison (2026-06-28)
**Purpose**: Map shared vs. lab-specific phases and identify parity gaps before extraction

## Current Verdict

| Lab | Verdict |
|-----|---------|
| **CNPG live incident lab** | Current reference proof for live single-pass incident diagnosis feedback-loop closure |
| **OTel demo lab** | Telemetry-grounded evidence/diagnosis proof (not yet at parity with CNPG) |

**Current model**: Deterministic detection + LLM-assisted diagnosis (not fully autonomous).
Do not claim LLM-assisted detection unless the LLM actually participates in detection/classification.

**Important**: The recent OTel screenshot failure with `Unable to connect to the server: dial tcp ... i/o timeout` is a **shared cluster connectivity/preflight failure**, not an OTel lab semantic failure. Kubernetes documents this as a kubectl connectivity troubleshooting case.

## Lab Claims

| Lab | Primary Claim | What It Proves | What It Does Not Prove |
|-----|--------------|----------------|------------------------|
| CNPG live incident lab | k9b can detect a live Kubernetes readiness incident, promote it, run one-pass LLM-assisted diagnosis, persist the result, and emit upload-safe artifacts | Full provider smoke pipeline with backend health, scheduler health, incident discovery, one-pass diagnosis call, persisted diagnosis contract verification, and artifact sanitization | OTel/telemetry-grounded diagnosis, non-Kubernetes scenarios |
| OTel demo lab | k9b can observe a live service-behavior failure in the OTel demo, correlate it with traffic/telemetry evidence, and use that evidence in the incident diagnosis path | OTel demo stack deployment, traffic generation, feature-flag injection, telemetry oracle verification, deterministic/oracle diagnosis | Real k9b/provider-backed diagnosis, persisted diagnosis contract, provider smoke |

**Note**: A deterministic/oracle diagnosis artifact is useful for scenario verification, but it is **not provider-smoke parity** unless the workflow calls the live k9b one-pass diagnosis API and verifies provider configured/invoked state.

## Phase-by-Phase Comparison

| Phase | CNPG Lab | OTel Lab | Shared? | Extraction Recommendation |
|-------|----------|----------|---------|--------------------------|
| kubeconfig bootstrap | Protected env secret decode | Direct kubeconfig decode | Partial | Extract shared bootstrap helper after parity achieved |
| cluster connectivity | kubectl cluster-info, get nodes | kubectl cluster-info (fails early on timeout) | Yes | Extract shared connectivity check |
| namespace lifecycle | Create lab namespace with labels | Namespace creation in lifecycle | Yes | Extract shared namespace helper |
| image/render preflight | Full render preflight + registry check | Not applicable (no Helm deploy in lab) | No | N/A - OTel uses existing cluster |
| Helm deploy | Full Helm upgrade with provider config | Not applicable | No | N/A |
| rollout monitor | Proactive rollout monitor with 90s deadline | Not applicable | No | N/A |
| backend health gate | `check_backend_health_gate.py` with 30 retries | Not implemented | No | Keep separate until OTel parity |
| scheduler health gate | `check_scheduler_health_gate.py` | Not implemented | No | Keep separate until OTel parity |
| CNPG operator preflight | CRD + operator pod verification | N/A | No | Keep CNPG-specific |
| CNPG cluster creation | Cluster CR with 1 instance | N/A | No | Keep CNPG-specific |
| OTel demo stack readiness | N/A | Phase 1 deploy + Phase 1b baseline | No | Keep OTel-specific |
| traffic generation | N/A | Phase 2 traffic generation | No | Keep OTel-specific |
| failure injection | Readiness probe fixture (deterministic) | Feature-flag + cache failure injection | No | Keep separate - different semantics |
| incident discovery | Real k9b API integration (`check_incident_discovery_gate.py`) | Placeholder - k9b API integration not implemented | No | Keep separate - OTel needs real integration first |
| one-pass diagnosis | `POST /api/incidents/{id}/one-pass-diagnosis` with provider smoke | Fake/oracle diagnosis artifact only | No | Keep separate - OTel needs real provider call |
| persisted diagnosis | `check_persisted_diagnosis_contract.py` with verification | Not implemented | No | Keep separate until OTel parity |
| artifact sanitization | `verify_diagnosis_provider_artifacts.py` with fail-closed behavior | Not implemented | No | Keep separate until OTel parity |

## Provider and Persistence Parity

| Check | CNPG Lab | OTel Lab | Status |
|-------|----------|----------|--------|
| Calls `POST /api/incidents/{id}/one-pass-diagnosis` | ✅ Yes (Phase 3) | ❌ No - uses fake/oracle diagnosis | **Gap** |
| Verifies HTTP 200 response | ✅ Yes | ❌ No | **Gap** |
| Verifies `provider_configured=true` | ✅ Yes | ❌ No | **Gap** |
| Verifies `provider_invocation_attempted=true` | ✅ Yes | ❌ No | **Gap** |
| Fetches incident afterward | ✅ Yes (Phase 4) | ❌ No | **Gap** |
| Verifies `automatic_diagnosis_review` state | ✅ Yes | ❌ No | **Gap** |
| Sanitizes raw provider artifacts before upload | ✅ Yes | ❌ No | **Gap** |

**Conclusion**: OTel lab lacks all provider-smoke and persisted-diagnosis parity gates. The oracle/deterministic diagnosis in OTel is useful for scenario verification but is **not equivalent** to CNPG's live provider integration.

## Artifact Safety Parity

| Aspect | CNPG Lab | OTel Lab | Status |
|--------|----------|----------|--------|
| Raw temp directory use | ✅ Uses `RUNNER_TEMP` outside `lab-artifacts/` | ❌ Not implemented | **Gap** |
| Sanitized artifact output path | ✅ `lab-artifacts/live-sanitized/` | ❌ Not implemented | **Gap** |
| Fail-closed verifier behavior | ✅ `verify_diagnosis_provider_artifacts.py` | ❌ Not implemented | **Gap** |
| Secret/topology leakage checks | ✅ Via artifact verifier | ❌ Not implemented | **Gap** |
| Upload-safe artifact gate | ✅ `.safe-for-upload` marker | ❌ Not implemented | **Gap** |
| Bounded summaries | ✅ Via `check_persisted_diagnosis_contract.py` | ❌ Not implemented | **Gap** |

## Connectivity Failure Classification

**Desired common failure classes for cluster connectivity** (document-only in this ACT):

| Failure Class | Description |
|---------------|-------------|
| `cluster_api_timeout` | TCP connection timeout to API server (e.g., `dial tcp ... i/o timeout`) |
| `kubeconfig_missing` | Kubeconfig secret not found |
| `kubeconfig_invalid` | Kubeconfig file is invalid or malformed |
| `kubeconfig_decode_failed` | Base64 decode failed |
| `cluster_auth_failed` | Authentication check failed |
| `api_discovery_failed` | Server discovery/ping failed |
| `namespace_rbac_denied` | RBAC permissions insufficient for namespace operations |
| `unknown_cluster_connectivity_failure` | Uncategorized connectivity failure |

**Note**: The recent OTel screenshot failure (`Unable to connect to the server: dial tcp 192.168.50.11:6443: i/o timeout`) belongs to `cluster_api_timeout` / cluster_connectivity, not to OTel lab semantics.

Do not implement the full classifier in this ACT. The classifier belongs in the next parity/extraction ACT.

## Proposed Shared Extraction Boundary

### Safe to Extract Later (After OTel Parity)

- Protected kubeconfig bootstrap/decode helper
- Cluster connectivity check/classification
- Namespace lifecycle helper
- Helm render/install evidence capture
- k9b rollout monitor wrapper
- Backend health gate (`check_backend_health_gate.py`)
- Scheduler health gate (`check_scheduler_health_gate.py`)
- One-pass diagnosis provider smoke gate
- Persisted diagnosis contract verification (`check_persisted_diagnosis_contract.py`)
- Artifact sanitizer/verifier wrapper
- Bounded summary rendering helpers

### Keep Lab-Local

- CNPG operator preflight (CRD + pod verification)
- CNPG Cluster CR lifecycle
- CNPG/pod readiness fixture (deterministic readiness probe failure)
- OTel demo install/readiness (Phase 1, 1b)
- OTel traffic generation (Phase 2)
- OTel feature-flag/cache/recommendation-service injection
- OTel trace/log/metric evidence oracle
- Scenario-specific diagnosis quality assertions
- Reusable workflow/composite action work (deferred until comparison complete)

## Recommended Next ACT

Because OTel lacks provider-smoke and persisted-diagnosis parity, the next ACT should be **parity before extraction**:

```
ACT: Bring OTel Lab to Provider/Persisted-Diagnosis Parity with CNPG Before Extraction
```

**Acceptance criteria**:
1. OTel lab integrates real k9b incident discovery (replacing placeholder)
2. OTel lab adds backend health gate before incident discovery
3. OTel lab adds scheduler health gate before incident discovery
4. OTel lab calls `POST /api/incidents/{id}/one-pass-diagnosis` with provider smoke
5. OTel lab verifies persisted diagnosis contract (provider_configured, provider_invocation_attempted, automatic_diagnosis_review)
6. OTel lab sanitizes provider artifacts before upload
7. CNPG lab behavior unchanged
8. Verification gate passes

**Rationale**: The CNPG lab has already proven the full provider/persistence path. Extracting shared harness code before OTel achieves parity would result in a shared harness that only one lab uses. Bring OTel to parity first, then extract.

## Files Changed by This Comparison ACT

| File | Purpose |
|------|---------|
| `docs/labs/cnpg-vs-otel-lab-contract-comparison.md` | This comparison document |
| `tests/test_lab_contract_comparison_doc.py` | Contract inventory test |
| `docs/docs_inventory.csv` | Labs entries added |

# LLM Anonymization Design (REM-P2)

**Document**: Cluster Metadata Anonymization for LLM Prompts  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.1  
**Date**: 2026-05-06  
**Author**: k9b Design  
**Status**: Phase 2 Implemented  
**Parent**: GAP-P2 from `llm-prompt-security-audit.md`, REM-P2 backlog

---

## Executive Summary

This document designs the anonymization layer for cluster metadata (names, IDs, namespaces, workloads) before LLM prompts are sent to external providers.

**Context**:
- GAP-P1 is mitigated: all prompt paths call `sanitize_prompt()` (credential redaction)
- GAP-P2 remains open: no systematic cluster/namespace/workload name anonymization
- Current sanitizer redacts credentials but does not anonymize infrastructure metadata

**Goal**: Define what infrastructure metadata must be anonymized, how aliases are generated, which implementation approach to use, and how to test it.

---

## 1. Metadata Inventory

### 1.1 Metadata Types Entering LLM Prompts

| Metadata Type | Example | Source | Prompt Path | Current Handling |
|---------------|---------|--------|-------------|------------------|
| **Cluster ID/Name** | `prod-us-east-1`, `admin@cluster1` | `ClusterSnapshot.metadata` | All 3 paths | Raw via `sanitize_prompt()` |
| **Namespace Names** | `default`, `production`, `kube-system` | Cluster API | All 3 paths | Raw |
| **Node Names** | `node-001`, `k8s-worker-3` | Cluster API | Path 1 | Raw |
| **Pod Names** | `nginx-deployment-abc123` | Cluster API | Paths 1, 2 | Raw |
| **Deployment Names** | `myapp-v1`, `api-gateway` | Cluster API | Paths 1, 2 | Raw |
| **StatefulSet Names** | `postgres-primary` | Cluster API | Paths 1, 2 | Raw |
| **DaemonSet Names** | `fluentd-ds` | Cluster API | Paths 1, 2 | Raw |
| **Service Names** | `nginx-svc` | Cluster API | Paths 1, 2 | Raw |
| **Ingress Hostnames** | `app.example.com` | Cluster API | Path 1 | Raw |
| **Helm Release Names** | `ingress-nginx`, `cert-manager` | Cluster API | Path 1 | Raw |
| **CRD Names** | `prometheuses.monitoring.coreos.com` | Cluster API | Path 1 | Raw |
| **Labels** | `app.kubernetes.io/name` | Cluster API | All 3 paths | Raw |
| **Annotations** | `prometheus.io/scrape` | Cluster API | All 3 paths | Raw |
| **Run ID** | `run-2024-01-15-abc123` | Artifact | All 3 paths | Raw via `sanitize_prompt()` |
| **Event Messages** | Warning event content | Cluster API | Paths 2, 3 | Raw via `sanitize_prompt()` |

### 1.2 Severity Classification

| Classification | Description | Handling Required |
|---------------|-------------|-------------------|
| **CRITICAL** | Credentials, tokens, secrets | Must be redacted (existing) |
| **HIGH** | Cluster topology, business context | Must be anonymized before external LLM |
| **MEDIUM** | Cluster identifiers, workload names | Anonymization acceptable |
| **LOW** | Counts, timestamps, status | Standard handling |

---

## 2. Anonymization Policy

### 2.1 Must Always Be Anonymized (External LLM Providers)

These fields MUST be anonymized before sending to any external LLM provider (OpenAI-compatible, etc.):

| Field Category | Examples | Rationale |
|----------------|----------|-----------|
| Cluster identifiers | `cluster_id`, cluster context names | Reveals infrastructure topology |
| Namespace names | `default`, `production`, `kube-system` | Reveals organizational structure |
| Node names | `node-001`, `k8s-worker-3` | Reveals naming conventions |
| Workload names | Deployment, StatefulSet, DaemonSet names | Reveals application inventory |
| Pod names | `nginx-deployment-abc123` | Reveals deployment patterns |
| Service names | `nginx-svc`, `api-gateway` | Reveals service inventory |
| Helm release names | `ingress-nginx`, `cert-manager` | Reveals installed tooling |
| CRD custom names | `prometheuses.monitoring.coreos.com` | Reveals custom resources |
| Ingress hostnames | `app.example.com` | Reveals external endpoints |
| Labels/annotations containing names | `app.kubernetes.io/name: myapp` | May reveal business context |

### 2.2 May Remain Visible (Local llama.cpp Only)

When the LLM provider is configured as **local llama.cpp** (`LLAMACPP_BASE_URL` is localhost/127.0.0.1), the following MAY remain visible:

| Field | Rationale | Risk Justification |
|-------|-----------|-------------------|
| Cluster identifiers | Local processing only | Data never leaves operator workstation |
| Namespace names | Local processing only | Data never leaves operator workstation |
| All other infrastructure names | Local processing only | Data never leaves operator workstation |

**Rationale**: When using local llama.cpp, data remains on the operator's workstation and does not expose infrastructure to external parties.

### 2.3 Must Never Leave the Process (Even After Anonymization)

| Data | Rationale |
|------|-----------|
| Raw credential values | Already handled by `sanitize_prompt()`, must remain |
| Kubernetes API tokens | Must never appear in prompts |
| kubeconfig content | Already blocked by `sanitize_prompt()` |
| Secret manifest contents | Already blocked by `sanitize_prompt()` |
| Bearer/auth tokens | Already blocked by `sanitize_prompt()` |

### 2.4 Should Be Preserved for Diagnostic Usefulness

To maintain diagnostic value, preserve these in anonymized form:

| Data | Preservation Strategy |
|------|----------------------|
| Resource counts | Node count, pod count, namespace count remain as integers |
| Resource relationships | Keep `namespace/name` pattern but with anonymized values |
| Resource status | Phase, conditions, timestamps remain as-is |
| Schema structure | JSON/YAML structure intact, only names replaced |
| Kubernetes kinds | `kind: Deployment` preserved, only name anonymized |
| Severity levels | Warning, critical, info preserved |
| Timestamps | Collection timestamps remain as-is |

---

## 3. Stable Aliasing Rules

### 3.1 Deterministic Within a Single Run

The anonymizer MUST produce consistent aliases within one prompt run:

```
# Same real name maps to same alias within one run
"production" namespace → "namespace-a"
"default" namespace → "namespace-b"
```

**Implementation**: Use a mapping dict that persists for the duration of one prompt construction.

### 3.2 No Cross-Run Correlation (Unless Explicitly Enabled)

The anonymizer MUST NOT correlate across separate runs:

```
# Run 1
"production" → "namespace-a"

# Run 2 (separate invocation)
"production" → "namespace-a" OR "namespace-x" (different mapping)
```

**Rationale**: Prevents LLM providers from correlating cluster data across multiple prompts over time.

**Optional mode**: Cross-run correlation can be enabled via config for local debugging only (`LLM_ANONYMIZE_PERSIST=true`).

### 3.3 Readable Aliases Format

Use predictable, readable aliases that preserve kind context:

| Real Name | Alias Pattern | Example |
|-----------|---------------|---------|
| Cluster | `cluster-{letter}` | `cluster-a`, `cluster-b` |
| Namespace | `namespace-{letter}` | `namespace-a`, `namespace-b` |
| Node | `node-{letter}` | `node-a`, `node-b` |
| Workload (Deployment/StatefulSet/DaemonSet) | `{kind}-{letter}` | `deployment-a`, `statefulset-b` |
| Pod | `pod-{letter}` | `pod-a`, `pod-b` |
| Service | `service-{letter}` | `service-a`, `service-b` |
| Helm Release | `release-{letter}` | `release-a`, `release-b` |
| CRD | `crd-{letter}` | `crd-a`, `crd-b` |
| Ingress Hostname | `host-{letter}` | `host-a`, `host-b` |

**Rules**:
1. Single lowercase letter suffix (`a`, `b`, `c`, ... `z`, then `aa`, `ab`, ...)
2. Alias assigned in order of first appearance
3. Preserve Kubernetes `kind` field value (important for diagnostics)

### 3.4 Preserve Resource Type/Kind Where Useful

```
# Before anonymization
kind: Deployment
metadata:
  name: myapp-v1
  namespace: production

# After anonymization  
kind: Deployment
metadata:
  name: deployment-a
  namespace: namespace-a
```

---

## 4. Implementation Options

### 4.1 Option A: Pre-Prompt Recursive Sanitizer/Anonymizer

Add an anonymization layer that runs before `sanitize_prompt()`:

```
Input Data → Anonymizer → Anonymized Data → Prompt Builder → sanitize_prompt() → LLM Provider
```

**Pros**:
- Minimal changes to existing prompt builders
- Centralized anonymization logic
- Composable with existing `sanitize_prompt()`

**Cons**:
- Must handle all data structures (dicts, lists, strings)
- Must preserve structure while replacing values
- Performance cost for recursive traversal

**Implementation Sketch**:
```python
class Anonymizer:
    def __init__(self, provider_type: str):
        self._mappings: dict[str, dict[str, str] = {}
        self._provider_type = provider_type
        self._counter: dict[str, int] = {}
    
    def anonymize(self, data: Any) -> Any: ...
    def anonymize_string(self, value: str, kind: str) -> str: ...
    def _generate_alias(self, kind: str) -> str: ...
```

### 4.2 Option B: Prompt-Builder-Aware Field Anonymization

Add anonymization at each prompt builder function:

```
prompts.py: build_assessment_prompt()
  → anon.anonymize(snapshot)  # Pre-process snapshot
  → _metadata_summary()       # Uses anonymized values
  → build prompt
  → sanitize_prompt()
```

**Pros**:
- Explicit control over what's anonymized
- Easy to audit specific fields
- Fine-grained per-field logic

**Cons**:
- Requires changes in multiple places
- Risk of missing fields
- Harder to maintain consistency

### 4.3 Option C: Provider-Boundary Anonymization Wrapper

Wrap the LLM provider invocation with anonymization:

```
Prompt Builder → Prompt → ProviderWrapper → Anonymize Prompt → LLM Provider
```

**Pros**:
- Single interception point
- All prompts anonymized before leaving process
- Clear boundary

**Cons**:
- Operates on string level (less precise than structure-aware)
- May miss embedded names in structured data
- Risk of over/under anonymization

**Implementation Sketch**:
```python
def anonymize_prompt(prompt: str, provider_type: str) -> str:
    if is_local_provider(provider_type):
        return prompt  # No anonymization for local
    # Regex-based replacement of known patterns
    patterns = [
        (r'cluster["\s:=]+([a-zA-Z0-9_-]+)', r'cluster: cluster-\1'),  # rough
        ...
    ]
```

---

## 5. Recommendation

### 5.1 Recommended Approach: Option A (Pre-Prompt Recursive Anonymizer)

**Choice**: Implement a `MetadataAnonymizer` class that preprocesses data structures before prompt construction, combined with a provider-aware wrapper that decides when to apply anonymization.

**Why**:
1. **Structure-aware**: Can preserve JSON/YAML structure while replacing values
2. **Centralized**: Single place to audit what's anonymized
3. **Composable**: Works with existing `sanitize_prompt()` (order: anonymize → sanitize)
4. **Provider-aware**: Can bypass for local llama.cpp without code changes
5. **Testable**: Unit tests can verify mapping correctness

### 5.2 Placement in Flow

```
┌──────────────────────────────────────────────────────────────┐
│  k9b Backend Process                                         │
│                                                              │
│  ClusterSnapshot / DrilldownArtifact / ReviewInput          │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  MetadataAnonymizer.anonymize(data, provider_type)  │     │
│  │  - Detects provider_type (local vs external)        │     │
│  │  - Builds stable alias mappings                     │     │
│  │  - Recursively replaces names with aliases          │     │
│  └─────────────────────────────────────────────────────┘     │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Prompt Builder (build_*_prompt)                     │    │
│  │  - Uses anonymized data                              │    │
│  │  - Builds prompt string                              │    │
│  └─────────────────────────────────────────────────────┘    │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  sanitize_prompt() - Credential redaction          │    │
│  └─────────────────────────────────────────────────────┘    │
│         │                                                   │
│         ▼                                                   │
│  LLM Provider (local llama.cpp or external)                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Scope** | Structured data (dicts, lists) | More precise than regex on strings |
| **Bypass** | Local llama.cpp (localhost/127.0.0.1) | Data stays local |
| **Alias format** | `{kind}-{letter}` | Readable, preserves kind context |
| **Cross-run** | Fresh mapping per run | No correlation over time |
| **Order** | Anonymize → Sanitize | Anonymization first, then credential redaction |

---

## 6. Risk Tradeoffs

### 6.1 Tradeoff Analysis

| Decision | Gains | Risks |
|----------|-------|-------|
| **Anonymize all cluster names** | Infrastructure topology protected | LLM has less context for diagnosis |
| **Preserve aliases consistently** | Diagnostic continuity within run | Potential for alias→name mapping leakage |
| **Bypass for local llama.cpp** | Simpler local debugging | Inconsistent behavior depending on provider |
| **Fresh mapping per run** | No cross-run correlation | Cannot compare same cluster across runs |

### 6.2 Mitigations

| Risk | Mitigation |
|------|------------|
| LLM has less context | Aliases are consistent within run; LLM can still reason about relationships |
| Alias→name mapping leakage | Mapping never leaves process; only aliases in prompts |
| Inconsistent behavior | Provider detection is explicit; documented in config |
| Diagnostic usefulness loss | Preserve resource kinds, counts, status, structure |

### 6.3 Performance Impact

| Operation | Estimated Cost |
|-----------|---------------|
| Anonymize call (simple dict) | <1ms |
| Anonymize call (snapshot with 100+ resources) | <5ms |
| Recursive traversal | O(n) where n = number of fields |

**Assessment**: Negligible performance impact relative to LLM call latency.

---

## 7. Test Plan

### 7.1 Unit Tests

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| `test_same_name_same_alias` | Anonymize `"production"` twice | Same alias returned |
| `test_different_names_different_aliases` | Anonymize `"production"`, `"staging"` | Different aliases |
| `test_alias_format_cluster` | Input `"my-cluster"` | Output matches `cluster-{letter}` pattern |
| `test_alias_format_namespace` | Input `"default"` | Output matches `namespace-{letter}` pattern |
| `test_alias_format_workload` | Input `{"kind": "Deployment", "name": "myapp"}` | Output has `deployment-{letter}` name |
| `test_nested_structure` | Input `{"spec": {"namespace": "prod"}}` | Nested namespace anonymized |
| `test_list_of_resources` | Input `[{"name": "a"}, {"name": "b"}]` | Both anonymized with different aliases |
| `test_preserves_kind` | Input `{"kind": "StatefulSet", "name": "pg"}` | `kind` field unchanged |
| `test_preserves_counts` | Input `{"node_count": 5}` | Count remains as integer |
| `test_preserves_timestamps` | Input `{"timestamp": "2024-01-15T10:00:00Z"}` | Timestamp unchanged |

### 7.2 Integration Tests

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| `test_snapshot_anonymization` | ClusterSnapshot with known names | Names replaced with aliases in prompt |
| `test_drilldown_anonymization` | DrilldownArtifact with known namespaces | Namespaces anonymized |
| `test_review_enrichment_anonymization` | ReviewInput with cluster metadata | Cluster names anonymized |
| `test_local_provider_bypass` | Provider = llama.cpp local | No anonymization applied |
| `test_external_provider_applies` | Provider = external API | Anonymization applied |

### 7.3 Security Tests

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| `test_credentials_still_redacted` | Input with `"token": "secret123"` | Token remains redacted by `sanitize_prompt()` |
| `test_alias_not_correlated_across_runs` | Two separate anonymizer instances | Same input → different alias |
| `test_local_debug_mode_aliases` | Config `LLM_ANONYMIZE_PERSIST=true` | Aliases persist across runs |
| `test_no_real_names_in_prompt` | Full prompt built from snapshot | No real cluster/namespace names visible |

### 7.4 Verification Commands

```bash
# Run unit tests
.venv/bin/python -m pytest tests/test_anonymizer.py -v

# Run integration tests
.venv/bin/python -m pytest tests/integration/test_prompt_anonymization.py -v

# Run security tests
.venv/bin/python -m pytest tests/test_anonymizer_security.py -v

# Verify no real names in prompts
LLM_DUMP_PROMPTS=1 .venv/bin/python -m k9b health --run-id test-run
# Check that prompts contain aliases like "cluster-a", "namespace-b"
```

---

## 8. Implementation Phases

### 8.1 Phase 1: Core Anonymizer ✅ IMPLEMENTED

- [x] Create `src/k8s_diag_agent/security/anonymizer.py`
- [x] Implement `MetadataAnonymizer` class with mapping logic
- [x] Implement `anonymize()` method for dict, list, string types
- [x] Implement `_generate_alias()` for stable alias generation
- [x] Unit tests for core functionality (`tests/test_metadata_anonymizer.py`)
- [x] Shape preservation tests (no spurious metadata keys added)
- [x] Labels/annotations behavior: preserved by default (use `anonymize_labels_annotations()` for special handling)

**Phase 1 Status**: Core anonymizer implemented and tested (40 tests passing).

### 8.2 Phase 1b: Label/Annotation Handling (Deferred)

- [ ] Decision: integrate `anonymize_labels_annotations()` into `anonymize()` OR keep separate
- [ ] Consider: when should label/annotation values be anonymized vs. preserved?
- [ ] Follow-up: update `anonymize()` to optionally process labels/annotations if desired

**Rationale for deferral**: Labels/annotations require careful handling. Some operators may want them preserved for context. The core anonymizer works correctly for primary metadata fields; label/annotation handling is an enhancement.

### 8.3 Phase 2: Prompt Path Integration ✅ IMPLEMENTED

- [x] Integrate with `build_assessment_prompt()` in `prompts.py`
- [x] Integrate with `build_drilldown_prompt()` in `drilldown_prompts.py`
- [x] Integrate with `_build_prompt()` in `llamacpp_adapter.py`
- [x] Verify existing `sanitize_prompt()` still called after anonymization
- [x] Anonymization is enabled by default for all LLM prompt paths
- [x] Local-provider bypass is NOT implemented (deferred per design)

**Phase 2 Status**: All 3 prompt paths now anonymize cluster metadata before building prompts.
- Single `MetadataAnonymizer` instance per prompt for alias consistency
- Original input objects are not mutated
- `sanitize_prompt()` still runs after anonymization
- Integration tests added in `tests/test_prompt_anonymization.py`

**Note**: Local-provider bypass is intentionally not implemented in this slice.
The design document (Section 2.2) describes this as a future/optional feature.
If needed, it can be added by checking `LLAMACPP_BASE_URL` for localhost/127.0.0.1.

### 8.4 Phase 3: Testing & Validation (OPEN)

- [ ] Run unit tests from Section 7.1
- [ ] Run integration tests from Section 7.2
- [ ] Run security tests from Section 7.3
- [ ] Verify `scripts/verify_all.sh` passes

---

## 9. Open Questions

| ID | Question | Impact | Status |
|----|---------|--------|--------|
| **Q-P1** | Should `run_id` be anonymized or left as-is? | Affects traceability | Open |
| **Q-P2** | Should labels containing business context be anonymized? | Affects label handling | Open |
| **Q-P3** | Is there a config flag to disable anonymization for debugging? | Affects UX | Recommended |

---

## 10. Related Documents

| Document | Relationship |
|----------|-------------|
| `docs/security/llm-prompt-security-audit.md` | Parent audit; GAP-P2 source |
| `docs/security/threat-model.md` | RISK-01, RISK-06 mapping |
| `src/k8s_diag_agent/security/sanitizer.py` | Existing credential redaction |
| `src/k8s_diag_agent/llm/prompts.py` | Path 1 prompt builder |
| `src/k8s_diag_agent/llm/drilldown_prompts.py` | Path 2 prompt builder |
| `src/k8s_diag_agent/external_analysis/llamacpp_adapter.py` | Path 3 prompt builder |

---

## 11. Next Steps

This design document is the input for the next implementation prompt. The next prompt should:

1. Ask for implementation of the `MetadataAnonymizer` class
2. Reference this document as the design specification
3. Request tests as specified in Section 7
4. Target `scripts/verify_all.sh` as the acceptance gate

---

**Document End**
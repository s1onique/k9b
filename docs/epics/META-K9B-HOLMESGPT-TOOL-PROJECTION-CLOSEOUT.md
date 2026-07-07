# META-K9B-HOLMESGPT-TOOL-PROJECTION-CLOSEOUT

**Epic**: META-K9B-HOLMESGPT-FACTORY-TRANSFER01  
**Slice**: Tool-Output Projection Transfer  
**Status**: CLOSED  
**Date**: 2026-07-07

---

## Why This Slice Exists

The HolmesGPT-inspired tool infrastructure introduced read-only Kubernetes collectors that produce unbounded output. Without projection, large kubectl responses (pods, events, deployments) could bloat LLM prompts and leak local filesystem paths.

This slice establishes bounded metadata contracts from raw collector output to LLM-facing prompts, ensuring:

- **Read-only safety**: Raw kubectl output is projected through budget/spill/reducer
- **Local path protection**: `raw_artifact_path` never reaches serialized bundles or prompts
- **Token budget control**: Only bounded metadata reaches LLM context
- **Auditability**: `raw_artifact_id` provides artifact reference without path leakage

---

## Upstream HolmesGPT Inspiration

HolmesGPT demonstrated that read-only tool outputs can be bounded by budget and spill mechanisms, with only metadata reaching LLM prompts. The artifact ID provides audit reference while raw output stays in controlled storage.

Key insight: Projecting tool output through budget/spill creates a separable boundary where metadata flows to LLM context but raw payloads remain artifactized.

---

## k9b Factory-Native Adaptation

k9b adapted HolmesGPT patterns to its incident-driven architecture:

| HolmesGPT Pattern | k9b Adaptation |
|-------------------|----------------|
| Tool budget/spill | `project_read_only_tool_output()` |
| Artifact reference | `raw_artifact_id` in `ToolOutputSpillResult` |
| Bounded metadata | `ToolProjectionMetadata` dataclass |
| Incident evidence | `IncidentEvidenceBundle.tool_output_projection` |
| Case-file assembly | `build_incident_case_file()` |
| LLM prompt | `build_diagnosis_prompt()` |

The adaptation preserves the boundary pattern while integrating with k9b's incident lifecycle, artifact storage, and case-file generation.

---

## Completed ACTs

| ACT | Subject | Commit |
|-----|---------|--------|
| ACT-K9B-HOLMESGPT-VERIFY01 | Initial verification scaffolding | - |
| ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01 | Split tool infrastructure | - |
| ACT-K9B-HOLMESGPT-TOOL-INFRA-PRODUCTION-SEAM01 | Wire bounded tool output into read-only check | f568203 |
| ACT-K9B-HOLMESGPT-COLLECT-PODS-CALLER-COMPAT01 | Propagate pod projection metadata | da50517 |
| ACT-K9B-LAB-FINDINGS-GIT-HYGIENE01 | Keep generated lab findings out of fixtures | c6b8726 |
| ACT-K9B-HOLMESGPT-TOOL-PROJECTION-SECOND-COLLECTOR01 | Project second read-only collector output | 256ab7f |
| ACT-K9B-HOLMESGPT-TOOL-PROJECTION-CONTRACT01 | Stabilize projection metadata contract | da9cc39 |
| ACT-K9B-HOLMESGPT-TOOL-PROJECTION-BUNDLE-CONTRACT01 | Lock serialized projection metadata | 4d9a48b |
| ACT-K9B-HOLMESGPT-TOOL-PROJECTION-DEPLOYMENTS01 | Project deployment collector output | 09d752e |
| ACT-K9B-HOLMESGPT-SPILL-REASON-TYPO01 | Fix spill reason enum typo | fc750a2 |
| ACT-K9B-HOLMESGPT-LLM-CASEFILE-PROJECTION-CONTRACT01 | Lock case-file projection boundary | 0882822 |

Commits verified against repository HEAD (0882822).

---

## Final Architecture

```
raw Kubernetes collector output
    ↓
ToolBudget (token/size limit)
    ↓
project_read_only_tool_output() → ToolOutputSpillResult
    ↓
reducer/spill pipeline
    ↓
ToolProjectionMetadata (canonical schema)
    ↓
IncidentEvidenceBundle.tool_output_projection
    ↓
written incident.json (artifactized)
    ↓
build_incident_case_file() → sanitized packet
    ↓
LLM-facing case file (safe metadata only)
    ↓
build_diagnosis_prompt() → prompt
```

---

## Protected Boundaries

### 1. Collector Boundary

Raw kubectl output is projected through `project_read_only_tool_output()`:

```python
# src/k8s_diag_agent/collect/tool_output_projection.py
spill_result = project_read_only_tool_output(raw_output, budget, ...)
# spill_result.raw_artifact_path is internal-only
# spill_result.raw_artifact_id is the external reference
```

### 2. Serialized Bundle Boundary

`IncidentEvidenceBundle` and written `incident.json` preserve safe metadata only:

```python
# src/k8s_diag_agent/collect/incident_models.py
@dataclass
class IncidentEvidenceBundle:
    tool_output_projection: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Excludes: raw_artifact_path, raw_output, llm_visible (standalone)
```

### 3. Case-File Boundary

`build_incident_case_file()` strips forbidden projection keys recursively:

```python
# src/k8s_diag_agent/collect/incident_case_file.py
_FORBIDDEN_PROJECTION_KEYS = frozenset({
    "raw_artifact_path",
    "raw_output",
    "llm_visible",  # standalone - llm_visible_size_bytes is allowed
})
```

### 4. Prompt Boundary

`build_diagnosis_prompt()` includes sanitized projection metadata:

```python
# src/k8s_diag_agent/collect/incident_llm_diagnosis.py
# Includes tool_output_projection (already sanitized in build_incident_case_file)
# Does not reintroduce raw output or local paths
```

---

## Collector Coverage

| Collector | Status | Projection Metadata |
|-----------|--------|-------------------|
| `collect_pods` | ✅ Implemented | `kubectl_get` → pods metadata |
| `collect_events` | ✅ Implemented | `kubectl_events` → events metadata |
| `collect_deployments` | ✅ Implemented | `kubectl_get` → deployments metadata |

All three collectors return `(items, errors, projection_metadata)` tuple.

---

## Metadata Schema

### Canonical Shape

```python
@dataclass(frozen=True)
class ToolProjectionMetadata:
    schema_version: str           # "1.0"
    source_tool: str              # "kubectl_get", "kubectl_events"
    spill_occurred: bool          # True if content was artifactized
    spill_reason: str | None      # Reason for spill (if occurred)
    raw_artifact_id: str | None   # Artifact reference ID (not local path)
    raw_size_bytes: int           # Raw tool output size in bytes
    llm_visible_size_bytes: int   # LLM-visible projection size in bytes
    content_type: str             # "json", "manifest"
    error: str | None             # Bounded error message
    provenance: dict[str, Any]    # Provenance tracking dict
```

### Schema Version

`PROJECTION_METADATA_SCHEMA_VERSION = "1.0"`

### Allowed Field: `llm_visible_size_bytes`

`llm_visible_size_bytes` is **allowed** and **preserved**. This is the size metric for LLM-visible projection, distinct from the forbidden `llm_visible` standalone object.

---

## Forbidden Persisted/Prompt Fields

These fields must never appear in serialized bundles, case files, or prompts:

| Forbidden Field | Reason |
|-----------------|--------|
| `raw_artifact_path` | Local absolute filesystem paths |
| `raw_output` | Raw tool output payloads |
| `llm_visible` (standalone) | Raw LLM-visible content objects |
| Raw Kubernetes list bodies | Bypasses projection budget |

The `llm_visible_size_bytes` field is explicitly **allowed** as it is a size metric, not content.

---

## Verification Commands

### Contract Tests

```bash
python3 -m pytest \
  tests/test_tool_projection_metadata_contract.py \
  tests/test_tool_projection_bundle_contract.py \
  tests/test_tool_projection_bundle_contract_e2e.py \
  tests/test_tool_projection_bundle_written_contract.py \
  tests/test_tool_projection_deployments_bundle_contract.py \
  tests/test_incident_case_file_tool_projection_contract.py \
  tests/test_incident_case_file_tool_projection_contract_edge_cases.py \
  tests/test_incident_llm_prompt_tool_projection_contract.py
```

### Collector Projection Tests

```bash
python3 -m pytest \
  tests/test_tool_output_projection_seam.py \
  tests/test_collect_events_projection.py \
  tests/test_collect_deployments_projection.py
```

### Closure Verifier

```bash
python3 -m pytest tests/test_holmesgpt_tool_projection_epic_closure.py
```

### Quality Gates

```bash
ruff check src tests docs
mypy src/k8s_diag_agent
python3 scripts/verify_llm_friendly.py
./scripts/verify_all.sh --act-local
```

---

## Remaining Out-of-Scope HolmesGPT Ideas

These ideas are explicitly deferred to future epics:

| Idea | Deferral Reason |
|------|-----------------|
| Approval streaming HTTP/SSE | Requires UX and API design |
| Frontend tools | Separate epic scope |
| Provider breadth/productization | Product roadmap |
| Eval marker taxonomy | Eval infrastructure epic |
| Install surface polish | Release engineering epic |
| Automatic remediation | Safety considerations |
| Third-party toolset YAML contracts | External integration epic |
| Multi-provider capability matrix | Provider abstraction epic |

---

## Non-Goals (Explicitly Excluded)

- ❌ New collectors beyond pods/events/deployments
- ❌ Changes to projection schema version
- ❌ Changes to spill thresholds
- ❌ Changes to reducer behavior
- ❌ Removal of `LLMR_VISIBLE_EXCEEDED` compatibility alias
- ❌ Frontend work
- ❌ Approval streaming
- ❌ Provider abstraction work
- ❌ Remediation features

---

## Reference Files

- `src/k8s_diag_agent/collect/tool_projection_metadata.py` - Canonical schema
- `src/k8s_diag_agent/collect/tool_output_projection.py` - Budget/spill seam
- `src/k8s_diag_agent/collect/incident_models.py` - Bundle model
- `src/k8s_diag_agent/collect/incident_case_file.py` - Case-file boundary
- `src/k8s_diag_agent/collect/incident_llm_diagnosis.py` - Prompt boundary
- `tests/test_tool_projection_metadata_contract.py` - Schema tests
- `tests/test_tool_projection_bundle_contract.py` - Bundle tests
- `tests/test_incident_case_file_tool_projection_contract.py` - Case-file tests
- `tests/test_incident_llm_prompt_tool_projection_contract.py` - Prompt tests

---

## Epic Status

**META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / Tool-Output Projection Slice: CLOSED**

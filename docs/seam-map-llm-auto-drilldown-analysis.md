# Seam Map: LLM Auto-Drilldown Analysis

**Status**: ACT 1 - Seam mapped (extraction candidate identified)  
**Inspected**: `_run_auto_drilldown_analysis`  
**Epic**: Extract health loop LLM auto-drilldown analysis

---

## Current State

The LLM auto-drilldown analysis seam has **partial extraction**. Core responsibilities are already separated into focused modules, but **orchestration remains embedded in `loop.py`**.

---

## 1. Orchestration Remaining in loop.py

**Location**: `src/k8s_diag_agent/health/loop.py` lines 705-1006

**Size**: ~300 lines

**Shape** (pseudocode):

```python
def _run_auto_drilldown_analysis(self, drilldowns, directories):
    policy = self.config.external_analysis.auto_drilldown
    if not policy.enabled or policy.max_per_run <= 0 or not drilldowns:
        return []
    
    artifacts = []
    attempts = 0
    for drilldown in drilldowns:
        if attempts >= policy.max_per_run:
            break
        attempts += 1
        
        # Timing
        start = time.perf_counter()
        
        # Prompt measurement (calls external build_drilldown_prompt)
        actual_prompt = build_drilldown_prompt(drilldown)
        actual_prompt_chars = len(actual_prompt)
        
        # LLM call start logging
        self._log_event("llm-call", "INFO", "LLM call started", ...)
        
        # Call external assess_drilldown_artifact
        try:
            assessment = assess_drilldown_artifact(drilldown, provider_name=...)
            # Extract findings, next_checks, summary from assessment
            status = ExternalAnalysisStatus.SUCCESS
        except LLMResponseParseError as exc:
            # Build failure metadata, diagnostics
            status = ExternalAnalysisStatus.FAILED
        except ValueError as exc:
            status = ExternalAnalysisStatus.SKIPPED
        except Exception as exc:
            # Classify failure, build diagnostics
            status = ExternalAnalysisStatus.FAILED
        
        # Create ExternalAnalysisArtifact
        artifact = ExternalAnalysisArtifact(...)
        
        # Write artifact
        write_external_analysis_artifact(artifact_path, artifact)
        
        # Result logging
        self._log_event("external-analysis", ...)
        self._log_event("llm-call", ...)
    
    return artifacts
```

**Responsibilities**:
- Policy check (`policy.enabled`, `max_per_run`)
- Loop iteration with attempt counting
- Timing measurement (`time.perf_counter()`)
- Prompt character counting (for diagnostics)
- LLM call start/result logging
- Failure metadata assembly
- `ExternalAnalysisArtifact` construction
- Artifact path naming
- Artifact persistence via `write_external_analysis_artifact`

---

## 2. Extractable: LLM Prompt/Context Assembly

**Module**: `src/k8s_diag_agent/llm/drilldown_prompts.py`

**Size**: 221 lines

**Public API**:
```python
def build_drilldown_prompt(artifact: DrilldownArtifact) -> str:
    """Build LLM prompt from drilldown artifact."""
```

**Responsibilities**:
- Anonymize cluster identifiers via `MetadataAnonymizer`
- Truncate bulky sections (events: 5, pods: 5, rollouts: 3)
- Format artifact metadata, evidence summary, warning events
- Apply prompt boundary markers (BEGIN/END_UNTRUSTED_CLUSTER_DATA)
- Generate schema reminder with constraints (max 2 items per list)
- Sanitize prompt via `sanitize_prompt()`

**Status**: **Already extracted** ✓

---

## 3. Extractable: LLM Response Parsing/Validation

**Module**: `src/k8s_diag_agent/llm/assessor_schema.py`

**Size**: 276 lines

**Public API**:
```python
class AssessorAssessment:
    @classmethod
    def from_dict(cls, raw: Any, path: str = "assessment") -> AssessorAssessment: ...
    def to_dict(self) -> dict[str, Any]: ...
```

**Nested validators**:
- `AssessorSignal.from_dict()`
- `AssessorFinding.from_dict()`
- `AssessorHypothesis.from_dict()`
- `AssessorNextCheck.from_dict()`
- `AssessorRecommendedAction.from_dict()`

**Status**: **Already extracted** ✓

---

## 4. Extractable: LLM Provider Interaction

**Module**: `src/k8s_diag_agent/llm/llamacpp_provider.py`

**Size**: 143 lines

**Public API**:
```python
class LlamaCppProvider(LLMProvider):
    def assess(
        self,
        prompt: str,
        payload: LLMAssessmentInput,
        *,
        max_tokens: int | None = None,
        response_format_json: bool | None = None,
    ) -> dict[str, Any]: ...
    
    def max_tokens_for_operation(self, operation: str) -> int | None: ...
```

**Responsibilities**:
- Build HTTP request payload via `build_payload()`
- Send request to llama.cpp endpoint
- Extract response via `extract_assessment()`
- Validate against `AssessorAssessment` schema
- Handle HTTP errors with `build_error_message()`

**Status**: **Already extracted** ✓

**Related**: `src/k8s_diag_agent/llm/llamacpp_provider_response.py` (227 lines)
- `extract_assessment()` - Parse HTTP response, extract JSON content
- `build_error_message()` - Human-readable error messages

---

## 5. Extractable: Drilldown Assessment Orchestration

**Module**: `src/k8s_diag_agent/health/drilldown_assessor.py`

**Size**: 253 lines

**Public API**:
```python
def assess_drilldown_artifact(
    artifact: DrilldownArtifact,
    provider_name: str = "default",
    *,
    max_tokens: int | None = None,
) -> AssessorAssessment:
    """Run the named provider against a drilldown artifact."""

def build_drilldown_prompt_diagnostics(...) -> dict[str, object]: ...

def resolve_drilldown_max_tokens(provider_name: str, ...) -> int | None: ...

def extract_drilldown_prompt_sections(artifact: DrilldownArtifact) -> list[PromptSection]: ...
```

**Responsibilities**:
- Build LLM prompt via `build_drilldown_prompt()`
- Construct `LLMAssessmentInput` payload
- Sanitize payload via `sanitize_payload()`
- Call provider `assess()` method
- Return `AssessorAssessment` object

**Status**: **Already extracted** ✓

---

## 6. Fallback/Error Behavior

**Module**: `src/k8s_diag_agent/llm/llamacpp_provider_errors.py`

**Size**: 216 lines

**Public API**:
```python
class LLMFailureClass(StrEnum):
    LLM_CLIENT_READ_TIMEOUT = "llm_client_read_timeout"
    LLM_CLIENT_CONNECT_TIMEOUT = "llm_client_connect_timeout"
    LLM_SERVER_HTTP_ERROR = "llm_server_http_error"
    LLM_RESPONSE_PARSE_ERROR = "llm_response_parse_error"
    ...

def classify_llm_failure(exc: BaseException, ...) -> tuple[LLMFailureClass, str]: ...

class LLMResponseParseError(ValueError):
    def to_diagnostics(self) -> dict[str, Any]: ...
```

**Status**: **Already extracted** ✓

---

## Proposed Module Names for Extraction

### Option A: Extract to `loop_runner_drilldown_analysis.py`

Create new module under `health/`:

```
src/k8s_diag_agent/health/loop_runner_drilldown_analysis.py
```

**Responsibilities**:
- Policy check (enabled, max_per_run)
- Loop iteration with attempt counting
- Timing measurement
- Prompt character measurement
- LLM call logging (start/result)
- ExternalAnalysisArtifact construction
- Artifact path naming
- Artifact persistence
- Failure metadata assembly

**Interface**:
```python
from .loop_types import HealthSnapshotRecord

def run_auto_drilldown_analysis_for_records(
    drilldowns: list[DrilldownArtifact],
    directories: dict[str, Path],
    run_id: str,
    run_label: str,
    auto_drilldown_policy: AutoDrilldownPolicy,
    provider_name: str,
    log_event_fn: LogEventFn | None = None,
) -> list[ExternalAnalysisArtifact]:
```

### Option B: Extract to `llm/drilldown_analysis.py`

Create new module under `llm/`:

```
src/k8s_diag_agent/llm/drilldown_analysis.py
```

**Responsibilities**:
- Same as Option A but places orchestration closer to LLM seam

---

## Call Site

Single call site at `loop.py` line 469:

```python
auto_artifacts = self._run_auto_drilldown_analysis(drilldowns, directories)
```

---

## Dependencies Passed Through

| Dependency | Source | Purpose |
|------------|--------|---------|
| `run_id` | `self.run_id` | Artifact naming, logging |
| `run_label` | `self.run_label` | Logging |
| `auto_drilldown` policy | `self.config.external_analysis.auto_drilldown` | Rate limiting |
| `_log_event` | `self._log_event` | Structured logging |
| `assess_drilldown_artifact` | `drilldown_assessor` | LLM assessment |
| `write_external_analysis_artifact` | `external_analysis.artifact` | Persistence |

---

## Runner State Coupling

Minimal coupling:

- Passes `run_id` and `run_label` for logging metadata
- Uses `self._log_event` callback for structured logging
- No state mutation beyond logging

---

## LLM Provider Coupling

The orchestration calls:
- `build_drilldown_prompt()` from `llm/drilldown_prompts.py`
- `assess_drilldown_artifact()` from `health/drilldown_assessor.py`
- `build_drilldown_prompt_diagnostics()` for failure logging

These are already properly abstracted through module seams.

---

## Artifact Behavior

### Auto Drilldown Artifact

- **Path**: `{run_id}-{label}-auto-{provider}.json` in `external_analysis/`
- **Purpose**: `ExternalAnalysisPurpose.AUTO_DRILLDOWN`
- **Payload**: `AssessorAssessment.to_dict()` on success
- **Non-fatal**: Failed/skipped drilldowns don't stop the run

### Status Mapping

| Condition | Status |
|-----------|--------|
| `assess_drilldown_artifact()` succeeds | `SUCCESS` |
| `LLMResponseParseError` | `FAILED` |
| Other `ValueError` (schema validation) | `SKIPPED` |
| Network/provider error | `FAILED` |

---

## Logging Behavior

| Event | Severity | When |
|-------|----------|------|
| `llm-call` (start) | INFO | Before LLM call |
| `llm-call` (result) | INFO/WARNING/ERROR | After LLM call |
| `llm-prompt-diagnostics` | ERROR | On parse/classification failure |
| `auto-drilldown` | INFO/WARNING/ERROR | Based on status |

---

## Why Extraction Should Proceed

1. **Separation of concerns**: Loop orchestration (`loop.py`) should coordinate, not implement LLM pipeline details
2. **Testability**: Extracted module can be unit tested without health loop runner
3. **Parallel extraction pattern**: Follows existing pattern (e.g., `loop_runner_comparisons.py`, `loop_runner_drilldowns.py`)
4. **Minimal blast radius**: The orchestration is already decoupled via module seams

---

## Non-Goals for ACT 1

- No behavior changes to `_run_auto_drilldown_analysis`
- No new features
- No test additions (verification only)

---

## Next Recommended ACT

**ACT 2**: Extract `_run_auto_drilldown_analysis` orchestration to `loop_runner_drilldown_analysis.py`

**Steps**:
1. Create `loop_runner_drilldown_analysis.py` module
2. Move orchestration logic (timing, logging, artifact construction, persistence)
3. Keep external calls to `assess_drilldown_artifact()`, `build_drilldown_prompt_diagnostics()`
4. Update `loop.py` to import and delegate
5. Run verification gate
6. Commit with seam map update

---

## Acceptance Criteria Status

- [x] Loop.py inspected for LLM auto-drilldown analysis responsibilities
- [x] Nearby helper modules inspected (drilldown.py, loop_drilldown_helpers.py, etc.)
- [x] LLM module files inspected (prompts.py, drilldown_prompts.py, etc.)
- [x] Extractable responsibilities identified
- [x] Seam map document produced under `docs/`
- [ ] Proposed module names finalized
- [ ] Extraction performed (deferred to ACT 2)
- [ ] Verification gate run
- [ ] Commit if verification passes
# Seam Map: LLM Auto-Drilldown Analysis

**Status**: ACT 2 - Extraction complete  
**Extracted**: `_run_auto_drilldown_analysis` → `loop_runner_drilldown_analysis.py`  
**Epic**: Extract health loop LLM auto-drilldown analysis

---

## Current State

The LLM auto-drilldown analysis seam has **full extraction complete**. Orchestration has been moved from `loop.py` to `loop_runner_drilldown_analysis.py`. `loop.py` now delegates to the extracted helper.

---

## 1. Orchestration Extracted to loop_runner_drilldown_analysis.py

**Location**: `src/k8s_diag_agent/health/loop_runner_drilldown_analysis.py`

**Size**: ~400 lines

**Public API**:
```python
def run_auto_drilldown_analysis(
    *,
    drilldowns: list[DrilldownArtifact],
    directories: dict[str, Path],
    run_id: str,
    run_label: str,
    auto_drilldown_policy: AutoDrilldownPolicy,
    provider_name: str,
    log_event_fn: LogEventFn | None = None,
) -> list[ExternalAnalysisArtifact]:
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

**Status**: **Extracted** ✓ (ACT 2 complete)

---

## 2. loop.py Delegation

**Location**: `src/k8s_diag_agent/health/loop.py` lines 705-720

**Implementation**:
```python
def _run_auto_drilldown_analysis(self, drilldowns, directories):
    """Run LLM-based auto-drilldown analysis on drilldown artifacts.

    Delegates to the extracted loop_runner_drilldown_analysis module.
    Preserves behavior exactly - no schema or artifact contract changes.
    """
    from .loop_runner_drilldown_analysis import run_auto_drilldown_analysis as _run_auto_drilldown_impl

    return _run_auto_drilldown_impl(
        drilldowns=drilldowns,
        directories=directories,
        run_id=self.run_id,
        run_label=self.run_label,
        auto_drilldown_policy=self.config.external_analysis.auto_drilldown,
        provider_name=self.config.external_analysis.auto_drilldown.provider or "default",
        log_event_fn=self._log_event,
    )
```

**Status**: **Delegating** ✓

---

## 3. LLM Prompt/Context Assembly

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

## 4. LLM Response Parsing/Validation

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

## 5. LLM Provider Interaction

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

## 6. Drilldown Assessment Orchestration

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

## 7. Fallback/Error Behavior

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

## Module Extraction Decision

**Selected**: Option A - `loop_runner_drilldown_analysis.py`

Rationale:
- Follows existing extraction pattern (`loop_runner_comparisons.py`, `loop_runner_drilldowns.py`)
- Places orchestration near other health loop runner helpers
- Minimal coupling to runner via explicit dependency injection

---

## Call Sites

Single call site at `loop.py` line 469:

```python
auto_artifacts = self._run_auto_drilldown_analysis(drilldowns, directories)
```

`HealthLoopRunner._run_auto_drilldown_analysis` now delegates to `loop_runner_drilldown_analysis.run_auto_drilldown_analysis()`.

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
- Uses `log_event_fn` callback for structured logging
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
| `external-analysis` | INFO/WARNING/ERROR | Based on status |

---

## Why Extraction Proceeded

1. **Separation of concerns**: Loop orchestration (`loop.py`) should coordinate, not implement LLM pipeline details
2. **Testability**: Extracted module can be unit tested without health loop runner
3. **Parallel extraction pattern**: Follows existing pattern (e.g., `loop_runner_comparisons.py`, `loop_runner_drilldowns.py`)
4. **Minimal blast radius**: The orchestration is already decoupled via module seams

---

## Acceptance Criteria Status

- [x] Loop.py inspected for LLM auto-drilldown analysis responsibilities
- [x] Nearby helper modules inspected (drilldown.py, loop_drilldown_helpers.py, etc.)
- [x] LLM module files inspected (prompts.py, drilldown_prompts.py, etc.)
- [x] Extractable responsibilities identified
- [x] Seam map document produced under `docs/`
- [x] Proposed module names finalized
- [x] Extraction performed (ACT 2 complete)
- [x] Verification gate run
- [x] Commit if verification passes

---

## ACT 2 Summary

**Files created**:
- `src/k8s_diag_agent/health/loop_runner_drilldown_analysis.py` - Extraction target
- `tests/test_loop_runner_drilldown_analysis.py` - Unit tests

**Files modified**:
- `src/k8s_diag_agent/health/loop.py` - Delegates to extracted helper
- `docs/seam-map-llm-auto-drilldown-analysis.md` - Updated status

**Behavior preserved**:
- Policy check (enabled, max_per_run)
- Loop iteration with attempt counting
- Timing measurement
- Prompt character measurement
- LLM call logging (start/result/diagnostics)
- Status mapping (SUCCESS/FAILED/SKIPPED)
- Artifact construction and persistence
- Failure metadata assembly
- Skip on SKIPPED with reason

**Tests added**:
- `test_disabled_policy_returns_no_artifacts`
- `test_max_per_run_zero_returns_no_artifacts`
- `test_empty_drilldowns_returns_no_artifacts`
- `test_max_per_run_limits_attempts`
- `test_successful_assessment_writes_artifact_and_logs_result`
- `test_parse_failure_produces_failed_artifact_and_diagnostics_logging`
- `test_validation_valueerror_maps_to_skipped_non_fatal_behavior`
- `test_network_error_produces_failed_artifact`
- `test_no_log_fn_does_not_fail`
- `test_artifact_path_format_preserved`
- `test_skipped_stops_loop_early`
- `test_external_analysis_log_emitted`

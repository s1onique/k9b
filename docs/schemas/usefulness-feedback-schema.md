# Usefulness Feedback Schema

Defines the JSON contract for batch usefulness feedback on executed next-check candidates, enabling external reviewer model evaluation and machine-importable feedback ingestion.

## Usefulness Feedback Contract

This schema is used for importing reviewed usefulness judgments into the system. It is the inverse of the export schema (`next-check-usefulness-review/v1`).

### Schema Version

```
next-check-usefulness-feedback/v2
```

### Document Structure

```json
{
  "schema_version": "next-check-usefulness-feedback/v2",
  "run_id": "health-run-20260408T061911Z",
  "run_label": "Daily Health Check",
  "generated_at": "2026-04-08T12:00:00Z",
  "reviewer_notes": "Optional reviewer notes about the batch",
  "entries": [
    {
      "artifact_path": "external-analysis/health-run-20260408T061911Z-next-check-execution-0.json",
      "run_id": "health-run-20260408T061911Z",
      "candidate_id": "candidate-001",
      "candidate_index": 0,
      "cluster_label": "cluster-a",
      "command_family": "kubectl-logs",
      "command_preview": "kubectl logs deployment/app -n default",
      "description": "Get application logs",
      "execution_status": "success",
      "timed_out": false,
      "timestamp": "2026-04-08T06:20:00Z",
      "usefulness_class": "useful",
      "usefulness_summary": "Logs revealed CPU throttling events that correlate with the observed latency spike."
    }
  ]
}
```

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | Yes | Must be `next-check-usefulness-feedback/v2` |
| `run_id` | string | Yes | Identifier of the run this feedback applies to |
| `run_label` | string | No | Human-readable label for the run |
| `generated_at` | string | No | RFC3339 timestamp when feedback was generated |
| `reviewer_notes` | string | No | Free-form notes from the reviewer about the batch |
| `entries` | array | Yes | Non-empty list of feedback entries |

### Entry Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `artifact_path` | string | Yes | Relative path to the execution artifact (from health directory root) |
| `run_id` | string | Yes | Run identifier (must match top-level) |
| `candidate_id` | string | No | Candidate identifier from planning |
| `candidate_index` | integer | No | Candidate index in the plan |
| `cluster_label` | string | No | Target cluster for this check |
| `command_family` | string | No | Command family grouping (e.g., `kubectl-logs`, `kubectl-get`) |
| `command_preview` | string | No | Preview of the actual command that was executed |
| `description` | string | No | Human-readable description of the candidate |
| `execution_status` | string | No | Execution outcome: `success`, `failed`, `timed-out`, `skipped` |
| `timed_out` | boolean | No | Whether execution timed out |
| `timestamp` | string | No | RFC3339 timestamp of the execution |
| `usefulness_class` | string | **Yes** | Usefulness classification (see below) |
| `usefulness_summary` | string | **Yes** | Summary explanation of the usefulness judgment |
| `review_stage` | string | No | Stage of investigation (see Context Fields below) |
| `workstream` | string | No | Type of diagnostic workstream (see Context Fields below) |
| `problem_class` | string | No | Problem category (see Context Fields below) |
| `judgment_scope` | string | No | Scope of judgment (see Context Fields below) |
| `reviewer_confidence` | string | No | Reviewer's confidence level (see Context Fields below) |

### Context Fields (Optional)

These optional fields enable stage-aware usefulness feedback. They are not required for backward compatibility but enable more nuanced analysis when provided.

#### review_stage

| Value | Description |
|-------|-------------|
| `initial_triage` | Initial assessment phase |
| `focused_investigation` | Deep-dive investigation |
| `parity_validation` | Verification against baseline |
| `follow_up` | Post-resolution check |
| `unknown` | Unspecified stage |

#### workstream

| Value | Description |
|-------|-------------|
| `incident` | Incident response |
| `evidence` | Evidence gathering |
| `drift` | Configuration drift detection |
| `unknown` | Unspecified workstream |

#### problem_class

| Value | Description |
|-------|-------------|
| `workload_failure` | Pod/deployment failures |
| `readiness_probe` | Readiness probe issues |
| `liveness_probe` | Liveness probe issues |
| `crashloop` | CrashLoopBackOff state |
| `image_pull` | Image pull failures |
| `job_failure` | Job execution failures |
| `node_condition` | Node-level issues |
| `platform_drift` | Platform configuration drift |
| `networking` | Network-related issues |
| `storage` | Storage/PVC issues |
| `unknown` | Unspecified problem |

#### judgment_scope

| Value | Description |
|-------|-------------|
| `run_context` | Judgment applies to this specific run |
| `pattern_level` | Judgment represents a broader pattern |

#### reviewer_confidence

| Value | Description |
|-------|-------------|
| `low` | Low confidence in judgment |
| `medium` | Medium confidence in judgment |
| `high` | High confidence in judgment |

### Usefulness Classes

| Value | Description |
|-------|-------------|
| `useful` | Command output provided actionable diagnostic signal |
| `partial` | Output was partially useful but noisy or incomplete |
| `noisy` | Output was unhelpful or masked the relevant signal |
| `empty` | No useful output was produced (command failed or returned empty) |

### Import Contract

1. **Required fields**: `artifact_path`, `run_id`, `usefulness_class`, `usefulness_summary`
2. **Idempotency**: Re-importing the same feedback entry updates the artifact in place (no duplication)
3. **Dedupe key**: The combination of `run_id` + `candidate_index` + `artifact_path` serves as the dedupe key
4. **Validation**: Invalid `usefulness_class` values cause entry rejection with error reporting

### Derived Summary Artifact

After import, a summary artifact is generated at:
```
health/diagnostic-packs/{run_id}/usefulness_summary.json
```

This artifact contains:
- Counts by usefulness class
- Counts by command family
- Duplicate group statistics
- Top candidates flagged for planner improvement
- Context-aware conditional rollups (when context fields are provided):
  - by command_family
  - by command_family + workstream
  - by command_family + review_stage
  - by command_family + problem_class

> **Note**: Command-family judgments are context-sensitive. A command family that appears "noisy" in one stage (e.g., `initial_triage`) may be very useful in another (e.g., `focused_investigation`). Do not treat command-family judgments as global by default. Use the context-aware rollups to make informed decisions.

## Export Schema (Reference)

The export schema (`next-check-usefulness-review/v1`) is the inverse contract used for generating review files. See `scripts/export_next_check_usefulness_review.py` for details.

### Export Entry Structure

```json
{
  "artifact_path": "external-analysis/health-run-20260408T061911Z-next-check-execution-0.json",
  "run_id": "health-run-20260408T061911Z",
  "run_label": "Daily Health Check",
  "candidate_id": "candidate-001",
  "candidate_index": 0,
  "cluster_label": "cluster-a",
  "command_preview": "kubectl logs deployment/app -n default",
  "command_family": "kubectl-logs",
  "description": "Get application logs",
  "execution_status": "success",
  "timed_out": false,
  "status": "success",
  "result_summary": "Captured 150 lines of logs showing OOMKilled events",
  "suggested_next_operator_move": "Check memory limits on the affected deployment",
  "timestamp": "2026-04-08T06:20:00Z",
  "usefulness_class": null,
  "usefulness_summary": null,
  "result_digest": "OK (1234B)",
  "result_digest_lines": ["pod-xyz 1/1 Running 0 2d"],
  "stderr_digest": null,
  "stdout_digest": "pod-xyz 1/1 Running 0 2d",
  "signal_markers": ["OOMKilled", "CrashLoopBackOff"],
  "failure_class": null,
  "exit_code": 0,
  "output_bytes_captured": 1234,
  "stdout_truncated": false,
  "stderr_truncated": false
}
```

### Result Digest Fields

The export includes compact result digest fields derived from execution artifacts. These enable high-quality reviewer judgment without exposing full stdout/stderr dumps.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `result_digest` | string | Yes | Compact primary digest summarizing result (e.g., "OK (1234B)", "TIMED_OUT", error excerpt) |
| `result_digest_lines` | array | No | Up to 5 most useful output lines; includes `[+N more lines]` indicator if truncated |
| `stderr_digest` | string | No | Compact stderr summary if stderr was non-empty (first error line, max 100 chars) |
| `stdout_digest` | string | No | Compact stdout summary (first non-error line, max 100 chars) |
| `signal_markers` | array | No | K8s diagnostic markers extracted from output (e.g., CrashLoopBackOff, OOMKilled, Forbidden) |
| `failure_class` | string | No | Failure classification if command failed (e.g., "timeout", "not_found", "permission_denied") |
| `exit_code` | integer | No | Command exit code if available |
| `output_bytes_captured` | integer | No | Total bytes captured from stdout+stderr |
| `stdout_truncated` | boolean | No | Whether stdout was truncated during capture |
| `stderr_truncated` | boolean | No | Whether stderr was truncated during capture |

### Signal Markers

The following diagnostic markers may be extracted from execution output:

| Marker | Description |
|--------|-------------|
| `CrashLoopBackOff` | Pod is in CrashLoopBackOff state |
| `ImagePullBackOff` | Image pull failed |
| `ErrImagePull` | Image pull error |
| `OOMKilled` | Pod was killed due to memory limit |
| `Evicted` | Pod was evicted |
| `FailedScheduling` | Pod failed to schedule |
| `ReadinessProbeFailed` | Readiness probe failed |
| `LivenessProbeFailed` | Liveness probe failed |
| `StartupProbeFailed` | Startup probe failed |
| `ProbeFailed` | Generic probe failure |
| `Forbidden` | Permission forbidden |
| `Unauthorized` | Unauthorized access |
| `NotFound` | Resource not found |
| `DNSError` | DNS resolution failed |
| `ConnectionRefused` | Connection refused |
| `TLSCertError` | TLS/certificate error |
| `Timeout` | Command timed out |
| `ResourceQuota` | Resource quota exceeded |
| `ResourceLimit` | Resource limit hit |

### Duplicate Detection

Export entries may include duplicate metadata when multiple candidates produce identical outputs:

```json
{
  "duplicate_group_id": "dup-kubectl-logs-001",
  "duplicate_count": 3,
  "duplicate_siblings": [
    "external-analysis/...-execution-0.json",
    "external-analysis/...-execution-5.json",
    "external-analysis/...-execution-12.json"
  ],
  "representative_entry_index": 0
}
```

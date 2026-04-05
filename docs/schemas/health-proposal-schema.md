# Health Proposal Schema

Defines the canonical JSON that records each adaptation proposal emitted by the health review layer.

| Field | Type | Description |
| --- | --- | --- |
| `proposal_id` | string | Unique identifier scoped to the health run (e.g., `<run_id>-warning-threshold`). |
| `source_run_id` | string | `run_id` that generated the health review artifact. |
| `source_artifact_path` | string | Filesystem path of the health review (`runs/health/reviews/<run_id>-review.json`). |
| `target` | string | Dot-notated config or subsystem that should be tuned (e.g., `health.trigger_policy.warning_event_threshold`). |
| `proposed_change` | string | Human-readable description of the specific adjustment being suggested. |
| `rationale` | string | Why this change is believed to improve signal/noise quality. |
| `confidence` | `ConfidenceLevel` (`low`, `medium`, `high`) | Estimated certainty of the proposal. |
| `expected_benefit` | string | Anticipated operational improvement (noise reduction, fewer false positives, etc.). |
| `rollback_note` | string | How to revert the tuning change or what to monitor if it regresses. |

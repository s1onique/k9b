# Feedback Artifact Schema

Defines the structured artifacts that capture each operational run, the comparisons it produces, and the evaluation/adaptation signal that follows.

## RunArtifact
| Field | Type | Description |
| --- | --- | --- |
| `run_id` | string | Unique identifier for the run (CID-like or timestamp-based). |
| `timestamp` | RFC3339 timestamp | When the run started or was recorded. |
| `context_name` | string, optional | Operational context (cluster name, fixture id). |
| `collector_version` | string | Agent/CLI version that captured or replayed the evidence. |
| `collection_status` | string | `complete`, `partial`, or `failed`, describing evidence availability. |
| `snapshot_pair` | `SnapshotPairArtifact` | The primary and secondary snapshots evaluated in this run. |
| `comparison_summary` | map&lt;string,int&gt; | Counts of added/removed/changed objects from the comparator. |
| `missing_evidence` | list&lt;string&gt; | Explicitly reported telemetry gaps that were noted during collection. |
| `assessment` | `AssessmentArtifact`, optional | JSON assessment emitted after reasoning completes. |
| `validation_results` | list&lt;`ValidationResult`&gt; | Validators or evals that inspected the run and their outcomes. |
| `failure_modes` | list&lt;`FailureMode`&gt; | Catalog of detected failures during this run or eval. |
| `proposed_improvements` | list&lt;`ProposedImprovement`&gt; | Suggestions for the adaptation loop, if any. |
| `notes` | string, optional | Free-form context or operator notes. |

## SnapshotPairArtifact
| Field | Type | Description |
| --- | --- | --- |
| `primary_snapshot_id` | string | Source snapshot identifier or path. |
| `primary_snapshot_path` | string | Filesystem path of the primary snapshot artifact. |
| `secondary_snapshot_id` | string, optional | Identifier for the comparison target (if any). |
| `secondary_snapshot_path` | string, optional | Filesystem path of the secondary snapshot artifact. |
| `comparison_summary` | map&lt;string,int&gt; | Reuse counts for added/removed/changed resources. |
| `status` | string | `complete`, `partial`, or `failed` for the comparison step. |
| `start_time` | RFC3339 timestamp, optional | When the pair comparison began. |
| `end_time` | RFC3339 timestamp, optional | When the pair comparison finished. |
| `missing_evidence` | list&lt;string&gt; | Evidence that could not be collected for this comparison. |

## AssessmentArtifact
| Field | Type | Description |
| --- | --- | --- |
| `assessment_id` | string | Non-secret identifier tied to the assessment payload. |
| `schema_version` | string | Schema version (e.g., `assessment-schema:v1`). |
| `assessment` | object | The structured assessment JSON (signals, findings, hypotheses, etc.). |
| `overall_confidence` | string, optional | Summary confidence extracted from the assessment. |

## ValidationResult
| Field | Type | Description |
| --- | --- | --- |
| `name` | string | Validator/eval identifier (e.g., `schema-check`, `falsifiability`). |
| `passed` | boolean | Whether the validator succeeded. |
| `errors` | list&lt;string&gt; | Human-friendly reasons for failure. |
| `checked_at` | RFC3339 timestamp | When the validation was run. |
| `failure_mode` | `FailureMode`, optional | Categorized failure tied to this validation. |

## FailureMode
| Value | Description |
| --- | --- |
| `missing_evidence` | Evidence required by reasoning was unavailable. |
| `false_certainty` | Assessment expressed unjustified confidence. |
| `validation_failure` | A validator or eval check failed. |
| `collection_error` | Snapshot collection yielded partial/inconsistent data. |
| `invalid_artifact` | The artifact schema itself was malformed. |
| `other` | Uncategorized failure that still requires attention. |

## ProposedImprovement
| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Identifier for the improvement proposal. |
| `description` | string | What should change (prompt, rule, schema, etc.). |
| `target` | string | Asset or subsystem the improvement affects. |
| `owner` | string, optional | Who should review the proposal. |
| `confidence` | `ConfidenceLevel`, optional | How confident the proposer is in the fix. |
| `rationale` | string, optional | Why the improvement matters. |
| `related_failure_modes` | list&lt;`FailureMode`&gt; | Failure modes that motivated the proposal. |

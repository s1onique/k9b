# Run Artifact Layout

Defines where replayable evidence, comparison summaries, assessments, and feedback artifacts live on disk so the operational, evaluation, and adaptation loops stay inspectable.

## Directory structure
- `runs/snapshots/`: sanitized Kubernetes snapshots collected during the run. Files keep deterministic snapshot metadata so the collector/compare CLI path keeps working unchanged.
- `runs/comparisons/`: JSON summaries produced by `compare_snapshots` or similar tooling; typically contains version deltas, Helm diff metadata, and missing evidence notes.
- `runs/assessments/`: assessment payloads (matching `docs/schemas/assessment-schema.md`) produced during reasoning or LLM paths to keep track of expected outputs.
- `runs/feedback/`: `RunArtifact` JSON blobs that bind snapshots, comparisons, assessments, validation results, failure modes, and proposed improvements.
- `runs/health/`: health artifacts produced by `run-health-loop`, including per-cluster assessments, triggered comparisons, and the persistent health history that feeds trigger heuristics.

## Naming conventions
- Snapshot files are `runs/snapshots/{context}-{timestamp}.json` so collection flows can append data without breaking the deterministic CLI or fixture runner.
- Comparison files are `runs/comparisons/{run_id}-diff.json` and contain the comparator summary referenced by the `snapshot_pair` inside a `RunArtifact`.
- Assessments are `runs/assessments/{run_id}-assessment.json` and mirror the structure described in `docs/schemas/assessment-schema.md`.
- Feedback artifacts live in `runs/feedback/{timestamp}-{run_id}.json` and conform to `docs/schemas/feedback-artifact-schema.md`.
- Health assessments are `runs/health/assessments/{run_id}-{cluster}.json` and follow the same assessment schema. Each health artifact (assessments, comparisons, triggers) records the stable `run_label` from the config while `{run_id}` is the timestamped identifier generated for the current execution. Triggered comparisons land under `runs/health/comparisons` along with `runs/health/triggers`, and `runs/health/history.json` tracks the previous runs that inform heuristics.

## Operational guarantees
- The existing deterministic collection/compare commands continue to serialize snapshots and diffs under `runs/snapshots` and `runs/comparisons` as before; feedback artifacts are additive and only read optional extra metadata.
- The `k8s-diag-agent run-feedback` command bridges collection, comparison, optional assessment, and validation so every execution writes a self-contained set of artifacts under this layout. Validators can replay a `RunArtifact` by reading the referenced snapshot, comparison, and assessment files, enabling evaluation and adaptation loops to rerun deterministically.

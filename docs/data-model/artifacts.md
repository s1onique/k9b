# Artifact taxonomy

## Purpose

Document durable artifact taxonomy and source-of-truth boundaries.

**Rule: Artifacts own evidence truth.**

## Immutable source-of-truth artifacts

These artifacts are written once and never modified:

| Artifact | Path pattern | Authority |
|----------|--------------|-----------|
| Pack ZIP | `diagnostic-packs/diagnostic-pack-{run_id}-{timestamp}.zip` | Immutable source of truth |
| Run-scoped contents | `diagnostic-packs/{run_id}/` | Immutable source of truth |
| ClusterSnapshot | `runs/health/snapshots/{run_id}-{cluster_label}-{timestamp}.json` | Immutable source of truth |
| Assessment | `runs/health/assessments/{run_id}-{cluster_label}.json` | Immutable source of truth |
| Comparison | `runs/health/comparisons/{run_id}-{primary}-vs-{secondary}-comparison.json` | Immutable source of truth |
| Drilldown | `runs/health/drilldowns/{run_id}-{cluster_label}.json` | Immutable source of truth |
| Review | `runs/health/reviews/{run_id}-review.json` | Immutable source of truth |
| Proposal | `runs/health/proposals/{proposal_id}.json` | Immutable source of truth |
| ExternalAnalysisArtifact | `runs/health/external-analysis/{run_id}-{cluster_label}-{adapter}.json` | Immutable source of truth |
| History fact artifacts | `runs/health/history/{run_id}-{cluster_id}-{artifact_id}.json` | Immutable source of truth |
| Alertmanager action artifacts | `runs/health/alertmanager-source-actions/{run_id}-{source_id}-{action}-{artifact_id}.json` | Immutable append-only |

## Latest mirror semantics

**The `diagnostic-packs/latest/` directory is a mutable derived convenience alias, NOT an immutable artifact.**

- It exists for operator convenience and UI/API convenience paths.
- It is overwritten in place when new diagnostic packs are generated or refreshed.
- Immutable truth lives in the actual diagnostic pack ZIP file and run-scoped pack contents.
- API/UI consumers must NOT treat `latest/` paths as immutable references.

### Source-of-truth boundary

- **Pack ZIP files** (`diagnostic-packs/diagnostic-pack-{run_id}-{timestamp}.zip`) are immutable once written.
- **Run-scoped contents** (`diagnostic-packs/{run_id}/`) are immutable once written.
- **`latest/` mirror** is derived and mutable—use for convenience only.

## History and notifications

### History

- `runs/health/history.json` keeps per-target history used for regression detection. This aggregate file is **mutable**: each run overwrites the previous state so it always reflects the latest observation for each cluster.
- Immutable history fact artifacts complement the mutable aggregate: each health run also writes per-cluster fact artifacts under `runs/health/history/`. These `HealthHistoryFactArtifact` entries are immutable once written.

### Notifications

Notifications under `runs/health/notifications/` record events from the loop, proposals, and external analysis adapters.

## Derived projections

### UI index

`write_health_ui_index` re-reads the current run's artifacts and produces `runs/health/ui-index.json`. The UI/API then derive payloads from that index so the backend never stores another copy.

### LLM/provider artifacts

Each completed provider call is captured as an `ExternalAnalysisArtifact`. The UI computes `llmStats` from these artifacts.

`llmStats` in the UI index is derived strictly from the latest run's `external-analysis` artifacts, while `historicalLlmStats` is recomputed by re-scanning retained JSON files.

### Provider execution visibility

The `provider_execution` slice reports how each provider-assisted branch actually executed in the current run. It summarizes run-scoped config plus artifacts and is purely observability-focused.

## Immutable vs mutable summary

| Type | Examples | Mutability |
|------|----------|------------|
| **Immutable source of truth** | Pack ZIPs, run-scoped contents, snapshots, assessments, drilldowns, reviews, proposals, history fact artifacts, Alertmanager action artifacts | Written once, never modified |
| **Mutable convenience alias** | `latest/` mirrors, `history.json` | Overwritten, not authoritative |
| **Derived projections** | `ui-index.json`, LLM stats, provider execution slices | Computed on read, not persistence |

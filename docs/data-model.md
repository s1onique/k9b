# Data model and run lifecycle

## Purpose

- Capture the current artifact-first contracts that tie the scheduler, backend, and UI together.
- Show how the durable JSON blobs under `runs/health/…` remain the source of truth while the UI and API layers derive their projections from them.
- Describe the implicit lifecycle stages `run-health-loop` already follows so future work can target those transitions without assuming a formal state machine beyond what is currently implemented.

## Core entities (current reality)

### `run_label`
- Declared in `runs/health-config*.json` and treated as the stable fleet label for every iteration.
- Recorded verbatim in each artifact so runs can be tied back to the policy that spawned them (the deprecated per-run `run_id` field is now interpreted as this label if present).

### `run_id`
- Generated on every invocation of `run-health-loop` (and anything that drives it, such as `scripts/run_health_scheduler.py`).
- Timestamp-based, unique per execution, and used to name files under `runs/health/{snapshots,assessments,…}` plus in the `RunArtifact` `run_id` field.

### Target cluster / cluster label / context
- Each entry in the health config supplies a `cluster_label` (human-friendly key), a `context` (kubeconfig identifier), `cluster_class`, `cluster_role`, and `baseline_cohort` metadata.
- These values appear in every snapshot, assessment, drilldown, notification, and history row, so they are the stable identity used throughout the run.

### Snapshot
- Sanitized `ClusterSnapshot` JSON per target, written under `runs/health/snapshots/{run_id}-{cluster_label}.json`.
- Captures raw evidence (`node_count`, control plane version, events, pods, etc.) and feeds both the comparator and the health assessment logic.

### Assessment
- Per-cluster health assessment stored at `runs/health/assessments/{run_id}-{cluster_label}.json` (see `docs/schemas/assessment-schema.md`).
- Contains health rating, missing evidence, findings, hypotheses, next checks, recommended actions, confidence, and links back to the snapshot used.

### Comparison
- Triggered comparisons live under `runs/health/comparisons/{run_id}-{primary_label}-vs-{secondary_label}.json` and summarize resource additions/removals plus any drift notes.
- Produced when `run-health-loop` detects a policy trigger (`peer_mappings`, `--trigger`, or suspicious drift) and stores the comparator output referenced by both the review and the notification artifacts.

### Trigger
- Each comparison writes a `runs/health/triggers/{run_id}-{primary_label}.json` entry containing the `ComparisonTriggerArtifact`—the why behind the comparison (intent, reasons, comparison summary, eligibility status).
- The trigger record is the authoritative list of policies or metadata conditions that caused the comparator to run.

### Drilldown
- When a trigger fires, the health loop collects additional drilldown evidence (non-running pods, warning events, sectioned summaries) and writes it as `runs/health/drilldowns/{run_id}-{cluster_label}.json`.
- Drilldowns feed `assess-drilldown`, provide human-oriented context for reviewers, and are surfaced to the UI as “drilldown availability.”

### Review
- `run-health-loop` writes a review artifact per fleet run under `runs/health/reviews/{run_id}-review.json`.
- Reviews aggregate the per-cluster assessments, comparisons, triggers, drilldowns, and generated proposals so the adaptation loop has a single JSON document to reference.

### Proposal
- Typed adaptation suggestions live under `runs/health/proposals/{proposal_id}.json` (see `docs/schemas/health-proposal-schema.md`).
- Each proposal references its `source_run_id`, the triggering review path, expected benefit, confidence, and rationale for tuning thresholds, watched releases, or other policy artifacts.

### History entry
- `runs/health/history.json` keeps the persisted per-cluster history (previous node/pod counts, control plane version, watched Helm releases/CRDs, and missing-evidence markers).
- The loop reads this history before every run so “changed since previous run” findings can be generated deterministically.

### Notification
- Notification artifacts are durable JSON files written to `runs/health/notifications/{timestamp}-{kind}.json` whenever the loop or downstream helpers (proposal checkers, external analysis, etc.) wants to signal an event.
- The CLI command `deliver-notifications` and any future Mattermost/pager integrations hydrate these artifacts via `notification.Artifact` before dispatching.

### Derived UI/API projection
- The backend produces `runs/health/ui-index.json` for every run via `health.ui.write_health_ui_index()`.
- `src/k8s_diag_agent/ui/model.py` builds a `UIIndexContext` from that index, and `src/k8s_diag_agent/ui/api.py` turns the context into `RunPayload`, `FleetPayload`, `ClusterDetailPayload`, `ProposalsPayload`, and `NotificationsPayload` objects that the HTTP API exposes.
- This view model is read-only and derived fully from the durable artifacts; it is not part of the persistence layer but is regenerated whenever a new run finishes.

## Durable artifacts vs operational streams

- **Source of truth:** `runs/health/` (snapshots, assessments, comparisons, triggers, drilldowns, reviews, proposals, notifications, history, and the UI index) is the canonical persisted record.
- **Structured logs (stdout/stderr):** `scripts/run_health_scheduler.py` and `run-health-loop` emit JSON into the console so operators can stream progress, but those streams are not considered durable—consult the artifacts to reconstruct the run.
- **Optional mirrors:** Files such as `runs/health/scheduler.log` or `/runs/health/*.log` may duplicate entries for legacy tooling, but they are derived from the same console stream and not treated as the single source of truth.
- **LLM call artifacts:** Every completed provider invocation—success or failure—is persisted as an `ExternalAnalysisArtifact` under `runs/health/external-analysis/`. The UI aggregates those artifacts when building `llmStats`, so operators can inspect how many LLM calls actually ran, which adapters they used, and what latencies were observed without relying on loose logs. Skipped adapters (status `skipped`) do not count as LLM calls.

## Run lifecycle (implicit stages)

> There is no explicit enum-based state machine today; `run-health-loop` implements a predictable sequence of stages while recording `collection_status` (complete/partial/failed) in each `RunArtifact`.

1. **Scheduled / invoked:** Either the scheduler (`scripts/run_health_scheduler.py`) or an operator invokes `run-health-loop`. A lock file under `runs/health/.health-loop.lock` prevents overlap, and the `run_label` from the config is paired with a freshly minted `run_id`.
2. **Run started:** The loop records the start event, creates per-run directories, and emits a structured log entry with `clusterCount`, `run_id`, `run_label`, and the desired rhythm parameters (`--once`, `--every-seconds`).
3. **Snapshots collected:** Each target cluster snapshot is sanitized and persisted under `runs/health/snapshots/`. The run metadata (`RunArtifact.snapshot_pair`) notes collection status and missing telemetry.
4. **Assessments written:** Health assessments for every cluster are written to `runs/health/assessments/` along with the confidence, findings, missing evidence, and references to the snapshot that produced them.
5. **Comparisons triggered:** When peer mappings flag suspicious drift or a manual `--trigger` is supplied, the comparator runs, stores its summary under `runs/health/comparisons/`, and emits the corresponding trigger record under `runs/health/triggers/`.
6. **Drilldowns gathered:** Triggered clusters collect drilldown evidence, which is stored under `runs/health/drilldowns/` and later surfaced to `assess-drilldown` or the UI as “drilldown availability.”

> **Optional LLM-assisted analysis:** The health loop can optionally hand a cluster artifact to an LLM adapter whenever `external_analysis.manual` is enabled or a manual `--external-analysis` / `--provider` request lands in `run-health-loop`. The same provider seam backs the standalone CLI entry points `assess-drilldown` (run against `runs/health/drilldowns/*.json`) and `assess-snapshots` (run against two sanitized snapshot files). Each provider invocation that completes (success or failure) writes a durable `runs/health/external-analysis/{run_id}-{cluster}-{tool}.json` artifact, and those artifacts feed the `llmStats` slice described further below. These LLM stages are opt-in branches, not part of the mandatory harvest-compare-review path; if no provider is configured or no manual flag is set, the run simply skips them.
7. **Review created:** The health review aggregates snapshots, assessments, comparisons, triggers, and drilldowns into `runs/health/reviews/{run_id}-review.json`; this review is the document proposals read when deciding on candidate adjustments.
8. **Proposals generated:** `generate_proposals_from_review` (called inside the same loop) emits typed proposals into `runs/health/proposals/` with lifecycle history entries that are logged and persisted.
9. **Notifications / summary derived:** The loop writes notification artifacts (degraded health, suspicious comparisons, proposals created/checked, external analysis) into `runs/health/notifications/`. The `health-summary` command and UI build their human-friendly reports from the artifacts listed above.
10. **Run completed / partial / failed:** A successful run populates all directories and appends a history entry in `runs/health/history.json`. Partial runs mark missing evidence, and failures leave structured logs plus a `RunArtifact.collection_status` of `failed` so future tooling can spot gaps.

## Derived UI/API projections

- The backend does not store a separate database; instead it rebuilds the UI index after every run via `health.ui.write_health_ui_index()` (outputs `runs/health/ui-index.json`).
- `ui/model.build_ui_context` loads that index, and `ui/api.build_*` serializes the context into the payloads the frontend consumes (`RunPayload`, `FleetPayload`, `ClusterDetailPayload`, `ProposalsPayload`, `NotificationsPayload`).
- Artifact links (snapshots, assessments, drilldowns, proposals, notification payloads) are surfaced on the UI so operators can open the same durable files that produced the view.
- Any additional summaries (fleet ratings, proposal lifecycle, drilldown coverage, notification history) are recalculated on the fly from the durable artifacts—no derived view is treated as a persistence boundary.
- The run payload now includes an `llmStats` slice that is computed from the `runs/health/external-analysis` artifacts so operators can see how many provider calls were made, how many succeeded/failed, their latencies, and which adapters supplied them.

## Evolution guidance

1. **Artifact-first stays the source of truth.** Future indexing, searchable caches, or persistence layers must read from the JSON artifacts under `runs/` and write back only after confirming they can rebuild from those files.
2. **Keep rebuildability.** If a future index (SQLite, Postgres, or Elastic) is introduced, it should be derived deterministically from the artifacts. Operators and tests should still be able to point at a `runs/health/` directory and reconstruct a previous run.
3. **Do not replace the current file-backed layout.** Any persistence change should sit beside the existing artifacts, not inside them, so the inspectable JSON dir structure remains valid while experimentation continues.
4. **Document before changing.** Add new sections to this doc whenever an entity or lifecycle stage mutates so future developers can reason about the artifact-first contracts before touching runtime behavior.

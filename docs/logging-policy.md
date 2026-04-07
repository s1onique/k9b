# Logging policy

This policy turns the existing observability posture for the health/review/adaptation workflow into a concrete logging standard. Logs exist to document what the health loop, drilldown collection, review/scoring, proposal generation/promotion, and scheduler/operator scripts knew, when they knew it, and how to correlate back to run artifacts without guessing.

## Scope

- `run-health-loop`, its drilldown collectors, the review/assessment artifacts, and the adaptations they emit
- Drilldown assessments and the `assess-drilldown`/`assess-snapshots` flows that feed review decisions
- Proposal generation (`run-health-loop`), scoring (`check-proposal`), and promotion helpers (`promote-proposal`) that emit new configs or baselines
- Scheduler and operator helpers such as `scripts/run_health_scheduler.py` that orchestrate the rhythm of the loop

## Log goals

- Surface start/stop, success, failure, and retry reasoning for the scheduler, health loop, and review orchestration
- Preserve enough metadata so a reviewer can correlate a log line with the artifacts that were produced in that run
- Capture warning/error signals that explain why a proposal was rejected, why a drilldown was forced, or why a run was partial/missing evidence
- Allow automation to pivot to the next evidence-to-collect query without re-parsing unstructured prose

## Required fields

Every structured log entry that feeds the health review pipeline should include at least the following:

1. `timestamp` – UTC, ISO 8601 (e.g., `2026-04-06T06:12:05Z`).
2. `component` – the logical producer (`health-loop`, `drilldown-collector`, `review-assessment`, `proposal-promotion`, `health-scheduler`, etc.).
3. `severity` – one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Always uppercase.
4. `message` – concise human-readable description of what happened; keep the explanatory text short and let metadata carry the rest.
5. `run_label` – the stable label from the health config (fallback to a deprecated `run_id` when no label exists).

Other metadata fields should be present when they help correlate artifacts (see the next section).

## Severity usage

- `DEBUG`: low-value breadcrumbs for local development (not required in production logs).
- `INFO`: normal lifecycle transitions (scheduler start/stop, run-health-loop invocation, review summary, proposal creation).
- `WARNING`: partial results (missing evidence, skipped targets, forced drilldowns) where the run completed but produced data that needs attention.
- `ERROR`: failures that stop a stage from completing (config missing, collection failure, provider/LLM rejection).
- `CRITICAL`: catastrophic conditions that should trigger operator alerting (data corruption, repeated health loop crashes, lost history store). Reserve for non-recoverable states.

## Structured vs human logs

- **Structured logs**: use JSON lines or stable key-value payloads so downstream analysis can `grep key=value` instead of re-parsing transcripts. Always emit `timestamp`, `component`, `severity`, `message`, `run_label`, and any available artifact correlation keys. Example: the scheduler now writes JSON entries into `runs/health/scheduler.log`, although stdout/stderr has become the primary stream for those entries.
- **Human logs**: CLI output and `print()` statements stay terse, summary-focused, and optional (`--quiet`). Do not convert CLI summaries into source-of-truth logs; keep them as aids for live operators. When you add new CLI output, favor the existing `format_summary`/`format_health_summary` helpers so reviewers can parse the results by reading the artifact files instead of relying on transient text.

## Log destinations

- **Streams first**: operational logs flow to stdout/stderr by default. Treat them as event streams, and do not rely on repo-local log files as the primary sink. When `emit_structured_log` is invoked without an explicit `log_path`, the output should go straight to the process streams; components may optionally duplicate entries into `runs/health/*.log` when downstream consumers still expect those files.
- **Files remain durable artifacts**: snapshots, assessments, drilldowns, proposals, reviews, and history records stay in `runs/health/...` as file-backed artifacts. The console stream is the live signal, and the files are the durable records that help auditors replay what happened.
- **Exceptions must be explicit**: any component still writing primarily to a repo-local log file must document the compatibility reason and confirm that stdout/stderr remains the main operational stream.

## Privacy and redaction rules

- Never log API tokens, kubeconfig blobs, or other secrets. If a log would normally include a sensitive field, replace it with a placeholder such as `<scrubbed>` or record only the `artifact_path` that holds the original value.
- Prefer sanitized identifiers (e.g., `label` instead of raw kube context) and avoid leaking customer data by trimming hostnames or DNS details that are not already captured in sanctioned history artifacts.
- The scheduler log should only reference stable labels or the trusted `runs/health-config.local.json` contents; its JSON format makes it easy to scrub or redact after-the-fact if a config accidentally contains private text.

## Artifact correlation fields

Logs must include any of these fields when they are relevant to the event being logged. A missing field should be justified in the log text.

| Field | Use case |
| --- | --- |
| `run_id` | Unique identifier created per iteration (e.g., `health-run-20260406T061200Z`). Always include if known; `run-health-loop` writes artifacts with it. |
| `run_label` | Stable label from the config (`health-run` in the examples). Use for long-lived dashboards. |
| `cluster_label` | The target label (e.g., `cluster-alpha`). Attach to per-cluster prompts, drilldown, or review log entries. |
| `proposal_id` | The GUID of a proposal under review or promotion. Log it when a proposal is created, replayed, or promoted. |
| `artifact_path` | Path to the generated JSON (snapshot, assessment, drilldown artifact, proposal, promotion patch, etc.). This lets operators open the file referenced by the log line. |

Additional helpful fields include `collector_version`, `target_labels` (comma-delimited clusters affected by the event), `command`, `command_args`, and `severity_reason`. Ensure these are included before adding new ones so logs stay predictable.

## Implementation notes (current reality)

- `scripts/run_health_scheduler.py` streams scheduler entries to stdout/stderr as the canonical sink and only mirrors them into `runs/health/scheduler.log` when `K9B_HEALTH_SCHEDULER_LOG_PATH` points at that file. Each entry carries `component`, `severity`, `message`, `run_label`, `target_labels`, `command`, `event`, and `config_path`. This document is the source of truth for how we expect structured scheduler logs to look.
- Other modules that eventually adopt logging should follow the same schema: keep the JSON payload lean, include the required fields, and add artifact correlation keys when the log references a specific cluster, proposal, or artifact.

Follow this policy when you touch logging in any component of the observability pipeline. When the policy does not cover an edge case, prefer the minimally sufficient change that keeps the logs actionable, private, and correlatable.

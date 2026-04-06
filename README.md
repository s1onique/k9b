# k8s-diag-agent

Fixture-driven Kubernetes diagnostics agent that can ingest replayable snapshots or collect real cluster state. Prefer running commands through the project virtual environment (`.venv/bin/python`).

## CLI usage

### Diagnose a fixture (legacy interface)
```bash
k8s-diag-agent fixtures/<name>.json [--output <path>] [--quiet]
```
This path loads a fixture, normalizes signals, runs the reasoning layer, and optionally writes a structured assessment.

### Collect a live snapshot
```bash
k8s-diag-agent snapshot --context <kube-context> --output <snapshot.json>
```
This command discovers the requested Kubernetes context, queries the control plane version, Helm releases, and CRD definitions, and writes a typed `ClusterSnapshot` to the specified file.

### Compare two snapshots
```bash
k8s-diag-agent compare <snapshot-a.json> <snapshot-b.json>
```
Runs the comparator over two snapshot files, reporting differences in Kubernetes versions, Helm release/chart versions, and CRD presence/versions.

### Collect snapshots for configured contexts
```bash
k8s-diag-agent batch-snapshot [--config snapshots/targets.local.json]
```
Reads `snapshots/targets.local.json` (or the path passed via `--config`). Copy `snapshots/targets.local.example.json`, which uses placeholder contexts such as `cluster-alpha`, into `snapshots/targets.local.json`, replace the placeholders with your real kube contexts, and keep the populated `.local` file untracked. Real runs require the `.local` file; the CLI now fails fast rather than falling back to the example placeholder, so documentation or CI wishing to exercise the command must explicitly point at the example config.

### Evaluate a health proposal

```bash
k8s-diag-agent check-proposal runs/health/proposals/<proposal-id>.json [--fixture tests/fixtures/snapshots/sanitized-alpha.json]
```

`check-proposal` replays a health review proposal against a fixture, reports noise reduction, signal loss, and the simulated test outcome, and lets operators gate each adaptation before it touches configurable thresholds.

## Development

- `.venv/bin/python -m unittest discover tests` (active verification path)
- `.venv/bin/python -m mypy src tests` (type checker; see [typing guidance](docs/typing.md))
- Logs from the health loop, drilldown collectors, review/scoring flows, and scheduler/operator helpers must follow the standards defined in [docs/logging-policy.md](docs/logging-policy.md).
- Follow [docs/security-policy.md](docs/security-policy.md) for secrets handling, live evidence boundaries, provider/environment rules, and proposal-gated adaptation hygiene.

## Fast feedback loops

Use these quick guards before the full verification pipeline settles in:

- `.venv/bin/python -m ruff check src tests`
- `.venv/bin/python -m pytest tests/unit/test_cli_smoke.py`
- `pre-commit run --all-files`

## Optional LLM assessment path

```bash
k8s-diag-agent assess-snapshots \
  tests/fixtures/snapshots/sanitized-alpha.json \
  <edited-snapshot.json> \
  [--provider default] [--output path.json]
```

The new `assess-snapshots` command runs the live comparison logic, feeds the sanitized snapshots and diff into the provider seam, and emits an `Assessment`-like JSON payload. Base the initial pairs on `tests/fixtures/snapshots/sanitized-alpha.json` and the derived comparison artifact under `tests/fixtures/comparisons/sanitized-alpha-vs-beta.json` while adjusting the secondary snapshot to produce the diff you want to replay.

## Operational feedback run

Use `run-feedback` to anchor the operational + evaluation loop so each collection, comparison, and optional assessment becomes typed, inspectable, and replayable.

```
k8s-diag-agent run-feedback --config runs/run-config.local.json
```

## Per-cluster health loop

`run-health-loop` evaluates each configured cluster independently and only compares peers when explicit triggers fire.

```
k8s-diag-agent run-health-loop --config runs/health-config.local.json [--trigger primary:secondary]
```

Copy `runs/health-config.local.example.json` → `runs/health-config.local.json`, keep placeholders (`cluster-alpha`, `cluster-beta`, etc.), and replace them with your real contexts before running. The config describes which clusters to monitor, watched Helm releases/CRDs, trigger policies, and peer mappings. Leave `peer_mappings` empty (and omit `manual_pairs`) when you just need per-cluster health assessments because comparisons only run for configured peers or explicit triggers. Use `--trigger` to force a manual comparison pair for a single run.

The health config now declares a stable `run_label` instead of a fixed `run_id`. Every invocation of `run-health-loop` generates a unique `run_id` (timestamped and safe for filenames) while keeping the configured label in the produced artifacts so you can still correlate runs with your policy. Existing configs that still set `run_id` will continue to work for now, but that value is treated as the run label and a warning flags the deprecation.

Scheduling is optional but the health loop now ships with built-in rhythm control: `--every-seconds` keeps re-running the loop at the requested interval, `--max-runs` caps the number of iterations, and `--once` forces a single collection even if you pass scheduling arguments. A lockfile under `runs/health/.health-loop.lock` prevents overlapping runs and each iteration emits a short summary of the generated artifacts so you can track progress without enabling the verbose collector output.

To operate the loop continuously, use `scripts/run_health_scheduler.py` with the cadence flags that match your shift cycle (for example `.venv/bin/python scripts/run_health_scheduler.py --every-seconds 300 --max-runs 48`). The wrapper drives `run-health-loop`, logs each scheduler invocation to `runs/health/scheduler.log`, and keeps the deterministic file-backed layout that every review and adaptation run relies on.

After a run finishes, `k8s-diag-agent health-summary --runs-dir runs/health` prints a compact view of the latest artifacts: per-cluster health ratings, the top finding, generated proposals, promoted/adapted proposals with before/after noise/quality deltas, and the comparisons that triggered. Include `--run-id <id>` when you need to revisit a specific iteration.

Every run also gathers lightweight health signals (node readiness/pressure counts, non-running pods, CrashLoopBackOff and ImagePullBackOff tallies, pending pods, failed jobs, and recent warning events) and wires them into the assessment so findings explicitly separate baseline drift, workload health issues, missing evidence, and regressions.


### One-shot health run workflow

1. Copy `runs/health-config.local.example.json` → `runs/health-config.local.json`, replace placeholder contexts with your real clusters, and keep the populated file out of git. `.gitignore` now ignores every `*.local.json` runtime config plus any `snapshots/*.json` captures, and the private-context checker scans live snapshot files so cluster ids can’t slip into commits.
2. Run `.venv/bin/python -m k8s_diag_agent.cli run-health-loop --config runs/health-config.local.json` (or `k8s-diag-agent run-health-loop --config runs/health-config.local.json`). Each invocation still emits a unique `run_id` but reuses the stable `run_label` you configured so the artifacts stay correlated across runs.
3. Inspect the generated artifacts if you want a reviewable record of the execution:
   - `runs/health/snapshots/` for raw cluster evidence captured during this run
   - `runs/health/assessments/` for the serialized `Assessment` objects that include the new deterministic findings about collection quality, watched resources, and regression-aware signals
   - `runs/health/comparisons/` for the diffs that explain why peers were compared
   - `runs/health/triggers/` for the trigger envelopes that store the exact reason strings that caused each comparison
   - `runs/health/drilldowns/` for the collected drilldown evidence that feeds `assess-drilldown` and contextualizes the review
   - `runs/health/reviews/` for the health review payloads plus `runs/health/proposals/` for typed adaptation ideas (see `docs/schemas/health-proposal-schema.md` for the proposal contract)
   - `runs/health/history.json` for the persisted per-cluster history that powers "changed since previous run" findings (node/pod counts, control plane version, watched Helm releases/CRDs, and missing evidence). This history plays a key role in keeping future runs regression-aware.
4. Repeat the command to capture another point in time; the deterministic findings plus the persisted history let you replay or reason about regressions without needing a scheduler. Use `--trigger primary:secondary` when you want to force a peer comparison for a single run.


### Health review and adaptation workflow

1. Run `run-health-loop` to collect snapshots, build health assessments, record review artifacts, and emit adaptation proposals; each proposal is written under `runs/health/proposals/` and references the review that inspired it.
2. Inspect the drilldown evidence under `runs/health/drilldowns/` or call `assess-drilldown` if you need an optional LLM judgment on a focused artifact.
3. Re-evaluate any proposal with `k8s-diag-agent check-proposal runs/health/proposals/<proposal-id>.json [--fixture <fixture>]` to see the projected noise reduction, signal loss, and test/eval outcome before accepting a change to thresholds or policies.
4. Repeat the health loop + review + proposal cycle so changes remain grounded in evidence, and only apply adjustments after they survive the `check-proposal` replay.


### Local config runbook
1. Copy `runs/run-config.local.example.json` → `runs/run-config.local.json` and `snapshots/targets.local.example.json` → `snapshots/targets.local.json` before running collection. Replace each `cluster-*` placeholder with your real contexts and keep the populated `.local` files out of git; real runs now require the `.local` files because the CLI will exit when only the example config exists. `.gitignore` already keeps runtime configs and logs ignored so the repository stays free of private names.
2. `collect_and_compare_clusters.sh` loads the preferred config (`local` first, then the template) and builds the `CONTEXTS` array from the `targets` list. Use this script to automate the same run-feedback/batch-snapshot flows; the `--context` overrides are still available for ad-hoc targets.
3. Always invoke diagnostics via `.venv/bin/python` so the virtualenv-controlled interpreter stays aligned with project guidance.

The `ban-private-contexts` pre-commit hook now also inspects the tracked snapshot directories so names collected at runtime never slip into commits.

If the LLM assessment is optional or fails, the run still captures the snapshots/comparisons, records the failure in the feedback artifact, and only exits non-zero when collection itself fails critically. The resulting artifacts become the typed trace that later evaluation, scoring, and adaptation loops consume.

See `docs/typing.md` for the type-annotation conventions that guide new code.

## llama.cpp provider

Configure the environment before invoking `assess-snapshots` so the `llamacpp` provider can talk to your OpenAI-compatible llama.cpp deployment:

- `LLAMA_CPP_BASE_URL` (required): base URL of the llama.cpp service (for example `http://localhost:8080`). Do not include `/v1` or other path fragments; the provider appends `/v1/chat/completions` automatically.
- `LLAMA_CPP_MODEL` (required): model alias exposed by the server (for example `llama3-q4_0`).
- `LLAMA_CPP_API_KEY` (optional): bearer token or API key that the server expects; omit or leave blank to skip the `Authorization` header when your deployment does not require authentication.

Because the provider appends `/v1/chat/completions`, ensure `LLAMA_CPP_BASE_URL` does not already include `/v1` so that the final endpoint resolves correctly.

The `llamacpp` provider sends the prompt and sanitized cluster evidence to `/v1/chat/completions` and validates the JSON response with `AssessorAssessment.from_dict`. If you need deterministic fallback behavior, keep using `--provider default`.

Example usage:

```bash
LLAMA_CPP_BASE_URL=http://localhost:8080 \
LLAMA_CPP_API_KEY=my-key \
LLAMA_CPP_MODEL=llama3-q4_0 \
k8s-diag-agent assess-snapshots \
  tests/fixtures/snapshots/sanitized-alpha.json \
  tests/fixtures/snapshots/sanitized-beta.json \
  --provider llamacpp
```

If your llama.cpp endpoint does not require authentication, drop the `LLAMA_CPP_API_KEY` assignment (or set it to an empty string) and the provider will send the request without an `Authorization` header.

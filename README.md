# k8s-diag-agent

Fixture-driven Kubernetes diagnostics agent that can ingest replayable snapshots or collect real cluster state. Prefer running commands through the project virtual environment (`.venv/bin/python`).

## Data model and run lifecycle

Artifact-first semantics, entity definitions, and the current run lifecycle are documented in [docs/data-model.md](docs/data-model.md). Refer to that page before making UI, persistence, or workflow changes so future work learns the current contracts instead of inferring them from code.

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

- `scripts/verify_all.sh` (canonical acceptance gate; runs Ruff, unittest, mypy, and the frontend `npm run test:ui` + `npm run build` steps after `npm ci`). Work is not complete unless this script exits successfully and prints `VERIFICATION GATE: PASSED` (or a blocking explanation is documented when the gate cannot run).
- `.venv/bin/python -m unittest discover tests` (active verification path)
- `.venv/bin/python -m mypy src tests` (type checker; see [typing guidance](docs/typing.md))
- Frontend UI smoke: `cd frontend && npm run test:ui`
- Frontend build check: `cd frontend && npm run build`
- Logs from the health loop, drilldown collectors, review/scoring flows, and scheduler/operator helpers must follow the standards defined in [docs/logging-policy.md](docs/logging-policy.md).
- Follow [docs/security-policy.md](docs/security-policy.md) for secrets handling, live evidence boundaries, provider/environment rules, and proposal-gated adaptation hygiene.

## Fast feedback loops

Use these quick guards before the full verification pipeline settles in:

- `scripts/verify_all.sh`
- `.venv/bin/python -m ruff check src tests`
- `.venv/bin/python -m unittest tests/unit/test_fast_feedback_smoke.py`
- `.venv/bin/python -m pytest tests/unit/test_cli_smoke.py`
- `cd frontend && npm run test:ui`
- `cd frontend && npm run build`
- `pre-commit run --all-files`

The `test_fast_feedback_smoke.py` regression exercises the config loader, structured logging, and sanitization-aware CLI path so you can trust the fast feedback loop before you commit.

## Run the UI locally

### Backend startup

- `scripts/start_backend.sh` validates `.venv/bin/python`, optionally runs `scripts/run_health_once.sh`, and launches `python -m k8s_diag_agent.cli health-ui` with the collected artifacts.
- Override the configuration file with `HEALTH_CONFIG_PATH`, the artifact directories with `HEALTH_RUNS_DIR` or `HEALTH_UI_RUNS_DIR`, and the listening address with `HEALTH_UI_HOST`/`HEALTH_UI_PORT`.
- Emit the health digest via `HEALTH_RUN_DIGEST=1` (stdout) or `HEALTH_DIGEST_OUTPUT=path` while still seeding the UI with `run_health_once.sh`.

### Frontend startup

- `scripts/start_frontend.sh` confirms `npm` is available, runs `npm ci` whenever `frontend/node_modules` is absent, and starts the Vite dev server with `FRONTEND_HOST`/`FRONTEND_PORT` (defaults to `127.0.0.1:5173`).
- The Vite dev server proxies `/api` and `/artifact` requests to `http://127.0.0.1:8080`, so run `scripts/start_backend.sh` (or otherwise keep the backend listening on that port) before opening the UI to avoid HTML responses from Vite.

### Optional refresh-less backend mode

- Set `HEALTH_SKIP_REFRESH=1` when invoking `scripts/start_backend.sh` to reuse the last health artifacts without rerunning the snapshot step, which keeps the UI up while new backend runs are unnecessary.

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

 Copy `runs/health-config.local.example.json` → `runs/health-config.local.json`, keep placeholders (`cluster-alpha`, `cluster-beta`, etc.), and replace them with your real contexts before running. The config describes which clusters to monitor, watched Helm releases/CRDs, trigger policies, and peer mappings.
 Each target entry now declares `cluster_class`, `cluster_role`, and `baseline_cohort` (or legacy `platform_generation`) so the loop can reason about responsibility and cohort compatibility across suspicious-drift pairs.
 Run `.venv/bin/python scripts/inspect_health_config.py runs/health-config.local.json` to preview the metadata matrix, see which peers are eligible, skipped, or unsafe, and confirm every suspicious-drift comparison remains policy-compatible before executing the loop.
 Each mapping must declare exactly one `primary`/`secondary` pair so the intentional same-role comparison stays focused. Leave `peer_mappings` empty (and omit `manual_pairs`) when you just need per-cluster health assessments because comparisons only run for configured peers or explicit triggers. Use `--trigger` to force a manual comparison pair for a single run.

The health config now declares a stable `run_label` instead of a fixed `run_id`. Every invocation of `run-health-loop` generates a unique `run_id` (timestamped and safe for filenames) while keeping the configured label in the produced artifacts so you can still correlate runs with your policy. Existing configs that still set `run_id` will continue to work for now, but that value is treated as the run label and a warning flags the deprecation.

 Scheduling is optional but the health loop now ships with built-in rhythm control: `--every-seconds` keeps re-running the loop at the requested interval, `--max-runs` caps the number of iterations, and `--once` forces a single collection even if you pass scheduling arguments. A lockfile under `runs/health/.health-loop.lock` prevents overlapping runs and each iteration emits a structured JSON summary event so you can track progress without flapping the verbose collector output.

To operate the loop continuously, use `scripts/run_health_scheduler.py` with the cadence flags that match your shift cycle (for example `.venv/bin/python scripts/run_health_scheduler.py --every-seconds 300 --max-runs 48`). The wrapper drives `run-health-loop`, emits scheduler events to stdout/stderr as the canonical operational stream, and maintains the deterministic file-backed artifacts that every review and adaptation run relies on. Set `K9B_HEALTH_SCHEDULER_LOG_PATH` if you still need a mirrored `runs/health/scheduler.log` for legacy tooling.

After a run finishes, `k8s-diag-agent health-summary --runs-dir runs/health` prints a compact view of the latest artifacts: per-cluster health ratings, the top finding, generated proposals, promoted/adapted proposals with before/after noise/quality deltas, and the comparisons that triggered. Each comparison line now documents whether the pair was eligible, skipped, or flagged as unsafe, why it was run or skipped, the classification (expected vs suspicious drift), the expected and ignored drift categories, and any notes you configured in `peer_mappings`, making it easier to understand how the policy drove the comparison. Include `--run-id <id>` when you need to revisit a specific iteration.

Every run also gathers lightweight health signals (node readiness/pressure counts, non-running pods, CrashLoopBackOff and ImagePullBackOff tallies, pending pods, failed jobs, and recent warning events) and wires them into the assessment so findings explicitly separate baseline drift, workload health issues, missing evidence, and regressions.

### Continuous scheduler + UI workflow

1. Start the backend (`scripts/start_backend.sh`) so the API serving the UI and artifact endpoints keeps the latest diagnostics in `runs/health`.
2. Launch the scheduler alongside it via `.venv/bin/python scripts/run_health_scheduler.py --every-seconds 300 --max-runs 0`. The helper keeps writing to the file-backed `runs/health` hierarchy (snapshots, assessments, proposals, digests) so the UI sees fresh artifacts without any database or job queue; scheduler events stream to stdout/stderr as structured JSON lines by default and can be mirrored into `scheduler.log` when `K9B_HEALTH_SCHEDULER_LOG_PATH` is set.
3. In a separate terminal, run `scripts/start_frontend.sh` (or `cd frontend && npm run dev`) to keep the React UI pointed at the backend; the UI will poll `/api` and surface fleet/cluster states as each periodic run completes.

 Keeping the scheduler, backend, and frontend running together gives you a shifting production-like loop: the scheduler continuously collects evidence, the backend serves the updated artifacts, and the frontend renders the compact fleet dashboard plus selection-driven cluster detail without introducing a new persistence layer.

The scheduler's run-summary entries now emit `freshness_age_seconds`, `expected_interval_seconds`, and `freshness_status` so you can see whether runs are keeping up with the configured cadence, and the UI surfaces a matching `freshness` field derived from the scheduler interval and the last run timestamp.


### One-shot health run workflow

1. Copy `runs/health-config.local.example.json` → `runs/health-config.local.json`, replace placeholder contexts with your real clusters, and keep the populated file out of git. `.gitignore` now ignores every `*.local.json` runtime config plus any `snapshots/*.json` captures, and the private-context checker scans live snapshot files so cluster ids can’t slip into commits.
    The bundled example policy highlights how to declare the fleet metadata you actually care about: watched Helm releases and CRDs, cluster class/role annotations, and an intentional same-role peer mapping where expected drift categories are spelled out. The baseline file in the same directory now captures a realistic control-plane version window, curated release targets, required CRD families, and the drift categories you choose to ignore versus the ones you expect to change.
    Refer to `docs/baseline_watch_practices.md` for platform-level advice about pruning the baseline and keeping watched releases aligned with the policy.
2. Run `.venv/bin/python -m k8s_diag_agent.cli run-health-loop --config runs/health-config.local.json` (or `k8s-diag-agent run-health-loop --config runs/health-config.local.json`). Each invocation still emits a unique `run_id` but reuses the stable `run_label` you configured so the artifacts stay correlated across runs.
    The runtime stream is now structured JSON only, so rely on the generated artifacts, `k8s-diag-agent health-summary`, or the UI when you need a human-readable recap.
3. Inspect the generated artifacts if you want a reviewable record of the execution:
   - `runs/health/snapshots/` for raw cluster evidence captured during this run
   - `runs/health/assessments/` for the serialized `Assessment` objects that include the new deterministic findings about collection quality, watched resources, and regression-aware signals
   - `runs/health/comparisons/` for the diffs that explain why peers were compared
   - `runs/health/triggers/` for the trigger envelopes that store the exact reason strings that caused each comparison
   - `runs/health/drilldowns/` for the collected drilldown evidence that feeds `assess-drilldown` and contextualizes the review
   - `runs/health/reviews/` for the health review payloads plus `runs/health/proposals/` for typed adaptation ideas (see `docs/schemas/health-proposal-schema.md` for the proposal contract)
   - `runs/health/history.json` for the persisted per-cluster history that powers "changed since previous run" findings (node/pod counts, control plane version, watched Helm releases/CRDs, and missing evidence). This history plays a key role in keeping future runs regression-aware.
4. Repeat the command to capture another point in time; the deterministic findings plus the persisted history let you replay or reason about regressions without needing a scheduler. Use `--trigger primary:secondary` when you want to force a peer comparison for a single run.


### Operator quick run script

`scripts/run_health_once.sh` wraps `inspect_health_config.py`, `run-health-loop --once`, and `health-summary`; pass `--digest` or `--digest-output <path>` to run `make_health_digest.sh` afterward. The wrapper reads the config's `output_dir`, keeps every step inside the configured artifact layout, and presents the same eligibility/unsafe signals you already get from the individual commands.


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

## Containerized stack (Podman / Docker Compose)

Build the Python and frontend images once, then wire them together with a shared `runs` volume and kubeconfig mount.

1. Ensure the runtime configs you plan to use live under `runs/` (for example `runs/health-config.local.json`).
2. Place a kubeconfig bundle under `podman/kubeconfig/config` (symlink or copy from `~/.kube/config`). The compose stack mounts this path so `kubectl`/`helm` inside the Python container can authenticate.
3. `podman machine start` (for Podman Desktop on macOS) so the VM can handle port forwarding; `podman machine init` is required the first time.
4. `podman compose up --build -d` (or `docker compose up --build -d`) to start scheduler, backend, and frontend. The backend publishes `8080`, the frontend publishes `5173`, and the scheduler keeps writing artifacts into `./runs/health`.
5. `podman compose down` (or `docker compose down`) to stop the stack while keeping the `runs` artifacts on disk.

### Volumes & environment worth noting

- `./runs:/app/runs`: shared file-backed artifacts so the backend UI can read what the scheduler writes.
- `./podman/kubeconfig:/app/kubeconfig`: kubeconfig required by `kubectl`/`helm`. Replace `podman/kubeconfig/config` with your real config before starting.
- `frontend_node_modules:/app/frontend/node_modules`: keeps `npm ci` output outside the source tree when the frontend host directory is mounted.
- Environment variables injected by the compose file:
  - `HEALTH_CONFIG_PATH`, `HEALTH_RUNS_DIR`, `HEALTH_UI_RUNS_DIR`, `HEALTH_UI_HOST`, `HEALTH_UI_PORT` for the backend.
  - `HEALTH_CONFIG_PATH`, `HEALTH_RUNS_DIR` for the scheduler.
  - `KUBECONFIG` pointing at `/app/kubeconfig/config` for the Python containers.
  - `VITE_BACKEND_HOST`, `VITE_BACKEND_PORT` so the Vite dev server proxies `/api` and `/artifact` to the backend container instead of `127.0.0.1`.

### Podman Desktop (macOS) caveats

- Podman Desktop runs containers inside a virtual machine, so publishing ports (`8080`, `5173`) is the only way to reach the UI from the macOS host. Use `podman machine ssh` if you need to troubleshoot inside the VM.
- The VM does not automatically share `~/.kube`, so copy or symlink your kubeconfig into `podman/kubeconfig` before starting the stack. The Kubernetes context can still reference remote clusters; only the local file needs to exist.
- Restarting the `podman machine` resets the VM; the compose stack can be brought up again without rebuilding as long as `./runs` and `podman/kubeconfig` remain intact.

If the LLM assessment is optional or fails, the run still captures the snapshots/comparisons, records the failure in the feedback artifact, and only exits non-zero when collection itself fails critically. The resulting artifacts become the typed trace that later evaluation, scoring, and adaptation loops consume.

See `docs/typing.md` for the type-annotation conventions that guide new code.

## llama.cpp provider

Configure the environment before invoking `assess-snapshots` so the `llamacpp` provider can talk to your OpenAI-compatible llama.cpp deployment:

- `LLAMA_CPP_BASE_URL` (required): base URL of the llama.cpp service (for example `http://localhost:8080`). Do not include `/v1` or other path fragments; the provider appends `/v1/chat/completions` automatically.
- `LLAMA_CPP_MODEL` (required): model alias exposed by the server (for example `llama3-q4_0`).
- `LLAMA_CPP_API_KEY` (optional): bearer token or API key that the server expects; omit or leave blank to skip the `Authorization` header when your deployment does not require authentication.

Because the provider appends `/v1/chat/completions`, ensure `LLAMA_CPP_BASE_URL` does not already include `/v1` so that the final endpoint resolves correctly.

The `llamacpp` provider sends the prompt and sanitized cluster evidence to `/v1/chat/completions`. Assessment-style flows such as `assess-snapshots`, `assess-drilldown`, and any path that produces an `Assessment` validate the response with `AssessorAssessment.from_dict`, while review enrichment uses the bounded advisory schema checked by `ReviewEnrichmentPayload.from_dict` so the payload stays limited to `summary`, `triageOrder`/`triage_order`, `topConcerns`/`top_concerns`, `evidenceGaps`/`evidence_gaps`, `nextChecks`/`next_checks`, and `focusNotes`/`focus_notes`. If you need deterministic fallback behavior, keep using `--provider default`.

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

## Provider-assisted review enrichment

The health loop can optionally run an advisory provider-assisted review enrichment *after* it builds the deterministic review artifact. Enrichment adds triage order, top concerns, evidence gaps, and suggested next checks without changing the deterministic review or proposal generation.

Enable it by extending `runs/health-config.local.json` with the `external_analysis.review_enrichment` block (the bundled example already declares `auto_drilldown` and `review_enrichment` alongside `external_analysis.adapters`). Flip `review_enrichment.enabled` to `true` and point `review_enrichment.provider` at the same adapter you enabled in `external_analysis.adapters` (for example `llamacpp`). The same `LLAMA_CPP_*` environment variables described above secure the llama.cpp adapter you register.

When enabled, each run writes `runs/health/external-analysis/{run_id}-review-enrichment-{provider}.json` with the enrichment payload and records success/failure/skipped status in the UI. The Review enrichment panel highlights the status pill, surfaces `skipReason` when the provider is unavailable, and reports `errorSummary` when the request fails. Skipped or failed enrichment runs do not block the deterministic health review or proposal flow.

To keep the external-analysis archive from growing without bounds, the `external_analysis` block accepts an optional `retention` object. Specify `max_artifacts` to keep only the most recent N JSON artifacts and/or `max_age_days` to drop any file older than the given window; retention only prunes historical files so the current run stays intact, and the `llmStats`/`llmActivity` slices simply reflect whatever artifacts remain on disk.

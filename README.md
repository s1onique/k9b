# k9b

k9b is a Kubernetes operations intelligence workbench that helps platform engineers and operators review cluster health, surface actionable findings from noisy signals, and follow evidence-grounded diagnostic workflows without autonomous cluster mutation.

It runs against real clusters via a read-only snapshot collector, persists all evidence as typed, reviewable artifacts, and keeps LLM-assisted branches opt-in, auditable, and advisory-only.

---

## What k9b is

k9b is a Kubernetes health intelligence and review workbench for operators who need to:

- Review cluster health signals, alerts, runs, proposals, summaries, drilldowns, and enrichment flows
- Follow operator-facing workflows that preserve provenance and reviewability
- Use LLM assistance as a bounded advisory layer, not an automatic truth source
- Run against real clusters in read-only/safety-first mode

k9b is designed for production-adjacent environments with genuine cluster evidence, not demo-only flows.

---

## Why it exists

Kubernetes produces too many raw signals. Alerts and logs often lack prioritization, grouping, and operator context. LLMs can help, but only if:

- Evidence boundaries are treated as first-class engineering concerns
- Prompt safety and repeatability are built-in, not bolted on
- Operator review is the gating step before any adaptation

k9b turns noisy cluster evidence into typed, inspectable, replayable artifacts that operators can trace from signal to finding to hypothesis to recommended next check.

---

## Current capabilities

### Cluster health and assessment

- **Snapshot collection** — Collect sanitized cluster snapshots via `k8s-diag-agent snapshot --context <context> --output <file>` or batch mode with `k8s-diag-agent batch-snapshot --config <file>`
- **Health loop** — Run per-cluster health evaluation on a configurable schedule: `k8s-diag-agent run-health-loop --config runs/health-config.local.json`
- **Health assessments** — Deterministic findings about node readiness, pod health, control plane version, Helm releases, CRDs, and regression-aware signals
- **Cluster comparison** — Compare two snapshots to detect drift in versions, releases, and CRDs: `k8s-diag-agent compare <a.json> <b.json>`

### Alert and summary processing

- **Alertmanager source attribution** — Distinguish alerts by cluster of origin and registry namespace
- **Health summaries** — Compact per-cluster summaries with ratings, top findings, and generated proposals
- **Review bundles** — Canonical JSON artifacts bundling fleet state, assessments, drilldowns, and proposals

### Drilldowns and comparisons

- **Automatic drilldown collection** — Warning events, non-running pods, pod descriptions, rollouts, image pull secrets, pattern-specific kubectl outputs
- **Suspicious-drift detection** — Peer-cluster comparison that surfaces unexpected configuration differences across same-role clusters
- **Policy-gated eligibility** — Comparison pairs are evaluated against configured policies; ineligible or unsafe pairs are explicitly skipped

### Review enrichment (LLM-assisted, opt-in)

- **Review enrichment** — Advisory LLM analysis of health reviews adds triage order, top concerns, evidence gaps, and suggested next checks without changing deterministic outputs
- **Drilldown assessment** — Optional LLM judgment on focused drilldown artifacts
- **Diagnostic-pack review** — Second-opinion provider analysis against the generated review artifact

### Proposal and advisory UI

- **Health proposals** — Typed adaptation suggestions (threshold tuning, noise filters, baseline updates) written under `runs/health/proposals/`
- **Proposal replay** — Validate proposals before applying: `k8s-diag-agent check-proposal runs/health/proposals/<id>.json [--fixture <fixture>]`
- **Web UI** — React frontend surfacing fleet dashboard, cluster detail, review panels, proposal management, and diagnostic-pack review

### Next-check workflow

- **Deterministic next-check planning** — Safe diagnostic step candidates per cluster/context derived from current findings
- **Batch execution** — Run eligible checks in batch with dry-run preview: `python scripts/run_batch_next_checks.py --latest [--dry-run]`
- **Usefulness review loop** — Export, annotate, and import feedback on check quality over time
- **Operator approval gating** — Promotes deterministic checks into managed queue with explicit approval before execution

### Demo shell

- **Demo shell component** — Pure Elm-ish state model for demo/demo-like behavior in the UI (`frontend/src/demo-shell/`), testable without React rendering

### Theme system

- **Three themes** — dark (default), solarized-light, rose-pine with runtime switching via `ThemeSwitch` and localStorage persistence

### Safety gates

- **Evidence boundaries** — LLM prompts are bounded and validated; evidence files are redacted before provider calls
- **Semantic injection detection** — Deterministic local detector integrated into prompt construction path
- **Path containment** — Path traversal prevention for static/artifact serving; dotdot, encoding, and symlink boundaries tested
- **LLM-friendly file limits** — Files under 500 lines enforced; splitting required above threshold
- **No autonomous mutation** — Agent never mutates live clusters without explicit operator approval; proposals must pass replay validation
- **Private context protection** — Pre-commit hook blocks private cluster names from commits; snapshots checked at runtime

### Local quality gates

- **Full acceptance gate** — `scripts/verify_all.sh` runs ruff-lint, unit-tests, mypy, and frontend test/build (prints `VERIFICATION GATE: PASSED` on success)
- **Scoped lanes** — `--python-only`, `--frontend-only`, `--helm-only` flags for targeted runs
- **Security baseline** — Pre-commit hook for secrets, private contexts, and security-sensitive patterns
- **LLM evidence/safety gates** — Deterministic tests for evidence boundaries and semantic injection detection (`scripts/verify_llm_evidence_boundaries.py`, `scripts/verify_llm_semantic_injection_detection.py`)

---

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- kubectl configured with target cluster contexts (for live collection)
- Frontend dependencies installed: `cd frontend && npm ci`

### Install dependencies

```bash
# Python virtual environment
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Frontend dependencies
cd frontend && npm ci && cd ..
```

### Run the full acceptance gate

```bash
scripts/verify_all.sh
```

Expected output on success: `VERIFICATION GATE: PASSED`

### Local UI (backend + frontend)

```bash
# Terminal 1: Backend (runs health loop then launches API on port 8080)
scripts/start_backend.sh

# Terminal 2: Frontend (Vite dev server on port 5173)
scripts/start_frontend.sh

# Open http://127.0.0.1:5173
```

The backend refreshes health artifacts before launching; set `HEALTH_SKIP_REFRESH=1` to skip the refresh step and reuse existing artifacts.

### One-shot health run

```bash
# Copy and edit the config
cp runs/health-config.local.example.json runs/health-config.local.json
# Replace placeholder contexts with your real cluster contexts

# Run health loop once
.venv/bin/python -m k8s_diag_agent.cli run-health-loop --config runs/health-config.local.json

# Print summary
k8s-diag-agent health-summary --runs-dir runs/health
```

### Containerized stack (Docker/Podman Compose)

```bash
# Place kubeconfig at podman/kubeconfig/config
# Ensure runtime configs exist under runs/

# Build and start all services
podman compose up --build -d

# Stop (artifacts persist in ./runs)
podman compose down
```

Backend: http://localhost:8080  
Frontend: http://localhost:5173

---

## Repository map

```
k9b/
├── src/k8s_diag_agent/          # Python diagnostics core
│   ├── collect/                  # Cluster snapshot collection
│   ├── normalize/                # Evidence normalization
│   ├── correlate/                # Cross-layer correlation
│   ├── reason/                   # Finding/hypothesis generation
│   ├── recommend/                # Next-check/action recommendations
│   ├── render/                   # Structured output formatting
│   ├── health/                   # Health loop and assessment
│   ├── llm/                      # LLM provider seam
│   ├── external_analysis/        # Provider-assisted flows
│   ├── security/                 # Path validation, injection detection
│   └── ui/                       # Health UI API
├── frontend/                     # React UI (Vite + TypeScript)
│   └── src/
│       ├── app/                  # App shell and routing
│       ├── components/           # UI components
│       ├── features/             # Feature modules (fleet, cluster detail, etc.)
│       ├── demo-shell/           # Demo shell state model
│       ├── components/styles/   # Theme CSS files
│       └── themes.css            # Theme definitions (dark, solarized-light, rose-pine)
├── tests/                        # Python test suite
├── evals/                        # Eval scenarios and fixtures
├── fixtures/                     # Scenario fixtures
├── runs/                         # Runtime artifacts (gitignored)
├── scripts/                      # Operational scripts
│   ├── verify_all.sh             # Canonical acceptance gate
│   ├── start_backend.sh          # Backend launcher
│   ├── start_frontend.sh         # Frontend launcher
│   ├── run_health_once.sh        # Operator quick-run wrapper
│   ├── run_health_scheduler.py   # Scheduler wrapper
│   ├── run_batch_next_checks.py  # Next-check batch executor
│   ├── verify_llm_evidence_boundaries.py
│   └── verify_llm_semantic_injection_detection.py
├── docs/
│   ├── doctrine/                 # Engineering doctrine manifests
│   ├── schemas/                  # JSON schema definitions
│   ├── security/                 # Security guidance
│   ├── data-model.md             # Artifact contracts and run lifecycle
│   ├── typing.md                 # Type annotation conventions
│   ├── logging-policy.md         # Structured logging standards
│   └── security-policy.md        # Secrets, evidence, automation boundaries
├── .kilocode/rules/              # Repo guidance
│   └── memory-bank/              # Project context files
├── charts/                       # Helm charts
└── docker/                       # Dockerfile and helpers
```

---

## Engineering doctrine

k9b follows distinctive engineering rules that keep the workbench trustworthy and evolvable:

**Evidence boundary discipline** — Raw cluster data is captured once, sanitized, and treated as immutable source of truth. LLM prompts are constructed from bounded, redacted evidence. Provider output is advisory and replayable.

**Deterministic core, optional provider branches** — Assessment, review, and proposal generation run deterministically. LLM-assisted paths (enrichment, drilldown analysis, diagnostic-pack review) are opt-in and auditable through external-analysis artifacts.

**Signal/finding/hypothesis separation** — The system never collapses observed signal, derived symptom, hypothesis, confidence, and recommended action into one opaque conclusion. Reviewers can trace how each conclusion was reached.

**Artifact-first execution** — All runs produce typed, inspectable, replayable artifacts under `runs/health/`. The UI/API are read-only projections of these artifacts, not a separate source of truth.

**LLM-friendly file discipline** — New Python files target under 300 lines (warning) or 500 lines (failure); TypeScript files follow similar limits. Large files must be justified and split.

**CSS ownership and theme isolation** — Theme tokens and raw colors stay in theme CSS files (`themes.css`, `index.css`), not in component CSS. See `docs/doctrine/css-ownership.md`.

**Safety-first automation** — The agent never mutates live clusters autonomously. All adaptations pass through `check-proposal` replay validation and explicit operator approval.

See also:
- [`.kilocode/rules/20-architecture-doctrine.md`](.kilocode/rules/20-architecture-doctrine.md)
- [`docs/doctrine/constitution.md`](docs/doctrine/constitution.md)
- [`docs/doctrine/seed_rules.md`](docs/doctrine/seed_rules.md)
- [`docs/security-policy.md`](docs/security-policy.md)

---

## LLM and safety posture

k9b treats LLM output as **advisory and reviewable**, never as automatic truth:

- **Evidence boundaries** — Evidence files are validated and redacted before provider calls. `scripts/verify_llm_evidence_boundaries.py` runs deterministic tests that require no API keys.
- **Semantic injection detection** — Deterministic local detector runs against prompt inputs. `scripts/verify_llm_semantic_injection_detection.py` verifies correct integration.
- **Provider seams are auditable** — All provider invocations write structured `ExternalAnalysisArtifact` payloads recording success/failure, latency, and structured interpretation.
- **Provenance preserved** — Every LLM-assisted output references its source artifacts so reviewers can trace back to deterministic evidence.
- **No autonomous mutation** — Proposals must pass `check-proposal` replay validation. Execution requires explicit operator approval.

These boundaries are not advisory moral guidance — they are enforced through tests, path validation, file size limits, and the artifact model itself.

---

## Development workflow

1. **Make a small scoped change** — Follow the smallest coherent fix. Preserve artifact-first behavior.
2. **Run targeted tests** — For the affected path, use the fast feedback loop:
   ```bash
   .venv/bin/python -m ruff check src tests
   .venv/bin/python -m unittest tests/unit/test_fast_feedback_smoke.py
   cd frontend && npm run test:ui
   ```
3. **Run the canonical gate** — Before claiming completion:
   ```bash
   scripts/verify_all.sh
   ```
   Work is not complete unless the gate prints `VERIFICATION GATE: PASSED`.
4. **Update docs/tests if behavior changed** — If the change affects artifact contracts, UI claims, or safety behavior, update the relevant tests and documentation.
5. **Produce a close report with verification output** — Include exact commands and results, not summaries.

### File size discipline

New Python files must stay under 300 lines (warning threshold) or 500 lines (failure threshold). Split large files rather than letting them grow indefinitely.

### Security-sensitive changes

Changes affecting static serving, artifact serving, path validation, or secrets handling require path traversal regression tests. See `docs/doctrine/path-security-doctrine.md`.

---

## Status

- **Active development** — APIs, UI, and workflows are still evolving.
- **Real-cluster/read-only operator workflows** are the primary focus.
- **Deterministic assessment/review/proposal paths** are stable and tested.
- **LLM-assisted branches** (enrichment, drilldown analysis, diagnostic-pack review) are opt-in, auditable, and do not block deterministic flows.
- **Some integrations** (llama.cpp adapter, specific LLM providers) are experimental depending on local setup.
- **Production readiness** — Do not claim production readiness without explicit evidence in the repository.

---

## License

License: not specified in this repository yet.

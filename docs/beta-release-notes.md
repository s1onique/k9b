# Beta Release Notes — k9b v0.1.0-beta (2026-05-13)

## Overview

k9b beta is a Kubernetes diagnostics agent that helps platform engineers and operators detect abnormal cluster states, surface evidence-based hypotheses, and recommend safe next diagnostic steps. The beta is designed for **evaluation and early-adopter feedback collection**, not production deployment.

This document summarizes what is included in the beta, what is intentionally out of scope, known limits, and verification status.

---

## What Is Included

### Core Diagnostics

- **Cluster state collection**: Captures sanitized snapshots via `k8s-diag-agent snapshot`, including node/pod counts, control plane version, Helm releases, and CRD definitions.
- **Peer comparison**: Compares snapshots across same-role clusters to detect suspicious drift in Helm releases, control plane versions, and CRDs.
- **Structured incident reports**: Produces typed `Assessment` artifacts with five distinguishable claim types (`observed`, `derived`, `hypothesis`, `recommendation`, `unknown`) so reviewers can trace how each conclusion was reached.
- **Worklist generation**: Generates ranked operator worklists with actionable next checks, explicit safety levels, and provenance backing each recommendation.
- **Source provenance**: Every claim includes `sourceArtifactRefs` linking to originating artifacts so recommendations are traceable.
- **Evidence freshness tracking**: Reports run freshness status (`fresh`, `delayed`, `stale`) and emits `staleEvidenceWarnings[]` when evidence may be outdated.

### Health Loop

- **`run-health-loop`**: Evaluates configured clusters independently and runs peer comparisons when triggers fire.
- **Scheduling support**: Built-in rhythm control via `--every-seconds`, `--max-runs`, and `--once` flags; optional `scripts/run_health_scheduler.py` wrapper for continuous operation.
- **Health summary**: `k8s-diag-agent health-summary --runs-dir runs/health` prints per-cluster health ratings, top findings, generated proposals, and comparison results.
- **Per-cluster history**: Persists `runs/health/history.json` for regression-aware findings across runs.

### Diagnostic Pack System

- **Pack generation**: `scripts/diagnostic_pack_review.py` produces `review_bundle.json` and `review_input_14b.json` for reviewer-friendly consumption.
- **Immutable artifacts**: Pack ZIP files and run-scoped contents are immutable once written; `latest/` mirrors are mutable convenience aliases.
- **Artifact manifest**: Every pack exposes `artifact_manifest.included_paths` for model consumption.

### Alertmanager Integration

- **Source discovery**: Discovers Alertmanager sources via `monitoring.coreos.com/v1beta1` probes and maintains a cross-run registry.
- **Source promotion/disable**: UI-driven promote/disable actions with immutable append-only action artifacts for audit trail.
- **Source state tracking**: Tracks `original_state`, `resulting_state`, and `previous_desired_state` for state transition visibility.

### Provider-Assisted Paths (Optional)

- **LLM assessment**: `k8s-diag-agent assess-snapshots` runs live comparison logic through an optional provider seam; base path is deterministic regardless of provider availability.
- **Review enrichment**: Health loop can optionally run advisory provider-assisted review enrichment after building the deterministic review artifact.
- **llama.cpp adapter**: Supports OpenAI-compatible llama.cpp deployments via `LLAMA_CPP_BASE_URL`, `LLAMA_CPP_MODEL`, and `LLAMA_CPP_API_KEY` environment variables.
- **Graceful degradation**: Provider failures do not block deterministic collection or proposal generation.

### CLI Commands

| Command | Purpose |
|---------|---------|
| `k8s-diag-agent snapshot` | Collect a live cluster snapshot |
| `k8s-diag-agent compare` | Compare two snapshot files |
| `k8s-diag-agent batch-snapshot` | Collect snapshots for configured contexts |
| `k8s-diag-agent assess-snapshots` | Run optional LLM assessment on snapshot pair |
| `k8s-diag-agent check-proposal` | Replay a health proposal against a fixture |
| `k8s-diag-agent run-health-loop` | Run per-cluster health loop |
| `k8s-diag-agent health-summary` | Print compact health run summary |
| `k8s-diag-agent health-ui` | Serve health UI backend |

### Batch Next-Check Execution

- **`scripts/run_batch_next_checks.py`**: Executes eligible next-check candidates in batch; respects `safeToAutomate`, command family validity, and approval requirements.
- **`scripts/export_next_check_usefulness_review.py`**: Exports execution results for operator review.
- **`scripts/import_next_check_usefulness_feedback.py`**: Imports reviewed feedback into execution artifacts to close the adaptation loop.

---

## Changelog Entry (Beta)

```markdown
## [0.1.0-beta] — 2026-05-13

### Added
- **Incident report claim taxonomy**: Five distinguishable claim types (`observed`, `derived`, `hypothesis`, `recommendation`, `unknown`) with explicit source provenance and confidence levels.
- **Fleet-aware drift detection**: Cross-cluster comparison of Helm releases, control plane versions, and CRDs with suspicious-drift classification.
- **Worklist generation**: Ranked operator worklists with `rankingReason` transparency, safety-level tagging, and batch execution support.
- **Evidence freshness tracking**: Run freshness status (`fresh`/`delayed`/`stale`) and `staleEvidenceWarnings[]` to prevent silent reliance on outdated evidence.
- **Diagnostic pack system**: Immutable pack ZIP files with `review_bundle.json` and `review_input_14b.json` for reviewer-friendly consumption.
- **Alertmanager source management**: Cross-run registry with promote/disable actions and append-only audit artifacts.
- **Provider-assisted enrichment**: Optional LLM review enrichment (advisory only, never authoritative) with llama.cpp adapter.
- **Health loop scheduling**: Built-in rhythm control and optional scheduler wrapper for continuous operation.
- **Per-cluster history**: Regression-aware findings powered by persisted `history.json`.
- **Feedback adaptation provenance**: Usefulness feedback loop that strengthens hypotheses without silent overwriting of diagnosis.
```

---

## Known Limits

The beta has documented limits that operators and reviewers should understand:

### Beta Guarantees (What the Beta Provides)

1. **Evidence-first reasoning**: All conclusions are grounded in deterministic artifacts with traceable `sourceArtifactRefs`.
2. **Explicit uncertainty**: Unknown evidence is surfaced as `unknown` claims with `whyMissing` explanation; confidence is reduced when gaps are significant.
3. **Separation of concerns**: Observed vs derived vs hypothesis vs recommendation vs unknown are distinguishable claim types.
4. **Operator control**: Auto-execution only applies to `safeToAutomate=true` checks with explicit approval; all high-risk actions require operator review.
5. **Artifact immutability**: Pack ZIP files and run-scoped contents are written once and not silently overwritten.

### Intentionally Deferred (Not in Beta Scope)

1. **No automatic remediation**: The beta does not apply configuration changes or remediate clusters.
2. **No root-cause proof**: The system cannot prove causality; it provides supporting evidence and hypotheses. Root-cause language requires explicit non-empty `basis` in hypothesis claims.
3. **No real-time alerting**: The system runs on configured intervals, not as a continuous alerting system.
4. **No guaranteed diagnostic completeness**: Coverage is a best-effort assessment based on collected evidence.
5. **No fleet-wide baseline coherence**: Cross-cluster reasoning requires peers with matching `cluster_class` and `cluster_role`; baseline cohorts limit drift detection scope.

### Operational Caveats

1. **Provider-assisted content is advisory**: LLM enrichment appears only in `inferences[]` with `basis: ["review-enrichment"]` and is never in `facts[]`; operators must not treat it as authoritative.
2. **Stale evidence warnings**: When freshness is `delayed` or `stale`, operators should check scheduler health before acting on evidence.
3. **Provenance filtering is conservative**: Non-useful artifacts are filtered, but minimum provenance is preserved to prevent claims without references.
4. **Cross-cluster reasoning limits**: Conclusions depend on available comparable evidence; absence of drift does not guarantee health.
5. **`latest/` mirrors are mutable**: `diagnostic-packs/latest/` is a derived convenience alias, not an immutable source of truth.

---

## Verification Status

The beta verification gate is **green** as of 2026-05-13.

### Verification Gate

```bash
scripts/verify_all.sh
```

This script runs:
- **Python lane**: ruff-lint, unit-tests, mypy
- **Frontend lane**: npm-ci, npm-test-ui, npm-build
- **Helm lane**: helm-lint, helm-template, helm-selector

Run the Python lane only for documentation-focused verification:

```bash
scripts/verify_all.sh --python-only
```

### Regression Coverage

- Incident report quality fixtures: `tests/fixtures/incident_report_fixtures.py`
- Cross-cluster findings fixtures: `tests/fixtures/incident_report_cross_cluster_fixtures.py`
- Worklist ranking rationale tests: `tests/unit/test_api_incident_report.py::WorklistRankingRationaleTests`
- Feedback adaptation provenance tests: `tests/unit/test_api_incident_report.py::FeedbackAdaptationProvenanceTests`
- Unit tests: `tests/unit/test_api_incident_report.py`

### Verification Result

- `scripts/verify_all.sh` exits 0 with `VERIFICATION GATE: PASSED`
- No known regressions in beta contract behavior

---

## Migration and Configuration Notes

### Local Config Setup

1. Copy `runs/health-config.local.example.json` → `runs/health-config.local.json` and replace placeholder contexts (`cluster-alpha`, `cluster-beta`, etc.) with real kube contexts. Keep the populated `.local` file out of git.
2. Copy `runs/run-config.local.example.json` → `runs/run-config.local.json` for feedback runs.
3. Copy `snapshots/targets.local.example.json` → `snapshots/targets.local.json` for batch snapshot collection.

### Health Config Metadata

The health config now declares:
- `cluster_class`: Logical grouping (e.g., `production`, `staging`)
- `cluster_role`: Role within class (e.g., `primary`, `secondary`)
- `baseline_cohort`: Shared upgrade baseline for drift detection eligibility

Run `scripts/inspect_health_config.py runs/health-config.local.json` to preview the metadata matrix and verify peer eligibility.

### Scheduler Usage

For continuous operation:

```bash
.venv/bin/python scripts/run_health_scheduler.py --every-seconds 300 --max-runs 48
```

The scheduler writes structured JSON events to stdout/stderr and maintains `runs/health/.health-loop.lock` to prevent overlapping runs.

### Containerized Deployment

1. Ensure runtime configs live under `runs/` (e.g., `runs/health-config.local.json`).
2. Place kubeconfig bundle under `podman/kubeconfig/config` (symlink or copy from `~/.kube/config`).
3. `podman compose up --build -d` (or `docker compose up --build -d`) to start scheduler, backend, and frontend.

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [docs/beta-operator-guide.md](beta-operator-guide.md) | Operator-facing contract, claim taxonomy, command semantics |
| [docs/beta-demo-readiness-checklist.md](beta-demo-readiness-checklist.md) | Representative scenarios, inspection steps, acceptance criteria |
| [docs/data-model.md](data-model.md) | Detailed data model, run lifecycle, artifact contracts |
| [docs/schemas/incident-report-schema.md](schemas/incident-report-schema.md) | Incident report schema specification |
| [docs/worklist-ranking-rationale.md](worklist-ranking-rationale.md) | Detailed worklist ranking logic |
| [docs/provenance-filtering.md](provenance-filtering.md) | Artifact filtering for operator trust |

---

## Feedback and Issues

Beta feedback is welcome. When reporting issues:

1. Include the run_id and relevant artifact paths from `runs/health/`.
2. Describe the expected behavior vs observed behavior.
3. If reporting a diagnostic discrepancy, include the relevant incident report or worklist item JSON.

Do not include cluster names, pod names, or other private identifiers in bug reports.
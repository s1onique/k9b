# K3s CNPG Incident Lab

## Purpose

This lab provides a canonical, reproducible environment for testing k9b's ability to detect and triage incidents in a CloudNativePG-managed PostgreSQL cluster running on K3s.

The lab is designed to:

1. Provision a K3s cluster (or connect to an existing one)
2. Deploy k9b as the diagnostic agent
3. Install the CloudNativePG operator
4. Deploy a minimal PostgreSQL cluster managed by CNPG
5. Inject a controlled, reversible incident
6. Capture diagnostic artifacts proving the incident was detected
7. Optionally exercise LLM-based triage (wired but dry-run in this scaffold ACT)

## Current Status

**This lab scaffold is now wired into CI with live K3s provisioning support.**

- The Go-based lab runner and artifact structure are implemented
- The GitHub Actions workflow builds and verifies scaffold artifacts in CI
- Live K3s provisioning in CI is available via manual `workflow_dispatch` with `run_live_lab=true`
- LLM triage integration is wired but not implemented
- Full autonomous triage loop is deferred to future ACTs

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│           GitHub Actions (workflow_dispatch + CI)                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │   Build Lab      │→ │   Run Tests      │→ │   Upload     │   │
│  │   Runner         │  │   Verify Fixtures│  │   Artifacts  │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
│                                                              │
│  ┌──────────────────┐  (only when run_live_lab=true)         │
│  │   Live K3s Lab   │→ Provision K3s → CNPG → k9b → Inject  │
│  │                  │  → Artifacts → Verify → Upload          │
│  └──────────────────┘                                         │
└─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼ (when live lab runs)
┌─────────────────────────────────────────────────────────────────┐
│                      K3s Cluster (lab)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   CNPG       │  │   k9b        │  │   PostgreSQL         │ │
│  │   Operator   │  │   Agent      │  │   Cluster            │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Artifact Directory                            │
│  lab-result.json                                                │
│  baseline/          incident/           recovery-or-final/       │
│    nodes.txt          injected-change.yaml  pods.txt            │
│    pods.txt           pods.txt           events.txt             │
│    cnpg-clusters.json events.txt         cnpg-clusters.json     │
│    k9b-status.json    cnpg-clusters.json                        │
│                      k9b-incidents.json                          │
│                      k9b-incident-detail.json                    │
│  logs/                                                             │
│    lab-runner.log                                                │
│    k3s.log (live only)                                          │
│    cnpg-operator.log (live only)                                 │
│    k9b.log (live only)                                          │
└─────────────────────────────────────────────────────────────────┘
```

## CI Workflow

### Triggers

The workflow runs on:
- **Manual dispatch**: `workflow_dispatch` with configurable inputs
  - `artifact_retention_days`: Number of days to keep CI artifacts (default: 7)
  - `run_live_lab`: Whether to run live K3s provisioning (default: false)
  - `incident_scenario`: Which incident scenario to run (default: pod-failure)
- **PR**: When lab-related files change (workflow, Go code, Python verifier, fixtures)
- **Push to main**: When lab-related files change

**Important**: Live K3s provisioning only runs when `run_live_lab=true` is explicitly set in manual dispatch. PR/push runs only build-and-verify.

### CI Jobs

#### build-and-verify Job

The `build-and-verify` job always runs:
1. Builds the Go lab runner (`dist/k9b-cnpg-incident-lab`)
2. Runs Go unit tests for `internal/lab/cnpg`
3. Runs Python verifier tests
4. Verifies passing fixture (`fixtures/lab/pass`)
5. Verifies failing fixtures fail for intended reasons
6. Uploads build outputs and verification logs as artifacts

#### live-k3s-lab Job

The `live-k3s-lab` job runs **only** when manually requested (`run_live_lab=true`):
1. Depends on `build-and-verify` completing successfully
2. Provisions a real K3s cluster on the runner
3. Installs the real CloudNativePG operator from official manifest
4. Deploys a minimal CNPG PostgreSQL cluster
5. Deploys the k9b agent
6. Injects the `pod-failure` incident scenario
7. Collects live artifacts
8. Verifies artifacts with the existing verifier
9. Uploads live lab artifacts with distinct naming

### Build Commands

```bash
# Sync workspace and build
go work sync
go build -o dist/k9b-cnpg-incident-lab ./cmd/k9b-cnpg-incident-lab

# Run Go tests
go test -v ./internal/lab/cnpg/...

# Run Python verifier tests
.venv/bin/python -m pytest tests/test_verify_k3s_cnpg_incident_lab.py -v
```

## How to Run

### Manual Execution (Local)

Prerequisites:
- K3s cluster accessible via `kubectl`
- `KUBECONFIG` environment variable set
- Go 1.25+ installed

```bash
# Build the lab runner (requires go.work workspace)
go work sync
go build -o dist/k9b-cnpg-incident-lab ./cmd/k9b-cnpg-incident-lab

# Run the incident lab against an existing cluster.
make lab-k9b-cnpg-incident-live KUBECONFIG=/path/to/kubeconfig SCENARIO=pod-failure

# Verify artifacts.
make verify-lab-k9b-cnpg-incident-live ARTIFACT_DIR=./lab-artifacts/live
```

### GitHub Actions (Manual Dispatch)

1. Navigate to **Actions** → **K3s CNPG Incident Lab**
2. Click **Run workflow**
3. Configure inputs:
   - `artifact_retention_days`: Number of days to keep CI artifacts (default: 7)
   - `run_live_lab`: Set to `true` to run live K3s provisioning (default: false)
   - `incident_scenario`: Choose incident scenario (default: pod-failure)
4. Click **Run workflow**

**Example**: Running with live K3s:
- Set `run_live_lab` to `true`
- Set `incident_scenario` to `pod-failure`
- The workflow will provision K3s, install CNPG, deploy k9b, inject the incident, and verify artifacts

### GitHub Actions (CI)

The workflow automatically runs on:
- PRs that modify lab-related files
- Pushes to main that modify lab-related files

No manual configuration required for CI runs. Live K3s is **not** run automatically.

### Artifact Verification (Local)

```bash
# Verify passing fixture.
make verify-lab-fixture-pass

# Verify fail fixture (missing k9b incident).
make verify-lab-fixture-fail-no-incident

# Verify fail fixture (secret leakage).
make verify-lab-fixture-fail-secret

# Verify live lab artifacts.
make verify-lab-k9b-cnpg-incident-live ARTIFACT_DIR=./lab-artifacts/live
```

## Pinned Versions

| Component | Version | Manifest URL |
|-----------|---------|--------------|
| K3s | v1.31.0+k3s1 | https://get.k3s.io |
| CNPG Operator | 1.26.0 | https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/v1.26.0/releases/cnpg-1.26.0.yaml |
| PostgreSQL | 17.5 | ghcr.io/cloudnative-pg/postgresql:17.5 |
| k9b | 0.1.0 | ghcr.io/s1onique/k9b:v0.1.0 |

## Live Lab Artifact Upload

Live lab artifacts are uploaded with a distinct name:
```
k9b-cnpg-incident-lab-live-{run_id}
```

This distinguishes them from build-and-verify artifacts:
```
k9b-cnpg-incident-lab-ci-{run_id}
```

## Required Secrets

| Secret | Required For | Notes |
|--------|-------------|-------|
| `OPENROUTER_API_KEY` | LLM triage | Only needed if `enable_llm_triage=true` |

The CI workflow does NOT require:
- Kubernetes credentials (kubeconfig is generated by K3s)
- CNPG credentials (lab uses ephemeral test secrets)
- Any other secrets for the scaffold implementation

**Secret Hygiene**: The live lab explicitly avoids uploading:
- kubeconfig contents
- service account tokens
- generated database passwords
- OpenRouter keys
- GitHub tokens
- bearer tokens
- private keys
- full Secret resources

## Incident Scenarios

### pod-failure (Current)

**Description**: Induce a pod failure by adding a failing readiness probe.

**Mechanism**:
1. Wait for CNPG cluster to reach healthy state
2. Either:
   - Patch the CNPG PostgreSQL pod with a failing readiness probe (`/bin/false`), OR
   - Create a lab-owned app pod with a failing readiness probe (fallback)
3. Wait for the pod to enter `NotReady` state
4. Observe k9b incident detection (deferred to future ACT)

**Expected Symptom**: Pod reports NotReady, k9b detects incident (when implemented).

**Recovery**: CNPG self-heals or pod is deleted.

**Safety**: Non-destructive, reversible, no data loss (single-pod test cluster).

## Artifact Schema

### lab-result.json

```json
{
  "ok": true,
  "scenario": "pod-failure",
  "started_at": "2026-06-16T10:00:00Z",
  "finished_at": "2026-06-16T10:15:00Z",
  "cluster_mode": "provision",
  "k3s_version": "v1.31.0+k3s1",
  "cnpg_operator_version": "1.26.0",
  "k9b_version": "0.1.0",
  "incident_detected": false,
  "incident_id": null,
  "artifact_dir": "/path/to/artifacts",
  "failure_reason": "k9b live detection deferred - incident lab infrastructure proven",
  "llm_triage_enabled": false,
  "llm_triage_attempted": false,
  "llm_triage_artifact": null
}
```

### Directory Structure

```
artifact-dir/
├── lab-result.json           # Lab outcome and metadata
├── baseline/                 # Pre-incident cluster state
│   ├── nodes.txt             # kubectl get nodes -o wide
│   ├── nodes.json            # Structured node data
│   ├── pods.txt              # kubectl get pods -o wide
│   ├── events.txt            # kubectl get events (live only)
│   ├── cnpg-clusters.json    # CNPG operator/cluster status
│   └── k9b-status.json       # k9b agent status
├── incident/                 # Post-injection cluster state
│   ├── injected-change.yaml  # The manifest that caused the incident
│   ├── pods.txt              # Pod status during incident
│   ├── events.txt            # Kubernetes events during incident
│   ├── cnpg-clusters.json    # CNPG status during incident
│   ├── cnpg-cluster.yaml     # CNPG cluster manifest (live only)
│   ├── describe-pods.txt     # Detailed pod descriptions (live only)
│   ├── k9b-incidents.json    # k9b detected incidents
│   └── k9b-incident-detail.json  # Detailed incident info
├── recovery-or-final/        # Post-recovery or final state
│   ├── pods.txt
│   ├── events.txt
│   └── cnpg-clusters.json
└── logs/
    ├── lab-runner.log        # Timestamped lab execution log
    ├── k3s.log               # K3s journal logs (live only)
    ├── cnpg-operator.log     # CNPG operator logs (live only)
    └── k9b.log               # k9b agent logs (live only)
```

## Safety Boundaries

1. **No production data**: Lab uses ephemeral storage and test credentials
2. **Reversible incidents**: All incidents have documented recovery steps
3. **No node-level operations**: No destructive node behavior
4. **No external dependencies**: All components are self-contained (except K3s)
5. **Secret hygiene**: API keys and tokens never logged or included in artifacts
6. **CI-only live runs**: Live K3s only runs when explicitly requested

## Current Limitations

1. **k9b live detection deferred**: Full k9b incident detection against live CNPG deferred to future ACT
2. **No LLM triage implementation**: OpenRouter wiring exists but calls are no-ops
3. **Single scenario**: Only `pod-failure` is implemented
4. **No autonomous loop**: Full multi-pass diagnosis is deferred
5. **Timing dependencies**: Uses sleeps instead of proper condition waits in some places
6. **CNPG CRD assumptions**: Assumes k9b Incident CRD exists (not implemented in scaffold)
7. **Intentionally workspace-built**: The lab runner requires `go.work` and cannot be built outside the workspace (e.g., `GOWORK=off go build` will fail). This is expected behavior for a nested module scaffold.

## Next ACTs (Deferred)

1. **ACT 2**: k9b live incident detection against CNPG cluster
2. **ACT 3**: LLM triage integration with OpenRouter
3. **ACT 4**: Additional incident scenarios (connection blocked, PVC failure, etc.)
4. **ACT 5**: Autonomous multi-pass diagnosis loop
5. **ACT 6**: Result comparison and triage quality scoring

## CI / Testing

Lab tests run automatically in GitHub Actions CI on PR/push when lab files change.

```bash
# Run Go unit tests for lab package.
go test -v ./internal/lab/cnpg/...

# Python verifier tests run in CI via pytest
make test-lab

# Local verification
./scripts/verify_all.sh --act-local
```

## Files Changed

| File | Purpose |
|------|---------|
| `cmd/k9b-cnpg-incident-lab/main.go` | Lab runner entrypoint |
| `internal/lab/cnpg/config.go` | Configuration types and validation |
| `internal/lab/cnpg/artifacts.go` | Artifact writing and secret detection |
| `internal/lab/cnpg/k3s.go` | K3s cluster client and provisioning |
| `internal/lab/cnpg/cnpg.go` | CloudNativePG operator and cluster management |
| `internal/lab/cnpg/k9b.go` | k9b deployment and incident detection |
| `internal/lab/cnpg/incident.go` | Incident scenario definitions |
| `internal/lab/cnpg/runner.go` | Main lab orchestration |
| `internal/lab/cnpg/config_test.go` | Go unit tests |
| `.github/workflows/k9b-cnpg-incident-lab.yml` | CI workflow (build-and-verify + live K3s) |
| `go.work` | Go workspace for local CI builds |
| `scripts/verify_k3s_cnpg_incident_lab_artifact.py` | Artifact verifier |
| `tests/test_verify_k3s_cnpg_incident_lab.py` | Verifier unit tests |
| `fixtures/lab/pass/` | Passing fixture for verifier tests |
| `fixtures/lab/fail-no-incident/` | Fail fixture (missing k9b incident) |
| `fixtures/lab/fail-secret/` | Fail fixture (secret leakage) |
| `Makefile` | Lab targets including live lab |
| `docs/labs/k3s-cnpg-incident-lab.md` | This documentation |

## Verification

```bash
# Verify artifact fixture passes.
.venv/bin/python scripts/verify_k3s_cnpg_incident_lab_artifact.py \
  --artifact-dir fixtures/lab/pass

# Verify fail fixture fails as expected.
.venv/bin/python scripts/verify_k3s_cnpg_incident_lab_artifact.py \
  --artifact-dir fixtures/lab/fail-no-incident
# Expected: exit code 1, mentions missing k9b-incidents.json

# Verify secret fixture fails as expected.
.venv/bin/python scripts/verify_k3s_cnpg_incident_lab_artifact.py \
  --artifact-dir fixtures/lab/fail-secret
# Expected: exit code 1, mentions password/secret detection

# Verify live lab artifacts (after running live lab).
make verify-lab-k9b-cnpg-incident-live ARTIFACT_DIR=./lab-artifacts/live
```

## Commit Information

- **ACT Type**: Live K3s provisioning in CI (infrastructure proven, k9b detection deferred)
- **Scenario**: pod-failure
- **OpenRouter**: Wired, not called
- **Workflow**: `.github/workflows/k9b-cnpg-incident-lab.yml`
- **Trigger mode**: workflow_dispatch + path-scoped PR/push
- **Live K3s trigger**: workflow_dispatch with run_live_lab=true
- **Go module/workspace strategy**: go.work with local workspace
- **CI build command**: `go work sync && go build -o dist/k9b-cnpg-incident-lab ./cmd/k9b-cnpg-incident-lab`
- **CI test command**: `go test -v ./internal/lab/cnpg/...` + pytest (via `make test-lab`)
- **Artifact upload names**:
  - Build-and-verify: `k9b-cnpg-incident-lab-ci-{run_id}`
  - Live lab: `k9b-cnpg-incident-lab-live-{run_id}`
- **K3s version**: v1.31.0+k3s1
- **CNPG operator version**: 1.26.0
- **Live K3s execution**: Available via manual dispatch with run_live_lab=true
- **k9b live detection**: Deferred to future ACT

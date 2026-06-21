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

**This lab scaffold is now wired into CI.** The GitHub Actions workflow builds and verifies the lab artifacts on every PR and push.

- The Go-based lab runner and artifact structure are implemented
- The GitHub Actions workflow builds and verifies scaffold artifacts in CI
- Live K3s provisioning in CI is not yet functional (deferred to future ACT)
- LLM triage integration is wired but not implemented
- Full autonomous triage loop is deferred to future ACTs

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│               GitHub Actions (workflow_dispatch + CI)            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │   Build Lab      │→ │   Run Tests      │→ │   Upload     │   │
│  │   Runner         │  │   Verify Fixtures│  │   Artifacts  │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼ (future ACT)
┌─────────────────────────────────────────────────────────────────┐
│                      K3s Cluster (lab)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │   CNPG       │  │   k9b        │  │   PostgreSQL         │   │
│  │   Operator   │  │   Agent      │  │   Cluster            │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
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
└─────────────────────────────────────────────────────────────────┘
```

## CI Workflow

### Triggers

The workflow runs on:
- **Manual dispatch**: `workflow_dispatch` with artifact retention input
- **PR**: When lab-related files change (workflow, Go code, Python verifier, fixtures)
- **Push to main**: When lab-related files change

### CI Jobs

The `build-and-verify` job:
1. Builds the Go lab runner (`dist/k9b-cnpg-incident-lab`)
2. Runs Go unit tests for `internal/lab/cnpg`
3. Runs Python verifier tests
4. Verifies passing fixture (`fixtures/lab/pass`)
5. Verifies failing fixtures fail for intended reasons
6. Uploads build outputs and verification logs as artifacts

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

# Run the incident lab.
make run-lab KUBECONFIG=/path/to/kubeconfig SCENARIO=pod-failure

# Verify artifacts.
make verify-lab-k9b-cnpg-incident ARTIFACT_DIR=./lab-artifacts
```

### GitHub Actions (Manual Dispatch)

1. Navigate to **Actions** → **K3s CNPG Incident Lab**
2. Click **Run workflow**
3. Configure inputs:
   - `artifact_retention_days`: Number of days to keep CI artifacts (default: 7)
4. Click **Run workflow**

### GitHub Actions (CI)

The workflow automatically runs on:
- PRs that modify lab-related files
- Pushes to main that modify lab-related files

No manual configuration required for CI runs.

### Artifact Verification (Local)

```bash
# Verify passing fixture.
make verify-lab-fixture-pass

# Verify fail fixture (missing k9b incident).
make verify-lab-fixture-fail-no-incident

# Verify fail fixture (secret leakage).
make verify-lab-fixture-fail-secret
```

## Required Secrets

| Secret | Required For | Notes |
|--------|-------------|-------|
| `OPENROUTER_API_KEY` | LLM triage | Only needed if `enable_llm_triage=true` |

The CI workflow does NOT require:
- Kubernetes credentials (no live K3s in CI yet)
- CNPG credentials (lab uses ephemeral test secrets)
- Any other secrets for the scaffold implementation

## Incident Scenarios

### pod-failure (Current)

**Description**: Induce a CNPG pod failure by patching the PostgreSQL pod's readiness probe to always fail.

**Mechanism**:
1. Wait for CNPG cluster to reach healthy state
2. Patch the StatefulSet to add a failing readiness probe (`/bin/false`)
3. Wait for the pod to enter `NotReady` state
4. Observe k9b incident detection

**Expected Symptom**: CNPG reports unhealthy cluster, k9b detects Pod NotReady incident.

**Recovery**: Remove the failing readiness probe by patching with `null`. CNPG self-heals the pod.

**Safety**: Non-destructive, reversible, no data loss (single-pod test cluster).

## Artifact Schema

### lab-result.json

```json
{
  "ok": true,
  "scenario": "pod-failure",
  "started_at": "2026-06-16T10:00:00Z",
  "finished_at": "2026-06-16T10:15:00Z",
  "cluster_mode": "local",
  "k3s_version": "v1.31.0+k3s1",
  "cnpg_operator_version": "1.26.0",
  "k9b_version": "0.1.0",
  "incident_detected": true,
  "incident_id": "inc-pod-failure-001",
  "artifact_dir": "/path/to/artifacts",
  "failure_reason": null,
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
│   ├── cnpg-clusters.json    # CNPG operator/cluster status
│   └── k9b-status.json       # k9b agent status
├── incident/                 # Post-injection cluster state
│   ├── injected-change.yaml  # The manifest that caused the incident
│   ├── pods.txt              # Pod status during incident
│   ├── events.txt            # Kubernetes events during incident
│   ├── cnpg-clusters.json    # CNPG status during incident
│   ├── k9b-incidents.json    # k9b detected incidents
│   └── k9b-incident-detail.json  # Detailed incident info
├── recovery-or-final/        # Post-recovery or final state
│   ├── pods.txt
│   ├── events.txt
│   └── cnpg-clusters.json
└── logs/
    └── lab-runner.log        # Timestamped lab execution log
```

## Safety Boundaries

1. **No production data**: Lab uses ephemeral storage and test credentials
2. **Reversible incidents**: All incidents have documented recovery steps
3. **No node-level operations**: No destructive node behavior
4. **No external dependencies**: All components are self-contained (except K3s)
5. **Secret hygiene**: API keys and tokens never logged or included in artifacts

## Current Limitations

1. **No live K3s provisioning**: CI builds and verifies artifacts but does not provision K3s
2. **No LLM triage implementation**: OpenRouter wiring exists but calls are no-ops
3. **Single scenario**: Only `pod-failure` is implemented
4. **No autonomous loop**: Full multi-pass diagnosis is deferred
5. **Timing dependencies**: Uses sleeps instead of proper condition waits in some places
6. **CNPG CRD assumptions**: Assumes k9b Incident CRD exists
7. **Intentionally workspace-built**: The lab runner requires `go.work` and cannot be built outside the workspace (e.g., `GOWORK=off go build` will fail). This is expected behavior for a nested module scaffold.

## Next ACTs (Deferred)

1. **ACT 2**: Live K3s provisioning in CI (KinD or k3s-in-Docker)
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
| `.github/workflows/k9b-cnpg-incident-lab.yml` | CI workflow (build-and-verify) |
| `go.work` | Go workspace for local CI builds |
| `scripts/verify_k3s_cnpg_incident_lab_artifact.py` | Artifact verifier |
| `tests/test_verify_k3s_cnpg_incident_lab.py` | Verifier unit tests |
| `fixtures/lab/pass/` | Passing fixture for verifier tests |
| `fixtures/lab/fail-no-incident/` | Fail fixture (missing k9b incident) |
| `fixtures/lab/fail-secret/` | Fail fixture (secret leakage) |
| `Makefile` | Lab targets |
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
```

## Commit Information

- **ACT Type**: CI-wired (not live-lab-proven)
- **Scenario**: pod-failure
- **OpenRouter**: Wired, dry-run only
- **Workflow**: `.github/workflows/k9b-cnpg-incident-lab.yml`
- **Trigger mode**: workflow_dispatch + path-scoped PR/push
- **Go module/workspace strategy**: go.work with local workspace
- **CI build command**: `go work sync && go build -o dist/k9b-cnpg-incident-lab ./cmd/k9b-cnpg-incident-lab`
- **CI test command**: `go test -v ./internal/lab/cnpg/...` + pytest (via `make test-lab`)
- **Artifact upload name**: `k9b-cnpg-incident-lab-ci-{run_id}`
- **Live K3s execution**: Deferred to future ACT
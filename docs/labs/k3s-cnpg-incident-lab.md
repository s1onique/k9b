# K3s CNPG Incident Lab

## Purpose

This lab provides a canonical, reproducible environment for testing k9b's ability to detect and triage incidents in a CloudNativePG-managed PostgreSQL cluster running on K3s.

The lab is designed to:

1. Provision a K3s cluster (or connect to an existing one)
2. Build the current k9b container image from the repository checkout
3. Import the image into K3s containerd runtime
4. Deploy k9b via the project Helm chart with chart image overrides
5. Install the CloudNativePG operator
6. Deploy a minimal PostgreSQL cluster managed by CNPG
7. Inject a controlled, reversible incident using a tracked manifest
8. Capture diagnostic artifacts proving the incident was detected
9. Optionally exercise LLM-based triage (wired but dry-run in this scaffold ACT)

## Current Status

**This lab scaffold builds k9b from current checkout and deploys via Helm chart.**

- The Go-based lab runner and artifact structure are implemented
- The GitHub Actions workflow builds a fresh k9b image from current checkout
- The image is imported into K3s containerd for local use
- k9b is deployed via the project Helm chart with image value overrides
- Live K3s provisioning in CI is available via manual `workflow_dispatch` with `run_live_lab=true`
- Incident manifests are tracked in the repository, not embedded in workflows
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
│  │   Live K3s Lab   │→ Build Image → Import → Helm → Inject  │
│  │                  │  → Artifacts → Verify → Upload          │
│  └──────────────────┘                                         │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ (when live lab runs)
┌─────────────────────────────────────────────────────────────────┐
│                      K3s Cluster (lab)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   CNPG       │  │   k9b        │  │   PostgreSQL         │ │
│  │   Operator   │  │   (Helm)     │  │   Cluster            │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Artifact Directory                            │
│  lab-result.json                                                │
│  baseline/          incident/           recovery-or-final/         │
│    nodes.txt          injected-change.yaml  pods.txt            │
│    pods.txt           pods.txt           events.txt             │
│    cnpg-clusters.json events.txt         cnpg-clusters.json     │
│    k9b-status.json    cnpg-clusters.json                        │
│    k9b-all.txt        k9b-incidents.json                        │
│    k9b-describe.txt   k9b-incident-detail.json                  │
│    k9b-pods.json                                                   │
│  logs/                                                             │
│    lab-runner.log                                                │
│    k3s.log (live only)                                          │
│    cnpg-operator.log (live only)                                 │
│    k9b.log (live only)                                          │
│    helm-k9b-status.txt (live only)                              │
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
2. Builds a fresh k9b container image from the current checkout using `Dockerfile.python`
3. Imports the image into K3s containerd runtime
4. Provisions a real K3s cluster on the runner
5. Installs the real CloudNativePG operator from official manifest
6. Deploys a minimal CNPG PostgreSQL cluster
7. Sets up Helm
8. Deploys k9b via the project Helm chart (`./charts/k9b`) with image overrides:
   - `image.backend.repository=k9b-lab`
   - `image.backend.tag=${GITHUB_SHA}`
   - `image.backend.pullPolicy=Never`
   - `backend.auth.enabled=false`
9. Asserts that k9b pods use the run-built image (fatal check)
10. Injects the `pod-failure` incident using a tracked manifest (`fixtures/lab/live/pod-failure/injected-change.yaml`)
11. Verifies the incident symptom (pod should be NotReady)
12. Collects live artifacts including Helm release status
13. Verifies artifacts with the existing verifier
14. Uploads live lab artifacts with distinct naming

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
- Docker installed (for building k9b image)

```bash
# Build the lab runner (requires go.work workspace)
go work sync
go build -o dist/k9b-cnpg-incident-lab ./cmd/k9b-cnpg-incident-lab

# Build k9b image locally (for local lab testing)
docker build -f Dockerfile.python -t k9b-lab:local .

# Import image into K3s (if using local K3s)
docker save k9b-lab:local | sudo k3s ctr images import -

# Install Helm chart with local image
helm upgrade --install k9b ./charts/k9b \
  --namespace k9b \
  --create-namespace \
  --set image.backend.repository="k9b-lab" \
  --set image.backend.tag="local" \
  --set image.backend.pullPolicy=Never \
  --set backend.auth.enabled=false

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
- The workflow will build k9b from checkout, import into K3s, deploy via Helm, inject the incident, and verify artifacts

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
| Helm | 3.16.3 | azure/setup-helm@v4 |
| k9b | `${GITHUB_SHA}` (built from checkout) | Built from `Dockerfile.python` |

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
- Container registry credentials (image is built locally and imported)
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

**Description**: Deploy a lab-owned failing app pod with a deterministic failing readiness probe.

**Mechanism**:
1. Apply the tracked manifest: `fixtures/lab/live/pod-failure/injected-change.yaml`
2. The manifest creates a Pod named `cnpg-lab-failing-app` in the `cnpg-lab` namespace
3. The pod has a readiness probe that always fails (`/bin/false`)
4. The pod remains in `Running` phase but `NotReady` condition
5. Observe k9b incident detection (deferred to future ACT)

**Expected Symptom**: Pod reports NotReady, k9b detects incident (when implemented).

**Recovery**: Delete the pod.

**Safety**: Non-destructive, reversible, no data loss (single-pod test cluster, not CNPG internal mutation).

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
  "k9b_version": "605cda253d90029b57965292d8127be22efab248",
  "k9b_image_repository": "k9b-lab",
  "k9b_image_tag": "605cda253d90029b57965292d8127be22efab248",
  "incident_detected": false,
  "incident_id": null,
  "artifact_dir": "/path/to/artifacts",
  "failure_reason": "k9b live detection deferred",
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
│   ├── k9b-status.json       # Helm release status
│   ├── k9b-all.txt           # kubectl get all -n k9b
│   ├── k9b-describe.txt      # kubectl describe deployment -n k9b
│   └── k9b-pods.json          # kubectl get pods -n k9b -o json
├── incident/                 # Post-injection cluster state
│   ├── injected-change.yaml  # The tracked manifest that caused the incident
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
    ├── k9b.log               # k9b agent logs (live only)
    └── helm-k9b-status.txt   # Helm release status (live only)
```

## Safety Boundaries

1. **No production data**: Lab uses ephemeral storage and test credentials
2. **Reversible incidents**: All incidents have documented recovery steps
3. **No node-level operations**: No destructive node behavior
4. **No external dependencies**: All components are self-contained (except K3s)
5. **Secret hygiene**: API keys and tokens never logged or included in artifacts
6. **CI-only live runs**: Live K3s only runs when explicitly requested
7. **Lab-owned workloads**: Incident manifests create separate lab workloads, not CNPG internal mutations

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
| `.github/workflows/k9b-cnpg-incident-lab-live.yml` | Live workflow with Docker build, Helm deploy |
| `go.work` | Go workspace for local CI builds |
| `scripts/verify_k3s_cnpg_incident_lab_artifact.py` | Artifact verifier |
| `tests/test_verify_k3s_cnpg_incident_lab.py` | Verifier unit tests |
| `tests/test_live_lab_config.py` | Live lab config tests (Docker build, Helm deploy, etc.) |
| `fixtures/lab/live/pod-failure/injected-change.yaml` | Tracked incident manifest |
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

- **ACT Type**: Product-faithful k9b deployment via Helm chart (no hardcoded image, tracked incident manifest)
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
- **Helm version**: 3.16.3
- **k9b image**: Built from current checkout via `Dockerfile.python`, tagged with `${GITHUB_SHA}`
- **Image import**: `docker save k9b-lab:${SHA} | sudo k3s ctr images import -`
- **Helm deployment**: `helm upgrade --install k9b ./charts/k9b --set image.backend.repository=k9b-lab --set image.backend.tag=${SHA} --set image.backend.pullPolicy=Never`
- **Incident manifest**: `fixtures/lab/live/pod-failure/injected-change.yaml` (tracked in repo)
- **k9b live detection**: Deferred to future ACT

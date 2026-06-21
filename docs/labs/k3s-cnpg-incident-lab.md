# K3s CNPG Incident Lab

## Purpose

This lab provides a canonical, reproducible environment for testing k9b's ability to detect and triage incidents in a CloudNativePG-managed PostgreSQL cluster running on K3s.

The lab is designed to run in **existing-cluster namespace mode**, where:
- The GitHub Actions runner runs inside the target K3s cluster
- CloudNativePG is already preinstalled in `cnpg-system`
- Harbor is already running in-cluster
- k9b images are built by the canonical Harbor image-build workflow and consumed by the lab

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
│  │   Build Lab      │→ k9b-image-builder (Harbor) → Deploy   │
│  │   Images         │  via Helm → Inject → Artifacts → Upload  │
│  └──────────────────┘                                         │
└─────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ (when live lab runs)
┌─────────────────────────────────────────────────────────────────┐
│                 Existing K3s Cluster (self-hosted runner)          │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  GitHub Actions Runner (in-cluster)                       │ │
│  │  ┌────────────────────────────────────────────────────┐ │ │
│  │  │  k9b-cnpg-incident-lab-live.yml                     │ │ │
│  │  │  - Preflights existing CNPG operator                │ │ │
│  │  │  - Creates unique lab namespace                     │ │ │
│  │  │  - Deploys k9b via Helm (consumes Harbor image)     │ │ │
│  │  │  - Deploys CNPG Cluster in lab namespace           │ │ │
│  │  │  - Injects incident, collects artifacts             │ │ │
│  │  └────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   CNPG       │  │   k9b        │  │   PostgreSQL         │ │
│  │   Operator   │  │   (Helm)     │  │   Cluster            │ │
│  │   (existing) │  │   (lab ns)   │  │   (lab ns)          │ │
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
│    cnpg-operator-preflight.txt                                   │
│    k9b.log (live only)                                          │
│    helm-k9b-status.txt (live only)                              │
│    k9b-images.txt (live only)                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Existing-Cluster Namespace Mode

The lab was converted from nested K3s provisioning to existing-cluster namespace mode because:

1. **GitHub Actions runners already run inside the target K3s cluster** - No need to provision a nested K3s
2. **CloudNativePG is preinstalled** - No need to install the CNPG operator
3. **Harbor is available in-cluster** - Images are built by the canonical workflow and pushed to Harbor
4. **No Docker socket in runner pods** - Cannot build images in the live workflow

### Image-Builder Ownership

The canonical `k9b-image-builder.yml` workflow owns:
- Harbor registry/project conventions
- Harbor authentication
- BuildKit/rootless build implementation
- Image tags, digests, build cache settings
- CA trust for Harbor
- Build-platform settings

The live lab workflow **only consumes** image outputs and must not contain:
- `docker build` / `docker push` / `docker save`
- `/var/run/docker.sock`
- `buildctl` / `buildctl-daemonless.sh`
- Harbor auth material construction
- Registry password handling

## CI Workflow

### Triggers

The workflow runs on:
- **Manual dispatch**: `workflow_dispatch` with configurable inputs
  - `artifact_retention_days`: Number of days to keep CI artifacts (default: 7)
  - `run_live_lab`: Whether to run live namespace-mode lab (default: false)
  - `incident_scenario`: Which incident scenario to run (default: pod-failure)
- **PR**: When lab-related files change (workflow, Go code, Python verifier, fixtures)
- **Push to main**: When lab-related files change

**Important**: Live lab only runs when `run_live_lab=true` is explicitly set in manual dispatch.

### CI Jobs

#### build-and-verify Job

The `build-and-verify` job runs on `ubuntu-latest` and:
1. Builds the Go lab runner (`dist/k9b-cnpg-incident-lab`)
2. Runs Go unit tests for `internal/lab/cnpg`
3. Runs Python verifier tests
4. Verifies passing fixture (`fixtures/lab/pass`)
5. Verifies failing fixtures fail for intended reasons
6. Uploads build outputs and verification logs as artifacts

#### build-lab-images Job (only when live lab requested)

The `build-lab-images` job:
1. Calls the reusable `k9b-image-builder.yml` workflow
2. Builds and pushes k9b backend/frontend images to Harbor
3. Exposes image repository/tag/ref/digest as outputs

#### live-k3s-lab Job (only when live lab requested)

The `live-k3s-lab` job runs on self-hosted runner with cluster access and:
1. Preflights existing cluster access
2. Preflights existing CNPG operator/CRD
3. Creates unique lab namespace (`k9b-cnpg-lab-${GITHUB_RUN_ID}`)
4. Deploys k9b via Helm chart using image-builder outputs
5. Asserts k9b pod image matches image-builder output
6. Deploys CNPG Cluster in lab namespace
7. Injects pod-failure incident using tracked manifest
8. Verifies incident symptom (pod NotReady)
9. Collects artifacts and runs verifier
10. Cleans up lab namespace (always runs)
11. Uploads artifacts

## Required Runner Scale Sets

The lab uses two distinct ARC runner scale sets:

| Runner Scale Set | Purpose | Docker/Buildx |
|-----------------|---------|---------------|
| `spbnix-k8s-docker` | Image-builder workflow only | Required |
| `spbnix-k8s` | Live namespace lab workflow | Not needed |

### Image-Builder Runner: `spbnix-k8s-docker`

The `k9b-image-builder.yml` reusable workflow runs on `spbnix-k8s-docker`:

```yaml
runs-on: spbnix-k8s-docker
```

This runner scale set has Docker/Buildx capability for:
- Building multi-arch images (linux/amd64, linux/arm64)
- Pushing to Harbor registry
- Running QEMU for cross-arch builds

### Live Lab Runner: `spbnix-k8s`

The `k9b-cnpg-incident-lab-live.yml` workflow runs on `spbnix-k8s`:

```yaml
runs-on: spbnix-k8s
```

This runner scale set provides:
- Cluster access via in-cluster service account
- kubectl, Helm, Python
- CNPG operator visibility in `cnpg-system`
- Harbor access for image pulls

**Important**: The live lab does not need Docker and must not run on the Docker builder scale set.

## Required CNPG Operator Prerequisite

The lab requires the CloudNativePG operator to be preinstalled:

```bash
kubectl get crd clusters.postgresql.cnpg.io
kubectl get pods -n cnpg-system
kubectl get deployments -n cnpg-system
```

If CNPG CRD/operator is missing, the lab fails with:
```
Existing CNPG operator/CRD not found; namespace-mode lab requires preinstalled CNPG.
```

## Incident Scenarios

### pod-failure (Current)

**Description**: Deploy a lab-owned failing app pod with a deterministic failing readiness probe.

**Mechanism**:
1. Apply the tracked manifest: `fixtures/lab/live/pod-failure/injected-change.yaml`
2. The manifest creates a Pod named `cnpg-lab-failing-app` in the lab namespace
3. The pod has a readiness probe that always fails (`/bin/false`)
4. The pod remains in `Running` phase but `NotReady` condition
5. k9b incident detection is deferred to future ACT

**Expected Symptom**: Pod reports NotReady, k9b detects incident (when implemented).

**Recovery**: Delete the pod.

**Safety**: Non-destructive, reversible, no data loss.

## Artifact Schema

### lab-result.json (Namespace Mode)

```json
{
  "ok": true,
  "scenario": "pod-failure",
  "started_at": "2026-06-21T20:00:00Z",
  "finished_at": "2026-06-21T20:15:00Z",
  "cluster_mode": "existing",
  "runner_mode": "self-hosted",
  "cnpg_operator_mode": "existing",
  "lab_namespace": "k9b-cnpg-lab-123456",
  "k9b_image_repository": "harbor-pve1.spbnix.local/k9b/k9b-backend",
  "k9b_image_tag": "c29014919519ed1fa1a0d12aadf291f23f932fa2",
  "k9b_image_ref": "harbor-pve1.spbnix.local/k9b/k9b-backend:c29014919519ed1fa1a0d12aadf291f23f932fa2",
  "k9b_image_digest": "sha256:...",
  "incident_detected": false,
  "artifact_dir": "./lab-artifacts/live",
  "failure_reason": "k9b live detection deferred",
  "llm_triage_enabled": false,
  "llm_triage_attempted": false
}
```

### Directory Structure

```
artifact-dir/
├── lab-result.json           # Lab outcome and metadata
├── baseline/                 # Pre-incident cluster state
│   ├── nodes.txt             # kubectl get nodes -o wide
│   ├── pods.txt              # kubectl get pods -n <lab_ns> -o wide
│   ├── events.txt            # kubectl get events -n <lab_ns>
│   ├── cnpg-clusters.json    # CNPG operator/cluster status
│   ├── k9b-status.json       # Helm release status
│   ├── k9b-all.txt           # kubectl get all -n <lab_ns>
│   ├── k9b-describe.txt     # kubectl describe deployment -n <lab_ns>
│   └── k9b-pods.json         # kubectl get pods -n <lab_ns> -o json
├── incident/                 # Post-injection cluster state
│   ├── injected-change.yaml  # The tracked manifest (namespace replaced)
│   ├── pods.txt              # Pod status during incident
│   ├── events.txt            # Kubernetes events during incident
│   ├── cnpg-clusters.json    # CNPG status during incident
│   ├── cnpg-cluster.yaml     # CNPG cluster manifest
│   ├── describe-pods.txt     # Detailed pod descriptions
│   ├── k9b-incidents.json    # k9b detected incidents
│   └── k9b-incident-detail.json  # Detailed incident info
├── recovery-or-final/        # Post-recovery or final state
│   ├── pods.txt
│   ├── events.txt
│   └── cnpg-clusters.json
└── logs/
    ├── lab-runner.log        # Timestamped lab execution log
    ├── cnpg-operator.log     # CNPG operator logs
    ├── cnpg-operator-preflight.txt  # CNPG preflight results
    ├── k9b.log               # k9b agent logs
    ├── helm-k9b-status.txt   # Helm release status
    └── k9b-images.txt        # Observed k9b pod images
```

## Secret Hygiene

The lab explicitly avoids uploading:
- kubeconfig contents
- service account tokens
- generated database passwords
- OpenRouter keys
- GitHub tokens
- bearer tokens
- private keys
- full Secret resources

## Safety Boundaries

1. **Lab namespace cleanup**: Always runs via `if: always()` - deletes only `${LAB_NAMESPACE}`
2. **No system namespace mutation**: Does not touch `cnpg-system`, `kube-system`, `harbor`
3. **No CNPG operator installation**: Accepts preinstalled operator only
4. **No nested K3s**: Runs on existing cluster infrastructure
5. **k9b live detection deferred**: Not implemented in this ACT

## Build Commands

```bash
# Sync workspace and build
go work sync
go build -o dist/k9b-cnpg-incident-lab ./cmd/k9b-cnpg-incident-lab

# Run Go tests
go test -v ./internal/lab/cnpg/...
```

## Manual GitHub Actions Dispatch

1. Navigate to **Actions** → **K3s CNPG Incident Lab**
2. Click **Run workflow**
3. Configure inputs:
   - `artifact_retention_days`: Number of days (default: 7)
   - `run_live_lab`: Set to `true` to run live namespace-mode lab
   - `incident_scenario`: Choose incident scenario (default: pod-failure)
4. Click **Run workflow**

## Files Changed

| File | Purpose |
|------|---------|
| `.github/workflows/k9b-image-builder.yml` | Reusable image-build workflow (new) |
| `.github/workflows/k9b-cnpg-incident-lab.yml` | Main CI workflow with image-builder integration |
| `.github/workflows/k9b-cnpg-incident-lab-live.yml` | Live workflow in namespace mode |
| `scripts/verify_k3s_cnpg_incident_lab_artifact.py` | Artifact verifier with namespace-mode support |
| `tests/test_live_lab_config.py` | Workflow config tests (namespace mode) |
| `fixtures/lab/live/pod-failure/injected-change.yaml` | Tracked incident manifest |
| `docs/labs/k3s-cnpg-incident-lab.md` | This documentation |

## Verification

### CI / Manual

These verification commands are for CI and manual testing purposes only:

```bash
# Run lab config tests
.venv/bin/python -m pytest tests/test_live_lab_config.py -v
# Run verifier tests
.venv/bin/python -m pytest tests/test_verify_k3s_cnpg_incident_lab.py -v

# Verify passing fixture
.venv/bin/python scripts/verify_k3s_cnpg_incident_lab_artifact.py \
  --artifact-dir fixtures/lab/pass

# Run ACT-local verification
./scripts/verify_all.sh --act-local
```

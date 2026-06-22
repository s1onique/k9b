# K3s CNPG Incident Lab

## Navigation

- [Architecture Details](./k3s-cnpg-incident-lab-architecture.md) - Design decisions, RBAC, runner setup
- [Contract Reference](./k3s-cnpg-incident-lab-contract.md) - Artifact schemas, incident scenarios, files changed
- [Runbook](./k3s-cnpg-incident-lab-runbook.md) - Prerequisites, safety boundaries, verification commands

---

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
│  │  │  - Installs kubectl v1.31.0                         │ │ │
│  │  │  - Configures in-cluster kubeconfig from SA mount   │ │ │
│  │  │  - Verifies RBAC permissions (fatal preflight)      │ │ │
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

The lab runs in **existing-cluster namespace mode** with these characteristics:
- GitHub Actions runners run inside the target K3s cluster
- CloudNativePG is preinstalled; no CNPG operator install needed
- Images are built by canonical workflow and pushed to Harbor
- No Docker socket in runner pods (live workflow consumes images only)

### kubectl and In-Cluster kubeconfig Bootstrap

The live workflow bootstraps kubectl and kubeconfig entirely within the workflow:
1. **kubectl**: Uses `azure/setup-kubectl@v4` with pinned version `v1.31.0`
2. **kubeconfig**: Constructed from in-cluster service account mount at `/var/run/secrets/kubernetes.io/serviceaccount/`
3. **Security**: Token never echoed, no `--raw` config view, not uploaded as artifact

### RBAC Preflight (Fatal)

The workflow includes mandatory RBAC preflight checks. See [Architecture Details](./k3s-cnpg-incident-lab-architecture.md) for:
- Admin RBAC workflow (protected, manual-only trigger)
- Permission smoke checks
- RBAC preflight failure diagnostics
- One-time RBAC manifest application

### Runner Service Account Requirements

| Permission | Scope | Purpose |
|------------|-------|---------|
| get pods | all namespaces | Cluster-wide pod visibility |
| get nodes | cluster | Node health checks |
| get CRDs | cluster | CNPG CRD existence check |
| get pods/deployments | cnpg-system | CNPG operator visibility |
| create/patch/delete namespaces | cluster | Lab namespace lifecycle |
| create/get/delete pods | lab namespace | Incident injection and cleanup |
| create configmaps/secrets | lab namespace | Helm chart resource creation |
| create/get clusters.postgresql.cnpg.io | lab namespace | CNPG Cluster lifecycle |

### Required Runner Scale Sets

| Runner Scale Set | Purpose | Docker/Buildx |
|-----------------|---------|---------------|
| `spbnix-k8s-docker` | Image-builder workflow only | Required |
| `spbnix-k8s` | Live namespace lab workflow | Not needed |

See [Architecture Details](./k3s-cnpg-incident-lab-architecture.md) for runner setup details.

## CI Workflow

### Triggers

The workflow runs on:
- **Manual dispatch**: `workflow_dispatch` with configurable inputs
  - `artifact_retention_days`: Days to keep CI artifacts (default: 7)
  - `run_live_lab`: Whether to run live namespace-mode lab (default: false)
  - `incident_scenario`: Which incident scenario to run (default: pod-failure)
- **PR**: When lab-related files change (workflow, Go code, Python verifier, fixtures)
- **Push to main**: When lab-related files change

**Important**: Live lab only runs when `run_live_lab=true` is explicitly set.

### CI Jobs

#### build-and-verify Job

Runs on `ubuntu-latest`:
1. Builds the Go lab runner (`dist/k9b-cnpg-incident-lab`)
2. Runs Go unit tests for `internal/lab/cnpg`
3. Runs Python verifier tests
4. Verifies passing fixture (`fixtures/lab/pass`)
5. Verifies failing fixtures fail for intended reasons
6. Uploads build outputs and verification logs as artifacts

#### build-lab-images Job (only when live lab requested)

1. Calls the reusable `k9b-image-builder.yml` workflow
2. Builds and pushes k9b backend/frontend images to Harbor
3. Exposes image repository/tag/ref/digest as outputs

#### live-k3s-lab Job (only when live lab requested)

Runs on self-hosted runner with cluster access:
1. Installs kubectl (pinned v1.31.0)
2. Configures in-cluster kubeconfig from service account mount
3. Verifies RBAC permissions (fatal preflight)
4. Preflights existing CNPG operator/CRD
5. Creates unique lab namespace (`k9b-cnpg-lab-${GITHUB_RUN_ID}`)
6. Verifies namespace-scoped RBAC permissions
7. Deploys k9b via Helm chart using image-builder outputs
8. Asserts k9b pod image matches image-builder output
9. Deploys CNPG Cluster in lab namespace
10. Injects pod-failure incident using tracked manifest
11. Verifies incident symptom (pod NotReady)
12. Collects artifacts and runs verifier
13. Cleans up lab namespace (always runs)
14. Uploads artifacts

## Artifact Map

See [Contract Reference](./k3s-cnpg-incident-lab-contract.md) for:
- `lab-result.json` schema
- Complete directory structure
- Secret hygiene requirements

## Quick Reference

### Prerequisites
- CloudNativePG operator preinstalled in `cnpg-system`
- ARC runner scale sets configured
- Harbor registry with k9b images
- RBAC manifest applied (one-time)

### Incident Scenarios
See [Contract Reference](./k3s-cnpg-incident-lab-contract.md) for all scenarios.

**Current**: pod-failure - Non-destructive failing readiness probe, reversible.

### Verification Commands
See [Runbook](./k3s-cnpg-incident-lab-runbook.md) for:
- Lab config tests
- Verifier tests
- ACT-local verification
- Live lab acceptance criteria
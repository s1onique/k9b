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

The lab was converted from nested K3s provisioning to existing-cluster namespace mode because:

1. **GitHub Actions runners already run inside the target K3s cluster** - No need to provision a nested K3s
2. **CloudNativePG is preinstalled** - No need to install the CNPG operator
3. **Harbor is available in-cluster** - Images are built by the canonical workflow and pushed to Harbor
4. **No Docker socket in runner pods** - Cannot build images in the live workflow

### kubectl and In-Cluster kubeconfig Bootstrap

The live workflow bootstraps kubectl and kubeconfig entirely within the workflow:

1. **kubectl installation**: Uses `azure/setup-kubectl@v4` with a pinned version (`v1.31.0`) compatible with the cluster. No kubectl baked into the runner image is required.

2. **In-cluster kubeconfig**: Constructs kubeconfig from the in-cluster service account mount at `/var/run/secrets/kubernetes.io/serviceaccount/`:
   - Reads `KUBERNETES_SERVICE_HOST` to determine API server address
   - Uses `token` file for authentication
   - Uses `ca.crt` for certificate verification
   - Configures context `in-cluster` with `runner-sa` credentials

3. **Security hygiene**:
   - Token is never echoed or printed
   - `kubectl config view --raw` is not used (would leak embedded tokens)
   - kubeconfig is not uploaded as an artifact
   - `KUBECONFIG` is exported to `$GITHUB_ENV` for subsequent steps

### RBAC Preflight (Fatal)

The workflow includes mandatory RBAC preflight checks that fail the job if permissions are missing. These checks use a helper script (`scripts/k9b_cnpg_live_lab_rbac_preflight.sh`) that provides actionable error output identifying exactly which permission is missing.

### RBAC Security Boundary

The live lab runner service account (`system:serviceaccount:github-actions-runner:spbnix-k8s-gha-rs-no-permission`) **must not be able to update ClusterRoles, ClusterRoleBindings, Roles, or RoleBindings**. This is a deliberate security boundary to prevent CI from granting itself new permissions.

**The live lab workflow does NOT apply RBAC itself.** Instead, a separate protected admin workflow handles RBAC changes.

#### Admin RBAC Workflow

A dedicated GitHub Actions workflow applies the live-lab RBAC manifest safely:

```yaml
name: K9B CNPG Live Lab RBAC Admin
on:
  workflow_dispatch:
    inputs:
      confirm_apply:
        description: 'Type APPLY to apply live-lab RBAC manifest'
        required: true
      dry_run:
        description: 'Run server-side dry-run only'
        required: true
        default: true
```

**Location**: `.github/workflows/k9b-cnpg-live-lab-rbac-admin.yml`

**Key security features:**

1. **Manual-only trigger**: No push, PR, or schedule triggers
2. **Protected environment**: Requires `k9b-live-lab-admin` environment with manual approval
3. **Admin kubeconfig**: Uses `K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64` secret (base64-encoded)
4. **Exact confirmation**: Requires `confirm_apply=APPLY` exactly
5. **Fixed manifest path**: Only applies `deploy/github-actions/k9b-cnpg-live-lab-runner-rbac.yaml`
6. **Server-side dry-run**: Always runs dry-run before apply
7. **Manifest validation**: Verifies no placeholders, wildcards, or cluster-admin
8. **Permission verification**: Confirms live runner permissions via `kubectl auth can-i --as`
9. **Proper cleanup**: Removes temp kubeconfig and smoke namespace with `if: always()`

**How to run:**

1. Navigate to **Actions** → **K9B CNPG Live Lab RBAC Admin**
2. Click **Run workflow**
3. Set `confirm_apply: APPLY`
4. Set `dry_run: true` (recommended first run to review changes)
5. Wait for protected environment approval
6. Review dry-run output in workflow logs
7. If satisfied, re-run with `dry_run: false`

**Required setup:**

1. Create GitHub environment: `k9b-live-lab-admin`
2. Add required reviewers (trusted maintainers/admins)
3. Add environment secret: `K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64`
   ```bash
   # Extract only pve1-k3s-main context and encode as base64:
   scripts/extract_kubeconfig_context_secret.py \
     --context pve1-k3s-main \
     --kubeconfig ~/.kube/config
   ```
   
   The script will:
   - Extract only the `pve1-k3s-main` context from your kubeconfig
   - Validate the extracted kubeconfig has exactly one context
   - Write a single-line base64 string to `/tmp/k9b-admin-kubeconfig-pve1-k3s-main.b64`
   - Print instructions for pasting into GitHub
   
   Open the generated file and paste its contents into the environment secret.
   
   **Do not commit the generated file.**

   Alternatively, for `--stdout` mode (copy/paste directly):
   ```bash
   scripts/extract_kubeconfig_context_secret.py --stdout --force
   ```

**Permission smoke checks:**

The admin workflow verifies that the live lab runner has:
- ✓ `get pods --all-namespaces`
- ✓ `get nodes`
- ✓ `get customresourcedefinitions.apiextensions.k8s.io/clusters.postgresql.cnpg.io`
- ✓ `create/patch/delete namespaces`
- ✓ `get/create/delete persistentvolumeclaims`
- ✓ `get/create clusters.postgresql.cnpg.io`

And that the live runner **cannot**:
- ✗ `get secrets` (correctly denied)
- ✗ `update clusterroles.rbac.authorization.k8s.io` (correctly denied)
- ✗ `update clusterrolebindings.rbac.authorization.k8s.io` (correctly denied)

**What must never be uploaded:**
- kubeconfig contents
- service account tokens
- base64-decoded credentials

**Manifest path:** `deploy/github-actions/k9b-cnpg-live-lab-runner-rbac.yaml`

**Before namespace creation:**
- `get pods --all-namespaces`
- `get nodes`
- `get customresourcedefinitions.apiextensions.k8s.io/clusters.postgresql.cnpg.io`
- `get pods -n cnpg-system`
- `get deployments -n cnpg-system`
- `create namespaces`
- `patch namespaces`
- `delete namespaces`

**After namespace creation (lab namespace-scoped):**
- `create pods -n $LAB_NAMESPACE`
- `delete pods -n $LAB_NAMESPACE`
- `list pods -n $LAB_NAMESPACE`
- `get pods/log -n $LAB_NAMESPACE`
- `get events -n $LAB_NAMESPACE`
- `get services -n $LAB_NAMESPACE`
- `get deployments.apps -n $LAB_NAMESPACE`
- `get statefulsets.apps -n $LAB_NAMESPACE`
- `create configmaps -n $LAB_NAMESPACE`
- `create secrets -n $LAB_NAMESPACE`
- `create clusters.postgresql.cnpg.io -n $LAB_NAMESPACE`
- `get clusters.postgresql.cnpg.io -n $LAB_NAMESPACE`
- `get jobs.batch -n $LAB_NAMESPACE`

#### Reading RBAC Preflight Failures

When RBAC preflight fails, the workflow outputs actionable diagnostics:

```text
Checking: create namespaces ... NO
ERROR: missing permission for: create namespaces
Command: kubectl auth can-i create namespaces --quiet
```

This output:
1. Identifies which permission check failed (`create namespaces`)
2. Shows the exact `kubectl auth can-i` command that was run
3. Is printed before the job exits with failure

The workflow also prints Kubernetes subject diagnostics before RBAC checks:

```text
=== Kubernetes Subject Diagnostics ===
ServiceAccount namespace: actions-runner
Current context: in-cluster
Authenticated subject:
system:serviceaccount:actions-runner:github-actions-runner
Subject info captured
```

This helps identify which service account is being used when permissions fail.

#### One-Time RBAC Manifest Application

The live lab does NOT grant itself permissions. To run the live lab, a cluster admin must apply the RBAC manifest once:

```bash
# Apply the RBAC manifest (one-time setup)
kubectl apply -f deploy/github-actions/k9b-cnpg-live-lab-runner-rbac.yaml
```

**Runner ServiceAccount**: `system:serviceaccount:github-actions-runner:spbnix-k8s-gha-rs-no-permission`

The manifest is now apply-ready with the actual runner ServiceAccount substituted. No manual replacement is required.

**Helm ConfigMap Driver**: The live workflow uses `HELM_DRIVER=configmap` to avoid granting Secret read access for Helm release metadata. This allows Helm to store release information in ConfigMaps instead of Secrets.

The manifest structure:
- **ClusterRole + ClusterRoleBinding** for cluster-scoped resources (namespaces, nodes, CRD)
- **ClusterRole + ClusterRoleBinding** for lab namespace resources (grants cluster-wide to any namespace the runner creates)
- **Role + RoleBinding** for cnpg-system namespace (read-only CNPG operator visibility)

**Cluster-wide grant note**: The lab namespace ClusterRoleBinding grants namespaced permissions cluster-wide because lab namespaces are dynamically generated per run (`k9b-cnpg-lab-${GITHUB_RUN_ID}`). This is a conscious tradeoff since Kubernetes cannot pre-bind RoleBindings to namespaces that do not yet exist.

The manifest intentionally:
- Does NOT bind `cluster-admin`
- Does NOT use wildcard verbs or resources
- Does NOT grant secrets read access (only create/update)
- Grants minimal permissions required for the lab

### Runner Service Account Requirements

The `spbnix-k8s` runner's service account must have the following RBAC permissions:

| Permission | Scope | Purpose |
|------------|-------|---------|
| get pods | all namespaces | Cluster-wide pod visibility for diagnostics |
| get nodes | cluster | Node health checks |
| get customresourcedefinitions.apiextensions.k8s.io/clusters.postgresql.cnpg.io | cluster | CNPG CRD existence check |
| get pods/deployments | cnpg-system | CNPG operator visibility |
| create/patch/delete namespaces | cluster | Lab namespace lifecycle |
| create/get/delete pods | lab namespace | Incident injection and cleanup |
| create configmaps/secrets | lab namespace | Helm chart resource creation |
| create/get clusters.postgresql.cnpg.io | lab namespace | CNPG Cluster lifecycle |

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
- In-cluster service account mount for kubeconfig bootstrap
- kubectl, Helm, Python (via workflow installation)
- CNPG operator visibility in `cnpg-system`
- Harbor access for image pulls

**Note**: The `spbnix-k8s` runner does NOT need kubectl baked in. The workflow installs kubectl via `azure/setup-kubectl@v4`.

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
- kubeconfig contents (generated in-memory from service account)
- service account tokens (used only for kubectl config, never echoed)
- generated database passwords
- OpenRouter keys
- GitHub tokens
- bearer tokens
- private keys
- full Secret resources

**kubeconfig security**: The kubeconfig is generated from the in-cluster service account mount and stored at `$HOME/.kube/config`. It is:
- Never echoed or printed
- Not uploaded as an artifact
- Used only for kubectl operations within the workflow

## Safety Boundaries

1. **Lab namespace cleanup**: Always runs via `if: always()` - deletes only `${LAB_NAMESPACE}`
2. **No system namespace mutation**: Does not touch `cnpg-system`, `kube-system`, `harbor`
3. **No CNPG operator installation**: Accepts preinstalled operator only
4. **No nested K3s**: Runs on existing cluster infrastructure
5. **k9b live detection deferred**: Not implemented in this ACT
6. **RBAC preflight is fatal**: Missing permissions cause immediate job failure

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
| `.github/workflows/k9b-image-builder.yml` | Reusable image-build workflow |
| `.github/workflows/k9b-cnpg-incident-lab.yml` | Main CI workflow with image-builder integration |
| `.github/workflows/k9b-cnpg-incident-lab-live.yml` | Live workflow with kubectl bootstrap and RBAC preflight |
| `.github/workflows/k9b-cnpg-live-lab-rbac-admin.yml` | Protected admin workflow for applying live-lab RBAC manifest |
| `scripts/k9b_cnpg_live_lab_rbac_preflight.sh` | Helper script for self-identifying RBAC failures |
| `scripts/verify_k3s_cnpg_incident_lab_artifact.py` | Artifact verifier with namespace-mode support |
| `tests/test_live_lab_config.py` | Workflow config tests (kubectl bootstrap, RBAC, secret hygiene) |
| `tests/test_live_lab_admin_rbac_workflow.py` | Tests for admin RBAC workflow |
| `fixtures/lab/live/pod-failure/injected-change.yaml` | Tracked incident manifest |
| `deploy/github-actions/k9b-cnpg-live-lab-runner-rbac.yaml` | Minimal RBAC manifest for spbnix-k8s runner |
| `docs/labs/k3s-cnpg-incident-lab.md` | This documentation |

## Verification

### CI / Manual

These verification commands are for CI and manual testing purposes only:

```bash
# Run lab config tests (includes kubectl bootstrap and RBAC tests)
.venv/bin/python -m pytest tests/test_live_lab_config.py -v

# Run verifier tests
.venv/bin/python -m pytest tests/test_verify_k3s_cnpg_incident_lab.py -v

# Verify passing fixture
.venv/bin/python scripts/verify_k3s_cnpg_incident_lab_artifact.py \
  --artifact-dir fixtures/lab/pass

# Run ACT-local verification
./scripts/verify_all.sh --act-local
```

### Live Lab Acceptance Criteria

For a successful live lab run:

1. **Runner pickup**: Job is picked up by `spbnix-k8s` runner
2. **kubectl setup**: `Set up kubectl` step completes successfully
3. **kubeconfig bootstrap**: `Configure in-cluster kubeconfig` step completes
4. **kubectl availability**: `kubectl version --client` passes
5. **RBAC preflight**: `kubectl auth can-i` checks pass (or fail with clear missing permission error)
6. **CNPG preflight**: CNPG operator visibility check passes
7. **No token leakage**: No tokens or kubeconfig printed or uploaded
8. **Namespace-mode preserved**: Lab uses unique namespace, not cluster-wide resources
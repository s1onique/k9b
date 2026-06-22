# K3s CNPG Incident Lab - Architecture

This document details the architecture and design decisions for the K3s CNPG Incident Lab.

## Existing-Cluster Namespace Mode

The lab was converted from nested K3s provisioning to existing-cluster namespace mode because:

1. **GitHub Actions runners already run inside the target K3s cluster** - No need to provision a nested K3s
2. **CloudNativePG is preinstalled** - No need to install the CNPG operator
3. **Harbor is available in-cluster** - Images are built by the canonical workflow and pushed to Harbor
4. **No Docker socket in runner pods** - Cannot build images in the live workflow

## kubectl and In-Cluster kubeconfig Bootstrap

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

## RBAC Preflight (Fatal)

The workflow includes mandatory RBAC preflight checks that fail the job if permissions are missing. These checks use a helper script (`scripts/k9b_cnpg_live_lab_rbac_preflight.sh`) that provides actionable error output identifying exactly which permission is missing.

## RBAC Security Boundary

The live lab runner service account (`system:serviceaccount:github-actions-runner:spbnix-k8s-gha-rs-no-permission`) **must not be able to update ClusterRoles, ClusterRoleBindings, Roles, or RoleBindings**. This is a deliberate security boundary to prevent CI from granting itself new permissions.

**The live lab workflow does NOT apply RBAC itself.** Instead, a separate protected admin workflow handles RBAC changes.

### Admin RBAC Workflow

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

### Reading RBAC Preflight Failures

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

### One-Time RBAC Manifest Application

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

## Runner Service Account Requirements

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

## Image-Builder Ownership

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
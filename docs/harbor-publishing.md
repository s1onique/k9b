# Harbor Publishing

This repository uses GitHub Actions to build and push Docker images and Helm charts to the Harbor registry at `registry.spbnix.com`.

## Verification Gate

Before any Docker image is built or pushed, the workflow runs `./scripts/verify_all.sh` as a verification gate. This ensures:
- Python code passes linting (ruff), unit tests, and type checking (mypy)
- Frontend code passes dependency installation, UI tests, and build

If verification fails:
- No Docker images are built
- No images are pushed to Harbor
- The workflow exits with failure

## GitHub Actions Secrets Required

Before the workflow can push images, add these secrets to your GitHub repository:

| Secret | Description |
|--------|-------------|
| `HARBOR_USERNAME` | Your Harbor username |
| `HARBOR_TOKEN` | Harbor access token (preferably a robot-account token with push access) |
| `SPBNIX_CA_CERT_PEM` | PEM-encoded CA certificate (or CA chain) for `registry.spbnix.com` / `harbor-pve1.spbnix.local` |

**Note:** `HARBOR_TOKEN` should preferably be a Harbor robot-account token with push access to the target Harbor project.

## SPbNIX Harbor CA Certificate

The `SPBNIX_CA_CERT_PEM` secret contains the PEM-encoded CA certificate (or CA chain) required to trust the SPbNIX Harbor registry. This is needed because `registry.spbnix.com` resolves to `harbor-pve1.spbnix.local`, which uses a certificate signed by the internal SPbNIX CA.

### Creating the Secret

The CA certificate is typically provided by the SPbNIX infrastructure team. Once you have the PEM file:

```bash
# For repository-level secret
gh secret set SPBNIX_CA_CERT_PEM --repo s1onique/k9b < spbnix-harbor-ca.pem

# For organization-level secret (if applicable)
gh secret set SPBNIX_CA_CERT_PEM --org s1onique < spbnix-harbor-ca.pem
```

Alternatively, set it via the GitHub UI: **Settings → Secrets and variables → Actions → New repository secret**.

### CA Installation Behavior

The CA is installed in two places:

1. **Runner trust store** - For Docker CLI operations (login, diagnostics)
2. **BuildKit containers** - For image push operations via `docker/build-push-action`

This ensures end-to-end TLS verification without disabling certificate checks.

## Registry Configuration

| Setting | Value |
|---------|-------|
| Registry | `registry.spbnix.com` |
| Harbor Project | `gitinsky` |
| DockerHub Proxy Cache | `registry.spbnix.com/dockerhub-cache` |

## DockerHub Proxy Cache

Base images for Docker builds are routed through Harbor's proxy cache to avoid DockerHub layer pull instability.

### How It Works

- **Harbor project**: `dockerhub-cache` (proxy-cache mode, not a push target)
- **Purpose**: Cache DockerHub layers locally to avoid rate limiting and pull failures
- **Images routed through proxy**:
  - `python:3.12-slim` → `registry.spbnix.com/dockerhub-cache/library/python:3.12-slim`
  - `node:20-slim` → `registry.spbnix.com/dockerhub-cache/library/node:20-slim`
  - `nginxinc/nginx-unprivileged:stable-alpine` → `registry.spbnix.com/dockerhub-cache/nginxinc/nginx-unprivileged:stable-alpine`

### DockerHub Official Images

DockerHub official images (like `python`, `node`, `nginx`) require the `library/` prefix in Harbor because they live under the `library/` namespace on DockerHub.

### Verification

The script `scripts/verify_dockerhub_base_images.sh` checks that CI-critical Dockerfiles use the Harbor proxy cache and fails if direct DockerHub base images are detected.

### Notes

- This fixes DockerHub layer pull instability, not GitHub Actions cache timeouts
- The proxy cache is read-only from the build perspective (pull only)
- After first pull, layers are cached in Harbor and subsequent builds use local layers

## Image Names

| Image | Harbor URL |
|-------|------------|
| Backend | `registry.spbnix.com/gitinsky/k9b-backend` |
| Frontend (Node) | `registry.spbnix.com/gitinsky/k9b-frontend` |

## Helm Chart

| Artifact | Harbor OCI URL |
|----------|----------------|
| Helm chart | `oci://registry.spbnix.com/gitinsky/k9b:<version>` |

Install published chart:
```bash
helm install infra-k9b oci://registry.spbnix.com/gitinsky/k9b --version <version>
```

## Trigger Events

| Event | Trigger Condition | Action |
|-------|-------------------|--------|
| `pull_request` | PR opened/updated on `main` | Build only (no push) - verification gate runs first |
| `push` | Merge to `main` | Build + push after verification |
| `push` | Push to `release/**` branch | Build + push after verification |
| `push` | Push version tag `v*` | Build + push after verification |
| `workflow_dispatch` | Manual trigger from GitHub Actions UI or `gh workflow run` | Build + push after verification |

### Manual Runs

Manual runs (`workflow_dispatch`) are **publishing runs** because the workflow pushes whenever the event is not `pull_request`. Use caution when triggering manually from the Actions UI.

To trigger manually:
```bash
gh workflow run harbor.yml
```

Or via GitHub Actions UI: Repository → Actions → Build and Push to Harbor → Run workflow

## Image Tags Produced

All images are tagged with the short Git commit SHA only:
- `{COMMIT_SHORT_SHA}` - e.g., `4344ab1`

Example image tags:
- `registry.spbnix.com/gitinsky/k9b-backend:4344ab1`
- `registry.spbnix.com/gitinsky/k9b-frontend:4344ab1`

### On `pull_request` (build only)
- `{sha}` - short Git commit SHA (not pushed)

### On `push` to `main`, `release/**`, or version tag `v*`
- `{sha}` - short Git commit SHA

### Manual `workflow_dispatch` runs
- `{sha}` - short Git commit SHA

## Workflow Files

| Workflow | Purpose |
|----------|---------|
| `.github/workflows/harbor.yml` | Build and push container images to Harbor |
| `.github/workflows/helm-chart.yml` | Build and push Helm chart to Harbor OCI |

## Helm OCI Dual-Login Workaround

**Status:** Active workaround (do not remove until Harbor is fixed)

**Problem:** Harbor leaks its internal hostname (`harbor-pve1.spbnix.local`) in OCI blob-upload redirect responses. Additionally, the internal hostname uses an internal CA not trusted by CI runners.

**Workaround:** Log into both hostnames before pushing the chart:
- `registry.spbnix.com` - external/public hostname (via `docker/login-action`)
- `harbor-pve1.spbnix.local` - internal blob-upload hostname (via `helm registry login --insecure`)

**How it works:** The `publish` job in `helm-chart.yml` runs:
1. External host login: `docker/login-action` to `registry.spbnix.com`
2. Internal host login: `helm registry login harbor-pve1.spbnix.local --username ... --password-stdin --insecure`

The `--insecure` flag is isolated to the internal hostname workaround only, since that host uses a self-signed internal CA.

**Long-term fix:** Repair Harbor's external URL / reverse-proxy configuration so it never emits internal hostnames in redirect responses. Once fixed:
1. Remove the internal-host login step from `helm-chart.yml`
2. Update this documentation to mark the workaround as removed
3. Verify `helm push` succeeds with only the external hostname login

**Verifier:** The script `scripts/verify_helm_oci_login.sh` checks that:
- Both hostnames have login steps (docker/login-action for external, helm --insecure for internal)
- Push target remains `oci://registry.spbnix.com/k9b`
- No plain `--password` usage (must use `--password-stdin` or secrets injection)
- No secrets are echoed or printed
- `--insecure` is only used for the internal hostname (isolated to workaround)

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     harbor.yml                              │
│                                                             │
│  ┌─────────┐                                                │
│  │ verify  │ ── runs ./scripts/verify_all.sh ───────────────│
│  └────┬────┘                                                │
│       │                                                     │
│       ├─────────────────┬────────────────────┐               │
│       ▼                 ▼                    ▼               │
│  ┌───────────┐    ┌───────────┐   ┌───────────────┐        │
│  │ build-    │    │ frontend  │   │ (future jobs) │        │
│  │ push      │    │           │   │               │        │
│  └───────────┘    └───────────┘   └───────────────┘        │
│       │                 │                                │
│       ▼                 ▼                                │
│  Harbor push      Harbor push                            │
└─────────────────────────────────────────────────────────────┘
```

The `verify` job runs first. Both `build-push` and `frontend` jobs depend on `verify` completing successfully before they start. If verification fails, no Docker builds or pushes occur.

## Platforms

Both images are built for:
- `linux/amd64`
- `linux/arm64`

## Security Notes

- **Verification gate runs before any Docker operations** - ensures code quality before shipping
- Images are **never** pushed from `pull_request` events (untrusted context)
- Credentials are stored as GitHub Actions secrets, never in code
- Harbor login only runs when push is enabled (not on PR builds)
- **Use a Harbor robot-account token** for `HARBOR_TOKEN` to limit access scope

## GitHub Actions Runner Configuration

Publish jobs (`build-push` and `frontend` in `harbor.yml`, `publish` in `helm-chart.yml`) run on the self-hosted Kubernetes runner (`spbnix-k8s`) because Harbor resolves to internal SPbNIX/private DNS names during OCI push operations. GitHub-hosted runners cannot resolve these internal addresses.

| Job | Runner | Reason |
|-----|--------|--------|
| `verify` | `ubuntu-latest` (GitHub-hosted) | Public verification, no Harbor access required |
| `package` | `ubuntu-latest` (GitHub-hosted) | Helm chart packaging only |
| `build-push` | `spbnix-k8s` (self-hosted) | Internal Harbor DNS required |
| `frontend` | `spbnix-k8s` (self-hosted) | Internal Harbor DNS required |
| `publish` | `spbnix-k8s` (self-hosted) | Internal Harbor OCI push required |

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

# DockerHub Publishing

This repository uses GitHub Actions to build and push Docker images to DockerHub.

## GitHub Actions Secrets Required

Before the workflow can push images, add these secrets to your GitHub repository:

| Secret | Description |
|--------|-------------|
| `DOCKERHUB_USERNAME` | Your DockerHub username or organization name |
| `DOCKERHUB_TOKEN` | DockerHub access token (not your password) |

To create a DockerHub access token:
1. Go to DockerHub → Account Settings → Security → Access Tokens
2. Create a new token with at least "Read, Write, Delete" permissions

## Image Names

| Image | DockerHub URL |
|-------|---------------|
| Backend (Python) | `docker.io/s1onique/k9b-python` |
| Frontend (Node) | `docker.io/s1onique/k9b-python-frontend` |

**Namespace:** `s1onique` (GitHub username matches DockerHub namespace)

## Trigger Events

| Event | Trigger Condition | Action |
|-------|-------------------|--------|
| `pull_request` | PR opened/updated on `main` | Build only (no push) |
| `push` | Merge to `main` | Build + push |
| `push` | Push to `release/**` branch | Build + push |
| `push` | Push version tag `v*` | Build + push |
| `workflow_dispatch` | Manual trigger from GitHub Actions UI or `gh workflow run` | Build + push |

### Manual Runs

Manual runs (`workflow_dispatch`) are **publishing runs** because the workflow pushes whenever the event is not `pull_request`. Use caution when triggering manually from the Actions UI.

To trigger manually:
```bash
gh workflow run dockerhub.yml
```

Or via GitHub Actions UI: Repository → Actions → Build and Push to DockerHub → Run workflow

## Image Tags Produced

### On `pull_request` (build only)
- `{sha}` - short Git commit SHA

### On `push` to `main`
- `{branch}` - branch name (e.g., `main`)
- `{sha}` - short Git commit SHA
- `latest` - always tagged

### On `push` to `release/**`
- `{branch}` - branch name (e.g., `release/v1`)
- `{sha}` - short Git commit SHA

### On `push` of version tag `v1.2.3`
- `1.2.3` - full semantic version
- `1.2` - major.minor
- `1` - major only
- `{sha}` - short Git commit SHA

## Workflow File

The workflow is defined in `.github/workflows/dockerhub.yml`.

## Platforms

Both images are built for:
- `linux/amd64`
- `linux/arm64`

## Security Notes

- Images are **never** pushed from `pull_request` events (untrusted context)
- Credentials are stored as GitHub Actions secrets, never in code
- DockerHub login only runs when push is enabled (not on PR builds)

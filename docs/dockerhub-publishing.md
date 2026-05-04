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
| Backend (Python) | `docker.io/gitinsky/k9b-python` |
| Frontend (Node) | `docker.io/gitinsky/k9b-frontend` |

**Namespace:** `gitinsky`

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

All images are tagged with the short Git commit SHA only:
- `{COMMIT_SHORT_SHA}` - e.g., `4344ab1`

Example image tags:
- `docker.io/gitinsky/k9b-python:4344ab1`
- `docker.io/gitinsky/k9b-frontend:4344ab1`

### On `pull_request` (build only)
- `{sha}` - short Git commit SHA (not pushed)

### On `push` to `main`, `release/**`, or version tag `v*`
- `{sha}` - short Git commit SHA

### Manual `workflow_dispatch` runs
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

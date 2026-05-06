# k9b Helm Chart

Kubernetes diagnostics and monitoring agent powered by LLM.

## Overview

This Helm chart deploys k9b, an LLM-based Kubernetes monitoring and diagnostics agent. It includes:

- **Backend**: REST API and UI server (Python/FastAPI)
- **Scheduler**: Scheduled health loop execution
- **Frontend**: Web UI for diagnostics visualization

## Features

- Deploys three components: backend, scheduler, and frontend
- Supports ingress configuration for external access
- External secrets for kubeconfig (no embedded secrets)
- External ConfigMap for health configuration
- Configurable resource limits and replica counts
- Security contexts for Pod and container level

## Quick Start

### Prerequisites

- Kubernetes v1.21+
- Helm v3
- kubectl configured with cluster access

### Create Required Resources

Before installing, create the required Secret for kubeconfig:

```bash
kubectl create secret generic k9b-kubeconfig \
  --from-file=config=/path/to/kubeconfig
```

### Install the Chart

```bash
# Render locally first
helm template k9b ./charts/k9b

# Install with default values
helm install k9b ./charts/k9b

# Install with custom registry
helm install k9b ./charts/k9b \
  --set image.backend.repository=ghcr.io/your-org/k9b \
  --set image.backend.tag=v1.0.0 \
  --set image.frontend.repository=ghcr.io/your-org/k9b-frontend \
  --set image.frontend.tag=v1.0.0
```

### Verify Installation

```bash
# Check deployment status
kubectl get deployments -l app.kubernetes.io/name=k9b

# Check pod status
kubectl get pods -l app.kubernetes.io/name=k9b

# View pod logs
kubectl logs -l app.kubernetes.io/component=backend
```

### Install from OCI Registry

When published, you can install directly from the OCI registry:

```bash
# Log in to DockerHub (if using private charts)
helm registry login registry-1.docker.io

# Install the latest version
helm install k9b oci://registry-1.docker.io/<org>/k9b

# Install a specific version
helm install k9b oci://registry-1.docker.io/<org>/k9b --version 0.1.0

# Install with custom values
helm install k9b oci://registry-1.docker.io/<org>/k9b \
  --set image.backend.repository=your-registry/k9b \
  --set image.backend.tag=v1.0.0
```

Replace `<org>` with your DockerHub organization name.

### Uninstall

```bash
helm uninstall k9b
```

## Configuration

### Image Configuration

| Parameter | Description | Default |
|----------|-------------|---------|
| `image.backend.repository` | Backend image repository | `localhost/k9b_python` |
| `image.backend.tag` | Backend image tag | `latest` |
| `image.frontend.repository` | Frontend image repository | `localhost/k9b_frontend` |
| `image.frontend.tag` | Frontend image tag | `latest` |
| `image.*.pullPolicy` | Image pull policy | `IfNotPresent` |

### Backend Configuration

| Parameter | Description | Default |
|----------|-------------|---------|
| `backend.replicaCount` | Number of backend replicas | `1` |
| `backend.service.port` | Backend service port | `8080` |
| `backend.env.HEALTH_SKIP_REFRESH` | Skip auto-refresh | `"1"` |
| `backend.resources.*` | CPU/memory limits | See values.yaml |

### Scheduler Configuration

| Parameter | Description | Default |
|----------|-------------|---------|
| `scheduler.replicaCount` | Number of scheduler replicas | `1` |
| `scheduler.env.LLAMA_CPP_BASE_URL` | LLM provider URL | `""` |
| `scheduler.env.LLAMA_CPP_MODEL` | Model name | `""` |

### Frontend Configuration

| Parameter | Description | Default |
|----------|-------------|---------|
| `frontend.replicaCount` | Number of frontend replicas | `1` |
| `frontend.service.port` | Frontend service port | `5173` |

### Ingress Configuration

| Parameter | Description | Default |
|----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.host` | Hostname for ingress | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |

### External Resources

External resources are **optional** and must be explicitly enabled:

| Parameter | Description | Default |
|----------|-------------|---------|
| `kubeconfig.enabled` | Enable kubeconfig Secret mount | `false` |
| `kubeconfig.secretName` | Kubeconfig Secret name | `k9b-kubeconfig` |
| `kubeconfig.mountPath` | Mount path for kubeconfig | `/app/kubeconfig` |
| `healthConfig.enabled` | Enable health config ConfigMap mount | `false` |
| `healthConfig.configMapName` | Health config ConfigMap name | `k9b-health-config` |
| `healthConfig.mountPath` | Mount path for health config | `/app/runs` |

When `kubeconfig.enabled=true`, create the Secret before installing:

```bash
kubectl create secret generic k9b-kubeconfig --from-file=config=/path/to/kubeconfig
helm install k9b ./charts/k9b --set kubeconfig.enabled=true
```

When `healthConfig.enabled=true`, create the ConfigMap before installing:

```bash
kubectl create configmap k9b-health-config --from-file=health-config.json=/path/to/health-config.json
helm install k9b ./charts/k9b --set healthConfig.enabled=true
```

## Linting and Testing

### Run Helm Lint

```bash
helm lint charts/k9b
```

### Render Templates

```bash
helm template k9b charts/k9b
```

### Render with Custom Values

```bash
helm template k9b charts/k9b \
  --values charts/k9b/values.yaml \
  --set image.backend.repository=gcr.io/your-project/k9b \
  --set ingress.enabled=true \
  --set ingress.host=k9b.example.com
```

## Security Considerations

### General Security

- No secrets are embedded in chart defaults
- Kubeconfig is expected to be provided via an external Secret
- Health configuration is expected to be provided via an external ConfigMap
- Container runs as non-root by default (uid 1000)
- Capability dropping is enabled by default
- Use `containerSecurityContext` to further restrict privileges

### UI/API Authentication (AUTH-07, AUTH-10)

The k9b backend exposes a REST API and UI server with mutation endpoints that can modify cluster state.

#### Default Security Posture

By default, the backend binds to `127.0.0.1` (localhost-only) which provides safe access without additional configuration. This is suitable for:

- Local development with `kubectl port-forward`
- Standalone operator workstation deployments
- CI/CD pipelines with local access

#### Exposed Deployment Pattern (AUTH-10)

If you need cluster-wide access (binding to `0.0.0.0` or external IPs), you MUST enable both:

1. **`backend.unsafeBind: true`** - Acknowledges the risk of binding to non-loopback
2. **`uiAuth.enabled: true`** - Protects mutation endpoints with bearer token

**Example: Cluster-wide exposed deployment**

```bash
# Step 1: Create the auth secret
kubectl create secret generic k9b-ui-auth --from-literal=K9B_UI_TOKEN=<your-secure-token>

# Step 2: Install with exposed bind + auth
helm install k9b ./charts/k9b \
  --set backend.env.HEALTH_UI_HOST=0.0.0.0 \
  --set backend.unsafeBind=true \
  --set uiAuth.enabled=true \
  --set uiAuth.secretName=k9b-ui-auth
```

**values.yaml equivalent:**

```yaml
backend:
  unsafeBind: true
  env:
    HEALTH_UI_HOST: "0.0.0.0"

uiAuth:
  enabled: true
  secretName: "k9b-ui-auth"
```

#### Secure Deployment Patterns

When binding to non-loopback addresses, you MUST use one of the following:

1. **Bearer Token Authentication** (recommended for direct exposure) - See below
2. **Reverse Proxy Authentication** (recommended for ingress-based access) - See below

#### Bearer Token Authentication

When `backend.env.HEALTH_UI_HOST` is set to `0.0.0.0` or an external IP address, you strongly SHOULD configure bearer token authentication or place the service behind an authenticated reverse proxy:

**Step 1: Create the Kubernetes Secret**

```bash
kubectl create secret generic k9b-ui-auth --from-literal=K9B_UI_TOKEN=<your-secure-token>
```

**Step 2: Install/upgrade the chart with auth enabled**

```bash
helm install k9b ./charts/k9b \
  --set uiAuth.enabled=true \
  --set uiAuth.secretName=k9b-ui-auth
```

**values.yaml configuration:**

```yaml
uiAuth:
  enabled: true
  secretName: "k9b-ui-auth"
```

**Example Secret manifest:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: k9b-ui-auth
type: Opaque
stringData:
  K9B_UI_TOKEN: "your-secure-bearer-token-here"
```

**Making authenticated requests:**

```bash
curl -X POST http://k9b-backend:8080/api/next-check-approval \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-secure-token>" \
  -d '{"clusterLabel": "prod", "candidateIndex": 0}'
```

**Protected endpoints**: The following POST mutation endpoints are protected by bearer token authentication when `K9B_UI_TOKEN` is configured:
- `/api/deterministic-next-check/promote`
- `/api/next-check-execution`
- `/api/next-check-approval`
- `/api/next-check-execution-usefulness`
- `/api/alertmanager-relevance-feedback`
- `/api/run-batch-next-check-execution`
- `/api/runs/{run_id}/alertmanager-sources/{source_id}/action`

**Note**: GET endpoints remain unprotected. If you require read authentication, use a reverse proxy with auth.

#### Reverse Proxy Authentication

Configure authentication at your reverse proxy layer (nginx, traefik, ambassador) before requests reach k9b.

**Ingress example with Basic Auth annotation (nginx-ingress):**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: k9b-ingress
  annotations:
    nginx.ingress.kubernetes.io/auth-type: basic
    nginx.ingress.kubernetes.io/auth-secret: k9b-basic-auth
    nginx.ingress.kubernetes.io/auth-realm: "k9b API"
spec:
  ingressClassName: nginx
  rules:
  - host: k9b.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: k9b-backend
            port:
              number: 8080
```

Create the auth secret:

```bash
htpasswd -c auth admin
kubectl create secret generic k9b-basic-auth --from-file=auth
```

#### Security Notes

| Aspect | Status |
|--------|--------|
| Default bind address | `127.0.0.1` (localhost-only) **DONE** (AUTH-10) |
| Non-loopback requires unsafeBind | **Enforced** via `--unsafe-bind` flag **DONE** (AUTH-10) |
| Bearer token auth for POST endpoints | **Implemented** (AUTH-04/05/06) |
| GET endpoint protection | **Deferred** (use reverse proxy) |
| Token validation | Timing-attack resistant via `hmac.compare_digest` |
| Token logging | Token never echoed in logs or errors |

#### Helm Values Security Options

| Value | Purpose | Default |
|-------|---------|---------|
| `backend.unsafeBind` | Allow non-loopback binding | `false` |
| `uiAuth.enabled` | Enable bearer token auth | `false` |
| `uiAuth.secretName` | Secret containing `K9B_UI_TOKEN` | `k9b-ui-auth` |
| `backend.env.HEALTH_UI_HOST` | Bind address | `127.0.0.1` |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        k9b Helm Chart                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐   │
│  │  Backend   │    │  Scheduler  │    │      Frontend       │   │
│  │  (Python)  │    │  (Python)   │    │   (React/Vite)     │   │
│  │  :8080     │    │             │    │      :5173          │   │
│  └──────┬──────┘    └──────┬──────┘    └──────────┬──────────┘   │
│         │                  │                       │              │
│         │                  │                       │              │
│         └──────────────────┴───────────────────────┘              │
│                            │                                      │
│                   ┌────────▼────────┐                            │
│                   │   Kubernetes   │                            │
│                   │     Cluster    │                            │
│                   └────────────────┘                            │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐   │
│  │  Kubeconfig │    │   Health    │    │   UI Auth Secret    │   │
│  │   Secret    │    │  ConfigMap  │    │  (K9B_UI_TOKEN)     │   │
│  └─────────────┘    └─────────────┘    └─────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Contributing

See [k9b repository](https://github.com/s1onique/k9b) for contribution guidelines.

## Versioning

This chart follows [semantic versioning](https://semver.org/).

| Field | Description | Example |
|-------|-------------|---------|
| `version` (Chart.yaml) | Chart version, follows semver | `0.1.0`, `1.0.0` |
| `appVersion` (Chart.yaml) | Application version (k9b release) | `0.1.0` |
| `image.backend.tag` (values) | Backend Docker image tag | `latest`, `v1.0.0` |
| `image.frontend.tag` (values) | Frontend Docker image tag | `latest`, `v1.0.0` |

### Versioning Policy

- **Chart version**: Manually bumped in `Chart.yaml` before publishing
- **Image tags**: Configurable through values; operator is responsible for matching images to chart version
- **Breaking changes**: Chart version bump follows semver; breaking changes increment major version

### Upgrading

```bash
# Upgrade to a new chart version
helm upgrade k9b oci://registry-1.docker.io/<org>/k9b --version 1.0.0

# Upgrade with new image tags
helm upgrade k9b oci://registry-1.docker.io/<org>/k9b \
  --set image.backend.tag=v1.0.0 \
  --set image.frontend.tag=v1.0.0
```

## License

Apache License 2.0

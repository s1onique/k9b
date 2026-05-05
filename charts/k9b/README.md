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

- No secrets are embedded in chart defaults
- Kubeconfig is expected to be provided via an external Secret
- Health configuration is expected to be provided via an external ConfigMap
- Container runs as non-root by default (uid 1000)
- Capability dropping is enabled by default
- Use `containerSecurityContext` to further restrict privileges

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
│  ┌─────────────┐    ┌─────────────┐                             │
│  │  Kubeconfig │    │   Health    │                             │
│  │   Secret    │    │  ConfigMap  │                             │
│  └─────────────┘    └─────────────┘                             │
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

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
- Embedded health configuration as ConfigMap (no external resources required)
- Embedded service account and read-only RBAC for diagnostics
- Persistent storage for health run artifacts
- Configurable resource limits and replica counts
- Security contexts for Pod and container level
- In-cluster service account authentication by default

## Quick Start

### Prerequisites

- Kubernetes v1.21+
- Helm v3
- kubectl configured with cluster access

### Install the Chart

k9b is distributed as a **rolling beta** from the repository. The supported consumption path is:

```bash
# Install from local chart (supported beta path)
helm install infra-k9b ./charts/k9b -n k9b --create-namespace

# Render locally first to inspect
helm template infra-k9b ./charts/k9b
```

**Beta consumption model:**
- Clone/pull the repository for the latest version
- Install the Helm chart from local checkout
- Build images locally or provide explicit image overrides

**Note:** The default `values.yaml` references Harbor images at `registry.spbnix.com/gitinsky/k9b-backend` and `registry.spbnix.com/gitinsky/k9b-frontend`. Images are published via GitHub Actions. Override using `--set` flags or use docker-compose for local development.

**For local development with docker-compose:**
```bash
docker compose up --build -d
```

**For Helm deployment with custom image registry:**
```bash
helm install infra-k9b ./charts/k9b -n k9b \
  --set image.backend.repository=your-registry/k9b-backend \
  --set image.backend.tag=ecacd81 \
  --set image.frontend.repository=your-registry/k9b-frontend \
  --set image.frontend.tag=ecacd81
```

**Images are published to Harbor.** Harbor publishing requires `HARBOR_USERNAME` and `HARBOR_TOKEN` GitHub secrets. See [docs/harbor-publishing.md](../../docs/harbor-publishing.md) for workflow details.

### Upgrade the Chart

```bash
# Upgrade with new image tags
helm upgrade infra-k9b ./charts/k9b -n k9b \
  --set image.backend.tag=<new-tag> \
  --set image.frontend.tag=<new-tag>
```

### Verify Installation

```bash
# Check deployment status
kubectl get pods -n k9b

# View scheduler logs
kubectl logs -n k9b deploy/infra-k9b-scheduler

# Check scheduler mounts
kubectl exec -n k9b deploy/infra-k9b-scheduler -- sh -lc 'ls -la /app/runs /app/runs/health-config.json'
```

### Uninstall

```bash
helm uninstall infra-k9b -n k9b
```

## Configuration

### Image Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.backend.repository` | Backend/scheduler image repository | `registry.spbnix.com/gitinsky/k9b-backend` |
| `image.backend.tag` | Backend/scheduler image tag | `ecacd81` |
| `image.frontend.repository` | Frontend image repository | `registry.spbnix.com/gitinsky/k9b-frontend` |
| `image.frontend.tag` | Frontend image tag | `ecacd81` |
| `image.*.pullPolicy` | Image pull policy | `IfNotPresent` |

### Backend Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backend.replicaCount` | Number of backend replicas | `1` |
| `backend.service.port` | Backend service port | `8080` |
| `backend.env.HEALTH_SKIP_REFRESH` | Skip auto-refresh | `"1"` |
| `backend.env.HEALTH_UI_HOST` | UI bind address | `0.0.0.0` (cluster-wide) |
| `backend.resources.*` | CPU/memory limits | See values.yaml |

### Scheduler Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `scheduler.replicaCount` | Number of scheduler replicas | `1` |
| `scheduler.unsafeBind` | Allow binding to 0.0.0.0 | `true` |
| `scheduler.command` | Override container command | `[]` |
| `scheduler.args` | Override container args | `[]` |
| `scheduler.env.LLAMA_CPP_BASE_URL` | LLM provider URL | `""` |
| `scheduler.env.LLAMA_CPP_MODEL` | Model name | `""` |

#### Image Entrypoint Dispatch

The published backend image (`registry.spbnix.com/gitinsky/k9b-backend`) uses an entrypoint dispatcher script (`/app/docker-entrypoint.sh`) that expects the first argument to be a service name (`backend` or `scheduler`). The script dispatches to the appropriate startup script based on the first argument.

**Default scheduler invocation:**

When `scheduler.args` is empty (the default), the chart renders:
```yaml
args:
  - scheduler
  - --unsafe-bind   # if scheduler.unsafeBind=true (default)
```

This invokes the entrypoint as:
```bash
/app/docker-entrypoint.sh scheduler --unsafe-bind
```

Which dispatches to:
```bash
exec ./scripts/run_health_scheduler.py --unsafe-bind
```

#### Scheduler Unsafe Bind

The scheduler exposes a health UI/API server that binds to `0.0.0.0:8080` by default. This is intentional for in-cluster access but requires explicit acknowledgement via `--unsafe-bind`.

**Why enabled by default:**
- The scheduler needs to serve UI/API endpoints for health diagnostics
- In-cluster pods can access the service via the Kubernetes DNS name
- Service remains ClusterIP by default (not exposed externally)

**Warning:** The scheduler API exposes mutation endpoints:
- `POST /api/next-check-approval`
- `POST /api/next-check-execution`
- `POST /api/deterministic-next-check/promote`

**Recommended access pattern (port-forwarding):**

```bash
kubectl port-forward -n k9b deploy/infra-k9b-scheduler 8080:8080
open http://127.0.0.1:8080
```

**If exposing via Ingress:** Require auth and consider NetworkPolicy.

**Override behavior:**

```yaml
# Disable unsafe bind (use loopback or custom args)
scheduler:
  unsafeBind: false
```

When `scheduler.unsafeBind=false` and `scheduler.args` is empty, the chart renders:
```yaml
args:
  - scheduler
```

**Custom args:**

When `scheduler.args` is explicitly set, it replaces the default args entirely. You must include `scheduler` as the first element to use the entrypoint dispatcher:

```yaml
# Custom args with full control
scheduler:
  args:
    - scheduler
    - --custom-flag

# Or bypass the dispatcher entirely (not recommended for production)
scheduler:
  command: ["./scripts/run_health_scheduler.py"]
  args:
    - --unsafe-bind
```

**Important:** If you set `scheduler.args` without `scheduler` as the first element, the entrypoint script will fail with "exec: --: invalid option" because it interprets the first arg as a command to exec directly.

### Frontend Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `frontend.replicaCount` | Number of frontend replicas | `1` |
| `frontend.service.port` | Frontend service port | `5173` |

### Health Configuration

The chart embeds health configuration as a ConfigMap. Customise via `healthConfig.data`:

```yaml
healthConfig:
  enabled: true
  data:
    targets:
      - name: "prod-cluster"
        kubeContext: "prod"
```

This maps to `/app/runs/health-config.json` inside the scheduler container.

The scheduler also requires a baseline configuration file mounted at `/app/runs/health-baseline.local.json`:

```yaml
healthConfig:
  baseline:
    enabled: true
    data: {}
```

The baseline file stores cluster health state snapshots used for comparison during health runs. Customize via `healthConfig.baseline.data`.

### Runs Storage

Persistent storage for health run artifacts:

```yaml
runs:
  persistence:
    enabled: true
    size: 2Gi
    accessModes:
      - ReadWriteOnce
    storageClassName: ""  # Use cluster default
    mountPath: /app/runs
```

Mounted into both scheduler and backend for artifact sharing.

### Service Account and RBAC

By default, the chart creates a ServiceAccount and read-only ClusterRole for diagnostics:

```yaml
serviceAccount:
  create: true
  name: ""  # Defaults to <fullname>-sa

rbac:
  create: true
  clusterWide: true  # ClusterRole; false for namespaced Role
```

ClusterRole includes read access to:
- Core: pods, services, endpoints, events, namespaces, nodes, configmaps, persistentvolumeclaims, persistentvolumes
- Apps: deployments, replicasets, statefulsets, daemonsets
- Batch: jobs, cronjobs
- Networking: ingresses, networkpolicies
- Autoscaling: horizontalpodautoscalers
- Metrics: pods, nodes (metrics.k8s.io)

### External Kubeconfig (Optional)

By default, uses in-cluster service account authentication. For external cluster access:

```yaml
kubeconfig:
  enabled: true
  secretName: "k9b-kubeconfig"
  mountPath: "/app/kubeconfig"
```

Create the secret before enabling:

```bash
kubectl create secret generic k9b-kubeconfig --from-file=config=/path/to/kubeconfig
```

### Ingress Configuration

The k9b ingress routes all external traffic to the **frontend service**, which proxies `/api/` to the backend internally via nginx. This keeps the backend service internal-only.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name (e.g., nginx, traefik) | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts` | List of hosts with paths | `[]` |
| `ingress.tls` | TLS configuration | `[]` |

#### Plain HTTP Ingress

```yaml
ingress:
  enabled: true
  className: nginx
  hosts:
    - host: k9b.example.com
      paths:
        - path: /
          pathType: Prefix
```

#### NGINX Ingress with cert-manager TLS

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
  hosts:
    - host: k9b.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: k9b-tls
      hosts:
        - k9b.example.com
```

#### Multiple Hosts

```yaml
ingress:
  enabled: true
  className: nginx
  hosts:
    - host: k9b.example.com
      paths:
        - path: /
          pathType: Prefix
    - host: www.k9b.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: k9b-tls
      hosts:
        - k9b.example.com
        - www.k9b.example.com
```

#### Traffic Flow

```
External Traffic
      │
      ▼
┌─────────────────┐
│  Ingress         │
│  (nginx/traefik)│
└────────┬────────┘
         │ /
         ▼
┌─────────────────┐
│  Frontend        │  ◄── Ingress routes here
│  Service :8080   │
└────────┬────────┘
         │ /api/
         ▼
┌─────────────────┐
│  Backend        │  ◄── Internal only
│  Service :8080  │
└─────────────────┘
```

The frontend nginx ConfigMap (`frontend.configmapNginx: true`) handles the `/api/` proxy internally using the Helm-templated backend service name.

## Linting and Testing

### Run Helm Lint

```bash
helm lint charts/k9b
```

### Render Templates

```bash
helm template infra-k9b charts/k9b
```

### Render with Custom Values

```bash
helm template infra-k9b charts/k9b \
  --values charts/k9b/values.yaml \
  --set ingress.enabled=true \
  --set ingress.host=k9b.example.com
```

## Security Considerations

### General Security

- No secrets are embedded in chart defaults
- Service account authentication used by default (no kubeconfig required)
- Container runs as non-root by default (uid 1000)
- Capability dropping is enabled by default
- Read-only ClusterRole for diagnostics (no write access)
- Use `containerSecurityContext` to further restrict privileges

### UI/API Authentication (AUTH-07, AUTH-10)

The k9b backend exposes a REST API and UI server with mutation endpoints that can modify cluster state.

#### Default Security Posture

By default, the backend binds to `0.0.0.0` (cluster-wide) for in-cluster Kubernetes Service access. This requires `uiAuth.enabled=true` when exposed externally. For localhost-only access, set `backend.env.HEALTH_UI_HOST=127.0.0.1`.

#### Exposed Deployment Pattern (AUTH-10)

If you need cluster-wide access (binding to `0.0.0.0` or external IPs), you MUST enable both:

1. **`backend.unsafeBind: true`** - Acknowledges the risk of binding to non-loopback
2. **`uiAuth.enabled: true`** - Protects mutation endpoints with bearer token

**Example: Cluster-wide exposed deployment**

```bash
# Step 1: Create the auth secret
kubectl create secret generic k9b-ui-auth --from-literal=K9B_UI_TOKEN=<your-secure-token>

# Step 2: Install with exposed bind + auth
helm install infra-k9b ./charts/k9b -n k9b \
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
helm install infra-k9b ./charts/k9b -n k9b \
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
| Default bind address | `0.0.0.0` (cluster-wide, requires uiAuth for external exposure) |
| Non-loopback requires unsafeBind | **Enforced** via `--unsafe-bind` flag **DONE** (AUTH-10) |
| Bearer token auth for POST endpoints | **Implemented** (AUTH-04/05/06) |
| GET endpoint protection | **Deferred** (use reverse proxy) |
| Token validation | Timing-attack resistant via `hmac.compare_digest` |
| Token logging | Token never echoed in logs or errors |

#### Helm Values Security Options

| Value | Purpose | Default |
|-------|---------|---------|
| `backend.unsafeBind` | Allow non-loopback binding (required for HEALTH_UI_HOST=0.0.0.0) | `true` |
| `scheduler.unsafeBind` | Allow scheduler binding to 0.0.0.0 | `true` |
| `uiAuth.enabled` | Enable bearer token auth | `false` |
| `uiAuth.secretName` | Secret containing `K9B_UI_TOKEN` | `k9b-ui-auth` |
| `backend.env.HEALTH_UI_HOST` | Backend bind address | `0.0.0.0` |

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
│         │                  │                       │              │
│         └──────────────────┴───────────────────────┘              │
│                            │                                      │
│                   ┌────────▼────────┐                            │
│                   │   Kubernetes   │                            │
│                   │     Cluster    │                            │
│                   └────────────────┘                            │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐   │
│  │ ServiceAcct │    │   Health    │    │   UI Auth Secret    │   │
│  │   + RBAC    │    │  ConfigMap  │    │  (K9B_UI_TOKEN)     │   │
│  └─────────────┘    └─────────────┘    └─────────────────────┘   │
│                                                                 │
│  ┌─────────────┐                                               │
│  │    Runs     │                                               │
│  │    PVC      │                                               │
│  └─────────────┘                                               │
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
| `image.backend.tag` (values) | Backend Docker image tag | `ecacd81`, `v1.0.0` |
| `image.frontend.tag` (values) | Frontend Docker image tag | `ecacd81`, `v1.0.0` |

### Versioning Policy

- **Chart version**: Manually bumped in `Chart.yaml` before publishing
- **Image tags**: Configurable through values; operator is responsible for matching images to chart version
- **Breaking changes**: Chart version bump follows semver; breaking changes increment major version

### Upgrading

```bash
# Upgrade to a new chart version
helm upgrade infra-k9b ./charts/k9b -n k9b --version 1.0.0

# Upgrade with new image tags
helm upgrade infra-k9b ./charts/k9b -n k9b \
  --set image.backend.tag=v1.0.0 \
  --set image.frontend.tag=v1.0.0
```

## License

Apache License 2.0
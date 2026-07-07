# In-Cluster Deployment Guide

This guide explains how to deploy K9b inside a Kubernetes cluster without mounting a kubeconfig Secret.

## Overview

When deployed in-cluster, K9b uses the Pod ServiceAccount token mounted at `/var/run/secrets/kubernetes.io/serviceaccount/token` and the standard `KUBERNETES_SERVICE_HOST`/`KUBERNETES_SERVICE_PORT` environment variables for authentication.

## Quick Install

```bash
# Install with in-cluster authentication (default)
helm install k9b ./charts/k9b \
  --namespace k9b \
  --create-namespace \
  --set kubernetes.auth.mode=inCluster

# Or use auto-detection (defaults to in-cluster when deployed in a pod)
helm install k9b ./charts/k9b \
  --namespace k9b \
  --create-namespace
```

## Configuration Options

### Authentication Modes

| Mode | Description |
|------|-------------|
| `auto` | Default. Prefer explicit kubeconfig if present, otherwise use in-cluster auth |
| `inCluster` | Force use of Pod ServiceAccount token |
| `kubeconfig` | Require explicit kubeconfig file |

### RBAC Scope

| Setting | Description |
|---------|-------------|
| `rbac.clusterWide=true` | Creates ClusterRole with cluster-wide read access (default) |
| `rbac.clusterWide=false` | Creates Role with namespaced read access |

### Example: Namespaced Diagnostics

For environments where cluster-wide access is not available:

```bash
helm install k9b ./charts/k9b \
  --namespace k9b \
  --create-namespace \
  --set kubernetes.auth.mode=inCluster \
  --set rbac.clusterWide=false \
  --set serviceAccount.name=k9b-diagnostics
```

### Example: Cluster-Wide Diagnostics (Default)

For full cluster visibility:

```bash
helm install k9b ./charts/k9b \
  --namespace k9b \
  --create-namespace \
  --set kubernetes.auth.mode=inCluster \
  --set rbac.clusterWide=true
```

## Verification Commands

After deployment, verify RBAC permissions:

```bash
# Check ServiceAccount was created
kubectl -n k9b get serviceaccount

# Verify RBAC resources
kubectl -n k9b get clusterrole,clusterrolebinding  # For clusterWide=true
kubectl -n k9b get role,rolebinding              # For clusterWide=false

# Verify kubectl access from scheduler pod
kubectl -n k9b exec deploy/k9b-scheduler -- kubectl auth can-i get pods --all-namespaces

# List all pods across namespaces (requires cluster-wide)
kubectl -n k9b exec deploy/k9b-scheduler -- kubectl get pods -A

# Test read-only access to specific resources
kubectl -n k9b exec deploy/k9b-scheduler -- kubectl get nodes
kubectl -n k9b exec deploy/k9b-scheduler -- kubectl get events -A
```

## RBAC Permissions

### Cluster-Wide (Default)

The ClusterRole provides read-only access to:

- **Core**: pods, services, endpoints, events, namespaces, nodes, configmaps
- **Apps**: deployments, replicasets, statefulsets, daemonsets
- **Batch**: jobs, cronjobs
- **Networking**: ingresses, networkpolicies
- **Autoscaling**: horizontalpodautoscalers
- **Metrics**: pods, nodes
- **Discovery**: endpointslices (Service backend identity)
- **Monitoring**: alertmanagers, prometheuses, prometheusrules, servicemonitors, podmonitors, alertmanagerconfigs (Prometheus Operator CRDs)


### Namespaced

The Role provides read-only access to namespaced resources:

- **Core**: pods, services, endpoints, events, configmaps
- **Apps**: deployments, replicasets, statefulsets, daemonsets
- **Batch**: jobs, cronjobs
- **Networking**: ingresses, networkpolicies
- **Autoscaling**: horizontalpodautoscalers
- **Metrics**: pods
- **Discovery**: endpointslices (Service backend identity)
- **Monitoring**: alertmanagers, prometheuses, alertmanagerconfigs, prometheusrules, servicemonitors, podmonitors (Prometheus Operator CRDs)

## Alertmanager Discovery RBAC Verification

After deployment, verify K9B has read-only access to Alertmanager discovery resources:

```bash
# Get the backend service account name (handles custom names)
SA="$(kubectl -n k9b get deploy k9b-backend -o jsonpath='{.spec.template.spec.serviceAccountName}')"
SA="${SA:-default}"

# Verify EndpointSlice access (Service backend identity)
kubectl auth can-i list endpointslices.discovery.k8s.io --as="system:serviceaccount:k9b:${SA}"
kubectl auth can-i get endpointslices.discovery.k8s.io --as="system:serviceaccount:k9b:${SA}"
kubectl auth can-i watch endpointslices.discovery.k8s.io --as="system:serviceaccount:k9b:${SA}"

# Verify Prometheus Operator CRD access
kubectl auth can-i list alertmanagers.monitoring.coreos.com --as="system:serviceaccount:k9b:${SA}"
kubectl auth can-i list prometheuses.monitoring.coreos.com --as="system:serviceaccount:k9b:${SA}"
kubectl auth can-i list alertmanagerconfigs.monitoring.coreos.com --as="system:serviceaccount:k9b:${SA}"

# Verify StatefulSet access (Alertmanager StatefulSets)
kubectl auth can-i list statefulsets.apps --as="system:serviceaccount:k9b:${SA}"
kubectl auth can-i get statefulsets.apps --as="system:serviceaccount:k9b:${SA}"

# Verify Pod access in monitoring namespace
kubectl auth can-i list pods -n monitoring --as="system:serviceaccount:k9b:${SA}"
kubectl auth can-i get pods -n monitoring --as="system:serviceaccount:k9b:${SA}"

# Verify no secrets access (security requirement)
kubectl auth can-i list secrets --as="system:serviceaccount:k9b:${SA}"
# Expected: no

# Verify no write access to discovery resources
kubectl auth can-i create alertmanagers.monitoring.coreos.com --as="system:serviceaccount:k9b:${SA}"
# Expected: no
kubectl auth can-i update alertmanagers.monitoring.coreos.com --as="system:serviceaccount:k9b:${SA}"
# Expected: no
kubectl auth can-i delete alertmanagers.monitoring.coreos.com --as="system:serviceaccount:k9b:${SA}"
# Expected: no
```

All commands above should return `yes` for read access and `no` for secrets and write operations.


## Troubleshooting

### Pod Not Starting

Check if the ServiceAccount token is mounted:

```bash
kubectl -n k9b exec deploy/k9b-backend -- ls /var/run/secrets/kubernetes.io/serviceaccount/
```

Expected output should include `token`, `ca.crt`, and `namespace` files.

### Authentication Failures

Verify RBAC binding:

```bash
# For cluster-wide
kubectl get clusterrolebinding -n k9b

# Check subjects include the ServiceAccount
kubectl describe clusterrolebinding -n k9b
```

### Environment Variables

In in-cluster mode, the following are automatically available:

- `KUBERNETES_SERVICE_HOST` - Kubernetes API server host
- `KUBERNETES_SERVICE_PORT` - Kubernetes API server port
- `POD_NAMESPACE` - The namespace where the pod is running (exposed via downward API)

## External Cluster Access

If you need to access a different cluster than where K9b is deployed:

```bash
helm install k9b ./charts/k9b \
  --namespace k9b \
  --create-namespace \
  --set kubernetes.auth.mode=kubeconfig \
  --set kubeconfig.enabled=true \
  --set kubeconfig.secretName=my-kubeconfig
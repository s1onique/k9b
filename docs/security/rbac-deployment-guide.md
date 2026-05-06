# RBAC and Deployment Privilege Guide

**Document**: RBAC and Deployment Privilege Guide  
**Project**: k9b - Kubernetes Diagnostics Operator Console  
**Version**: 1.0  
**Date**: 2026-05-06  
**Related**: RISK-08, GAP-02, AUTH-10, `docs/security/threat-model.md`  

---

## 1. Overview

This document specifies the minimum Kubernetes RBAC permissions required for k9b to function, classified by operational risk. Operators should grant the smallest set of permissions needed for their intended use case.

**Key principle**: k9b is primarily a diagnostic read-only tool. Write permissions are only required for operator-approved next-check execution.

---

## 2. Kubernetes API Operations Inventory

### 2.1 Core Collection Operations

k9b performs these kubectl/helm operations via the health loop:

| Operation | Resource | Scope | Purpose |
|-----------|----------|-------|---------|
| `kubectl get nodes` | nodes | cluster | Node health and capacity |
| `kubectl get pods --all-namespaces` | pods | cluster | Pod status across namespaces |
| `kubectl get services -A` | services | cluster | Service discovery |
| `kubectl get endpoints -A` | endpoints | cluster | Endpoint health |
| `kubectl get events -A` | events | cluster | Warning/error event correlation |
| `kubectl get jobs --all-namespaces` | jobs | cluster | Batch job status |
| `kubectl config get-contexts` | configmaps (kube-system) | cluster | Available contexts |
| `helm list --all-namespaces` | helmreleases (via helm) | cluster | Helm release inventory |
| `kubectl get crds` | customresourceddefinitions | cluster | CRD discovery |

### 2.2 Image Pull Secret Drilldown

When warning events indicate `FailedToRetrieveImagePullSecret`, k9b performs additional inspection:

| Operation | Resource | Scope | Purpose |
|-----------|----------|-------|---------|
| `kubectl get deployments -n <ns>` | deployments | namespace | Find deployments using the secret |
| `kubectl get secret -n <ns> <name>` | secrets | namespace | Verify target secret exists |
| `kubectl get externalsecrets -n <ns>` | externalsecrets | namespace | Check ExternalSecret CR status |

### 2.3 Alertmanager Discovery and Port-Forward

For Alertmanager integration (if enabled):

| Operation | Resource | Scope | Purpose |
|-----------|----------|-------|---------|
| `kubectl get alertmanagers -A` | alertmanagers (prometheus-operator) | cluster | Discover Alertmanager instances |
| `kubectl get prometheuses -A` | prometheuses (prometheus-operator) | cluster | Discover related Prometheus |
| `kubectl get svc -A` | services | cluster | Resolve Alertmanager service endpoints |
| `kubectl get pods -A -l app=alertmanager` | pods | cluster | Find Alertmanager pods |
| `kubectl port-forward -n <ns> svc/<name>` | services/pods | namespace | Access cluster-internal Alertmanager API |

### 2.4 Next-Check Execution (Operator-Approved)

When operators approve next-check execution, additional read operations occur:

| Operation | Resource | Scope | Purpose |
|-----------|----------|-------|---------|
| `kubectl describe <resource>` | various | namespace | Detailed resource inspection |
| `kubectl logs <pod>` | pods | namespace | Log retrieval |
| `kubectl top <resource>` | pods/nodes | namespace | Resource metrics (requires metrics-server) |

---

## 3. Permission Classification

### 3.1 Required Read-Only Permissions

These permissions are required for basic k9b functionality. They provide read-only access to cluster state:

```yaml
# Namespace-scoped Role for k9b
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: k9b-read-only
  namespace: <target-namespace>
rules:
  # Core cluster reading
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints", "events", "limitranges", "resourcequotas"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["node.k8s.io"]
    resources: ["runtimeclasses"]
    verbs: ["get", "list", "watch"]
  # For cluster-wide collection
  - apiGroups: [""]
    resources: ["nodes", "namespaces", "persistentvolumes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses"]
    verbs: ["get", "list", "watch"]
```

### 3.2 Sensitive Read Permissions

These permissions involve accessing potentially sensitive data. Grant only if the corresponding features are needed:

```yaml
# Image pull secret drilldown (only if this feature is needed)
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list"]  # NOTE: Only get for specific secrets needed
    # Consider restricting to specific secrets if possible:
    # resourceNames: ["<specific-secret-name>"]

  # External secrets CRD (only if ExternalSecret operator is deployed)
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets"]
    verbs: ["get", "list", "watch"]
```

**⚠️ Warning**: `secrets` access allows reading deployment image pull secrets and any other secrets in the namespace. Consider:

1. Using a dedicated namespace for k9b with minimal secret exposure
2. Using cluster-wide secrets read only if image pull secret drilldown is required
3. Restricting to specific secret names if possible

### 3.3 Optional Permissions

These permissions are only needed for specific features:

```yaml
# Helm releases (only if Helm v3 is deployed and helm releases should be monitored)
  # Note: This typically requires cluster-wide access via ClusterRole
  - apiGroups: ["helm.k8s.io"]
    resources: ["helmreleases"]
    verbs: ["get", "list"]

# CRD discovery (read-only inspection)
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourceddefinitions"]
    verbs: ["get", "list", "watch"]

# Alertmanager/Prometheus operators (only if Alertmanager integration is enabled)
  - apiGroups: ["monitoring.coreos.com"]
    resources: ["alertmanagers", "prometheuses", "prometheusagents"]
    verbs: ["get", "list", "watch"]
```

### 3.4 Permissions That Should NEVER Be Granted

These permissions are not required by k9b and should be explicitly denied:

```yaml
# DENY rules - these permissions are NOT needed
rules:
  # Write operations
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["create", "update", "patch", "delete", "deletecollection"]

  # Escalation
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["clusterroles", "clusterrolebindings", "roles", "rolebindings"]
    verbs: ["get", "list", "watch", "escalate", "bind"]

  # Secrets write (should never be needed)
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["create", "update", "patch", "delete"]

  # Pod exec/logs write (not needed - logs are read-only)
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["*"]  # Only get/list if logs inspection enabled

  # Token review (service account token creation)
  - apiGroups: ["authentication.k8s.io"]
    resources: ["tokenreviews"]
    verbs: ["create"]
```

---

## 4. Recommended RBAC Shapes

### 4.1 Minimal Namespace-Scoped Role

For single-namespace diagnostics with no image pull secret drilldown:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: k9b-minimal
  namespace: <target-namespace>
rules:
  # Core reading
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints", "events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get", "list", "watch"]
```

### 4.2 Standard Namespace-Scoped Role (Recommended)

For typical operator use with image pull secret drilldown:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: k9b-standard
  namespace: <target-namespace>
rules:
  # Core cluster reading
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints", "events", "configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list"]  # For image pull secret drilldown
  - apiGroups: [""]
    resources: ["resourcequotas", "limitranges"]
    verbs: ["get", "list"]
```

### 4.3 Cluster-Wide ClusterRole (Multi-Namespace Support)

For multi-namespace or cluster-wide monitoring:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: k9b-cluster-read
rules:
  # Cluster-wide reading
  - apiGroups: [""]
    resources: ["nodes", "namespaces", "persistentvolumes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourceddefinitions"]
    verbs: ["get", "list", "watch"]

  # Namespaced reading (will be bound to specific namespaces)
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints", "events", "configmaps", "secrets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]

  # Optional: Helm releases (if Helm operator deployed)
  - apiGroups: ["helm.k8s.io"]
    resources: ["helmreleases"]
    verbs: ["get", "list"]

  # Optional: External secrets (if ExternalSecret operator deployed)
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets"]
    verbs: ["get", "list", "watch"]

  # Optional: Alertmanager integration
  - apiGroups: ["monitoring.coreos.com"]
    resources: ["alertmanagers", "prometheuses"]
    verbs: ["get", "list", "watch"]
```

---

## 5. Namespace vs. Cluster Scope Guidance

### 5.1 Choose Namespace-Scoped When

- Monitoring a single namespace or a small set of namespaces
- Operators have cluster-admin or can create RoleBindings
- Image pull secret drilldown is needed in specific namespaces
- Minimal permission footprint is required

### 5.2 Choose Cluster-Scoped (ClusterRole) When

- Multi-namespace monitoring is required
- Cluster-wide resources (nodes, persistentvolumes) need monitoring
- CRD discovery across the cluster is needed
- Helm releases across all namespaces should be monitored
- Alertmanager integration spanning multiple namespaces is required

### 5.3 ServiceAccount Example

```yaml
# ServiceAccount for k9b
apiVersion: v1
kind: ServiceAccount
metadata:
  name: k9b
  namespace: k9b-system  # Dedicated namespace recommended

---
# RoleBinding for namespace-scoped access
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: k9b-read-access
  namespace: monitored-namespace
subjects:
  - kind: ServiceAccount
    name: k9b
    namespace: k9b-system
roleRef:
  kind: Role
  name: k9b-standard
  apiGroup: rbac.authorization.k8s.io
```

---

## 6. Network Policy Guidance

### 6.1 Recommended NetworkPolicy Posture

k9b should be deployed with restrictive network policies:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: k9b-restrictive
  namespace: k9b-system
spec:
  podSelector:
    matchLabels:
      app: k9b-backend
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow UI server access (adjust port as needed)
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: operator-namespace  # Adjust to your setup
      ports:
        - protocol: TCP
          port: 8080
  egress:
    # Allow DNS resolution
    - to:
        - namespaceSelector: {}
          pods:
            namespaceSelector:
              matchLabels:
                kubernetes.io/kube-apiserver: "true"
      ports:
        - protocol: TCP
          port: 53
    # Allow API server communication
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/kube-apiserver: "true"
      ports:
        - protocol: TCP
          port: 443
    # Allow metrics-server (optional, for kubectl top)
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/namespace: kube-system
      ports:
        - protocol: TCP
          port: 443

# NOTE: NetworkPolicy selectors for kube-apiserver/DNS are cluster-specific.
# Treat this as a template and adapt labels/CIDRs to your CNI and control-plane layout.
```

### 6.2 Port Exposure Summary

| Port | Direction | Purpose | Required |
|------|-----------|---------|----------|
| 8080 | Ingress | UI/API server | Yes (for operator access) |
| 53 | Egress | DNS | Yes |
| 443 | Egress | Kubernetes API | Yes |
| 9093 | Egress | Alertmanager (if enabled) | Optional |

---

## 7. Service Exposure and AUTH-10 Reference

### 7.1 UI Server Binding

From `docs/security/operator-auth-design.md` (AUTH-10):

> **Default bind**: `127.0.0.1:8080` (localhost-only) ✅
> **Helm chart default**: `HEALTH_UI_HOST: "127.0.0.1"` - localhost-only.
> Cluster-wide access requires setting `HEALTH_UI_HOST: "0.0.0.0"`, `backend.unsafeBind: true`, and `uiAuth.enabled=true` or an authenticated reverse proxy.

**Recommendations**:

1. **Local workstation deployment**: Use default localhost binding (127.0.0.1)
2. **Cluster deployment**: 
   - Set `backend.env.HEALTH_UI_HOST: "127.0.0.1"` 
   - Use port-forward or authenticated ingress for access
   - Enable `uiAuth.enabled=true` with `K9B_UI_TOKEN` for production
3. **External access**: Configure authenticated reverse proxy (nginx, traefik) with:
   - TLS termination
   - Bearer token validation
   - IP allowlist if possible

### 7.2 Alertmanager Port-Forward

k9b uses `kubectl port-forward` to access cluster-internal Alertmanager endpoints. This:

- Requires `get` permission on the target service/pod
- Opens a local TCP port on the k9b host
- Should be protected by firewall rules on the k9b host
- Does not require cluster-wide network policies (port-forward is local to k9b host)

---

## 8. Residual Risks

### 8.1 Known Limitations

| Risk | Description | Mitigation |
|------|-------------|------------|
| **Secrets exposure** | Role with `secrets` get/list allows reading any secret in the namespace | Use dedicated namespace; restrict resource names if possible |
| **Cluster-wide read** | ClusterRole provides broad read access | Scope to specific namespaces via RoleBindings |
| **Port-forward abuse** | Port-forward allows local access to cluster services | Firewall k9b host; limit source IP access |
| **LLM data exfiltration** | Cluster data enters LLM prompts | See `docs/security/llm-anonymization-design.md` |
| **Token in transit** | K9B_UI_TOKEN transmitted in API calls | Use TLS; rotate tokens regularly |

### 8.2 Deployment Recommendations

1. **Create dedicated `k9b-system` namespace** for k9b components
2. **Use separate ServiceAccount** per monitored namespace (via RoleBindings)
3. **Enable uiAuth** for any non-localhost deployment
4. **Audit RoleBindings** regularly to ensure least privilege
5. **Rotate ServiceAccount tokens** per your organization's rotation policy

---

## 9. Helm Chart Integration Notes

### 9.1 Current Chart State

The Helm chart at `charts/k9b/` currently:
- Does **not** include RBAC templates (no Role, ClusterRole, ServiceAccount, RoleBinding)
- Requires operators to create RBAC resources separately
- Uses existing kubeconfig for authentication (see `kubeconfig.enabled` in values.yaml)

### 9.2 Future RBAC Templates

A future implementation may add optional RBAC templates. Until then:

1. Create RBAC resources as documented in this guide
2. Reference the ServiceAccount in your k9b deployment
3. Mount the ServiceAccount token in the k9b pod for in-cluster authentication

### 9.3 Example Helm Values for ServiceAccount

```yaml
# values.yaml additions (future support)
serviceAccount:
  create: true
  name: k9b
  annotations:
    # Add annotations as needed for IRSA, Workload Identity, etc.
```

---

## 10. Quick Reference

### 10.1 Minimum Permissions (Namespace-Scoped)

```yaml
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints", "events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch"]
```

### 10.2 With Image Pull Secret Drilldown

```yaml
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints", "events", "secrets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets"]
    verbs: ["get", "list"]
```

### 10.3 With Alertmanager Integration

```yaml
rules:
  # Standard namespace scope
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints", "events", "secrets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch"]
  # Alertmanager CRD (requires cluster-wide or monitoring namespace access)
  - apiGroups: ["monitoring.coreos.com"]
    resources: ["alertmanagers", "prometheuses"]
    verbs: ["get", "list", "watch"]
```

---

## 11. Related Documents

| Document | Purpose |
|----------|---------|
| `docs/security/threat-model.md` | Security threat analysis including RISK-08 |
| `docs/security/operator-auth-design.md` | UI server authentication (AUTH-10) |
| `docs/security/llm-anonymization-design.md` | LLM prompt data handling |
| `charts/k9b/values.yaml` | Helm chart configuration |
| `src/k8s_diag_agent/health/image_pull_secret.py` | Image pull secret implementation |
| `src/k8s_diag_agent/health/loop_alertmanager_port_forward.py` | Port-forward implementation |

---

**Document End**
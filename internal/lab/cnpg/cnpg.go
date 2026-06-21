// cnpg.go: CloudNativePG operator and cluster management for the incident lab.
package cnpg

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// CNPGNamespace is the namespace where CNPG operator is installed.
const CNPGNamespace = "cnpg-system"

// CNPGOperatorVersion is the pinned version of the CNPG operator.
const CNPGOperatorVersion = "1.26.0"

// CNPGOperatorManifest is the official CNPG operator manifest URL.
const CNPGOperatorManifest = "https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/v%s/releases/cnpg-1.26.0.yaml"

// CNPGClusterManifest is a minimal PostgreSQL cluster manifest template.
// The lab namespace and cluster name are injected at runtime.
const CNPGClusterManifest = `apiVersion: v1
kind: Namespace
metadata:
  name: %s
---
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: %s
  namespace: %s
spec:
  instances: 1
  imageName: ghcr.io/cloudnative-pg/postgresql:17.5
  storage:
    size: 1Gi
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
    limits:
      cpu: "500m"
      memory: "512Mi"
  bootstrap:
    initdb:
      database: appdb
      owner: appuser
  superuserSecret:
    name: %s
`

// CNPGSuperuserSecret is the secret name for the CNPG superuser.
const CNPGSuperuserSecret = "cnpg-superuser-secret"

// CNPGSuperuserSecretManifest creates a minimal secret for CNPG superuser.
const CNPGSuperuserSecretManifest = `apiVersion: v1
kind: Secret
metadata:
  name: %s
  namespace: %s
type: Opaque
stringData:
  username: postgres
  password: %s
`

// CNPGStatus captures the status of the CNPG operator and clusters.
type CNPGStatus struct {
	OperatorInstalled   bool   `json:"operator_installed"`
	OperatorVersion     string `json:"operator_version,omitempty"`
	OperatorReady       bool   `json:"operator_ready"`
	ClustersInstalled   int    `json:"clusters_installed"`
	ClusterDetails      []ClusterDetail `json:"cluster_details,omitempty"`
	ErrorMsg            string `json:"error,omitempty"`
}

// ClusterDetail captures details about a specific CNPG cluster.
type ClusterDetail struct {
	Name      string `json:"name"`
	Namespace string `json:"namespace"`
	Ready     bool   `json:"ready"`
	Instances int    `json:"instances"`
	Phase     string `json:"phase,omitempty"`
}

// InstallCNPGOperator installs the CloudNativePG operator.
func InstallCNPGOperator(ctx context.Context, client *K8sClient) error {
	// Build manifest inline (URL is documented but not fetched to avoid network dependency).
	_ = fmt.Sprintf(CNPGOperatorManifest, CNPGOperatorVersion)
	manifest := fmt.Sprintf(`apiVersion: v1
kind: Namespace
metadata:
  name: %s
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cnpg-manager
  namespace: %s
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cnpg-manager
rules:
  - apiGroups: [""]
    resources: ["configmaps", "secrets", "services"]
    verbs: ["*"]
  - apiGroups: ["postgresql.cnpg.io"]
    resources: ["clusters", "backups", "poolers"]
    verbs: ["*"]
`, CNPGNamespace, CNPGNamespace)

	// Apply namespace and RBAC first.
	if err := client.ApplyYAML(ctx, manifest); err != nil {
		return fmt.Errorf("apply CNPG namespace/RBAC: %w", err)
	}

	// Apply operator deployment using a simplified inline manifest.
	// In production, use the official release manifest.
	operatorManifest := fmt.Sprintf(`apiVersion: apps/v1
kind: Deployment
metadata:
  name: cnpg-operator
  namespace: %s
  labels:
    app.kubernetes.io/name: cnpg-operator
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: cnpg-operator
  template:
    metadata:
      labels:
        app.kubernetes.io/name: cnpg-operator
    spec:
      serviceAccountName: cnpg-manager
      containers:
      - name: operator
        image: ghcr.io/cloudnative-pg/cloudnative-pg:%s
        args:
        - controller
        env:
        - name: CNPG_OPERATOR_CONFIG
          value: "{}"
        resources:
          requests:
            cpu: "100m"
            memory: "64Mi"
          limits:
            cpu: "500m"
            memory: "256Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: cnpg-webhook-service
  namespace: %s
spec:
  selector:
    app.kubernetes.io/name: cnpg-operator
  ports:
  - port: 443
    targetPort: 9443
`, CNPGNamespace, CNPGOperatorVersion, CNPGNamespace)

	if err := client.ApplyYAML(ctx, operatorManifest); err != nil {
		return fmt.Errorf("apply CNPG operator deployment: %w", err)
	}

	// Wait for operator rollout.
	if err := WaitForDeployment(ctx, client, CNPGNamespace, "cnpg-operator", 5*time.Minute); err != nil {
		return fmt.Errorf("wait for CNPG operator rollout: %w", err)
	}

	return nil
}

// WaitForDeployment waits for a deployment to be ready.
func WaitForDeployment(ctx context.Context, client *K8sClient, namespace, name string, timeout time.Duration) error {
	deadline, ok := ctx.Deadline()
	if !ok {
		deadline = time.Now().Add(timeout)
	}
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			var deploy struct {
				Status struct {
					Replicas            int `json:"replicas"`
					ReadyReplicas       int `json:"readyReplicas"`
					AvailableReplicas   int `json:"availableReplicas"`
				} `json:"status"`
			}
			if err := client.RunKubectlJSON(ctx, &deploy, "-n", namespace, "get", "deployment", name); err != nil {
				continue
			}
			if deploy.Status.AvailableReplicas >= 1 {
				return nil
			}
			if time.Now().After(deadline) {
				return fmt.Errorf("timeout waiting for deployment %s/%s", namespace, name)
			}
		}
	}
}

// DeployCNPGCluster deploys a minimal CNPG cluster.
func DeployCNPGCluster(ctx context.Context, client *K8sClient, namespace, clusterName string) error {
	// Create superuser secret first.
	secretManifest := fmt.Sprintf(CNPGSuperuserSecretManifest,
		CNPGSuperuserSecret, namespace, "lab-password-change-me")
	if err := client.ApplyYAML(ctx, secretManifest); err != nil {
		return fmt.Errorf("apply CNPG superuser secret: %w", err)
	}

	// Deploy the cluster.
	clusterManifest := fmt.Sprintf(CNPGClusterManifest,
		namespace, clusterName, namespace, CNPGSuperuserSecret)
	if err := client.ApplyYAML(ctx, clusterManifest); err != nil {
		return fmt.Errorf("apply CNPG cluster manifest: %w", err)
	}

	// Wait for cluster to be ready.
	if err := WaitForCNPGCluster(ctx, client, namespace, clusterName, 10*time.Minute); err != nil {
		return fmt.Errorf("wait for CNPG cluster ready: %w", err)
	}

	return nil
}

// WaitForCNPGCluster waits for a CNPG cluster to reach Ready state.
func WaitForCNPGCluster(ctx context.Context, client *K8sClient, namespace, clusterName string, timeout time.Duration) error {
	deadline, ok := ctx.Deadline()
	if !ok {
		deadline = time.Now().Add(timeout)
	}
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			var cluster struct {
				Status struct {
					Instances int    `json:"instances"`
					Phase     string `json:"phase"`
				} `json:"status"`
			}
			if err := client.RunKubectlJSON(ctx, &cluster, "-n", namespace, "get", "cluster", clusterName); err != nil {
				continue
			}
			if cluster.Status.Phase == "Cluster in healthy state" || cluster.Status.Phase == "Healthy" {
				return nil
			}
			if time.Now().After(deadline) {
				return fmt.Errorf("timeout waiting for CNPG cluster %s/%s (phase: %s)",
					namespace, clusterName, cluster.Status.Phase)
			}
		}
	}
}

// GetCNPGStatus queries the CNPG operator and cluster status.
func GetCNPGStatus(ctx context.Context, client *K8sClient) (*CNPGStatus, error) {
	status := &CNPGStatus{}

	// Check if CNPG operator deployment exists and is ready.
	var deploy struct {
		Status struct {
			AvailableReplicas int `json:"availableReplicas"`
		} `json:"status"`
	}
	if err := client.RunKubectlJSON(ctx, &deploy, "-n", CNPGNamespace, "get", "deployment", "cnpg-operator"); err != nil {
		status.ErrorMsg = fmt.Sprintf("CNPG operator not found: %v", err)
		return status, nil
	}
	status.OperatorInstalled = true
	status.OperatorVersion = CNPGOperatorVersion
	status.OperatorReady = deploy.Status.AvailableReplicas >= 1

	// List CNPG clusters.
	var clusters struct {
		Items []struct {
			Metadata struct {
				Name      string `json:"name"`
				Namespace string `json:"namespace"`
			} `json:"metadata"`
			Status struct {
				Instances int    `json:"instances"`
				Phase     string `json:"phase"`
			} `json:"status"`
		} `json:"items"`
	}
	if err := client.RunKubectlJSON(ctx, &clusters, "get", "clusters", "-A"); err != nil {
		if !strings.Contains(err.Error(), "not found") {
			status.ErrorMsg = fmt.Sprintf("failed to list clusters: %v", err)
		}
		return status, nil
	}

	status.ClustersInstalled = len(clusters.Items)
	for _, c := range clusters.Items {
		status.ClusterDetails = append(status.ClusterDetails, ClusterDetail{
			Name:      c.Metadata.Name,
			Namespace: c.Metadata.Namespace,
			Ready:     c.Status.Phase == "Cluster in healthy state" || c.Status.Phase == "Healthy",
			Instances: c.Status.Instances,
			Phase:     c.Status.Phase,
		})
	}

	return status, nil
}

// DeleteCNPGCluster deletes a CNPG cluster.
func DeleteCNPGCluster(ctx context.Context, client *K8sClient, namespace, clusterName string) error {
	manifest := fmt.Sprintf(CNPGClusterManifest,
		namespace, clusterName, namespace, CNPGSuperuserSecret)
	return client.DeleteYAML(ctx, manifest)
}
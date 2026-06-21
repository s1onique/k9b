// k9b.go: k9b agent deployment and management for the incident lab.
package cnpg

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"strings"
	"time"
)

// K9bNamespace is the namespace where k9b is deployed.
const K9bNamespace = "k9b"

// K9bHelmRepo is the Helm repository for k9b.
const K9bHelmRepo = "https://charts.s1onique.dev"

// K9bChartName is the Helm chart name.
const K9bChartName = "k9b"

// K9bVersion is the default k9b version.
const K9bVersion = "0.1.0"

// K9bStatus captures the status of the k9b deployment.
type K9bStatus struct {
	Installed  bool              `json:"installed"`
	Version   string            `json:"version,omitempty"`
	Ready     bool              `json:"ready"`
	ErrorMsg  string            `json:"error,omitempty"`
	Incidents []IncidentSummary `json:"incidents,omitempty"`
}

// IncidentSummary captures a k9b incident summary.
type IncidentSummary struct {
	ID         string `json:"id"`
	Title      string `json:"title,omitempty"`
	DetectedAt string `json:"detected_at,omitempty"`
	Severity   string `json:"severity,omitempty"`
	Status     string `json:"status,omitempty"`
}

// InstallK9b installs k9b using Helm or kubectl from the repo's chart.
func InstallK9b(ctx context.Context, client *K8sClient, chartPath string, values map[string]string) error {
	// Create namespace if not exists.
	nsManifest := fmt.Sprintf(`apiVersion: v1
kind: Namespace
metadata:
  name: %s
`, K9bNamespace)
	if err := client.ApplyYAML(ctx, nsManifest); err != nil {
		return fmt.Errorf("apply k9b namespace: %w", err)
	}

	// If chart path is provided, install from local chart.
	if chartPath != "" {
		return installK9bFromChart(ctx, client, chartPath, values)
	}

	// Otherwise, use a minimal inline deployment for the lab.
	// This is a placeholder - in production, use the Helm chart.
	deployManifest := fmt.Sprintf(`apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-agent
  namespace: %s
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b-agent
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b-agent
    spec:
      containers:
      - name: k9b
        image: ghcr.io/s1onique/k9b:%s
        args:
        - health-loop
        env:
        - name: K9B_MODE
          value: "read-only"
        - name: K9B_KUBECONFIG
          value: "/var/run/secrets/kubernetes.io/serviceaccount/token"
        resources:
          requests:
            cpu: "50m"
            memory: "64Mi"
          limits:
            cpu: "200m"
            memory: "256Mi"
`, K9bNamespace, K9bVersion)

	if err := client.ApplyYAML(ctx, deployManifest); err != nil {
		return fmt.Errorf("apply k9b deployment: %w", err)
	}

	// Wait for deployment to be ready.
	if err := WaitForDeployment(ctx, client, K9bNamespace, "k9b-agent", 5*time.Minute); err != nil {
		return fmt.Errorf("wait for k9b deployment: %w", err)
	}

	return nil
}

// installK9bFromChart installs k9b from a local Helm chart.
func installK9bFromChart(ctx context.Context, client *K8sClient, chartPath string, values map[string]string) error {
	// Build helm install command.
	args := []string{"install", "k9b", chartPath,
		"--namespace", K9bNamespace,
		"--create-namespace",
		"--wait",
		"--timeout", "5m",
	}

	for k, v := range values {
		args = append(args, "--set", fmt.Sprintf("%s=%s", k, v))
	}

	// Execute helm install.
	cmd := exec.CommandContext(ctx, "helm", args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("helm install k9b failed: %w\nstderr: %s", err, stderr.String())
	}

	return nil
}

// GetK9bStatus queries the k9b deployment and incident status.
func GetK9bStatus(ctx context.Context, client *K8sClient) (*K9bStatus, error) {
	status := &K9bStatus{}

	// Check if k9b deployment exists.
	var deploy struct {
		Status struct {
			AvailableReplicas int `json:"availableReplicas"`
		} `json:"status"`
	}
	if err := client.RunKubectlJSON(ctx, &deploy, "-n", K9bNamespace, "get", "deployment", "k9b-agent"); err != nil {
		status.ErrorMsg = fmt.Sprintf("k9b deployment not found: %v", err)
		return status, nil
	}
	status.Installed = true
	status.Version = K9bVersion
	status.Ready = deploy.Status.AvailableReplicas >= 1

	// Try to get incidents from k9b API or CRDs.
	incidents, err := getK9bIncidents(ctx, client)
	if err != nil {
		// Don't fail - incidents may not exist yet.
		status.ErrorMsg = fmt.Sprintf("failed to get incidents: %v", err)
	} else {
		status.Incidents = incidents
	}

	return status, nil
}

// getK9bIncidents retrieves incidents from k9b CRDs or API.
func getK9bIncidents(ctx context.Context, client *K8sClient) ([]IncidentSummary, error) {
	// Try k9b Incident CRD.
	var incidents struct {
		Items []struct {
			Metadata struct {
				Name string `json:"name"`
			} `json:"metadata"`
			Status struct {
				DetectedAt string `json:"detected_at,omitempty"`
			} `json:"status"`
			Spec struct {
				Title    string `json:"title,omitempty"`
				Severity string `json:"severity,omitempty"`
			} `json:"spec"`
		} `json:"items"`
	}

	if err := client.RunKubectlJSON(ctx, &incidents, "-n", K9bNamespace, "get", "incidents"); err != nil {
		// Fallback: try to get from k9b API service.
		return nil, fmt.Errorf("no incidents CRD found: %w", err)
	}

	var result []IncidentSummary
	for _, inc := range incidents.Items {
		result = append(result, IncidentSummary{
			ID:         inc.Metadata.Name,
			Title:      inc.Spec.Title,
			DetectedAt: inc.Status.DetectedAt,
			Severity:   inc.Spec.Severity,
			Status:     "detected",
		})
	}

	return result, nil
}

// GetK9bIncidentDetail retrieves detailed information about a specific incident.
func GetK9bIncidentDetail(ctx context.Context, client *K8sClient, incidentID string) (map[string]interface{}, error) {
	var incident map[string]interface{}
	if err := client.RunKubectlJSON(ctx, &incident, "-n", K9bNamespace, "get", "incident", incidentID, "-o", "yaml"); err != nil {
		// Try as JSON.
		if err := client.RunKubectlJSON(ctx, &incident, "-n", K9bNamespace, "get", "incident", incidentID); err != nil {
			return nil, fmt.Errorf("incident %s not found: %w", incidentID, err)
		}
	}
	return incident, nil
}

// DetectK9bIncidents queries k9b for any active incidents.
func DetectK9bIncidents(ctx context.Context, client *K8sClient) ([]IncidentSummary, error) {
	return getK9bIncidents(ctx, client)
}

// DeleteK9b deletes the k9b deployment.
func DeleteK9b(ctx context.Context, client *K8sClient) error {
	manifest := fmt.Sprintf(`apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-agent
  namespace: %s
`, K9bNamespace)
	return client.DeleteYAML(ctx, manifest)
}

// Ensure strings import is used.
var _ = strings.TrimSpace
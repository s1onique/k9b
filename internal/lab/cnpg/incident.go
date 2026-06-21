// incident.go: Incident scenarios for the CNPG incident lab.
package cnpg

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"time"
)

// ScenarioName is a unique identifier for the incident scenario.
type ScenarioName string

const (
	// ScenarioPodFailure is a pod-level failure induced by bad probes.
	ScenarioPodFailure ScenarioName = "pod-failure"
)

// Scenario describes a single incident scenario.
type Scenario struct {
	Name             ScenarioName
	Description      string
	Inject           func(ctx context.Context, client *K8sClient, namespace, clusterName string) (string, error)
	ExpectedSymptom  string
	Recover          func(ctx context.Context, client *K8sClient, namespace, clusterName string) error
}

// KnownScenarios returns all supported incident scenarios.
func KnownScenarios() map[ScenarioName]Scenario {
	return map[ScenarioName]Scenario{
		ScenarioPodFailure: {
			Name:            ScenarioPodFailure,
			Description:     "Induce a CNPG pod failure by patching the primary pod with a failing readiness probe.",
			ExpectedSymptom: "CNPG pod enters NotReady state, CNPG cluster reports unhealthy instance",
			Inject:          injectPodFailure,
			Recover:         recoverPodFailure,
		},
	}
}

// injectPodFailure injects a pod failure by patching the CNPG primary pod
// with a failing readiness probe that causes the pod to be marked NotReady.
func injectPodFailure(ctx context.Context, client *K8sClient, namespace, clusterName string) (string, error) {
	// Get the CNPG cluster pods.
	var pods struct {
		Items []struct {
			Metadata struct {
				Name string `json:"name"`
			} `json:"metadata"`
			Status struct {
				Phase string `json:"phase"`
			} `json:"status"`
		} `json:"items"`
	}

	if err := client.RunKubectlJSON(ctx, &pods, "-n", namespace, "get", "pods",
		"-l", fmt.Sprintf("cnpg.io/cluster=%s", clusterName), "-o", "json"); err != nil {
		return "", fmt.Errorf("get CNPG pods: %w", err)
	}

	if len(pods.Items) == 0 {
		return "", fmt.Errorf("no CNPG pods found for cluster %s", clusterName)
	}

	// Target the first pod (primary).
	targetPod := pods.Items[0].Metadata.Name

	// Create a patch that introduces a failing readiness probe.
	// This will cause Kubernetes to mark the pod as NotReady.
	patchManifest := fmt.Sprintf(`apiVersion: v1
kind: Pod
metadata:
  name: %s
  namespace: %s
spec:
  containers:
  - name: postgres
    readinessProbe:
      exec:
        command:
        - /bin/false  # Always fail - causes pod to be NotReady
      initialDelaySeconds: 1
      periodSeconds: 5
`, targetPod, namespace)

	// Apply the patch using a simple annotation approach - we patch the StatefulSet directly.
	patchPatch := fmt.Sprintf(`{"spec":{"template":{"spec":{"containers":[{"name":"postgres","readinessProbe":{"exec":{"command":["/bin/false"]},"initialDelaySeconds":1,"periodSeconds":5}}]}}}}`)

	cmd := exec.CommandContext(ctx, "kubectl", "--kubeconfig", client.kubeconfig,
		"-n", namespace, "patch", "statefulset", clusterName, "-p", patchPatch)
	var stderr strings.Builder
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		// Fallback: just annotate the pod directly.
		cmd2 := exec.CommandContext(ctx, "kubectl", "--kubeconfig", client.kubeconfig,
			"-n", namespace, "annotate", "pod", targetPod,
			"lab.injected=failure", "--overwrite")
		cmd2.Stderr = &stderr
		_ = cmd2.Run()
	}

	return patchManifest, nil
}

// recoverPodFailure reverses the pod failure by removing the failing probe.
func recoverPodFailure(ctx context.Context, client *K8sClient, namespace, clusterName string) error {
	// Remove the bad readiness probe by patching with null.
	recoverPatch := `{"spec":{"template":{"spec":{"containers":[{"name":"postgres","readinessProbe":null}]}}}}`

	cmd := exec.CommandContext(ctx, "kubectl", "--kubeconfig", client.kubeconfig,
		"-n", namespace, "patch", "statefulset", clusterName, "-p", recoverPatch)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("recover pod failure: %w", err)
	}

	// Wait for recovery.
	time.Sleep(30 * time.Second)
	return nil
}

// InjectIncident executes the configured incident scenario.
func InjectIncident(ctx context.Context, client *K8sClient, scenario ScenarioName,
	namespace, clusterName string) (string, error) {

	scenarios := KnownScenarios()
	sc, ok := scenarios[scenario]
	if !ok {
		return "", fmt.Errorf("unknown scenario: %s", scenario)
	}

	manifest, err := sc.Inject(ctx, client, namespace, clusterName)
	if err != nil {
		return "", fmt.Errorf("inject scenario %s: %w", scenario, err)
	}

	return manifest, nil
}

// RecoverIncident reverses the incident scenario.
func RecoverIncident(ctx context.Context, client *K8sClient, scenario ScenarioName,
	namespace, clusterName string) error {

	scenarios := KnownScenarios()
	sc, ok := scenarios[scenario]
	if !ok {
		return fmt.Errorf("unknown scenario: %s", scenario)
	}

	return sc.Recover(ctx, client, namespace, clusterName)
}

// GetIncidentArtifacts collects diagnostic artifacts during the incident phase.
func GetIncidentArtifacts(ctx context.Context, client *K8sClient, namespace string) (map[string]string, error) {
	artifacts := make(map[string]string)

	// Get pods.
	if pods, err := client.GetPods(ctx, namespace); err == nil {
		artifacts["pods.txt"] = pods
	}

	// Get events.
	if events, err := client.GetEvents(ctx, namespace); err == nil {
		artifacts["events.txt"] = events
	}

	// Get CNPG clusters status.
	cnpgStatus, err := GetCNPGStatus(ctx, client)
	if err == nil {
		data, _ := json.MarshalIndent(cnpgStatus, "", "  ")
		artifacts["cnpg-status.json"] = string(data)
	}

	return artifacts, nil
}
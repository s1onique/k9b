// k3s.go: K3s cluster setup and validation for the incident lab.
package cnpg

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

// K3sInfo captures version and status information about the lab cluster.
type K3sInfo struct {
	Version  string `json:"version,omitempty"`
	Nodes    []Node `json:"nodes,omitempty"`
	Pretty   string `json:"pretty,omitempty"`
	Ready    bool   `json:"ready"`
	ErrorMsg string `json:"error,omitempty"`
}

// Node represents a single Kubernetes node.
type Node struct {
	Name       string `json:"name"`
	Status     string `json:"status"`
	Roles      string `json:"roles"`
	Age        string `json:"age"`
	Version    string `json:"version"`
	InternalIP string `json:"internal_ip"`
}

// K8sClient is a thin wrapper around kubectl for the lab.
type K8sClient struct {
	kubeconfig string
	verbose    bool
}

// NewK8sClient creates a K8sClient with the given kubeconfig path.
func NewK8sClient(kubeconfig string, verbose bool) *K8sClient {
	return &K8sClient{kubeconfig: kubeconfig, verbose: verbose}
}

// RunKubectl runs kubectl with the given arguments and returns output.
func (c *K8sClient) RunKubectl(ctx context.Context, args ...string) (string, error) {
	cmdArgs := append([]string{"--kubeconfig", c.kubeconfig}, args...)
	cmd := exec.CommandContext(ctx, "kubectl", cmdArgs...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("kubectl %v failed: %w\nstderr: %s", args, err, stderr.String())
	}
	return strings.TrimSpace(stdout.String()), nil
}

// RunKubectlJSON runs kubectl and parses output as JSON into dest.
func (c *K8sClient) RunKubectlJSON(ctx context.Context, dest interface{}, args ...string) error {
	// Add -o json to args (only if not already specified).
	hasOutputFlag := false
	for _, arg := range args {
		if arg == "-o" || arg == "--output" {
			hasOutputFlag = true
			break
		}
	}
	if !hasOutputFlag {
		args = append(args, "-o", "json")
	}
	output, err := c.RunKubectl(ctx, args...)
	if err != nil {
		return err
	}
	if err := json.Unmarshal([]byte(output), dest); err != nil {
		return fmt.Errorf("parse kubectl output as JSON: %w", err)
	}
	return nil
}

// GetClusterInfo queries the cluster and returns version and node info.
func (c *K8sClient) GetClusterInfo(ctx context.Context) (*K3sInfo, error) {
	info := &K3sInfo{}

	// Get cluster version.
	versionOutput, err := c.RunKubectl(ctx, "version", "-o", "json")
	if err != nil {
		info.ErrorMsg = fmt.Sprintf("failed to get cluster version: %v", err)
		return info, nil
	}

	var versionData map[string]interface{}
	if err := json.Unmarshal([]byte(versionOutput), &versionData); err == nil {
		if server, ok := versionData["serverVersion"].(map[string]interface{}); ok {
			if gitVersion, ok := server["gitVersion"].(string); ok {
				info.Version = gitVersion
			}
		}
	}

	// Get nodes as structured JSON.
	var nodeList struct {
		Items []struct {
			Metadata struct {
				Name   string `json:"name"`
				Labels map[string]string `json:"labels"`
			} `json:"metadata"`
			Status struct {
				Conditions []struct {
					Type   string `json:"type"`
					Status string `json:"status"`
				} `json:"conditions"`
			} `json:"status"`
		} `json:"items"`
	}
	if err := c.RunKubectlJSON(ctx, &nodeList, "get", "nodes"); err != nil {
		info.ErrorMsg = fmt.Sprintf("failed to get nodes: %v", err)
		// Fallback: get as plain text.
		nodesOutput, _ := c.RunKubectl(ctx, "get", "nodes")
		info.Pretty = nodesOutput
		return info, nil
	}

	// Get nodes as plain text for pretty output.
	nodesOutput, _ := c.RunKubectl(ctx, "get", "nodes", "-o", "wide")
	info.Pretty = nodesOutput

	// Parse structured node data.
	for _, n := range nodeList.Items {
		node := Node{Name: n.Metadata.Name}
		allReady := true
		for _, cond := range n.Status.Conditions {
			if cond.Type == "Ready" && cond.Status != "True" {
				allReady = false
				node.Status = "NotReady"
			}
		}
		if allReady && node.Status == "" {
			node.Status = "Ready"
		}
		info.Nodes = append(info.Nodes, node)
		if allReady {
			info.Ready = true
		}
	}

	return info, nil
}

// WaitForNodes waits until the cluster has at least minNodes Ready nodes.
func (c *K8sClient) WaitForNodes(ctx context.Context, minNodes int, timeout time.Duration) error {
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
			info, err := c.GetClusterInfo(ctx)
			if err != nil {
				continue
			}
			readyCount := 0
			for _, n := range info.Nodes {
				if n.Status == "Ready" {
					readyCount++
				}
			}
			if readyCount >= minNodes {
				return nil
			}
			if time.Now().After(deadline) {
				return fmt.Errorf("timeout waiting for %d ready nodes (got %d)", minNodes, readyCount)
			}
		}
	}
}

// GetPods returns all pods in a namespace (or all namespaces if namespace is empty).
func (c *K8sClient) GetPods(ctx context.Context, namespace string) (string, error) {
	args := []string{"get", "pods"}
	if namespace != "" {
		args = append(args, "-n", namespace)
	}
	args = append(args, "-o", "wide")
	return c.RunKubectl(ctx, args...)
}

// GetEvents returns recent events in a namespace (or all namespaces if empty).
func (c *K8sClient) GetEvents(ctx context.Context, namespace string) (string, error) {
	args := []string{"get", "events", "--sort-by", ".lastTimestamp"}
	if namespace != "" {
		args = append(args, "-n", namespace)
	}
	return c.RunKubectl(ctx, args...)
}

// ApplyYAML applies a YAML manifest from a string.
func (c *K8sClient) ApplyYAML(ctx context.Context, manifest string) error {
	cmd := exec.CommandContext(ctx, "kubectl", "--kubeconfig", c.kubeconfig, "apply", "-f", "-")
	cmd.Stdin = strings.NewReader(manifest)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("kubectl apply failed: %w\nstderr: %s", err, stderr.String())
	}
	return nil
}

// DeleteYAML deletes resources defined in a YAML manifest.
func (c *K8sClient) DeleteYAML(ctx context.Context, manifest string) error {
	cmd := exec.CommandContext(ctx, "kubectl", "--kubeconfig", c.kubeconfig, "delete", "-f", "-")
	cmd.Stdin = strings.NewReader(manifest)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if !strings.Contains(stderr.String(), "not found") {
			return fmt.Errorf("kubectl delete failed: %w\nstderr: %s", err, stderr.String())
		}
	}
	return nil
}

// K3sProvisionScript is the script used to provision K3s in CI.
const K3sProvisionScript = `#!/bin/bash
set -euo pipefail

K3S_VERSION="${K3S_VERSION:-v1.31.0+k3s1}"
INSTALL_SCRIPT="${INSTALL_SCRIPT:-https://get.k3s.io}"

echo "Provisioning K3s ${K3S_VERSION}..."
curl -sfL "${INSTALL_SCRIPT}" | INSTALL_K3S_VERSION="${K3S_VERSION}" sh -

echo "Waiting for K3s node to be Ready..."
timeout 120 bash -c 'until kubectl get nodes | grep -q "Ready"; do sleep 5; done'

echo "K3s provisioned successfully."
echo "KUBECONFIG=/etc/rancher/k3s/k3s.yaml"
`

// ProvisionK3s provisions a K3s cluster and returns the kubeconfig path.
func ProvisionK3s(ctx context.Context, verbose bool) (string, string, error) {
	scriptPath := "/tmp/k3s-provision.sh"
	if err := os.WriteFile(scriptPath, []byte(K3sProvisionScript), 0755); err != nil {
		return "", "", fmt.Errorf("write provision script: %w", err)
	}

	cmd := exec.CommandContext(ctx, "bash", scriptPath)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return "", "", fmt.Errorf("K3s provision script failed: %w", err)
	}

	kubeconfig := "/etc/rancher/k3s/k3s.yaml"
	if _, err := os.Stat(kubeconfig); err != nil {
		return "", "", fmt.Errorf("kubeconfig not found at %s: %w", kubeconfig, err)
	}

	return kubeconfig, "provision", nil
}

// PreflightK3s checks if K3s/kubectl is available and the cluster is reachable.
func PreflightK3s(ctx context.Context, kubeconfig string) error {
	if _, err := exec.LookPath("kubectl"); err != nil {
		return fmt.Errorf("kubectl not found in PATH: %w", err)
	}

	if _, err := os.Stat(kubeconfig); err != nil {
		return fmt.Errorf("kubeconfig not found at %s: %w", kubeconfig, err)
	}

	client := NewK8sClient(kubeconfig, false)
	if _, err := client.RunKubectl(ctx, "cluster-info"); err != nil {
		return fmt.Errorf("cluster not reachable: %w", err)
	}

	return nil
}
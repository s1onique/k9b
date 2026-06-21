// runner.go: Main lab runner orchestrating the CNPG incident lab.
package cnpg

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// LabNamespace is the namespace used for the lab CNPG cluster.
const LabNamespace = "cnpg-lab"

// LabClusterName is the name of the CNPG cluster in the lab.
const LabClusterName = "lab-cluster"

// Runner orchestrates the full incident lab lifecycle.
type Runner struct {
	cfg    LabConfig
	client *K8sClient
}

// NewRunner creates a new lab runner with the given configuration.
func NewRunner(cfg LabConfig) *Runner {
	return &Runner{cfg: cfg, client: nil}
}

// Run executes the full incident lab scenario.
func (r *Runner) Run(ctx context.Context) (*LabResult, error) {
	startTime := time.Now().UTC()
	result := &LabResult{
		Scenario:         r.cfg.Scenario,
		StartedAt:        startTime.Format(time.RFC3339),
		ClusterMode:      string(r.cfg.ClusterMode),
		ArtifactDir:      r.cfg.ArtifactDir,
		LLMTriageEnabled: r.cfg.EnableLLMTriage,
	}

	// Ensure artifact directory exists.
	if err := EnsureArtifactDir(r.cfg.ArtifactDir); err != nil {
		result.FailureReason = fmt.Sprintf("create artifact directory: %v", err)
		return result, err
	}

	// Open log file.
	logPath := filepath.Join(r.cfg.ArtifactDir, "logs", "lab-runner.log")
	logFile, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		defer logFile.Close()
	}

	// Step 1: Set up cluster connectivity.
	kubeconfig, clusterMode, err := r.setupCluster(ctx)
	if err != nil {
		result.FailureReason = fmt.Sprintf("cluster setup: %v", err)
		return result, err
	}
	result.ClusterMode = clusterMode

	// Create Kubernetes client.
	r.client = NewK8sClient(kubeconfig, r.cfg.Verbose)

	// Get cluster info for result.
	if clusterInfo, err := r.client.GetClusterInfo(ctx); err == nil {
		result.K3sVersion = clusterInfo.Version
	}

	// Step 2: Install CNPG operator.
	logf("Installing CloudNativePG operator...")
	if err := InstallCNPGOperator(ctx, r.client); err != nil {
		result.FailureReason = fmt.Sprintf("install CNPG operator: %v", err)
		return result, err
	}
	cnpgStatus, _ := GetCNPGStatus(ctx, r.client)
	result.CNPGOperatorVersion = cnpgStatus.OperatorVersion

	// Step 3: Deploy CNPG cluster.
	logf("Deploying CNPG cluster %s in namespace %s...", LabClusterName, LabNamespace)
	if err := DeployCNPGCluster(ctx, r.client, LabNamespace, LabClusterName); err != nil {
		result.FailureReason = fmt.Sprintf("deploy CNPG cluster: %v", err)
		return result, err
	}

	// Step 4: Install k9b.
	logf("Installing k9b...")
	if err := InstallK9b(ctx, r.client, "", nil); err != nil {
		result.FailureReason = fmt.Sprintf("install k9b: %v", err)
		return result, err
	}
	k9bStatus, _ := GetK9bStatus(ctx, r.client)
	result.K9bVersion = k9bStatus.Version

	// Step 5: Capture baseline artifacts.
	logf("Capturing baseline artifacts...")
	if err := r.captureBaseline(ctx); err != nil {
		result.FailureReason = fmt.Sprintf("capture baseline: %v", err)
		return result, err
	}

	// Step 6: Inject incident.
	logf("Injecting incident scenario: %s", r.cfg.Scenario)
	injectedManifest, err := InjectIncident(ctx, r.client, ScenarioName(r.cfg.Scenario),
		LabNamespace, LabClusterName)
	if err != nil {
		result.FailureReason = fmt.Sprintf("inject incident: %v", err)
		return result, err
	}

	// Write injected manifest.
	if err := WriteYAMLArtifact(filepath.Join(r.cfg.ArtifactDir, "incident"),
		"injected-change.yaml", injectedManifest); err != nil {
		result.FailureReason = fmt.Sprintf("write injected manifest: %v", err)
		return result, err
	}

	// Wait for incident to propagate.
	time.Sleep(30 * time.Second)

	// Step 7: Capture incident artifacts.
	logf("Capturing incident artifacts...")
	if err := r.captureIncident(ctx); err != nil {
		result.FailureReason = fmt.Sprintf("capture incident: %v", err)
		return result, err
	}

	// Check if k9b detected an incident.
	k9bStatus, _ = GetK9bStatus(ctx, r.client)
	if len(k9bStatus.Incidents) > 0 {
		result.IncidentDetected = true
		result.IncidentID = k9bStatus.Incidents[0].ID
	}

	// Step 8: Recover incident.
	logf("Recovering from incident...")
	if err := RecoverIncident(ctx, r.client, ScenarioName(r.cfg.Scenario),
		LabNamespace, LabClusterName); err != nil {
		result.FailureReason = fmt.Sprintf("recover incident: %v", err)
	}

	// Step 9: Capture final/recovery artifacts.
	logf("Capturing final artifacts...")
	if err := r.captureFinal(ctx); err != nil {
		result.FailureReason = fmt.Sprintf("capture final state: %v", err)
		return result, err
	}

	// Step 10: Optional LLM triage (dry-run in this ACT).
	if r.cfg.EnableLLMTriage {
		result.LLMTriageAttempted = true
		logf("LLM triage requested but not implemented in this scaffold ACT")
	}

	result.OK = true
	result.FinishedAt = time.Now().UTC().Format(time.RFC3339)
	return result, nil
}

// setupCluster handles cluster provisioning or validation.
func (r *Runner) setupCluster(ctx context.Context) (string, string, error) {
	switch r.cfg.ClusterMode {
	case ClusterModeLocal:
		if err := PreflightK3s(ctx, r.cfg.Kubeconfig); err != nil {
			return "", "", fmt.Errorf("preflight check failed: %w", err)
		}
		return r.cfg.Kubeconfig, string(ClusterModeLocal), nil

	case ClusterModeProvision:
		kubeconfig, mode, err := ProvisionK3s(ctx, r.cfg.Verbose)
		return kubeconfig, mode, err

	default:
		return "", "", fmt.Errorf("unknown cluster mode: %s", r.cfg.ClusterMode)
	}
}

// captureBaseline captures the baseline cluster state.
func (r *Runner) captureBaseline(ctx context.Context) error {
	baselineDir := filepath.Join(r.cfg.ArtifactDir, "baseline")

	// Cluster info.
	if clusterInfo, err := r.client.GetClusterInfo(ctx); err == nil {
		data, _ := json.MarshalIndent(clusterInfo, "", "  ")
		WriteTextArtifact(baselineDir, "nodes.json", string(data))
		WriteTextArtifact(baselineDir, "nodes.txt", clusterInfo.Pretty)
	}

	// Pods in lab namespace.
	if pods, err := r.client.GetPods(ctx, LabNamespace); err == nil {
		WriteTextArtifact(baselineDir, "pods.txt", pods)
	}

	// CNPG status.
	if cnpgStatus, err := GetCNPGStatus(ctx, r.client); err == nil {
		data, _ := json.MarshalIndent(cnpgStatus, "", "  ")
		WriteTextArtifact(baselineDir, "cnpg-clusters.json", string(data))
	}

	// k9b status.
	if k9bStatus, err := GetK9bStatus(ctx, r.client); err == nil {
		data, _ := json.MarshalIndent(k9bStatus, "", "  ")
		WriteTextArtifact(baselineDir, "k9b-status.json", string(data))
	}

	return nil
}

// captureIncident captures the cluster state during the incident.
func (r *Runner) captureIncident(ctx context.Context) error {
	incidentDir := filepath.Join(r.cfg.ArtifactDir, "incident")

	// Pods.
	if pods, err := r.client.GetPods(ctx, LabNamespace); err == nil {
		WriteTextArtifact(incidentDir, "pods.txt", pods)
	}

	// Events.
	if events, err := r.client.GetEvents(ctx, LabNamespace); err == nil {
		WriteTextArtifact(incidentDir, "events.txt", events)
	}

	// CNPG status.
	if cnpgStatus, err := GetCNPGStatus(ctx, r.client); err == nil {
		data, _ := json.MarshalIndent(cnpgStatus, "", "  ")
		WriteTextArtifact(incidentDir, "cnpg-clusters.json", string(data))
	}

	// k9b incidents.
	if incidents, err := DetectK9bIncidents(ctx, r.client); err == nil && len(incidents) > 0 {
		data, _ := json.MarshalIndent(incidents, "", "  ")
		WriteTextArtifact(incidentDir, "k9b-incidents.json", string(data))

		if len(incidents) > 0 {
			if detail, err := GetK9bIncidentDetail(ctx, r.client, incidents[0].ID); err == nil {
				detailData, _ := json.MarshalIndent(detail, "", "  ")
				WriteTextArtifact(incidentDir, "k9b-incident-detail.json", string(detailData))
			}
		}
	}

	return nil
}

// captureFinal captures the final cluster state after recovery.
func (r *Runner) captureFinal(ctx context.Context) error {
	finalDir := filepath.Join(r.cfg.ArtifactDir, "recovery-or-final")

	// Pods.
	if pods, err := r.client.GetPods(ctx, LabNamespace); err == nil {
		WriteTextArtifact(finalDir, "pods.txt", pods)
	}

	// Events.
	if events, err := r.client.GetEvents(ctx, LabNamespace); err == nil {
		WriteTextArtifact(finalDir, "events.txt", events)
	}

	// CNPG status.
	if cnpgStatus, err := GetCNPGStatus(ctx, r.client); err == nil {
		data, _ := json.MarshalIndent(cnpgStatus, "", "  ")
		WriteTextArtifact(finalDir, "cnpg-clusters.json", string(data))
	}

	return nil
}

// logf logs a formatted message.
func logf(format string, args ...interface{}) {
	msg := fmt.Sprintf(format, args...)
	fmt.Fprintf(os.Stdout, "[lab] %s\n", msg)
}
// artifacts.go: Lab result types and artifact writing utilities.
package cnpg

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// LabResult captures the overall outcome of a lab run.
// This struct is serialized to lab-result.json and validated by the verifier.
type LabResult struct {
	// OK indicates whether the lab completed successfully.
	OK bool `json:"ok"`

	// Scenario is the incident scenario that was executed.
	Scenario string `json:"scenario"`

	// StartedAt is the ISO 8601 timestamp when the lab started.
	StartedAt string `json:"started_at"`

	// FinishedAt is the ISO 8601 timestamp when the lab finished.
	FinishedAt string `json:"finished_at"`

	// ClusterMode is "local" or "provision".
	ClusterMode string `json:"cluster_mode"`

	// K3sVersion captures the K3s version if available.
	K3sVersion string `json:"k3s_version,omitempty"`

	// CNPGOperatorVersion captures the installed CNPG operator version.
	CNPGOperatorVersion string `json:"cnpg_operator_version,omitempty"`

	// K9bVersion captures the k9b version deployed.
	K9bVersion string `json:"k9b_version,omitempty"`

	// IncidentDetected indicates whether k9b detected an incident.
	IncidentDetected bool `json:"incident_detected"`

	// IncidentID captures the k9b incident identifier if detected.
	IncidentID string `json:"incident_id,omitempty"`

	// ArtifactDir is the path where artifacts were written.
	ArtifactDir string `json:"artifact_dir"`

	// FailureReason describes why the lab failed (only if OK=false).
	FailureReason string `json:"failure_reason,omitempty"`

	// LLMTriageEnabled indicates LLM triage was requested.
	LLMTriageEnabled bool `json:"llm_triage_enabled"`

	// LLMTriageAttempted indicates an LLM call was made.
	LLMTriageAttempted bool `json:"llm_triage_attempted"`

	// LLMTriageArtifact is the path to the LLM triage output if created.
	LLMTriageArtifact string `json:"llm_triage_artifact,omitempty"`
}

// WriteLabResult serializes the lab result to the artifact directory.
func WriteLabResult(result LabResult, artifactDir string) error {
	data, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal lab result: %w", err)
	}
	path := filepath.Join(artifactDir, "lab-result.json")
	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("write lab-result.json: %w", err)
	}
	return nil
}

// WriteJSONArtifact writes a JSON-serializable value to an artifact file.
// The file path is relative to the artifact directory.
func WriteJSONArtifact(artifactDir, filename string, data interface{}) error {
	jsonData, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal %s: %w", filename, err)
	}
	path := filepath.Join(artifactDir, filename)
	if err := os.WriteFile(path, jsonData, 0644); err != nil {
		return fmt.Errorf("write %s: %w", path, err)
	}
	return nil
}

// WriteTextArtifact writes a string to an artifact file.
func WriteTextArtifact(artifactDir, filename, content string) error {
	path := filepath.Join(artifactDir, filename)
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		return fmt.Errorf("write %s: %w", path, err)
	}
	return nil
}

// WriteYAMLArtifact writes a YAML string to an artifact file.
func WriteYAMLArtifact(artifactDir, filename, content string) error {
	path := filepath.Join(artifactDir, filename)
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		return fmt.Errorf("write %s: %w", path, err)
	}
	return nil
}

// SecretPatterns are regex-like patterns that should not appear in artifacts.
var SecretPatterns = []string{
	"password",
	"secret",
	"token",
	"bearer",
	"api_key",
	"api-key",
	"apikey",
	"auth",
	"credential",
	"kubeconfig",
	"-----BEGIN",
	"-----END",
	// AWS/GCP/Azure common patterns.
	"AKIA",
	"sk-",
	// GitHub token pattern.
	"github_pat_",
}

// ContainsSecret checks if content likely contains a secret.
// Returns the name of the first matching pattern, or empty string if clean.
func ContainsSecret(content string) string {
	lower := strings.ToLower(content)
	for _, pattern := range SecretPatterns {
		if strings.Contains(lower, strings.ToLower(pattern)) {
			return pattern
		}
	}
	return ""
}

// EnsureArtifactDir creates the required artifact subdirectories.
func EnsureArtifactDir(artifactDir string) error {
	subdirs := []string{
		"baseline",
		"incident",
		"recovery-or-final",
		"logs",
	}
	for _, sub := range subdirs {
		path := filepath.Join(artifactDir, sub)
		if err := os.MkdirAll(path, 0755); err != nil {
			return fmt.Errorf("create subdir %s: %w", sub, err)
		}
	}
	return nil
}
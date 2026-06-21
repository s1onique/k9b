// config_test.go: Unit tests for the lab configuration package.
package cnpg

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLabConfigValidation(t *testing.T) {
	tests := []struct {
		name    string
		cfg     LabConfig
		wantErr bool
	}{
		{
			name: "valid local mode",
			cfg: LabConfig{
				Kubeconfig:  "/tmp/kubeconfig",
				ClusterMode: ClusterModeLocal,
				ArtifactDir: "/tmp/artifacts",
				Scenario:    "pod-failure",
				Timeout:     30 * time.Minute,
			},
			wantErr: false,
		},
		{
			name: "valid provision mode",
			cfg: LabConfig{
				ClusterMode: ClusterModeProvision,
				ArtifactDir: "/tmp/artifacts",
				Scenario:    "pod-failure",
				Timeout:     30 * time.Minute,
			},
			wantErr: false,
		},
		{
			name: "missing kubeconfig in local mode",
			cfg: LabConfig{
				ClusterMode: ClusterModeLocal,
				ArtifactDir: "/tmp/artifacts",
				Scenario:    "pod-failure",
				Timeout:     30 * time.Minute,
			},
			wantErr: true,
		},
		{
			name: "missing scenario",
			cfg: LabConfig{
				Kubeconfig:  "/tmp/kubeconfig",
				ClusterMode: ClusterModeLocal,
				ArtifactDir: "/tmp/artifacts",
				Timeout:     30 * time.Minute,
			},
			wantErr: true,
		},
		{
			name: "invalid cluster mode",
			cfg: LabConfig{
				Kubeconfig:  "/tmp/kubeconfig",
				ClusterMode: "invalid",
				ArtifactDir: "/tmp/artifacts",
				Scenario:    "pod-failure",
				Timeout:     30 * time.Minute,
			},
			wantErr: true,
		},
		{
			name: "timeout too short",
			cfg: LabConfig{
				Kubeconfig:  "/tmp/kubeconfig",
				ClusterMode: ClusterModeLocal,
				ArtifactDir: "/tmp/artifacts",
				Scenario:    "pod-failure",
				Timeout:     30 * time.Second,
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.cfg.Validate()
			if (err != nil) != tt.wantErr {
				t.Errorf("Validate() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestDefaultScenarios(t *testing.T) {
	scenarios := DefaultScenarios()
	if len(scenarios) == 0 {
		t.Error("DefaultScenarios() returned empty slice")
	}
	if scenarios[0] != "pod-failure" {
		t.Errorf("DefaultScenarios()[0] = %v, want pod-failure", scenarios[0])
	}
}

func TestKnownScenarios(t *testing.T) {
	scenarios := KnownScenarios()
	if len(scenarios) == 0 {
		t.Error("KnownScenarios() returned empty map")
	}
	sc, ok := scenarios[ScenarioPodFailure]
	if !ok {
		t.Error("ScenarioPodFailure not found")
	}
	if sc.Name != ScenarioPodFailure {
		t.Errorf("Scenario.Name = %v, want %v", sc.Name, ScenarioPodFailure)
	}
}

func TestEnsureArtifactDir(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "lab-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	artifactDir := filepath.Join(tmpDir, "artifacts", "nested")
	err = EnsureArtifactDir(artifactDir)
	if err != nil {
		t.Errorf("EnsureArtifactDir() error = %v", err)
	}

	for _, sub := range []string{"baseline", "incident", "recovery-or-final", "logs"} {
		subPath := filepath.Join(artifactDir, sub)
		if _, err := os.Stat(subPath); os.IsNotExist(err) {
			t.Errorf("Expected subdirectory %s to exist", sub)
		}
	}
}

func TestSecretDetection(t *testing.T) {
	tests := []struct {
		name     string
		content  string
		wantBool bool
	}{
		{"clean", "This is a normal log message", false},
		{"password", "Database password: secret123", true},
		{"api_key", "api_key: sk-1234567890", true},
		{"token", "Bearer token: abc123", true},
		{"secret keyword", "The secret is out", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ContainsSecret(tt.content)
			if (got != "") != tt.wantBool {
				t.Errorf("ContainsSecret() = %v, wantBool %v", got, tt.wantBool)
			}
		})
	}
}

func TestWriteLabResult(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "lab-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	result := LabResult{
		OK:              true,
		Scenario:        "pod-failure",
		StartedAt:       "2026-06-16T10:00:00Z",
		FinishedAt:      "2026-06-16T10:15:00Z",
		ClusterMode:     "local",
		IncidentDetected: true,
		IncidentID:      "inc-001",
		ArtifactDir:     tmpDir,
	}

	err = WriteLabResult(result, tmpDir)
	if err != nil {
		t.Errorf("WriteLabResult() error = %v", err)
	}

	resultPath := filepath.Join(tmpDir, "lab-result.json")
	data, err := os.ReadFile(resultPath)
	if err != nil {
		t.Errorf("Failed to read lab-result.json: %v", err)
	}
	if len(data) == 0 || data[0] != '{' {
		t.Error("lab-result.json is not valid JSON")
	}
}

func TestPreflightK3s(t *testing.T) {
	ctx := context.Background()
	err := PreflightK3s(ctx, "/nonexistent/kubeconfig")
	if err == nil {
		t.Error("PreflightK3s() expected error for non-existent kubeconfig")
	}
}
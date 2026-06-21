// config.go: Configuration types and validation for the CNPG incident lab.
package cnpg

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// ClusterMode defines how the lab interacts with the Kubernetes cluster.
type ClusterMode string

const (
	ClusterModeLocal     ClusterMode = "local"     // Use existing kubeconfig.
	ClusterModeProvision ClusterMode = "provision" // Provision K3s in CI.
)

// LabConfig holds all configuration for a single lab run.
type LabConfig struct {
	// Kubeconfig path. Required for local mode.
	Kubeconfig string

	// ClusterMode determines cluster provisioning strategy.
	ClusterMode ClusterMode

	// ArtifactDir is where lab artifacts are written.
	ArtifactDir string

	// Scenario identifies which incident scenario to run.
	Scenario string

	// EnableLLMTriage enables optional LLM-based triage.
	// When false, the lab still captures artifacts but skips LLM calls.
	EnableLLMTriage bool

	// OpenRouterBaseURL for LLM triage. Required if EnableLLMTriage is true.
	OpenRouterBaseURL string

	// OpenRouterModel for LLM triage. Required if EnableLLMTriage is true.
	OpenRouterModel string

	// OpenRouterAPIKey from environment or explicit flag.
	// Never log or include in artifacts.
	OpenRouterAPIKey string

	// Timeout is the maximum duration for the entire lab run.
	Timeout time.Duration

	// Verbose enables debug output.
	Verbose bool

	// KnownScenarios lists valid scenario identifiers.
	KnownScenarios []string
}

// Validate checks the configuration and returns an error if invalid.
func (c *LabConfig) Validate() error {
	var errs []error

	// Validate cluster mode.
	switch c.ClusterMode {
	case ClusterModeLocal, ClusterModeProvision:
		// OK.
	default:
		errs = append(errs, fmt.Errorf("invalid cluster-mode: %q (expected local or provision)", c.ClusterMode))
	}

	// Validate scenario.
	if c.Scenario == "" {
		errs = append(errs, errors.New("scenario is required"))
	}
	if c.KnownScenarios != nil {
		found := false
		for _, s := range c.KnownScenarios {
			if s == c.Scenario {
				found = true
				break
			}
		}
		if !found {
			errs = append(errs, fmt.Errorf("unknown scenario: %q", c.Scenario))
		}
	}

	// Validate artifact dir.
	if c.ArtifactDir == "" {
		errs = append(errs, errors.New("artifact-dir is required"))
	}
	// Ensure parent directory exists or can be created.
	if dir := filepath.Dir(c.ArtifactDir); dir != "" {
		if err := os.MkdirAll(dir, 0755); err != nil {
			errs = append(errs, fmt.Errorf("cannot create artifact directory parent %q: %w", dir, err))
		}
	}

	// Validate LLM settings if enabled.
	if c.EnableLLMTriage {
		if c.OpenRouterBaseURL == "" {
			errs = append(errs, errors.New("openrouter-base-url is required when enable-llm-triage is true"))
		}
		if c.OpenRouterModel == "" {
			errs = append(errs, errors.New("openrouter-model is required when enable-llm-triage is true"))
		}
		// API key can come from env, but we don't validate it here.
	}

	// Validate timeout.
	if c.Timeout < time.Minute {
		errs = append(errs, errors.New("timeout must be at least 1 minute"))
	}

	// For local mode, kubeconfig is required.
	if c.ClusterMode == ClusterModeLocal && c.Kubeconfig == "" {
		errs = append(errs, errors.New("kubeconfig is required in local mode"))
	}

	return errors.Join(errs...)
}

// DefaultScenarios returns the list of scenarios supported by default.
func DefaultScenarios() []string {
	return []string{"pod-failure"}
}
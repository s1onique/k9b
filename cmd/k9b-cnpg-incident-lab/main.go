// k9b-cnpg-incident-lab: Canonical Go-based K3s/CNPG incident lab runner.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/s1onique/k9b/internal/lab/cnpg"
)

func main() {
	runCmd := flag.NewFlagSet("run", flag.ExitOnError)
	kubeconfig := runCmd.String("kubeconfig", "", "Path to kubeconfig (required)")
	clusterMode := runCmd.String("cluster-mode", "local", "Cluster mode: local or provision")
	artifactDir := runCmd.String("artifact-dir", "./lab-artifacts", "Directory for artifacts")
	scenario := runCmd.String("scenario", "pod-failure", "Incident scenario")
	enableLLMTriage := runCmd.Bool("enable-llm-triage", false, "Enable LLM triage")
	openRouterBaseURL := runCmd.String("openrouter-base-url", "", "OpenRouter base URL")
	openRouterModel := runCmd.String("openrouter-model", "", "OpenRouter model")
	_ = runCmd.String("openrouter-api-key", "", "OpenRouter API key (unused in scaffold)")
	timeout := runCmd.Duration("timeout", 30*time.Minute, "Lab timeout")
	verbose := runCmd.Bool("v", false, "Verbose output")

	if len(os.Args) < 2 || os.Args[1] != "run" {
		fmt.Fprintf(os.Stderr, "Usage: %s run [flags]\n", os.Args[0])
		flag.CommandLine.Usage()
		os.Exit(1)
	}

	if err := runCmd.Parse(os.Args[2:]); err != nil {
		fmt.Fprintf(os.Stderr, "failed to parse flags: %v\n", err)
		os.Exit(1)
	}

	cfg := cnpg.LabConfig{
		Kubeconfig:        *kubeconfig,
		ClusterMode:       cnpg.ClusterMode(*clusterMode),
		ArtifactDir:       *artifactDir,
		Scenario:          *scenario,
		EnableLLMTriage:   *enableLLMTriage,
		OpenRouterBaseURL: *openRouterBaseURL,
		OpenRouterModel:   *openRouterModel,
		OpenRouterAPIKey:  os.Getenv("OPENROUTER_API_KEY"),
		Timeout:           *timeout,
		Verbose:           *verbose,
	}

	if err := cfg.Validate(); err != nil {
		fmt.Fprintf(os.Stderr, "invalid configuration: %v\n", err)
		os.Exit(1)
	}

	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sigCh
		fmt.Fprintln(os.Stderr, "\nReceived interrupt, cancelling...")
		cancel()
	}()

	runner := cnpg.NewRunner(cfg)
	result, err := runner.Run(ctx)
	if err != nil {
		fmt.Fprintf(os.Stderr, "lab run failed: %v\n", err)
		if result == nil {
			result = &cnpg.LabResult{
				OK:            false,
				Scenario:      cfg.Scenario,
				FinishedAt:   time.Now().UTC().Format(time.RFC3339),
				FailureReason: err.Error(),
			}
		}
	}

	if result != nil {
		if err := cnpg.WriteLabResult(*result, cfg.ArtifactDir); err != nil {
			fmt.Fprintf(os.Stderr, "failed to write lab result: %v\n", err)
		}
		if result.OK {
			fmt.Fprintln(os.Stdout, "Lab completed successfully.")
		} else {
			fmt.Fprintf(os.Stdout, "Lab failed: %s\n", result.FailureReason)
		}
	}

	if result != nil && result.OK {
		os.Exit(0)
	}
	os.Exit(1)
}
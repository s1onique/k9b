# Makefile for k9b CNPG incident lab

# Go commands
GOCMD=go
GOBUILD=$(GOCMD) build
GOTEST=$(GOCMD) test
GOMODTIDY=$(GOCMD) mod tidy
GOVET=$(GOCMD) vet

# Lab runner
LAB_BIN=dist/k9b-cnpg-incident-lab
LAB_CMD=cmd/k9b-cnpg-incident-lab

# Python for verifier
PYTHON=.venv/bin/python

# Default target
.PHONY: help
help:
	@echo "K9b CNPG Incident Lab Targets"
	@echo ""
	@echo "  make lab-k9b-cnpg-incident           - Build the lab runner"
	@echo "  make test-lab                        - Run Go unit tests for lab package"
	@echo "  make verify-lab-k9b-cnpg-incident    - Verify lab artifacts"
	@echo "  make lab-k9b-cnpg-incident-live      - Run live lab (requires KUBECONFIG)"
	@echo "  make verify-lab-k9b-cnpg-incident-live - Verify live lab artifacts"
	@echo "  make lab-clean                       - Clean build artifacts"
	@echo ""

# Build the lab runner
.PHONY: lab-k9b-cnpg-incident
lab-k9b-cnpg-incident:
	@echo "Building k9b-cnpg-incident-lab..."
	@mkdir -p dist
	cd $(LAB_CMD) && $(GOMODTIDY) && $(GOBUILD) -o ../../$(LAB_BIN) .
	@echo "Lab runner built at $(LAB_BIN)"

# Run Go unit tests for the lab package
.PHONY: test-lab
test-lab:
	@echo "Running lab package unit tests..."
	cd $(LAB_CMD) && $(GOTEST) -v ./...
	cd internal/lab/cnpg && $(GOTEST) -v ./...

# Verify lab artifacts
# Usage: make verify-lab-k9b-cnpg-incident ARTIFACT_DIR=/path/to/artifacts
.PHONY: verify-lab-k9b-cnpg-incident
verify-lab-k9b-cnpg-incident:
ifndef ARTIFACT_DIR
	$(error ARTIFACT_DIR is undefined - point to artifact directory)
endif
	@echo "Verifying lab artifacts at $(ARTIFACT_DIR)..."
	$(PYTHON) scripts/verify_k3s_cnpg_incident_lab_artifact.py --artifact-dir $(ARTIFACT_DIR)

# Verify with passing fixture
.PHONY: verify-lab-fixture-pass
verify-lab-fixture-pass:
	@echo "Verifying passing fixture..."
	$(PYTHON) scripts/verify_k3s_cnpg_incident_lab_artifact.py --artifact-dir fixtures/lab/pass

# Verify with failing fixture (missing k9b incident)
.PHONY: verify-lab-fixture-fail-no-incident
verify-lab-fixture-fail-no-incident:
	@echo "Verifying fail fixture (missing k9b incident)..."
	$(PYTHON) scripts/verify_k3s_cnpg_incident_lab_artifact.py --artifact-dir fixtures/lab/fail-no-incident
	@echo "Expected: verification should FAIL"

# Verify with failing fixture (secret leakage)
.PHONY: verify-lab-fixture-fail-secret
verify-lab-fixture-fail-secret:
	@echo "Verifying fail fixture (secret leakage)..."
	$(PYTHON) scripts/verify_k3s_cnpg_incident_lab_artifact.py --artifact-dir fixtures/lab/fail-secret
	@echo "Expected: verification should FAIL"

# Clean build artifacts
.PHONY: lab-clean
lab-clean:
	@echo "Cleaning lab artifacts..."
	rm -rf dist/
	rm -rf lab-artifacts/

# Check Go syntax/formatting
.PHONY: lab-lint
lab-lint:
	@echo "Checking lab Go code..."
	cd $(LAB_CMD) && $(GOVET) ./...
	cd internal/lab/cnpg && $(GOVET) ./...

# Duplicate code detection
# Scans: src/, scripts/, tests/, frontend/src/
# Excludes: node_modules, coverage, .venv, etc. (via .jscpd.json)
.PHONY: check-duplicates
check-duplicates:
	@echo "Running duplicate code detection..."
	mkdir -p artifacts/jscpd
	cd frontend && npx jscpd --config ../.jscpd.json ../src ../scripts ../tests ./src

# Local check - verify lab can build (without running)
.PHONY: lab-check
lab-check:
	@echo "Checking lab runner can build..."
	cd $(LAB_CMD) && $(GOMODTIDY)
	cd $(LAB_CMD) && $(GOVET) ./...
	@echo "Lab runner check complete."

# =============================================================================
# Live Lab Targets
# =============================================================================

# Run live lab against an existing K3s cluster
# Usage: make lab-k9b-cnpg-incident-live KUBECONFIG=/path/to/kubeconfig SCENARIO=pod-failure
.PHONY: lab-k9b-cnpg-incident-live
lab-k9b-cnpg-incident-live:
ifndef KUBECONFIG
	$(error KUBECONFIG is undefined - point to kubeconfig file)
endif
	@echo "Running live K3s/CNPG incident lab..."
	@echo "KUBECONFIG=$(KUBECONFIG)"
	@echo "SCENARIO=$(or $(SCENARIO),pod-failure)"
	@echo "ARTIFACT_DIR=$(or $(ARTIFACT_DIR),./lab-artifacts/live)"
	@mkdir -p dist
	cd $(LAB_CMD) && $(GOMODTIDY) && $(GOBUILD) -o ../../$(LAB_BIN) .
	$(LAB_BIN) run \
		--kubeconfig $(KUBECONFIG) \
		--cluster-mode local \
		--artifact-dir $(or $(ARTIFACT_DIR),./lab-artifacts/live) \
		--scenario $(or $(SCENARIO),pod-failure) \
		--timeout 30m \
		-v

# Verify live lab artifacts
# Usage: make verify-lab-k9b-cnpg-incident-live ARTIFACT_DIR=./lab-artifacts/live
.PHONY: verify-lab-k9b-cnpg-incident-live
verify-lab-k9b-cnpg-incident-live:
ifndef ARTIFACT_DIR
	$(error ARTIFACT_DIR is undefined - point to live artifact directory)
endif
	@echo "Verifying live lab artifacts at $(ARTIFACT_DIR)..."
	$(PYTHON) scripts/verify_k3s_cnpg_incident_lab_artifact.py --artifact-dir $(ARTIFACT_DIR) --verbose

# =============================================================================
# vmalert/Alertmanager Live Lab Targets
# =============================================================================

# Run vmalert/Alertmanager live lab
# Usage: make lab-k9b-vmalert-alertmanager-live KUBECONFIG=/path/to/kubeconfig
.PHONY: lab-k9b-vmalert-alertmanager-live
lab-k9b-vmalert-alertmanager-live:
ifndef KUBECONFIG
	$(error KUBECONFIG is undefined - point to kubeconfig file)
endif
	@echo "Running vmalert/Alertmanager live lab..."
	@echo "KUBECONFIG=$(KUBECONFIG)"
	@echo "ARTIFACT_DIR=$(or $(ARTIFACT_DIR),./lab-artifacts/vmalert-alertmanager)"
	@mkdir -p $(or $(ARTIFACT_DIR),./lab-artifacts/vmalert-alertmanager)
	$(PYTHON) scripts/k9b_vmalert_alertmanager_lab.py run \
		--kubeconfig $(KUBECONFIG) \
		--artifact-dir $(or $(ARTIFACT_DIR),./lab-artifacts/vmalert-alertmanager) \
		--timeout 20m

# Verify vmalert/Alertmanager live lab artifacts
# Usage: make verify-lab-k9b-vmalert-alertmanager-live ARTIFACT_DIR=./lab-artifacts/vmalert-alertmanager
.PHONY: verify-lab-k9b-vmalert-alertmanager-live
verify-lab-k9b-vmalert-alertmanager-live:
ifndef ARTIFACT_DIR
	$(error ARTIFACT_DIR is undefined - point to artifact directory)
endif
	@echo "Verifying vmalert/Alertmanager live lab artifacts at $(ARTIFACT_DIR)..."
	$(PYTHON) scripts/k9b_vmalert_alertmanager_lab_contract.py --artifact-dir $(ARTIFACT_DIR)

# K3s CNPG Incident Lab - Runbook

This document contains operational runbook information for the K3s CNPG Incident Lab.

## Required CNPG Operator Prerequisite

The lab requires the CloudNativePG operator to be preinstalled:

```bash
kubectl get crd clusters.postgresql.cnpg.io
kubectl get pods -n cnpg-system
kubectl get deployments -n cnpg-system
```

If CNPG CRD/operator is missing, the lab fails with:
```
Existing CNPG operator/CRD not found; namespace-mode lab requires preinstalled CNPG.
```

## Safety Boundaries

1. **Lab namespace cleanup**: Always runs via `if: always()` - deletes only `${LAB_NAMESPACE}`
2. **No system namespace mutation**: Does not touch `cnpg-system`, `kube-system`, `harbor`
3. **No CNPG operator installation**: Accepts preinstalled operator only
4. **No nested K3s**: Runs on existing cluster infrastructure
5. **k9b live detection deferred**: Not implemented in this ACT
6. **RBAC preflight is fatal**: Missing permissions cause immediate job failure

## Build Commands

```bash
# Sync workspace and build
go work sync
go build -o dist/k9b-cnpg-incident-lab ./cmd/k9b-cnpg-incident-lab

# Run Go tests
go test -v ./internal/lab/cnpg/...
```

## Manual GitHub Actions Dispatch

1. Navigate to **Actions** → **K3s CNPG Incident Lab**
2. Click **Run workflow**
3. Configure inputs:
   - `artifact_retention_days`: Number of days (default: 7)
   - `run_live_lab`: Set to `true` to run live namespace-mode lab
   - `incident_scenario`: Choose incident scenario (default: pod-failure)
4. Click **Run workflow**

## Verification

### CI / Manual

These verification commands are for CI and manual testing purposes only:

```bash
# Run lab config tests (includes kubectl bootstrap and RBAC tests)
.venv/bin/python -m pytest tests/test_live_lab_config.py -v

# Run verifier tests
.venv/bin/python -m pytest tests/test_verify_k3s_cnpg_incident_lab.py -v

# Verify passing fixture
.venv/bin/python scripts/verify_k3s_cnpg_incident_lab_artifact.py \
  --artifact-dir fixtures/lab/pass

# Run ACT-local verification
./scripts/verify_all.sh --act-local
```

### Live Lab Acceptance Criteria

For a successful live lab run:

1. **Runner pickup**: Job is picked up by `spbnix-k8s` runner
2. **kubectl setup**: `Set up kubectl` step completes successfully
3. **kubeconfig bootstrap**: `Configure in-cluster kubeconfig` step completes
4. **kubectl availability**: `kubectl version --client` passes
5. **RBAC preflight**: `kubectl auth can-i` checks pass (or fail with clear missing permission error)
6. **CNPG preflight**: CNPG operator visibility check passes
7. **No token leakage**: No tokens or kubeconfig printed or uploaded
8. **Namespace-mode preserved**: Lab uses unique namespace, not cluster-wide resources
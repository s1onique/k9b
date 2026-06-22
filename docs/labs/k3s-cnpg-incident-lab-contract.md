# K3s CNPG Incident Lab - Contract Reference

This document specifies the artifact contracts and schemas for the K3s CNPG Incident Lab.

## Artifact Schema

### lab-result.json (Namespace Mode)

```json
{
  "ok": true,
  "scenario": "pod-failure",
  "started_at": "2026-06-21T20:00:00Z",
  "finished_at": "2026-06-21T20:15:00Z",
  "cluster_mode": "existing",
  "runner_mode": "self-hosted",
  "cnpg_operator_mode": "existing",
  "lab_namespace": "k9b-cnpg-lab-123456",
  "k9b_image_repository": "harbor-pve1.spbnix.local/k9b/k9b-backend",
  "k9b_image_tag": "c29014919519ed1fa1a0d12aadf291f23f932fa2",
  "k9b_image_ref": "harbor-pve1.spbnix.local/k9b/k9b-backend:c29014919519ed1fa1a0d12aadf291f23f932fa2",
  "k9b_image_digest": "sha256:...",
  "incident_detected": false,
  "artifact_dir": "./lab-artifacts/live",
  "failure_reason": "k9b live detection deferred",
  "llm_triage_enabled": false,
  "llm_triage_attempted": false
}
```

### Directory Structure

```
artifact-dir/
├── lab-result.json           # Lab outcome and metadata
├── baseline/                 # Pre-incident cluster state
│   ├── nodes.txt             # kubectl get nodes -o wide
│   ├── pods.txt              # kubectl get pods -n <lab_ns> -o wide
│   ├── events.txt            # kubectl get events -n <lab_ns>
│   ├── cnpg-clusters.json    # CNPG operator/cluster status
│   ├── k9b-status.json       # Helm release status
│   ├── k9b-all.txt           # kubectl get all -n <lab_ns>
│   ├── k9b-describe.txt     # kubectl describe deployment -n <lab_ns>
│   └── k9b-pods.json         # kubectl get pods -n <lab_ns> -o json
├── incident/                 # Post-injection cluster state
│   ├── injected-change.yaml  # The tracked manifest (namespace replaced)
│   ├── pods.txt              # Pod status during incident
│   ├── events.txt            # Kubernetes events during incident
│   ├── cnpg-clusters.json    # CNPG status during incident
│   ├── cnpg-cluster.yaml     # CNPG cluster manifest
│   ├── describe-pods.txt     # Detailed pod descriptions
│   ├── k9b-incidents.json    # k9b detected incidents
│   └── k9b-incident-detail.json  # Detailed incident info
├── recovery-or-final/        # Post-recovery or final state
│   ├── pods.txt
│   ├── events.txt
│   └── cnpg-clusters.json
└── logs/
    ├── lab-runner.log        # Timestamped lab execution log
    ├── cnpg-operator.log     # CNPG operator logs
    ├── cnpg-operator-preflight.txt  # CNPG preflight results
    ├── k9b.log               # k9b agent logs
    ├── helm-k9b-status.txt   # Helm release status
    └── k9b-images.txt        # Observed k9b pod images
```

## Secret Hygiene

The lab explicitly avoids uploading:
- kubeconfig contents (generated in-memory from service account)
- service account tokens (used only for kubectl config, never echoed)
- generated database passwords
- OpenRouter keys
- GitHub tokens
- bearer tokens
- private keys
- full Secret resources

**kubeconfig security**: The kubeconfig is generated from the in-cluster service account mount and stored at `$HOME/.kube/config`. It is:
- Never echoed or printed
- Not uploaded as an artifact
- Used only for kubectl operations within the workflow

## Incident Scenarios

### pod-failure (Current)

**Description**: Deploy a lab-owned failing app pod with a deterministic failing readiness probe.

**Mechanism**:
1. Apply the tracked manifest: `fixtures/lab/live/pod-failure/injected-change.yaml`
2. The manifest creates a Pod named `cnpg-lab-failing-app` in the lab namespace
3. The pod has a readiness probe that always fails (`/bin/false`)
4. The pod remains in `Running` phase but `NotReady` condition
5. k9b incident detection is deferred to future ACT

**Expected Symptom**: Pod reports NotReady, k9b detects incident (when implemented).

**Recovery**: Delete the pod.

**Safety**: Non-destructive, reversible, no data loss.

## Files Changed

| File | Purpose |
|------|---------|
| `.github/workflows/k9b-image-builder.yml` | Reusable image-build workflow |
| `.github/workflows/k9b-cnpg-incident-lab.yml` | Main CI workflow with image-builder integration |
| `.github/workflows/k9b-cnpg-incident-lab-live.yml` | Live workflow with kubectl bootstrap and RBAC preflight |
| `.github/workflows/k9b-cnpg-live-lab-rbac-admin.yml` | Protected admin workflow for applying live-lab RBAC manifest |
| `scripts/k9b_cnpg_live_lab_rbac_preflight.sh` | Helper script for self-identifying RBAC failures |
| `scripts/verify_k3s_cnpg_incident_lab_artifact.py` | Artifact verifier with namespace-mode support |
| `tests/test_live_lab_config.py` | Workflow config tests (kubectl bootstrap, RBAC, secret hygiene) |
| `tests/test_live_lab_admin_rbac_workflow.py` | Tests for admin RBAC workflow |
| `fixtures/lab/live/pod-failure/injected-change.yaml` | Tracked incident manifest |
| `deploy/github-actions/k9b-cnpg-live-lab-runner-rbac.yaml` | Minimal RBAC manifest for spbnix-k8s runner |
| `docs/labs/k3s-cnpg-incident-lab.md` | Canonical lab entrypoint |
| `docs/labs/k3s-cnpg-incident-lab-architecture.md` | Architecture and design decisions |
| `docs/labs/k3s-cnpg-incident-lab-contract.md` | Artifact schemas and contracts (this file) |
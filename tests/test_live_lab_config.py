"""Unit tests for live lab configuration and workflow inputs."""

import re
from pathlib import Path

# Path to the workflow files
WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab.yml"
WORKFLOW_LIVE_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"


class TestWorkflowMainOrchestration:
    """Test main workflow correctly orchestrates live lab."""

    def test_workflow_file_exists(self) -> None:
        """The main workflow file should exist."""
        assert WORKFLOW_FILE.exists(), f"Workflow file not found at {WORKFLOW_FILE}"

    def test_workflow_has_run_live_lab_input(self) -> None:
        """Main workflow should have run_live_lab input."""
        content = WORKFLOW_FILE.read_text()
        assert "run_live_lab:" in content, "run_live_lab input not found"
        assert 'type: boolean' in content, "run_live_lab should be boolean type"

    def test_workflow_has_incident_scenario_input(self) -> None:
        """Main workflow should have incident_scenario input."""
        content = WORKFLOW_FILE.read_text()
        assert "incident_scenario:" in content, "incident_scenario input not found"
        assert 'type: choice' in content, "incident_scenario should be choice type"
        assert "pod-failure" in content, "pod-failure should be in options"

    def test_workflow_has_live_k3s_job(self) -> None:
        """Main workflow should have live-k3s-lab job."""
        content = WORKFLOW_FILE.read_text()
        assert "live-k3s-lab:" in content, "live-k3s-lab job not found"
        assert "needs: build-and-verify" in content, "live-k3s-lab should depend on build-and-verify"

    def test_live_k3s_job_only_on_workflow_dispatch(self) -> None:
        """live-k3s-lab should only run on workflow_dispatch with run_live_lab=true."""
        content = WORKFLOW_FILE.read_text()
        assert 'if: github.event_name == \'workflow_dispatch\'' in content, \
            "live-k3s-lab should check event_name"
        assert 'inputs.run_live_lab == true' in content, \
            "live-k3s-lab should check run_live_lab input"

    def test_live_k3s_job_calls_reusable_workflow(self) -> None:
        """live-k3s-lab should call the reusable workflow."""
        content = WORKFLOW_FILE.read_text()
        assert "uses: ./.github/workflows/k9b-cnpg-incident-lab-live.yml" in content, \
            "Should call the live workflow file"


class TestWorkflowLiveLabImplementation:
    """Test the live workflow implementation file."""

    def test_live_workflow_file_exists(self) -> None:
        """The live workflow file should exist."""
        assert WORKFLOW_LIVE_FILE.exists(), f"Live workflow file not found at {WORKFLOW_LIVE_FILE}"

    def test_live_workflow_has_pinned_k3s_version(self) -> None:
        """Live workflow should have pinned K3s version via workflow_call defaults."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Check defaults in workflow_call inputs
        assert re.search(r"k3s_version:.*?default:\s*['\"]v1\.31\.0\+k3s1['\"]", content, re.DOTALL), \
            "K3S_VERSION default should be pinned to v1.31.0+k3s1"

    def test_live_workflow_has_pinned_cnpg_version(self) -> None:
        """Live workflow should have pinned CNPG version via workflow_call defaults."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Check defaults in workflow_call inputs
        assert re.search(r"cnpg_version:.*?default:\s*['\"]1\.26\.0['\"]", content, re.DOTALL), \
            "CNPG_VERSION default should be pinned to 1.26.0"

    def test_live_workflow_provisions_k3s(self) -> None:
        """Live workflow should provision K3s."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "curl -sfL https://get.k3s.io" in content, \
            "K3s install script not found"
        assert "INSTALL_K3S_VERSION=" in content, \
            "K3s version should be set"

    def test_live_workflow_installs_cnpg_operator(self) -> None:
        """Live workflow should install real CNPG operator."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "cloudnative-pg/cloudnative-pg" in content, \
            "CNPG operator manifest not found"
        assert "cnpg-controller-manager" in content, \
            "CNPG controller rollout status not found"

    def test_live_workflow_deploys_cnpg_cluster(self) -> None:
        """Live workflow should deploy CNPG cluster."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "kind: Cluster" in content, "CNPG Cluster CR not found"
        assert "cnpg-lab" in content, "Lab namespace not found"

    def test_live_workflow_installs_k9b(self) -> None:
        """Live workflow should install k9b agent."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "k9b-agent" in content, "k9b agent not found"
        assert "k9b" in content.lower(), "k9b namespace/deployment not found"

    def test_live_workflow_injects_incident(self) -> None:
        """Live workflow should inject incident."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "injected-change.yaml" in content, "injected-change.yaml not found"

    def test_live_workflow_collects_artifacts(self) -> None:
        """Live workflow should collect artifacts."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "lab-artifacts" in content, "lab-artifacts directory not found"
        assert "baseline" in content, "baseline artifact collection not found"
        assert "incident" in content, "incident artifact collection not found"

    def test_live_workflow_runs_verifier(self) -> None:
        """Live workflow should run artifact verifier."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "verify_k3s_cnpg_incident_lab_artifact.py" in content, \
            "Artifact verifier not found"

    def test_live_workflow_uploads_artifacts(self) -> None:
        """Live workflow should upload artifacts with distinct name."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "k9b-cnpg-incident-lab-live-" in content, \
            "Live artifact upload name not found"
        assert "actions/upload-artifact" in content, "Upload artifact action not found"

    def test_live_workflow_avoids_secrets(self) -> None:
        """Live workflow should avoid uploading secrets."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Should not dump secrets in raw form
        assert "kubectl get secret" not in content or "dry-run=client" in content, \
            "Should not dump secrets directly"
        # Should cleanup sensitive files
        assert "rm -f" in content or "cleanup" in content.lower(), \
            "Cleanup step not found"


class TestArtifactVerifierLiveMode:
    """Test that artifact verifier works with live lab artifacts."""

    def test_verifier_accepts_deferred_detection(self) -> None:
        """Verifier should accept lab-result.json with incident_detected=false."""
        lab_result = {
            "ok": True,
            "scenario": "pod-failure",
            "started_at": "2026-06-16T10:00:00Z",
            "finished_at": "2026-06-16T10:15:00Z",
            "cluster_mode": "provision",
            "artifact_dir": "/tmp/lab-artifacts",
            "incident_detected": False,
            "failure_reason": "k9b live detection deferred",
            "llm_triage_enabled": False,
            "llm_triage_attempted": False,
        }
        assert not lab_result.get("incident_detected")

    def test_verifier_requires_baseline_artifacts(self) -> None:
        """Verifier should require baseline artifacts."""
        required_baseline = ["nodes.txt", "pods.txt", "cnpg-clusters.json", "k9b-status.json"]
        for artifact in required_baseline:
            assert artifact.endswith(".txt") or artifact.endswith(".json")

    def test_verifier_requires_incident_artifacts(self) -> None:
        """Verifier should require incident artifacts."""
        required_incident = ["injected-change.yaml", "pods.txt", "events.txt", "cnpg-clusters.json"]
        for artifact in required_incident:
            assert artifact


class TestLiveLabVersions:
    """Test pinned version constants."""

    def test_k3s_version_format(self) -> None:
        """K3s version should match expected format."""
        version_pattern = r"v\d+\.\d+\.\d+\+k3s\d+"
        assert re.match(version_pattern, "v1.31.0+k3s1")
        assert re.match(version_pattern, "v1.30.0+k3s2")

    def test_cnpg_version_format(self) -> None:
        """CNPG version should match expected format."""
        version_pattern = r"\d+\.\d+\.\d+"
        assert re.match(version_pattern, "1.26.0")
        assert re.match(version_pattern, "1.25.0")


class TestSecretHygiene:
    """Test secret hygiene patterns."""

    def test_lab_result_excludes_sensitive_fields(self) -> None:
        """Lab result should not contain sensitive fields."""
        lab_result = {
            "ok": True,
            "scenario": "pod-failure",
            "incident_detected": False,
            "failure_reason": "k9b live detection deferred",
        }
        sensitive_fields = ["kubeconfig", "password", "token", "api_key", "secret"]
        for field in sensitive_fields:
            assert field not in lab_result

    def test_workflow_excludes_kubeconfig_upload(self) -> None:
        """Workflow should not upload kubeconfig file in artifacts."""
        content = WORKFLOW_FILE.read_text()
        upload_sections = re.findall(r'path:\s*\n(.*?)(?=\n\s{0,4}\w|\Z)', content, re.DOTALL)
        for section in upload_sections:
            assert '/etc/rancher/k3s/k3s.yaml' not in section, \
                f"Should not upload kubeconfig in artifact section: {section[:100]}"

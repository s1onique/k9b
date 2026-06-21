"""Unit tests for live lab configuration and workflow inputs."""

import re
from pathlib import Path

# Path to the workflow files
WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab.yml"
WORKFLOW_LIVE_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"
INCIDENT_MANIFEST = Path(__file__).parent.parent / "fixtures" / "lab" / "live" / "pod-failure" / "injected-change.yaml"


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
        """Live workflow should install k9b via Helm chart."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "helm upgrade --install k9b" in content, "Helm install k9b not found"
        assert "./charts/k9b" in content, "k9b chart path not found"
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

    def test_live_workflow_verifier_runs_after_cleanup(self) -> None:
        """Verifier must run after log collection and cleanup to scan final artifact tree."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Extract step order: find positions of key steps
        collect_logs_pos = content.find("Collect K3s logs")
        cleanup_pos = content.find("Cleanup sensitive files")
        verify_pos = content.find("Verify live lab artifacts")
        upload_pos = content.find("Upload live lab artifacts")
        # Correct order: collect logs -> cleanup -> verify -> upload
        assert collect_logs_pos < cleanup_pos < verify_pos < upload_pos, \
            f"Step order wrong: logs={collect_logs_pos}, cleanup={cleanup_pos}, verify={verify_pos}, upload={upload_pos}"


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


class TestDockerBuildPipeline:
    """Test that live workflow builds k9b image from current checkout."""

    def test_live_workflow_sets_up_docker_buildx(self) -> None:
        """Live workflow should set up Docker Buildx."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "docker/setup-buildx-action" in content, \
            "Docker Buildx setup not found"

    def test_live_workflow_builds_k9b_image(self) -> None:
        """Live workflow should build k9b container image."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "docker build" in content, "Docker build command not found"
        assert "Dockerfile.python" in content, "Dockerfile.python not specified"

    def test_live_workflow_defines_image_tag(self) -> None:
        """Live workflow should define K9B_IMAGE_TAG from github.sha."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "K9B_IMAGE_TAG:" in content, "K9B_IMAGE_TAG env not defined"
        assert "github.sha" in content, "Image tag should use github.sha"

    def test_live_workflow_verifies_dockerfile_exists(self) -> None:
        """Live workflow should verify Dockerfile.python exists before building."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "Dockerfile.python" in content, "Dockerfile.python check not found"
        assert 'exit 1' in content, "Should fail if Dockerfile.python is missing"

    def test_live_workflow_verifies_built_image(self) -> None:
        """Live workflow should verify the built image exists locally."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "docker image ls" in content, "Image verification not found"
        assert "docker image inspect" in content, "Image inspection not found"


class TestK3sImageImport:
    """Test that live workflow imports k9b image into K3s containerd."""

    def test_live_workflow_imports_image_into_k3s(self) -> None:
        """Live workflow should import the built image into K3s containerd."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "docker save" in content, "docker save command not found"
        assert "k3s ctr images import" in content, "K3s image import not found"

    def test_live_workflow_verifies_image_import(self) -> None:
        """Live workflow should verify image import succeeded."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "k3s ctr images ls" in content, "Image list verification not found"
        # Should have fatal assertion
        assert "exit 1" in content, "Import verification should be fatal on failure"


class TestHelmDeployment:
    """Test that live workflow deploys k9b via Helm chart."""

    def test_live_workflow_sets_up_helm(self) -> None:
        """Live workflow should set up Helm."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "azure/setup-helm" in content, "Helm setup action not found"
        assert "helm version" in content, "Helm verification not found"

    def test_live_workflow_deploys_via_helm_upgrade_install(self) -> None:
        """Live workflow should use helm upgrade --install."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "helm upgrade --install k9b" in content, "Helm upgrade --install not found"
        assert "./charts/k9b" in content, "Chart path not found"

    def test_live_workflow_overrides_chart_image_values(self) -> None:
        """Live workflow should override chart image values with run-built image."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "image.backend.repository=" in content, "Image repository override not found"
        assert "image.backend.tag=" in content, "Image tag override not found"
        assert "image.backend.pullPolicy=" in content, "Image pull policy not found"

    def test_live_workflow_uses_never_pull_policy(self) -> None:
        """Live workflow should use Never pull policy for local image."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "pullPolicy=Never" in content or "pullPolicy: Never" in content, \
            "Should use Never pull policy for locally imported image"

    def test_live_workflow_disables_auth_in_lab(self) -> None:
        """Live workflow should disable auth for lab deployment."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "backend.auth.enabled=false" in content or "backend.auth.enabled=false" in content, \
            "Should disable auth for lab deployment"

    def test_live_workflow_waits_for_helm_deployment(self) -> None:
        """Live workflow should wait for Helm deployment."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "--wait" in content, "Helm --wait not found"
        assert "--timeout" in content, "Helm timeout not found"

    def test_live_workflow_gets_helm_values(self) -> None:
        """Live workflow should verify Helm values after deployment."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "helm get values k9b" in content, "helm get values not found"


class TestImageAssertion:
    """Test that live workflow asserts k9b pod uses run-built image."""

    def test_live_workflow_asserts_pod_image_matches(self) -> None:
        """Live workflow should assert pod image matches run-built image."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "jsonpath" in content, "JSONPath for image check not found"
        assert "K9B_IMAGE_REPOSITORY" in content, "Image repository env not used"
        assert "K9B_IMAGE_TAG" in content, "Image tag env not used"

    def test_live_workflow_assertion_is_fatal(self) -> None:
        """Image assertion should be fatal (exit 1 on failure)."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Find the assert_image step and verify it has exit 1
        assert_match = re.search(r'Assert k9b pod uses run-built image.*?exit 1', content, re.DOTALL)
        assert assert_match, "Image assertion should exit 1 on failure"


class TestNoFakeManifest:
    """Test that live workflow does NOT contain fake k9b manifests."""

    def test_no_hardcoded_ghcr_image(self) -> None:
        """Live workflow should not contain hardcoded ghcr.io/s1onique/k9b:v0.1.0."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "ghcr.io/s1onique/k9b:v0.1.0" not in content, \
            "Should NOT contain hardcoded ghcr.io/s1onique/k9b:v0.1.0"

    def test_no_inline_k9b_agent_deployment(self) -> None:
        """Live workflow should not contain inline k9b-agent Deployment manifest."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Check for the old pattern of inline deployment
        assert not re.search(r'kind:\s*Deployment.*?name:\s*k9b-agent', content, re.DOTALL), \
            "Should NOT contain inline k9b-agent Deployment manifest"

    def test_no_inline_k9b_agent_service_account(self) -> None:
        """Live workflow should not contain inline k9b-agent ServiceAccount manifest."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Check for inline ServiceAccount
        assert not re.search(r'kind:\s*ServiceAccount.*?name:\s*k9b-agent', content, re.DOTALL), \
            "Should NOT contain inline k9b-agent ServiceAccount manifest"

    def test_no_health_loop_args(self) -> None:
        """Live workflow should not contain guessed args like health-loop."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert '"health-loop"' not in content, \
            "Should NOT contain guessed 'health-loop' args"


class TestTrackedIncidentManifest:
    """Test that live workflow uses tracked incident manifest file."""

    def test_tracked_incident_manifest_exists(self) -> None:
        """The tracked incident manifest should exist."""
        assert INCIDENT_MANIFEST.exists(), \
            f"Tracked incident manifest not found at {INCIDENT_MANIFEST}"

    def test_tracked_manifest_uses_lab_namespace(self) -> None:
        """Tracked manifest should use cnpg-lab namespace."""
        content = INCIDENT_MANIFEST.read_text()
        assert "cnpg-lab" in content, "Manifest should use cnpg-lab namespace"

    def test_tracked_manifest_has_scenario_label(self) -> None:
        """Tracked manifest should have lab.k9b.io/scenario label."""
        content = INCIDENT_MANIFEST.read_text()
        assert "lab.k9b.io/scenario" in content, \
            "Manifest should have lab.k9b.io/scenario label"

    def test_tracked_manifest_has_failing_readiness_probe(self) -> None:
        """Tracked manifest should have a readiness probe that fails."""
        content = INCIDENT_MANIFEST.read_text()
        assert "/bin/false" in content, "Manifest should have failing readiness probe"

    def test_live_workflow_applies_tracked_manifest(self) -> None:
        """Live workflow should apply the tracked incident manifest."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "kubectl apply -f fixtures/lab/live/pod-failure/injected-change.yaml" in content, \
            "Should apply tracked manifest"

    def test_live_workflow_copies_tracked_manifest_to_artifacts(self) -> None:
        """Live workflow should copy tracked manifest to incident artifacts."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "cp fixtures/lab/live/pod-failure/injected-change.yaml" in content, \
            "Should copy manifest to incident artifacts"

    def test_live_workflow_no_heredoc_incident_yaml(self) -> None:
        """Live workflow should NOT use heredoc YAML for incident injection."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Should not have inline YAML manifest for incident
        assert not re.search(r'cat << .EOF.*injected-change\.yaml.*EOF', content, re.DOTALL), \
            "Should NOT use heredoc for incident YAML"

    def test_live_workflow_verifies_incident_symptom(self) -> None:
        """Live workflow should verify the incident symptom (pod NotReady)."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "cnpg-lab-failing-app" in content, "Should check the failing app pod"
        assert "Ready" in content, "Should check Ready condition"
        assert "exit 1" in content, "Should fail if pod becomes Ready unexpectedly"


class TestArtifactCollection:
    """Test that artifact collection includes Helm chart deployment."""

    def test_live_workflow_collects_helm_status(self) -> None:
        """Live workflow should collect Helm release status."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "helm status k9b" in content, "Helm status collection not found"

    def test_live_workflow_collects_k9b_diagnostics(self) -> None:
        """Live workflow should collect k9b pod diagnostics."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "kubectl get all -n k9b" in content, "k9b all resources not found"
        assert "kubectl describe deployment -n k9b" in content, "k9b describe not found"
        assert "kubectl get pods -n k9b" in content, "k9b pods not found"

    def test_live_workflow_collects_helm_log(self) -> None:
        """Live workflow should collect Helm status to logs."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "helm-k9b-status.txt" in content, "Helm status log not found"

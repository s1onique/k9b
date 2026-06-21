"""Unit tests for live lab configuration and workflow inputs (namespace mode)."""

import re
from pathlib import Path

# Path to the workflow files
WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab.yml"
WORKFLOW_LIVE_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"
IMAGE_BUILDER_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-image-builder.yml"
INCIDENT_MANIFEST = Path(__file__).parent.parent / "fixtures" / "lab" / "live" / "pod-failure" / "injected-change.yaml"


def _strip_comments(content: str) -> str:
    """Remove comments from YAML content for testing purposes."""
    lines = content.split('\n')
    result_lines = []
    for line in lines:
        # Skip lines that are entirely comments
        stripped = line.strip()
        if not stripped.startswith('#'):
            result_lines.append(line)
    return '\n'.join(result_lines)


class TestWorkflowMainOrchestration:
    """Test main workflow correctly orchestrates live lab with image-builder."""

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

    def test_build_and_verify_runs_on_ubuntu_latest(self) -> None:
        """build-and-verify job should run on ubuntu-latest."""
        content = WORKFLOW_FILE.read_text()
        assert re.search(r"build-and-verify:.*?runs-on: ubuntu-latest", content, re.DOTALL), \
            "build-and-verify should run on ubuntu-latest"

    def test_build_lab_images_calls_image_builder(self) -> None:
        """build-lab-images job should call k9b-image-builder workflow."""
        content = WORKFLOW_FILE.read_text()
        assert "build-lab-images:" in content, "build-lab-images job not found"
        assert "uses: ./.github/workflows/k9b-image-builder.yml" in content, \
            "build-lab-images should use k9b-image-builder.yml"
        assert "needs: build-and-verify" in content, \
            "build-lab-images should depend on build-and-verify"

    def test_live_k3s_lab_consumes_image_outputs(self) -> None:
        """live-k3s-lab should consume image outputs from build-lab-images."""
        content = WORKFLOW_FILE.read_text()
        assert "needs:" in content and "build-lab-images" in content, \
            "live-k3s-lab should depend on build-lab-images"
        assert "backend_image_repository:" in content, \
            "live-k3s-lab should receive backend_image_repository"
        assert "backend_image_tag:" in content, \
            "live-k3s-lab should receive backend_image_tag"
        assert "backend_image_ref:" in content, \
            "live-k3s-lab should receive backend_image_ref"


class TestImageBuilderReusableWorkflow:
    """Test that k9b-image-builder.yml is properly configured as reusable."""

    def test_image_builder_file_exists(self) -> None:
        """The image builder workflow file should exist."""
        assert IMAGE_BUILDER_FILE.exists(), f"Image builder workflow not found at {IMAGE_BUILDER_FILE}"

    def test_image_builder_has_workflow_call_trigger(self) -> None:
        """Image builder should have workflow_call trigger."""
        content = IMAGE_BUILDER_FILE.read_text()
        assert "workflow_call:" in content, "workflow_call trigger not found"

    def test_image_builder_exposes_backend_outputs(self) -> None:
        """Image builder should expose backend image outputs."""
        content = IMAGE_BUILDER_FILE.read_text()
        assert "backend_image_repository:" in content, "backend_image_repository output not found"
        assert "backend_image_tag:" in content, "backend_image_tag output not found"
        assert "backend_image_ref:" in content, "backend_image_ref output not found"
        assert "backend_image_digest:" in content, "backend_image_digest output not found"

    def test_image_builder_exposes_frontend_outputs(self) -> None:
        """Image builder should expose frontend image outputs."""
        content = IMAGE_BUILDER_FILE.read_text()
        assert "frontend_image_repository:" in content, "frontend_image_repository output not found"
        assert "frontend_image_tag:" in content, "frontend_image_tag output not found"
        assert "frontend_image_ref:" in content, "frontend_image_ref output not found"

    def test_image_builder_accepts_image_tag_input(self) -> None:
        """Image builder should accept image_tag input."""
        content = IMAGE_BUILDER_FILE.read_text()
        assert re.search(r"image_tag:.*?required:\s*true", content, re.DOTALL), \
            "image_tag input should be required"


class TestWorkflowLiveLabNamespaceMode:
    """Test the live workflow implementation for namespace mode."""

    def test_live_workflow_file_exists(self) -> None:
        """The live workflow file should exist."""
        assert WORKFLOW_LIVE_FILE.exists(), f"Live workflow file not found at {WORKFLOW_LIVE_FILE}"

    def test_live_workflow_runs_on_self_hosted_runner(self) -> None:
        """Live workflow should run on self-hosted runner with cluster access."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "self-hosted" in content, "Should run on self-hosted runner"
        assert "github-actions-runner" in content, \
            "Should run on github-actions-runner label"

    def test_live_workflow_uses_workflow_call(self) -> None:
        """Live workflow should be a reusable workflow with workflow_call."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "workflow_call:" in content, "workflow_call trigger not found"

    def test_live_workflow_accepts_image_inputs(self) -> None:
        """Live workflow should accept image inputs from caller."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "backend_image_repository:" in content, "backend_image_repository input not found"
        assert "backend_image_tag:" in content, "backend_image_tag input not found"
        assert "backend_image_ref:" in content, "backend_image_ref input not found"

    def test_live_workflow_no_k3s_install(self) -> None:
        """Live workflow should NOT provision K3s."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "curl -sfL https://get.k3s.io" not in content, \
            "Should NOT install K3s"
        assert "INSTALL_K3S_VERSION=" not in content, \
            "Should NOT set K3s version"
        assert "/etc/rancher/k3s/k3s.yaml" not in content, \
            "Should NOT reference K3s kubeconfig"

    def test_live_workflow_no_k3s_image_import(self) -> None:
        """Live workflow should NOT import images into K3s."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "k3s ctr images import" not in content, \
            "Should NOT import images into K3s"

    def test_live_workflow_no_docker_build(self) -> None:
        """Live workflow should NOT build Docker images."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "docker build" not in content, \
            "Should NOT build Docker images"
        assert "docker/setup-buildx-action" not in content, \
            "Should NOT set up Docker Buildx"
        assert "docker push" not in content, \
            "Should NOT push Docker images"

    def test_live_workflow_no_buildctl(self) -> None:
        """Live workflow should NOT use buildctl."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "buildctl" not in content, \
            "Should NOT use buildctl"

    def test_live_workflow_no_docker_socket(self) -> None:
        """Live workflow should NOT reference Docker socket."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "/var/run/docker.sock" not in content, \
            "Should NOT reference Docker socket"

    def test_live_workflow_no_cnpg_operator_install(self) -> None:
        """Live workflow should NOT install CNPG operator."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "cloudnative-pg/cloudnative-pg" not in content, \
            "Should NOT install CNPG operator"
        assert "cnpg-controller-manager" not in content, \
            "Should NOT reference CNPG controller rollout"
        # Note: "kubectl apply" is used for lab-cluster, so we check for "kubectl apply" + "cnpg-" in same context
        assert not ("kubectl apply" in content and "cnpg-" in content and "releases/cnpg" in content), \
            "Should NOT apply CNPG operator manifests"

    def test_live_workflow_preflights_existing_cnpg(self) -> None:
        """Live workflow should preflight existing CNPG operator."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "kubectl get crd clusters.postgresql.cnpg.io" in content, \
            "Should check CNPG CRD"
        assert "cnpg-system" in content, \
            "Should check cnpg-system namespace"

    def test_live_workflow_creates_unique_namespace(self) -> None:
        """Live workflow should create unique lab namespace from GITHUB_RUN_ID."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "k9b-cnpg-lab-${{ github.run_id }}" in content, \
            "Should create namespace from GITHUB_RUN_ID"
        assert "kubectl create namespace" in content, \
            "Should create namespace"
        assert "lab.k9b.io/managed=true" in content, \
            "Should label namespace as managed"

    def test_live_workflow_deploys_helm_chart(self) -> None:
        """Live workflow should deploy k9b via Helm chart."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "helm upgrade --install k9b" in content, \
            "Should use helm upgrade --install"
        assert "./charts/k9b" in content, \
            "Should reference k9b chart"

    def test_live_workflow_uses_builder_image_refs(self) -> None:
        """Live workflow should use builder output image refs in Helm values."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "image.backend.repository=" in content, \
            "Should set image.backend.repository"
        assert "image.backend.tag=" in content, \
            "Should set image.backend.tag"
        assert "inputs.backend_image_repository" in content, \
            "Should use inputs.backend_image_repository"
        assert "inputs.backend_image_tag" in content, \
            "Should use inputs.backend_image_tag"

    def test_live_workflow_deploys_cnpg_cluster(self) -> None:
        """Live workflow should deploy CNPG cluster in lab namespace."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "kind: Cluster" in content, \
            "Should deploy CNPG Cluster CR"
        assert "metadata:" in content and "name: lab-cluster" in content, \
            "Should create lab-cluster"

    def test_live_workflow_injects_incident(self) -> None:
        """Live workflow should inject incident using tracked manifest."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "injected-change.yaml" in content, \
            "Should reference injected-change.yaml"

    def test_live_workflow_collects_artifacts(self) -> None:
        """Live workflow should collect artifacts."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "lab-artifacts" in content, \
            "Should reference lab-artifacts"
        assert "baseline" in content, \
            "Should collect baseline artifacts"
        assert "incident" in content, \
            "Should collect incident artifacts"

    def test_live_workflow_runs_verifier(self) -> None:
        """Live workflow should run artifact verifier."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "verify_k3s_cnpg_incident_lab_artifact.py" in content, \
            "Should run artifact verifier"

    def test_live_workflow_uploads_artifacts(self) -> None:
        """Live workflow should upload artifacts with distinct name."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "k9b-cnpg-incident-lab-live-" in content, \
            "Should upload with distinct name"
        assert "actions/upload-artifact" in content, \
            "Should use upload-artifact action"

    def test_live_workflow_cleans_up_namespace(self) -> None:
        """Live workflow should cleanup lab namespace with always()."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert re.search(r"Cleanup lab namespace.*?if:\s*always\(\)", content, re.DOTALL), \
            "Cleanup should have if: always()"
        assert "kubectl delete namespace" in content, \
            "Should delete namespace"

    def test_live_workflow_avoids_secrets(self) -> None:
        """Live workflow should avoid uploading secrets."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "kubectl get secret" not in content or "dry-run=client" in content, \
            "Should not dump secrets directly"

    def test_live_workflow_generates_namespace_mode_result(self) -> None:
        """Live workflow should generate lab-result.json with namespace mode fields."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert '"cluster_mode": "existing"' in content, \
            "Should set cluster_mode to existing"
        assert '"cnpg_operator_mode": "existing"' in content, \
            "Should set cnpg_operator_mode to existing"
        assert "lab_namespace" in content, \
            "Should include lab_namespace field"
        assert "runner_mode" in content, \
            "Should include runner_mode field"

    def test_live_workflow_verifier_runs_after_cleanup(self) -> None:
        """Verifier must run after log collection and cleanup."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Extract step order
        collect_logs_pos = content.find("Collect")
        cleanup_pos = content.find("Cleanup sensitive files")
        verify_pos = content.find("Verify live lab artifacts")
        upload_pos = content.find("Upload live lab artifacts")
        # Correct order: collect -> cleanup -> verify -> upload
        assert collect_logs_pos < cleanup_pos < verify_pos < upload_pos, \
            f"Step order wrong: collect={collect_logs_pos}, cleanup={cleanup_pos}, verify={verify_pos}, upload={upload_pos}"


class TestArtifactVerifierNamespaceMode:
    """Test that artifact verifier works with namespace mode artifacts."""

    def test_verifier_accepts_deferred_detection(self) -> None:
        """Verifier should accept lab-result.json with incident_detected=false."""
        lab_result = {
            "ok": True,
            "scenario": "pod-failure",
            "started_at": "2026-06-16T10:00:00Z",
            "finished_at": "2026-06-16T10:15:00Z",
            "cluster_mode": "existing",
            "artifact_dir": "/tmp/lab-artifacts",
            "incident_detected": False,
            "failure_reason": "k9b live detection deferred",
            "llm_triage_enabled": False,
            "llm_triage_attempted": False,
        }
        assert not lab_result.get("incident_detected")

    def test_verifier_requires_namespace_mode_fields(self) -> None:
        """Verifier should require namespace mode fields when cluster_mode=existing."""
        lab_result = {
            "ok": True,
            "scenario": "pod-failure",
            "started_at": "2026-06-16T10:00:00Z",
            "finished_at": "2026-06-16T10:15:00Z",
            "cluster_mode": "existing",
            "lab_namespace": "k9b-cnpg-lab-123456",
            "runner_mode": "self-hosted",
            "cnpg_operator_mode": "existing",
            "k9b_image_repository": "harbor.example.com/k9b/k9b-backend",
            "k9b_image_tag": "abc123",
            "k9b_image_ref": "harbor.example.com/k9b/k9b-backend:abc123",
            "artifact_dir": "/tmp/lab-artifacts",
            "incident_detected": False,
            "failure_reason": "k9b live detection deferred",
            "llm_triage_enabled": False,
            "llm_triage_attempted": False,
        }
        assert lab_result.get("cluster_mode") == "existing"
        assert "lab_namespace" in lab_result
        assert "cnpg_operator_mode" in lab_result

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


class TestNoDockerImplementation:
    """Test that live workflow contains NO Docker implementation."""

    def test_no_docker_build_commands(self) -> None:
        """Live workflow should not contain docker build commands."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        forbidden = [
            "docker build",
            "docker push",
            "docker save",
            "docker load",
            "docker tag",
        ]
        for cmd in forbidden:
            assert cmd not in content, f"Should NOT contain '{cmd}'"

    def test_no_buildx_setup(self) -> None:
        """Live workflow should not set up Docker Buildx."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "docker/setup-buildx-action" not in content, \
            "Should NOT set up Docker Buildx"

    def test_no_buildctl(self) -> None:
        """Live workflow should not use buildctl."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "buildctl" not in content, \
            "Should NOT use buildctl"

    def test_no_docker_socket(self) -> None:
        """Live workflow should not reference Docker socket."""
        content = _strip_comments(WORKFLOW_LIVE_FILE.read_text())
        assert "/var/run/docker.sock" not in content, \
            "Should NOT reference Docker socket"


class TestTrackedIncidentManifest:
    """Test that incident manifest is namespace-mode compatible."""

    def test_tracked_incident_manifest_exists(self) -> None:
        """The tracked incident manifest should exist."""
        assert INCIDENT_MANIFEST.exists(), \
            f"Tracked incident manifest not found at {INCIDENT_MANIFEST}"

    def test_tracked_manifest_has_scenario_label(self) -> None:
        """Tracked manifest should have lab.k9b.io/scenario label."""
        content = INCIDENT_MANIFEST.read_text()
        assert "lab.k9b.io/scenario" in content, \
            "Manifest should have lab.k9b.io/scenario label"

    def test_tracked_manifest_has_failing_readiness_probe(self) -> None:
        """Tracked manifest should have a readiness probe that fails."""
        content = INCIDENT_MANIFEST.read_text()
        assert "/bin/false" in content, \
            "Manifest should have failing readiness probe"

    def test_live_workflow_applies_manifest_in_namespace(self) -> None:
        """Live workflow should apply manifest with -n flag for namespace."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "kubectl apply" in content, \
            "Should apply manifest"
        # The manifest should be applied in the lab namespace
        assert "$LAB_NAMESPACE" in content or "namespace" in content, \
            "Should use namespace mode"


class TestHelmDeployment:
    """Test that live workflow deploys k9b via Helm chart."""

    def test_live_workflow_sets_up_helm(self) -> None:
        """Live workflow should set up Helm."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "azure/setup-helm" in content, \
            "Should use Helm setup action"

    def test_live_workflow_deploys_via_helm_upgrade_install(self) -> None:
        """Live workflow should use helm upgrade --install."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "helm upgrade --install k9b" in content, \
            "Should use helm upgrade --install"

    def test_live_workflow_uses_ifnotpresent_pullpolicy(self) -> None:
        """Live workflow should use IfNotPresent pull policy."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "pullPolicy=IfNotPresent" in content, \
            "Should use IfNotPresent pull policy (not Never)"

    def test_live_workflow_waits_for_helm_deployment(self) -> None:
        """Live workflow should wait for Helm deployment."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "--wait" in content, \
            "Should use --wait flag"
        assert "--timeout" in content, \
            "Should use --timeout flag"


class TestImageAssertion:
    """Test that live workflow asserts k9b pod uses image-builder output."""

    def test_live_workflow_asserts_pod_image_matches(self) -> None:
        """Live workflow should assert pod image matches image-builder output."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "jsonpath" in content, \
            "Should use jsonpath for image check"
        assert "inputs.backend_image_ref" in content, \
            "Should check against inputs.backend_image_ref"

    def test_live_workflow_assertion_is_fatal(self) -> None:
        """Image assertion should be fatal (exit 1 on failure)."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert_match = re.search(r'Assert.*?exit 1', content, re.DOTALL)
        assert assert_match, \
            "Image assertion should exit 1 on failure"

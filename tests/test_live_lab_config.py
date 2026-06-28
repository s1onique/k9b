"""Unit tests for live lab configuration and workflow inputs (namespace mode)."""

import re
from pathlib import Path

# Path to the workflow files
WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab.yml"
WORKFLOW_LIVE_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"
IMAGE_BUILDER_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-image-builder.yml"
INCIDENT_MANIFEST = Path(__file__).parent.parent / "fixtures" / "lab" / "live" / "pod-failure" / "injected-change.yaml"
RBAC_MANIFEST = Path(__file__).parent.parent / "deploy" / "github-actions" / "k9b-cnpg-live-lab-runner-rbac.yaml"


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

    def test_live_workflow_runs_on_spbnix_k8s_scale_set(self) -> None:
        """Live workflow should run on spbnix-k8s ARC runner scale set."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "runs-on: spbnix-k8s" in content, \
            "Should run on spbnix-k8s runner scale set"
        assert "github-actions-runner" not in content, \
            "Should NOT run on github-actions-runner label"
        assert "runs-on:\n      - self-hosted" not in content, \
            "Should NOT use multi-label self-hosted runner"

    def test_live_workflow_does_not_use_docker_scale_set(self) -> None:
        """Live workflow should NOT run on Docker-capable runner scale set."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "spbnix-k8s-docker" not in content, \
            "Should NOT run on spbnix-k8s-docker scale set (no Docker needed)"

    def test_live_workflow_has_bootstrap_and_preflight(self) -> None:
        """Live workflow should have bootstrap and kubectl verification steps."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "Bootstrap protected kubeconfig" in content, \
            "Should have bootstrap step"
        assert "Verify kubectl with protected kubeconfig" in content, \
            "Should verify kubectl with protected kubeconfig"
        assert "kubectl --kubeconfig" in content, \
            "Should use --kubeconfig for kubectl"
        assert "cluster-info" in content.lower(), \
            "Should verify cluster reachability"

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
        assert "clusters.postgresql.cnpg.io" in content, \
            "Should check CNPG CRD"
        assert "cnpg-system" in content, \
            "Should check cnpg-system namespace"

    def test_live_workflow_creates_unique_namespace(self) -> None:
        """Live workflow should create unique lab namespace from GITHUB_RUN_ID."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "k9b-cnpg-lab-${{ github.run_id }}" in content, \
            "Should create namespace from GITHUB_RUN_ID"
        assert "kubectl create namespace" in content or "create namespace" in content, \
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
        assert "delete namespace" in content, \
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
        # Extract step order (sanitized pipeline)
        collect_logs_pos = content.find("Collect")
        cleanup_pos = content.find("Cleanup sensitive files")
        sanitize_pos = content.find("Sanitize artifacts for verification")
        verify_pos = content.find("Verify sanitized artifacts")
        upload_pos = content.find("Upload live lab artifacts")
        # Correct order: collect -> cleanup -> sanitize -> verify -> upload
        assert collect_logs_pos < cleanup_pos < sanitize_pos < verify_pos < upload_pos, \
            f"Step order wrong: collect={collect_logs_pos}, cleanup={cleanup_pos}, sanitize={sanitize_pos}, verify={verify_pos}, upload={upload_pos}"
        # Verify safety boundary
        assert "SANITIZED_ARTIFACTS_SAFE=true" in content, \
            "Should set SANITIZED_ARTIFACTS_SAFE after sanitization"
        assert "path: ./lab-artifacts/live-sanitized/**" in content, \
            "Should upload sanitized artifacts only"
        assert "path: ./lab-artifacts/live/**" not in content, \
            "Should NOT upload raw live artifacts"


class TestKubectlBootstrap:
    """Test kubectl bootstrap using protected environment kubeconfig (not in-cluster SA)."""

    def test_live_workflow_installs_kubectl_before_preflight(self) -> None:
        """Live workflow should install kubectl using azure/setup-kubectl before bootstrap."""
        content = WORKFLOW_LIVE_FILE.read_text()
        setup_pos = content.find("azure/setup-kubectl@v4")
        bootstrap_pos = content.find("Bootstrap protected kubeconfig")
        assert setup_pos != -1, "azure/setup-kubectl@v4 not found"
        assert bootstrap_pos != -1, "Bootstrap protected kubeconfig step not found"
        assert setup_pos < bootstrap_pos, \
            f"kubectl setup ({setup_pos}) must come before bootstrap ({bootstrap_pos})"

    def test_live_workflow_uses_pinned_kubectl_version(self) -> None:
        """Live workflow should use a pinned kubectl version, not 'latest'.
        
        Requires azure/setup-kubectl@v4 to specify with.version, and accepts either:
        a) inline semantic version (e.g., version: 'v1.31.0')
        b) env indirection (version: '${{ env.KUBECTL_VERSION }}') but only when 
           KUBECTL_VERSION is defined as a pinned semantic version in env.
        
        The key contract is: NOT floating/latest.
        """
        content = WORKFLOW_LIVE_FILE.read_text()
        
        # Check setup-kubectl has a version specified in with: block
        # Accepts both quoted and unquoted values
        setup_kubectl_match = re.search(
            r"azure/setup-kubectl@v4.*?"
            r"with:\s*"
            r"(?:version:\s*['\"]v\d+\.\d+(?:\.\d+)?['\"]"  # a) inline version (quoted)
            r"|version:\s*['\"]?\${{\s*env\.KUBECTL_VERSION\s*}}['\"]?)"  # b) env indirection (quoted or unquoted)
            ,
            content,
            re.DOTALL
        )
        assert setup_kubectl_match, \
            "azure/setup-kubectl@v4 must specify with.version (inline or via KUBECTL_VERSION)"
        
        # Check if using env indirection (with or without quotes)
        using_env_indirection = bool(re.search(
            r"version:\s*['\"]?\${{\s*env\.KUBECTL_VERSION\s*}}['\"]?",
            content
        ))
        
        if using_env_indirection:
            # If using env indirection, KUBECTL_VERSION must be defined as a pinned version
            kubectl_version_match = re.search(
                r"KUBECTL_VERSION:\s*['\"]v\d+\.\d+\.\d+['\"]",
                content
            )
            assert kubectl_version_match, \
                "KUBECTL_VERSION must be defined with a pinned semantic version (e.g., 'v1.31.0')"
        
        # Should NOT use 'latest' inline (with or without quotes)
        assert not re.search(r"version:\s*['\"]?latest['\"]?", content), \
            "Should NOT use 'latest' for kubectl version"
        
        # Should NOT use 'latest' via KUBECTL_VERSION env
        env_latest_match = re.search(r"KUBECTL_VERSION:\s*['\"]latest['\"]", content)
        assert not env_latest_match, \
            "KUBECTL_VERSION should not be 'latest'"

    def test_live_workflow_uses_protected_kubeconfig_not_incluster(self) -> None:
        """Live workflow should use protected kubeconfig, NOT in-cluster SA mount."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Should use protected environment
        assert "environment: k9b-live-lab-admin" in content, \
            "Should use protected environment k9b-live-lab-admin"
        # Should use the bootstrap script
        assert "k9b_cnpg_live_lab_bootstrap.sh" in content, \
            "Should use bootstrap script for kubeconfig"
        # Should NOT configure in-cluster kubeconfig from SA mount
        assert "/var/run/secrets/kubernetes.io/serviceaccount" not in content, \
            "Should NOT use in-cluster service account mount"
        assert "kubectl config set-cluster in-cluster" not in content, \
            "Should NOT configure in-cluster context"
        assert "KUBERNETES_SERVICE_HOST" not in content, \
            "Should NOT check KUBERNETES_SERVICE_HOST"

    def test_live_workflow_calls_bootstrap_before_using_kubectl(self) -> None:
        """Bootstrap must complete before kubectl is used."""
        content = WORKFLOW_LIVE_FILE.read_text()
        bootstrap_pos = content.find("Bootstrap protected kubeconfig")
        # Find first kubectl --kubeconfig usage
        first_kubectl = content.find("kubectl --kubeconfig=")
        assert bootstrap_pos != -1, "Bootstrap step not found"
        assert first_kubectl != -1, "No kubectl --kubeconfig usage found"
        assert bootstrap_pos < first_kubectl, \
            f"Bootstrap ({bootstrap_pos}) must come before kubectl usage ({first_kubectl})"

    def test_live_workflow_exports_kubeconfig_path(self) -> None:
        """Live workflow should export KUBECONFIG path to GITHUB_ENV via bootstrap."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Bootstrap script exports KUBECONFIG via echo >> ${GITHUB_ENV}
        assert "GITHUB_ENV" in content, \
            "Should use GITHUB_ENV for KUBECONFIG"
        # Should use KUBECONFIG from bootstrap
        assert "${KUBECONFIG}" in content or "$KUBECONFIG" in content, \
            "Should use KUBECONFIG from bootstrap"

    def test_live_workflow_uses_kubeconfig_for_all_kubectl(self) -> None:
        """All kubectl commands must use --kubeconfig flag.
        
        Only checks actual kubectl command invocations in shell run blocks.
        Skips cache restore/save metadata (id:, path:, key:, uses: actions/cache/*)
        since these are YAML metadata, not shell commands.
        """
        content = WORKFLOW_LIVE_FILE.read_text()
        
        # Count kubectl --kubeconfig occurrences (primary check)
        kubectl_kubeconfig_count = len(re.findall(r"kubectl\s+--kubeconfig", content))
        assert kubectl_kubeconfig_count > 10, \
            f"Expected many kubectl --kubeconfig usages, found {kubectl_kubeconfig_count}"
        
        # Verify no kubectl commands in run: blocks without --kubeconfig
        lines = content.split('\n')
        bare_kubectl_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Skip if no kubectl reference
            if 'kubectl' not in line:
                continue
            
            # Skip if already has --kubeconfig
            if '--kubeconfig' in line:
                continue
            
            # Skip comments
            if stripped.startswith('#'):
                continue
            
            # Skip YAML step metadata lines that happen to contain "kubectl":
            # - id: cache-kubectl
            # - path: ${{ runner.tool_cache }}/kubectl
            # - key: kubectl-${{ runner.os }}-${{ runner.arch }}-${{ env.KUBECTL_VERSION }}
            # - if: steps.cache-kubectl.outputs.cache-hit != 'true'
            # - uses: actions/cache/restore@v4 (cache action with kubectl in path/key is OK)
            if re.match(r'^\s*id:\s*\S', stripped):
                continue  # id: cache-kubectl
            if re.match(r'^\s*path:', stripped):
                continue  # path: ${{ runner.tool_cache }}/kubectl
            if re.match(r'^\s*key:', stripped):
                continue  # key: kubectl-... (cache key, not a command)
            if re.match(r'^\s*if:', stripped):
                continue  # if: steps.cache-kubectl.outputs...
            if 'uses:' in line and 'actions/cache' in stripped:
                continue  # uses: actions/cache/restore@v4 or save@v4
            if 'uses:' in line:
                continue  # Skip all other uses: steps (e.g., azure/setup-kubectl)
            
            # Skip step names (contain '- name:')
            if '- name:' in line:
                continue
            
            # Skip echo commands (just echo statements mentioning kubectl)
            if stripped.startswith('echo '):
                continue
            
            # Skip description lines
            if re.match(r'^\s*description:', stripped):
                continue
            
            # Skip 'with:' blocks (part of uses: steps)
            if stripped.startswith('with:'):
                continue
            
            # Skip YAML list item indicators for 'with' values (e.g., version:, repository:)
            if re.match(r'^\s+\w+:', stripped) and not stripped.startswith('run:'):
                # This is a YAML key-value pair, not a command
                # But be careful: 'run: |' or 'run: >' starts a run block
                continue
            
            # If we get here, it's likely a real kubectl command without --kubeconfig
            bare_kubectl_lines.append(line.strip())
        
        assert len(bare_kubectl_lines) == 0, \
            f"Found kubectl commands without --kubeconfig: {bare_kubectl_lines}"

    def test_live_workflow_configures_readonly_diagnostics(self) -> None:
        """Live workflow should have bounded preflight diagnostics without token exposure."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Should verify kubectl works with protected kubeconfig
        assert "Verify kubectl with protected kubeconfig" in content, \
            "Should verify kubectl with protected kubeconfig"
        # Should have cluster-info
        assert "cluster-info" in content.lower() or "cluster_info" in content, \
            "Should verify cluster reachability"

    def test_cache_metadata_with_kubectl_is_not_bare_command(self) -> None:
        """Cache restore/save metadata containing 'kubectl' must not be flagged as bare kubectl commands.
        
        Regression test: cache metadata like id: cache-kubectl, path: .../kubectl, 
        key: kubectl-... are YAML metadata, not shell commands. The kubeconfig test
        should ignore these lines.
        """
        content = WORKFLOW_LIVE_FILE.read_text()
        
        # Verify cache restore step exists with kubectl in metadata
        assert "actions/cache/restore@v5" in content, \
            "Should use actions/cache/restore@v5"
        assert "id: cache-kubectl" in content, \
            "Should have id: cache-kubectl step"
        assert "path: ${{ runner.tool_cache }}/kubectl" in content, \
            "Should have kubectl path in cache restore"
        assert "key: kubectl-" in content, \
            "Should have kubectl key in cache restore"
        
        # Verify cache save step exists
        assert "actions/cache/save@v5" in content, \
            "Should use actions/cache/save@v5"
        
        # Verify the cache metadata contains 'kubectl' but is NOT a shell command
        lines_with_kubectl = [line for line in content.split('\n') if 'kubectl' in line]
        
        # Filter to lines that are cache metadata (should be skipped by kubeconfig test)
        cache_metadata_lines = [
            line for line in lines_with_kubectl
            if 'id: cache-kubectl' in line 
            or 'path: ${{ runner.tool_cache }}/kubectl' in line
            or 'key: kubectl-' in line
            or 'if: steps.cache-kubectl' in line
        ]
        
        assert len(cache_metadata_lines) > 0, \
            "Should have cache metadata lines containing 'kubectl'"
        
        # These lines should NOT be shell commands (no run: prefix)
        for line in cache_metadata_lines:
            assert not re.match(r'^\s*run:', line.strip()), \
                f"Cache metadata should not be a run: block: {line.strip()}"


class TestRBACPreflight:
    """Test fatal RBAC preflight checks for live lab permissions."""

    def test_live_workflow_has_fatal_rbac_preflight(self) -> None:
        """Live workflow should have RBAC preflight checks via bootstrap script."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # The bootstrap script handles credential validation
        assert "k9b_cnpg_live_lab_bootstrap.sh" in content, \
            "Should use bootstrap script that validates credentials"

    def test_live_workflow_uses_rbac_helper_script(self) -> None:
        """Live workflow should use RBAC helper script for namespace checks."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "k9b_cnpg_live_lab_rbac_preflight.sh namespace" in content, \
            "Should use RBAC helper script for namespace checks"

    def test_live_workflow_uses_rbac_helper_script_namespace(self) -> None:
        """Live workflow should use RBAC helper script for namespace checks."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "k9b_cnpg_live_lab_rbac_preflight.sh namespace" in content, \
            "Should use RBAC helper script for namespace checks"

    def test_live_workflow_has_subject_diagnostics(self) -> None:
        """Bootstrap script should validate credential source (detects wrong identity)."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Bootstrap script validates credential source
        assert "k9b_cnpg_live_lab_bootstrap.sh" in content, \
            "Should use bootstrap script for credential validation"

    def test_live_workflow_no_raw_auth_can_i_cluster(self) -> None:
        """Live workflow should NOT use raw kubectl auth can-i for cluster checks."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Find the Verify live lab Kubernetes permissions step
        step_match = re.search(
            r'- name: Verify live lab Kubernetes permissions\s*\n\s+run:\s*(.*?)\n\s+(?=- name:|\s+- uses:)',
            content,
            re.DOTALL
        )
        if step_match:
            cluster_run = step_match.group(1)
            # Should only have the script call, not raw kubectl auth can-i commands
            assert "scripts/k9b_cnpg_live_lab_rbac_preflight.sh cluster" in cluster_run, \
                "Should call RBAC preflight script"
            # Should NOT have raw kubectl auth can-i commands
            assert "kubectl auth can-i" not in cluster_run, \
                "Should NOT have raw kubectl auth can-i commands"

    def test_live_workflow_no_raw_auth_can_i_namespace(self) -> None:
        """Live workflow should NOT use raw kubectl auth can-i for namespace checks."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Extract the namespace RBAC section
        ns_section_match = re.search(
            r'Verify namespace-scoped Kubernetes permissions.*?(?=\n\s{0,4}-\sname:|$)',
            content,
            re.DOTALL
        )
        if ns_section_match:
            ns_section = ns_section_match.group(0)
            # Should not have bare kubectl auth can-i commands
            assert "kubectl auth can-i create pods -n" not in ns_section, \
                "Should NOT have raw kubectl auth can-i for namespace checks"

    def test_live_workflow_checks_get_pods_all_namespaces(self) -> None:
        """Live workflow should check get pods permission across all namespaces (via script)."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # Check the script exists and is referenced
        assert "k9b_cnpg_live_lab_rbac_preflight.sh" in content, \
            "Should reference RBAC preflight script"

    def test_live_workflow_checks_get_nodes(self) -> None:
        """Live workflow should check get nodes permission (via script)."""
        # Check the script exists
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        assert rbac_script.exists(), f"RBAC script should exist at {rbac_script}"
        script_content = rbac_script.read_text()
        assert "get nodes" in script_content, \
            "Script should check get nodes permission"

    def test_live_workflow_checks_create_namespaces(self) -> None:
        """Live workflow should check create namespaces permission (via script)."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        assert "create namespaces" in script_content, \
            "Script should check create namespaces permission"

    def test_live_workflow_checks_delete_namespaces(self) -> None:
        """Live workflow should check delete namespaces permission (via script)."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        assert "delete namespaces" in script_content, \
            "Script should check delete namespaces permission"

    def test_live_workflow_checks_patch_namespaces(self) -> None:
        """Live workflow should check patch namespaces permission (via script)."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        assert "patch namespaces" in script_content, \
            "Script should check patch namespaces permission (required for kubectl label)"

    def test_live_workflow_checks_cnpg_crd_access(self) -> None:
        """Live workflow should check CNPG CRD access permissions (via script)."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        assert "clusters.postgresql.cnpg.io" in script_content, \
            "Script should check CNPG CRD permission"
        assert "cnpg-system" in script_content, \
            "Script should check cnpg-system namespace access"

    def test_live_workflow_has_namespace_scoped_permissions(self) -> None:
        """Live workflow should verify namespace-scoped permissions after namespace creation."""
        content = WORKFLOW_LIVE_FILE.read_text()
        # The workflow uses "Check namespace-scoped Kubernetes permissions"
        assert "Check namespace-scoped Kubernetes permissions" in content or \
               "k9b_cnpg_live_lab_rbac_preflight.sh namespace" in content, \
            "Should have namespace-scoped permission check step"

    def test_rbac_script_has_check_can_i_helper(self) -> None:
        """RBAC script should have check_can_i helper function."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        assert "check_can_i()" in script_content, \
            "Script should have check_can_i function"
        assert "--quiet" in script_content, \
            "Script should use --quiet flag"

    def test_rbac_script_failure_prints_error(self) -> None:
        """RBAC script should print actionable error on failure."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        assert "ERROR: missing permission for:" in script_content, \
            "Script should print missing permission error"
        assert "Command: kubectl auth can-i" in script_content, \
            "Script should print the failing command"

    def test_rbac_script_has_subject_diagnostics(self) -> None:
        """RBAC script should have subject diagnostics function."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        assert "print_subject_diagnostics" in script_content, \
            "Script should have subject diagnostics function"
        assert "kubectl auth whoami" in script_content, \
            "Script should try kubectl auth whoami"

    def test_rbac_script_no_token_leakage(self) -> None:
        """RBAC script should not leak tokens."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        # Should not echo token or use --raw
        assert "echo.*token" not in script_content.lower(), \
            "Script should not echo token"
        assert "config view --raw" not in script_content, \
            "Script should not use kubectl config view --raw"

    def test_rbac_script_has_set_euo_pipefail(self) -> None:
        """RBAC script should have set -euo pipefail."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        assert "set -euo pipefail" in script_content, \
            "Script should have set -euo pipefail"


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

    def test_live_workflow_uses_helm_configmap_driver(self) -> None:
        """Live workflow should use HELM_DRIVER=configmap to avoid Secret read permissions."""
        content = WORKFLOW_LIVE_FILE.read_text()
        assert "HELM_DRIVER" in content, \
            "Should set HELM_DRIVER environment variable"
        assert "configmap" in content, \
            "Should use configmap driver for Helm"


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


class TestRBACPreflightNamedResource:
    """Test that RBAC preflight uses named-resource TYPE/NAME form for resourceNames-restricted rules."""

    def test_rbac_preflight_uses_named_crd_resource_check(self) -> None:
        """RBAC preflight should use named TYPE/NAME form for resourceNames-restricted CRD check."""
        rbac_script = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_rbac_preflight.sh"
        script_content = rbac_script.read_text()
        # Should use fully qualified TYPE/NAME form
        assert "customresourcedefinitions.apiextensions.k8s.io/clusters.postgresql.cnpg.io" in script_content, \
            "Should use named resource TYPE/NAME form for CRD check"
        # Should NOT use the ambiguous broad form
        assert "get crd clusters.postgresql.cnpg.io" not in script_content, \
            "Should NOT use broad 'get crd' form"

    def test_rbac_manifest_keeps_cnpg_crd_resource_name_scope(self) -> None:
        """RBAC manifest should keep resourceNames-restricted scope for CNPG CRD."""
        content = RBAC_MANIFEST.read_text()
        # Should have resourceNames restriction
        assert 'resourceNames: ["clusters.postgresql.cnpg.io"]' in content, \
            "Manifest should keep resourceNames restriction for CNPG CRD"
        # Should grant only get verb
        assert 'verbs: ["get"]' in content, \
            "Manifest should grant only get verb for CRD"
        # Should NOT grant wildcard resources
        assert not re.search(r'resources:\s*\[\s*["\']?\*["\']?\s*\]', content), \
            "Manifest should NOT use wildcard resources"


class TestRBACManifest:
    """Test the RBAC manifest for live lab runner."""

    def test_rbac_manifest_exists(self) -> None:
        """RBAC manifest should exist."""
        assert RBAC_MANIFEST.exists(), f"RBAC manifest should exist at {RBAC_MANIFEST}"

    def test_rbac_manifest_contains_cluster_role(self) -> None:
        """RBAC manifest should contain ClusterRole."""
        content = RBAC_MANIFEST.read_text()
        assert "kind: ClusterRole" in content, \
            "Manifest should contain ClusterRole"

    def test_rbac_manifest_contains_cluster_role_binding(self) -> None:
        """RBAC manifest should contain ClusterRoleBinding."""
        content = RBAC_MANIFEST.read_text()
        assert "kind: ClusterRoleBinding" in content, \
            "Manifest should contain ClusterRoleBinding"

    def test_rbac_manifest_no_cluster_admin(self) -> None:
        """RBAC manifest should NOT bind cluster-admin."""
        content = RBAC_MANIFEST.read_text()
        # Check only non-comment lines
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            assert "cluster-admin" not in stripped.lower(), \
                f"Manifest should NOT bind cluster-admin: {stripped[:100]}"

    def test_rbac_manifest_no_wildcard_verbs(self) -> None:
        """RBAC manifest should NOT use wildcard verbs."""
        content = RBAC_MANIFEST.read_text()
        # Check for wildcard verbs in rules (not in comments)
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or not stripped:
                continue
            # Check for wildcard verbs
            assert not re.search(r'verbs:\s*\[\s*["\']?\*["\']?\s*\]', line), \
                f"Manifest should NOT use wildcard verbs: {line.strip()}"

    def test_rbac_manifest_no_wildcard_resources(self) -> None:
        """RBAC manifest should NOT use wildcard resources."""
        content = RBAC_MANIFEST.read_text()
        # Check for wildcard resources in rules
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or not stripped:
                continue
            # Check for wildcard resources
            assert not re.search(r'resources:\s*\[\s*["\']?\*["\']?\s*\]', line), \
                f"Manifest should NOT use wildcard resources: {line.strip()}"

    def test_rbac_manifest_has_service_account_subject(self) -> None:
        """RBAC manifest should have ServiceAccount subject."""
        content = RBAC_MANIFEST.read_text()
        assert "kind: ServiceAccount" in content, \
            "Manifest should have ServiceAccount subject"
        assert "- kind: ServiceAccount" in content, \
            "Manifest should specify ServiceAccount kind in subjects"

    def test_rbac_manifest_has_proper_labels(self) -> None:
        """RBAC manifest should have proper labels."""
        content = RBAC_MANIFEST.read_text()
        assert "app.kubernetes.io/name: k9b-cnpg-incident-lab" in content, \
            "Manifest should have app label"
        assert "app.kubernetes.io/component: ci-rbac" in content, \
            "Manifest should have component label"

    def test_rbac_manifest_has_namespace_lifecycle(self) -> None:
        """RBAC manifest should include namespace lifecycle permissions."""
        content = RBAC_MANIFEST.read_text()
        assert '"namespaces"' in content, \
            "Manifest should include namespaces resource"
        assert "create" in content and "delete" in content, \
            "Manifest should include create/delete for namespaces"

    def test_rbac_manifest_has_cnpg_permissions(self) -> None:
        """RBAC manifest should include CNPG Cluster permissions."""
        content = RBAC_MANIFEST.read_text()
        assert "clusters.postgresql.cnpg.io" in content or "clusters" in content, \
            "Manifest should include CNPG Cluster permissions"
        assert "postgresql.cnpg.io" in content, \
            "Manifest should include CNPG API group"

    def test_rbac_manifest_has_actual_runner_service_account(self) -> None:
        """RBAC manifest should have actual runner service account, not placeholder."""
        content = RBAC_MANIFEST.read_text()
        # Check no placeholders remain
        assert "<RUNNER_SERVICE_ACCOUNT>" not in content, \
            "Manifest should not contain <RUNNER_SERVICE_ACCOUNT> placeholder"
        assert "<RUNNER_NAMESPACE>" not in content, \
            "Manifest should not contain <RUNNER_NAMESPACE> placeholder"
        # Check actual values are present
        assert "name: spbnix-k8s-gha-rs-no-permission" in content, \
            "Manifest should contain actual service account name"
        assert "namespace: github-actions-runner" in content, \
            "Manifest should contain actual service account namespace"

    def test_rbac_manifest_no_invalid_namespace_rule_field(self) -> None:
        """RBAC manifest should NOT have 'namespaces:' field inside RBAC rules."""
        content = RBAC_MANIFEST.read_text()
        # The word "namespaces" should only appear as a resource, not as a field key
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # Check that we don't have "namespaces:" as a rule field (it would mean someone tried to
            # grant namespace-level scoping incorrectly)
            assert not re.match(r'^\s*namespaces:\s*$', stripped), \
                f"Manifest should not have 'namespaces:' field in RBAC rules: {stripped}"

    def test_rbac_manifest_does_not_grant_secret_read(self) -> None:
        """RBAC manifest should NOT grant Secret get/list/watch verbs."""
        content = RBAC_MANIFEST.read_text()
        # Check that secrets are only granted create/update/delete
        assert 'resources: ["secrets"]' in content, \
            "Manifest should grant secrets permissions"
        # Check that we have create, delete, patch, update for secrets
        assert 'verbs: ["create", "delete", "patch", "update"]' in content, \
            "Manifest should grant only create/update/delete for secrets"
        # Check that we don't have get/list/watch on secrets
        # Look for patterns like 'verbs: ["get"]' or 'verbs: ["get", "list", "watch"]' after secrets resource
        secret_block_match = re.search(
            r'resources:\s*\[\s*["\']?secrets["\']?\s*\].*?verbs:\s*\[(.*?)\]',
            content,
            re.DOTALL
        )
        if secret_block_match:
            verbs = secret_block_match.group(1)
            assert "get" not in verbs.lower(), \
                f"Manifest should NOT grant 'get' verb on secrets: found {verbs}"
            assert "list" not in verbs.lower(), \
                f"Manifest should NOT grant 'list' verb on secrets: found {verbs}"
            assert "watch" not in verbs.lower(), \
                f"Manifest should NOT grant 'watch' verb on secrets: found {verbs}"

    def test_rbac_manifest_documents_actual_service_account(self) -> None:
        """RBAC manifest should document the actual runner service account."""
        content = RBAC_MANIFEST.read_text()
        # Should document the actual service account in comments
        assert "spbnix-k8s-gha-rs-no-permission" in content, \
            "Manifest should document actual service account name"
        assert "github-actions-runner" in content, \
            "Manifest should document actual service account namespace"
        # Full subject format in comments
        assert "system:serviceaccount:github-actions-runner:spbnix-k8s-gha-rs-no-permission" in content, \
            "Manifest should document full service account subject"

    def test_rbac_manifest_deployments_under_apps_api_group(self) -> None:
        """RBAC manifest should grant deployments under apiGroups: apps for cnpg-system."""
        content = RBAC_MANIFEST.read_text()
        # Find the Role for cnpg-system
        role_match = re.search(
            r'kind: Role.*?name: k9b-cnpg-live-lab-runner-cnpg-system.*?rules:(.*?)(?=---\s*#|$)',
            content,
            re.DOTALL
        )
        assert role_match, "Should have Role for cnpg-system"
        role_rules = role_match.group(1)
        # Check that deployments are under apps apiGroup
        assert 'apiGroups: ["apps"]' in role_rules, \
            "Role for cnpg-system should use apiGroups: [\"apps\"] for deployments"
        assert 'resources: ["deployments"]' in role_rules, \
            "Role for cnpg-system should grant deployments"


class TestOtelLiveLabRunnerContract:
    """Test that OTel demo lab uses the same runner selector as CNPG live lab."""

    def test_otel_workflow_file_exists(self) -> None:
        """The OTel demo workflow file should exist."""
        OTEL_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-incident-lab.yml"
        assert OTEL_WORKFLOW_FILE.exists(), f"OTel workflow file not found at {OTEL_WORKFLOW_FILE}"

    def test_otel_live_lab_uses_spbnix_k8s(self) -> None:
        """OTel live lab should use spbnix-k8s runner (same as CNPG live lab)."""
        OTEL_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-incident-lab.yml"
        content = OTEL_WORKFLOW_FILE.read_text()
        assert "runs-on: spbnix-k8s" in content, \
            "OTel live lab should run on spbnix-k8s (same as CNPG live lab)"

    def test_otel_live_lab_does_not_use_ubuntu_latest(self) -> None:
        """OTel live lab should NOT use ubuntu-latest runner (cannot reach private API)."""
        OTEL_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-incident-lab.yml"
        content = OTEL_WORKFLOW_FILE.read_text()
        # Find the live-k3s-lab job section and check its runs-on
        live_lab_match = re.search(
            r'live-k3s-lab:.*?runs-on:\s*(\S+)',
            content,
            re.DOTALL
        )
        assert live_lab_match, "live-k3s-lab job should have runs-on"
        runner = live_lab_match.group(1)
        assert runner != "ubuntu-latest", \
            f"OTel live lab should NOT use ubuntu-latest (uses {runner})"

    def test_both_live_labs_use_same_runner(self) -> None:
        """Both CNPG and OTel live labs should use the same spbnix-k8s runner."""
        content_cnpg = WORKFLOW_LIVE_FILE.read_text()
        otel_workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-incident-lab.yml"
        content_otel = otel_workflow_path.read_text()

        # Extract runs-on for each live lab
        cnpg_match = re.search(r'live-k3s-lab:.*?runs-on:\s*(\S+)', content_cnpg, re.DOTALL)
        otel_match = re.search(r'live-k3s-lab:.*?runs-on:\s*(\S+)', content_otel, re.DOTALL)

        assert cnpg_match, "CNPG live lab should have runs-on"
        assert otel_match, "OTel live lab should have runs-on"

        cnpg_runner = cnpg_match.group(1)
        otel_runner = otel_match.group(1)

        assert cnpg_runner == otel_runner, \
            f"Both live labs should use same runner: CNPG={cnpg_runner}, OTel={otel_runner}"
        assert cnpg_runner == "spbnix-k8s", \
            f"Both live labs should use spbnix-k8s, got {cnpg_runner}"

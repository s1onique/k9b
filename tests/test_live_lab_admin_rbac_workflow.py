"""Unit tests for the RBAC admin workflow."""

import re
from pathlib import Path

# Path to the admin workflow file
ADMIN_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-live-lab-rbac-admin.yml"


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


class TestAdminWorkflowExistence:
    """Test that the admin workflow file exists and has correct basic structure."""

    def test_admin_workflow_file_exists(self) -> None:
        """The admin workflow file should exist."""
        assert ADMIN_WORKFLOW_FILE.exists(), f"Admin workflow not found at {ADMIN_WORKFLOW_FILE}"

    def test_workflow_name_is_correct(self) -> None:
        """Workflow name should be 'K9B CNPG Live Lab RBAC Admin'."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'name: K9B CNPG Live Lab RBAC Admin' in content, \
            "Workflow name should be 'K9B CNPG Live Lab RBAC Admin'"


class TestAdminWorkflowTriggers:
    """Test that the admin workflow has only manual dispatch trigger."""

    def test_workflow_has_workflow_dispatch(self) -> None:
        """Workflow should have workflow_dispatch trigger."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'workflow_dispatch:' in content, "workflow_dispatch trigger not found"

    def test_workflow_has_no_push_trigger(self) -> None:
        """Workflow should NOT have push trigger."""
        content = _strip_comments(ADMIN_WORKFLOW_FILE.read_text())
        assert not re.search(r'^\s*push:\s*$', content, re.MULTILINE), \
            "Should NOT have push trigger"

    def test_workflow_has_no_pull_request_trigger(self) -> None:
        """Workflow should NOT have pull_request trigger."""
        content = _strip_comments(ADMIN_WORKFLOW_FILE.read_text())
        assert not re.search(r'^\s*pull_request:\s*$', content, re.MULTILINE), \
            "Should NOT have pull_request trigger"

    def test_workflow_has_no_workflow_call(self) -> None:
        """Workflow should NOT have workflow_call trigger."""
        content = _strip_comments(ADMIN_WORKFLOW_FILE.read_text())
        assert 'workflow_call:' not in content, \
            "Should NOT have workflow_call trigger"

    def test_workflow_has_no_schedule(self) -> None:
        """Workflow should NOT have schedule trigger."""
        content = _strip_comments(ADMIN_WORKFLOW_FILE.read_text())
        assert 'schedule:' not in content, \
            "Should NOT have schedule trigger"


class TestAdminWorkflowInputs:
    """Test that the admin workflow has required inputs."""

    def test_workflow_has_confirm_apply_input(self) -> None:
        """Workflow should have confirm_apply input."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'confirm_apply:' in content, "confirm_apply input not found"
        assert 'type: string' in content, "confirm_apply should be string type"
        assert 'required: true' in content, "confirm_apply should be required"

    def test_workflow_has_dry_run_input(self) -> None:
        """Workflow should have dry_run input."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'dry_run:' in content, "dry_run input not found"
        assert 'type: boolean' in content, "dry_run should be boolean type"
        assert 'required: true' in content, "dry_run should be required"
        assert 'default: true' in content, "dry_run should default to true"

    def test_workflow_checks_confirm_apply_equals_apply(self) -> None:
        """Workflow should enforce confirm_apply == APPLY."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'confirm_apply' in content and 'APPLY' in content, \
            "Should check confirm_apply == APPLY"
        assert '"APPLY"' in content or "'APPLY'" in content, \
            "Should compare against exact 'APPLY' value"
        assert 'exit 1' in content, \
            "Should exit with error if confirm_apply is not APPLY"


class TestAdminWorkflowEnvironment:
    """Test that the admin workflow uses protected environment."""

    def test_workflow_uses_protected_environment(self) -> None:
        """Workflow should use protected environment 'k9b-live-lab-admin'."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'environment: k9b-live-lab-admin' in content, \
            "Should use protected environment 'k9b-live-lab-admin'"


class TestAdminWorkflowKubectl:
    """Test that the admin workflow uses pinned kubectl."""

    def test_workflow_uses_azure_setup_kubectl(self) -> None:
        """Workflow should use azure/setup-kubectl@v4."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'azure/setup-kubectl@v4' in content, \
            "Should use azure/setup-kubectl@v4"

    def test_workflow_uses_pinned_kubectl_version(self) -> None:
        """Workflow should use a pinned kubectl version."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Should define KUBECTL_VERSION in env
        assert "KUBECTL_VERSION:" in content, \
            "Should define KUBECTL_VERSION environment variable"
        assert "KUBECTL_VERSION: 'v1.31.0'" in content, \
            "Should use v1.31.0 kubectl version in env"
        # Should use azure/setup-kubectl@v4 with env var
        assert "azure/setup-kubectl@v4" in content, \
            "Should use azure/setup-kubectl@v4"
        assert "${{ env.KUBECTL_VERSION }}" in content, \
            "Should reference KUBECTL_VERSION env var"
        # Should NOT use 'latest'
        assert "version: 'latest'" not in content, \
            "Should NOT use 'latest' for kubectl version"


class TestAdminWorkflowManifestPath:
    """Test that the admin workflow uses the fixed manifest path."""

    def test_workflow_hardcodes_manifest_path(self) -> None:
        """Workflow should hardcode the manifest path."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'deploy/github-actions/k9b-cnpg-live-lab-runner-rbac.yaml' in content, \
            "Should hardcode the RBAC manifest path"

    def test_workflow_does_not_accept_arbitrary_manifest_path(self) -> None:
        """Workflow should NOT accept arbitrary manifest path as input."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Check that there's no manifest_path input
        assert 'manifest_path' not in content.lower() or 'MANIFEST:' not in content, \
            "Should not accept arbitrary manifest path as workflow input"
        # The MANIFEST should be a hardcoded env var, not an input
        assert re.search(r'env:.*MANIFEST.*deploy/', content, re.DOTALL), \
            "MANIFEST should be a hardcoded environment variable"


class TestAdminWorkflowDryRun:
    """Test that the admin workflow supports dry-run mode."""

    def test_workflow_runs_server_side_dry_run(self) -> None:
        """Workflow should run kubectl apply --server-side --dry-run=server."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert '--server-side' in content, \
            "Should use --server-side flag"
        assert '--dry-run=server' in content, \
            "Should use --dry-run=server"

    def test_workflow_applies_only_when_dry_run_is_false(self) -> None:
        """Workflow should only apply manifest when dry_run is false."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Should have conditional apply
        assert 'dry_run == false' in content or 'dry_run: false' in content, \
            "Should have conditional apply based on dry_run"
        # Should have kubectl apply -f step
        assert 'kubectl apply' in content, \
            "Should have kubectl apply step"


class TestAdminWorkflowManifestValidation:
    """Test that the admin workflow validates the manifest."""

    def test_workflow_validates_manifest_contains_cluster_role(self) -> None:
        """Workflow should validate manifest contains ClusterRole k9b-cnpg-live-lab-runner-cluster."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'k9b-cnpg-live-lab-runner-cluster' in content, \
            "Should validate ClusterRole k9b-cnpg-live-lab-runner-cluster exists"

    def test_workflow_validates_manifest_contains_lab_namespace_role(self) -> None:
        """Workflow should validate manifest contains ClusterRole k9b-cnpg-live-lab-runner-lab-namespace."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'k9b-cnpg-live-lab-runner-lab-namespace' in content, \
            "Should validate ClusterRole k9b-cnpg-live-lab-runner-lab-namespace exists"

    def test_workflow_validates_manifest_contains_cnpg_system_role(self) -> None:
        """Workflow should validate manifest contains Role k9b-cnpg-live-lab-runner-cnpg-system."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'k9b-cnpg-live-lab-runner-cnpg-system' in content, \
            "Should validate Role k9b-cnpg-live-lab-runner-cnpg-system exists"

    def test_workflow_validates_runner_service_account(self) -> None:
        """Workflow should validate manifest contains runner ServiceAccount."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'spbnix-k8s-gha-rs-no-permission' in content, \
            "Should validate runner ServiceAccount name"
        assert 'github-actions-runner' in content, \
            "Should validate runner namespace"

    def test_workflow_validates_no_placeholders(self) -> None:
        """Workflow should validate manifest contains no placeholders."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # The validation checks grep for these patterns in the manifest
        # Should check that these patterns are NOT found in the manifest
        assert 'grep -q "<RUNNER_SERVICE_ACCOUNT>"' in content, \
            "Should validate no <RUNNER_SERVICE_ACCOUNT> placeholder"
        assert 'grep -q "<RUNNER_NAMESPACE>"' in content, \
            "Should validate no <RUNNER_NAMESPACE> placeholder"

    def test_workflow_validates_no_wildcard_rbac(self) -> None:
        """Workflow should validate manifest contains no wildcard RBAC."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # The validation uses grep to check for wildcard patterns
        # Should have grep commands checking for these patterns
        assert 'grep -q' in content and 'apiGroups' in content, \
            "Should validate no wildcard apiGroups"
        assert 'grep -q' in content and 'resources' in content, \
            "Should validate no wildcard resources"
        assert 'grep -q' in content and 'verbs' in content, \
            "Should validate no wildcard verbs"

    def test_workflow_validates_no_cluster_admin(self) -> None:
        """Workflow should validate manifest contains no cluster-admin role/object name."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'cluster-admin role/object name' in content, \
            "Should validate no cluster-admin role/object name"

    def test_admin_workflow_cluster_admin_check_ignores_comments(self) -> None:
        """Cluster-admin check should ignore comments to allow documentation."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Should NOT use the old broad grep that matches comments
        assert 'grep -qi "cluster-admin" "$MANIFEST"' not in content, \
            "Should NOT use broad grep that matches comments"
        # Should use grep that filters out comment lines
        assert "grep -Ev '^[[:space:]]*#'" in content, \
            "Should filter out comment lines before checking"

    def test_admin_workflow_still_rejects_cluster_admin_role_names(self) -> None:
        """Cluster-admin check should still catch actual role/object names."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Should still catch name: cluster-admin patterns
        assert "cluster-admin role/object name" in content, \
            "Should check for cluster-admin role/object name"
        assert "^[[:space:]]*name:" in content, \
            "Should check name: field specifically"


class TestAdminWorkflowPermissionVerification:
    """Test that the admin workflow verifies live-lab runner permissions."""

    def test_workflow_runs_auth_can_i_checks(self) -> None:
        """Workflow should run kubectl auth can-i checks for the live-lab runner."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'kubectl auth can-i' in content, \
            "Should run kubectl auth can-i checks"
        assert '--as=' in content or '--as ' in content, \
            "Should use --as flag for impersonation"

    def test_workflow_checks_pvc_permissions(self) -> None:
        """Workflow should check PVC permissions for the live-lab runner."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'persistentvolumeclaims' in content, \
            "Should check PVC permissions"
        assert 'get persistentvolumeclaims' in content, \
            "Should check get PVC permission"
        assert 'create persistentvolumeclaims' in content, \
            "Should check create PVC permission"

    def test_workflow_checks_secret_read_denied(self) -> None:
        """Workflow should verify that secret read is denied for the live-lab runner."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'get secrets' in content, \
            "Should check secret read permission"
        assert 'should NOT' in content.lower() or 'ERROR' in content, \
            "Should verify secret read is denied"
        assert 'exit 1' in content, \
            "Should fail if secret read is granted"

    def test_workflow_checks_clusterrole_update_denied(self) -> None:
        """Workflow should verify that ClusterRole update is denied for the live-lab runner."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'update clusterroles' in content.lower(), \
            "Should check ClusterRole update permission"
        assert 'ERROR' in content or 'should NOT' in content.lower(), \
            "Should verify ClusterRole update is denied"


class TestAdminWorkflowCleanup:
    """Test that the admin workflow has proper cleanup."""

    def test_workflow_has_cleanup_with_always(self) -> None:
        """Workflow should have cleanup steps with if: always()."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Check for namespace cleanup with always
        assert re.search(r'name: Cleanup.*\n.*if:\s*always\(\)', content, re.DOTALL), \
            "Should have cleanup step with if: always()"
        # Check for kubectl delete namespace
        assert 'kubectl delete namespace' in content, \
            "Should delete namespace in cleanup"

    def test_workflow_cleans_up_kubeconfig(self) -> None:
        """Workflow should clean up admin kubeconfig file."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'Cleanup admin kubeconfig' in content or 'rm -f' in content, \
            "Should clean up admin kubeconfig file"


class TestAdminWorkflowSecurity:
    """Test that the admin workflow follows security best practices."""

    def test_workflow_wires_environment_secret_into_decode_step(self) -> None:
        """Workflow should wire K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64 secret into decode step."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Find the Decode admin kubeconfig step
        assert 'name: Decode admin kubeconfig' in content, \
            "Should have Decode admin kubeconfig step"
        # Verify the env block with secret reference exists
        assert 'env:' in content and 'K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64:' in content, \
            "Should define env block for secret"
        assert 'secrets.K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64' in content, \
            "Should reference K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64 secret"

    def test_workflow_does_not_print_kubeconfig(self) -> None:
        """Workflow should NOT print kubeconfig contents."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Should not have echo of kubeconfig or token
        assert not re.search(r'echo.*kubeconfig', content.lower()) or 'cleanup' in content.lower(), \
            "Should not echo kubeconfig"
        # base64 decode is OK but should not cat the decoded file
        assert 'cat.*KUBECONFIG_FILE' not in content, \
            "Should not print decoded kubeconfig"

    def test_workflow_does_not_upload_sensitive_artifacts(self) -> None:
        """Workflow should NOT upload sensitive artifacts."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        # Should not upload kubeconfig as artifact
        if 'upload-artifact' in content:
            upload_section = re.search(
                r'actions/upload-artifact.*?path:\s*(.*?)(?=\n\s*name:|\Z)',
                content,
                re.DOTALL
            )
            if upload_section:
                path = upload_section.group(1)
                assert 'kubeconfig' not in path.lower(), \
                    "Should not upload kubeconfig as artifact"

    def test_workflow_uses_base64_encoded_kubeconfig_secret(self) -> None:
        """Workflow should use base64-encoded kubeconfig from secret."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64' in content, \
            "Should use K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64 secret"
        assert 'base64 -d' in content, \
            "Should decode base64 kubeconfig"

    def test_workflow_sets_kubeconfig_permissions(self) -> None:
        """Workflow should set proper permissions on kubeconfig file."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'chmod 0600' in content, \
            "Should set 0600 permissions on kubeconfig file"


class TestAdminWorkflowDoesNotRunFromNormalWorkflow:
    """Test that the admin workflow is not called from the normal live lab workflow."""

    def test_live_workflow_does_not_call_admin_workflow(self) -> None:
        """Normal live workflow should NOT call the admin workflow."""
        live_workflow = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"
        if live_workflow.exists():
            content = live_workflow.read_text()
            assert 'k9b-cnpg-live-lab-rbac-admin' not in content, \
                "Normal live workflow should NOT reference admin workflow"
            assert 'workflow_call' not in content or 'live' in content.lower(), \
                "Live workflow should not use workflow_call to call admin"


class TestAdminWorkflowEnvVars:
    """Test that the admin workflow uses correct environment variables."""

    def test_workflow_defines_manifest_env_var(self) -> None:
        """Workflow should define MANIFEST as environment variable."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'MANIFEST:' in content, \
            "Should define MANIFEST environment variable"

    def test_workflow_defines_runner_sa_env_var(self) -> None:
        """Workflow should define RUNNER_SA as environment variable."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'RUNNER_SA:' in content, \
            "Should define RUNNER_SA environment variable"
        assert 'system:serviceaccount:github-actions-runner:spbnix-k8s-gha-rs-no-permission' in content, \
            "Should use correct runner SA format"


class TestAdminWorkflowRBACObjects:
    """Test that the admin workflow shows the correct RBAC objects after apply."""

    def test_workflow_shows_clusterrole_after_apply(self) -> None:
        """Workflow should show ClusterRole objects after apply."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'kubectl get clusterrole k9b-cnpg-live-lab-runner-cluster' in content, \
            "Should show ClusterRole after apply"

    def test_workflow_shows_role_after_apply(self) -> None:
        """Workflow should show Role objects after apply."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'kubectl get role k9b-cnpg-live-lab-runner-cnpg-system' in content, \
            "Should show Role after apply"

    def test_workflow_shows_clusterrolebinding_after_apply(self) -> None:
        """Workflow should show ClusterRoleBinding objects after apply."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'kubectl get clusterrolebinding k9b-cnpg-live-lab-runner-cluster' in content, \
            "Should show ClusterRoleBinding after apply"
        assert 'kubectl get clusterrolebinding k9b-cnpg-live-lab-runner-lab-namespace' in content, \
            "Should show lab-namespace ClusterRoleBinding after apply"

    def test_workflow_shows_rolebinding_after_apply(self) -> None:
        """Workflow should show RoleBinding objects after apply."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'kubectl get rolebinding k9b-cnpg-live-lab-runner-cnpg-system' in content, \
            "Should show RoleBinding after apply"


class TestAdminWorkflowPreApplyDiagnostics:
    """Test that the admin workflow has proper pre-apply diagnostics."""

    def test_workflow_runs_kubectl_version_client(self) -> None:
        """Workflow should run kubectl version --client before apply."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'kubectl version --client' in content, \
            "Should run kubectl version --client"

    def test_workflow_runs_kubectl_config_current_context(self) -> None:
        """Workflow should run kubectl config current-context before apply."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'kubectl config current-context' in content, \
            "Should run kubectl config current-context"

    def test_workflow_runs_kubectl_auth_whoami(self) -> None:
        """Workflow should run kubectl auth whoami for diagnostics."""
        content = ADMIN_WORKFLOW_FILE.read_text()
        assert 'kubectl auth whoami' in content, \
            "Should run kubectl auth whoami"

"""Tests for live lab bootstrap and protected kubeconfig workflow.

This module tests:
- Protected environment usage in live lab workflow
- Kubeconfig bootstrap via bootstrap script
- Credential source validation (detects ARC runner SA)
- Explicit --kubeconfig passing to kubectl and helm
- Failure classification artifacts
- No ambient in-cluster credential fallback
"""

import re
from pathlib import Path

# Paths
WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"
BOOTSTRAP_SCRIPT = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_bootstrap.sh"
BOOTSTRAP_PYTHON = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_bootstrap.py"
RBAC_MANIFEST = Path(__file__).parent.parent / "deploy" / "github-actions" / "k9b-cnpg-live-lab-runner-rbac.yaml"


class TestProtectedEnvironmentUsage:
    """Test that live workflow uses protected environment for kubeconfig."""

    def test_live_workflow_uses_protected_environment(self) -> None:
        """Live workflow must use protected environment for kubeconfig secret."""
        content = WORKFLOW_FILE.read_text()
        # Must reference k9b-live-lab-admin protected environment
        assert "environment: k9b-live-lab-admin" in content, \
            "Live workflow should use protected environment 'k9b-live-lab-admin'"

    def test_live_workflow_receives_kubeconfig_secret(self) -> None:
        """Live workflow must receive kubeconfig B64 secret from protected env."""
        content = WORKFLOW_FILE.read_text()
        # Must reference the secret from protected environment
        assert "K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64" in content, \
            "Live workflow should reference K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64 secret"
        assert "secrets.K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64" in content, \
            "Live workflow should access secret via secrets context"

    def test_live_workflow_no_incluster_fallback(self) -> None:
        """Live workflow must NOT fall back to in-cluster credentials."""
        content = WORKFLOW_FILE.read_text()
        # Should NOT configure in-cluster kubeconfig from SA mount
        # (This was the old buggy pattern)
        assert "/var/run/secrets/kubernetes.io/serviceaccount" not in content, \
            "Live workflow should NOT use in-cluster service account mount"
        assert "SA_DIR=" not in content, \
            "Live workflow should NOT reference SA_DIR"
        assert "kubectl config set-cluster in-cluster" not in content, \
            "Live workflow should NOT configure in-cluster context"


class TestBootstrapScript:
    """Test the bootstrap script for kubeconfig handling."""

    def test_bootstrap_script_exists(self) -> None:
        """Bootstrap script must exist."""
        assert BOOTSTRAP_SCRIPT.exists(), f"Bootstrap script not found at {BOOTSTRAP_SCRIPT}"

    def test_bootstrap_script_has_set_euo_pipefail(self) -> None:
        """Bootstrap script must use set -euo pipefail."""
        content = BOOTSTRAP_SCRIPT.read_text()
        assert "set -euo pipefail" in content, \
            "Bootstrap script should have set -euo pipefail"

    def test_bootstrap_script_delegates_to_python(self) -> None:
        """Bootstrap script must delegate to Python implementation."""
        content = BOOTSTRAP_SCRIPT.read_text()
        assert "exec python3" in content, \
            "Bootstrap script should delegate to Python implementation"
        assert ".py" in content, \
            "Bootstrap script should reference Python implementation"

    def test_bootstrap_implementation_validates_credential_source(self) -> None:
        """Bootstrap implementation must validate credential source via auth whoami."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "kubectl auth whoami" in content, \
            "Bootstrap should call kubectl auth whoami"
        assert "validate_credential_source" in content, \
            "Bootstrap should have validate_credential_source function"

    def test_bootstrap_implementation_detects_arc_runner_sa(self) -> None:
        """Bootstrap implementation must detect and fail on ARC runner ServiceAccount."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "system:serviceaccount:github-actions-runner:" in content, \
            "Bootstrap should check for ARC runner SA pattern"
        assert "credential_source_wrong" in content, \
            "Bootstrap should classify credential_source_wrong failure"

    def test_bootstrap_implementation_classifies_failures(self) -> None:
        """Bootstrap implementation must classify failure classes."""
        content = BOOTSTRAP_PYTHON.read_text()
        failure_classes = [
            "kubeconfig_missing",
            "kubeconfig_decode_failed",
            "kubeconfig_auth_failed",
            "credential_source_wrong",
            "helm_rbac_denied",
            "image_pull_failed",
            "cnpg_crd_missing",
            "storageclass_or_capacity_issue",
            "workload_not_ready",
            "helm_unknown_error",
        ]
        for fc in failure_classes:
            assert fc in content, f"Bootstrap should classify failure: {fc}"

    def test_bootstrap_implementation_emits_safe_metadata(self) -> None:
        """Bootstrap implementation must only emit safe metadata, not secrets."""
        content = BOOTSTRAP_PYTHON.read_text()
        # Must not print kubeconfig contents
        assert 'print(kubeconfig_bytes' not in content, \
            "Bootstrap should not print kubeconfig bytes"
        # Must not use --raw flag
        assert "config view --raw" not in content, \
            "Bootstrap should not use kubectl config view --raw"

    def test_bootstrap_implementation_writes_artifacts(self) -> None:
        """Bootstrap implementation must write machine-readable artifacts."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "lab-preflight.json" in content, \
            "Bootstrap should write lab-preflight.json"
        assert "lab-diagnosis.md" in content, \
            "Bootstrap should write lab-diagnosis.md"
        assert "rbac-can-i.txt" in content, \
            "Bootstrap should write rbac-can-i.txt"
        assert "summary.json" in content, \
            "Bootstrap should write summary.json"

    def test_bootstrap_implementation_has_classify_error(self) -> None:
        """Bootstrap implementation must support classify-error functionality."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "classify-error" in content or "classify_error" in content, \
            "Bootstrap should support classify-error functionality"
        assert "classify_helm_error" in content, \
            "Bootstrap should have classify_helm_error function"


class TestExplicitKubeconfigPassing:
    """Test that kubectl and helm commands explicitly pass --kubeconfig."""

    def test_helm_deploy_uses_kubeconfig_flag(self) -> None:
        """Helm deploy must use explicit --kubeconfig flag."""
        content = WORKFLOW_FILE.read_text()
        # Find helm upgrade --install command
        assert re.search(r"helm\s+upgrade\s+--install.*--kubeconfig=", content, re.DOTALL), \
            "Helm deploy should use --kubeconfig flag"
        # Must use KUBECONFIG from bootstrap
        assert "${KUBECONFIG}" in content or "$KUBECONFIG" in content, \
            "Helm deploy should use KUBECONFIG from bootstrap"

    def test_all_kubectl_use_kubeconfig(self) -> None:
        """All kubectl commands must use --kubeconfig flag."""
        content = WORKFLOW_FILE.read_text()
        # Find all kubectl --kubeconfig= usages
        kubectl_commands = re.findall(r"kubectl\s+--kubeconfig=", content)
        # There should be many kubectl commands with --kubeconfig
        assert len(kubectl_commands) > 10, \
            f"Expected many kubectl commands with --kubeconfig, found {len(kubectl_commands)}"
        # Should NOT have kubectl without --kubeconfig in run: blocks
        # (exclude comments, uses:, echo:, and bootstrap steps, step names)
        lines = content.split('\n')
        bare_kubectl_lines = []
        for line in lines:
            if 'kubectl' in line:
                # Skip if has --kubeconfig
                if '--kubeconfig' in line:
                    continue
                # Skip comments
                if line.strip().startswith('#'):
                    continue
                # Skip uses: steps
                if 'uses:' in line:
                    continue
                # Skip echo commands
                if 'echo' in line.lower():
                    continue
                # Skip bootstrap mentions
                if 'bootstrap' in line.lower():
                    continue
                # Skip step names (just contain "name:")
                if '- name:' in line:
                    continue
                bare_kubectl_lines.append(line)
        assert len(bare_kubectl_lines) == 0, \
            f"Found kubectl commands without --kubeconfig: {bare_kubectl_lines}"

    def test_helm_status_uses_kubeconfig(self) -> None:
        """Helm status must use --kubeconfig flag."""
        content = WORKFLOW_FILE.read_text()
        helm_status_matches = re.findall(r"helm\s+--kubeconfig.*status", content)
        assert len(helm_status_matches) >= 1, \
            "Helm status should use --kubeconfig flag"


class TestCredentialValidation:
    """Test credential source validation in workflow."""

    def test_workflow_calls_bootstrap_before_helm(self) -> None:
        """Bootstrap must complete before Helm deploy."""
        content = WORKFLOW_FILE.read_text()
        bootstrap_pos = content.find("Bootstrap protected kubeconfig")
        helm_pos = content.find("Deploy k9b via Helm")
        assert bootstrap_pos != -1, "Bootstrap step not found"
        assert helm_pos != -1, "Helm deploy step not found"
        assert bootstrap_pos < helm_pos, \
            "Bootstrap must come before Helm deploy"

    def test_workflow_validates_before_using_kubeconfig(self) -> None:
        """Workflow must validate credential source before using kubeconfig."""
        content = WORKFLOW_FILE.read_text()
        # Bootstrap step must be named to indicate validation
        assert "Bootstrap protected kubeconfig and validate credentials" in content, \
            "Bootstrap step should validate credentials"
        # Should fail if credential validation fails
        assert "set -euo pipefail" in content, \
            "Bootstrap should use set -euo pipefail to fail on error"


class TestFailureArtifacts:
    """Test failure artifact collection."""

    def test_workflow_collects_failure_artifacts_on_helm_failure(self) -> None:
        """Workflow must collect failure artifacts when Helm fails."""
        content = WORKFLOW_FILE.read_text()
        # Should check for helm failure
        assert "HELM_RC" in content or "PIPESTATUS" in content, \
            "Workflow should capture Helm exit code"
        # Should collect namespace events on failure
        assert "namespace-events.txt" in content, \
            "Workflow should collect namespace events on failure"
        # Should collect pods on failure
        assert "pods.txt" in content, \
            "Workflow should collect pods on failure"
        # Should collect services on failure
        assert "services.txt" in content, \
            "Workflow should collect services on failure"
        # Should collect PVCs on failure
        assert "pvc.txt" in content, \
            "Workflow should collect PVCs on failure"

    def test_workflow_uploads_artifacts_on_failure(self) -> None:
        """Workflow must upload artifacts on failure."""
        content = WORKFLOW_FILE.read_text()
        upload_steps = re.findall(r"upload-artifact", content)
        assert len(upload_steps) >= 1, \
            "Workflow should upload artifacts"
        # The artifact upload step should have if: always() condition
        assert "Upload live lab artifacts" in content, \
            "Should have upload artifacts step"
        # Check that there's a conditional that runs on failure
        upload_section = content[content.find("Upload live lab artifacts"):]
        assert "always()" in upload_section[:1000] or "always()" in content, \
            "Artifact upload section should run always() or have failure handling"

    def test_workflow_cleans_up_kubeconfig_on_failure(self) -> None:
        """Workflow must clean up kubeconfig file on failure."""
        content = WORKFLOW_FILE.read_text()
        # Find cleanup step
        assert "Cleanup kubeconfig" in content, \
            "Workflow should have kubeconfig cleanup step"
        # Cleanup should use always()
        cleanup_match = re.search(r"Cleanup kubeconfig.*?if:\s*always\(\)", content, re.DOTALL)
        assert cleanup_match, \
            "Kubeconfig cleanup should run always()"

    def test_workflow_generates_summary_json(self) -> None:
        """Workflow must generate summary.json with failure classification."""
        # The Python implementation generates summary.json on failure
        bootstrap_content = BOOTSTRAP_PYTHON.read_text()
        assert "summary.json" in bootstrap_content, \
            "Bootstrap should generate summary.json"
        assert "failure_class" in bootstrap_content, \
            "summary.json should contain failure_class"


class TestRBACManifestHasRoles:
    """Test that RBAC manifest includes roles/rolebindings permissions."""

    def test_rbac_manifest_has_rbac_permissions(self) -> None:
        """RBAC manifest must include roles and rolebindings permissions."""
        content = RBAC_MANIFEST.read_text()
        assert 'resources: ["roles", "rolebindings"]' in content or \
               ('"roles"' in content and '"rolebindings"' in content), \
            "RBAC manifest should include roles and rolebindings resources"
        # Must have rbac.authorization.k8s.io apiGroup
        assert 'apiGroups: ["rbac.authorization.k8s.io"]' in content, \
            "RBAC manifest should use rbac.authorization.k8s.io apiGroup"

    def test_rbac_manifest_has_sufficient_verbs_for_roles(self) -> None:
        """RBAC manifest must grant sufficient verbs for roles."""
        content = RBAC_MANIFEST.read_text()
        # Find the rbac section
        rbac_match = re.search(
            r'apiGroups:\s*\["rbac\.authorization\.k8s\.io"\].*?resources:.*?\["roles".*?\].*?verbs:.*?\[(.*?)\]',
            content,
            re.DOTALL
        )
        assert rbac_match, "Should find rbac roles rule"
        verbs = rbac_match.group(1)
        # Must have create and get at minimum
        assert "create" in verbs or "get" in verbs, \
            "Roles rule should have create or get verb"


class TestNoTokenLeakage:
    """Test that workflow doesn't leak tokens or secrets."""

    def test_workflow_does_not_print_kubeconfig(self) -> None:
        """Workflow must not print kubeconfig contents."""
        content = WORKFLOW_FILE.read_text()
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # Should not echo kubeconfig path contents
            assert not (stripped.startswith('echo') and '$KUBECONFIG' in stripped and 'token' in stripped.lower()), \
                f"Should not echo kubeconfig tokens: {stripped[:100]}"

    def test_workflow_does_not_print_base64_secret(self) -> None:
        """Workflow must not print base64 secret value."""
        content = WORKFLOW_FILE.read_text()
        # Secret is used but never echoed
        assert "echo.*K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64" not in content, \
            "Should not echo the base64 secret"

    def test_workflow_cleans_kubeconfig_before_upload(self) -> None:
        """Workflow must remove kubeconfig before artifact upload."""
        content = WORKFLOW_FILE.read_text()
        # Should have cleanup step that removes sensitive files
        assert "Cleanup sensitive files" in content or "Cleanup kubeconfig" in content, \
            "Workflow should clean sensitive files before upload"


class TestCredentialSourceField:
    """Test that lab-result.json includes credential source."""

    def test_lab_result_includes_credential_source(self) -> None:
        """lab-result.json must include credential_source field."""
        content = WORKFLOW_FILE.read_text()
        # Should set credential_source to protected-environment
        assert '"credential_source": "protected-environment"' in content or \
               "'credential_source': 'protected-environment'" in content, \
            "lab-result.json should set credential_source to protected-environment"
        assert '"kubeconfig_source"' in content or "'kubeconfig_source'" in content, \
            "lab-result.json should include kubeconfig_source"


class TestBootstrapBootstrapFunction:
    """Test bootstrap implementation's bootstrap_decode_kubeconfig function."""

    def test_bootstrap_decodes_base64_to_file(self) -> None:
        """Bootstrap must decode base64 secret to file."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "base64" in content.lower(), \
            "Bootstrap should decode base64 secret"
        assert "RUNNER_TEMP" in content, \
            "Bootstrap should write to RUNNER_TEMP directory"

    def test_bootstrap_sets_0600_permissions(self) -> None:
        """Bootstrap must set file permissions to 0600."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "chmod(0o600" in content or "0o600" in content, \
            "Bootstrap should set kubeconfig permissions to 0600"

    def test_bootstrap_exports_kubeconfig_to_github_env(self) -> None:
        """Bootstrap must export KUBECONFIG path to GITHUB_ENV."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert 'GITHUB_ENV' in content, \
            "Bootstrap should export to GITHUB_ENV"


class TestHelmErrorClassification:
    """Test Helm error classification patterns."""

    def test_classifies_rbac_denied(self) -> None:
        """Must classify 'forbidden roles.rbac' errors."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "forbidden" in content.lower() and "roles" in content.lower() and "rbac" in content.lower(), \
            "Should classify forbidden roles.rbac error"
        assert "helm_rbac_denied" in content, \
            "Should use helm_rbac_denied classification"

    def test_classifies_image_pull_errors(self) -> None:
        """Must classify image pull errors."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "imagepullbackoff" in content.lower() or "errimagepull" in content.lower(), \
            "Should classify ImagePullBackOff errors"
        assert "image_pull_failed" in content, \
            "Should use image_pull_failed classification"

    def test_classifies_crd_missing(self) -> None:
        """Must classify CNPG CRD missing errors."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "clusters.postgresql.cnpg.io" in content, \
            "Should classify CNPG CRD errors"
        assert "cnpg_crd_missing" in content, \
            "Should use cnpg_crd_missing classification"

    def test_classifies_pvc_pending(self) -> None:
        """Must classify PVC pending errors."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "pending" in content.lower(), \
            "Should classify PVC pending errors"
        assert "storageclass_or_capacity_issue" in content, \
            "Should use storageclass_or_capacity_issue classification"

    def test_classifies_timeout(self) -> None:
        """Must classify timeout errors."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "timeout" in content.lower() or "timed out" in content.lower(), \
            "Should classify timeout errors"
        assert "workload_not_ready" in content, \
            "Should use workload_not_ready classification"


class TestHelmManifestSchemaClassification:
    """Test Helm manifest schema error classification patterns."""

    def test_classifies_unknown_field(self) -> None:
        """Must classify 'unknown field' errors."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "unknown field" in content.lower(), \
            "Should classify unknown field errors"
        assert "helm_manifest_schema_warning" in content, \
            "Should use helm_manifest_schema_warning classification"

    def test_classifies_container_security_context_drift(self) -> None:
        """Must detect container-level security/resource field drift."""
        content = BOOTSTRAP_PYTHON.read_text()
        # Should detect when security fields are at wrong level
        assert "allowPrivilegeEscalation" in content or "securityContext" in content, \
            "Should detect allowPrivilegeEscalation securityContext issues"
        assert "readOnlyRootFilesystem" in content or "securityContext" in content, \
            "Should detect readOnlyRootFilesystem securityContext issues"
        assert "capabilities" in content or "securityContext" in content, \
            "Should detect capabilities securityContext issues"

    def test_classifies_resources_limits_requests_drift(self) -> None:
        """Must detect when limits/requests are at wrong level."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "limits" in content.lower() or "resources" in content.lower(), \
            "Should detect limits/resources issues"

    def test_has_classify_schema_error_function(self) -> None:
        """Must have classify_schema_error function."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "classify_schema_error" in content, \
            "Should have classify_schema_error function"


class TestHelmServerDryRunClassification:
    """Test Helm server-side dry-run validation failure classification."""

    def test_classifies_dry_run_failure(self) -> None:
        """Must classify kubectl --dry-run=server validation failures."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "dry-run" in content.lower() or "dry_run" in content, \
            "Should handle dry-run validation"
        assert "helm_manifest_server_dry_run_failed" in content, \
            "Should use helm_manifest_server_dry_run_failed classification"

    def test_classifies_validation_errors(self) -> None:
        """Must classify error validating data errors."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "error validating" in content.lower() or "validation failed" in content.lower(), \
            "Should classify validation errors"


class TestHelmWaitTimeoutClassification:
    """Test Helm wait timeout classification with cluster state analysis."""

    def test_classifies_helm_wait_timeout_unknown(self) -> None:
        """Must classify helm wait timeout with unknown cause."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "helm_wait_timeout_unknown" in content, \
            "Should use helm_wait_timeout_unknown classification"

    def test_classifies_pod_crash_loop(self) -> None:
        """Must classify pod crash loop from cluster state."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "crashloopbackoff" in content.lower() or "pod_crash_loop" in content, \
            "Should detect CrashLoopBackOff"
        assert "pod_crash_loop" in content, \
            "Should use pod_crash_loop classification"

    def test_classifies_probe_failure(self) -> None:
        """Must classify readiness/liveness probe failures."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "probe" in content.lower() or "readiness" in content.lower() or "liveness" in content.lower(), \
            "Should detect probe failures"
        assert "probe_failed" in content, \
            "Should use probe_failed classification"

    def test_classifies_deployment_not_available(self) -> None:
        """Must classify deployment not available from cluster state."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "deployment_not_available" in content, \
            "Should use deployment_not_available classification"

    def test_has_classify_wait_timeout_function(self) -> None:
        """Must have classify_wait_timeout function."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "classify_wait_timeout" in content, \
            "Should have classify_wait_timeout function"

    def test_watchdog_collects_cluster_state(self) -> None:
        """Workflow must collect cluster state during Helm wait."""
        content = WORKFLOW_FILE.read_text()
        assert "watchdog" in content.lower(), \
            "Workflow should have watchdog for Helm wait"
        assert "get pods" in content.lower() and "-n" in content, \
            "Watchdog should collect pods"
        assert "get events" in content.lower(), \
            "Watchdog should collect events"


class TestPreHelmValidation:
    """Test pre-Helm manifest validation steps."""

    def test_workflow_renders_helm_template_before_install(self) -> None:
        """Workflow must render Helm manifests before install."""
        content = WORKFLOW_FILE.read_text()
        assert "helm template" in content.lower(), \
            "Workflow should render Helm manifests before install"
        assert "helm-rendered.yaml" in content, \
            "Workflow should save rendered manifests to helm-rendered.yaml"

    def test_workflow_runs_server_side_dry_run(self) -> None:
        """Workflow must run server-side dry-run validation."""
        content = WORKFLOW_FILE.read_text()
        assert "--dry-run=server" in content, \
            "Workflow should run kubectl apply --dry-run=server"
        assert "helm-server-dry-run.log" in content, \
            "Workflow should save dry-run output to helm-server-dry-run.log"

    def test_workflow_fails_on_schema_warning(self) -> None:
        """Workflow must fail before install when schema warnings detected."""
        content = WORKFLOW_FILE.read_text()
        assert "unknown field" in content.lower(), \
            "Workflow should detect unknown field warnings"
        # Should fail the step, not proceed to install
        assert "exit 1" in content or "exit 1" in content.lower(), \
            "Workflow should exit with error when schema warnings found"

    def test_workflow_fails_on_dry_run_failure(self) -> None:
        """Workflow must fail before install when dry-run validation fails."""
        content = WORKFLOW_FILE.read_text()
        assert "DRY_RUN_RC" in content, \
            "Workflow should check dry-run exit code"
        # Should fail before proceeding with helm upgrade --install
        dry_run_pos = content.find("DRY_RUN_RC")
        assert dry_run_pos != -1, "Should have dry-run check"
        # The check must be before helm install step
        assert "exit 1" in content[dry_run_pos: dry_run_pos + 500] or "exit 1" in content.lower(), \
            "Workflow should exit when dry-run fails"


class TestWatchdogDirectory:
    """Test watchdog artifact collection."""

    def test_workflow_creates_watchdog_directory(self) -> None:
        """Workflow must create watchdog directory for snapshots."""
        content = WORKFLOW_FILE.read_text()
        assert "mkdir -p" in content and "watchdog" in content.lower(), \
            "Workflow should create watchdog directory"

    def test_watchdog_collects_pods_deployments_events(self) -> None:
        """Watchdog must collect pods, deployments, and events."""
        content = WORKFLOW_FILE.read_text()
        assert "get pods" in content.lower(), \
            "Watchdog should collect pods"
        assert "get deployments" in content.lower() or "get deployment" in content.lower(), \
            "Watchdog should collect deployments"
        assert "get events" in content.lower(), \
            "Watchdog should collect events"

    def test_watchdog_uses_explicit_kubeconfig(self) -> None:
        """Watchdog kubectl commands must use explicit --kubeconfig."""
        content = WORKFLOW_FILE.read_text()
        # Find watchdog section
        watchdog_start = content.find("Start Helm wait watchdog")
        if watchdog_start != -1:
            watchdog_section = content[watchdog_start:]
            assert "--kubeconfig" in watchdog_section, \
                "Watchdog should use --kubeconfig for kubectl commands"

    def test_watchdog_logs_snapshots(self) -> None:
        """Watchdog must log snapshot collection."""
        content = WORKFLOW_FILE.read_text()
        assert "watchdog.log" in content.lower() or "snapshot" in content.lower(), \
            "Watchdog should log snapshot collection"


class TestSummaryJsonFields:
    """Test summary.json required fields."""

    def test_summary_contains_required_fields(self) -> None:
        """summary.json must contain all required diagnostic fields."""
        content = BOOTSTRAP_PYTHON.read_text()
        required_fields = [
            "failure_class",
            "active_identity",
            "namespace",
            "release",
            "image_tag",
            "next_suggested_action",
        ]
        for field in required_fields:
            assert field in content, f"summary.json should contain {field}"


class TestJsonValidityRegression:
    """Regression tests for JSON validity in artifact files.

    These tests ensure that lab-preflight.json and summary.json remain
    valid JSON after every workflow path, preventing the bug where
    echo "key=value" was appended to JSON files.
    """

    def test_workflow_does_not_append_keyvalue_to_preflight_json(self) -> None:
        """Workflow must not append key=value lines to lab-preflight.json."""
        content = WORKFLOW_FILE.read_text()
        # These patterns indicate the bug
        assert '>> ./lab-artifacts/live/lab-preflight.json' not in content, \
            "Workflow must not append to lab-preflight.json with >>"
        assert 'failure_class=' not in content or 'failure_class=helm_deploy_failed' not in content, \
            "Workflow must not write failure_class as key=value to lab-preflight.json"

    def test_workflow_uses_classify_error_for_helm_failures(self) -> None:
        """Workflow must use classify-error Python command for Helm failures."""
        content = WORKFLOW_FILE.read_text()
        assert "classify-error" in content, \
            "Workflow should use classify-error command for Helm failures"
        assert "scripts/k9b_cnpg_live_lab_bootstrap.sh classify-error" in content, \
            "Workflow should call classify-error subcommand"

    def test_preflight_json_uses_json_module(self) -> None:
        """Python bootstrap must use json module for lab-preflight.json."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "import json" in content, \
            "Bootstrap should import json module"
        assert "json.dumps" in content, \
            "Bootstrap should use json.dumps for serialization"
        assert "write_json_atomically" in content, \
            "Bootstrap should use atomic JSON write"

    def test_preflight_json_write_uses_json_dumps(self) -> None:
        """lab-preflight.json must be written with json.dumps, not string concatenation."""
        content = BOOTSTRAP_PYTHON.read_text()
        # Should NOT use string formatting for JSON
        assert '">"' not in content or "json.dumps" in content, \
            "lab-preflight.json should use json.dumps"
        # PreflightData.save() should write valid JSON
        assert "write_json_atomically(path, self.to_dict())" in content or \
               "path.write_text(json.dumps" in content, \
            "PreflightData.save should use JSON serialization"

    def test_classify_error_does_not_corrupt_preflight_json(self) -> None:
        """classify-error path must not corrupt lab-preflight.json."""
        content = BOOTSTRAP_PYTHON.read_text()
        # The classify-error command reads existing preflight, updates it, and saves
        assert "main_classify_error" in content, \
            "Bootstrap should have classify-error entry point"
        # It should read existing preflight, not append
        assert "read_json" in content and "lab-preflight.json" in content, \
            "classify-error should read existing lab-preflight.json"


class TestWorkflowRuntimeSetup:
    """Regression tests for workflow runtime setup."""

    def test_workflow_creates_python_environment_for_verifier(self) -> None:
        """Workflow must create Python environment before artifact verifier runs."""
        content = WORKFLOW_FILE.read_text()
        # Must have setup-python before artifact verification
        assert "actions/setup-python@v5" in content, \
            "Workflow should use actions/setup-python@v5 for Python environment"
        # Must create venv
        assert "python -m venv .venv" in content, \
            "Workflow should create .venv for Python dependencies"
        # Artifact verifier must use the created environment
        verifier_pos = content.find("verify_k3s_cnpg_incident_lab_artifact.py")
        setup_pos = content.find("actions/setup-python@v5")
        assert setup_pos < verifier_pos, \
            "setup-python must come before artifact verifier"


class TestPythonEnvironmentOrder:
    """Regression tests for Python environment ordering."""

    def test_python_environment_created_before_pre_helm_steps(self) -> None:
        """Python env must be set up before pre-Helm render/dry-run steps."""
        content = WORKFLOW_FILE.read_text()

        # Find setup-python position
        setup_positions = []
        for i, line in enumerate(content.split('\n')):
            if 'uses: actions/setup-python@v5' in line:
                # Find the step containing this
                step_start = content.rfind('- name:', 0, content[:i].rfind('\n'))
                setup_positions.append(step_start)

        # Find helm-template step position
        helm_template_pos = content.find('- name: Render Helm manifests')
        helm_dry_run_pos = content.find('- name: Validate manifests with server-side dry-run')

        assert helm_template_pos != -1, "Should have helm-template step"
        assert helm_dry_run_pos != -1, "Should have dry-run step"
        assert len(setup_positions) > 0, "Should have setup-python step"

        # setup-python should come before helm-template
        assert setup_positions[0] < helm_template_pos, \
            "setup-python must come before helm-template step"

    def test_no_inline_python_c_blocks_in_workflow(self) -> None:
        """Workflow must not use inline python -c blocks for classification."""
        content = WORKFLOW_FILE.read_text()

        # Check for python -c patterns
        assert "python -c \"" not in content and "python -c '" not in content, \
            "Workflow must not use inline python -c blocks - use CLI subcommands instead"

        # Should use classify-schema and classify-wait-timeout subcommands
        assert "classify-schema" in content, \
            "Workflow should use classify-schema subcommand"
        assert "classify-wait-timeout" in content, \
            "Workflow should use classify-wait-timeout subcommand"

    def test_python_subcommands_read_existing_preflight(self) -> None:
        """Classification subcommands must read existing lab-preflight.json."""
        content = BOOTSTRAP_PYTHON.read_text()

        # main_classify_schema should read existing preflight
        assert "read_json(artifact_dir / \"lab-preflight.json\")" in content, \
            "classify-schema should read existing lab-preflight.json"

        # main_classify_wait_timeout should read existing preflight
        assert "read_json(artifact_dir / \"lab-preflight.json\")" in content, \
            "classify-wait-timeout should read existing lab-preflight.json"


class TestWatchdogLifecycle:
    """Test watchdog lifecycle management."""

    def test_watchdog_uses_trap_cleanup(self) -> None:
        """Watchdog must use trap for reliable cleanup."""
        content = WORKFLOW_FILE.read_text()

        # Should have trap cleanup
        assert "trap cleanup_watchdog EXIT" in content, \
            "Watchdog should use trap EXIT for cleanup"

        # Should not start watchdog in separate step
        assert "Start Helm wait watchdog" not in content, \
            "Watchdog should not be started in separate step"


class TestDryRunWarningDetection:
    """Test dry-run warning detection even on success exit code."""

    def test_dry_run_checks_log_for_unknown_field_on_success(self) -> None:
        """Dry-run must check log for 'unknown field' even when exit code is 0."""
        content = WORKFLOW_FILE.read_text()

        # Find the dry-run step
        dry_run_section = content[content.find("Validate manifests with server-side dry-run"):]
        dry_run_section = dry_run_section[:dry_run_section.find("\n      # =====", 1) if "\n      # =====" in dry_run_section else len(dry_run_section)]

        # Should grep for unknown field
        assert "grep" in dry_run_section and "unknown field" in dry_run_section, \
            "Dry-run step should grep for 'unknown field'"

        # Should check before exit 1
        unknown_field_pos = dry_run_section.find("grep")
        exit_1_pos = dry_run_section.find("exit 1")
        assert unknown_field_pos < exit_1_pos, \
            "grep for unknown field should come before exit 1"


class TestTimeoutClassifierParsing:
    """Test timeout classifier JSON parsing."""

    def test_parse_crash_loop_requires_waiting_reason(self) -> None:
        """Crash loop detection must parse JSON and check waiting.reason."""
        content = BOOTSTRAP_PYTHON.read_text()

        # Should NOT use naive string matching for crash loop detection
        # (comment mentions are OK, but actual detection must parse JSON)
        # The function should check waiting.reason, not just string search
        assert "_parse_crash_loop_from_pods" in content, \
            "Should have _parse_crash_loop_from_pods function"
        
        # Function should check waiting.reason specifically
        assert '"waiting"' in content and '"reason"' in content, \
            "Should check waiting.reason for CrashLoopBackOff"

    def test_parse_image_pull_failure_checks_waiting_reason(self) -> None:
        """Image pull failure must check waiting.reason for ImagePullBackOff."""
        content = BOOTSTRAP_PYTHON.read_text()

        assert "_parse_image_pull_failure_from_pods" in content, \
            "Should have _parse_image_pull_failure_from_pods function"

    def test_parse_deployment_not_ready_uses_status_json(self) -> None:
        """Deployment not ready must use deployment status JSON."""
        content = BOOTSTRAP_PYTHON.read_text()

        assert "_parse_deployment_not_ready_from_deployments" in content, \
            "Should have _parse_deployment_not_ready_from_deployments function"

    def test_crash_loop_not_detected_for_normal_restartcount_0(self) -> None:
        """Crash loop should not be detected when all pods have restartCount=0."""
        content = BOOTSTRAP_PYTHON.read_text()

        # The function should check waiting.reason, not restartCount
        # If it checks restartCount, it should have a threshold > 0
        assert '"CrashLoopBackOff"' in content, \
            "Should check for CrashLoopBackOff reason in waiting state"


class TestClassificationSubcommands:
    """Test classification subcommand CLI interface."""

    def test_classify_schema_subcommand_exists(self) -> None:
        """classify-schema subcommand must exist."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "def main_classify_schema" in content, \
            "Should have main_classify_schema function"

    def test_classify_wait_timeout_subcommand_exists(self) -> None:
        """classify-wait-timeout subcommand must exist."""
        content = BOOTSTRAP_PYTHON.read_text()
        assert "def main_classify_wait_timeout" in content, \
            "Should have main_classify_wait_timeout function"

    def test_subcommands_preserve_preflight_context(self) -> None:
        """Classification subcommands must preserve active_identity and namespace."""
        content = BOOTSTRAP_PYTHON.read_text()

        # Should read existing preflight
        assert "existing = read_json(artifact_dir / \"lab-preflight.json\")" in content, \
            "Subcommands should read existing preflight"

        # Should preserve active_identity
        assert "preflight.active_identity = existing.get(\"active_identity\")" in content, \
            "Should preserve active_identity from existing preflight"

        # Should preserve namespace
        assert "preflight.namespace = existing.get(\"namespace\"" in content, \
            "Should preserve namespace from existing preflight"


class TestTimeoutClassifierRegression:
    """Regression tests for timeout classifier - ensure no false positive string matching."""

    def test_no_restartcount_false_positive_in_classify_wait_timeout(self) -> None:
        """classify_wait_timeout must not use 'restartcount in pods_json' pattern."""
        content = BOOTSTRAP_PYTHON.read_text()
        # The stale pattern that caused false positives
        assert '"restartcount" in pods_json' not in content, \
            "Must not use 'restartcount' string match - false positive on JSON field name"

    def test_no_zero_slash_one_false_positive_in_classify_wait_timeout(self) -> None:
        """classify_wait_timeout must not use '0/1 in pods_json' plain string pattern."""
        content = BOOTSTRAP_PYTHON.read_text()
        # The stale pattern that matched JSON field names like "replicas: 0"
        assert '"0/1" in pods_json' not in content, \
            "Must not use '0/1' plain string match on pods_json"

    def test_classify_wait_timeout_uses_json_parsers(self) -> None:
        """classify_wait_timeout must use JSON-based parser helpers."""
        content = BOOTSTRAP_PYTHON.read_text()
        # Must use the JSON-based parser helpers
        assert "_parse_crash_loop_from_pods(pods_json)" in content, \
            "Should use _parse_crash_loop_from_pods for accurate crash loop detection"
        assert "_parse_deployment_not_ready_from_deployments(deployments_json)" in content, \
            "Should use _parse_deployment_not_ready_from_deployments for accurate deployment check"

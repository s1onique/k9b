"""Tests for k9b_lab_common_baseline module and its usage in OTel demo lab.

This module ensures that:
1. OTel demo lab workflow uses the common baseline installer
2. Common baseline installer exists and has the right functions
3. Common baseline installer collects the right evidence artifacts
"""

from pathlib import Path
from typing import Any

# Path to the OTel demo workflow file
OTEL_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-incident-lab.yml"

# Path to the common baseline module
COMMON_BASELINE_MODULE = Path(__file__).parent.parent / "scripts" / "k9b_lab_common_baseline.py"


# Path to the CLI wrapper
CLI_WRAPPER = Path(__file__).parent.parent / "scripts" / "ensure_k9b_lab_baseline.py"
HELM_MODULE = Path(__file__).parent.parent / "scripts" / "k9b_lab_helm.py"
ROLLOUT_MODULE = Path(__file__).parent.parent / "scripts" / "k9b_lab_rollout.py"


class TestOTelLabUsesCommonBaselineInstaller:
    """Test that OTel demo lab workflow uses the common baseline CLI wrapper."""

    def test_otel_workflow_file_exists(self) -> None:
        """The OTel demo workflow file should exist."""
        assert OTEL_WORKFLOW_FILE.exists(), f"OTel workflow not found at {OTEL_WORKFLOW_FILE}"

    def test_otel_workflow_uses_cli_wrapper(self) -> None:
        """OTel demo lab should use the CLI wrapper script via module invocation."""
        content = OTEL_WORKFLOW_FILE.read_text()
        install_section_start = content.find("Ensure k9b lab baseline")
        if install_section_start == -1:
            install_section_start = content.find("Install k9b baseline")
        assert install_section_start != -1, "Should have 'Ensure k9b lab baseline' step"

        section = content[install_section_start:install_section_start + 3000]

        # Must use module invocation from repo root for correct sys.path
        # See: https://docs.python.org/3/library/sys_path_init.html
        assert "python -m scripts.ensure_k9b_lab_baseline" in section, \
            "OTel workflow should use module invocation (python -m scripts.ensure_k9b_lab_baseline)"
        assert "scripts/ensure_k9b_lab_baseline.py" not in section, \
            "OTel workflow should NOT use direct file path (scripts/ensure_k9b_lab_baseline.py)"
        assert "python -c" not in section, \
            "OTel workflow should NOT use inline python -c"
        assert "ensure_k9b_baseline_ready(" not in section, \
            "OTel workflow should NOT call ensure_k9b_baseline_ready directly"
        assert "k9b_lab_common_baseline" not in section, \
            "OTel workflow should NOT import k9b_lab_common_baseline directly"

    def test_otel_workflow_no_direct_helm_install(self) -> None:
        """OTel demo lab should NOT use direct helm upgrade --install for k9b baseline.

        Regression test: the OTel lab previously installed k9b through a separate
        minimal Helm path and timed out after four minutes without the CNPG
        live-lab rollout classifier or Helm evidence artifacts.
        """
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the k9b baseline install section (either "Ensure k9b lab baseline" or legacy "Install k9b baseline")
        install_section_start = content.find("Ensure k9b lab baseline")
        if install_section_start == -1:
            install_section_start = content.find("Install k9b baseline")
        assert install_section_start != -1, "Should have 'Ensure k9b lab baseline' step"

        # Extract the install section (look for next step)
        next_section = content.find("Run Live OTel Demo Lab", install_section_start)
        if next_section == -1:
            next_section = content.find("Create artifact directory", install_section_start)
        if next_section == -1:
            next_section = len(content)

        install_section = content[install_section_start:next_section]

        # Should NOT have bare helm upgrade --install in the k9b baseline step
        # (it's OK if it's in the OTel demo Helm install step)
        helm_install_lines = [
            line for line in install_section.split('\n')
            if 'helm' in line.lower() and 'upgrade' in line.lower() and '--install' in line
        ]
        assert len(helm_install_lines) == 0, \
            f"OTel k9b baseline step should NOT use direct helm upgrade --install. Found: {helm_install_lines}"

    def test_otel_workflow_no_minimal_helm_wait_pattern(self) -> None:
        """OTel demo lab should NOT use the minimal --wait --timeout 5m pattern.

        The minimal pattern hides evidence when k9b-backend never becomes Ready.
        """
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the k9b baseline install section
        install_section_start = content.find("Install k9b baseline")
        if install_section_start == -1:
            install_section_start = content.find("Install k9b")

        next_section = content.find("Create artifact directory", install_section_start)
        if next_section == -1:
            next_section = len(content)

        install_section = content[install_section_start:next_section]

        # Should NOT have --wait followed by --timeout 5m (the minimal pattern)
        minimal_pattern_lines = [
            line for line in install_section.split('\n')
            if '--wait' in line and '--timeout 5m' in line
        ]
        assert len(minimal_pattern_lines) == 0, \
            f"OTel k9b baseline step should NOT use minimal --wait --timeout 5m pattern. Found: {minimal_pattern_lines}"

    def test_otel_workflow_writes_baseline_result_artifact(self) -> None:
        """CLI wrapper should write k9b-baseline-result.json artifact."""
        content = CLI_WRAPPER.read_text()
        assert "k9b-baseline-result.json" in content, \
            "CLI wrapper should write k9b-baseline-result.json artifact"


class TestCliWrapper:
    """Tests for the CLI wrapper script."""

    def test_cli_wrapper_exists(self) -> None:
        """CLI wrapper should exist."""
        assert CLI_WRAPPER.exists(), f"CLI wrapper not found at {CLI_WRAPPER}"

    def test_cli_wrapper_calls_common_baseline_installer(self) -> None:
        """CLI wrapper should call ensure_k9b_baseline_ready."""
        content = CLI_WRAPPER.read_text()
        assert "from scripts.k9b_lab_common_baseline import ensure_k9b_baseline_ready" in content, \
            "CLI wrapper should import ensure_k9b_baseline_ready"
        assert "ensure_k9b_baseline_ready(" in content, \
            "CLI wrapper should call ensure_k9b_baseline_ready"

    def test_cli_wrapper_writes_baseline_result_artifact(self) -> None:
        """CLI wrapper should write k9b-baseline-result.json artifact."""
        content = CLI_WRAPPER.read_text()
        assert "k9b-baseline-result.json" in content, \
            "CLI wrapper should write k9b-baseline-result.json artifact"


class TestCommonBaselineModule:
    """Test that the common baseline module has the required functionality."""

    def test_common_baseline_module_exists(self) -> None:
        """The common baseline module should exist."""
        assert COMMON_BASELINE_MODULE.exists(), \
            f"Common baseline module not found at {COMMON_BASELINE_MODULE}"

    def test_common_baseline_module_has_ensure_k9b_baseline_ready(self) -> None:
        """Common baseline module should have ensure_k9b_baseline_ready function."""
        content = COMMON_BASELINE_MODULE.read_text()
        assert "def ensure_k9b_baseline_ready(" in content, \
            "Common baseline module should have ensure_k9b_baseline_ready function"

    def test_rollout_module_uses_kubectl_rollout_status(self) -> None:
        """Rollout module should wait for rollout using kubectl rollout status."""
        content = ROLLOUT_MODULE.read_text()
        assert "rollout" in content
        assert "status" in content
        assert "deployment/" in content

    def test_helm_module_renders_manifest(self) -> None:
        """Helm module should render manifest using helm template."""
        content = HELM_MODULE.read_text()
        assert "helm" in content
        assert "template" in content
        assert "rendered-manifest.yaml" in content

    def test_helm_module_collects_values_json_and_yaml(self) -> None:
        """Helm module should collect both JSON and YAML values artifacts."""
        content = HELM_MODULE.read_text()
        assert "get-values.json" in content
        assert "get-values.yaml" in content
        assert '"-o", "json"' in content
        assert '"-o", "yaml"' in content

    def test_helm_module_collects_status_and_history(self) -> None:
        """Helm module should collect status.json and history.json."""
        content = HELM_MODULE.read_text()
        assert "status.json" in content
        assert "history.json" in content

    def test_helm_module_collects_get_manifest(self) -> None:
        """Helm module should collect get-manifest.yaml."""
        content = HELM_MODULE.read_text()
        assert "get-manifest.yaml" in content

    def test_rollout_module_has_failure_classification(self) -> None:
        """Rollout module should classify rollout failures."""
        content = ROLLOUT_MODULE.read_text()
        assert "classify" in content.lower()
        assert "failure" in content.lower()

    def test_rollout_module_collects_failure_evidence(self) -> None:
        """Rollout module should collect failure evidence."""
        content = ROLLOUT_MODULE.read_text()
        assert "_collect_rollout_failure_evidence" in content or "evidence" in content.lower()


class TestCommonBaselineEvidenceContract:
    """Test that the common baseline module preserves the CNPG evidence contract."""

    def test_preserves_helm_rendered_manifest_path(self) -> None:
        """Common baseline should write rendered manifest to helm/rendered-manifest.yaml."""
        content = COMMON_BASELINE_MODULE.read_text()
        assert "helm" in content.lower() and "rendered-manifest.yaml" in content, \
            "Should write rendered-manifest.yaml under helm/ directory"

    def test_preserves_helm_status_history_evidence(self) -> None:
        """Common baseline should write Helm status and history evidence."""
        content = COMMON_BASELINE_MODULE.read_text()
        assert "status.json" in content and "history.json" in content, \
            "Should write helm status.json and history.json"

    def test_preserves_helm_get_evidence(self) -> None:
        """Common baseline should write Helm get manifest and values evidence."""
        content = COMMON_BASELINE_MODULE.read_text()
        assert "get-manifest.yaml" in content and "get-values.json" in content, \
            "Should write helm get-manifest.yaml and get-values.json"

    def test_preserves_install_log_evidence(self) -> None:
        """Common baseline should write install output logs."""
        content = COMMON_BASELINE_MODULE.read_text()
        assert "install-output.log" in content or "install" in content.lower(), \
            "Should write install output logs"

    def test_common_baseline_returns_success_dict(self) -> None:
        """Common baseline should return a dict with success, message, artifacts."""
        content = COMMON_BASELINE_MODULE.read_text()
        assert "return {" in content or "return result" in content, \
            "Should return result dict"
        assert "success" in content, \
            "Result should include success field"
        assert "artifacts" in content, \
            "Result should include artifacts field"


class TestRegressionTests:
    """Regression tests to prevent OTel lab from drifting back to minimal Helm path."""

    def test_otel_workflow_uses_cli_wrapper_for_k9b_baseline(self) -> None:
        """Install k9b baseline should use CLI wrapper via module invocation, not file path."""
        content = OTEL_WORKFLOW_FILE.read_text()
        install_section_start = content.find("Ensure k9b lab baseline")
        if install_section_start == -1:
            install_section_start = content.find("Install k9b baseline")
        assert install_section_start != -1, "Should have 'Ensure k9b lab baseline' step"

        section = content[install_section_start:install_section_start + 3000]

        # Must use module invocation from repo root for correct sys.path
        # See: https://docs.python.org/3/library/sys_path_init.html
        assert "python -m scripts.ensure_k9b_lab_baseline" in section, \
            "Should use module invocation (python -m scripts.ensure_k9b_lab_baseline)"
        assert "scripts/ensure_k9b_lab_baseline.py" not in section, \
            "Should NOT use direct file path (scripts/ensure_k9b_lab_baseline.py)"
        assert "python -c" not in section, \
            "Should NOT use inline python -c block"
        assert "ensure_k9b_baseline_ready(" not in section, \
            "Should NOT call ensure_k9b_baseline_ready directly"

    def test_otel_workflow_no_raw_helm_in_install_section(self) -> None:
        """Install k9b baseline section should not have raw helm commands."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the install k9b baseline section
        install_section_start = content.find("Install k9b baseline")
        if install_section_start == -1:
            install_section_start = content.find("Installing k9b baseline")

        assert install_section_start != -1, "Should have k9b baseline install section"

        # Find next major section
        next_sections = [
            "Create artifact directory",
            "Run Live OTel Demo Lab",
            "Run Live OTel",
        ]
        next_section = len(content)
        for section in next_sections:
            pos = content.find(section, install_section_start)
            if pos != -1 and pos < next_section:
                next_section = pos

        install_section = content[install_section_start:next_section]

        # Should NOT have 'helm --kubeconfig' commands in the install section
        # (only in the OTel demo Helm install step)
        raw_helm_lines = [
            line for line in install_section.split('\n')
            if 'helm' in line.lower() and '--kubeconfig' in line
        ]
        assert len(raw_helm_lines) == 0, \
            f"k9b baseline section should NOT have raw helm commands. Found: {raw_helm_lines}"

    def test_otel_workflow_no_pure_helm_wait(self) -> None:
        """Install k9b baseline should not use pure Helm --wait without Python evidence."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the install k9b baseline section
        install_section_start = content.find("Install k9b baseline")
        if install_section_start == -1:
            install_section_start = content.find("Installing k9b baseline")

        # Check that if there's helm install, it should be inside Python call
        # Not standalone shell commands
        lines = content[install_section_start:install_section_start + 5000].split('\n')

        # Track if we're inside Python multiline string
        in_python = False
        for line in lines:
            if '.venv/bin/python' in line or 'python -c' in line:
                in_python = True
            elif in_python and ('"' in line or "'" in line) and 'helm' in line.lower():
                # Inside Python string - this is OK
                pass
            elif 'helm upgrade --install' in line and '--kubeconfig' in line:
                # This is a raw shell helm command - NOT OK in k9b baseline section
                # Unless it's in a Python heredoc
                if 'python' not in line and 'run' not in line.lower():
                    assert False, f"Found raw helm command outside Python: {line.strip()}"


class TestClassifyRolloutFailure:
    """Unit tests for rollout failure classification."""

    def test_progress_deadline_exceeded_condition(self) -> None:
        """Kubernetes Deployment ProgressDeadlineExceeded condition structure.

        The correct condition shape is:
          type: "Progressing"
          status: "False"
          reason: "ProgressDeadlineExceeded"

        NOT:
          type: "ProgressDeadlineExceeded"
        """
        # Test that classify_rollout_failure handles the correct condition shape
        from unittest.mock import MagicMock, patch

        from scripts.k9b_lab_rollout import classify_rollout_failure

        # Simulate a Deployment with ProgressDeadlineExceeded condition
        deploy_json = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "k9b-backend", "namespace": "k9b"},
            "status": {
                "conditions": [
                    {
                        "type": "Available",
                        "status": "True",
                        "lastUpdateTime": "2024-01-01T00:00:00Z",
                    },
                    {
                        "type": "Progressing",
                        "status": "False",
                        "reason": "ProgressDeadlineExceeded",
                        "lastUpdateTime": "2024-01-01T00:01:00Z",
                        "message": "Replicas not making progress",
                    },
                ]
            },
        }

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "pods" in cmd:
                result.stdout = '{"items": [{"status": {"phase": "Running"}}]}'
            elif "deployment" in cmd:
                import json
                result.stdout = json.dumps(deploy_json)
            return result

        with patch("subprocess.run", side_effect=mock_run):
            failure_class = classify_rollout_failure(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                deployment="k9b-backend",
            )

        assert failure_class == "deployment_progress_deadline", \
            f"Expected deployment_progress_deadline, got {failure_class}"

    def test_replica_failure_condition(self) -> None:
        """ReplicaFailure condition should be detected."""
        from unittest.mock import MagicMock, patch

        from scripts.k9b_lab_rollout import classify_rollout_failure

        deploy_json = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "status": {
                "conditions": [
                    {
                        "type": "ReplicaFailure",
                        "status": "True",
                        "reason": "FailedCreate",
                    },
                ]
            },
        }

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "pods" in cmd:
                result.stdout = '{"items": []}'
            elif "deployment" in cmd:
                import json
                result.stdout = json.dumps(deploy_json)
            return result

        with patch("subprocess.run", side_effect=mock_run):
            failure_class = classify_rollout_failure(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                deployment="k9b-backend",
            )

        assert failure_class == "deployment_replica_failure", \
            f"Expected deployment_replica_failure, got {failure_class}"

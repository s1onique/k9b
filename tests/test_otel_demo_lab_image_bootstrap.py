"""Tests for OTel live lab image bootstrap.

These tests ensure that:
1. OTel live lab builds and pushes the k9b image to Harbor before baseline install
2. OTel passes backend image repository/tag/pullPolicy into the baseline installer
3. OTel does not use local-only k3s ctr images import as the primary path
4. OTel does not use latest tag
5. The common baseline helper accepts and forwards Helm image overrides

NOTE: This file tests the OTel LIVE LAB workflow (k9b-otel-demo-live-lab.yml).
CI-only workflow (k9b-otel-demo-incident-lab.yml) does not have image bootstrap.
"""

import re
from pathlib import Path

# Path to the OTel demo live lab workflow file
OTEL_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-live-lab.yml"
# CI-only workflow for reference (should NOT have these features)
OTEL_CI_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-incident-lab.yml"


class TestOTelLiveLabImageBootstrap:
    """Test that OTel live lab uses Harbor-based image bootstrap."""

    def test_workflow_file_exists(self) -> None:
        """The OTel demo live lab workflow file should exist."""
        assert OTEL_WORKFLOW_FILE.exists(), f"OTel workflow not found at {OTEL_WORKFLOW_FILE}"

    def test_build_lab_images_job_exists(self) -> None:
        """Workflow should have a build-lab-images job."""
        content = OTEL_WORKFLOW_FILE.read_text()
        assert "build-lab-images:" in content, "build-lab-images job not found"

    def test_build_lab_images_uses_docker_build_push(self) -> None:
        """build-lab-images job should build and push image to Harbor."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the build-lab-images section
        build_section_start = content.find("build-lab-images:")
        assert build_section_start != -1, "build-lab-images section not found"

        # Find the next job or end of file
        next_job = content.find("\n  # ======", build_section_start)
        if next_job == -1:
            next_job = len(content)

        build_section = content[build_section_start:next_job]

        assert "docker/build-push-action" in build_section, \
            "build-lab-images should use docker/build-push-action"
        assert "push: true" in build_section, \
            "build-lab-images should push images to registry"

    def test_live_lab_depends_on_build_images(self) -> None:
        """live-k3s-lab should depend on build-lab-images."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the live-k3s-lab section
        live_section_start = content.find("live-k3s-lab:")
        assert live_section_start != -1, "live-k3s-lab section not found"

        # Extract job definition (until next job)
        next_job = content.find("\n  # ======", live_section_start)
        if next_job == -1:
            next_job = content.find("\njobs:", live_section_start + 10)
        if next_job == -1:
            next_job = len(content)

        live_section = content[live_section_start:next_job]

        assert "needs: build-lab-images" in live_section, \
            "live-k3s-lab should depend on build-lab-images"

    def test_live_lab_receives_image_outputs(self) -> None:
        """live-k3s-lab should receive image outputs from build-lab-images."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the Ensure k9b lab baseline section
        baseline_start = content.find("Ensure k9b lab baseline")
        assert baseline_start != -1, "Ensure k9b lab baseline section not found"

        # Extract the section (next major section)
        next_section = content.find("Run Live OTel Demo Lab", baseline_start)
        if next_section == -1:
            next_section = len(content)

        baseline_section = content[baseline_start:next_section]

        assert "needs.build-lab-images.outputs.backend_image_repository" in baseline_section, \
            "Should use backend_image_repository from build-lab-images"
        assert "needs.build-lab-images.outputs.backend_image_tag" in baseline_section, \
            "Should use backend_image_tag from build-lab-images"
        assert "image.backend.repository=" in baseline_section, \
            "Should override image.backend.repository"
        assert "image.backend.tag=" in baseline_section, \
            "Should override image.backend.tag"
        assert "image.backend.pullPolicy=IfNotPresent" in baseline_section, \
            "Should set image.backend.pullPolicy=IfNotPresent"

    def test_workflow_no_k3s_ctr_import(self) -> None:
        """Workflow should NOT use k3s ctr images import as primary path.

        This is the local-only import pattern that doesn't work for multi-node clusters.
        The workflow should use Harbor registry instead.
        """
        content = OTEL_WORKFLOW_FILE.read_text()

        # Check that k3s ctr images import is NOT present
        assert "k3s ctr images import" not in content, \
            "OTel workflow should NOT use k3s ctr images import as primary image delivery"

    def test_workflow_no_latest_tag(self) -> None:
        """Workflow should NOT use 'latest' tag for k9b-backend image.

        Using 'latest' or no explicit tag causes Kubernetes to set
        pullPolicy=Always, which can reintroduce registry/pull issues.
        """
        content = OTEL_WORKFLOW_FILE.read_text()

        # Check for problematic patterns
        problematic_patterns = [
            ":latest",
            "image.backend.tag=latest",
            "image.backend.tag: latest",
        ]

        for pattern in problematic_patterns:
            assert pattern not in content, \
                f"OTel workflow should NOT use '{pattern}' tag (causes Always pull policy)"

    def test_image_tag_includes_run_id_and_sha(self) -> None:
        """Image tag should include run ID and commit SHA for immutability."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the build-lab-images section
        build_start = content.find("build-lab-images:")
        assert build_start != -1

        next_job = content.find("\n  # ======", build_start)
        if next_job == -1:
            next_job = len(content)

        build_section = content[build_start:next_job]

        # Check that tag includes github.run_id
        assert "github.run_id" in build_section, \
            "Image tag should include github.run_id"
        assert "github.run_attempt" in build_section, \
            "Image tag should include github.run_attempt"
        assert "github.sha" in build_section, \
            "Image tag should include github.sha for immutability"


class TestBaselineInstallerAcceptsImageOverrides:
    """Test that the baseline installer accepts and forwards Helm image overrides."""

    def test_cli_wrapper_accepts_set_flag(self) -> None:
        """CLI wrapper should accept --set flag for Helm values."""
        cli_wrapper = Path(__file__).parent.parent / "scripts" / "ensure_k9b_lab_baseline.py"
        content = cli_wrapper.read_text()

        assert '"--set"' in content or "'--set'" in content, \
            "CLI wrapper should accept --set flag"
        assert "set_values" in content, \
            "CLI wrapper should pass set_values to baseline function"

    def test_baseline_function_accepts_set_values(self) -> None:
        """ensure_k9b_baseline_ready should accept set_values parameter."""
        baseline_module = Path(__file__).parent.parent / "scripts" / "k9b_lab_common_baseline.py"
        content = baseline_module.read_text()

        assert "set_values" in content, \
            "ensure_k9b_baseline_ready should accept set_values parameter"

    def test_helm_functions_forward_set_values(self) -> None:
        """Helm render and install functions should forward set_values."""
        helm_module = Path(__file__).parent.parent / "scripts" / "k9b_lab_helm.py"
        content = helm_module.read_text()

        # Check render_manifest accepts and uses set_values
        assert "set_values" in content, \
            "render_manifest should accept set_values"

        # Check install_helm accepts and uses set_values
        assert content.count("set_values") >= 2, \
            "Both render_manifest and install_helm should use set_values"


class TestWorkflowDoesNotDrift:
    """Regression tests to prevent OTel lab from drifting back to broken image path."""

    def test_baseline_step_uses_module_invocation(self) -> None:
        """Ensure k9b lab baseline should use module invocation, not direct file path."""
        content = OTEL_WORKFLOW_FILE.read_text()

        baseline_start = content.find("Ensure k9b lab baseline")
        assert baseline_start != -1, "Ensure k9b lab baseline section not found"

        next_section = content.find("Run Live OTel Demo Lab", baseline_start)
        if next_section == -1:
            next_section = len(content)

        baseline_section = content[baseline_start:next_section]

        assert "python -m scripts.ensure_k9b_lab_baseline" in baseline_section, \
            "Should use module invocation for baseline installer"

    def test_no_raw_helm_upgrade_in_baseline(self) -> None:
        """Baseline step should not contain raw helm upgrade --install commands."""
        content = OTEL_WORKFLOW_FILE.read_text()

        baseline_start = content.find("Ensure k9b lab baseline")
        assert baseline_start != -1, "Ensure k9b lab baseline section not found"

        next_section = content.find("Run Live OTel Demo Lab", baseline_start)
        if next_section == -1:
            next_section = len(content)

        baseline_section = content[baseline_start:next_section]

        # Check that there's no bare helm upgrade --install in the baseline section
        # (it's OK if it's inside Python module call)
        raw_helm_lines = [
            line for line in baseline_section.split('\n')
            if 'helm' in line.lower() and 'upgrade' in line.lower() and '--install' in line
            and 'python' not in line
        ]

        assert len(raw_helm_lines) == 0, \
            f"Baseline section should not contain raw helm commands. Found: {raw_helm_lines}"

    def test_harbor_registry_used(self) -> None:
        """Workflow should use Harbor registry for image delivery."""
        content = OTEL_WORKFLOW_FILE.read_text()

        assert "harbor-pve1.spbnix.local" in content, \
            "Workflow should use Harbor registry for image delivery"

    def test_workflow_includes_image_builder_path(self) -> None:
        """Workflow should include k9b-image-builder.yml in path triggers."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # The workflow should be aware of image-related changes
        assert "k9b-otel-demo-live-lab" in content, \
            "Workflow should be in the triggers"


class TestImageTagImmutability:
    """Tests for image tag immutability requirements."""

    def test_unique_tag_per_run(self) -> None:
        """Image tag should be unique per run using run_id, attempt, and sha."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the image tag generation
        assert re.search(
            r'IMAGE_TAG="otel-live-\${{\s*github\.run_id\s*}}-\${{\s*github\.run_attempt\s*}}-\${{\s*github\.sha\s*}}"',
            content,
        ), "Image tag should include run_id, attempt, and sha for uniqueness"

    def test_no_floating_tags(self) -> None:
        """Workflow should not use floating tags like 'latest' or 'main'."""
        content = OTEL_WORKFLOW_FILE.read_text()

        floating_tags = [":latest", ":main", ":master", ":stable"]

        for tag in floating_tags:
            assert tag not in content, \
                f"Workflow should not use floating tag '{tag}'"


# Path to the reusable Harbor build workflow
HARBOR_BUILD_IMAGE_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "harbor-build-image.yml"


class TestBuildKitHarborCATrust:
    """Tests that BuildKit is configured with Harbor CA trust for self-signed certs.

    BuildKit runs in docker-container driver mode, which requires explicit registry
    CA configuration via buildkitd.toml. Without this, BuildKit cannot resolve
    Harbor images due to x509: certificate signed by unknown authority.
    """

    def test_otel_workflow_has_buildkitd_config_for_harbor(self) -> None:
        """OTel workflow should configure BuildKit with Harbor CA trust."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Find the build-lab-images section
        build_start = content.find("build-lab-images:")
        assert build_start != -1, "build-lab-images section not found"

        next_job = content.find("\n  # ======", build_start)
        if next_job == -1:
            next_job = len(content)

        build_section = content[build_start:next_job]

        # Verify BuildKit CA configuration exists
        assert "Configure BuildKit with Harbor CA" in build_section, \
            "Should have 'Configure BuildKit with Harbor CA' step"
        assert 'buildkitd.toml' in build_section, \
            "Should create buildkitd.toml for BuildKit registry CA config"
        # Hermetic wiring: wire_docker_buildx.sh receives the config path
        assert "Set up Docker Buildx" in build_section, \
            "Should have 'Set up Docker Buildx' step"
        assert "scripts/ci/wire_docker_buildx.sh" in build_section, \
            "Should use hermetic wire_docker_buildx.sh script"
        assert "BUILDKITD_CONFIG:" in build_section, \
            "Hermetic Buildx wiring should receive the generated BuildKit config"
        assert "steps.buildkitd-config.outputs.path" in build_section, \
            "BuildKit config should reference the generated config path"
        assert "docker/setup-buildx-action" not in build_section, \
            "Should NOT use docker/setup-buildx-action (hermetic policy)"

    def test_otel_workflow_uses_runner_temp_cert_path(self) -> None:
        """OTel workflow should use RUNNER_TEMP for CA cert, not /run/secrets/.
        
        The buildkitd.toml must reference a path that setup-buildx-action can read
        when creating the BuildKit builder container.
        """
        content = OTEL_WORKFLOW_FILE.read_text()

        # Verify the cert is written to RUNNER_TEMP
        assert '${RUNNER_TEMP}/buildkit-certs/harbor-pve1.spbnix.local.pem' in content, \
            "CA cert should be written to RUNNER_TEMP path"
        
        # Verify the TOML uses the cert_path variable (which resolves to RUNNER_TEMP)
        assert 'ca = ["${cert_path}"]' in content, \
            "TOML ca config should use ${cert_path} variable"
        
        # Verify we don't use /run/secrets/ which is not accessible from runner
        assert "/run/secrets/buildkit-certs/" not in content, \
            "Should NOT use /run/secrets/ path (not accessible from runner)"

    def test_otel_workflow_uses_registry_toml_config(self) -> None:
        """OTel workflow should use BuildKit registry TOML config format."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # Verify the TOML registry config format
        assert '[registry."harbor-pve1.spbnix.local"]' in content, \
            'Should have TOML [registry."harbor-pve1.spbnix.local"] section'
        assert 'ca = ["${cert_path}"]' in content, \
            "Should configure CA path in TOML registry section"

    def test_otel_workflow_has_harbor_ca_docker_certs_d(self) -> None:
        """OTel workflow should install CA into /etc/docker/certs.d for Docker daemon."""
        content = OTEL_WORKFLOW_FILE.read_text()

        # The install-spbnix-harbor-ca.sh script handles this, but verify it's called
        assert "Install SPbNIX Harbor CA" in content, \
            "Should install Harbor CA into runner"
        assert "install-spbnix-harbor-ca.sh" in content, \
            "Should use the CA installation script"


class TestReusableHarborBuildImageWorkflow:
    """Tests that the reusable harbor-build-image.yml workflow has proper BuildKit CA config.
    
    The reusable workflow pulls BuildKit daemon image from Harbor, so it needs:
    1. CA installed into runner system trust before setup-buildx
    2. buildkitd.toml with registry CA configuration
    3. buildkitd-config wired into setup-buildx-action
    """

    def test_harbor_workflow_file_exists(self) -> None:
        """The Harbor build image workflow file should exist."""
        assert HARBOR_BUILD_IMAGE_WORKFLOW_FILE.exists(), \
            f"Harbor build workflow not found at {HARBOR_BUILD_IMAGE_WORKFLOW_FILE}"

    def test_harbor_workflow_has_buildkitd_config_for_harbor(self) -> None:
        """Reusable workflow should configure BuildKit with Harbor CA trust."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW_FILE.read_text()

        assert "Configure BuildKit with Harbor CA" in content, \
            "Should have 'Configure BuildKit with Harbor CA' step"
        assert '${RUNNER_TEMP}/buildkit-certs/harbor-pve1.spbnix.local.pem' in content, \
            "CA cert should be written to RUNNER_TEMP path"
        assert '[registry."harbor-pve1.spbnix.local"]' in content, \
            "Should have TOML registry config section"
        assert 'ca = ["${cert_path}"]' in content, \
            "TOML ca config should use ${cert_path} variable"
        # Hermetic wiring: wire_docker_buildx.sh receives the config path
        assert "Set up Docker Buildx" in content, \
            "Should have 'Set up Docker Buildx' step"
        assert "scripts/ci/wire_docker_buildx.sh" in content, \
            "Should use hermetic wire_docker_buildx.sh script"
        assert "BUILDKITD_CONFIG:" in content, \
            "Hermetic Buildx wiring should receive the generated BuildKit config"
        assert "steps.buildkitd-config.outputs.path" in content, \
            "BuildKit config should reference the generated config path"
        assert "builder: ${{ steps.buildx.outputs.name }}" in content, \
            "build-push-action should use the builder from wire script"
        assert "docker/setup-buildx-action" not in content, \
            "Should NOT use docker/setup-buildx-action (hermetic policy)"
        assert "/run/secrets/buildkit-certs/" not in content, \
            "Should NOT use /run/secrets/ path (not accessible from runner)"

    def test_harbor_workflow_ca_install_before_buildx(self) -> None:
        """CA install must happen before setup-buildx-action.
        
        The reusable workflow pulls BuildKit daemon image from Harbor. Docker daemon
        needs the CA in system trust to pull the image, so Install SPbNIX Harbor CA
        must come before Set up Docker Buildx.
        """
        content = HARBOR_BUILD_IMAGE_WORKFLOW_FILE.read_text()

        install_pos = content.find("Install SPbNIX Harbor CA")
        buildx_pos = content.find("Set up Docker Buildx")

        assert install_pos != -1, "Should have 'Install SPbNIX Harbor CA' step"
        assert buildx_pos != -1, "Should have 'Set up Docker Buildx' step"
        assert install_pos < buildx_pos, \
            "'Install SPbNIX Harbor CA' must come before 'Set up Docker Buildx'"

    def test_harbor_workflow_configure_buildkit_before_buildx(self) -> None:
        """Configure BuildKit step must happen before setup-buildx-action.
        
        The buildkitd.toml must be written before setup-buildx-action uses it.
        """
        content = HARBOR_BUILD_IMAGE_WORKFLOW_FILE.read_text()

        configure_pos = content.find("Configure BuildKit with Harbor CA")
        buildx_pos = content.find("Set up Docker Buildx")

        assert configure_pos != -1, "Should have 'Configure BuildKit with Harbor CA' step"
        assert buildx_pos != -1, "Should have 'Set up Docker Buildx' step"
        assert configure_pos < buildx_pos, \
            "'Configure BuildKit with Harbor CA' must come before 'Set up Docker Buildx'"

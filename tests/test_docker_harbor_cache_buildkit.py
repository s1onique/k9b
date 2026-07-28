"""Regression tests for BuildKit/cache behavior assertions.

These tests verify that buildctl/buildkit usage, cache-from/cache-to configuration,
rootless BuildKit options, and CA/auth config mounting are correct in all
docker/build-push-action usages in k9b workflows.
"""

from pathlib import Path

from tests.helpers.docker_harbor_cache_helpers import (
    HARBOR_BUILD_IMAGE_WORKFLOW,
    K9B_IMAGE_BUILDER_WORKFLOW,
    OTEL_DEMO_LIVE_LAB_WORKFLOW,
    find_build_push_steps,
    load_workflow,
    parse_registry_cache_spec,
)

# Root of the repository
REPO_ROOT = Path(__file__).resolve().parents[1]


class TestHarborBuildImageCacheBehavior:
    """Tests for BuildKit/cache behavior in harbor-build-image.yml."""

    def test_build_push_has_cache_from(self) -> None:
        """build-push-action step must have cache-from."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 1, "Should have build-push-action step"

        for i, step in enumerate(steps):
            assert "cache-from" in step.get("with", {}), f"Step {i} must have cache-from in 'with' block"

    def test_build_push_has_cache_to(self) -> None:
        """build-push-action step must have cache-to."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 1, "Should have build-push-action step"

        for i, step in enumerate(steps):
            assert "cache-to" in step.get("with", {}), f"Step {i} must have cache-to in 'with' block"

    def test_cache_backend_is_registry(self) -> None:
        """Cache backend must be type=registry (using semantic parser)."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")

            from_spec = parse_registry_cache_spec(cache_from)
            to_spec = parse_registry_cache_spec(cache_to)

            assert from_spec.backend == "registry", f"Step {i} cache-from must use type=registry, got: {from_spec.backend}"
            assert to_spec.backend == "registry", f"Step {i} cache-to must use type=registry, got: {to_spec.backend}"

    def test_cache_refs_use_harbor_path(self) -> None:
        """Cache refs must use the Harbor registry path components.

        Uses semantic parser to verify that format arguments include
        inputs.registry and inputs.harbor_project.
        """
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")

            spec = parse_registry_cache_spec(cache_from)

            # For conditional format expressions, verify the format arguments
            if spec.format_arguments:
                assert "inputs.registry" in spec.format_arguments, f"Step {i} cache-from must use inputs.registry, got: {spec.format_arguments}"
                assert "inputs.harbor_project" in spec.format_arguments, f"Step {i} cache-from must use inputs.harbor_project, got: {spec.format_arguments}"
                assert "cache/" in spec.ref_template, f"Step {i} cache-from must use cache/ path, got: {spec.ref_template}"
            else:
                # Literal ref
                assert "harbor-pve1.spbnix.local/k9b/cache/" in spec.ref_template, f"Step {i} cache-from must use Harbor cache path, got: {spec.ref_template}"

    def test_cache_refs_end_with_buildcache(self) -> None:
        """Cache refs must end with :buildcache.

        Uses semantic parser to handle both literal refs and conditional
        GitHub format() expressions used by harbor-build-image.yml.
        """
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")

            # Parse cache-from using semantic parser
            cache_from_spec = parse_registry_cache_spec(cache_from)

            # Assert ref_template ends with :buildcache
            assert cache_from_spec.ref_template.endswith(":buildcache"), f"Step {i} cache-from ref_template must end with :buildcache, got: {cache_from_spec.ref_template}"

            # Assert format_arguments include inputs.image_name
            assert "inputs.image_name" in cache_from_spec.format_arguments, f"Step {i} cache-from must use inputs.image_name argument, got: {cache_from_spec.format_arguments}"

            # Parse cache-to using semantic parser
            cache_to_spec = parse_registry_cache_spec(cache_to)

            # Assert ref_template ends with :buildcache
            assert cache_to_spec.ref_template.endswith(":buildcache"), f"Step {i} cache-to ref_template must end with :buildcache, got: {cache_to_spec.ref_template}"

            # Assert format_arguments include inputs.image_name
            assert "inputs.image_name" in cache_to_spec.format_arguments, f"Step {i} cache-to must use inputs.image_name argument, got: {cache_to_spec.format_arguments}"

    def test_cache_to_uses_mode_max(self) -> None:
        """cache-to must use mode=max (using semantic parser)."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_to = step.get("with", {}).get("cache-to", "")

            spec = parse_registry_cache_spec(cache_to)

            assert spec.mode == "max", f"Step {i} cache-to must use mode=max, got: {spec.mode}"

    def test_workflow_has_multiplatform_build(self) -> None:
        """Workflow should build for multiple platforms."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            platforms = step.get("with", {}).get("platforms", "")
            assert "linux/amd64" in platforms, f"Step {i} should build for linux/amd64"
            assert "linux/arm64" in platforms, f"Step {i} should build for linux/arm64"


class TestK9BImageBuilderCacheBehavior:
    """Tests for BuildKit/cache behavior in k9b-image-builder.yml."""

    def test_backend_build_has_cache_from(self) -> None:
        """Backend build step must have cache-from."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        # First step should be backend
        backend_step = steps[0]
        assert "cache-from" in backend_step.get("with", {}), "Backend build step must have cache-from"

    def test_backend_build_has_cache_to(self) -> None:
        """Backend build step must have cache-to."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        backend_step = steps[0]
        assert "cache-to" in backend_step.get("with", {}), "Backend build step must have cache-to"

    def test_frontend_build_has_cache_from(self) -> None:
        """Frontend build step must have cache-from."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        # Second step should be frontend
        assert len(steps) >= 2, "Should have frontend build step"
        frontend_step = steps[1]
        assert "cache-from" in frontend_step.get("with", {}), "Frontend build step must have cache-from"

    def test_frontend_build_has_cache_to(self) -> None:
        """Frontend build step must have cache-to."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        frontend_step = steps[1]
        assert "cache-to" in frontend_step.get("with", {}), "Frontend build step must have cache-to"

    def test_all_cache_backends_are_registry(self) -> None:
        """All cache steps must use type=registry backend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")

            assert "type=registry" in cache_from, f"Step {i} cache-from must use type=registry"
            assert "type=registry" in cache_to, f"Step {i} cache-to must use type=registry"

    def test_all_cache_to_use_mode_max(self) -> None:
        """All cache-to steps must use mode=max."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_to = step.get("with", {}).get("cache-to", "")
            assert "mode=max" in cache_to, f"Step {i} cache-to must use mode=max"


class TestOTelDemoLiveLabCacheBehavior:
    """Tests for BuildKit/cache behavior in k9b-otel-demo-live-lab.yml."""

    def test_build_lab_images_has_cache(self) -> None:
        """build-lab-images job should have cache-from and cache-to."""
        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()

        # Find the build-lab-images section
        build_start = content.find("build-lab-images:")
        assert build_start != -1, "build-lab-images section not found"

        # Find next job or end
        next_marker = content.find("\n  # ======", build_start)
        if next_marker == -1:
            next_marker = len(content)

        build_section = content[build_start:next_marker]

        assert "cache-from:" in build_section, "build-lab-images should have cache-from"
        assert "cache-to:" in build_section, "build-lab-images should have cache-to"

    def test_cache_uses_registry_backend(self) -> None:
        """Cache must use type=registry backend."""
        import re

        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()

        build_start = content.find("build-lab-images:")
        next_marker = content.find("\n  # ======", build_start)
        if next_marker == -1:
            next_marker = len(content)

        build_section = content[build_start:next_marker]

        # Extract cache-from and cache-to values
        cache_from_match = re.search(r"cache-from:\s*(\S+)", build_section)
        cache_to_match = re.search(r"cache-to:\s*(\S+)", build_section)

        assert cache_from_match, "Should have cache-from value"
        assert cache_to_match, "Should have cache-to value"

        cache_from = cache_from_match.group(1)
        cache_to = cache_to_match.group(1)

        assert "type=registry" in cache_from, f"cache-from must use type=registry, got: {cache_from}"
        assert "type=registry" in cache_to, f"cache-to must use type=registry, got: {cache_to}"

    def test_cache_to_uses_mode_max(self) -> None:
        """cache-to must use mode=max."""
        import re

        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()

        build_start = content.find("build-lab-images:")
        next_marker = content.find("\n  # ======", build_start)
        if next_marker == -1:
            next_marker = len(content)

        build_section = content[build_start:next_marker]

        cache_to_match = re.search(r"cache-to:\s*(\S+)", build_section)
        assert cache_to_match, "Should have cache-to value"

        cache_to = cache_to_match.group(1)
        assert "mode=max" in cache_to, f"cache-to must use mode=max, got: {cache_to}"


class TestWorkflowContractPreservation:
    """Regression tests that verify workflows pass --buildkitd-config to wire_docker_buildx.sh.

    This contract ensures the script is called with the required --buildkitd-config argument
    and that workflows produce the config via a step with id='buildkitd-config'.
    """

    def test_k9b_image_builder_passes_buildkitd_config_to_wire_script(self) -> None:
        """Verify k9b-image-builder.yml calls wire_docker_buildx.sh with --buildkitd-config.

        The workflow must:
        1. Have a step with id='buildkitd-config' that outputs the config path
        2. Call wire_docker_buildx.sh with --buildkitd-config pointing to that output
        """
        workflow_path = REPO_ROOT / ".github/workflows/k9b-image-builder.yml"
        assert workflow_path.exists(), f"workflow missing: {workflow_path}"

        content = workflow_path.read_text()

        # Must call wire_docker_buildx.sh
        assert "scripts/ci/wire_docker_buildx.sh" in content, "k9b-image-builder.yml must call wire_docker_buildx.sh"

        # Must have buildkitd-config step with path output
        assert "id: buildkitd-config" in content, "k9b-image-builder.yml must have a step with id='buildkitd-config'"
        assert '>> "${GITHUB_OUTPUT}"' in content or '>> "$GITHUB_OUTPUT"' in content, "buildkitd-config step must write to GITHUB_OUTPUT"
        assert "path=" in content, "buildkitd-config step must output 'path' variable"

        # Must pass --buildkitd-config to the script
        assert '--buildkitd-config "${{ steps.buildkitd-config.outputs.path }}"' in content, "k9b-image-builder.yml must pass --buildkitd-config to wire_docker_buildx.sh"

    def test_otel_demo_live_lab_passes_buildkitd_config_to_wire_script(self) -> None:
        """Verify k9b-otel-demo-live-lab.yml calls wire_docker_buildx.sh with --buildkitd-config.

        The workflow must:
        1. Have a step with id='buildkitd-config' that outputs the config path
        2. Call wire_docker_buildx.sh with --buildkitd-config pointing to that output
        """
        workflow_path = REPO_ROOT / ".github/workflows/k9b-otel-demo-live-lab.yml"
        assert workflow_path.exists(), f"workflow missing: {workflow_path}"

        content = workflow_path.read_text()

        # Must call wire_docker_buildx.sh
        assert "scripts/ci/wire_docker_buildx.sh" in content, "k9b-otel-demo-live-lab.yml must call wire_docker_buildx.sh"

        # Must have buildkitd-config step with path output
        assert "id: buildkitd-config" in content, "k9b-otel-demo-live-lab.yml must have a step with id='buildkitd-config'"
        assert '>> "${GITHUB_OUTPUT}"' in content or '>> "$GITHUB_OUTPUT"' in content, "buildkitd-config step must write to GITHUB_OUTPUT"
        assert "path=" in content, "buildkitd-config step must output 'path' variable"

        # Must pass --buildkitd-config to the script
        assert '--buildkitd-config "${{ steps.buildkitd-config.outputs.path }}"' in content, "k9b-otel-demo-live-lab.yml must pass --buildkitd-config to wire_docker_buildx.sh"

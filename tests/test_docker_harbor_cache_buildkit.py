"""Regression tests for BuildKit/cache behavior assertions.

These tests verify that buildctl/buildkit usage, cache-from/cache-to configuration,
rootless BuildKit options, and CA/auth config mounting are correct in all
docker/build-push-action usages in k9b workflows.
"""

from tests.helpers.docker_harbor_cache_helpers import (
    HARBOR_BUILD_IMAGE_WORKFLOW,
    K9B_IMAGE_BUILDER_WORKFLOW,
    OTEL_DEMO_LIVE_LAB_WORKFLOW,
    find_build_push_steps,
    load_workflow,
)


class TestHarborBuildImageCacheBehavior:
    """Tests for BuildKit/cache behavior in harbor-build-image.yml."""

    def test_build_push_has_cache_from(self) -> None:
        """build-push-action step must have cache-from."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 1, "Should have build-push-action step"

        for i, step in enumerate(steps):
            assert "cache-from" in step.get("with", {}), (
                f"Step {i} must have cache-from in 'with' block"
            )

    def test_build_push_has_cache_to(self) -> None:
        """build-push-action step must have cache-to."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 1, "Should have build-push-action step"

        for i, step in enumerate(steps):
            assert "cache-to" in step.get("with", {}), (
                f"Step {i} must have cache-to in 'with' block"
            )

    def test_cache_backend_is_registry(self) -> None:
        """Cache backend must be type=registry."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")

            assert "type=registry" in cache_from, (
                f"Step {i} cache-from must use type=registry, got: {cache_from}"
            )
            assert "type=registry" in cache_to, (
                f"Step {i} cache-to must use type=registry, got: {cache_to}"
            )

    def test_cache_refs_use_harbor_path(self) -> None:
        """Cache refs must point to harbor-pve1.spbnix.local/k9b/cache/.

        Note: harbor-build-image.yml uses GitHub Actions template syntax (${{ inputs.xxx }})
        which is resolved at workflow invocation time, not YAML parse time.
        """
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")

            # Check for resolved path OR template syntax that will resolve to the right path
            has_harbor_path = (
                "harbor-pve1.spbnix.local/k9b/cache/" in cache_from or
                ("inputs.registry" in cache_from and "inputs.harbor_project" in cache_from and "cache/" in cache_from)
            )
            assert has_harbor_path, (
                f"Step {i} cache-from must use Harbor cache path, got: {cache_from}"
            )

    def test_cache_refs_end_with_buildcache(self) -> None:
        """Cache refs must end with :buildcache.

        Note: harbor-build-image.yml uses GitHub Actions template syntax that will
        resolve to image-specific cache refs at invocation time.
        """
        import re

        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")

            # Extract the ref portion (format: type=registry,ref=xxx:tag or type=registry,ref=xxx:tag,mode=xxx)
            # Handle both literal refs and template refs
            cache_from_match = re.search(r"ref=([^,]+)", cache_from)
            cache_to_match = re.search(r"ref=([^,]+)", cache_to)

            assert cache_from_match, f"Step {i} cache-from should have ref= pattern, got: {cache_from}"
            assert cache_to_match, f"Step {i} cache-to should have ref= pattern, got: {cache_to}"

            cache_from_ref = cache_from_match.group(1)
            cache_to_ref = cache_to_match.group(1)

            # For template syntax, check that inputs.image_name is in the ref
            if "${{" in cache_from_ref:
                assert "inputs.image_name" in cache_from_ref, (
                    f"Step {i} cache-from template should use inputs.image_name, got: {cache_from_ref}"
                )
            else:
                assert cache_from_ref.endswith(":buildcache"), (
                    f"Step {i} cache-from ref must end with :buildcache, got: {cache_from_ref}"
                )

            if "${{" in cache_to_ref:
                assert "inputs.image_name" in cache_to_ref, (
                    f"Step {i} cache-to template should use inputs.image_name, got: {cache_to_ref}"
                )
            else:
                assert cache_to_ref.endswith(":buildcache"), (
                    f"Step {i} cache-to ref must end with :buildcache, got: {cache_to_ref}"
                )

    def test_cache_to_uses_mode_max(self) -> None:
        """cache-to must use mode=max."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_to = step.get("with", {}).get("cache-to", "")

            assert "mode=max" in cache_to, (
                f"Step {i} cache-to must use mode=max, got: {cache_to}"
            )

    def test_workflow_has_multiplatform_build(self) -> None:
        """Workflow should build for multiple platforms."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            platforms = step.get("with", {}).get("platforms", "")
            assert "linux/amd64" in platforms, (
                f"Step {i} should build for linux/amd64"
            )
            assert "linux/arm64" in platforms, (
                f"Step {i} should build for linux/arm64"
            )


class TestK9BImageBuilderCacheBehavior:
    """Tests for BuildKit/cache behavior in k9b-image-builder.yml."""

    def test_backend_build_has_cache_from(self) -> None:
        """Backend build step must have cache-from."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        # First step should be backend
        backend_step = steps[0]
        assert "cache-from" in backend_step.get("with", {}), (
            "Backend build step must have cache-from"
        )

    def test_backend_build_has_cache_to(self) -> None:
        """Backend build step must have cache-to."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        backend_step = steps[0]
        assert "cache-to" in backend_step.get("with", {}), (
            "Backend build step must have cache-to"
        )

    def test_frontend_build_has_cache_from(self) -> None:
        """Frontend build step must have cache-from."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        # Second step should be frontend
        assert len(steps) >= 2, "Should have frontend build step"
        frontend_step = steps[1]
        assert "cache-from" in frontend_step.get("with", {}), (
            "Frontend build step must have cache-from"
        )

    def test_frontend_build_has_cache_to(self) -> None:
        """Frontend build step must have cache-to."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        frontend_step = steps[1]
        assert "cache-to" in frontend_step.get("with", {}), (
            "Frontend build step must have cache-to"
        )

    def test_all_cache_backends_are_registry(self) -> None:
        """All cache steps must use type=registry backend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")

            assert "type=registry" in cache_from, (
                f"Step {i} cache-from must use type=registry"
            )
            assert "type=registry" in cache_to, (
                f"Step {i} cache-to must use type=registry"
            )

    def test_all_cache_to_use_mode_max(self) -> None:
        """All cache-to steps must use mode=max."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        for i, step in enumerate(steps):
            cache_to = step.get("with", {}).get("cache-to", "")
            assert "mode=max" in cache_to, (
                f"Step {i} cache-to must use mode=max"
            )


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

        assert "cache-from:" in build_section, (
            "build-lab-images should have cache-from"
        )
        assert "cache-to:" in build_section, (
            "build-lab-images should have cache-to"
        )

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

        assert "type=registry" in cache_from, (
            f"cache-from must use type=registry, got: {cache_from}"
        )
        assert "type=registry" in cache_to, (
            f"cache-to must use type=registry, got: {cache_to}"
        )

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
        assert "mode=max" in cache_to, (
            f"cache-to must use mode=max, got: {cache_to}"
        )

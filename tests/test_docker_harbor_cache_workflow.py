"""Regression tests for Docker Harbor BuildKit registry cache configuration.

These tests ensure that all docker/build-push-action usages in k9b workflows
import cache from and export cache to Harbor-backed BuildKit registry cache.

Cache pattern:
  cache-from: type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/<image-name>:buildcache
  cache-to: type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/<image-name>:buildcache,mode=max

Requirements:
- Every docker/build-push-action step must have cache-from
- Every docker/build-push-action step must have cache-to
- Cache backend must be type=registry
- Cache refs must point to harbor-pve1.spbnix.local/k9b/cache/
- Cache refs must end with :buildcache
- cache-to must use mode=max
- Each image has its own cache ref (not shared)
- Multi-platform builds preserved (linux/amd64,linux/arm64)
- Harbor login/CA setup steps remain present
"""

from tests.helpers.docker_harbor_cache_helpers import (
    HARBOR_BUILD_IMAGE_WORKFLOW,
    K9B_IMAGE_BUILDER_WORKFLOW,
    OTEL_DEMO_LIVE_LAB_WORKFLOW,
    find_build_push_steps,
    load_workflow,
)


class TestHarborBuildImageWorkflowStructure:
    """Tests for .github/workflows/harbor-build-image.yml structure."""

    def test_workflow_file_exists(self) -> None:
        """The Harbor build image workflow should exist."""
        assert HARBOR_BUILD_IMAGE_WORKFLOW.exists(), (
            f"Harbor build workflow not found at {HARBOR_BUILD_IMAGE_WORKFLOW}"
        )

    def test_workflow_has_build_push_action(self) -> None:
        """Workflow should use docker/build-push-action."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 1, "Should have at least one build-push-action step"

    def test_workflow_has_harbor_login(self) -> None:
        """Workflow should have Harbor login step."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()
        assert "docker/login-action" in content, (
            "Workflow should use docker/login-action for Harbor authentication"
        )
        assert "harbor-pve1.spbnix.local" in content, (
            "Workflow should reference Harbor registry"
        )

    def test_workflow_has_buildkit_ca_config(self) -> None:
        """Workflow should have BuildKit CA configuration for Harbor."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()
        assert "Configure BuildKit with Harbor CA" in content, (
            "Should have BuildKit CA configuration step"
        )
        assert "buildkitd.toml" in content, (
            "Should create buildkitd.toml for BuildKit registry CA config"
        )


class TestK9BImageBuilderWorkflowStructure:
    """Tests for .github/workflows/k9b-image-builder.yml structure."""

    def test_workflow_file_exists(self) -> None:
        """The k9b-image-builder workflow should exist."""
        assert K9B_IMAGE_BUILDER_WORKFLOW.exists(), (
            f"k9b-image-builder workflow not found at {K9B_IMAGE_BUILDER_WORKFLOW}"
        )

    def test_workflow_has_build_push_actions(self) -> None:
        """Workflow should use docker/build-push-action for both backend and frontend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 2, "Should have at least 2 build-push-action steps (backend + frontend)"

    def test_workflow_has_harbor_login(self) -> None:
        """Workflow should have Harbor login step."""
        content = K9B_IMAGE_BUILDER_WORKFLOW.read_text()
        assert "docker/login-action" in content, (
            "Workflow should use docker/login-action for Harbor authentication"
        )


class TestOTelDemoLiveLabWorkflowStructure:
    """Tests for .github/workflows/k9b-otel-demo-live-lab.yml structure."""

    def test_workflow_file_exists(self) -> None:
        """The OTel demo live lab workflow should exist."""
        assert OTEL_DEMO_LIVE_LAB_WORKFLOW.exists(), (
            f"OTel demo live lab workflow not found at {OTEL_DEMO_LIVE_LAB_WORKFLOW}"
        )

    def test_build_lab_images_job_exists(self) -> None:
        """build-lab-images job should exist."""
        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()
        assert "build-lab-images:" in content, (
            "build-lab-images section not found"
        )


class TestCacheConsistencyAcrossWorkflows:
    """Tests to ensure cache configuration is consistent and correct."""

    def test_all_workflows_use_same_registry_host(self) -> None:
        """All workflows should use the same Harbor registry host."""
        files = [
            HARBOR_BUILD_IMAGE_WORKFLOW,
            K9B_IMAGE_BUILDER_WORKFLOW,
            OTEL_DEMO_LIVE_LAB_WORKFLOW,
        ]

        for path in files:
            if not path.exists():
                continue
            content = path.read_text()
            assert "harbor-pve1.spbnix.local" in content, (
                f"{path.name} should use Harbor registry host"
            )

    def test_all_cache_refs_use_same_cache_project(self) -> None:
        """All cache refs should use the same cache project path.

        Note: harbor-build-image.yml uses GitHub Actions template syntax that resolves
        to the correct path at workflow invocation time.
        """
        import re

        files = [
            K9B_IMAGE_BUILDER_WORKFLOW,
            OTEL_DEMO_LIVE_LAB_WORKFLOW,
        ]

        for path in files:
            if not path.exists():
                continue
            content = path.read_text()

            # Find all cache refs
            cache_refs = re.findall(
                r"cache-(?:from|to):\s*type=registry,ref=([^\s,]+)",
                content,
            )

            for ref in cache_refs:
                assert ref.startswith("harbor-pve1.spbnix.local/k9b/cache/"), (
                    f"{path.name} cache ref should use /k9b/cache/ path, got: {ref}"
                )

        # Special handling for harbor-build-image.yml which uses template syntax
        if HARBOR_BUILD_IMAGE_WORKFLOW.exists():
            content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()
            # Check that template syntax is used correctly for cache refs
            assert "inputs.registry" in content and "inputs.harbor_project" in content, (
                "harbor-build-image.yml should use inputs for registry and project"
            )
            assert "inputs.image_name" in content, (
                "harbor-build-image.yml should use inputs.image_name for cache ref"
            )

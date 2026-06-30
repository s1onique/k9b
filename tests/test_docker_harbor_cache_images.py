"""Regression tests for Docker Harbor cache image/tag/repository assertions.

These tests verify that image names, tags, and repository paths are correct
in all docker/build-push-action usages in k9b workflows.
"""

from tests.helpers.docker_harbor_cache_helpers import (
    K9B_IMAGE_BUILDER_WORKFLOW,
    OTEL_DEMO_LIVE_LAB_WORKFLOW,
    find_build_push_steps,
    load_workflow,
)


class TestK9BImageBuilderImageNames:
    """Tests for image/tag assertions in k9b-image-builder.yml."""

    def test_backend_cache_ref_is_image_specific(self) -> None:
        """Backend cache ref must be specific to k9b-backend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        backend_cache_from = steps[0].get("with", {}).get("cache-from", "")
        backend_cache_to = steps[0].get("with", {}).get("cache-to", "")

        assert "/cache/k9b-backend:" in backend_cache_from, (
            f"Backend cache-from should reference k9b-backend, got: {backend_cache_from}"
        )
        assert "/cache/k9b-backend:" in backend_cache_to, (
            f"Backend cache-to should reference k9b-backend, got: {backend_cache_to}"
        )

    def test_frontend_cache_ref_is_image_specific(self) -> None:
        """Frontend cache ref must be specific to k9b-frontend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        frontend_cache_from = steps[1].get("with", {}).get("cache-from", "")
        frontend_cache_to = steps[1].get("with", {}).get("cache-to", "")

        assert "/cache/k9b-frontend:" in frontend_cache_from, (
            f"Frontend cache-from should reference k9b-frontend, got: {frontend_cache_from}"
        )
        assert "/cache/k9b-frontend:" in frontend_cache_to, (
            f"Frontend cache-to should reference k9b-frontend, got: {frontend_cache_to}"
        )

    def test_cache_refs_are_not_shared(self) -> None:
        """Backend and frontend should NOT share cache refs."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)

        backend_cache = steps[0].get("with", {}).get("cache-from", "")
        frontend_cache = steps[1].get("with", {}).get("cache-from", "")

        assert backend_cache != frontend_cache, (
            "Backend and frontend should not share cache refs"
        )
        assert "k9b-backend" in backend_cache, "Backend cache should reference k9b-backend"
        assert "k9b-frontend" in frontend_cache, "Frontend cache should reference k9b-frontend"


class TestOTelDemoLiveLabImageNames:
    """Tests for image/tag assertions in k9b-otel-demo-live-lab.yml."""

    def test_cache_uses_harbor_path(self) -> None:
        """Cache refs must use Harbor path."""
        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()

        assert "harbor-pve1.spbnix.local/k9b/cache/" in content, (
            "Workflow should use Harbor cache path"
        )

    def test_cache_ends_with_buildcache(self) -> None:
        """Cache refs must end with :buildcache."""
        import re

        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()

        # Find cache-from and cache-to in build section
        build_start = content.find("build-lab-images:")
        next_marker = content.find("\n  # ======", build_start)
        if next_marker == -1:
            next_marker = len(content)

        build_section = content[build_start:next_marker]

        # Extract the ref portion - ref comes before comma for mode= params
        # Format: type=registry,ref=<ref>,mode=max OR type=registry,ref=<ref>
        cache_from_match = re.search(r"cache-from:\s*type=registry,ref=([^,\n]+)", build_section)
        cache_to_match = re.search(r"cache-to:\s*type=registry,ref=([^,\n]+)", build_section)

        assert cache_from_match, f"Should have cache-from with ref, got section:\n{build_section[:500]}"
        assert cache_to_match, f"Should have cache-to with ref, got section:\n{build_section[:500]}"

        cache_from_ref = cache_from_match.group(1).strip()
        cache_to_ref = cache_to_match.group(1).strip()

        assert cache_from_ref.endswith(":buildcache"), (
            f"cache-from ref must end with :buildcache, got: {cache_from_ref}"
        )
        assert cache_to_ref.endswith(":buildcache"), (
            f"cache-to ref must end with :buildcache, got: {cache_to_ref}"
        )

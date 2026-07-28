"""Contract tests for harbor-build-image workflow Buildx rendering.

Tests Track B: Buildx authority rendering.
"""

import yaml
from typing import Any
from harbor_build_image_authority_support import HARBOR_BUILD_IMAGE_WORKFLOW


class TestBuildxRendering:
    """Tests for Buildx cache authority rendering."""

    def _get_build_push_step(self) -> Any:  
        """Get the build-push-action step."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)
        steps = workflow["jobs"]["build"]["steps"]
        for step in steps:
            if step.get("name") == "Build and push image":
                return step
        return None

    def test_build_push_uses_input_condition(self) -> None:
        """build-push-action push must use image_push_enabled input."""
        step = self._get_build_push_step()
        assert step is not None, "Build and push image step not found"

        # push is in the 'with' block
        with_block = step.get("with") or {}
        push_value = with_block.get("push")
        assert push_value is not None, "push must be configured"
        assert "image_push_enabled" in str(push_value), f"push must use image_push_enabled input, got: {push_value}"

    def test_cache_from_uses_input_condition(self) -> None:
        """cache-from must use registry_cache_read_enabled input."""
        step = self._get_build_push_step()
        assert step is not None

        with_block = step.get("with") or {}
        cache_from = with_block.get("cache-from") or ""
        # The cache-from expression includes registry_cache_read_enabled
        assert "registry_cache_read_enabled" in str(cache_from), f"cache-from must use registry_cache_read_enabled input, got: {cache_from}"

    def test_cache_to_uses_input_condition(self) -> None:
        """cache-to must use registry_cache_write_enabled input."""
        step = self._get_build_push_step()
        assert step is not None

        with_block = step.get("with") or {}
        cache_to = with_block.get("cache-to") or ""
        # The cache-to expression includes registry_cache_write_enabled
        assert "registry_cache_write_enabled" in str(cache_to), f"cache-to must use registry_cache_write_enabled input, got: {cache_to}"

    def test_no_unconditional_cache_to(self) -> None:
        """cache-to must NOT be unconditional true."""
        step = self._get_build_push_step()
        assert step is not None

        with_block = step.get("with") or {}
        cache_to = with_block.get("cache-to") or ""

        # Must not be a static unconditional value
        assert cache_to not in ("true", "True", True), "cache-to must not be unconditional true"

        # Must use the input condition
        assert "registry_cache_write_enabled" in str(cache_to), f"cache-to must be conditional on registry_cache_write_enabled, got: {cache_to}"

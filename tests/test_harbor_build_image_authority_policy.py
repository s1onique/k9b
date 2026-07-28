"""Contract tests for harbor-build-image workflow policy truth table.

Tests Track E: Authority policy truth table coverage.
"""

import yaml
from harbor_build_image_authority_support import HARBOR_WORKFLOW


class TestPolicyTruthTable:
    """Tests for authority policy truth table."""

    def _get_callers(self) -> list[tuple[str, dict]]:
        """Get all callers of harbor-build-image.yml."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        callers = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                callers.append((job_name, job_config))
        return callers

    def test_pr_event_image_push_false(self) -> None:
        """All callers must have image_push=false for PR (event expression)."""
        callers = self._get_callers()
        assert len(callers) > 0, "Must have at least one caller"

        for job_name, job_config in callers:
            with_block = job_config.get("with") or {}
            image_push = with_block.get("image_push_enabled")

            # Must use event expression (not hardcoded)
            assert image_push is not None, f"{job_name}: image_push_enabled must be set"
            assert "github.event_name" in str(image_push), f"{job_name}: image_push_enabled must use event expression, got: {image_push}"

    def test_pr_event_cache_write_false(self) -> None:
        """All callers must have cache_write=false for PR (event expression)."""
        callers = self._get_callers()

        for job_name, job_config in callers:
            with_block = job_config.get("with") or {}
            cache_write = with_block.get("registry_cache_write_enabled")

            assert cache_write is not None, f"{job_name}: registry_cache_write_enabled must be set"
            assert "github.event_name" in str(cache_write), f"{job_name}: registry_cache_write_enabled must use event expression, got: {cache_write}"

    def test_pr_event_cache_read_true(self) -> None:
        """All callers must have cache_read=true (always read cache)."""
        callers = self._get_callers()

        for job_name, job_config in callers:
            with_block = job_config.get("with") or {}
            cache_read = with_block.get("registry_cache_read_enabled")

            assert cache_read is not None, f"{job_name}: registry_cache_read_enabled must be set"
            # cache_read is always true for all callers
            assert cache_read is True, f"{job_name}: registry_cache_read_enabled must be true, got: {cache_read}"

    def test_trusted_push_all_write_true(self) -> None:
        """Trusted push callers must use event expression for write authorities."""
        callers = self._get_callers()

        for job_name, job_config in callers:
            with_block = job_config.get("with") or {}

            # All callers use event expression for write authorities
            image_push = with_block.get("image_push_enabled")
            cache_write = with_block.get("registry_cache_write_enabled")

            assert image_push is not None, f"{job_name}: image_push_enabled must be set"
            assert cache_write is not None, f"{job_name}: registry_cache_write_enabled must be set"

            # Both must use event expression (evaluates to true for non-PR)
            assert "github.event_name" in str(image_push), f"{job_name}: image_push_enabled must use event expression"
            assert "github.event_name" in str(cache_write), f"{job_name}: registry_cache_write_enabled must use event expression"

"""Contract tests for harbor-build-image workflow policy truth table.

Tests Track E: Authority policy truth table coverage.
CORRECTION07-B: Updated for split PR/trusted caller structure.
"""

import yaml
from harbor_build_image_authority_support import HARBOR_WORKFLOW


class TestPolicyTruthTable:
    """Tests for authority policy truth table."""

    def _get_pr_callers(self) -> list[tuple[str, dict]]:
        """Get PR callers of harbor-build-image.yml."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        callers = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                if job_name.endswith("-pr"):
                    callers.append((job_name, job_config))
        return callers

    def _get_trusted_callers(self) -> list[tuple[str, dict]]:
        """Get trusted publication callers of harbor-build-image.yml."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        callers = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                if "-publish" in job_name:
                    callers.append((job_name, job_config))
        return callers

    def test_pr_event_image_push_false(self) -> None:
        """PR callers must have image_push=false (hardcoded, correct for PR)."""
        callers = self._get_pr_callers()
        assert len(callers) > 0, "Must have at least one PR caller"

        for job_name, job_config in callers:
            with_block = job_config.get("with") or {}
            image_push = with_block.get("image_push_enabled")

            # PR callers must have image_push=false
            assert image_push is not None, f"{job_name}: image_push_enabled must be set"
            assert image_push is False, f"{job_name}: PR callers must have image_push_enabled=false, got: {image_push}"

    def test_pr_event_cache_write_false(self) -> None:
        """PR callers must have cache_write=false (hardcoded, correct for PR)."""
        callers = self._get_pr_callers()

        for job_name, job_config in callers:
            with_block = job_config.get("with") or {}
            cache_write = with_block.get("registry_cache_write_enabled")

            assert cache_write is not None, f"{job_name}: registry_cache_write_enabled must be set"
            assert cache_write is False, f"{job_name}: PR callers must have registry_cache_write_enabled=false, got: {cache_write}"

    def test_pr_event_cache_read_true(self) -> None:
        """PR callers must have cache_read=true (always read cache)."""
        callers = self._get_pr_callers()

        for job_name, job_config in callers:
            with_block = job_config.get("with") or {}
            cache_read = with_block.get("registry_cache_read_enabled")

            assert cache_read is not None, f"{job_name}: registry_cache_read_enabled must be set"
            assert cache_read is True, f"{job_name}: registry_cache_read_enabled must be true, got: {cache_read}"

    def test_trusted_push_all_write_true(self) -> None:
        """Trusted push callers must have all write authorities true."""
        callers = self._get_trusted_callers()
        assert len(callers) > 0, "Must have at least one trusted caller"

        for job_name, job_config in callers:
            with_block = job_config.get("with") or {}

            image_push = with_block.get("image_push_enabled")
            cache_write = with_block.get("registry_cache_write_enabled")
            cache_read = with_block.get("registry_cache_read_enabled")

            assert image_push is not None, f"{job_name}: image_push_enabled must be set"
            assert cache_write is not None, f"{job_name}: registry_cache_write_enabled must be set"
            assert cache_read is not None, f"{job_name}: registry_cache_read_enabled must be set"

            # Trusted callers have all authorities true
            assert image_push is True, f"{job_name}: trusted callers must have image_push_enabled=true, got: {image_push}"
            assert cache_write is True, f"{job_name}: trusted callers must have registry_cache_write_enabled=true, got: {cache_write}"
            assert cache_read is True, f"{job_name}: registry_cache_read_enabled must be true, got: {cache_read}"

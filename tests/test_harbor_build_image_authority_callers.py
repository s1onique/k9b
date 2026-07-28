"""Contract tests for harbor-build-image workflow caller authority matrix.

Tests Track C: Caller authority matrix coverage.
"""

import yaml
from harbor_build_image_authority_support import (
    HARBOR_BUILD_IMAGE_WORKFLOW,
    HARBOR_WORKFLOW,
    get_workflow_call_inputs,
)


class TestCallerAuthorityMatrix:
    """Tests for caller authority matrix."""

    def test_all_callers_supply_all_authorities(self) -> None:
        """Every caller must supply all required authority inputs."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            reusable = yaml.safe_load(f)

        inputs = get_workflow_call_inputs(reusable)
        required_inputs = [name for name, cfg in inputs.items() if isinstance(cfg, dict) and cfg.get("required") is True]

        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        callers = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                callers.append((job_name, job_config))

        assert len(callers) > 0, "Must have at least one harbor-build-image.yml caller"

        for job_name, job_config in callers:
            job_inputs = job_config.get("with") or {}
            for required_input in required_inputs:
                assert required_input in job_inputs, f"{job_name} must supply {required_input}"

    def test_pr_callers_use_read_only_matrix(self) -> None:
        """PR callers must use read-only authority matrix."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" not in job_config or "harbor-build-image.yml" not in job_config["uses"]:
                continue

            # PR callers must have image_push=false and cache_write=false
            with_block = job_config.get("with") or {}

            # For callers that are triggered by pull_request
            # Check the event mapping or assume PR context
            if "pull_request" in job_name.lower() or "pr" in job_name.lower():
                image_push = with_block.get("image_push_enabled")
                cache_write = with_block.get("registry_cache_write_enabled")

                assert image_push is False, f"{job_name}: image_push_enabled must be false for PR"
                assert cache_write is False, f"{job_name}: registry_cache_write_enabled must be false for PR"

    def test_login_condition_uses_authority_inputs(self) -> None:
        """Harbor login step must use authority inputs in condition."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        steps = workflow["jobs"]["build"]["steps"]
        login_step = None
        for step in steps:
            if step.get("name") == "Login to Harbor":
                login_step = step
                break

        assert login_step is not None, "Login to Harbor step not found"

        # Login must have condition using authority inputs
        condition = login_step.get("if")
        assert condition is not None, "Login step must have condition"
        assert "image_push_enabled" in str(condition) or "registry_cache_write_enabled" in str(condition), "Login condition must reference authority inputs"

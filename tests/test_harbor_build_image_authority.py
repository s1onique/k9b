"""Contract tests for harbor-build-image.yml workflow authority matrix.

These tests verify that ACT-K9B-IMAGE-BUILDER-REGISTRY-CACHE-AUTHORIZATION01
is correctly implemented:
- image_push_enabled controls application-image registry publication only
- registry_cache_read_enabled controls cache-from only
- registry_cache_write_enabled controls cache-to only

Authority matrix:
  pull_request:  image_push=false, cache_read=true, cache_write=false
  trusted push:  image_push=true,  cache_read=true, cache_write=true
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
HARBOR_BUILD_IMAGE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "harbor-build-image.yml"
HARBOR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "harbor.yml"


def load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow YAML file."""
    workflow: dict[str, Any] = yaml.safe_load(path.read_text())
    # YAML parses 'on:' as boolean True, so handle both cases
    # The YAML key 'on' becomes Python boolean True in the parsed dict
    workflow_any: dict[Any, Any] = workflow
    if True in workflow_any and "on" not in workflow_any:
        workflow_any["on"] = workflow_any.pop(True)
    return workflow


def get_workflow_call_inputs(workflow: dict[str, Any]) -> dict[str, Any]:
    """Get inputs from workflow_call trigger, handling YAML boolean parsing."""
    workflow_any: dict[Any, Any] = workflow
    on_block: Any = workflow_any.get("on")
    if on_block is None:
        on_block = workflow_any.get(True, {})
    if isinstance(on_block, dict):
        workflow_call: Any = on_block.get("workflow_call", {})
        if isinstance(workflow_call, dict):
            inputs: Any = workflow_call.get("inputs", {})
            if isinstance(inputs, dict):
                return inputs
    return {}


class TestHarborBuildImageInputs:
    """Tests that harbor-build-image.yml has the required authority inputs."""

    def test_workflow_file_exists(self) -> None:
        """The Harbor build image workflow file should exist."""
        assert HARBOR_BUILD_IMAGE_WORKFLOW.exists(), (
            f"Harbor build workflow not found at {HARBOR_BUILD_IMAGE_WORKFLOW}"
        )

    def test_has_image_push_enabled_input(self) -> None:
        """Workflow must have image_push_enabled input."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        inputs = get_workflow_call_inputs(workflow)
        assert "image_push_enabled" in inputs, (
            "harbor-build-image.yml must have image_push_enabled input"
        )

    def test_has_registry_cache_read_enabled_input(self) -> None:
        """Workflow must have registry_cache_read_enabled input."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        inputs = get_workflow_call_inputs(workflow)
        assert "registry_cache_read_enabled" in inputs, (
            "harbor-build-image.yml must have registry_cache_read_enabled input"
        )

    def test_has_registry_cache_write_enabled_input(self) -> None:
        """Workflow must have registry_cache_write_enabled input."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        inputs = get_workflow_call_inputs(workflow)
        assert "registry_cache_write_enabled" in inputs, (
            "harbor-build-image.yml must have registry_cache_write_enabled input"
        )

    def test_authority_inputs_are_boolean_type(self) -> None:
        """Authority inputs must be boolean type."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        inputs = get_workflow_call_inputs(workflow)

        for input_name in ["image_push_enabled", "registry_cache_read_enabled", "registry_cache_write_enabled"]:
            assert input_name in inputs, f"{input_name} must exist"
            assert inputs[input_name].get("type") == "boolean", (
                f"{input_name} must be boolean type"
            )

    def test_authority_inputs_have_descriptions(self) -> None:
        """Authority inputs must have descriptions."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        inputs = get_workflow_call_inputs(workflow)

        for input_name in ["image_push_enabled", "registry_cache_read_enabled", "registry_cache_write_enabled"]:
            assert input_name in inputs, f"{input_name} must exist"
            assert "description" in inputs[input_name], (
                f"{input_name} must have a description"
            )


class TestHarborBuildImageLoginCondition:
    """Tests that Harbor login is correctly conditioned on write authority."""

    def test_login_uses_input_condition(self) -> None:
        """Login step must use input conditions, not github.event_name."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()

        # Find the Login to Harbor step
        login_start = content.find("Login to Harbor")
        assert login_start != -1, "Must have 'Login to Harbor' step"

        # Extract the step block
        step_end = content.find("\n      - name:", login_start + 1)
        if step_end == -1:
            step_end = len(content)

        step_block = content[login_start:step_end]

        # The old pattern was: if: github.event_name != 'pull_request'
        # This must be replaced with input-based condition
        assert "github.event_name != 'pull_request'" not in step_block, (
            "Login step must NOT use github.event_name != 'pull_request'. "
            "Use inputs.image_push_enabled || inputs.registry_cache_write_enabled instead."
        )

        # Must use the input-based condition
        assert "inputs.image_push_enabled" in step_block or "inputs.registry_cache_write_enabled" in step_block, (
            "Login step must use inputs.image_push_enabled or inputs.registry_cache_write_enabled"
        )


class TestHarborBuildImageCacheConditioning:
    """Tests that cache-from and cache-to are correctly conditioned."""

    def test_cache_from_uses_input_condition(self) -> None:
        """cache-from must use registry_cache_read_enabled condition."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()

        # Find the Build and push image step
        build_start = content.find("Build and push image")
        assert build_start != -1, "Must have 'Build and push image' step"

        # Extract the step block
        step_end = content.find("\n      - name:", build_start + 1)
        if step_end == -1:
            step_end = len(content)

        step_block = content[build_start:step_end]

        # cache-from should use registry_cache_read_enabled
        assert "registry_cache_read_enabled" in step_block, (
            "cache-from must reference registry_cache_read_enabled"
        )

    def test_cache_to_uses_input_condition(self) -> None:
        """cache-to must use registry_cache_write_enabled condition."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()

        # Find the Build and push image step
        build_start = content.find("Build and push image")
        assert build_start != -1, "Must have 'Build and push image' step"

        # Extract the step block
        step_end = content.find("\n      - name:", build_start + 1)
        if step_end == -1:
            step_end = len(content)

        step_block = content[build_start:step_end]

        # cache-to should use registry_cache_write_enabled
        assert "registry_cache_write_enabled" in step_block, (
            "cache-to must reference registry_cache_write_enabled"
        )

    def test_no_unconditional_cache_to(self) -> None:
        """cache-to must NOT be unconditional (always present)."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()

        # Find the Build and push image step
        build_start = content.find("Build and push image")
        assert build_start != -1, "Must have 'Build and push image' step"

        # Extract the step block
        step_end = content.find("\n      - name:", build_start + 1)
        if step_end == -1:
            step_end = len(content)

        step_block = content[build_start:step_end]

        # Check that cache-to is conditional (not just a plain string)
        # The old pattern was: cache-to: type=registry,ref=...
        # This should be replaced with: cache-to: ${{ condition && format(...) || '' }}

        # If there's a literal cache-to: without expression, it must be conditional
        import re
        cache_to_literal = re.search(r"^\s*cache-to:\s*type=registry", step_block, re.MULTILINE)
        assert cache_to_literal is None, (
            "cache-to must NOT be unconditional. "
            "Use cache-to: ${{ inputs.registry_cache_write_enabled && format(...) || '' }}"
        )


class TestHarborWorkflowAuthorityInputs:
    """Tests that harbor.yml passes correct authority inputs based on event."""

    def test_harbor_workflow_file_exists(self) -> None:
        """The harbor.yml workflow file should exist."""
        assert HARBOR_WORKFLOW.exists(), (
            f"Harbor workflow not found at {HARBOR_WORKFLOW}"
        )

    def test_build_push_job_uses_event_condition_for_push(self) -> None:
        """build-push job must use github.event_name for authority inputs."""
        workflow = load_workflow(HARBOR_WORKFLOW)

        # Find build-push job
        build_push_job = workflow.get("jobs", {}).get("build-push", {})
        assert build_push_job, "harbor.yml must have build-push job"

        with_section = build_push_job.get("with", {})
        assert with_section, "build-push job must have 'with' section"

        # Check that image_push_enabled uses event condition
        assert "image_push_enabled" in with_section, (
            "build-push job must pass image_push_enabled"
        )
        image_push_expr = with_section["image_push_enabled"]
        assert "github.event_name" in image_push_expr, (
            "image_push_enabled must use github.event_name != 'pull_request'"
        )

    def test_frontend_job_uses_event_condition_for_push(self) -> None:
        """frontend job must use github.event_name for authority inputs."""
        workflow = load_workflow(HARBOR_WORKFLOW)

        # Find frontend job
        frontend_job = workflow.get("jobs", {}).get("frontend", {})
        assert frontend_job, "harbor.yml must have frontend job"

        with_section = frontend_job.get("with", {})
        assert with_section, "frontend job must have 'with' section"

        # Check that image_push_enabled uses event condition
        assert "image_push_enabled" in with_section, (
            "frontend job must pass image_push_enabled"
        )
        image_push_expr = with_section["image_push_enabled"]
        assert "github.event_name" in image_push_expr, (
            "image_push_enabled must use github.event_name != 'pull_request'"
        )

    def test_both_jobs_have_cache_write_disabled_for_pr(self) -> None:
        """Both jobs must disable cache_write for PRs."""
        workflow = load_workflow(HARBOR_WORKFLOW)

        for job_name in ["build-push", "frontend"]:
            job = workflow.get("jobs", {}).get(job_name, {})
            with_section = job.get("with", {})

            assert "registry_cache_write_enabled" in with_section, (
                f"{job_name} job must pass registry_cache_write_enabled"
            )
            cache_write_expr = with_section["registry_cache_write_enabled"]
            assert "github.event_name" in cache_write_expr, (
                f"{job_name} registry_cache_write_enabled must use github.event_name"
            )

    def test_both_jobs_have_cache_read_enabled(self) -> None:
        """Both jobs must enable cache_read for all builds."""
        workflow = load_workflow(HARBOR_WORKFLOW)

        for job_name in ["build-push", "frontend"]:
            job = workflow.get("jobs", {}).get(job_name, {})
            with_section = job.get("with", {})

            assert "registry_cache_read_enabled" in with_section, (
                f"{job_name} job must pass registry_cache_read_enabled"
            )
            # cache_read should be true (either literal or expression)
            cache_read_val = with_section["registry_cache_read_enabled"]
            assert cache_read_val is True or (
                isinstance(cache_read_val, str) and "true" in cache_read_val.lower()
            ), (
                f"{job_name} registry_cache_read_enabled should be true"
            )


class TestAuthorityPreflight:
    """Tests that authority preflight step exists and validates correctly."""

    def test_has_authority_preflight_step(self) -> None:
        """Workflow must have authority preflight step."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()
        assert "Authority preflight" in content, (
            "harbor-build-image.yml must have 'Authority preflight' step"
        )

    def test_preflight_validates_fork_pr_write_attempt(self) -> None:
        """Preflight must reject write operations on fork PRs."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()

        # Find the authority preflight step
        preflight_start = content.find("Authority preflight")
        assert preflight_start != -1, "Must have 'Authority preflight' step"

        # Extract the step block
        step_end = content.find("\n      # CA must be installed", preflight_start)
        if step_end == -1:
            step_end = content.find("\n      - name: Install SPbNIX", preflight_start)
        if step_end == -1:
            step_end = len(content)

        step_block = content[preflight_start:step_end]

        # Must check for fork PR
        assert "IS_FORK" in step_block or "fork" in step_block.lower(), (
            "Authority preflight must check for fork PRs"
        )

        # Must reject write operations on forks
        assert "ERROR" in step_block and (
            "Fork PR" in step_block or "fork" in step_block.lower()
        ), (
            "Authority preflight must reject write operations on fork PRs"
        )

    def test_preflight_checks_credential_availability(self) -> None:
        """Preflight must check credential availability when write is required."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()

        # Find the authority preflight step
        preflight_start = content.find("Authority preflight")
        assert preflight_start != -1, "Must have 'Authority preflight' step"

        # Extract the step block
        step_end = content.find("\n      # CA must be installed", preflight_start)
        if step_end == -1:
            step_end = content.find("\n      - name: Install SPbNIX", preflight_start)
        if step_end == -1:
            step_end = len(content)

        step_block = content[preflight_start:step_end]

        # Must check for Harbor credentials
        assert "HARBOR_USERNAME" in step_block or "secrets.HARBOR" in step_block, (
            "Authority preflight must check Harbor credentials"
        )

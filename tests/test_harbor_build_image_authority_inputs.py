"""Contract tests for harbor-build-image workflow authority inputs.

Tests Track A: Authority inputs explicit and fail-closed defaults.
"""

import yaml
from harbor_build_image_authority_support import (
    HARBOR_BUILD_IMAGE_WORKFLOW,
    get_workflow_call_inputs,
)


class TestHarborBuildImageInputs:
    """Tests for explicit authority inputs with fail-closed defaults."""

    def test_workflow_file_exists(self) -> None:
        """Workflow file must exist."""
        assert HARBOR_BUILD_IMAGE_WORKFLOW.exists(), f"Workflow file {HARBOR_BUILD_IMAGE_WORKFLOW} does not exist"

    def test_all_authority_inputs_are_required(self) -> None:
        """All three authority inputs must be required (no defaults for write ops)."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        inputs = get_workflow_call_inputs(workflow)

        # image_push_enabled must be required
        assert "image_push_enabled" in inputs, "image_push_enabled input missing"
        assert inputs["image_push_enabled"].get("required") is True, "image_push_enabled must be required"

        # registry_cache_read_enabled must be required
        assert "registry_cache_read_enabled" in inputs, "registry_cache_read_enabled input missing"
        assert inputs["registry_cache_read_enabled"].get("required") is True, "registry_cache_read_enabled must be required"

        # registry_cache_write_enabled must be required
        assert "registry_cache_write_enabled" in inputs, "registry_cache_write_enabled input missing"
        assert inputs["registry_cache_write_enabled"].get("required") is True, "registry_cache_write_enabled must be required"

    def test_no_write_enabled_defaults(self) -> None:
        """Write authorities must NOT have default: true."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        inputs = get_workflow_call_inputs(workflow)

        # image_push_enabled must NOT have default: true
        image_push_default = inputs["image_push_enabled"].get("default")
        assert image_push_default is not True, "image_push_enabled must NOT have default: true (fail-closed)"

        # registry_cache_write_enabled must NOT have default: true
        cache_write_default = inputs["registry_cache_write_enabled"].get("default")
        assert cache_write_default is not True, "registry_cache_write_enabled must NOT have default: true (fail-closed)"

    def test_authority_inputs_are_boolean_type(self) -> None:
        """Authority inputs must be boolean type."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        inputs = get_workflow_call_inputs(workflow)

        assert inputs["image_push_enabled"]["type"] == "boolean"
        assert inputs["registry_cache_read_enabled"]["type"] == "boolean"
        assert inputs["registry_cache_write_enabled"]["type"] == "boolean"

    def test_authority_inputs_have_descriptions(self) -> None:
        """Authority inputs must have descriptions explaining their purpose."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        inputs = get_workflow_call_inputs(workflow)

        assert "description" in inputs["image_push_enabled"]
        assert "description" in inputs["registry_cache_read_enabled"]
        assert "description" in inputs["registry_cache_write_enabled"]

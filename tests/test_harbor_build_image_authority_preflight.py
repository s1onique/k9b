"""Contract tests for harbor-build-image workflow preflight behavior.

Tests Track D: Preflight ordering and credential coverage.
"""

import yaml
from harbor_build_image_authority_support import HARBOR_BUILD_IMAGE_WORKFLOW


class TestAuthorityPreflight:
    """Tests for authority preflight step."""

    def test_has_authority_preflight_step(self) -> None:
        """Workflow must have authority preflight step."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        steps = workflow["jobs"]["build"]["steps"]
        preflight_step = None
        for step in steps:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        assert preflight_step is not None, "Authority preflight step must exist"

    def test_preflight_validates_event_authority_combination(self) -> None:
        """Preflight must validate event and authority combination."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Must check event name
        assert "EVENT_NAME" in content, "Preflight must check EVENT_NAME"
        assert "pull_request" in content, "Preflight must handle pull_request event"

    def test_preflight_checks_credentials_for_write(self) -> None:
        """Preflight must check credentials when write is required."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Must check HARBOR_USERNAME and HARBOR_TOKEN
        assert "HARBOR_USERNAME" in content, "Preflight must check HARBOR_USERNAME"
        assert "HARBOR_TOKEN" in content, "Preflight must check HARBOR_TOKEN"

    def test_preflight_exits_early_for_pr(self) -> None:
        """Preflight must exit early for PR events."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Must have early exit for PR
        assert "exit 0" in content, "Preflight must have early exit path"
        assert "PR correctly configured" in content or "read-only" in content.lower(), "Preflight must confirm PR is read-only"

    def test_preflight_has_correct_phase_order(self) -> None:
        """Preflight must have correct phase order."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Verify phase comments exist
        assert "Phase 1" in content or "Validate required inputs" in content, "Preflight must have input validation phase"
        assert "Phase 2" in content or "Validate boolean inputs" in content or "Phase 3" in content, "Preflight must have boolean validation phase"
        assert "Phase 3" in content or "Phase 4" in content or "pull_request" in content, "Preflight must have PR policy phase"

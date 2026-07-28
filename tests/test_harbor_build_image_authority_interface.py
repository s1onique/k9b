"""Contract tests for harbor-build-image workflow caller/callee interface.

Tests Track C: Secret boundary narrowing.
"""

import re

import yaml
from harbor_build_image_authority_support import (
    HARBOR_BUILD_IMAGE_WORKFLOW,
    HARBOR_WORKFLOW,
)


class TestSecretBoundary:
    """Tests for narrowed secret boundary."""

    def test_no_secrets_inherit_in_callers(self) -> None:
        """Callers must NOT use secrets: inherit as a value."""
        with open(HARBOR_WORKFLOW) as f:
            content = f.read()

        pattern = r"^    secrets: inherit$"
        match = re.search(pattern, content, re.MULTILINE)
        assert match is None, "secrets: inherit is forbidden - use explicit secrets mapping"

    def test_only_harbor_secrets_passed(self) -> None:
        """Only Harbor username and token secrets are passed."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        calls = []
        jobs = workflow.get("jobs") or {}
        for job_name, job_config in jobs.items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                calls.append((job_name, job_config))

        assert len(calls) > 0, "Must have at least one harbor-build-image.yml call"

        for job_name, job_config in calls:
            assert "secrets" in job_config, f"{job_name} must specify secrets"

            secrets = job_config["secrets"]

            # Must have HARBOR_USERNAME
            assert "HARBOR_USERNAME" in secrets, f"{job_name} must pass HARBOR_USERNAME"

            # Must have HARBOR_TOKEN
            assert "HARBOR_TOKEN" in secrets, f"{job_name} must pass HARBOR_TOKEN"

            # Must NOT have secrets: inherit
            assert secrets != "inherit", f"{job_name} must not use secrets: inherit"

    def test_harbor_username_mapped_correctly(self) -> None:
        """HARBOR_USERNAME must be mapped from repository secrets."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                secrets = job_config.get("secrets", {})
                if "HARBOR_USERNAME" in secrets:
                    value = secrets["HARBOR_USERNAME"]
                    assert "secrets.HARBOR_USERNAME" in value, f"{job_name} HARBOR_USERNAME must map from repository secrets"

    def test_harbor_token_mapped_correctly(self) -> None:
        """HARBOR_TOKEN must be mapped from repository secrets."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                secrets = job_config.get("secrets", {})
                if "HARBOR_TOKEN" in secrets:
                    value = secrets["HARBOR_TOKEN"]
                    assert "secrets.HARBOR_TOKEN" in value, f"{job_name} HARBOR_TOKEN must map from repository secrets"


class TestMissingSecretRegression:
    """Regression tests for missing secret interface parity."""

    def test_no_required_secrets_missing_from_callers(self) -> None:
        """Verify no required secrets are missing from callers."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            reusable = yaml.safe_load(f)

        # Get reusable workflow_call secrets
        on = reusable.get("on") or {}
        wc = on.get("workflow_call") if isinstance(on, dict) else {}
        reusable_secrets = (wc.get("secrets") or {}) if isinstance(wc, dict) else {}
        required_secrets = {name: cfg for name, cfg in reusable_secrets.items() if isinstance(cfg, dict) and cfg.get("required") is True}

        # Find all callers
        callers = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                callers.append((job_name, job_config))

        assert len(callers) > 0, "Must have at least one harbor-build-image.yml caller"

        missing = []
        for job_name, job_config in callers:
            caller_secrets = job_config.get("secrets") or {}
            for secret_name in required_secrets:
                if secret_name not in caller_secrets:
                    missing.append(f"{job_name}: missing required secret '{secret_name}'")

        assert len(missing) == 0, "Required secrets missing from callers:\n" + "\n".join(missing)

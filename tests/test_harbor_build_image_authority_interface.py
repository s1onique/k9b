"""Contract tests for harbor-build-image workflow caller/callee interface.

Tests Track C: Secret boundary narrowing.
CORRECTION07-B: Updated for split PR/trusted caller structure.
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

    def test_pr_callers_receive_only_ca_secret(self) -> None:
        """PR callers must receive only SPBNIX_CA_CERT_PEM, no Harbor auth."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        pr_calls = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                # PR callers end with -pr
                if job_name.endswith("-pr"):
                    pr_calls.append((job_name, job_config))

        assert len(pr_calls) > 0, "Must have at least one PR harbor-build-image.yml call"

        for job_name, job_config in pr_calls:
            secrets = job_config.get("secrets") or {}

            # PR callers MUST have CA secret
            assert "SPBNIX_CA_CERT_PEM" in secrets, f"{job_name} must pass SPBNIX_CA_CERT_PEM"
            assert "secrets.SPBNIX_CA_CERT_PEM" in secrets["SPBNIX_CA_CERT_PEM"], \
                f"{job_name} SPBNIX_CA_CERT_PEM must map from repository secrets"

            # PR callers MUST NOT have Harbor auth credentials
            assert "HARBOR_USERNAME" not in secrets, \
                f"{job_name} must NOT pass HARBOR_USERNAME (PR callers are read-only)"
            assert "HARBOR_TOKEN" not in secrets, \
                f"{job_name} must NOT pass HARBOR_TOKEN (PR callers are read-only)"

    def test_trusted_callers_receive_all_credentials(self) -> None:
        """Trusted publication callers must receive CA and Harbor auth."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        trusted_calls = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                # Trusted callers end with -publish
                if "-publish" in job_name:
                    trusted_calls.append((job_name, job_config))

        assert len(trusted_calls) > 0, "Must have at least one trusted harbor-build-image.yml call"

        for job_name, job_config in trusted_calls:
            secrets = job_config.get("secrets") or {}

            # Trusted callers MUST have all three credentials
            assert "SPBNIX_CA_CERT_PEM" in secrets, f"{job_name} must pass SPBNIX_CA_CERT_PEM"
            assert "HARBOR_USERNAME" in secrets, f"{job_name} must pass HARBOR_USERNAME"
            assert "HARBOR_TOKEN" in secrets, f"{job_name} must pass HARBOR_TOKEN"

            # Verify mapping
            assert "secrets.SPBNIX_CA_CERT_PEM" in secrets["SPBNIX_CA_CERT_PEM"], \
                f"{job_name} SPBNIX_CA_CERT_PEM must map from repository secrets"
            assert "secrets.HARBOR_USERNAME" in secrets["HARBOR_USERNAME"], \
                f"{job_name} HARBOR_USERNAME must map from repository secrets"
            assert "secrets.HARBOR_TOKEN" in secrets["HARBOR_TOKEN"], \
                f"{job_name} HARBOR_TOKEN must map from repository secrets"

    def test_harbor_username_mapped_correctly(self) -> None:
        """HARBOR_USERNAME must be mapped from repository secrets when present."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                secrets = job_config.get("secrets", {})
                if "HARBOR_USERNAME" in secrets:
                    value = secrets["HARBOR_USERNAME"]
                    assert "secrets.HARBOR_USERNAME" in value, \
                        f"{job_name} HARBOR_USERNAME must map from repository secrets"

    def test_harbor_token_mapped_correctly(self) -> None:
        """HARBOR_TOKEN must be mapped from repository secrets when present."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                secrets = job_config.get("secrets", {})
                if "HARBOR_TOKEN" in secrets:
                    value = secrets["HARBOR_TOKEN"]
                    assert "secrets.HARBOR_TOKEN" in value, \
                        f"{job_name} HARBOR_TOKEN must map from repository secrets"


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
        required_secrets = {
            name: cfg for name, cfg in reusable_secrets.items()
            if isinstance(cfg, dict) and cfg.get("required") is True
        }

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

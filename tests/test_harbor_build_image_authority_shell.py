"""Contract tests for harbor-build-image workflow shell safety.

Tests Track D: Shell safety - env transfer instead of inline interpolation.
"""

import pytest
import yaml


class TestShellSafety:
    """Tests for shell safety - env transfer pattern."""

    def test_preflight_uses_env_block(self) -> None:
        """Preflight must use env block for external values."""
        with open(".github/workflows/harbor-build-image.yml") as f:
            workflow = yaml.safe_load(f)

        preflight_step: dict | None = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        assert preflight_step is not None, "Authority preflight step not found"
        assert "env" in preflight_step, "Preflight must have env block"

    def test_preflight_env_contains_all_inputs(self) -> None:
        """Preflight env block must contain all input values."""
        with open(".github/workflows/harbor-build-image.yml") as f:
            workflow = yaml.safe_load(f)

        preflight_step: dict | None = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        assert preflight_step is not None
        env: dict = preflight_step.get("env") or {}

        assert "EVENT_NAME" in env, "EVENT_NAME must be in env"
        assert "ACTOR" in env, "ACTOR must be in env"
        assert "REPOSITORY" in env, "REPOSITORY must be in env"
        assert "REGISTRY" in env, "REGISTRY must be in env"
        assert "HARBOR_PROJECT" in env, "HARBOR_PROJECT must be in env"
        assert "IMAGE_NAME" in env, "IMAGE_NAME must be in env"
        assert "IMAGE_PUSH_ENABLED" in env, "IMAGE_PUSH_ENABLED must be in env"
        assert "CACHE_READ_ENABLED" in env, "CACHE_READ_ENABLED must be in env"
        assert "CACHE_WRITE_ENABLED" in env, "CACHE_WRITE_ENABLED must be in env"

    def test_preflight_uses_env_variables_not_direct_interpolation(self) -> None:
        """Preflight run body must use env variables, not direct interpolation."""
        with open(".github/workflows/harbor-build-image.yml") as f:
            workflow = yaml.safe_load(f)

        preflight_step: dict | None = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        assert preflight_step is not None
        run_body: str = preflight_step.get("run") or ""

        lines = run_body.split("\n")
        for line in lines:
            if line.strip().startswith("#"):
                continue
            if "echo" in line and ("inputs." in line or "github." in line or "secrets." in line):
                continue
            if "${{" in line and "env:" not in line:
                pytest.fail(f"Forbidden direct interpolation in shell: {line.strip()[:80]}")

    def test_preflight_does_not_print_credentials(self) -> None:
        """Preflight must not print credential values."""
        with open(".github/workflows/harbor-build-image.yml") as f:
            workflow = yaml.safe_load(f)

        preflight_step: dict | None = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        assert preflight_step is not None
        run_body: str = preflight_step.get("run") or ""

        assert 'echo "${HARBOR_USERNAME}"' not in run_body, "Must not echo HARBOR_USERNAME"
        assert 'echo "${HARBOR_TOKEN}"' not in run_body, "Must not echo HARBOR_TOKEN"

"""Tests for diagnosis provider Helm chart configuration.

These tests verify:
- Provider is disabled by default (no env vars rendered)
- secretKeyRef is only included when enabled
- All required env vars are set when enabled

Uses `helm template` for rendering (subprocess, no SDK dependency).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest


def render_deployment(values: dict[str, Any]) -> dict[str, Any]:
    """Render the backend deployment using `helm template`.

    Args:
        values: Helm values dict

    Returns:
        Parsed deployment YAML as dict

    Raises:
        RuntimeError: If helm template fails
    """
    chart_path = Path(__file__).resolve().parents[1] / "charts" / "k9b"

    # Write values to temp file
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        json.dump(values, f)
        values_file = f.name

    try:
        result = subprocess.run(
            [
                "helm",
                "template",
                "k9b",
                str(chart_path),
                "--show-only",
                "templates/deployment.yaml",
                "-f",
                values_file,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"helm template failed: {exc.stderr}"
        ) from exc
    finally:
        Path(values_file).unlink(missing_ok=True)

    # Parse YAML output
    import yaml

    docs: list[Any] = list(yaml.safe_load_all(result.stdout))
    if not docs:
        raise RuntimeError("helm template produced no YAML documents")
    return dict(docs[0])


def get_backend_env(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract backend container env vars from deployment."""
    containers: list[dict[str, Any]] = deployment["spec"]["template"]["spec"]["containers"]
    backend: dict[str, Any] = next((c for c in containers if c["name"] == "backend"), {})
    if not backend:
        return []
    env = backend.get("env")
    return env if env is not None else []


def env_var_names(env: list[dict[str, Any]]) -> set[str]:
    """Extract env var names from env list."""
    return {e["name"] for e in env}


def get_env_var(env: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Get env var by name."""
    for e in env:
        if e.get("name") == name:
            return e
    return None


class TestDiagnosisProviderDisabledByDefault:
    """When diagnosisProvider.enabled=false (default), no provider env vars are rendered."""

    def test_no_diagnosis_env_vars_when_disabled(self) -> None:
        """No diagnosis env vars when provider is disabled."""
        deployment = render_deployment({})
        env = get_backend_env(deployment)
        names = env_var_names(env)

        assert "K9B_DIAGNOSIS_PROVIDER_NAME" not in names
        assert "K9B_DIAGNOSIS_MODEL" not in names
        assert "K9B_DIAGNOSIS_BASE_URL" not in names
        assert "K9B_DIAGNOSIS_API_KEY" not in names
        assert "K9B_DIAGNOSIS_TIMEOUT_SECONDS" not in names
        assert "K9B_DIAGNOSIS_MAX_OUTPUT_CHARS" not in names

    def test_no_secret_key_ref_when_disabled(self) -> None:
        """No secretKeyRef for API key when provider is disabled."""
        deployment = render_deployment({})
        env = get_backend_env(deployment)

        for e in env:
            if e.get("name") == "K9B_DIAGNOSIS_API_KEY":
                pytest.fail("K9B_DIAGNOSIS_API_KEY should not be present when disabled")


class TestDiagnosisProviderEnabled:
    """When diagnosisProvider.enabled=true, all required env vars are rendered."""

    @pytest.fixture
    def enabled_values(self) -> dict[str, Any]:
        """Values with provider enabled."""
        return {
            "diagnosisProvider": {
                "enabled": True,
                "provider": "openai_compatible",
                "baseUrl": "http://llm-service:8080/v1",
                "model": "qwen/qwen2.5-7b-instruct",
                "existingSecret": "k9b-diagnosis-credentials",
                "apiKeyKey": "K9B_DIAGNOSIS_API_KEY",
                "timeoutSeconds": 120,
                "maxOutputChars": 8000,
            }
        }

    def test_all_required_env_vars_present(self, enabled_values: dict[str, Any]) -> None:
        """All required diagnosis env vars are rendered when enabled."""
        deployment = render_deployment(enabled_values)
        env = get_backend_env(deployment)
        names = env_var_names(env)

        assert "K9B_DIAGNOSIS_PROVIDER_NAME" in names
        assert "K9B_DIAGNOSIS_MODEL" in names
        assert "K9B_DIAGNOSIS_BASE_URL" in names
        assert "K9B_DIAGNOSIS_TIMEOUT_SECONDS" in names
        assert "K9B_DIAGNOSIS_MAX_OUTPUT_CHARS" in names

    def test_provider_name_value(self, enabled_values: dict[str, Any]) -> None:
        """Provider name env var has correct value."""
        deployment = render_deployment(enabled_values)
        env = get_backend_env(deployment)

        e = get_env_var(env, "K9B_DIAGNOSIS_PROVIDER_NAME")
        assert e is not None
        assert e.get("value") == "openai_compatible"

    def test_base_url_value(self, enabled_values: dict[str, Any]) -> None:
        """Base URL env var has correct value."""
        deployment = render_deployment(enabled_values)
        env = get_backend_env(deployment)

        e = get_env_var(env, "K9B_DIAGNOSIS_BASE_URL")
        assert e is not None
        assert e.get("value") == "http://llm-service:8080/v1"

    def test_model_value(self, enabled_values: dict[str, Any]) -> None:
        """Model env var has correct value."""
        deployment = render_deployment(enabled_values)
        env = get_backend_env(deployment)

        e = get_env_var(env, "K9B_DIAGNOSIS_MODEL")
        assert e is not None
        assert e.get("value") == "qwen/qwen2.5-7b-instruct"

    def test_timeout_value(self, enabled_values: dict[str, Any]) -> None:
        """Timeout env var has correct value."""
        deployment = render_deployment(enabled_values)
        env = get_backend_env(deployment)

        e = get_env_var(env, "K9B_DIAGNOSIS_TIMEOUT_SECONDS")
        assert e is not None
        assert e.get("value") == "120"

    def test_max_output_chars_value(self, enabled_values: dict[str, Any]) -> None:
        """Max output chars env var has correct value."""
        deployment = render_deployment(enabled_values)
        env = get_backend_env(deployment)

        e = get_env_var(env, "K9B_DIAGNOSIS_MAX_OUTPUT_CHARS")
        assert e is not None
        assert e.get("value") == "8000"

    def test_api_key_uses_secret_key_ref(self, enabled_values: dict[str, Any]) -> None:
        """API key env var uses secretKeyRef when secret is configured."""
        deployment = render_deployment(enabled_values)
        env = get_backend_env(deployment)

        e = get_env_var(env, "K9B_DIAGNOSIS_API_KEY")
        assert e is not None
        assert "valueFrom" in e
        assert "secretKeyRef" in e["valueFrom"]
        assert e["valueFrom"]["secretKeyRef"]["name"] == "k9b-diagnosis-credentials"
        assert e["valueFrom"]["secretKeyRef"]["key"] == "K9B_DIAGNOSIS_API_KEY"

    def test_api_key_not_value_when_secret_configured(self, enabled_values: dict[str, Any]) -> None:
        """API key env var has no value when secret is configured."""
        deployment = render_deployment(enabled_values)
        env = get_backend_env(deployment)

        e = get_env_var(env, "K9B_DIAGNOSIS_API_KEY")
        assert e is not None
        # When using secretKeyRef, value should NOT be present
        assert "value" not in e

    def test_api_key_absent_when_no_secret(self) -> None:
        """API key env var is not rendered when no secret is configured."""
        values = {
            "diagnosisProvider": {
                "enabled": True,
                "provider": "openai_compatible",
                "baseUrl": "http://llm-service:8080/v1",
                "model": "qwen/qwen2.5-7b-instruct",
                # No existingSecret
                "timeoutSeconds": 120,
                "maxOutputChars": 8000,
            }
        }
        deployment = render_deployment(values)
        env = get_backend_env(deployment)

        assert get_env_var(env, "K9B_DIAGNOSIS_API_KEY") is None


class TestDiagnosisProviderSecretKeyRefRawValue:
    """Verify secretKeyRef injects raw secret value into env var."""

    def test_secret_key_ref_injects_raw_value(self) -> None:
        """secretKeyRef makes K8s inject the raw secret value into the env var.

        This confirms the deployment.yaml contract: when using secretKeyRef,
        the env var K9B_DIAGNOSIS_API_KEY will contain the raw API key value
        (not an env var name reference), matching DiagnosisProviderConfig.from_env()
        expectation.
        """
        values = {
            "diagnosisProvider": {
                "enabled": True,
                "provider": "openai_compatible",
                "baseUrl": "http://llm-service:8080/v1",
                "model": "qwen/qwen2.5-7b-instruct",
                "existingSecret": "k9b-diagnosis-credentials",
                "apiKeyKey": "K9B_DIAGNOSIS_API_KEY",
            }
        }
        deployment = render_deployment(values)
        env = get_backend_env(deployment)

        e = get_env_var(env, "K9B_DIAGNOSIS_API_KEY")
        assert e is not None

        # secretKeyRef means Kubernetes will inject the raw Secret value
        # into this env var at pod startup. This is the expected behavior
        # for Helm chart integration with DiagnosisProviderConfig.
        assert "valueFrom" in e
        assert e["valueFrom"]["secretKeyRef"]["name"] == "k9b-diagnosis-credentials"


# Small provider tests are in tests/test_helm_small_provider.py

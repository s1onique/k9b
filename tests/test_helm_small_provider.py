"""Tests for small provider (scheduler) Helm chart configuration.

These tests verify:
- Small provider API key is disabled by default (no env var rendered)
- secretKeyRef is used when smallProvider.existingSecret is set
- Both diagnosisProvider and smallProvider can share the same Kubernetes Secret

Uses `helm template` for rendering (subprocess, no SDK dependency).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest


def render_scheduler_deployment(values: dict[str, Any]) -> dict[str, Any]:
    """Render the scheduler deployment using `helm template`.

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
                "templates/deployment-scheduler.yaml",
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


def render_backend_deployment(values: dict[str, Any]) -> dict[str, Any]:
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


def get_scheduler_env(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract scheduler container env vars from deployment."""
    containers: list[dict[str, Any]] = deployment["spec"]["template"]["spec"]["containers"]
    scheduler: dict[str, Any] = next((c for c in containers if c["name"] == "scheduler"), {})
    if not scheduler:
        return []
    env = scheduler.get("env")
    return env if env is not None else []


def get_backend_env(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract backend container env vars from deployment."""
    containers: list[dict[str, Any]] = deployment["spec"]["template"]["spec"]["containers"]
    backend: dict[str, Any] = next((c for c in containers if c["name"] == "backend"), {})
    if not backend:
        return []
    env = backend.get("env")
    return env if env is not None else []


def get_env_var(env: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Get env var by name."""
    for e in env:
        if e.get("name") == name:
            return e
    return None


class TestSmallProviderDisabledByDefault:
    """When scheduler.smallProvider.existingSecret is not set, no API key env var is rendered."""

    def test_no_small_provider_api_key_when_not_configured(self) -> None:
        """No K9B_EXTERNAL_ANALYSIS_API_KEY when smallProvider.existingSecret is not set."""
        deployment = render_scheduler_deployment({})
        env = get_scheduler_env(deployment)

        for e in env:
            if e.get("name") == "K9B_EXTERNAL_ANALYSIS_API_KEY":
                pytest.fail("K9B_EXTERNAL_ANALYSIS_API_KEY should not be present when no secret configured")


class TestSmallProviderWithSecret:
    """When scheduler.smallProvider.existingSecret is set, secretKeyRef is used."""

    def test_small_provider_api_key_uses_secret_key_ref(self) -> None:
        """API key env var uses secretKeyRef when smallProvider.existingSecret is configured."""
        values = {
            "scheduler": {
                "smallProvider": {
                    "existingSecret": "k9b-diagnosis-credentials",
                    "apiKeyKey": "K9B_EXTERNAL_ANALYSIS_API_KEY",
                }
            }
        }
        deployment = render_scheduler_deployment(values)
        env = get_scheduler_env(deployment)

        e = get_env_var(env, "K9B_EXTERNAL_ANALYSIS_API_KEY")
        assert e is not None
        assert "valueFrom" in e
        assert "secretKeyRef" in e["valueFrom"]
        assert e["valueFrom"]["secretKeyRef"]["name"] == "k9b-diagnosis-credentials"
        assert e["valueFrom"]["secretKeyRef"]["key"] == "K9B_EXTERNAL_ANALYSIS_API_KEY"

    def test_small_provider_api_key_no_value_when_secret_configured(self) -> None:
        """API key env var has no value when secret is configured (only secretKeyRef)."""
        values = {
            "scheduler": {
                "smallProvider": {
                    "existingSecret": "k9b-diagnosis-credentials",
                    "apiKeyKey": "K9B_EXTERNAL_ANALYSIS_API_KEY",
                }
            }
        }
        deployment = render_scheduler_deployment(values)
        env = get_scheduler_env(deployment)

        e = get_env_var(env, "K9B_EXTERNAL_ANALYSIS_API_KEY")
        assert e is not None
        # When using secretKeyRef, value should NOT be present
        assert "value" not in e


class TestSharedCredentialBundle:
    """Both diagnosisProvider and smallProvider can use the same Kubernetes Secret.

    This tests the shared credential bundle pattern:
    - diagnosisProvider uses K9B_DIAGNOSIS_API_KEY from k9b-diagnosis-credentials
    - smallProvider uses K9B_EXTERNAL_ANALYSIS_API_KEY from the same secret
    """

    def test_both_providers_use_same_secret_name(self) -> None:
        """Both providers can reference the same secret for different keys."""
        values = {
            "diagnosisProvider": {
                "enabled": True,
                "provider": "openai_compatible",
                "baseUrl": "http://llm-service:8080/v1",
                "model": "qwen/qwen2.5-7b-instruct",
                "existingSecret": "k9b-diagnosis-credentials",
                "apiKeyKey": "K9B_DIAGNOSIS_API_KEY",
            },
            "scheduler": {
                "smallProvider": {
                    "existingSecret": "k9b-diagnosis-credentials",
                    "apiKeyKey": "K9B_EXTERNAL_ANALYSIS_API_KEY",
                }
            },
        }

        # Render both deployments
        backend_deployment = render_backend_deployment(values)
        scheduler_deployment = render_scheduler_deployment(values)

        backend_env = get_backend_env(backend_deployment)
        scheduler_env = get_scheduler_env(scheduler_deployment)

        # Backend uses K9B_DIAGNOSIS_API_KEY
        backend_key = get_env_var(backend_env, "K9B_DIAGNOSIS_API_KEY")
        assert backend_key is not None
        assert backend_key["valueFrom"]["secretKeyRef"]["name"] == "k9b-diagnosis-credentials"
        assert backend_key["valueFrom"]["secretKeyRef"]["key"] == "K9B_DIAGNOSIS_API_KEY"

        # Scheduler uses K9B_EXTERNAL_ANALYSIS_API_KEY
        scheduler_key = get_env_var(scheduler_env, "K9B_EXTERNAL_ANALYSIS_API_KEY")
        assert scheduler_key is not None
        assert scheduler_key["valueFrom"]["secretKeyRef"]["name"] == "k9b-diagnosis-credentials"
        assert scheduler_key["valueFrom"]["secretKeyRef"]["key"] == "K9B_EXTERNAL_ANALYSIS_API_KEY"

    def test_no_raw_api_keys_in_rendered_yaml(self) -> None:
        """Verify no raw API key values appear in rendered YAML."""
        values = {
            "diagnosisProvider": {
                "enabled": True,
                "provider": "openai_compatible",
                "baseUrl": "http://llm-service:8080/v1",
                "model": "qwen/qwen2.5-7b-instruct",
                "existingSecret": "k9b-diagnosis-credentials",
                "apiKeyKey": "K9B_DIAGNOSIS_API_KEY",
            },
            "scheduler": {
                "smallProvider": {
                    "existingSecret": "k9b-diagnosis-credentials",
                    "apiKeyKey": "K9B_EXTERNAL_ANALYSIS_API_KEY",
                }
            },
        }

        # Render both deployments and check rendered YAML
        import tempfile
        chart_path = Path(__file__).resolve().parents[1] / "charts" / "k9b"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            json.dump(values, f)
            values_file = f.name

        try:
            result = subprocess.run(
                [
                    "helm",
                    "template",
                    "k9b",
                    str(chart_path),
                    "-f",
                    values_file,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        finally:
            Path(values_file).unlink(missing_ok=True)

        # Check that no raw API key values appear
        # (they should only appear in secretKeyRef, not in env var values)
        forbidden_patterns = [
            "k9b_diagnosis_api_key:",
            "k9b_external_analysis_api_key:",
            "secretkeyref",
        ]

        for pattern in forbidden_patterns:
            # The pattern should only appear in context of secretKeyRef (which is OK)
            # It should NOT appear as "value: <raw-key>"
            lines = result.stdout.split("\n")
            for line in lines:
                if "value:" in line.lower() and pattern.replace("-", "_") in line.lower():
                    # This would be a raw key value - check it's not an actual key
                    if "sk-" in line or "api-" in line or "secret" in line:
                        pytest.fail(f"Raw API key value found in rendered YAML: {line.strip()}")

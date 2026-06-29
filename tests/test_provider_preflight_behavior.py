# Copyright (c) 2025 Artem Chistyakov
# SPDX-License-Identifier: MIT

"""Behavioral regression tests for provider preflight.

These tests mock the _curl_service_pod function to test the behavioral contract
of run_provider_preflight() without duplicating the parsing logic. This ensures
the preflight behavior can evolve independently of the underlying parser.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


class TestProviderPreflightBehavior:
    """Behavioral tests for provider preflight using mocked curl."""

    @pytest.fixture
    def temp_artifact_dir(self) -> Iterator[Path]:
        """Create a temporary artifact directory."""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def _mock_curl_success(self, healthy_provider_response: dict) -> tuple[bool, str, int]:
        """Return a successful health response with provider available."""
        return True, json.dumps(healthy_provider_response), 200

    def test_passes_when_provider_available(self, temp_artifact_dir: Path) -> None:
        """Should pass when provider dependency shows 'available' status."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        health_response = {
            "healthy": True,
            "primary_failure_class": "",
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "available",
                    "phase": "models_list_ok",
                },
            ],
        }

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod",
            return_value=self._mock_curl_success(health_response),
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is True, f"Expected pass but got: {result.message}"
        assert result.check_method == "service"
        assert result.failure_class is None

    def test_fails_when_provider_disabled_required(self, temp_artifact_dir: Path) -> None:
        """Should fail with provider_disabled_required when provider is disabled."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        health_response = {
            "healthy": True,
            "provider_enabled": False,
            "provider_configured": False,
            "dependencies": [],
        }

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod",
            return_value=self._mock_curl_success(health_response),
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is False
        assert result.failure_class == "provider_disabled_required"

    def test_fails_when_provider_unavailable(self, temp_artifact_dir: Path) -> None:
        """Should fail with provider_unavailable when provider is unavailable."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        health_response = {
            "healthy": True,
            "primary_failure_class": "dependency_provider_connection_failed",
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "failure_class": "provider_connection_failed",
                },
            ],
        }

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod",
            return_value=self._mock_curl_success(health_response),
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is False
        assert result.failure_class == "provider_unavailable"

    def test_fails_when_provider_not_initialized(self, temp_artifact_dir: Path) -> None:
        """Should fail with provider_not_initialized when phase is not_initialized."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        health_response = {
            "healthy": True,
            "provider_enabled": True,
            "provider_configured": True,
            "phase": "not_initialized",
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "available",
                    "phase": "not_initialized",
                },
            ],
        }

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod",
            return_value=self._mock_curl_success(health_response),
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is False
        assert result.failure_class == "provider_not_initialized"

    def test_writes_result_artifact(self, temp_artifact_dir: Path) -> None:
        """Should write preflight result to artifact directory."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        health_response = {
            "healthy": True,
            "primary_failure_class": "",
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "available",
                    "phase": "models_list_ok",
                },
            ],
        }

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod",
            return_value=self._mock_curl_success(health_response),
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        artifact_file = temp_artifact_dir / "provider-preflight-result.json"
        assert artifact_file.exists(), "Result artifact should be written"

        artifact_data = json.loads(artifact_file.read_text())
        assert artifact_data["passed"] == result.passed
        assert artifact_data["check_method"] == "service"

    def test_connection_failure_falls_back_to_exec_local(self, temp_artifact_dir: Path) -> None:
        """Should fall back to exec-local when service curl fails."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        service_failure = (False, "connection refused", 0)
        exec_success_response = {
            "healthy": True,
            "primary_failure_class": "",
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "available",
                    "phase": "models_list_ok",
                },
            ],
        }
        exec_success = (True, json.dumps(exec_success_response), 200)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod",
            return_value=service_failure,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod",
            return_value=exec_success,
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is True
        assert result.check_method == "exec-local"

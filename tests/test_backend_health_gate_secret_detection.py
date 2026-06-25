#!/usr/bin/env python3
"""Tests for secretKeyRef detection in provider config.

Verifies proof-based secretKeyRef detection for diagnosis provider configuration.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.backend_health_gate.classification import _get_provider_config_status


class TestSecretKeyRefDetection:
    """Test proof-based secretKeyRef detection for provider config."""

    def _make_deployment_json(self, env_vars):
        """Create deployment JSON with specified env vars."""
        containers = [{"name": "backend", "env": env_vars}]
        items = [{
            "spec": {
                "template": {
                    "spec": {
                        "containers": containers
                    }
                }
            }
        }]
        return json.dumps({"items": items})

    def test_detects_diagnosis_api_key_secret_ref(self):
        """K9B_DIAGNOSIS_API_KEY + secretKeyRef sets diagnosis_provider_secret_ref_present=true."""
        deployment_json = self._make_deployment_json([
            {
                "name": "K9B_DIAGNOSIS_API_KEY",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "k9b-diagnosis-credentials",
                        "key": "K9B_DIAGNOSIS_API_KEY"
                    }
                }
            }
        ])
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=deployment_json, stderr="")
            
            status = _get_provider_config_status("/fake/kubeconfig", "test-ns")
        
        assert status["diagnosis_provider_secret_ref_present"] is True
        assert status["diagnosis_provider_enabled"] is True
        assert status["api_key_present"] is True

    def test_detects_external_analysis_api_key_secret_ref(self):
        """K9B_EXTERNAL_ANALYSIS_API_KEY + secretKeyRef sets small_provider_secret_ref_present=true."""
        deployment_json = self._make_deployment_json([
            {
                "name": "K9B_EXTERNAL_ANALYSIS_API_KEY",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "k9b-diagnosis-credentials",
                        "key": "K9B_EXTERNAL_ANALYSIS_API_KEY"
                    }
                }
            }
        ])
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=deployment_json, stderr="")
            
            status = _get_provider_config_status("/fake/kubeconfig", "test-ns")
        
        assert status["small_provider_secret_ref_present"] is True
        assert status["api_key_present"] is True
        assert status["diagnosis_provider_secret_ref_present"] is False

    def test_plain_env_var_without_secret_ref_does_not_set_secret_ref_present(self):
        """Plain env var (no secretKeyRef) does NOT set *_secret_ref_present=true."""
        deployment_json = self._make_deployment_json([
            {
                "name": "K9B_DIAGNOSIS_API_KEY",
                "value": "fake-key-value"  # Plain value, not secretKeyRef
            }
        ])
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=deployment_json, stderr="")
            
            status = _get_provider_config_status("/fake/kubeconfig", "test-ns")
        
        # Plain env vars should not set secret_ref_present flags
        assert status["diagnosis_provider_secret_ref_present"] is False
        assert status["small_provider_secret_ref_present"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

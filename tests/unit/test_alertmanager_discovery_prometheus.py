"""Unit tests for Prometheus CRD config discovery strategy.

Tests cover:
- Successful Prometheus config discovery
- Handling missing alerting config
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSourceOrigin,
    PrometheusCRDConfigDiscoveryStrategy,
)


class TestPrometheusCRDConfigDiscovery:
    """Tests for Prometheus CRD config-based discovery."""

    def test_prometheus_crd_config_discovery_success(self) -> None:
        """Test Prometheus CRD config discovery finds configured Alertmanagers."""
        strategy = PrometheusCRDConfigDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusList",
            "items": [
                {
                    "metadata": {
                        "name": "k8s",
                        "namespace": "monitoring",
                    },
                    "spec": {
                        "alerting": {
                            "alertmanagers": [
                                {
                                    "name": "main",
                                    "namespace": "monitoring",
                                }
                            ]
                        }
                    },
                }
            ],
        }

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(kubectl_output)

            mock_run.return_value = mock_result

            result = strategy.discover()

        assert result.strategy == "prometheus-crd-config"
        assert len(result.sources) == 1
        assert result.sources[0].origin == AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG

    def test_prometheus_crd_config_discovery_no_alertmanagers_configured(self) -> None:
        """Test Prometheus CRD config discovery handles no alerting config."""
        strategy = PrometheusCRDConfigDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusList",
            "items": [
                {
                    "metadata": {
                        "name": "k8s",
                        "namespace": "monitoring",
                    },
                    "spec": {},
                }
            ],
        }

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(kubectl_output)

            mock_run.return_value = mock_result

            result = strategy.discover()

        assert result.strategy == "prometheus-crd-config"
        assert len(result.sources) == 0

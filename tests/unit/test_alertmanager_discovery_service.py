"""Unit tests for service heuristic discovery strategy.

Tests cover:
- Successful service discovery
- Skipping non-matching services
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSourceOrigin,
    ServiceHeuristicDiscoveryStrategy,
)


class TestServiceHeuristicDiscovery:
    """Tests for service heuristic-based discovery."""

    def test_service_heuristic_discovery_success(self) -> None:
        """Test service heuristic discovery finds Alertmanager services."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "v1",
            "kind": "ServiceList",
            "items": [
                {
                    "metadata": {
                        "name": "alertmanager-main",
                        "namespace": "monitoring",
                    },
                    "spec": {
                        "ports": [
                            {"port": 9093, "targetPort": 9093}
                        ]
                    }
                }
            ],
        }

        pod_output = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": []
        }

        with patch("subprocess.run") as mock_run:
            mock_svc = MagicMock()
            mock_svc.returncode = 0
            mock_svc.stdout = json.dumps(kubectl_output)

            mock_pod = MagicMock()
            mock_pod.returncode = 0
            mock_pod.stdout = json.dumps(pod_output)

            mock_run.side_effect = [mock_svc, mock_pod]

            result = strategy.discover()

        assert result.strategy == "service-heuristic"
        assert len(result.sources) == 1
        assert result.sources[0].origin == AlertmanagerSourceOrigin.SERVICE_HEURISTIC
        assert result.sources[0].name == "alertmanager-main"

    def test_service_heuristic_skips_non_matching_services(self) -> None:
        """Test service heuristic skips services without 'alertmanager' in name."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "v1",
            "kind": "ServiceList",
            "items": [
                {
                    "metadata": {
                        "name": "nginx-service",
                        "namespace": "default",
                    },
                    "spec": {
                        "ports": [{"port": 80}]
                    }
                },
                {
                    "metadata": {
                        "name": "alertmanager-operated",
                        "namespace": "monitoring",
                    },
                    "spec": {
                        "ports": [{"port": 9093}]
                    }
                }
            ],
        }

        pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}

        with patch("subprocess.run") as mock_run:
            mock_svc = MagicMock()
            mock_svc.returncode = 0
            mock_svc.stdout = json.dumps(kubectl_output)

            mock_pod = MagicMock()
            mock_pod.returncode = 0
            mock_pod.stdout = json.dumps(pod_output)

            mock_run.side_effect = [mock_svc, mock_pod]

            result = strategy.discover()

        assert len(result.sources) == 1
        assert result.sources[0].name == "alertmanager-operated"

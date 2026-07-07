"""Unit tests for Alertmanager backing pod identity extraction.

Tests cover:
- Deduplication using backing pod UIDs from EndpointSlices
- Fallback to endpoint-based grouping when EndpointSlices unavailable
- Mocking kubectl calls for controlled test scenarios
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

from k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity import (
    get_service_backing_identity,
)


class TestGetServiceBackingIdentity:
    """Tests for get_service_backing_identity function."""

    def test_returns_none_when_kubectl_fails(self) -> None:
        """Should return None when kubectl command fails."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "context not found"
            
            result = get_service_backing_identity(
                namespace="monitoring",
                service_name="alertmanager-operated",
            )
            
            assert result is None

    def test_returns_none_on_timeout(self) -> None:
        """Should return None when kubectl command times out."""
        with patch(
            'subprocess.run',
            side_effect=subprocess.TimeoutExpired("cmd", 10)
        ):
            result = get_service_backing_identity(
                namespace="monitoring",
                service_name="alertmanager-operated",
            )
            
            assert result is None

    def test_parses_endpoint_slice_with_pod_uids(self) -> None:
        """Should correctly extract pod UIDs from EndpointSlice targetRef."""
        mock_response = {
            "items": [
                {
                    "endpoints": [
                        {
                            "targetRef": {
                                "kind": "Pod",
                                "namespace": "monitoring",
                                "name": "alertmanager-0",
                                "uid": "pod-uid-0"
                            },
                            "addresses": ["10.48.3.1"]
                        },
                        {
                            "targetRef": {
                                "kind": "Pod",
                                "namespace": "monitoring",
                                "name": "alertmanager-1",
                                "uid": "pod-uid-1"
                            },
                            "addresses": ["10.48.5.168"]
                        }
                    ]
                }
            ]
        }
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(mock_response)
            
            result = get_service_backing_identity(
                namespace="monitoring",
                service_name="alertmanager-operated",
            )
            
            assert result is not None
            assert result.kind == "backing_pods"
            assert result.uid_set == frozenset({"pod-uid-0", "pod-uid-1"})
            assert result.name_set == frozenset({"monitoring/alertmanager-0", "monitoring/alertmanager-1"})

    def test_returns_none_when_no_pod_references(self) -> None:
        """Should return None when no Pod targetRefs found in EndpointSlices."""
        mock_response: dict[str, object] = {"items": [{"endpoints": []}]}
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(mock_response)
            
            result = get_service_backing_identity(
                namespace="monitoring",
                service_name="alertmanager-operated",
            )
            
            # Empty endpoints should return None (no pods found)
            assert result is None

    def test_falls_back_to_legacy_endpoints(self) -> None:
        """Should fall back to legacy v1 Endpoints when EndpointSlices empty."""
        # First call (EndpointSlices) returns empty
        empty_response: dict[str, object] = {"items": [{"endpoints": []}]}
        # Second call (v1 Endpoints) returns pod UIDs
        endpoints_response = {
            "subsets": [
                {
                    "addresses": [
                        {
                            "targetRef": {
                                "kind": "Pod",
                                "namespace": "monitoring",
                                "name": "alertmanager-0",
                                "uid": "legacy-pod-uid-0"
                            }
                        }
                    ]
                }
            ]
        }
        
        def mock_side_effect(cmd: list[str], **kwargs):
            mock = type('MockResult', (), {'returncode': 0})()
            if 'endpointslices' in cmd:
                mock.stdout = json.dumps(empty_response)
            else:
                mock.stdout = json.dumps(endpoints_response)
            mock.stderr = ""
            return mock
        
        with patch('subprocess.run', side_effect=mock_side_effect):
            result = get_service_backing_identity(
                namespace="monitoring",
                service_name="alertmanager-operated",
            )
            
            assert result is not None
            assert result.uid_set == frozenset({"legacy-pod-uid-0"})

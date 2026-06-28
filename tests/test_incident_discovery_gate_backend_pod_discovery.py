"""Tests for robust backend pod discovery in incident discovery gate.

Verifies:
- Deployment selector extraction
- Service selector extraction
- Fallback chain behavior
- Diagnostic collection on failure
"""

from unittest.mock import MagicMock, patch

import pytest

from scripts.incident_discovery_gate.collect import (
    _BACKEND_LABEL_SELECTORS,
    _find_pods_with_selector,
    _get_deployment_selector,
    _get_service_selector,
    get_backend_pod_info,
)


class TestGetDeploymentSelector:
    """Tests for _get_deployment_selector helper."""

    @patch("subprocess.run")
    def test_returns_selector_from_deployment(self, mock_run: MagicMock) -> None:
        """Returns label selector from Deployment.spec.selector.matchLabels."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"spec":{"selector":{"matchLabels":{"app":"k9b","component":"backend"}}}}',
        )

        selector = _get_deployment_selector("kubeconfig", "namespace", "k9b-backend")

        assert selector == "app=k9b,component=backend"
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "deployment" in call_args
        assert "k9b-backend" in call_args

    @patch("subprocess.run")
    def test_returns_none_when_deployment_not_found(self, mock_run: MagicMock) -> None:
        """Returns None when deployment does not exist."""
        mock_run.return_value = MagicMock(returncode=1, stderr="NotFound")

        selector = _get_deployment_selector("kubeconfig", "namespace", "nonexistent")

        assert selector is None

    @patch("subprocess.run")
    def test_returns_none_when_no_match_labels(self, mock_run: MagicMock) -> None:
        """Returns None when Deployment has no matchLabels."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"spec":{"selector":{"matchExpressions":[{"key":"app","operator":"In","values":["k9b"]}]}}}',
        )

        selector = _get_deployment_selector("kubeconfig", "namespace", "k9b-backend")

        assert selector is None


class TestGetServiceSelector:
    """Tests for _get_service_selector helper."""

    @patch("subprocess.run")
    def test_returns_selector_from_service(self, mock_run: MagicMock) -> None:
        """Returns label selector from Service.spec.selector."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"spec":{"selector":{"app":"k9b"}}}',
        )

        selector = _get_service_selector("kubeconfig", "namespace", "k9b-backend")

        assert selector == "app=k9b"
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "service" in call_args
        assert "k9b-backend" in call_args

    @patch("subprocess.run")
    def test_returns_none_when_service_not_found(self, mock_run: MagicMock) -> None:
        """Returns None when service does not exist."""
        mock_run.return_value = MagicMock(returncode=1, stderr="NotFound")

        selector = _get_service_selector("kubeconfig", "namespace", "nonexistent")

        assert selector is None

    @patch("subprocess.run")
    def test_returns_none_when_no_selector(self, mock_run: MagicMock) -> None:
        """Returns None when Service has no selector."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"spec":{"ports":[{"port":8080}]}}',
        )

        selector = _get_service_selector("kubeconfig", "namespace", "k9b-backend")

        assert selector is None


class TestFindPodsWithSelector:
    """Tests for _find_pods_with_selector helper."""

    @patch("subprocess.run")
    def test_finds_running_pod(self, mock_run: MagicMock) -> None:
        """Finds and returns a Running pod."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"items":[{"metadata":{"name":"pod-abc","creationTimestamp":"2024-01-01T00:00:00Z"},"status":{"phase":"Running","podIP":"10.0.0.1","containerStatuses":[{"ready":true}]}}]}',
        )

        result = _find_pods_with_selector("kubeconfig", "namespace", "app=k9b")

        assert result["found"] is True
        assert result["pod_name"] == "pod-abc"
        assert result["total_running_pods"] == 1

    @patch("subprocess.run")
    def test_prefers_ready_pods(self, mock_run: MagicMock) -> None:
        """Prefers pods with all containers Ready."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"items":[{"metadata":{"name":"pod-not-ready","creationTimestamp":"2024-01-01T00:00:00Z"},"status":{"phase":"Running","podIP":"10.0.0.1","containerStatuses":[{"ready":false}]}},{"metadata":{"name":"pod-ready","creationTimestamp":"2024-01-01T00:00:01Z"},"status":{"phase":"Running","podIP":"10.0.0.2","containerStatuses":[{"ready":true}]}}]}',
        )

        result = _find_pods_with_selector("kubeconfig", "namespace", "app=k9b")

        assert result["found"] is True
        assert result["pod_name"] == "pod-ready"
        assert result["total_ready_pods"] == 1

    @patch("subprocess.run")
    def test_selects_oldest_pod_for_consistency(self, mock_run: MagicMock) -> None:
        """Selects oldest Running pod when multiple candidates exist."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"items":[{"metadata":{"name":"pod-new","creationTimestamp":"2024-01-02T00:00:00Z"},"status":{"phase":"Running","containerStatuses":[{"ready":true}]}},{"metadata":{"name":"pod-old","creationTimestamp":"2024-01-01T00:00:00Z"},"status":{"phase":"Running","containerStatuses":[{"ready":true}]}}]}',
        )

        result = _find_pods_with_selector("kubeconfig", "namespace", "app=k9b")

        assert result["found"] is True
        assert result["pod_name"] == "pod-old"

    @patch("subprocess.run")
    def test_returns_not_found_when_no_pods(self, mock_run: MagicMock) -> None:
        """Returns found=False when no pods match selector."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"items":[]}',
        )

        result = _find_pods_with_selector("kubeconfig", "namespace", "app=nonexistent")

        assert result["found"] is False
        assert "No pods found" in result["error"]


class TestGetBackendPodInfo:
    """Tests for get_backend_pod_info with robust selector discovery."""

    @patch("scripts.incident_discovery_gate.collect._find_pods_with_selector")
    @patch("scripts.incident_discovery_gate.collect._get_deployment_selector")
    @patch("scripts.incident_discovery_gate.collect._get_service_selector")
    def test_uses_deployment_selector_first(
        self,
        mock_get_svc_selector: MagicMock,
        mock_get_deploy_selector: MagicMock,
        mock_find_pods: MagicMock,
    ) -> None:
        """Uses Deployment selector as the first choice."""
        mock_get_deploy_selector.return_value = "app=k9b,component=backend"
        mock_find_pods.return_value = {
            "found": True,
            "pod_name": "pod-abc",
            "namespace": "namespace",
            "pod_ip": "10.0.0.1",
            "total_running_pods": 1,
            "total_ready_pods": 1,
        }

        result = get_backend_pod_info("kubeconfig", "namespace", "k9b-backend")

        assert result["found"] is True
        assert result["pod_name"] == "pod-abc"
        assert result["selector_used"] == "app=k9b,component=backend"
        assert result["selector_source"] == "deployment"
        mock_get_svc_selector.assert_not_called()

    @patch("scripts.incident_discovery_gate.collect._find_pods_with_selector")
    @patch("scripts.incident_discovery_gate.collect._get_deployment_selector")
    @patch("scripts.incident_discovery_gate.collect._get_service_selector")
    def test_falls_back_to_service_selector(
        self,
        mock_get_svc_selector: MagicMock,
        mock_get_deploy_selector: MagicMock,
        mock_find_pods: MagicMock,
    ) -> None:
        """Falls back to Service selector when Deployment selector fails."""
        mock_get_deploy_selector.return_value = None  # No Deployment found
        mock_get_svc_selector.return_value = "app=k9b"
        mock_find_pods.return_value = {
            "found": True,
            "pod_name": "pod-abc",
            "namespace": "namespace",
            "pod_ip": "10.0.0.1",
            "total_running_pods": 1,
            "total_ready_pods": 1,
        }

        result = get_backend_pod_info("kubeconfig", "namespace", "k9b-backend")

        assert result["found"] is True
        assert result["selector_used"] == "app=k9b"
        assert result["selector_source"] == "service"

    @patch("scripts.incident_discovery_gate.collect._find_pods_with_selector")
    @patch("scripts.incident_discovery_gate.collect._get_deployment_selector")
    @patch("scripts.incident_discovery_gate.collect._get_service_selector")
    def test_falls_back_to_known_labels(
        self,
        mock_get_svc_selector: MagicMock,
        mock_get_deploy_selector: MagicMock,
        mock_find_pods: MagicMock,
    ) -> None:
        """Falls back to known Helm labels when Deployment/Service fail."""
        # When deployment_selector is None, the step is skipped entirely
        mock_get_deploy_selector.return_value = None
        mock_get_svc_selector.return_value = None

        # Third fallback (app.kubernetes.io/component=backend) succeeds
        # Only 3 fallbacks tried since Deployment and Service selectors are None
        mock_find_pods.side_effect = [
            {"found": False, "error": "No pods found"},  # First fallback (app.kubernetes.io/name=k9b)
            {"found": False, "error": "No pods found"},  # Second fallback (app=k9b)
            {"found": True, "pod_name": "pod-abc", "namespace": "namespace", "pod_ip": "10.0.0.1", "total_running_pods": 1, "total_ready_pods": 1},  # Third fallback
        ]

        result = get_backend_pod_info("kubeconfig", "namespace", "k9b-backend")

        assert result["found"] is True
        assert result["selector_used"] == "app.kubernetes.io/component=backend"
        assert result["selector_source"] == "fallback"

    @patch("scripts.incident_discovery_gate.collect._find_pods_with_selector")
    @patch("scripts.incident_discovery_gate.collect._get_deployment_selector")
    @patch("scripts.incident_discovery_gate.collect._get_service_selector")
    @patch("scripts.incident_discovery_gate.collect._collect_namespace_diagnostics")
    def test_includes_diagnostics_on_failure(
        self,
        mock_collect_diagnostics: MagicMock,
        mock_get_svc_selector: MagicMock,
        mock_get_deploy_selector: MagicMock,
        mock_find_pods: MagicMock,
    ) -> None:
        """Collects namespace diagnostics when all selectors fail."""
        mock_get_deploy_selector.return_value = "app=k9b"
        mock_find_pods.return_value = {"found": False, "error": "No running pods"}
        mock_collect_diagnostics.return_value = {"namespace": "namespace", "pods": []}

        result = get_backend_pod_info("kubeconfig", "namespace", "k9b-backend")

        assert result["found"] is False
        assert "attempted_selectors" in result
        assert len(result["attempted_selectors"]) > 0
        assert "diagnostics" in result

    @patch("scripts.incident_discovery_gate.collect._find_pods_with_selector")
    @patch("scripts.incident_discovery_gate.collect._get_deployment_selector")
    @patch("scripts.incident_discovery_gate.collect._get_service_selector")
    def test_includes_selector_source_in_attempted(
        self,
        mock_get_svc_selector: MagicMock,
        mock_get_deploy_selector: MagicMock,
        mock_find_pods: MagicMock,
    ) -> None:
        """Each attempted selector includes its source."""
        mock_get_deploy_selector.return_value = "app=k9b,component=backend"
        mock_find_pods.return_value = {"found": False, "error": "No pods"}

        result = get_backend_pod_info("kubeconfig", "namespace", "k9b-backend")

        attempted = result.get("attempted_selectors", [])
        assert any(a["source"] == "deployment" for a in attempted)


class TestBackendLabelSelectors:
    """Tests for the _BACKEND_LABEL_SELECTORS fallback list."""

    def test_includes_helm_standard_labels(self) -> None:
        """The fallback list includes standard Helm labels."""
        assert "app.kubernetes.io/name=k9b" in _BACKEND_LABEL_SELECTORS

    def test_includes_app_label(self) -> None:
        """The fallback list includes simple app label."""
        assert "app=k9b" in _BACKEND_LABEL_SELECTORS

    def test_includes_component_label(self) -> None:
        """The fallback list includes component label."""
        assert "app.kubernetes.io/component=backend" in _BACKEND_LABEL_SELECTORS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

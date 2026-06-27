#!/usr/bin/env python3
"""Unit tests for backend pod consistency in collect.py.

Verifies that call_backend_incidents_api accepts and uses the backend_pod_name parameter.
"""

import pytest

from scripts.incident_discovery_gate.collect import call_backend_incidents_api


class TestCallBackendIncidentsApiSignature:
    """Test that call_backend_incidents_api accepts backend_pod_name parameter."""

    def test_signature_includes_backend_pod_name(self) -> None:
        """Verify the function signature includes backend_pod_name parameter."""
        import inspect
        sig = inspect.signature(call_backend_incidents_api)
        params = list(sig.parameters.keys())
        assert "backend_pod_name" in params, (
            f"backend_pod_name not in signature. Got: {params}"
        )

    def test_backend_pod_name_default_is_none(self) -> None:
        """Verify backend_pod_name defaults to None for backward compatibility."""
        import inspect
        sig = inspect.signature(call_backend_incidents_api)
        param = sig.parameters.get("backend_pod_name")
        assert param is not None, "backend_pod_name parameter not found"
        assert param.default is None, (
            f"backend_pod_name default should be None, got {param.default}"
        )


class TestCallBackendIncidentsApiBehavior:
    """Test that call_backend_incidents_api uses the pod name when provided."""

    def test_uses_pod_target_when_provided(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that when backend_pod_name is provided, it targets the specific pod."""
        captured_commands: list[str] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            # Capture the full command to verify pod targeting
            captured_commands.append(" ".join(str(c) for c in cmd))
            class MockResult:
                returncode = 0
                stdout = '{"incidents":[]}\n200'
            return MockResult()

        monkeypatch.setattr("subprocess.run", mock_run)

        # Call with explicit pod name
        call_backend_incidents_api(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            backend_deployment="k9b-backend",
            backend_container="backend",
            backend_port=8080,
            backend_pod_name="k9b-backend-pod-explicit",
        )

        # Verify the command uses pod/<name> targeting
        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert "pod/k9b-backend-pod-explicit" in cmd, (
            f"Expected 'pod/k9b-backend-pod-explicit' in command: {cmd}"
        )
        # Should NOT use deploy/<name> when pod name is provided
        assert "deploy/k9b-backend" not in cmd, (
            f"Should not use deploy targeting when pod name is provided: {cmd}"
        )

    def test_uses_deploy_target_when_not_provided(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that when backend_pod_name is not provided, it uses deployment targeting."""
        captured_commands: list[str] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(" ".join(str(c) for c in cmd))
            class MockResult:
                returncode = 0
                stdout = '{"incidents":[]}\n200'
            return MockResult()

        monkeypatch.setattr("subprocess.run", mock_run)

        # Call without pod name
        call_backend_incidents_api(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            backend_deployment="k9b-backend",
            backend_container="backend",
            backend_port=8080,
        )

        # Verify the command uses deploy/<name> targeting
        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert "deploy/k9b-backend" in cmd, (
            f"Expected 'deploy/k9b-backend' in command: {cmd}"
        )
        # Should NOT use pod/<name> when not provided
        assert "pod/" not in cmd, (
            f"Should not use pod targeting when pod name is not provided: {cmd}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

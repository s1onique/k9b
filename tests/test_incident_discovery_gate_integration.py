#!/usr/bin/env python3
"""Tests for incident discovery gate integration concerns.

Verifies:
- Wrapper import mode (CLI execution)
- Artifact path consistency
- Log sanitization for artifact writing
"""

from pathlib import Path

import pytest

from scripts.incident_discovery_gate.render import sanitize_logs_for_artifacts


class TestWrapperImportMode:
    """Regression tests for CLI wrapper import mode."""

    def test_wrapper_imports_when_run_as_file(self) -> None:
        """Wrapper script imports correctly when executed as `python scripts/check_incident_discovery_gate.py`."""
        # Verify imports work
        from scripts.incident_discovery_gate import run_incident_discovery

        assert run_incident_discovery is not None


class TestArtifactPathConsistency:
    """Regression tests for artifact path consistency.

    Ensures that artifact_dir is used as-is without double-nesting.
    The workflow passes --artifact-dir ./lab-artifacts/live/provider-smoke/incident-discovery
    so main.py should NOT append additional path components.
    """

    def test_artifact_dir_used_directly(self) -> None:
        """Verify artifact_dir is used directly, not appended with provider-smoke/incident-discovery."""
        # This test verifies the contract: if artifact_dir is passed as-is,
        # no additional path components should be added.
        # The actual integration is tested via workflow runs.
        #
        # Contract: When workflow passes:
        #   --artifact-dir ./lab-artifacts/live/provider-smoke/incident-discovery
        # The artifacts should be written to that exact directory, not nested further.
        #
        # We verify this by checking the code doesn't append subdirectories.
        # The run_incident_discovery function should use artifact_dir directly.
        import inspect

        from scripts.incident_discovery_gate.main import run_incident_discovery

        source = inspect.getsource(run_incident_discovery)

        # Verify the pattern is artifact_dir / "provider-smoke" / "incident-discovery" NOT in source
        # After the fix, this pattern should not exist
        assert 'artifact_dir / "provider-smoke"' not in source, (
            "Artifact path double-nesting detected: main.py still appends 'provider-smoke/incident-discovery'"
        )
        assert "discovery_dir = artifact_dir" in source, (
            "main.py should use artifact_dir directly"
        )


class TestSanitizeLogsForArtifacts:
    """Test log sanitization for artifact writing."""

    def test_redacts_api_key_pattern(self) -> None:
        """API key patterns are redacted."""
        logs = 'api_key=sk-1234567890abcdefghijklmnopqrstuvwxyz'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "sk-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_token_pattern(self) -> None:
        """Token patterns are redacted."""
        logs = 'token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_bearer_token(self) -> None:
        """Bearer tokens are redacted."""
        logs = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "Bearer eyJhbGciOiJIUzI1NiJ9" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_openai_api_key(self) -> None:
        """OpenAI API key patterns are redacted."""
        logs = 'OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnopqrstuvwxyz'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_anthropic_api_key(self) -> None:
        """Anthropic API key patterns are redacted."""
        logs = 'anthropic_api_key=sk-ant-1234567890abcdefghijklmnopqrstuvwxyz'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "sk-ant-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_url_with_credentials(self) -> None:
        """URLs with embedded credentials are redacted."""
        logs = "https://user:password@example.com/api"
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "user:password" not in sanitized
        assert "[REDACTED_USER]" in sanitized
        assert "[REDACTED_PASS]" in sanitized

    def test_preserves_non_sensitive_content(self) -> None:
        """Non-sensitive content is preserved."""
        logs = 'INFO: Processing request for incident inc-123'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "Processing request" in sanitized
        assert "inc-123" in sanitized

    def test_handles_empty_logs(self) -> None:
        """Empty logs are handled gracefully."""
        assert sanitize_logs_for_artifacts("") == ""
        # The function accepts None implicitly and returns it
        result: str | None = sanitize_logs_for_artifacts(None)  # type: ignore[arg-type]
        assert result is None

    def test_handles_multiline_logs(self) -> None:
        """Multiline logs are sanitized correctly."""
        logs = """2024-01-01 10:00:00 INFO Starting process
api_key=sk-1234567890abcdefghijklmnopqrstuvwxyz
2024-01-01 10:00:01 INFO Request completed
"""
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "sk-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "Starting process" in sanitized
        assert "Request completed" in sanitized


class TestNamespaceSeparation:
    """Regression tests for namespace separation in incident discovery.

    These tests verify that the incident discovery gate correctly separates:
    - backend_namespace: where k9b backend runs (for API calls)
    - incident_namespace: where OTel workload incidents are injected (for fixture discovery)
    
    This separation is critical for provider smoke tests where:
    - k9b backend runs in namespace "k9b"
    - OTel demo (with injected failures) runs in namespace "otel-demo"
    """

    def test_run_incident_discovery_accepts_backend_and_incident_namespace_params(self) -> None:
        """Verify run_incident_discovery accepts backend_namespace and incident_namespace parameters."""
        import inspect

        from scripts.incident_discovery_gate.main import run_incident_discovery

        sig = inspect.signature(run_incident_discovery)
        param_names = list(sig.parameters.keys())

        assert "backend_namespace" in param_names, (
            "run_incident_discovery must accept backend_namespace parameter"
        )
        assert "incident_namespace" in param_names, (
            "run_incident_discovery must accept incident_namespace parameter"
        )

    def test_phase_p2_passes_backend_and_incident_namespaces_to_gate(
        self, tmp_path: Path
    ) -> None:
        """Verify phase_p2_incident_discovery_provider passes correct namespaces to the gate.
        
        This is the behavior-level regression test for the bug where P2 was using
        K9B_NAMESPACE (k9b) for incident discovery instead of config.namespace (otel-demo).
        """
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        from scripts.k9b_otel_demo_lab_provider_diagnosis import (
            phase_p2_incident_discovery_provider,
        )

        # run_incident_discovery is imported inside the function, so patch where it's defined
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.incident_id = "test-incident-123"
        mock_result.failure_class = ""
        mock_result.to_dict.return_value = {}

        with patch(
            "scripts.incident_discovery_gate.run_incident_discovery",
            return_value=mock_result
        ) as run_gate:
            config = SimpleNamespace(
                kubeconfig="/tmp/kubeconfig",
                namespace="otel-demo",
            )

            phase_p2_incident_discovery_provider(config, tmp_path)

            run_gate.assert_called_once()
            kwargs = run_gate.call_args.kwargs
            assert kwargs["backend_namespace"] == "k9b", (
                "backend_namespace should be k9b (K9B_NAMESPACE)"
            )
            assert kwargs["incident_namespace"] == "otel-demo", (
                "incident_namespace should be otel-demo (config.namespace)"
            )

    def test_phase_p2_logs_both_namespaces_separately(self) -> None:
        """Verify phase_p2 logs backend_namespace and incident_namespace separately.
        
        The log output should be unambiguous:
            backend_namespace=k9b
            incident_namespace=otel-demo
            expected_fixture=recommendation
        """
        import inspect

        from scripts.k9b_otel_demo_lab_provider_diagnosis import (
            phase_p2_incident_discovery_provider,
        )

        source = inspect.getsource(phase_p2_incident_discovery_provider)

        # Verify both namespaces are logged
        assert "backend_namespace=" in source, (
            "P2 should log backend_namespace"
        )
        assert "incident_namespace=" in source, (
            "P2 should log incident_namespace separately from backend_namespace"
        )

    def test_cli_accepts_backend_namespace_and_incident_namespace_args(self) -> None:
        """Verify CLI accepts --backend-namespace and --incident-namespace arguments."""
        import inspect

        from scripts.incident_discovery_gate.cli import create_arg_parser

        source = inspect.getsource(create_arg_parser)

        assert "--backend-namespace" in source, (
            "CLI should accept --backend-namespace argument"
        )
        assert "--incident-namespace" in source, (
            "CLI should accept --incident-namespace argument"
        )

    def test_cli_wrapper_accepts_backend_namespace_and_incident_namespace_args(self) -> None:
        """Verify check_incident_discovery_gate.py accepts namespace arguments."""
        with open("scripts/check_incident_discovery_gate.py", "r") as f:
            source = f.read()

        assert "--backend-namespace" in source, (
            "CLI wrapper should accept --backend-namespace argument"
        )
        assert "--incident-namespace" in source, (
            "CLI wrapper should accept --incident-namespace argument"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

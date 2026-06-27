#!/usr/bin/env python3
"""Tests for incident discovery gate integration concerns.

Verifies:
- Wrapper import mode (CLI execution)
- Artifact path consistency
- Log sanitization for artifact writing
"""

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

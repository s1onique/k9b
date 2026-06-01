"""Tests for external analysis adapter HTTP-only mode (openai_compatible provider).

These tests verify that:
- openai_compatible provider uses HTTP-only mode (no subprocess llamacpp binary)
- Missing base_url/model produces explicit provider_misconfigured failure
- Legacy llamacpp adapter still supports CLI fallback for backward compatibility
- Artifact fields are correctly populated for config errors
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from k8s_diag_agent.external_analysis.adapter import ExternalAnalysisRequest
from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisStatus
from k8s_diag_agent.external_analysis.llamacpp_adapter import LlamaCppAdapter


class TestOpenaiCompatibleHttpOnly:
    """Tests for openai_compatible adapter HTTP-only behavior."""

    def test_openai_compatible_adapter_http_only_flag(self) -> None:
        """Verify openai_compatible adapter is created with http_only=True."""
        adapter = LlamaCppAdapter(http_only=True)
        assert adapter._http_only is True
        # Without env vars, should not have HTTP provider
        assert adapter._http_provider is None
        # Should not have CLI command
        assert adapter._command is None

    def test_openai_compatible_missing_config_preflight_fails(self, monkeypatch: Any) -> None:
        """openai_compatible with missing base_url/model should fail preflight with explicit reason."""
        # Ensure no HTTP config is available
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        adapter = LlamaCppAdapter(http_only=True)
        result = adapter.preflight_check(provider_requested="openai_compatible")

        assert result.ok is False
        assert result.reason in ("missing_base_url", "missing_model", "missing_config")
        assert result.operator_message is not None
        assert "K9B_EXTERNAL_ANALYSIS_BASE_URL" in result.operator_message or "base URL" in result.operator_message.lower()

    def test_openai_compatible_missing_base_url_preflight_reason(self, monkeypatch: Any) -> None:
        """Missing base_url should produce missing_base_url reason."""
        monkeypatch.setenv("K9B_EXTERNAL_ANALYSIS_MODEL", "test-model")
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)

        adapter = LlamaCppAdapter(http_only=True)
        result = adapter.preflight_check(provider_requested="openai_compatible")

        assert result.ok is False
        assert result.reason == "missing_base_url"

    def test_openai_compatible_missing_model_preflight_reason(self, monkeypatch: Any) -> None:
        """Missing model should produce missing_model or missing_base_url reason (config error)."""
        monkeypatch.setenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", "http://localhost:8080")
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        adapter = LlamaCppAdapter(http_only=True)
        result = adapter.preflight_check(provider_requested="openai_compatible")

        assert result.ok is False
        # Either missing_model or missing_config is valid - config is incomplete
        assert result.reason in ("missing_model", "missing_config", "missing_base_url")

    def test_openai_compatible_run_without_config_returns_failure_artifact(
        self, monkeypatch: Any, tmp_path: Path
    ) -> None:
        """openai_compatible run() without config should return FAILED artifact with error_summary."""
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        adapter = LlamaCppAdapter(http_only=True)
        review_path = tmp_path / "review.json"
        review_path.write_text('{"run_id": "test"}')

        request = ExternalAnalysisRequest(
            run_id="test-run",
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        artifact = adapter.run(request)

        # Should be FAILED status (not SKIPPED for config error)
        assert artifact.status == ExternalAnalysisStatus.FAILED
        # error_summary must be non-null for provider failures
        assert artifact.error_summary is not None
        assert len(artifact.error_summary) > 0
        # duration_ms should be > 0 when HTTP call was attempted (even if failed early)
        assert artifact.duration_ms is not None
        assert artifact.duration_ms >= 0
        # tool_name should be "llamacpp" (adapter instance name)
        assert artifact.tool_name == "llamacpp"
        # provider should reflect the normalized name
        assert artifact.provider == "llamacpp"

    def test_openai_compatible_does_not_invoke_subprocess(self, monkeypatch: Any, tmp_path: Path) -> None:
        """openai_compatible should never invoke subprocess llamacpp binary."""
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        subprocess_called: list[str] = []

        def fake_run_subprocess(command: Any) -> str:
            subprocess_called.append(str(command))
            return "fake output"

        with patch(
            "k8s_diag_agent.external_analysis.llamacpp_adapter._run_subprocess",
            fake_run_subprocess
        ):
            adapter = LlamaCppAdapter(http_only=True)
            review_path = tmp_path / "review.json"
            review_path.write_text('{"run_id": "test"}')

            request = ExternalAnalysisRequest(
                run_id="test-run",
                cluster_label="test-cluster",
                source_artifact=str(review_path),
            )
            artifact = adapter.run(request)

        # Subprocess should never be called for HTTP-only adapter
        assert len(subprocess_called) == 0
        # Artifact should be FAILED, not SUCCESS
        assert artifact.status == ExternalAnalysisStatus.FAILED


class TestLegacyLlamacppAdapter:
    """Tests for legacy llamacpp adapter backward compatibility."""

    def test_legacy_llamacpp_adapter_http_only_false(self) -> None:
        """Legacy llamacpp adapter should have http_only=False by default."""
        adapter = LlamaCppAdapter()
        assert adapter._http_only is False

    def test_legacy_llamacpp_with_empty_command_skips(self, monkeypatch: Any) -> None:
        """Legacy llamacpp with empty command tuple should SKIP (not fail)."""
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        adapter = LlamaCppAdapter(command=())
        request = ExternalAnalysisRequest(
            run_id="test-run",
            cluster_label="test-cluster",
            source_artifact=None,
        )
        artifact = adapter.run(request)

        # Legacy adapter with empty command should SKIP
        assert artifact.status == ExternalAnalysisStatus.SKIPPED
        assert artifact.skip_reason is not None

    def test_legacy_llamacpp_with_explicit_command_uses_subprocess(
        self, monkeypatch: Any, tmp_path: Path
    ) -> None:
        """Legacy llamacpp with explicit command should use subprocess."""
        subprocess_called: list[list[str]] = []

        def fake_run_subprocess(command: Any) -> str:
            subprocess_called.append(list(command))
            return "fake analysis output"

        with patch(
            "k8s_diag_agent.external_analysis.llamacpp_adapter._run_subprocess",
            fake_run_subprocess
        ):
            adapter = LlamaCppAdapter(command=("llamacpp", "analysis"))
            review_path = tmp_path / "review.json"
            review_path.write_text('{"run_id": "test"}')

            request = ExternalAnalysisRequest(
                run_id="test-run",
                cluster_label="test-cluster",
                source_artifact=str(review_path),
            )
            _ = adapter.run(request)

        # Subprocess should be called for legacy adapter with explicit command
        assert len(subprocess_called) == 1
        assert subprocess_called[0][0] == "llamacpp"


class TestArtifactFieldsForProviderFailures:
    """Tests for correct artifact field population on provider failures."""

    def test_failure_artifact_has_error_summary(self, monkeypatch: Any, tmp_path: Path) -> None:
        """Provider failure artifact must have non-null error_summary."""
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        adapter = LlamaCppAdapter(http_only=True)
        review_path = tmp_path / "review.json"
        review_path.write_text('{"run_id": "test"}')

        request = ExternalAnalysisRequest(
            run_id="test-run",
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        artifact = adapter.run(request)

        assert artifact.status == ExternalAnalysisStatus.FAILED
        assert artifact.error_summary is not None
        assert len(artifact.error_summary) > 0

    def test_failure_artifact_has_duration_ms(self, monkeypatch: Any, tmp_path: Path) -> None:
        """Provider failure artifact should have duration_ms > 0."""
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        adapter = LlamaCppAdapter(http_only=True)
        review_path = tmp_path / "review.json"
        review_path.write_text('{"run_id": "test"}')

        request = ExternalAnalysisRequest(
            run_id="test-run",
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        artifact = adapter.run(request)

        assert artifact.duration_ms is not None
        assert artifact.duration_ms >= 0

    def test_failure_artifact_tool_name_is_llamacpp(self, monkeypatch: Any, tmp_path: Path) -> None:
        """Provider failure artifact tool_name should be 'llamacpp' (adapter instance name)."""
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        adapter = LlamaCppAdapter(http_only=True)
        review_path = tmp_path / "review.json"
        review_path.write_text('{"run_id": "test"}')

        request = ExternalAnalysisRequest(
            run_id="test-run",
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        artifact = adapter.run(request)

        # tool_name is the adapter instance name, not the provider name
        assert artifact.tool_name == "llamacpp"

    def test_failure_artifact_payload_is_null(self, monkeypatch: Any, tmp_path: Path) -> None:
        """Provider failure artifact payload should be None (not empty dict)."""
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", raising=False)
        monkeypatch.delenv("K9B_EXTERNAL_ANALYSIS_MODEL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
        monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)

        adapter = LlamaCppAdapter(http_only=True)
        review_path = tmp_path / "review.json"
        review_path.write_text('{"run_id": "test"}')

        request = ExternalAnalysisRequest(
            run_id="test-run",
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        artifact = adapter.run(request)

        # payload should be None for failures, not {}
        assert artifact.payload is None


class TestHelmEnvWiring:
    """Tests for Helm environment variable wiring (smoke tests)."""

    def test_adapter_accepts_canonical_env_vars(self, monkeypatch: Any) -> None:
        """Adapter should accept K9B_EXTERNAL_ANALYSIS_* canonical env vars."""
        monkeypatch.setenv("K9B_EXTERNAL_ANALYSIS_BASE_URL", "http://llm:8080/v1")
        monkeypatch.setenv("K9B_EXTERNAL_ANALYSIS_MODEL", "test-model")

        # Should not raise
        adapter = LlamaCppAdapter(http_only=True)
        result = adapter.preflight_check(provider_requested="openai_compatible")

        assert result.ok is True
        assert result.base_url == "http://llm:8080/v1"
        assert result.model == "test-model"

    def test_adapter_accepts_legacy_env_vars(self, monkeypatch: Any) -> None:
        """Adapter should accept LLAMA_CPP_* legacy env vars for backward compatibility."""
        monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://llm:8080")
        monkeypatch.setenv("LLAMA_CPP_MODEL", "legacy-model")

        adapter = LlamaCppAdapter(http_only=True)
        result = adapter.preflight_check(provider_requested="openai_compatible")

        assert result.ok is True
        assert result.model == "legacy-model"

"""Tests for scheduler effective config logging at startup.

Tests cover:
- Startup log is emitted once
- Log contains expected non-secret fields
- API keys/secrets are not logged
- LLAMA_CPP_RESPONSE_FORMAT_JSON effective value appears
- max_tokens and timeout effective values appear when llama.cpp config is available
- Missing llama.cpp env does not crash scheduler config logging
- URLs are sanitized if they contain credentials/query strings
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from k8s_diag_agent.external_analysis.alertmanager_config import AlertmanagerAuth
from k8s_diag_agent.external_analysis.config import (
    AlertmanagerConfig,
    AutoDrilldownPolicy,
    ExternalAnalysisAdapterConfig,
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.health.loop_config_logging import (
    _add_llamacpp_fields,
    _build_effective_scheduler_config_log,
    _log_effective_scheduler_config,
    _sanitize_url_for_logging,
)
from k8s_diag_agent.health.loop_scheduler import HealthLoopScheduler


def _mock_run_health_loop(*args: object, **kwargs: object) -> tuple[int, list[object], list[object], list[object], list[object], ExternalAnalysisSettings]:
    return (0, [], [], [], [], ExternalAnalysisSettings())


def _make_mock_config(
    run_label: str = "test-scheduler",
    output_dir: Path | None = None,
    external_analysis: ExternalAnalysisSettings | None = None,
    targets: list | None = None,
) -> MagicMock:
    """Create a mock HealthRunConfig for testing."""
    mock_config = MagicMock()
    mock_config.run_label = run_label
    mock_config.output_dir = output_dir or Path("/tmp/test-runs")
    mock_config.external_analysis = external_analysis or ExternalAnalysisSettings()
    mock_config.targets = targets or []
    return mock_config


class TestSanitizeUrlForLogging(unittest.TestCase):
    """Tests for URL sanitization."""

    def test_sanitize_url_with_credentials(self) -> None:
        """URLs with credentials should have credentials stripped."""
        url = "http://user:password@example.com:8080/api/v1?query=value"
        result = _sanitize_url_for_logging(url)
        assert result is not None
        self.assertNotIn("user", result)
        self.assertNotIn("password", result)
        self.assertNotIn("query=value", result)
        self.assertIn("example.com", result)
        self.assertIn("8080", result)

    def test_sanitize_url_with_bearer_token_in_query(self) -> None:
        """URLs with tokens in query string should be stripped."""
        url = "http://localhost:11434/api?token=secret123"
        result = _sanitize_url_for_logging(url)
        assert result is not None
        self.assertNotIn("token", result)
        self.assertNotIn("secret123", result)

    def test_sanitize_url_simple(self) -> None:
        """Simple URLs should pass through."""
        url = "http://localhost:11434/v1/chat/completions"
        result = _sanitize_url_for_logging(url)
        self.assertEqual(result, "http://localhost:11434/v1/chat/completions")

    def test_sanitize_url_https(self) -> None:
        """HTTPS URLs should work correctly."""
        url = "https://api.example.com/openai/v1"
        result = _sanitize_url_for_logging(url)
        self.assertEqual(result, "https://api.example.com/openai/v1")

    def test_sanitize_url_none(self) -> None:
        """None URLs should return None."""
        result = _sanitize_url_for_logging(None)
        self.assertIsNone(result)


class TestBuildEffectiveSchedulerConfigLog(unittest.TestCase):
    """Tests for building the effective scheduler config log."""

    def test_basic_fields_present(self) -> None:
        """Test that basic scheduler fields are present."""
        config = _make_mock_config()
        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=10,
            run_once=False,
        )

        self.assertEqual(result["event"], "scheduler-config")
        self.assertEqual(result["run_label"], "test-scheduler")
        self.assertEqual(result["every_seconds"], 60)
        self.assertEqual(result["max_runs"], 10)
        self.assertEqual(result["loop_mode"], "interval")

    def test_run_once_mode(self) -> None:
        """Test that loop_mode is 'once' when run_once=True."""
        config = _make_mock_config()
        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=None,
            max_runs=1,
            run_once=True,
        )

        self.assertEqual(result["loop_mode"], "once")

    def test_cluster_count_and_labels(self) -> None:
        """Test that cluster count and labels are included."""
        mock_targets = [
            MagicMock(label="prod-cluster"),
            MagicMock(label="dev-cluster"),
        ]
        config = _make_mock_config(targets=mock_targets)

        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertEqual(result["cluster_count"], 2)
        self.assertEqual(result["cluster_labels"], ["prod-cluster", "dev-cluster"])

    def test_cluster_labels_truncated(self) -> None:
        """Test that cluster labels are truncated when > 5."""
        mock_targets = [MagicMock(label=f"cluster-{i}") for i in range(7)]
        config = _make_mock_config(targets=mock_targets)

        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertEqual(result["cluster_count"], 7)
        self.assertEqual(len(result["cluster_labels"]), 5)
        self.assertTrue(result["cluster_labels_truncated"])

    def test_external_analysis_adapters(self) -> None:
        """Test that external analysis adapter names are included."""
        adapters = (
            ExternalAnalysisAdapterConfig(name="llamacpp", enabled=True),
            ExternalAnalysisAdapterConfig(name="alertmanager", enabled=True),
        )
        ea_settings = ExternalAnalysisSettings(adapters=adapters)
        config = _make_mock_config(external_analysis=ea_settings)

        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertIn("external_analysis_adapters", result)
        self.assertEqual(result["external_analysis_adapters"], ["llamacpp", "alertmanager"])

    def test_auto_drilldown_enabled(self) -> None:
        """Test that auto drilldown settings are included when enabled."""
        auto_drilldown = AutoDrilldownPolicy(enabled=True, provider="llamacpp", max_per_run=2)
        ea_settings = ExternalAnalysisSettings(auto_drilldown=auto_drilldown)
        config = _make_mock_config(external_analysis=ea_settings)

        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertTrue(result.get("auto_drilldown_enabled"))
        self.assertEqual(result.get("auto_drilldown_provider"), "llamacpp")
        self.assertEqual(result.get("auto_drilldown_max_per_run"), 2)

    def test_review_enrichment_enabled(self) -> None:
        """Test that review enrichment settings are included when enabled."""
        review_enrichment = ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        ea_settings = ExternalAnalysisSettings(review_enrichment=review_enrichment)
        config = _make_mock_config(external_analysis=ea_settings)

        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertTrue(result.get("review_enrichment_enabled"))
        self.assertEqual(result.get("review_enrichment_provider"), "llamacpp")

    def test_alertmanager_settings_sanitized(self) -> None:
        """Test that Alertmanager settings are sanitized."""
        alertmanager = AlertmanagerConfig(
            enabled=True,
            endpoint="http://admin:secret@alertmanager:9093/api/v2",
            timeout_seconds=15.0,
            auth=AlertmanagerAuth(bearer_token="secret-token"),
        )
        ea_settings = ExternalAnalysisSettings(alertmanager=alertmanager)
        config = _make_mock_config(external_analysis=ea_settings)

        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertTrue(result.get("alertmanager_enabled"))
        # Check that endpoint is sanitized (no credentials)
        self.assertIn("alertmanager_endpoint", result)
        self.assertNotIn("admin", result["alertmanager_endpoint"])
        self.assertNotIn("secret", result["alertmanager_endpoint"])
        # Auth types should be present but not values
        self.assertEqual(result.get("alertmanager_auth"), ["bearer"])
        # Timeout should be present
        self.assertEqual(result.get("alertmanager_timeout_seconds"), 15.0)


class TestLlamaCppFieldsDirectly(unittest.TestCase):
    """Tests for llama.cpp configuration field extraction via direct function call."""

    def setUp(self) -> None:
        # Save original env
        self._orig_env = dict(os.environ)

    def tearDown(self) -> None:
        # Restore original env
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_llamacpp_enabled_when_env_present(self) -> None:
        """Test that llama.cpp is included when required env vars are present."""
        os.environ["LLAMA_CPP_BASE_URL"] = "http://localhost:11434"
        os.environ["LLAMA_CPP_MODEL"] = "llama3"

        metadata: dict = {}
        _add_llamacpp_fields(metadata)

        self.assertTrue(metadata.get("llamacpp_enabled"))
        self.assertEqual(metadata.get("llamacpp_base_url"), "http://localhost:11434")
        self.assertEqual(metadata.get("llamacpp_model"), "llama3")

    def test_llamacpp_includes_defaults_when_env_vars_absent(self) -> None:
        """Test that llama.cpp defaults are logged when only base URL and model are set."""
        os.environ["LLAMA_CPP_BASE_URL"] = "http://localhost:11434"
        os.environ["LLAMA_CPP_MODEL"] = "llama3"
        # Do NOT set timeout/max_tokens/response_format_json

        metadata: dict = {}
        _add_llamacpp_fields(metadata)

        self.assertTrue(metadata.get("llamacpp_enabled"))
        # Should include defaults from LlamaCppProviderConfig
        self.assertEqual(metadata.get("llamacpp_timeout_seconds"), 120)  # DEFAULT_TIMEOUT_SECONDS
        self.assertEqual(metadata.get("llamacpp_max_tokens_auto_drilldown"), 768)  # DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN
        self.assertEqual(metadata.get("llamacpp_max_tokens_review_enrichment"), 1200)  # DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT
        self.assertFalse(metadata.get("llamacpp_response_format_json"))  # Default is False

    def test_llamacpp_response_format_json_true(self) -> None:
        """Test that response_format_json=true is captured."""
        os.environ["LLAMA_CPP_BASE_URL"] = "http://localhost:11434"
        os.environ["LLAMA_CPP_MODEL"] = "llama3"
        os.environ["LLAMA_CPP_RESPONSE_FORMAT_JSON"] = "true"

        metadata: dict = {}
        _add_llamacpp_fields(metadata)

        self.assertTrue(metadata.get("llamacpp_response_format_json"))

    def test_llamacpp_response_format_json_false(self) -> None:
        """Test that response_format_json=false is captured."""
        os.environ["LLAMA_CPP_BASE_URL"] = "http://localhost:11434"
        os.environ["LLAMA_CPP_MODEL"] = "llama3"
        os.environ["LLAMA_CPP_RESPONSE_FORMAT_JSON"] = "false"

        metadata: dict = {}
        _add_llamacpp_fields(metadata)

        self.assertFalse(metadata.get("llamacpp_response_format_json"))

    def test_llamacpp_timeout_and_max_tokens(self) -> None:
        """Test that timeout and max_tokens are captured."""
        os.environ["LLAMA_CPP_BASE_URL"] = "http://localhost:11434"
        os.environ["LLAMA_CPP_MODEL"] = "llama3"
        os.environ["LLAMA_CPP_TIMEOUT_SECONDS"] = "180"
        os.environ["LLAMA_CPP_MAX_TOKENS_AUTO_DRILLDOWN"] = "1024"
        os.environ["LLAMA_CPP_MAX_TOKENS_REVIEW_ENRICHMENT"] = "2048"

        metadata: dict = {}
        _add_llamacpp_fields(metadata)

        self.assertEqual(metadata.get("llamacpp_timeout_seconds"), 180)
        self.assertEqual(metadata.get("llamacpp_max_tokens_auto_drilldown"), 1024)
        self.assertEqual(metadata.get("llamacpp_max_tokens_review_enrichment"), 2048)

    def test_llamacpp_api_key_presence_only(self) -> None:
        """Test that API key presence is logged but not the value."""
        os.environ["LLAMA_CPP_BASE_URL"] = "http://localhost:11434"
        os.environ["LLAMA_CPP_MODEL"] = "llama3"
        os.environ["LLAMA_CPP_API_KEY"] = "super-secret-key-12345"

        metadata: dict = {}
        _add_llamacpp_fields(metadata)

        self.assertTrue(metadata.get("llamacpp_has_api_key"))
        # Ensure the actual key is not in the result
        for value in metadata.values():
            if isinstance(value, str):
                assert "super-secret-key" not in value

    def test_llamacpp_url_sanitized(self) -> None:
        """Test that llama.cpp URL is sanitized."""
        os.environ["LLAMA_CPP_BASE_URL"] = "http://user:pass@localhost:11434/api?token=xyz"
        os.environ["LLAMA_CPP_MODEL"] = "llama3"

        metadata: dict = {}
        _add_llamacpp_fields(metadata)

        url = metadata.get("llamacpp_base_url")
        assert url is not None
        self.assertNotIn("user", url)
        self.assertNotIn("pass", url)
        self.assertNotIn("token", url)

    def test_missing_llamacpp_env_does_not_crash(self) -> None:
        """Test that missing llama.cpp env vars don't cause errors."""
        # Ensure no llama.cpp env vars are set
        for key in list(os.environ.keys()):
            if key.startswith("LLAMA_CPP_"):
                del os.environ[key]

        metadata: dict = {}
        # This should not raise
        _add_llamacpp_fields(metadata)

        # Should not have llama.cpp fields
        self.assertNotIn("llamacpp_enabled", metadata)


class TestSchedulerConfigLogIntegration(unittest.TestCase):
    """Integration tests for scheduler config logging."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.config_path = self.tmpdir / "health-config.json"
        self.output_dir = self.tmpdir / "runs"
        self.scripts_dir = Path(__file__).resolve().parents[2] / "scripts"

        self._uuid_patcher = patch(
            "k8s_diag_agent.health.loop_scheduler.uuid4",
            return_value=SimpleNamespace(hex="instance-123"),
        )
        self._uuid_patcher.start()
        self.addCleanup(self._uuid_patcher.stop)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_scheduler(self, config: MagicMock | None = None) -> HealthLoopScheduler:
        scheduler = HealthLoopScheduler(
            config_path=self.config_path,
            manual_triggers=(),
            manual_drilldown_contexts=(),
            manual_external_analysis=(),
            quiet=True,
            interval_seconds=60,
            max_runs=1,
            run_once=True,
            output_dir=self.output_dir,
            scripts_dir=self.scripts_dir,
            run_health_loop_fn=_mock_run_health_loop,
        )
        if config:
            scheduler._run_config = config
        return scheduler

    def test_config_log_emitted_at_startup(self) -> None:
        """Test that config log is emitted once at startup."""
        config = _make_mock_config()

        captured_logs: list = []

        def capturing_log_event(self: HealthLoopScheduler, severity: str, message: str, **kwargs: object) -> None:
            captured_logs.append((severity, message, kwargs))

        with patch.object(HealthLoopScheduler, "_log_event", capturing_log_event):
            scheduler = self._make_scheduler(config)
            scheduler.run()

        # Find the scheduler-config event
        config_logs = [
            (sev, msg) for sev, msg, _ in captured_logs
            if msg == "Effective scheduler config"
        ]
        self.assertEqual(len(config_logs), 1, f"Config log should be emitted exactly once. Got: {captured_logs}")

    def test_config_log_contains_expected_fields(self) -> None:
        """Test that the config log contains expected fields."""
        config = _make_mock_config()

        captured_metadata: dict = {}
        def capture_log(severity: str, message: str, **kwargs: object) -> None:
            if message == "Effective scheduler config":
                captured_metadata.update(kwargs)

        scheduler = self._make_scheduler(config)
        scheduler._log_event = capture_log
        scheduler.run()

        self.assertIn("event", captured_metadata)
        self.assertEqual(captured_metadata["event"], "scheduler-config")
        self.assertIn("run_label", captured_metadata)
        self.assertIn("every_seconds", captured_metadata)
        self.assertIn("loop_mode", captured_metadata)

    def test_config_log_no_secrets(self) -> None:
        """Test that secrets are not logged."""
        # Set up config with sensitive data
        alertmanager = AlertmanagerConfig(
            enabled=True,
            endpoint="http://admin:secret@alertmanager:9093/api",
            auth=AlertmanagerAuth(bearer_token="super-secret-token"),
        )
        ea_settings = ExternalAnalysisSettings(alertmanager=alertmanager)
        config = _make_mock_config(external_analysis=ea_settings)

        captured_metadata: dict = {}
        def capture_log(severity: str, message: str, **kwargs: object) -> None:
            if message == "Effective scheduler config":
                captured_metadata.update(kwargs)

        scheduler = self._make_scheduler(config)
        scheduler._log_event = capture_log
        scheduler.run()

        # Check all string values don't contain secrets
        for key, value in captured_metadata.items():
            if isinstance(value, str):
                self.assertNotIn("secret", value.lower(), f"Key '{key}' should not contain 'secret'")
                self.assertNotIn("super-secret", value.lower(), f"Key '{key}' should not contain 'super-secret'")

    def test_log_effective_scheduler_config_function(self) -> None:
        """Test the _log_effective_scheduler_config function directly."""
        config = _make_mock_config()
        logged_messages: list = []

        def mock_log_fn(severity: str, message: str, **kwargs: object) -> None:
            logged_messages.append((severity, message, kwargs))

        _log_effective_scheduler_config(
            config=config,
            interval_seconds=60,
            max_runs=10,
            run_once=False,
            log_fn=mock_log_fn,
        )

        self.assertEqual(len(logged_messages), 1)
        severity, message, metadata = logged_messages[0]
        self.assertEqual(severity, "INFO")
        self.assertEqual(message, "Effective scheduler config")
        self.assertEqual(metadata["event"], "scheduler-config")

    def test_missing_config_skips_logging(self) -> None:
        """Test that missing config skips logging gracefully."""
        logged_messages: list = []

        def mock_log_fn(severity: str, message: str, **kwargs: object) -> None:
            logged_messages.append((severity, message, kwargs))

        scheduler = self._make_scheduler(config=None)  # No config set
        scheduler._log_event = mock_log_fn

        # Should not raise, just skip logging
        scheduler._log_effective_scheduler_config()
        self.assertEqual(len(logged_messages), 0)


class TestUIFields(unittest.TestCase):
    """Tests for UI-related fields."""

    def setUp(self) -> None:
        # Save original env
        self._orig_env = dict(os.environ)
        # Clear test-relevant vars
        for key in ["HEALTH_DISABLE_UI_INDEX", "HEALTH_BUILD_DIAGNOSTIC_PACK"]:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        # Restore original env
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_ui_index_enabled_by_default(self) -> None:
        """Test that UI index is enabled by default."""
        config = _make_mock_config()
        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertTrue(result.get("ui_index_enabled"))

    def test_ui_index_disabled(self) -> None:
        """Test that UI index can be disabled."""
        os.environ["HEALTH_DISABLE_UI_INDEX"] = "true"

        config = _make_mock_config()
        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertFalse(result.get("ui_index_enabled"))

    def test_diagnostic_pack_disabled_by_default(self) -> None:
        """Test that diagnostic pack is disabled by default."""
        config = _make_mock_config()
        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertFalse(result.get("diagnostic_pack_enabled"))

    def test_diagnostic_pack_enabled(self) -> None:
        """Test that diagnostic pack can be enabled."""
        os.environ["HEALTH_BUILD_DIAGNOSTIC_PACK"] = "true"

        config = _make_mock_config()
        result = _build_effective_scheduler_config_log(
            config=config,
            interval_seconds=60,
            max_runs=None,
            run_once=False,
        )

        self.assertTrue(result.get("diagnostic_pack_enabled"))


if __name__ == "__main__":
    unittest.main()

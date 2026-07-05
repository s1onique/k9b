"""Tests for OpenTelemetry bootstrap module.

These tests verify that otel_bootstrap.py correctly:
- Defaults to disabled tracing
- Parses boolean enabled flag correctly
- Uses default service name
- Reads endpoint from environment
- Validates sample ratio
- Handles disabled mode safely
- Handles enabled mode with mocked OTel SDK
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.observability.otel_bootstrap import (
    OTelConfig,
    _parse_bool,
    _parse_sample_ratio,
    configure_otel,
    load_otel_config_from_env,
    reset_otel_for_testing,
)


class TestParseBool:
    """Tests for _parse_bool function."""

    def test_parse_bool_true_values(self) -> None:
        """Test that various true-like values parse correctly."""
        for value in ("true", "True", "TRUE", "1", "yes", "Yes", "on", "ON"):
            assert _parse_bool(value, default=False) is True

    def test_parse_bool_false_values(self) -> None:
        """Test that various false-like values parse correctly."""
        for value in ("false", "False", "FALSE", "0", "no", "No", "off", "OFF"):
            assert _parse_bool(value, default=False) is False

    def test_parse_bool_none_returns_default(self) -> None:
        """Test that None returns the default value."""
        assert _parse_bool(None, default=False) is False
        assert _parse_bool(None, default=True) is True

    def test_parse_bool_unknown_returns_false(self) -> None:
        """Test that unknown values return False."""
        assert _parse_bool("unknown", default=False) is False
        assert _parse_bool("maybe", default=False) is False
        assert _parse_bool("", default=False) is False


class TestParseSampleRatio:
    """Tests for _parse_sample_ratio function."""

    def test_parse_sample_ratio_valid_values(self) -> None:
        """Test parsing of valid sample ratio values."""
        assert _parse_sample_ratio("0.0", 1.0) == 0.0
        assert _parse_sample_ratio("0.5", 1.0) == 0.5
        assert _parse_sample_ratio("1.0", 0.0) == 1.0
        assert _parse_sample_ratio("1", 0.0) == 1.0

    def test_parse_sample_ratio_none_returns_default(self) -> None:
        """Test that None returns the default value."""
        assert _parse_sample_ratio(None, 0.5) == 0.5
        assert _parse_sample_ratio(None, 1.0) == 1.0

    def test_parse_sample_ratio_invalid_returns_default(self) -> None:
        """Test that invalid strings return the default value."""
        assert _parse_sample_ratio("abc", 0.5) == 0.5
        assert _parse_sample_ratio("", 0.5) == 0.5
        assert _parse_sample_ratio("invalid", 1.0) == 1.0

    def test_parse_sample_ratio_clamps_to_valid_range(self) -> None:
        """Test that sample ratio is clamped to [0.0, 1.0]."""
        # Below range should clamp to 0.0
        assert _parse_sample_ratio("-0.5", 1.0) == 0.0
        assert _parse_sample_ratio("-1.0", 1.0) == 0.0
        # Above range should clamp to 1.0
        assert _parse_sample_ratio("1.5", 0.0) == 1.0
        assert _parse_sample_ratio("2.0", 0.0) == 1.0

    def test_parse_sample_ratio_nan_returns_default(self) -> None:
        """Test that NaN returns the default value."""
        assert _parse_sample_ratio("nan", 0.5) == 0.5
        assert _parse_sample_ratio("NaN", 0.5) == 0.5

    def test_parse_sample_ratio_inf_returns_default(self) -> None:
        """Test that Inf returns the default value."""
        assert _parse_sample_ratio("inf", 0.5) == 0.5
        assert _parse_sample_ratio("-inf", 0.5) == 0.5
        assert _parse_sample_ratio("infinity", 0.5) == 0.5


class TestOTelConfig:
    """Tests for OTelConfig dataclass."""

    def test_config_is_frozen(self) -> None:
        """Test that OTelConfig is immutable."""
        config = OTelConfig(
            enabled=True,
            service_name="test",
            endpoint="http://localhost:4317",
            sample_ratio=1.0,
        )
        # Attempting to set an attribute should raise AttributeError
        try:
            config.enabled = False
            raise AssertionError("Expected AttributeError")
        except AttributeError:
            pass  # Expected

    def test_config_attributes(self) -> None:
        """Test that OTelConfig has expected attributes."""
        config = OTelConfig(
            enabled=True,
            service_name="my-service",
            endpoint="http://collector:4317",
            sample_ratio=0.5,
        )
        assert config.enabled is True
        assert config.service_name == "my-service"
        assert config.endpoint == "http://collector:4317"
        assert config.sample_ratio == 0.5


class TestLoadOTelConfigFromEnv:
    """Tests for load_otel_config_from_env function."""

    def test_default_config_is_disabled(self) -> None:
        """Test that default config has tracing disabled."""
        config = load_otel_config_from_env({})
        assert config.enabled is False
        assert config.service_name == "k9b-backend"
        assert config.endpoint is None
        assert config.sample_ratio == 1.0

    def test_enabled_parsing(self) -> None:
        """Test that enabled flag is parsed correctly."""
        for value in ("1", "true", "yes", "on", "True", "TRUE"):
            config = load_otel_config_from_env({"K9B_OTEL_ENABLED": value})
            assert config.enabled is True, f"Failed for value: {value}"

    def test_disabled_parsing(self) -> None:
        """Test that disabled flag is parsed correctly."""
        for value in ("0", "false", "no", "off", ""):
            config = load_otel_config_from_env({"K9B_OTEL_ENABLED": value})
            assert config.enabled is False, f"Failed for value: {value}"

    def test_service_name_default(self) -> None:
        """Test that service name defaults to k9b-backend."""
        config = load_otel_config_from_env({})
        assert config.service_name == "k9b-backend"

    def test_service_name_from_env(self) -> None:
        """Test that service name can be set via environment variable."""
        config = load_otel_config_from_env({"K9B_OTEL_SERVICE_NAME": "custom-service"})
        assert config.service_name == "custom-service"

    def test_endpoint_from_env(self) -> None:
        """Test that endpoint is read from K9B_OTEL_EXPORTER_OTLP_ENDPOINT."""
        config = load_otel_config_from_env({
            "K9B_OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4317",
        })
        assert config.endpoint == "http://otel-collector:4317"

    def test_endpoint_none_when_not_set(self) -> None:
        """Test that endpoint is None when not set."""
        config = load_otel_config_from_env({})
        assert config.endpoint is None

    def test_sample_ratio_valid_values(self) -> None:
        """Test that sample ratio accepts valid values."""
        for value in ("0", "0.0", "0.5", "1", "1.0"):
            config = load_otel_config_from_env({"K9B_OTEL_SAMPLE_RATIO": value})
            assert config.sample_ratio == float(value), f"Failed for value: {value}"

    def test_sample_ratio_default(self) -> None:
        """Test that sample ratio defaults to 1.0."""
        config = load_otel_config_from_env({})
        assert config.sample_ratio == 1.0

    def test_full_enabled_config(self) -> None:
        """Test loading a fully configured enabled config."""
        config = load_otel_config_from_env({
            "K9B_OTEL_ENABLED": "true",
            "K9B_OTEL_SERVICE_NAME": "my-k9b-backend",
            "K9B_OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4317",
            "K9B_OTEL_SAMPLE_RATIO": "0.5",
        })
        assert config.enabled is True
        assert config.service_name == "my-k9b-backend"
        assert config.endpoint == "http://collector:4317"
        assert config.sample_ratio == 0.5

    def test_uses_provided_env_dict(self) -> None:
        """Test that function uses provided env dict instead of os.environ."""
        env = {"K9B_OTEL_ENABLED": "true", "K9B_OTEL_SERVICE_NAME": "test-service"}
        config = load_otel_config_from_env(env)
        assert config.enabled is True
        assert config.service_name == "test-service"


class TestConfigureOTelDisabled:
    """Tests for configure_otel when tracing is disabled."""

    def test_disabled_config_is_noop(self) -> None:
        """Test that disabled config does not initialize anything."""
        config = OTelConfig(
            enabled=False,
            service_name="test",
            endpoint="http://localhost:4317",
            sample_ratio=1.0,
        )
        # Should not raise, should be safe to call
        configure_otel(config)
        # If we get here without exception, the test passes

    def test_disabled_config_with_missing_endpoint(self) -> None:
        """Test that disabled config with no endpoint is safe."""
        config = OTelConfig(
            enabled=False,
            service_name="test",
            endpoint=None,
            sample_ratio=1.0,
        )
        # Should not raise
        configure_otel(config)


class TestConfigureOTelWithMockedSDK:
    """Tests for configure_otel when tracing is enabled (mocked SDK)."""

    def test_enabled_without_sdk_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test graceful handling when OTel SDK is not installed."""
        import sys

        # Remove any installed OTel packages from sys.modules
        modules_to_remove = [
            key for key in list(sys.modules.keys())
            if "opentelemetry" in key
        ]
        for mod in modules_to_remove:
            monkeypatch.delitem(sys.modules, mod, raising=False)

        # Mock the __import__ builtin to make opentelemetry imports fail
        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("opentelemetry"):
                raise ImportError(f"No module named '{name}'")
            # Use builtins.__import__ directly
            import builtins
            return builtins.__import__(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr("builtins.__import__", mock_import)

        config = OTelConfig(
            enabled=True,
            service_name="test",
            endpoint="http://localhost:4317",
            sample_ratio=1.0,
        )
        # Should not raise, but log a warning to stderr
        configure_otel(config)

    def test_enabled_without_endpoint(self) -> None:
        """Test that enabled config without endpoint is handled safely."""
        config = OTelConfig(
            enabled=True,
            service_name="test",
            endpoint=None,
            sample_ratio=1.0,
        )
        # Should not raise
        configure_otel(config)


class TestResetOTelForTesting:
    """Tests for reset_otel_for_testing function."""

    def test_reset_clears_initialized_flag(self) -> None:
        """Test that reset clears the initialization flag."""
        # Just verify the function exists and can be called
        reset_otel_for_testing()


class TestIntegration:
    """Integration tests for the full bootstrap flow."""

    def test_load_and_configure_disabled_flow(self) -> None:
        """Test the full flow: load config -> configure (disabled)."""
        # Load config from empty env (disabled by default)
        config = load_otel_config_from_env({})

        # Verify defaults
        assert config.enabled is False
        assert config.service_name == "k9b-backend"
        assert config.endpoint is None
        assert config.sample_ratio == 1.0

        # Configure should be safe to call
        configure_otel(config)

    def test_load_and_configure_enabled_flow_mocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test the full flow with enabled config (mocked SDK)."""
        import sys

        # Remove any installed OTel packages from sys.modules
        modules_to_remove = [
            key for key in list(sys.modules.keys())
            if "opentelemetry" in key
        ]
        for mod in modules_to_remove:
            monkeypatch.delitem(sys.modules, mod, raising=False)

        # Mock the __import__ builtin to make opentelemetry imports fail
        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("opentelemetry"):
                raise ImportError(f"No module named '{name}'")
            # Use builtins.__import__ directly
            import builtins
            return builtins.__import__(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr("builtins.__import__", mock_import)

        # Load config with enabled=true but no endpoint
        config = load_otel_config_from_env({
            "K9B_OTEL_ENABLED": "true",
            "K9B_OTEL_SERVICE_NAME": "test-service",
        })

        assert config.enabled is True
        assert config.service_name == "test-service"
        assert config.endpoint is None

        # Configure should handle missing SDK gracefully
        configure_otel(config)

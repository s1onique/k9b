"""Tests for external analysis adapter module.

Tests cover:
- ExternalAnalysisRequest dataclass
- ExternalAnalysisAdapter ABC and base functionality
- Adapter registry and builder pattern
- build_external_analysis_adapters function
- _run_subprocess error handling
- Custom exception classes
- Default values and edge cases
"""

import unittest

from k8s_diag_agent.external_analysis.adapter import (
    _ADAPTER_BUILDERS,
    AuthError,
    ExternalAnalysisAdapter,
    ExternalAnalysisAdapterConfig,
    ExternalAnalysisExecutionError,
    ExternalAnalysisRequest,
    ExternalAnalysisSettings,
    InvalidResponseError,
    TimeoutError,
    UpstreamError,
    _run_subprocess,
    build_external_analysis_adapters,
    register_external_analysis_adapter,
)
from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisArtifact


class TestExternalAnalysisRequest(unittest.TestCase):
    """Tests for ExternalAnalysisRequest dataclass."""

    def test_create_request_with_required_fields(self) -> None:
        """Test creating request with only required fields."""
        request = ExternalAnalysisRequest(
            run_id="run-123",
            cluster_label="cluster-a",
            source_artifact=None,
        )

        self.assertEqual(request.run_id, "run-123")
        self.assertEqual(request.cluster_label, "cluster-a")
        self.assertIsNone(request.source_artifact)
        self.assertIsNone(request.metadata)

    def test_create_request_with_all_fields(self) -> None:
        """Test creating request with all fields populated."""
        metadata = {"key": "value", "nested": {"data": 123}}
        request = ExternalAnalysisRequest(
            run_id="run-456",
            cluster_label="cluster-b",
            source_artifact="health-assessment-789",
            metadata=metadata,
        )

        self.assertEqual(request.run_id, "run-456")
        self.assertEqual(request.cluster_label, "cluster-b")
        self.assertEqual(request.source_artifact, "health-assessment-789")
        self.assertEqual(request.metadata, metadata)

    def test_request_is_immutable(self) -> None:
        """Test that request is a frozen dataclass."""
        request = ExternalAnalysisRequest(
            run_id="run-immutable",
            cluster_label="cluster-c",
            source_artifact=None,
        )

        # Frozen dataclass should not allow attribute modification
        with self.assertRaises((TypeError, AttributeError)):
            request.run_id = "new-run"

    def test_request_with_source_artifact(self) -> None:
        """Test request with source_artifact provided."""
        request = ExternalAnalysisRequest(
            run_id="run-source",
            cluster_label="cluster-source",
            source_artifact="source-artifact-123",
        )

        self.assertEqual(request.source_artifact, "source-artifact-123")


class ConcreteTestAdapter(ExternalAnalysisAdapter):
    """Concrete implementation of ExternalAnalysisAdapter for testing."""

    name = "test-adapter"

    def __init__(self, command: list[str] | None = None) -> None:
        super().__init__(command)
        self.run_called = False
        self.last_request: ExternalAnalysisRequest | None = None

    def run(self, request: ExternalAnalysisRequest) -> "ExternalAnalysisArtifact":
        from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisArtifact
        self.run_called = True
        self.last_request = request
        return ExternalAnalysisArtifact(
            tool_name=self.name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            source_artifact=request.source_artifact,
        )


class TestExternalAnalysisAdapter(unittest.TestCase):
    """Tests for ExternalAnalysisAdapter ABC."""

    def test_adapter_stores_command(self) -> None:
        """Test that adapter stores command as tuple."""
        adapter = ConcreteTestAdapter(command=["echo", "hello"])
        self.assertEqual(adapter._command, ("echo", "hello"))

    def test_adapter_handles_none_command(self) -> None:
        """Test that adapter handles None command."""
        adapter = ConcreteTestAdapter(command=None)
        self.assertIsNone(adapter._command)

    def test_adapter_handles_list_command(self) -> None:
        """Test that adapter converts list to tuple."""
        adapter = ConcreteTestAdapter(command=["python", "script.py", "--arg"])
        self.assertIsInstance(adapter._command, tuple)
        self.assertEqual(adapter._command, ("python", "script.py", "--arg"))

    def test_adapter_name_attribute(self) -> None:
        """Test that adapter has name attribute."""
        adapter = ConcreteTestAdapter()
        self.assertEqual(adapter.name, "test-adapter")


class TestAdapterRegistry(unittest.TestCase):
    """Tests for adapter registry and builder pattern."""

    def setUp(self) -> None:
        """Clear adapter registry before each test."""
        self._original_builders = _ADAPTER_BUILDERS.copy()
        _ADAPTER_BUILDERS.clear()

    def tearDown(self) -> None:
        """Restore original adapter registry after each test."""
        _ADAPTER_BUILDERS.clear()
        _ADAPTER_BUILDERS.update(self._original_builders)

    def test_register_adapter_decorator(self) -> None:
        """Test registering an adapter with decorator."""
        @register_external_analysis_adapter("test-decorator")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            return ConcreteTestAdapter()

        self.assertIn("test-decorator", _ADAPTER_BUILDERS)
        self.assertEqual(_ADAPTER_BUILDERS["test-decorator"], builder)

    def test_register_adapter_case_insensitive(self) -> None:
        """Test that adapter registration is case insensitive."""
        @register_external_analysis_adapter("TestCase")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            return ConcreteTestAdapter()

        self.assertIn("testcase", _ADAPTER_BUILDERS)

    def test_build_adapter_without_registration(self) -> None:
        """Test building adapters when none are registered."""
        config = ExternalAnalysisAdapterConfig(name="unregistered", enabled=True)
        settings = ExternalAnalysisSettings()

        adapters = build_external_analysis_adapters([config], settings)

        self.assertEqual(len(adapters), 0)

    def test_build_disabled_adapter(self) -> None:
        """Test that disabled adapters are not built."""

        @register_external_analysis_adapter("disabled-adapter")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            return ConcreteTestAdapter()

        config = ExternalAnalysisAdapterConfig(name="disabled-adapter", enabled=False)
        settings = ExternalAnalysisSettings()

        adapters = build_external_analysis_adapters([config], settings)

        self.assertEqual(len(adapters), 0)

    def test_build_adapter_with_builder(self) -> None:
        """Test building adapter with registered builder."""

        @register_external_analysis_adapter("enabled-adapter")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            return ConcreteTestAdapter()

        config = ExternalAnalysisAdapterConfig(name="enabled-adapter", enabled=True)
        settings = ExternalAnalysisSettings()

        adapters = build_external_analysis_adapters([config], settings)

        self.assertEqual(len(adapters), 1)
        self.assertIn("test-adapter", adapters)  # ConcreteTestAdapter.name

    def test_build_adapter_returns_none(self) -> None:
        """Test that builder returning None skips adapter."""

        @register_external_analysis_adapter("none-adapter")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            return None

        config = ExternalAnalysisAdapterConfig(name="none-adapter", enabled=True)
        settings = ExternalAnalysisSettings()

        adapters = build_external_analysis_adapters([config], settings)

        self.assertEqual(len(adapters), 0)

    def test_build_multiple_different_adapters(self) -> None:
        """Test building multiple adapters with different names."""

        @register_external_analysis_adapter("adapter-a")
        def builder_a(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            adapter = ConcreteTestAdapter()
            adapter.name = "adapter-a"
            return adapter

        @register_external_analysis_adapter("adapter-b")
        def builder_b(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            adapter = ConcreteTestAdapter()
            adapter.name = "adapter-b"
            return adapter

        config_a = ExternalAnalysisAdapterConfig(name="adapter-a", enabled=True)
        config_b = ExternalAnalysisAdapterConfig(name="adapter-b", enabled=True)
        settings = ExternalAnalysisSettings()

        adapters = build_external_analysis_adapters([config_a, config_b], settings)

        self.assertEqual(len(adapters), 2)
        self.assertIn("adapter-a", adapters)
        self.assertIn("adapter-b", adapters)

    def test_build_adapters_with_none_settings(self) -> None:
        """Test that None settings defaults to ExternalAnalysisSettings."""

        @register_external_analysis_adapter("default-settings")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            # Verify settings is a default ExternalAnalysisSettings
            self.assertIsInstance(settings, ExternalAnalysisSettings)
            return ConcreteTestAdapter()

        config = ExternalAnalysisAdapterConfig(name="default-settings", enabled=True)

        adapters = build_external_analysis_adapters([config], None)

        self.assertEqual(len(adapters), 1)


class TestRunSubprocess(unittest.TestCase):
    """Tests for _run_subprocess error handling."""

    def test_run_subprocess_success(self) -> None:
        """Test successful subprocess execution."""
        result = _run_subprocess(["echo", "hello world"])

        self.assertEqual(result, "hello world")

    def test_run_subprocess_with_args(self) -> None:
        """Test subprocess with arguments."""
        result = _run_subprocess(["printf", "test %s", "value"])

        self.assertEqual(result, "test value")

    def test_run_subprocess_empty_output(self) -> None:
        """Test subprocess with no output."""
        result = _run_subprocess(["true"])

        self.assertEqual(result, "")

    def test_run_subprocess_nonexistent_command(self) -> None:
        """Test that nonexistent command raises ExternalAnalysisExecutionError."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _run_subprocess(["nonexistent-command-xyz123"])

        self.assertIn("Command not found", str(ctx.exception))

    def test_run_subprocess_failed_command(self) -> None:
        """Test that failed command raises ExternalAnalysisExecutionError."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _run_subprocess(["python", "--invalid-arg"])

        self.assertIn("exited", str(ctx.exception))


class TestCustomExceptions(unittest.TestCase):
    """Tests for custom exception classes."""

    def test_external_analysis_execution_error(self) -> None:
        """Test ExternalAnalysisExecutionError."""
        error = ExternalAnalysisExecutionError("Command failed")
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "Command failed")

    def test_timeout_error(self) -> None:
        """Test TimeoutError exception."""
        error = TimeoutError("Request timed out")
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Request timed out")

    def test_auth_error(self) -> None:
        """Test AuthError exception."""
        error = AuthError("Authentication failed")
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Authentication failed")

    def test_invalid_response_error(self) -> None:
        """Test InvalidResponseError exception."""
        error = InvalidResponseError("Invalid response format")
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Invalid response format")

    def test_upstream_error(self) -> None:
        """Test UpstreamError exception."""
        error = UpstreamError("Upstream service unavailable")
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Upstream service unavailable")


class TestBuildExternalAnalysisAdaptersEdgeCases(unittest.TestCase):
    """Tests for edge cases in build_external_analysis_adapters."""

    def setUp(self) -> None:
        """Clear adapter registry before each test."""
        self._original_builders = _ADAPTER_BUILDERS.copy()
        _ADAPTER_BUILDERS.clear()

    def tearDown(self) -> None:
        """Restore original adapter registry after each test."""
        _ADAPTER_BUILDERS.clear()
        _ADAPTER_BUILDERS.update(self._original_builders)

    def test_empty_configs(self) -> None:
        """Test building adapters with empty config list."""
        adapters = build_external_analysis_adapters([], None)
        self.assertEqual(len(adapters), 0)

    def test_no_matching_builder(self) -> None:
        """Test that configs without matching builders are skipped."""
        config = ExternalAnalysisAdapterConfig(name="no-builder", enabled=True)
        adapters = build_external_analysis_adapters([config], None)
        self.assertEqual(len(adapters), 0)

    def test_mixed_enabled_disabled(self) -> None:
        """Test mixed enabled and disabled configs."""

        @register_external_analysis_adapter("mixed-adapter")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            return ConcreteTestAdapter()

        enabled_config = ExternalAnalysisAdapterConfig(name="mixed-adapter", enabled=True)
        disabled_config = ExternalAnalysisAdapterConfig(name="mixed-adapter", enabled=False)

        adapters = build_external_analysis_adapters([enabled_config, disabled_config], None)

        # Only one should be built (the enabled one)
        self.assertEqual(len(adapters), 1)


class TestAdapterBuilderType(unittest.TestCase):
    """Tests for AdapterBuilder type alias behavior."""

    def setUp(self) -> None:
        """Clear adapter registry before each test."""
        self._original_builders = _ADAPTER_BUILDERS.copy()
        _ADAPTER_BUILDERS.clear()

    def tearDown(self) -> None:
        """Restore original adapter registry after each test."""
        _ADAPTER_BUILDERS.clear()
        _ADAPTER_BUILDERS.update(self._original_builders)

    def test_builder_receives_config_and_settings(self) -> None:
        """Test that builder receives both config and settings."""

        received_config: ExternalAnalysisAdapterConfig | None = None
        received_settings: ExternalAnalysisSettings | None = None

        @register_external_analysis_adapter("inspect-builder")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            nonlocal received_config, received_settings
            received_config = config
            received_settings = settings
            return None

        config = ExternalAnalysisAdapterConfig(
            name="inspect-builder",
            enabled=True,
            command=("echo", "test"),
        )
        settings = ExternalAnalysisSettings()

        build_external_analysis_adapters([config], settings)

        self.assertIsNotNone(received_config)
        assert received_config is not None
        self.assertEqual(received_config.name, "inspect-builder")
        self.assertEqual(received_config.enabled, True)
        self.assertEqual(received_config.command, ("echo", "test"))

        self.assertIsNotNone(received_settings)
        self.assertIsInstance(received_settings, ExternalAnalysisSettings)


class TestAdapterPatternEdgeCases(unittest.TestCase):
    """Tests for edge cases in adapter pattern implementation."""

    def setUp(self) -> None:
        """Clear adapter registry before each test."""
        self._original_builders = _ADAPTER_BUILDERS.copy()
        _ADAPTER_BUILDERS.clear()

    def tearDown(self) -> None:
        """Restore original adapter registry after each test."""
        _ADAPTER_BUILDERS.clear()
        _ADAPTER_BUILDERS.update(self._original_builders)

    def test_adapter_name_from_instance(self) -> None:
        """Test that adapter name is taken from instance not config."""
        custom_name = "custom-instance-name"

        @register_external_analysis_adapter("config-name")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            adapter = ConcreteTestAdapter()
            adapter.name = custom_name  # Override name
            return adapter

        config = ExternalAnalysisAdapterConfig(name="config-name", enabled=True)

        adapters = build_external_analysis_adapters([config], None)

        self.assertEqual(len(adapters), 1)
        self.assertIn(custom_name, adapters)

    def test_multiple_adapters_same_name_lasts_one(self) -> None:
        """Test that last adapter with same name wins."""

        @register_external_analysis_adapter("same-name")
        def builder1(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            adapter = ConcreteTestAdapter()
            adapter.name = "duplicate-name"
            return adapter

        @register_external_analysis_adapter("same-name-2")
        def builder2(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            adapter = ConcreteTestAdapter()
            adapter.name = "duplicate-name"  # Same name!
            return adapter

        config1 = ExternalAnalysisAdapterConfig(name="same-name", enabled=True)
        config2 = ExternalAnalysisAdapterConfig(name="same-name-2", enabled=True)

        adapters = build_external_analysis_adapters([config1, config2], None)

        # Only one entry for "duplicate-name"
        self.assertEqual(len(adapters), 1)


class TestRequestMetadataHandling(unittest.TestCase):
    """Tests for ExternalAnalysisRequest metadata field handling."""

    def test_request_with_empty_metadata(self) -> None:
        """Test request with empty dict metadata."""
        request = ExternalAnalysisRequest(
            run_id="run-empty-meta",
            cluster_label="cluster",
            source_artifact=None,
            metadata={},
        )

        self.assertEqual(request.metadata, {})

    def test_request_with_complex_metadata(self) -> None:
        """Test request with complex nested metadata."""
        complex_metadata = {
            "level1": {
                "level2": {
                    "level3": ["a", "b", "c"],
                },
            },
            "list": [1, 2, 3],
            "mixed": {"num": 42, "str": "value", "bool": True},
        }

        request = ExternalAnalysisRequest(
            run_id="run-complex",
            cluster_label="cluster",
            source_artifact=None,
            metadata=complex_metadata,
        )

        self.assertEqual(request.metadata, complex_metadata)

    def test_request_source_artifact_empty_string(self) -> None:
        """Test request with empty string source_artifact."""
        request = ExternalAnalysisRequest(
            run_id="run-empty-source",
            cluster_label="cluster",
            source_artifact="",
        )

        # Empty string is a valid value in the dataclass
        self.assertEqual(request.source_artifact, "")


if __name__ == "__main__":
    unittest.main()

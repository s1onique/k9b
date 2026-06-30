"""Tests for external analysis adapter module.

Tests cover:
- ExternalAnalysisRequest dataclass
- ExternalAnalysisAdapter ABC and base functionality
- Adapter registry and builder pattern
- build_external_analysis_adapters function
- _run_subprocess error handling
- Custom exception classes
- Default values and edge cases
- Command validation (REM-S3)
"""

import unittest
from typing import Any
from unittest.mock import patch

from k8s_diag_agent.external_analysis.adapter import (
    _ADAPTER_BUILDERS,
    _ALLOWED_COMMAND_FAMILIES,
    _BLOCKED_COMMAND_FAMILIES,
    _SHELL_METACHAR_PATTERN,
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
    _validate_command_for_execution,
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
            request.run_id = "new-run"  # type: ignore[misc]

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
        # The key is the normalized config name, not the adapter class's name attribute
        self.assertIn("enabled-adapter", adapters)

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
        """Test successful subprocess execution with allowed command."""
        mock_result = unittest.mock.Mock()
        mock_result.stdout = "command output"
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = _run_subprocess(["k8sgpt", "--help"])
            self.assertEqual(result, "command output")

    def test_run_subprocess_with_args(self) -> None:
        """Test subprocess with arguments using allowed command."""
        mock_result = unittest.mock.Mock()
        mock_result.stdout = "analysis result"
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = _run_subprocess(["llamacpp", "analyze", "--model", "test.gguf"])
            self.assertEqual(result, "analysis result")

    def test_run_subprocess_empty_output(self) -> None:
        """Test subprocess that exits successfully with no output."""
        mock_result = unittest.mock.Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = _run_subprocess(["llama-cli", "--version"])
            self.assertEqual(result, "")

    def test_run_subprocess_nonexistent_command(self) -> None:
        """Test that nonexistent command raises ExternalAnalysisExecutionError."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _run_subprocess(["nonexistent-command-xyz123"])

        self.assertIn("not a recognized", str(ctx.exception))

    def test_run_subprocess_failed_command(self) -> None:
        """Test that failed command raises ExternalAnalysisExecutionError."""
        import subprocess
        mock_result = unittest.mock.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: invalid option"

        def fake_run(cmd: list[str], **kwargs: Any) -> Any:
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd, output="", stderr="error: invalid option"
            )

        with patch("subprocess.run", side_effect=fake_run):
            with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
                _run_subprocess(["llamacpp", "--invalid-option"])

            self.assertIn("exited", str(ctx.exception))
            self.assertIn("llamacpp", str(ctx.exception))

    def test_run_subprocess_timeout(self) -> None:
        """Test that subprocess.TimeoutExpired is converted to ExternalAnalysisExecutionError."""
        import subprocess

        from k8s_diag_agent.external_analysis.adapter import (
            EXTERNAL_ANALYSIS_TIMEOUT_SECONDS,
            _run_subprocess,
        )

        def fake_run(cmd: list[str], **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=EXTERNAL_ANALYSIS_TIMEOUT_SECONDS)

        with patch("subprocess.run", side_effect=fake_run):
            with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
                _run_subprocess(["k8sgpt", "analysis", "--sensitive-arg", "secret-value"])

            error_msg = str(ctx.exception)
            self.assertIn("timed out", error_msg)
            self.assertIn(str(EXTERNAL_ANALYSIS_TIMEOUT_SECONDS), error_msg)
            # Verify only safe command summary is included (first element only)
            self.assertIn("k8sgpt", error_msg)
            self.assertNotIn("sensitive-arg", error_msg)
            self.assertNotIn("secret-value", error_msg)

    def test_run_subprocess_timeout_error_message_safe(self) -> None:
        """Test that timeout error message doesn't leak sensitive command args."""
        import subprocess

        from k8s_diag_agent.external_analysis.adapter import (
            EXTERNAL_ANALYSIS_TIMEOUT_SECONDS,
            _run_subprocess,
        )

        def fake_run(cmd: list[str], **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=EXTERNAL_ANALYSIS_TIMEOUT_SECONDS)

        sensitive_commands = [
            ["kubectl", "get", "secrets", "--token=super-secret"],
            ["helm", "install", "--kubeconfig=/path/to/sensitive/config"],
            ["k8sgpt", "analyze", "--password=secret123"],
        ]

        for cmd in sensitive_commands:
            with patch("subprocess.run", side_effect=fake_run):
                with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
                    _run_subprocess(cmd)

                error_msg = str(ctx.exception)
                # Only the first command element should appear
                self.assertIn(cmd[0], error_msg)
                # Sensitive args should not appear
                for part in cmd[1:]:
                    self.assertNotIn(part, error_msg)


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

    def test_adapter_key_uses_normalized_config_name(self) -> None:
        """Test that adapter dict key is the normalized config name, not adapter instance name.

        The adapter instance's name attribute can differ from the config name.
        The dict key is determined by the normalized config name, not adapter.name.
        """
        custom_instance_name = "custom-instance-name"

        @register_external_analysis_adapter("config-name")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            adapter = ConcreteTestAdapter()
            adapter.name = custom_instance_name  # Override instance name
            return adapter

        config = ExternalAnalysisAdapterConfig(name="config-name", enabled=True)

        adapters = build_external_analysis_adapters([config], None)

        self.assertEqual(len(adapters), 1)
        # The key is the normalized config name, not the adapter instance name
        self.assertIn("config-name", adapters)
        self.assertNotIn(custom_instance_name, adapters)
        # Verify the adapter instance has the custom name
        self.assertEqual(adapters["config-name"].name, custom_instance_name)

    def test_multiple_adapters_same_normalized_name_lasts_one(self) -> None:
        """Test that adapters with the same normalized config name collapse to one entry.

        This verifies the legacy → canonical adapter name behavior (llamacpp → openai_compatible).
        When two configs have names that normalize to the same key, only the last one wins.
        """

        @register_external_analysis_adapter("openai_compatible")
        def builder(
            config: ExternalAnalysisAdapterConfig,
            settings: ExternalAnalysisSettings,
        ) -> ExternalAnalysisAdapter | None:
            adapter = ConcreteTestAdapter()
            # Track which config was used via the command field
            adapter._test_config_name = config.name
            return adapter

        # First config uses legacy name "llamacpp" which normalizes to "openai_compatible"
        config1 = ExternalAnalysisAdapterConfig(
            name="llamacpp",
            enabled=True,
            command=("first",),
        )
        # Second config uses canonical name "openai_compatible"
        config2 = ExternalAnalysisAdapterConfig(
            name="openai_compatible",
            enabled=True,
            command=("second",),
        )

        adapters = build_external_analysis_adapters([config1, config2], None)

        # Both configs normalize to "openai_compatible", so only one entry remains (last wins)
        self.assertEqual(1, len(adapters))
        self.assertIn("openai_compatible", adapters)

        # The second config (canonical name) should be the one that wins
        adapter = adapters["openai_compatible"]
        self.assertEqual("openai_compatible", adapter._test_config_name)

    def test_different_normalized_names_keep_all_adapters(self) -> None:
        """Test that adapters with different normalized config names are all kept."""

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

        adapters = build_external_analysis_adapters([config_a, config_b], None)

        # Both adapters with different normalized names should be kept
        self.assertEqual(2, len(adapters))
        self.assertIn("adapter-a", adapters)
        self.assertIn("adapter-b", adapters)


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


class TestValidateCommandForExecution(unittest.TestCase):
    """Tests for _validate_command_for_execution (REM-S3)."""

    # === Allowed Commands Tests ===

    def test_accepts_k8sgpt_command(self) -> None:
        """Test that k8sgpt command is accepted."""
        _validate_command_for_execution(["k8sgpt", "analysis", "--explain"])

    def test_accepts_k8sgpt_with_path(self) -> None:
        """Test that k8sgpt with path prefix is accepted."""
        _validate_command_for_execution(["/usr/local/bin/k8sgpt", "analysis"])

    def test_accepts_llamacpp_command(self) -> None:
        """Test that llamacpp command is accepted."""
        _validate_command_for_execution(["llamacpp", "analyze", "--model", "model.gguf"])

    def test_accepts_llama_cli_command(self) -> None:
        """Test that llama-cli command is accepted."""
        _validate_command_for_execution(["llama-cli", "-m", "model.gguf", "-p", "prompt"])

    def test_accepts_llama_cpp_with_dots_command(self) -> None:
        """Test that llama.cpp command is accepted."""
        _validate_command_for_execution(["llama.cpp", "--help"])

    def test_accepts_command_case_insensitive(self) -> None:
        """Test that command matching is case-insensitive."""
        _validate_command_for_execution(["K8SGPT", "analysis"])
        _validate_command_for_execution(["K8sGpt", "analysis"])
        _validate_command_for_execution(["LLAMACPP", "--help"])

    # === Blocked Commands Tests ===

    def test_rejects_shell_interpreters(self) -> None:
        """Test that shell interpreters are rejected."""
        for shell in ["sh", "bash", "zsh", "fish", "dash"]:
            with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
                _validate_command_for_execution([shell, "-c", "echo test"])
            self.assertIn("not allowed", str(ctx.exception))

    def test_rejects_scripting_languages(self) -> None:
        """Test that scripting language interpreters are rejected."""
        blocked = ["python", "python3", "python2", "perl", "ruby", "node", "php", "lua"]
        for lang in blocked:
            with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
                _validate_command_for_execution([lang, "script"])
            self.assertIn("not allowed", str(ctx.exception))

    def test_rejects_network_tools(self) -> None:
        """Test that network tools are rejected."""
        for tool in ["curl", "wget", "nc", "netcat", "socat", "ncat", "openssl"]:
            with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
                _validate_command_for_execution([tool, "https://example.com"])
            self.assertIn("not allowed", str(ctx.exception))

    def test_rejects_kubectl(self) -> None:
        """Test that kubectl is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["kubectl", "get", "pods"])
        self.assertIn("not allowed", str(ctx.exception))

    def test_rejects_helm(self) -> None:
        """Test that helm is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["helm", "list"])
        self.assertIn("not allowed", str(ctx.exception))

    def test_rejects_docker(self) -> None:
        """Test that docker/podman are rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["docker", "ps"])
        self.assertIn("not allowed", str(ctx.exception))

    def test_rejects_ssh(self) -> None:
        """Test that ssh and remote access tools are rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["ssh", "user@host"])
        self.assertIn("not allowed", str(ctx.exception))

    # === Unrecognized Commands Tests ===

    def test_rejects_unknown_commands(self) -> None:
        """Test that unknown commands are rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["unknown-binary", "arg"])
        self.assertIn("not a recognized external analysis tool", str(ctx.exception))

    def test_rejects_custom_arbitrary_command(self) -> None:
        """Test that arbitrary local binaries are rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["my-custom-tool", "--flag"])
        self.assertIn("not a recognized external analysis tool", str(ctx.exception))

    # === Shell Metacharacter Tests ===

    def test_rejects_command_with_semicolon_in_name(self) -> None:
        """Test that command with semicolon is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["cmd;sleep", "1"])
        self.assertIn("unsupported characters", str(ctx.exception))

    def test_rejects_command_with_pipe_in_name(self) -> None:
        """Test that command with pipe is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["cmd|cat", "arg"])
        self.assertIn("unsupported characters", str(ctx.exception))

    def test_rejects_command_with_backtick_in_name(self) -> None:
        """Test that command with backtick is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["cmd`id`", "arg"])
        self.assertIn("unsupported characters", str(ctx.exception))

    def test_rejects_command_with_dollar_in_name(self) -> None:
        """Test that command with dollar sign is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["cmd$(whoami)", "arg"])
        self.assertIn("unsupported characters", str(ctx.exception))

    def test_rejects_command_with_newline_in_name(self) -> None:
        """Test that command with newline is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["cmd\nid", "arg"])
        self.assertIn("unsupported characters", str(ctx.exception))

    # === Empty/Invalid Input Tests ===

    def test_rejects_empty_command(self) -> None:
        """Test that empty command is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution([])
        self.assertIn("empty command", str(ctx.exception))

    def test_rejects_none_command(self) -> None:
        """Test that None command is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(None)  # type: ignore[arg-type]
        self.assertIn("empty command", str(ctx.exception))

    def test_rejects_string_command(self) -> None:
        """Test that string command (not list) is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution("echo hello")
        self.assertIn("must be a list", str(ctx.exception))

    def test_rejects_non_string_command_name(self) -> None:
        """Test that non-string command name is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution([123, "arg"])  # type: ignore[list-item]
        self.assertIn("must be a string", str(ctx.exception))

    # === Path Stripping Tests ===

    def test_strips_path_from_command_name(self) -> None:
        """Test that path components are stripped before checking."""
        # /usr/bin/k8sgpt should be recognized as k8sgpt
        _validate_command_for_execution(["/usr/bin/k8sgpt", "analysis"])
        _validate_command_for_execution(["/home/user/.local/bin/k8sgpt", "analysis"])

    def test_rejects_path_to_blocked_binary(self) -> None:
        """Test that path to blocked binary is rejected."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["/usr/bin/python", "script.py"])
        self.assertIn("not allowed", str(ctx.exception))

    # === Edge Cases ===

    def test_accepts_allowed_command_with_many_args(self) -> None:
        """Test that allowed command with many args is accepted."""
        cmd = ["k8sgpt", "analysis", "--kubecontext", "prod", "--namespace", "default", "--explain", "--no-cache"]
        _validate_command_for_execution(cmd)

    def test_error_message_safe(self) -> None:
        """Test that error messages do not leak sensitive arguments."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _validate_command_for_execution(["curl", "https://api.example.com/token=secret"])
        error_msg = str(ctx.exception)
        # Should mention the blocked command but not the full URL with token
        self.assertIn("curl", error_msg)
        self.assertNotIn("token=secret", error_msg)


class TestAllowedCommandFamilies(unittest.TestCase):
    """Tests for _ALLOWED_COMMAND_FAMILIES constant."""

    def test_contains_expected_families(self) -> None:
        """Test that allowed families contain expected commands."""
        expected = {"k8sgpt", "llamacpp", "llama-cli", "llama.cpp"}
        self.assertEqual(_ALLOWED_COMMAND_FAMILIES, expected)


class TestBlockedCommandFamilies(unittest.TestCase):
    """Tests for _BLOCKED_COMMAND_FAMILIES constant."""

    def test_contains_shells(self) -> None:
        """Test that blocked families include shell interpreters."""
        shells = {"sh", "bash", "zsh", "fish", "dash"}
        for shell in shells:
            self.assertIn(shell, _BLOCKED_COMMAND_FAMILIES)

    def test_contains_scripting_languages(self) -> None:
        """Test that blocked families include scripting languages."""
        languages = {"python", "python3", "perl", "ruby", "node", "php", "lua"}
        for lang in languages:
            self.assertIn(lang, _BLOCKED_COMMAND_FAMILIES)

    def test_contains_network_tools(self) -> None:
        """Test that blocked families include network tools."""
        tools = {"curl", "wget", "nc", "netcat", "socat"}
        for tool in tools:
            self.assertIn(tool, _BLOCKED_COMMAND_FAMILIES)

    def test_contains_kubectl_helm(self) -> None:
        """Test that kubectl and helm are blocked."""
        self.assertIn("kubectl", _BLOCKED_COMMAND_FAMILIES)
        self.assertIn("helm", _BLOCKED_COMMAND_FAMILIES)


class TestShellMetacharPattern(unittest.TestCase):
    """Tests for _SHELL_METACHAR_PATTERN regex."""

    def test_matches_semicolon(self) -> None:
        """Test that semicolon is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd;"))

    def test_matches_pipe(self) -> None:
        """Test that pipe is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd|"))

    def test_matches_ampersand(self) -> None:
        """Test that ampersand is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd&"))

    def test_matches_backtick(self) -> None:
        """Test that backtick is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd`"))

    def test_matches_dollar(self) -> None:
        """Test that dollar is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd$"))

    def test_matches_less_than(self) -> None:
        """Test that less-than is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd<"))

    def test_matches_greater_than(self) -> None:
        """Test that greater-than is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd>"))

    def test_matches_newline(self) -> None:
        """Test that newline is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd\n"))

    def test_matches_carriage_return(self) -> None:
        """Test that carriage return is matched."""
        self.assertIsNotNone(_SHELL_METACHAR_PATTERN.search("cmd\r"))

    def test_no_match_for_normal_command(self) -> None:
        """Test that normal command names don't match."""
        self.assertIsNone(_SHELL_METACHAR_PATTERN.search("k8sgpt"))
        self.assertIsNone(_SHELL_METACHAR_PATTERN.search("llama-cli"))
        self.assertIsNone(_SHELL_METACHAR_PATTERN.search("/usr/bin/k8sgpt"))


class TestRunSubprocessWithValidation(unittest.TestCase):
    """Tests for _run_subprocess with command validation (REM-S3)."""

    def test_subprocess_rejects_blocked_command(self) -> None:
        """Test that _run_subprocess rejects blocked commands before execution."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _run_subprocess(["curl", "https://example.com"])
        self.assertIn("not allowed", str(ctx.exception))

    def test_subprocess_rejects_unknown_command(self) -> None:
        """Test that _run_subprocess rejects unknown commands before execution."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _run_subprocess(["unknown-tool", "arg"])
        self.assertIn("not a recognized", str(ctx.exception))

    def test_subprocess_rejects_empty_command(self) -> None:
        """Test that _run_subprocess rejects empty commands."""
        with self.assertRaises(ExternalAnalysisExecutionError) as ctx:
            _run_subprocess([])
        self.assertIn("empty command", str(ctx.exception))

    def test_subprocess_accepts_k8sgpt(self) -> None:
        """Test that _run_subprocess accepts k8sgpt command."""
        mock_result = unittest.mock.Mock()
        mock_result.stdout = "k8sgpt version 0.1.0"
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = _run_subprocess(["k8sgpt", "version"])
            self.assertEqual(result, "k8sgpt version 0.1.0")


if __name__ == "__main__":
    unittest.main()

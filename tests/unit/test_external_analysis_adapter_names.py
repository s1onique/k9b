"""Tests for external analysis adapter name normalization (Phase 2 of llamacpp rename epic).

These tests verify that:
- 'openai_compatible' is the canonical adapter name
- 'llamacpp' is a legacy alias that normalizes to 'openai_compatible'
- Legacy name emits structured logging warning (not DeprecationWarning)
- Both names resolve to the same adapter behavior
- Error messages list sorted available names
"""

import logging
import logging.handlers
import unittest

from k8s_diag_agent.external_analysis.adapter import (
    _ADAPTER_BUILDERS,
    LEGACY_LLAMACPP_ADAPTER_NAME,
    OPENAI_COMPATIBLE_ADAPTER_NAME,
    build_external_analysis_adapters,
    get_available_adapter_names,
    normalize_adapter_name,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisAdapterConfig,
)


class TestCanonicalAdapterNameConstants(unittest.TestCase):
    """Test that adapter name constants are correctly defined."""

    def test_openai_compatible_canonical_name(self) -> None:
        """Canonical adapter name should be 'openai_compatible'."""
        self.assertEqual(OPENAI_COMPATIBLE_ADAPTER_NAME, "openai_compatible")

    def test_llamacpp_legacy_name(self) -> None:
        """Legacy adapter name should be 'llamacpp'."""
        self.assertEqual(LEGACY_LLAMACPP_ADAPTER_NAME, "llamacpp")


class TestNormalizeAdapterName(unittest.TestCase):
    """Test adapter name normalization."""

    def test_openai_compatible_normalizes_to_self(self) -> None:
        """'openai_compatible' should normalize to 'openai_compatible'."""
        result = normalize_adapter_name("openai_compatible")
        self.assertEqual(result, "openai_compatible")

    def test_openai_compatible_case_insensitive(self) -> None:
        """Case variations of 'openai_compatible' should all normalize correctly."""
        result = normalize_adapter_name("OpenAI_Compatible")
        self.assertEqual(result, "openai_compatible")
        result = normalize_adapter_name("OPENAI_COMPATIBLE")
        self.assertEqual(result, "openai_compatible")
        result = normalize_adapter_name("OpEnAi_CoMpAtIbLe")
        self.assertEqual(result, "openai_compatible")

    def test_llamacpp_normalizes_to_openai_compatible(self) -> None:
        """'llamacpp' should normalize to 'openai_compatible'."""
        result = normalize_adapter_name("llamacpp")
        self.assertEqual(result, OPENAI_COMPATIBLE_ADAPTER_NAME)

    def test_llamacpp_case_insensitive(self) -> None:
        """Case variations of 'llamacpp' should normalize to 'openai_compatible'."""
        result = normalize_adapter_name("LlamaCpp")
        self.assertEqual(result, OPENAI_COMPATIBLE_ADAPTER_NAME)
        result = normalize_adapter_name("LLAMACPP")
        self.assertEqual(result, OPENAI_COMPATIBLE_ADAPTER_NAME)

    def test_unknown_names_pass_through(self) -> None:
        """Unknown adapter names should pass through unchanged."""
        result = normalize_adapter_name("k8sgpt")
        self.assertEqual(result, "k8sgpt")
        result = normalize_adapter_name("unknown-adapter")
        self.assertEqual(result, "unknown-adapter")


class TestNormalizeAdapterNameEmitsStructuredWarning(unittest.TestCase):
    """Test that normalize_adapter_name emits structured logging warning for llamacpp."""

    def setUp(self) -> None:
        """Clear the deprecation warning tracker before each test."""
        # Import the module-level tracker and clear it
        from k8s_diag_agent.external_analysis import adapter as adapter_module
        adapter_module._DEPRECATION_WARNING_LOGGED.clear()
        # Set up logging capture for the adapter module
        self._logger = logging.getLogger("k8s_diag_agent.external_analysis.adapter")
        self._handler = logging.handlers.MemoryHandler(capacity=100)
        self._handler.setLevel(logging.WARNING)
        self._logger.addHandler(self._handler)
        self._original_level = self._logger.level
        self._logger.setLevel(logging.WARNING)

    def tearDown(self) -> None:
        """Restore logger state."""
        self._logger.removeHandler(self._handler)
        self._handler.close()
        self._logger.setLevel(self._original_level)

    def test_llamacpp_emits_structured_warning(self) -> None:
        """Calling normalize_adapter_name with 'llamacpp' should emit a structured warning."""
        normalize_adapter_name("llamacpp")

        # Check that a WARNING was logged
        records = self._handler.buffer
        warning_records = [r for r in records if r.levelno == logging.WARNING]
        self.assertTrue(
            len(warning_records) > 0,
            f"Expected at least one WARNING log for 'llamacpp', got {len(records)} total records"
        )
        # Verify the structured extra dict contains expected keys
        # Note: logging.Logger.warning(..., extra={...}) merges keys directly onto the record
        found_warning = False
        for record in warning_records:
            if (
                getattr(record, "event", None) == "deprecated-provider-alias"
                and getattr(record, "provider", None) == "llamacpp"
                and getattr(record, "replacement", None) == "openai_compatible"
            ):
                found_warning = True
                break
        self.assertTrue(
            found_warning,
            f"Expected structured warning with event='deprecated-provider-alias'. Records: {[r.__dict__ for r in warning_records]}"
        )

    def test_openai_compatible_no_warning(self) -> None:
        """Calling normalize_adapter_name with 'openai_compatible' should NOT emit a warning."""
        normalize_adapter_name("openai_compatible")

        # Should not emit any warnings for canonical name
        records = self._handler.buffer
        warning_records = [r for r in records if r.levelno == logging.WARNING]
        self.assertEqual(
            len(warning_records), 0,
            f"Should not emit WARNING for 'openai_compatible'. Got: {[r.__dict__ for r in warning_records]}"
        )

    def test_warning_only_issued_once(self) -> None:
        """Multiple calls with 'llamacpp' should only warn once (deduplicated by tracker)."""
        from k8s_diag_agent.external_analysis import adapter as adapter_module
        adapter_module._DEPRECATION_WARNING_LOGGED.clear()
        self._handler.buffer.clear()

        # Call multiple times
        normalize_adapter_name("llamacpp")
        normalize_adapter_name("llamacpp")
        normalize_adapter_name("llamacpp")

        # Should only have 1 warning, not 3 (deduplication via _DEPRECATION_WARNING_LOGGED)
        warning_records = [r for r in self._handler.buffer if r.levelno == logging.WARNING]
        self.assertEqual(
            len(warning_records), 1,
            f"Expected 1 warning due to deduplication, got {len(warning_records)}: {[r.__dict__ for r in warning_records]}"
        )


class TestBuildAdaptersWithCanonicalName(unittest.TestCase):
    """Test building adapters using canonical 'openai_compatible' name."""

    def setUp(self) -> None:
        """Save original registry state."""
        self._original_builders = _ADAPTER_BUILDERS.copy()

    def tearDown(self) -> None:
        """Restore original registry state."""
        _ADAPTER_BUILDERS.clear()
        _ADAPTER_BUILDERS.update(self._original_builders)

    def test_build_openai_compatible_adapter(self) -> None:
        """build_external_analysis_adapters should work with 'openai_compatible' config."""
        config = ExternalAnalysisAdapterConfig(
            name="openai_compatible",
            enabled=True,
            command=("echo", "test"),
        )
        adapters = build_external_analysis_adapters([config])

        # The adapter is registered under canonical "openai_compatible" name
        self.assertEqual(len(adapters), 1)
        self.assertIn("openai_compatible", adapters)
        self.assertNotIn("llamacpp", adapters)


class TestBuildAdaptersWithLegacyName(unittest.TestCase):
    """Test building adapters using legacy 'llamacpp' name."""

    def setUp(self) -> None:
        """Save original registry state."""
        self._original_builders = _ADAPTER_BUILDERS.copy()

    def tearDown(self) -> None:
        """Restore original registry state."""
        _ADAPTER_BUILDERS.clear()
        _ADAPTER_BUILDERS.update(self._original_builders)

    def test_build_llamacpp_adapter(self) -> None:
        """build_external_analysis_adapters should work with 'llamacpp' config (backward compat)."""
        config = ExternalAnalysisAdapterConfig(
            name="llamacpp",
            enabled=True,
            command=("echo", "test"),
        )

        # Should not raise - legacy name should work
        adapters = build_external_analysis_adapters([config])

        # The adapter is registered under the canonical name (normalized)
        self.assertEqual(len(adapters), 1)
        self.assertIn("openai_compatible", adapters)


class TestGetAvailableAdapterNames(unittest.TestCase):
    """Test get_available_adapter_names returns sorted list."""

    def setUp(self) -> None:
        """Save original registry state."""
        self._original_builders = _ADAPTER_BUILDERS.copy()

    def tearDown(self) -> None:
        """Restore original registry state."""
        _ADAPTER_BUILDERS.clear()
        _ADAPTER_BUILDERS.update(self._original_builders)

    def test_returns_sorted_tuple(self) -> None:
        """get_available_adapter_names should return a sorted tuple."""
        names = get_available_adapter_names()
        self.assertIsInstance(names, tuple)
        # Verify it's sorted
        self.assertEqual(names, tuple(sorted(names)))

    def test_includes_both_canonical_and_legacy(self) -> None:
        """Available names should include both 'openai_compatible' and 'llamacpp'."""
        names = get_available_adapter_names()
        # Both canonical and legacy names should be registered
        self.assertIn("openai_compatible", names)
        self.assertIn("llamacpp", names)


if __name__ == "__main__":
    unittest.main()

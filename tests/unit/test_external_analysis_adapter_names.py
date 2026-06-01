"""Tests for external analysis adapter name normalization (Phase 2 of llamacpp rename epic).

These tests verify that:
- 'openai_compatible' is the canonical adapter name
- 'llamacpp' is a legacy alias that normalizes to 'openai_compatible'
- Legacy name emits deprecation warning
- Both names resolve to the same adapter behavior
- Error messages list sorted available names
"""

import unittest
import warnings

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


class TestNormalizeAdapterNameEmitsWarning(unittest.TestCase):
    """Test that normalize_adapter_name emits deprecation warning for llamacpp."""

    def setUp(self) -> None:
        """Clear the deprecation warning tracker before each test."""
        # Import the module-level tracker and clear it
        from k8s_diag_agent.external_analysis import adapter as adapter_module
        adapter_module._DEPRECATION_WARNING_LOGGED.clear()

    def test_llamacpp_emits_deprecation_warning(self) -> None:
        """Calling normalize_adapter_name with 'llamacpp' should emit a DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            normalize_adapter_name("llamacpp")

            # Check that a DeprecationWarning was issued
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            self.assertTrue(
                len(deprecation_warnings) > 0,
                "Expected at least one DeprecationWarning for 'llamacpp'"
            )
            # Verify the warning message mentions the deprecated and canonical names
            warning_messages = [str(x.message) for x in deprecation_warnings]
            found_warning = any(
                "llamacpp" in msg and "openai_compatible" in msg for msg in warning_messages
            )
            self.assertTrue(
                found_warning,
                f"Expected warning to mention both 'llamacpp' and 'openai_compatible'. Got: {warning_messages}"
            )

    def test_openai_compatible_no_warning(self) -> None:
        """Calling normalize_adapter_name with 'openai_compatible' should NOT emit a warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            normalize_adapter_name("openai_compatible")

            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            self.assertEqual(
                len(deprecation_warnings), 0,
                "Should not emit DeprecationWarning for 'openai_compatible'"
            )

    def test_warning_only_issued_once(self) -> None:
        """Multiple calls with 'llamacpp' should only warn once."""
        from k8s_diag_agent.external_analysis import adapter as adapter_module
        adapter_module._DEPRECATION_WARNING_LOGGED.clear()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Call multiple times
            normalize_adapter_name("llamacpp")
            normalize_adapter_name("llamacpp")
            normalize_adapter_name("llamacpp")

            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            # Should only have 1 warning, not 3
            self.assertEqual(len(deprecation_warnings), 1)


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

        # The adapter is registered under "openai_compatible" name
        self.assertEqual(len(adapters), 1)
        # Adapter instance keys remain "llamacpp" until Phase 3 artifact/UI migration
        self.assertIn("llamacpp", adapters)


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

        # The adapter is registered under "llamacpp" name
        self.assertEqual(len(adapters), 1)
        # Adapter instance name is "llamacpp" (the class's name attribute)
        self.assertIn("llamacpp", adapters)


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

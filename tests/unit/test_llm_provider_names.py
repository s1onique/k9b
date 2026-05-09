"""Tests for LLM provider name normalization and aliasing.

These tests verify the canonical `openai_compatible` provider name and the legacy
`llamacpp` alias behavior, as part of Phase 1 of the provider rename epic.
"""
from __future__ import annotations

import logging
import logging.handlers  # noqa: F401 - needed for MemoryHandler
from unittest import TestCase

from k8s_diag_agent.llm.base import LLMProvider
from k8s_diag_agent.llm.provider import (
    AVAILABLE_PROVIDERS,
    DEFAULT_PROVIDER_NAME,
    LEGACY_LLAMACPP_PROVIDER_NAME,
    OPENAI_COMPATIBLE_PROVIDER_NAME,
    PROVIDERS,
    get_provider,
    normalize_provider_name,
)


class TestProviderNameConstants(TestCase):

    """Test that provider name constants are defined correctly."""

    def test_openai_compatible_canonical_name(self) -> None:
        """Canonical provider name should be 'openai_compatible'."""
        self.assertEqual(OPENAI_COMPATIBLE_PROVIDER_NAME, "openai_compatible")

    def test_llamacpp_legacy_name(self) -> None:
        """Legacy provider name should be 'llamacpp'."""
        self.assertEqual(LEGACY_LLAMACPP_PROVIDER_NAME, "llamacpp")

    def test_canonical_and_legacy_differ(self) -> None:
        """Canonical and legacy names should be different."""
        self.assertNotEqual(OPENAI_COMPATIBLE_PROVIDER_NAME, LEGACY_LLAMACPP_PROVIDER_NAME)


class TestProviderRegistry(TestCase):
    """Test that providers are registered correctly."""

    def test_openai_compatible_registered(self) -> None:
        """Canonical 'openai_compatible' provider should be registered."""
        self.assertIn(OPENAI_COMPATIBLE_PROVIDER_NAME, PROVIDERS)
        self.assertIsInstance(PROVIDERS[OPENAI_COMPATIBLE_PROVIDER_NAME], LLMProvider)

    def test_llamacpp_alias_registered(self) -> None:
        """Legacy 'llamacpp' alias should be registered for compatibility."""
        self.assertIn(LEGACY_LLAMACPP_PROVIDER_NAME, PROVIDERS)
        self.assertIsInstance(PROVIDERS[LEGACY_LLAMACPP_PROVIDER_NAME], LLMProvider)

    def test_both_names_point_to_same_provider(self) -> None:
        """Both canonical and legacy names should return the same provider instance."""
        canonical = PROVIDERS[OPENAI_COMPATIBLE_PROVIDER_NAME]
        legacy = PROVIDERS[LEGACY_LLAMACPP_PROVIDER_NAME]
        self.assertIs(canonical, legacy)

    def test_default_provider_still_available(self) -> None:
        """Default provider should still be available."""
        self.assertIn(DEFAULT_PROVIDER_NAME, PROVIDERS)
        self.assertIsInstance(PROVIDERS[DEFAULT_PROVIDER_NAME], LLMProvider)

    def test_available_providers_sorted(self) -> None:
        """AVAILABLE_PROVIDERS should be sorted for consistent error messages."""
        # Check it's a tuple and sorted
        self.assertIsInstance(AVAILABLE_PROVIDERS, tuple)
        self.assertEqual(list(AVAILABLE_PROVIDERS), sorted(AVAILABLE_PROVIDERS))


class TestNormalizeProviderName(TestCase):
    """Test the normalize_provider_name function."""

    def test_openai_compatible_normalizes_to_self(self) -> None:
        """'openai_compatible' should normalize to 'openai_compatible'."""
        result = normalize_provider_name("openai_compatible")
        self.assertEqual(result, "openai_compatible")

    def test_openai_compatible_case_insensitive(self) -> None:
        """'OpenAI_Compatible', 'OPENAI_COMPATIBLE', etc. should all normalize to 'openai_compatible'."""
        result = normalize_provider_name("OpenAI_Compatible")
        self.assertEqual(result, "openai_compatible")
        result = normalize_provider_name("OPENAI_COMPATIBLE")
        self.assertEqual(result, "openai_compatible")
        result = normalize_provider_name("OpEnAi_CoMpAtIbLe")
        self.assertEqual(result, "openai_compatible")

    def test_llamacpp_normalizes_to_openai_compatible(self) -> None:
        """'llamacpp' should normalize to 'openai_compatible'."""
        result = normalize_provider_name("llamacpp")
        self.assertEqual(result, OPENAI_COMPATIBLE_PROVIDER_NAME)

    def test_llamacpp_case_insensitive(self) -> None:
        """'LlamaCpp', 'LLAMACPP', etc. should all normalize to 'openai_compatible'."""
        result = normalize_provider_name("LlamaCpp")
        self.assertEqual(result, OPENAI_COMPATIBLE_PROVIDER_NAME)
        result = normalize_provider_name("LLAMACPP")
        self.assertEqual(result, OPENAI_COMPATIBLE_PROVIDER_NAME)

    def test_unknown_passes_through(self) -> None:
        """Unknown provider names should pass through unchanged."""
        result = normalize_provider_name("vllm")
        self.assertEqual(result, "vllm")
        result = normalize_provider_name("custom")
        self.assertEqual(result, "custom")
        result = normalize_provider_name("unknown")
        self.assertEqual(result, "unknown")

    def test_default_passes_through(self) -> None:
        """'default' should pass through unchanged."""
        result = normalize_provider_name("default")
        self.assertEqual(result, "default")


class ListHandler(logging.Handler):
    """Simple handler that stores records in a list."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def clear(self) -> None:
        self.records.clear()


class TestNormalizeProviderNameEmitsWarning(TestCase):
    """Test that normalize_provider_name emits deprecation warning for llamacpp."""

    def setUp(self) -> None:
        self.logger = logging.getLogger("k8s_diag_agent.llm.provider")
        # Capture logs at WARNING level
        self.handler = ListHandler()
        self.handler.setLevel(logging.WARNING)
        self.logger.addHandler(self.handler)

    def tearDown(self) -> None:
        self.logger.removeHandler(self.handler)

    def test_llamacpp_emits_warning(self) -> None:
        """Calling normalize_provider_name with 'llamacpp' should emit a warning."""
        self.handler.clear()
        normalize_provider_name("llamacpp")
        # Check that at least one WARNING was logged
        self.assertGreater(len(self.handler.records), 0)
        # Check the message contains the deprecation info
        messages = [record.getMessage() for record in self.handler.records]
        self.assertTrue(
            any("deprecated" in msg.lower() and "llamacpp" in msg for msg in messages),
            f"Expected deprecation warning for llamacpp. Got: {messages}",
        )

    def test_openai_compatible_no_warning(self) -> None:
        """Calling normalize_provider_name with 'openai_compatible' should NOT emit a warning."""
        self.handler.clear()
        normalize_provider_name("openai_compatible")
        # No WARNING should be emitted
        self.assertEqual(len(self.handler.records), 0, f"Unexpected warnings: {[r.getMessage() for r in self.handler.records]}")



class TestGetProvider(TestCase):
    """Test the get_provider function with canonical and legacy names."""

    def test_get_openai_compatible_works(self) -> None:
        """get_provider('openai_compatible') should work."""
        provider = get_provider("openai_compatible")
        self.assertIsInstance(provider, LLMProvider)

    def test_get_llamacpp_works(self) -> None:
        """get_provider('llamacpp') should work (legacy alias)."""
        provider = get_provider("llamacpp")
        self.assertIsInstance(provider, LLMProvider)

    def test_get_both_return_same_instance(self) -> None:
        """get_provider('openai_compatible') and get_provider('llamacpp') should return the same instance."""
        canonical = get_provider("openai_compatible")
        legacy = get_provider("llamacpp")
        self.assertIs(canonical, legacy)

    def test_get_default_still_works(self) -> None:
        """get_provider('default') should still work."""
        provider = get_provider("default")
        self.assertIsInstance(provider, LLMProvider)

    def test_get_none_returns_default(self) -> None:
        """get_provider(None) should return the default provider."""
        provider = get_provider(None)
        self.assertIsInstance(provider, LLMProvider)
        self.assertIs(provider, PROVIDERS[DEFAULT_PROVIDER_NAME])

    def test_get_unknown_fails(self) -> None:
        """get_provider with unknown name should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            get_provider("unknown-provider")
        # Verify error message mentions available providers
        error_msg = str(ctx.exception)
        self.assertIn("unknown-provider", error_msg)
        # Should list the canonical name
        self.assertIn(OPENAI_COMPATIBLE_PROVIDER_NAME, error_msg)

    def test_get_unknown_lists_available_providers(self) -> None:
        """Error message for unknown provider should list available providers."""
        with self.assertRaises(ValueError) as ctx:
            get_provider("totally-made-up")
        error_msg = str(ctx.exception)
        # Should contain all available provider names
        for name in PROVIDERS:
            self.assertIn(name, error_msg)
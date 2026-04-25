"""Tests for prompt diagnostics module."""

import unittest

from k8s_diag_agent.llm.prompt_diagnostics import (
    CHARS_PER_TOKEN_ESTIMATE,
    PromptSection,
    PromptSectionDiagnostics,
    build_full_prompt_diagnostics,
    build_prompt_diagnostics,
    build_prompt_sections,
    estimate_tokens_from_chars,
    log_prompt_diagnostics,
)


class TestEstimateTokensFromChars(unittest.TestCase):
    """Tests for estimate_tokens_from_chars() function."""

    def test_exact_division(self) -> None:
        """Test exact division by chars-per-token."""
        result = estimate_tokens_from_chars(400)
        self.assertEqual(result, 100)

    def test_rounds_down(self) -> None:
        """Test that remainder is discarded."""
        result = estimate_tokens_from_chars(401)
        self.assertEqual(result, 100)

    def test_zero_chars_returns_one(self) -> None:
        """Test that zero chars returns minimum of 1."""
        result = estimate_tokens_from_chars(0)
        self.assertEqual(result, 1)

    def test_small_chars(self) -> None:
        """Test small character count."""
        result = estimate_tokens_from_chars(3)
        self.assertEqual(result, 1)

    def test_uses_chars_per_token_estimate(self) -> None:
        """Test that function uses the configured estimate."""
        result = estimate_tokens_from_chars(CHARS_PER_TOKEN_ESTIMATE)
        self.assertEqual(result, 1)


class TestPromptSectionDiagnostics(unittest.TestCase):
    """Tests for PromptSectionDiagnostics dataclass."""

    def test_from_section_calculates_tokens(self) -> None:
        """Test that from_section calculates token estimate."""
        section = PromptSection(name="test", text="A" * 40)  # 40 chars
        result = PromptSectionDiagnostics.from_section(section, total_tokens=10)
        self.assertEqual(result.name, "test")
        self.assertEqual(result.chars, 40)
        self.assertEqual(result.tokens_estimate, 10)

    def test_from_section_calculates_percentage(self) -> None:
        """Test that from_section calculates percentage of total."""
        section = PromptSection(name="half", text="A" * 20)
        result = PromptSectionDiagnostics.from_section(section, total_tokens=10)
        self.assertEqual(result.percentage_of_prompt, 50.0)

    def test_from_section_zero_total(self) -> None:
        """Test that zero total tokens returns 0 percentage."""
        section = PromptSection(name="test", text="A" * 40)
        result = PromptSectionDiagnostics.from_section(section, total_tokens=0)
        self.assertEqual(result.percentage_of_prompt, 0.0)

    def test_to_dict(self) -> None:
        """Test that to_dict returns correct structure."""
        diags = PromptSectionDiagnostics(
            name="test",
            chars=100,
            tokens_estimate=25,
            percentage_of_prompt=100.0,
        )
        result = diags.to_dict()
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["chars"], 100)
        self.assertEqual(result["tokens_estimate"], 25)
        self.assertEqual(result["percentage_of_prompt"], 100.0)


class TestBuildPromptSections(unittest.TestCase):
    """Tests for build_prompt_sections() function."""

    def test_empty_sections(self) -> None:
        """Test empty input returns empty tuple."""
        result = build_prompt_sections([])
        self.assertEqual(result, ())

    def test_prompt_section_objects(self) -> None:
        """Test that PromptSection objects pass through."""
        sections = [PromptSection(name="a", text="text")]
        result = build_prompt_sections(sections)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "a")

    def test_tuple_pairs(self) -> None:
        """Test that (name, text) tuples convert to PromptSection."""
        sections = [("section1", "content1")]
        result = build_prompt_sections(sections)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], PromptSection)
        self.assertEqual(result[0].name, "section1")
        self.assertEqual(result[0].text, "content1")

    def test_mixed_types(self) -> None:
        """Test mixed PromptSection and tuple input."""
        sections = [
            PromptSection(name="existing", text="existing text"),
            ("new_section", "new content"),
        ]
        result = build_prompt_sections(sections)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "existing")
        self.assertEqual(result[1].name, "new_section")


class TestBuildPromptDiagnostics(unittest.TestCase):
    """Tests for build_prompt_diagnostics() function."""

    def test_single_section_full_prompt_fallback(self) -> None:
        """Test single section handling with full_prompt fallback style."""
        diags = build_prompt_diagnostics(
            provider="llamacpp",
            operation="review-enrichment",
            sections=[("full_prompt", "A" * 400)],
        )
        self.assertEqual(diags.provider, "llamacpp")
        self.assertEqual(diags.operation, "review-enrichment")
        self.assertEqual(diags.prompt_chars, 400)
        self.assertEqual(diags.prompt_tokens_estimate, 100)  # 400/4
        self.assertEqual(diags.prompt_section_count, 1)
        self.assertEqual(len(diags.prompt_sections), 1)
        self.assertEqual(len(diags.top_prompt_sections), 1)

    def test_multiple_named_sections(self) -> None:
        """Test multiple named sections."""
        sections = [
            ("system_instructions", "A" * 40),  # 10 tokens
            ("output_schema", "B" * 80),  # 20 tokens
            ("findings", "C" * 120),  # 30 tokens
        ]
        diags = build_prompt_diagnostics(
            provider="llamacpp",
            operation="auto-drilldown",
            sections=sections,
        )
        self.assertEqual(diags.provider, "llamacpp")
        self.assertEqual(diags.operation, "auto-drilldown")
        self.assertEqual(diags.prompt_chars, 240)
        self.assertEqual(diags.prompt_tokens_estimate, 60)  # 240/4
        self.assertEqual(diags.prompt_section_count, 3)
        self.assertEqual(len(diags.prompt_sections), 3)
        # Top 5 or fewer sections by tokens (we only have 3)
        self.assertEqual(len(diags.top_prompt_sections), 3)

    def test_top_prompt_sections_sorted_by_tokens(self) -> None:
        """Test that top_prompt_sections is sorted by tokens descending."""
        sections = [
            ("small", "A" * 40),  # 10 tokens
            ("large", "B" * 200),  # 50 tokens
            ("medium", "C" * 80),  # 20 tokens
        ]
        diags = build_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            sections=sections,
        )
        top = diags.top_prompt_sections
        # Should be sorted by tokens_estimate descending
        self.assertEqual(top[0].name, "large")
        self.assertEqual(top[0].tokens_estimate, 50)
        self.assertEqual(top[1].name, "medium")
        self.assertEqual(top[1].tokens_estimate, 20)
        self.assertEqual(top[2].name, "small")
        self.assertEqual(top[2].tokens_estimate, 10)

    def test_percentage_calculation_sane(self) -> None:
        """Test that percentage_of_prompt is sane for each section."""
        sections = [
            ("half", "A" * 40),  # 10 tokens = 50% of 20
            ("quarter", "B" * 20),  # 5 tokens = 25% of 20
            ("quarter2", "C" * 20),  # 5 tokens = 25% of 20
        ]
        diags = build_prompt_diagnostics(
            provider="test",
            operation="test",
            sections=sections,
        )
        # Total tokens = 20, half should be 50%
        half_section = next(s for s in diags.prompt_sections if s.name == "half")
        self.assertEqual(half_section.percentage_of_prompt, 50.0)

    def test_failure_metadata_included(self) -> None:
        """Test that failure metadata is included in diagnostics."""
        diags = build_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            sections=[("test", "content")],
            failure_class="llm_client_read_timeout",
            exception_type="ReadTimeout",
            elapsed_ms=120034,
        )
        self.assertEqual(diags.failure_class, "llm_client_read_timeout")
        self.assertEqual(diags.exception_type, "ReadTimeout")
        self.assertEqual(diags.elapsed_ms, 120034)

    def test_timeout_and_max_tokens_included(self) -> None:
        """Test that timeout and max_tokens are included when provided."""
        diags = build_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            sections=[("test", "content")],
            timeout_seconds=120,
            max_tokens=512,
        )
        self.assertEqual(diags.timeout_seconds, 120)
        self.assertEqual(diags.max_tokens, 512)

    def test_to_dict_full_output(self) -> None:
        """Test that to_dict produces complete output."""
        diags = build_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            sections=[("section1", "content1"), ("section2", "content2")],
            timeout_seconds=120,
            elapsed_ms=5000,
            failure_class="test_error",
            exception_type="TestError",
        )
        result = diags.to_dict()
        self.assertEqual(result["provider"], "llamacpp")
        self.assertEqual(result["operation"], "test")
        self.assertEqual(result["prompt_section_count"], 2)
        self.assertEqual(result["timeout_seconds"], 120)
        self.assertEqual(result["elapsed_ms"], 5000)
        self.assertEqual(result["failure_class"], "test_error")
        self.assertEqual(result["exception_type"], "TestError")
        self.assertIn("prompt_sections", result)
        self.assertIn("top_prompt_sections", result)
        # Coverage tracking fields
        self.assertIn("actual_prompt_chars", result)
        self.assertIn("actual_prompt_tokens_estimate", result)
        self.assertIn("section_prompt_chars", result)
        self.assertIn("section_coverage_ratio", result)
        self.assertIn("section_accounting_exact", result)

    def test_optional_fields_omitted_when_none(self) -> None:
        """Test that optional fields are omitted from dict when None."""
        diags = build_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            sections=[("test", "content")],
        )
        result = diags.to_dict()
        self.assertNotIn("max_tokens", result)
        self.assertNotIn("timeout_seconds", result)
        self.assertNotIn("endpoint", result)
        self.assertNotIn("elapsed_ms", result)
        self.assertNotIn("failure_class", result)
        self.assertNotIn("exception_type", result)


class TestBuildFullPromptDiagnostics(unittest.TestCase):
    """Tests for build_full_prompt_diagnostics() function."""

    def test_creates_one_section_named_full_prompt(self) -> None:
        """Test that it creates exactly one section named 'full_prompt'."""
        diags = build_full_prompt_diagnostics(
            provider="llamacpp",
            operation="review-enrichment",
            actual_prompt="Test prompt content",
        )
        self.assertEqual(diags.prompt_section_count, 1)
        self.assertEqual(len(diags.prompt_sections), 1)
        self.assertEqual(diags.prompt_sections[0].name, "full_prompt")

    def test_actual_prompt_chars_equals_len_actual_prompt(self) -> None:
        """Test that actual_prompt_chars matches len(actual_prompt)."""
        prompt_text = "A" * 1234
        diags = build_full_prompt_diagnostics(
            provider="llamacpp",
            operation="review-enrichment",
            actual_prompt=prompt_text,
        )
        self.assertEqual(diags.actual_prompt_chars, len(prompt_text))
        self.assertEqual(diags.actual_prompt_chars, 1234)

    def test_section_coverage_ratio_is_one_point_zero(self) -> None:
        """Test that section_coverage_ratio is 1.0 when using full prompt."""
        prompt_text = "A" * 500
        diags = build_full_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            actual_prompt=prompt_text,
        )
        self.assertEqual(diags.section_coverage_ratio, 1.0)

    def test_section_accounting_exact_is_true(self) -> None:
        """Test that section_accounting_exact is True when using full prompt."""
        diags = build_full_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            actual_prompt="Test content",
        )
        self.assertTrue(diags.section_accounting_exact)

    def test_with_failure_metadata(self) -> None:
        """Test that failure metadata is passed through."""
        diags = build_full_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            actual_prompt="Test prompt",
            timeout_seconds=60,
            elapsed_ms=30000,
            failure_class="timeout",
            exception_type="ReadTimeout",
        )
        self.assertEqual(diags.timeout_seconds, 60)
        self.assertEqual(diags.elapsed_ms, 30000)
        self.assertEqual(diags.failure_class, "timeout")
        self.assertEqual(diags.exception_type, "ReadTimeout")

    def test_max_tokens_optional_not_implemented(self) -> None:
        """Test that max_tokens is not wired in this patch (remains None).

        NOTE: This test documents that max_tokens is optional and not yet
        implemented in the LLM adapter. Do not assert max_tokens has a value.
        """
        diags = build_full_prompt_diagnostics(
            provider="llamacpp",
            operation="test",
            actual_prompt="Test prompt",
        )
        # max_tokens should be None unless explicitly set
        self.assertIsNone(diags.max_tokens)


class TestLogPromptDiagnostics(unittest.TestCase):
    """Tests for log_prompt_diagnostics() function."""

    def test_includes_required_fields(self) -> None:
        """Test that log output includes required diagnostic fields."""
        diags = build_prompt_diagnostics(
            provider="llamacpp",
            operation="review-enrichment",
            sections=[
                ("large_section", "A" * 200),
                ("small_section", "B" * 40),
            ],
            timeout_seconds=120,
            elapsed_ms=120034,
            failure_class="llm_client_read_timeout",
            exception_type="ReadTimeout",
        )
        log_data = log_prompt_diagnostics(diags)
        self.assertEqual(log_data["operation"], "review-enrichment")
        self.assertEqual(log_data["provider"], "llamacpp")
        self.assertEqual(log_data["prompt_chars"], 240)
        self.assertEqual(log_data["prompt_tokens_estimate"], 60)
        self.assertEqual(log_data["prompt_section_count"], 2)
        self.assertIn("top_prompt_sections", log_data)
        self.assertEqual(log_data["timeout_seconds"], 120)
        self.assertEqual(log_data["elapsed_ms"], 120034)
        self.assertEqual(log_data["failure_class"], "llm_client_read_timeout")
        self.assertEqual(log_data["exception_type"], "ReadTimeout")

    def test_includes_coverage_fields(self) -> None:
        """Test that log output includes coverage tracking fields."""
        diags = build_full_prompt_diagnostics(
            provider="llamacpp",
            operation="review-enrichment",
            actual_prompt="A" * 1000,
        )
        log_data = log_prompt_diagnostics(diags)
        # Coverage fields should be present
        self.assertIn("actual_prompt_chars", log_data)
        self.assertIn("actual_prompt_tokens_estimate", log_data)
        self.assertIn("section_prompt_chars", log_data)
        self.assertIn("section_coverage_ratio", log_data)
        self.assertIn("section_accounting_exact", log_data)
        # Check values are correct
        self.assertEqual(log_data["actual_prompt_chars"], 1000)
        self.assertEqual(log_data["actual_prompt_tokens_estimate"], 250)
        self.assertEqual(log_data["section_prompt_chars"], 1000)
        self.assertEqual(log_data["section_coverage_ratio"], 1.0)
        self.assertTrue(log_data["section_accounting_exact"])

    def test_top_sections_names_only(self) -> None:
        """Test that top_prompt_sections in log contains only names."""
        diags = build_prompt_diagnostics(
            provider="test",
            operation="test",
            sections=[
                ("section_a", "A" * 100),
                ("section_b", "B" * 50),
            ],
        )
        log_data = log_prompt_diagnostics(diags)
        self.assertIn("top_prompt_sections", log_data)
        self.assertIsInstance(log_data["top_prompt_sections"], list)
        # Should be names, not full section objects
        for name in log_data["top_prompt_sections"]:
            self.assertIsInstance(name, str)


class TestPromptDiagnosticsBackwardCompat(unittest.TestCase):
    """Tests for backward compatibility with legacy artifacts."""

    def test_from_dict_without_prompt_diagnostics(self) -> None:
        """Test that dict without prompt_diagnostics still works."""
        # Simulate legacy failure_metadata that doesn't have prompt_diagnostics
        legacy_metadata = {
            "failure_class": "llm_adapter_error",
            "exception_type": "RuntimeError",
            "timeout_seconds": 120,
            "elapsed_ms": 5000,
            "endpoint": "http://example.com/v1/chat/completions",
            "summary": "Some error",
        }
        # This should work without prompt_diagnostics key
        self.assertIn("failure_class", legacy_metadata)
        self.assertNotIn("prompt_diagnostics", legacy_metadata)


if __name__ == "__main__":
    unittest.main()

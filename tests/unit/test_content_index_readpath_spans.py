"""Tests for content index OTel span helpers.

Tests that span helpers don't raise without OTel configured.
"""

from __future__ import annotations

from k8s_diag_agent.content_index import CONTENT_INDEX_SCHEMA_VERSION
from k8s_diag_agent.content_index.readpath import (
    FallbackReason,
    record_fallback_span,
    record_success_span,
)


class TestSpanHelpers:
    """Test span helper functions (should be no-ops without OTel)."""

    def test_record_fallback_span_noops(self) -> None:
        """Test that record_fallback_span doesn't raise without OTel."""
        # Should not raise even without OTel configured
        record_fallback_span(
            "k9b.content_index.fallback",
            reason=FallbackReason.INDEX_NOT_FOUND,
            enabled=True,
            schema_version=None,
        )

    def test_record_success_span_noops(self) -> None:
        """Test that record_success_span doesn't raise without OTel."""
        # Should not raise even without OTel configured
        record_success_span(
            "k9b.content_index.project_response",
            enabled=True,
            schema_version=CONTENT_INDEX_SCHEMA_VERSION,
            count=1,
        )

    def test_record_fallback_span_with_all_params(self) -> None:
        """Test fallback span with all parameters."""
        record_fallback_span(
            "k9b.content_index.fallback",
            reason=FallbackReason.INDEX_SCHEMA_MISMATCH,
            enabled=True,
            schema_version="k9b.content_index.v99",
        )

    def test_record_success_span_with_count(self) -> None:
        """Test success span with count."""
        record_success_span(
            "k9b.content_index.project_response",
            enabled=True,
            schema_version=CONTENT_INDEX_SCHEMA_VERSION,
            count=42,
        )

"""Tests for prompt boundary marker constants (REM-P4).

These tests verify that boundary marker constants use the expected format
to separate trusted instructions from untrusted cluster/artifact data.
"""

from __future__ import annotations

from k8s_diag_agent.llm.prompt_boundaries import (
    BEGIN_OUTPUT_SCHEMA,
    BEGIN_UNTRUSTED_CLUSTER_DATA,
    END_OUTPUT_SCHEMA,
    END_UNTRUSTED_CLUSTER_DATA,
)


class TestBoundaryMarkerConstants:
    """Tests for boundary marker constants."""

    def test_marker_format(self) -> None:
        """Verify markers use the expected format with equals signs and underscores."""
        # Markers should be distinct and unlikely to appear in cluster data
        assert "=====" in BEGIN_UNTRUSTED_CLUSTER_DATA
        assert "=====" in END_UNTRUSTED_CLUSTER_DATA
        assert "=====" in BEGIN_OUTPUT_SCHEMA
        assert "=====" in END_OUTPUT_SCHEMA

        # Markers should contain descriptive names
        assert "UNTRUSTED" in BEGIN_UNTRUSTED_CLUSTER_DATA
        assert "CLUSTER_DATA" in BEGIN_UNTRUSTED_CLUSTER_DATA
        assert "OUTPUT_SCHEMA" in BEGIN_OUTPUT_SCHEMA

    def test_begin_end_pairs(self) -> None:
        """Verify BEGIN and END markers are distinct."""
        assert BEGIN_UNTRUSTED_CLUSTER_DATA != END_UNTRUSTED_CLUSTER_DATA
        assert BEGIN_OUTPUT_SCHEMA != END_OUTPUT_SCHEMA
        assert "BEGIN" in BEGIN_UNTRUSTED_CLUSTER_DATA
        assert "END" in END_UNTRUSTED_CLUSTER_DATA
        assert "BEGIN" in BEGIN_OUTPUT_SCHEMA
        assert "END" in END_OUTPUT_SCHEMA

    def test_markers_are_valid_identifiers(self) -> None:
        """Verify markers don't contain characters that might be in cluster data."""
        # Markers should not contain quotes, braces, or other JSON-like characters
        for marker in [
            BEGIN_UNTRUSTED_CLUSTER_DATA,
            END_UNTRUSTED_CLUSTER_DATA,
            BEGIN_OUTPUT_SCHEMA,
            END_OUTPUT_SCHEMA,
        ]:
            assert '"' not in marker
            assert "'" not in marker or marker.count("'") == 2  # Allow single quotes in Python string
            assert "{" not in marker
            assert "}" not in marker
            assert "[" not in marker
            assert "]" not in marker

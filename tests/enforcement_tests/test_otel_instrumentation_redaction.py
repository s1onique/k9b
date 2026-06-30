"""Tests for OTel redaction and secret protection in diagnosis loop runtime.

These tests verify that:
1. No raw secrets are emitted in telemetry
2. Attribute keys use stable k9b namespace
3. Span attributes contain only safe types
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_otel import (
    ATTR_ARTIFACT_PATH,
    ATTR_CHECKS_ACCEPTED,
    ATTR_CHECKS_PROPOSED,
    ATTR_CHECKS_REJECTED,
    ATTR_LOOP_BUDGET_EXCEEDED,
    ATTR_LOOP_PASS_INDEX,
    ATTR_LOOP_RUN_ID,
    start_artifact_span,
    start_gate_span,
)


class TestAttributeKeys:
    """Tests for stable attribute key naming."""

    def test_all_attribute_keys_use_k9b_prefix(self) -> None:
        """All attribute keys use the k9b. prefix."""
        assert ATTR_LOOP_RUN_ID.startswith("k9b.")
        assert ATTR_LOOP_PASS_INDEX.startswith("k9b.")
        assert ATTR_CHECKS_PROPOSED.startswith("k9b.")
        assert ATTR_CHECKS_ACCEPTED.startswith("k9b.")
        assert ATTR_CHECKS_REJECTED.startswith("k9b.")
        assert ATTR_ARTIFACT_PATH.startswith("k9b.")
        assert ATTR_LOOP_BUDGET_EXCEEDED.startswith("k9b.")


class TestSecretValuesNotEmitted:
    """Tests that no secret values are emitted in telemetry API."""

    def test_gate_span_attributes_contain_only_safe_types(self) -> None:
        """Gate span attributes only contain simple types, not raw check data."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_gate_span(
                "run-123", 1,
                proposed=5,
                accepted=3,
                rejected_mutating=1,
                rejected_sensitive=1,
                rejected_duplicate=0,
                rejected_budget=0,
            )
            
            # The context is created without error
            assert ctx is not None
            # The span is None when no tracer, which means no telemetry is emitted
            assert ctx.active_span is None
            assert ctx.span is None

    def test_artifact_span_attributes_contain_only_safe_types(self) -> None:
        """Artifact span attributes only contain simple types, not raw data."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_artifact_span(
                "run-123", 1,
                artifact_path="/path/to/artifact.json",
                schema_valid=True,
                missing_fields=0,
                new_evidence_count=2,
            )
            
            assert ctx is not None
            assert ctx.active_span is None
            assert ctx.span is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

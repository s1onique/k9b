"""Tests for OTel instrumentation in diagnosis loop runtime.

This module is a thin façade that re-exports tests from focused modules.
The tests are split into:
- test_otel_instrumentation_spans.py: High-level span helpers and span names
- test_otel_instrumentation_events.py: Event names and emission
- test_otel_instrumentation_attributes.py: SpanContext behavior
- test_otel_instrumentation_redaction.py: Secret protection and attribute safety
- test_otel_instrumentation_noop.py: Graceful degradation and noop behavior
"""
from __future__ import annotations

from .test_otel_instrumentation_attributes import TestSpanContext
from .test_otel_instrumentation_events import (
    TestEventNames,
    TestSpanContextEvents,
)
from .test_otel_instrumentation_noop import (
    TestExceptionRecording,
    TestInMemoryOTelTracerEvents,
    TestOTelGracefulDegradation,
    TestTelemetryFailureDoesNotBreakRuntime,
)
from .test_otel_instrumentation_redaction import (
    TestAttributeKeys,
    TestSecretValuesNotEmitted,
)

# Re-export all tests from split modules
from .test_otel_instrumentation_spans import (
    TestHighLevelSpanHelpers,
    TestInMemoryOTelTracer,
    TestSpanNames,
)

__all__ = [
    # Spans
    "TestHighLevelSpanHelpers",
    "TestSpanNames",
    "TestInMemoryOTelTracer",
    # Events
    "TestEventNames",
    "TestSpanContextEvents",
    # Attributes
    "TestSpanContext",
    # Redaction
    "TestAttributeKeys",
    "TestSecretValuesNotEmitted",
    # Noop/Graceful degradation
    "TestOTelGracefulDegradation",
    "TestTelemetryFailureDoesNotBreakRuntime",
    "TestExceptionRecording",
    "TestInMemoryOTelTracerEvents",
]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

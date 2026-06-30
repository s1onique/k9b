"""Helper fixtures for OTel instrumentation tests.

This module provides shared test fixtures that are used across multiple
OTel instrumentation test files. It intentionally does NOT have a test_
prefix so pytest does not collect it as a test file.
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_span() -> MagicMock:
    """Create a mock span for testing."""
    span = MagicMock()
    span.set_attribute = MagicMock()
    span.add_event = MagicMock()
    span.set_status = MagicMock()
    span.record_exception = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=None)
    return span


@pytest.fixture
def mock_tracer(mock_span: MagicMock) -> MagicMock:
    """Create a mock tracer that returns mock spans."""
    tracer = MagicMock()
    tracer.start_as_current_span = MagicMock(return_value=mock_span)
    tracer.start_span = MagicMock(return_value=mock_span)
    return tracer


@pytest.fixture
def in_memory_tracer_provider(self) -> Generator[Any, None, None]:
    """Create an in-memory tracer provider for testing."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import InMemorySpanExporter, SimpleSpanProcessor

        # Create in-memory exporter
        exporter = InMemorySpanExporter()
        
        # Create resource
        resource = Resource.create({"service.name": "k9b-test"})
        
        # Create tracer provider
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        
        # Set as global provider
        trace.set_tracer_provider(provider)
        
        yield exporter
        
        # Cleanup
        provider.shutdown()
    except ImportError:
        pytest.skip("OpenTelemetry SDK not available")

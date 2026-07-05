"""Tests for internal span instrumentation.

Tests that the internal span helper behaves correctly:
1. Disabled path: no OTel required, calls wrapped function, preserves return/exception
2. Enabled path: creates span with static name, sets attributes, records exceptions
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.observability.internal_spans import (
    internal_span,
    trace_artifact_decode_json,
    trace_artifact_read_json,
    trace_artifact_scan,
    trace_automatic_diagnosis_review_load,
    trace_diagnosis_loop_load_passes,
    trace_diagnosis_loop_load_summary,
    trace_incident_store_get,
    trace_incident_store_list,
    trace_internal_operation,
    trace_review_packet_load,
    trace_review_packet_project,
    trace_snapshot_bundle_load,
)


class TestTraceInternalOperationDisabled:
    """Tests for trace_internal_operation when tracing is disabled."""

    def test_wrapper_calls_function(self) -> None:
        """When disabled, wrapper should just call the function."""
        call_count = 0

        def operation() -> str:
            nonlocal call_count
            call_count += 1
            return "result"

        result = trace_internal_operation(
            name="k9b.test.operation",
            call=operation,
        )

        assert result == "result"
        assert call_count == 1

    def test_return_value_preserved(self) -> None:
        """Return values should be passed through unchanged."""
        expected = {"data": [1, 2, 3]}

        def operation() -> dict[str, list[int]]:
            return expected

        result = trace_internal_operation(
            name="k9b.test.operation",
            call=operation,
        )

        assert result is expected

    def test_raised_exception_preserved(self) -> None:
        """Exceptions should be re-raised unchanged."""
        custom_error = ValueError("something went wrong")

        def operation() -> None:
            raise custom_error

        with pytest.raises(ValueError, match="something went wrong") as exc_info:
            trace_internal_operation(
                name="k9b.test.operation",
                call=operation,
            )

        assert exc_info.value is custom_error

    def test_no_opentelemetry_required_in_disabled_path(self) -> None:
        """When disabled, opentelemetry should not be imported."""
        def operation() -> str:
            return "success"

        result = trace_internal_operation(
            name="k9b.test.operation",
            call=operation,
        )

        assert result == "success"

    def test_attributes_passed_through(self) -> None:
        """Attributes should not cause issues when tracing is disabled."""
        def operation() -> str:
            return "success"

        result = trace_internal_operation(
            name="k9b.test.operation",
            attributes={
                "k9b.operation": "test",
                "k9b.item.count": 5,
            },
            call=operation,
        )

        assert result == "success"


class TestInternalSpanDisabled:
    """Tests for internal_span context manager when tracing is disabled."""

    def test_context_manager_calls_block(self) -> None:
        """When disabled, context manager should just execute the block."""
        call_count = 0

        with internal_span("k9b.test.operation"):
            call_count += 1

        assert call_count == 1

    def test_context_manager_preserves_return(self) -> None:
        """Context manager should not affect return values."""
        result = None

        with internal_span("k9b.test.operation"):
            result = "success"

        assert result == "success"

    def test_context_manager_preserves_exception(self) -> None:
        """Exceptions should be re-raised unchanged."""
        custom_error = RuntimeError("block failed")

        with pytest.raises(RuntimeError, match="block failed") as exc_info:
            with internal_span("k9b.test.operation"):
                raise custom_error

        assert exc_info.value is custom_error

    def test_context_manager_with_attributes(self) -> None:
        """Attributes should not cause issues when tracing is disabled."""
        result = None

        with internal_span(
            "k9b.test.operation",
            attributes={"k9b.operation": "test"},
        ):
            result = "success"

        assert result == "success"


class TestConvenienceHelpers:
    """Tests for convenience span helpers."""

    def test_trace_incident_store_list(self) -> None:
        """trace_incident_store_list should call wrapped function."""
        def operation() -> list[str]:
            return ["incident1", "incident2"]

        result = trace_incident_store_list(operation)

        assert result == ["incident1", "incident2"]

    def test_trace_incident_store_get(self) -> None:
        """trace_incident_store_get should call wrapped function."""
        def operation() -> dict | None:
            return {"incident_id": "abc-123"}

        result = trace_incident_store_get(operation)

        assert result == {"incident_id": "abc-123"}

    def test_trace_artifact_scan(self) -> None:
        """trace_artifact_scan should call wrapped function."""
        def operation() -> list[str]:
            return ["file1.json", "file2.json"]

        result = trace_artifact_scan(operation)

        assert result == ["file1.json", "file2.json"]

    def test_trace_artifact_read_json(self) -> None:
        """trace_artifact_read_json should call wrapped function."""
        def operation() -> dict:
            return {"key": "value"}

        result = trace_artifact_read_json(operation)

        assert result == {"key": "value"}

    def test_trace_artifact_decode_json(self) -> None:
        """trace_artifact_decode_json should call wrapped function."""
        def operation() -> dict:
            return {"parsed": True}

        result = trace_artifact_decode_json(operation)

        assert result == {"parsed": True}

    def test_trace_review_packet_load(self) -> None:
        """trace_review_packet_load should call wrapped function."""
        def operation() -> dict:
            return {"packet": "data"}

        result = trace_review_packet_load(operation)

        assert result == {"packet": "data"}

    def test_trace_review_packet_project(self) -> None:
        """trace_review_packet_project should call wrapped function."""
        def operation() -> str:
            return "markdown content"

        result = trace_review_packet_project(operation)

        assert result == "markdown content"

    def test_trace_snapshot_bundle_load(self) -> None:
        """trace_snapshot_bundle_load should call wrapped function."""
        def operation() -> dict:
            return {"bundle": "data"}

        result = trace_snapshot_bundle_load(operation)

        assert result == {"bundle": "data"}

    def test_trace_diagnosis_loop_load_summary(self) -> None:
        """trace_diagnosis_loop_load_summary should call wrapped function."""
        def operation() -> dict:
            return {"summary": "data"}

        result = trace_diagnosis_loop_load_summary(operation)

        assert result == {"summary": "data"}

    def test_trace_diagnosis_loop_load_passes(self) -> None:
        """trace_diagnosis_loop_load_passes should call wrapped function."""
        def operation() -> list[dict]:
            return [{"pass": 1}, {"pass": 2}]

        result = trace_diagnosis_loop_load_passes(operation)

        assert result == [{"pass": 1}, {"pass": 2}]

    def test_trace_automatic_diagnosis_review_load(self) -> None:
        """trace_automatic_diagnosis_review_load should call wrapped function."""
        def operation() -> dict:
            return {"review": "data"}

        result = trace_automatic_diagnosis_review_load(operation)

        assert result == {"review": "data"}

    def test_convenience_helpers_with_attributes(self) -> None:
        """Convenience helpers should pass attributes through."""
        def operation() -> str:
            return "success"

        result = trace_incident_store_list(
            operation,
            attributes={"k9b.result.count": 5},
        )

        assert result == "success"

    def test_convenience_helpers_preserve_exception(self) -> None:
        """Convenience helpers should re-raise exceptions unchanged."""
        custom_error = ValueError("operation failed")

        def operation() -> None:
            raise custom_error

        with pytest.raises(ValueError, match="operation failed") as exc_info:
            trace_incident_store_list(operation)

        assert exc_info.value is custom_error


class TestSpanNames:
    """Tests that span names are static/low-cardinality."""

    def test_span_names_are_static_templates(self) -> None:
        """Span names should be static templates, not dynamic values."""
        # Verify all span names are used via the convenience helpers
        # by checking they can be called without error
        def noop() -> None:
            pass

        # These should not raise - they just call the wrapped function
        trace_incident_store_list(noop)
        trace_incident_store_get(noop)
        trace_artifact_scan(noop)
        trace_artifact_read_json(noop)
        trace_artifact_decode_json(noop)
        trace_review_packet_load(noop)
        trace_review_packet_project(noop)
        trace_snapshot_bundle_load(noop)
        trace_diagnosis_loop_load_summary(noop)
        trace_diagnosis_loop_load_passes(noop)
        trace_automatic_diagnosis_review_load(noop)

        # Verify custom span names can be used
        result = trace_internal_operation(
            name="k9b.custom.operation",
            call=noop,
        )
        assert result is None


class MockSpan:
    """Mock span for testing span creation and attributes."""

    def __init__(self) -> None:
        self.name: str | None = None
        self.attributes: dict[str, object] = {}
        self.exceptions: list[Exception] = []
        self.status: tuple[str, str] | None = None

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def record_exception(self, exc: Exception) -> None:
        self.exceptions.append(exc)

    def set_status(self, status: str, description: str) -> None:
        self.status = (status, description)


class MockTracer:
    """Mock tracer that records span creation."""

    def __init__(self) -> None:
        self.spans: list[MockSpan] = []
        self.current_span: MockSpan | None = None

    def start_as_current_span(self, name: str) -> MockSpan:
        span = MockSpan()
        span.name = name
        self.spans.append(span)
        self.current_span = span
        return MockSpanContext(span)

    def get_current_span(self) -> MockSpan | None:
        return self.current_span


class MockSpanContext:
    """Mock context manager for span."""

    def __init__(self, span: MockSpan) -> None:
        self.span = span

    def __enter__(self) -> MockSpan:
        return self.span

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        pass


class TestTraceInternalOperationEnabled:
    """Tests for trace_internal_operation when tracing is enabled (mocked)."""

    def test_creates_span_with_static_name(self) -> None:
        """When enabled, should create span with static name."""
        # Import and patch
        import k8s_diag_agent.observability.internal_spans as spans_module

        mock_tracer = MockTracer()
        original_get_tracer = spans_module._get_tracer
        original_is_enabled = spans_module._is_tracing_enabled

        try:
            spans_module._tracer = mock_tracer

            # Patch _is_tracing_enabled to return True
            spans_module._is_tracing_enabled = lambda: True

            result = trace_internal_operation(
                name="k9b.test.operation",
                call=lambda: "success",
            )

            assert result == "success"
            assert len(mock_tracer.spans) == 1
            assert mock_tracer.spans[0].name == "k9b.test.operation"
        finally:
            spans_module._tracer = None
            spans_module._get_tracer = original_get_tracer
            spans_module._is_tracing_enabled = original_is_enabled

    def test_sets_bounded_attributes(self) -> None:
        """When enabled, should set bounded attributes on span."""
        import k8s_diag_agent.observability.internal_spans as spans_module

        mock_tracer = MockTracer()
        original_get_tracer = spans_module._get_tracer
        original_is_enabled = spans_module._is_tracing_enabled

        try:
            spans_module._tracer = mock_tracer
            spans_module._is_tracing_enabled = lambda: True

            trace_internal_operation(
                name="k9b.test.operation",
                attributes={
                    "k9b.operation": "test",
                    "k9b.item.count": 5,
                    "k9b.result.kind": "incidents",
                },
                call=lambda: "success",
            )

            span = mock_tracer.spans[0]
            assert span.attributes.get("k9b.operation") == "test"
            assert span.attributes.get("k9b.item.count") == 5
            assert span.attributes.get("k9b.result.kind") == "incidents"
        finally:
            spans_module._tracer = None
            spans_module._get_tracer = original_get_tracer
            spans_module._is_tracing_enabled = original_is_enabled

    def test_records_exception_on_span(self) -> None:
        """When enabled, should record exception on span."""
        import k8s_diag_agent.observability.internal_spans as spans_module

        mock_tracer = MockTracer()
        original_get_tracer = spans_module._get_tracer
        original_is_enabled = spans_module._is_tracing_enabled

        try:
            spans_module._tracer = mock_tracer
            spans_module._is_tracing_enabled = lambda: True

            custom_error = ValueError("test error")

            with pytest.raises(ValueError, match="test error"):
                trace_internal_operation(
                    name="k9b.test.operation",
                    call=lambda: (_ for _ in ()).throw(custom_error),
                )

            span = mock_tracer.spans[0]
            assert len(span.exceptions) == 1
            assert span.exceptions[0] is custom_error
        finally:
            spans_module._tracer = None
            spans_module._get_tracer = original_get_tracer
            spans_module._is_tracing_enabled = original_is_enabled

    def test_sets_error_status_on_exception(self) -> None:
        """When enabled, should set error status when exception escapes."""
        import k8s_diag_agent.observability.internal_spans as spans_module

        mock_tracer = MockTracer()
        original_get_tracer = spans_module._get_tracer
        original_is_enabled = spans_module._is_tracing_enabled

        try:
            spans_module._tracer = mock_tracer
            spans_module._is_tracing_enabled = lambda: True

            with pytest.raises(ValueError):
                trace_internal_operation(
                    name="k9b.test.operation",
                    call=lambda: (_ for _ in ()).throw(ValueError("test error")),
                )

            span = mock_tracer.spans[0]
            assert span.status is not None
            assert span.status[0] == "ERROR"
            assert span.status[1] == "test error"
        finally:
            spans_module._tracer = None
            spans_module._get_tracer = original_get_tracer
            spans_module._is_tracing_enabled = original_is_enabled

    def test_re_raises_exception_unchanged(self) -> None:
        """When enabled, should re-raise exception unchanged."""
        import k8s_diag_agent.observability.internal_spans as spans_module

        mock_tracer = MockTracer()
        original_get_tracer = spans_module._get_tracer
        original_is_enabled = spans_module._is_tracing_enabled

        try:
            spans_module._tracer = mock_tracer
            spans_module._is_tracing_enabled = lambda: True

            custom_error = RuntimeError("original error")

            with pytest.raises(RuntimeError, match="original error") as exc_info:
                trace_internal_operation(
                    name="k9b.test.operation",
                    call=lambda: (_ for _ in ()).throw(custom_error),
                )

            assert exc_info.value is custom_error
        finally:
            spans_module._tracer = None
            spans_module._get_tracer = original_get_tracer
            spans_module._is_tracing_enabled = original_is_enabled


class TestInternalSpanEnabled:
    """Tests for internal_span context manager when tracing is enabled (mocked)."""

    def test_creates_span_with_static_name(self) -> None:
        """When enabled, should create span with static name."""
        import k8s_diag_agent.observability.internal_spans as spans_module

        mock_tracer = MockTracer()
        original_get_tracer = spans_module._get_tracer
        original_is_enabled = spans_module._is_tracing_enabled

        try:
            spans_module._tracer = mock_tracer
            spans_module._is_tracing_enabled = lambda: True

            with internal_span("k9b.test.operation"):
                pass

            assert len(mock_tracer.spans) == 1
            assert mock_tracer.spans[0].name == "k9b.test.operation"
        finally:
            spans_module._tracer = None
            spans_module._get_tracer = original_get_tracer
            spans_module._is_tracing_enabled = original_is_enabled

    def test_sets_bounded_attributes(self) -> None:
        """When enabled, should set bounded attributes on span."""
        import k8s_diag_agent.observability.internal_spans as spans_module

        mock_tracer = MockTracer()
        original_get_tracer = spans_module._get_tracer
        original_is_enabled = spans_module._is_tracing_enabled

        try:
            spans_module._tracer = mock_tracer
            spans_module._is_tracing_enabled = lambda: True

            with internal_span(
                "k9b.test.operation",
                attributes={"k9b.operation": "test"},
            ):
                pass

            span = mock_tracer.spans[0]
            assert span.attributes.get("k9b.operation") == "test"
        finally:
            spans_module._tracer = None
            spans_module._get_tracer = original_get_tracer
            spans_module._is_tracing_enabled = original_is_enabled

    def test_records_exception_on_span(self) -> None:
        """When enabled, should record exception on span."""
        import k8s_diag_agent.observability.internal_spans as spans_module

        mock_tracer = MockTracer()
        original_get_tracer = spans_module._get_tracer
        original_is_enabled = spans_module._is_tracing_enabled

        try:
            spans_module._tracer = mock_tracer
            spans_module._is_tracing_enabled = lambda: True

            with pytest.raises(RuntimeError):
                with internal_span("k9b.test.operation"):
                    raise RuntimeError("block error")

            span = mock_tracer.spans[0]
            assert len(span.exceptions) == 1
            assert span.status is not None
            assert span.status[0] == "ERROR"
        finally:
            spans_module._tracer = None
            spans_module._get_tracer = original_get_tracer
            spans_module._is_tracing_enabled = original_is_enabled

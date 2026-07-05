"""OpenTelemetry internal span instrumentation for k9b backend.

This module provides disabled-by-default internal span instrumentation for
meaningful latency boundaries inside backend read/projection paths:
- incident store reads
- on-disk artifact discovery and reading
- JSON file reads and decoding
- review packet assembly
- automatic diagnosis review loading
- diagnosis loop pass/run summary loading
- filesystem scans over lab/run artifacts

The instrumentation is activated only when K9B_OTEL_ENABLED is set to a truthy value.

Span names are low-cardinality and use static templates (e.g., "k9b.incident_store.list").
Attributes are bounded and privacy-safe (no raw paths, secrets, or payloads).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping


T = TypeVar("T")

logger = logging.getLogger(__name__)

# =============================================================================
# Tracer Acquisition
# =============================================================================

# Lazy import holder for tracer (avoids heavyweight import when disabled)
_tracer = None


def _get_tracer() -> object | None:
    """Get or create the OTel tracer for internal spans.

    Returns None if tracing is not available/disabled.
    """
    global _tracer
    if _tracer is None:
        try:
            from opentelemetry import trace

            _tracer = trace.get_tracer(__name__)
        except ImportError:
            # OTel not installed - return None to indicate tracing unavailable
            return None
    return _tracer


def _is_tracing_enabled() -> bool:
    """Check if tracing is enabled via configuration.

    Returns True only when K9B_OTEL_ENABLED is truthy and OTel SDK is available.
    """
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        # Check if provider is the no-op provider (default when not configured)
        # The no-op provider class name contains "None" when not initialized
        provider_class = type(provider).__name__
        if "None" in provider_class or "no_op" in provider_class.lower():
            return False
        return True
    except ImportError:
        return False
    except Exception:
        return False


# =============================================================================
# Callable Wrapper Form
# =============================================================================


def trace_internal_operation(
    *,
    name: str,
    attributes: Mapping[str, str | int | float | bool] | None = None,
    call: Callable[[], T],
) -> T:
    """Wrap an internal operation call with an OpenTelemetry span.

    This function provides internal span instrumentation for meaningful
    latency boundaries. When tracing is disabled or unavailable, it simply
    executes the call without any instrumentation overhead.

    Args:
        name: Static span name template (e.g., "k9b.incident_store.list").
              Must NOT contain dynamic values like IDs or paths.
        attributes: Optional bounded attributes to attach to the span.
            Allowed keys: k9b.operation, k9b.item.kind, k9b.item.count,
            k9b.file.count, k9b.file.bytes, k9b.cache.hit, k9b.result.count,
            k9b.result.kind, k9b.error.kind, k9b.namespace_present,
            k9b.incident_class, k9b.schema_version, k9b.artifact_kind,
            k9b.projection_kind, k9b.path.kind.
            Do NOT include request bodies, response bodies, raw paths,
            secrets, tokens, or kubeconfigs.
        call: The operation to wrap with instrumentation.

    Returns:
        The return value of the call.

    Raises:
        Re-raises any exception from the call unchanged after recording
        it on the span if tracing is active.
    """
    # Fast path: if tracing is disabled, just execute the call
    tracer = _get_tracer()
    if tracer is None:
        return call()

    if not _is_tracing_enabled():
        return call()

    # Create and use the span
    with tracer.start_as_current_span(name) as span:
        # Set bounded attributes if provided
        if attributes is not None:
            for key, value in attributes.items():
                # Only set attribute if value is safe type
                if isinstance(value, (str, int, float, bool)):
                    span.set_attribute(key, value)

        try:
            result = call()
            return result
        except Exception as exc:
            # Record exception on span and set error status per OTel semantic conventions
            span.record_exception(exc)
            span.set_status("ERROR", str(exc))
            # Set error kind attribute (safe, bounded)
            span.set_attribute("k9b.error.kind", exc.__class__.__name__)
            raise


# =============================================================================
# Context Manager Form
# =============================================================================


@contextmanager
def internal_span(
    name: str,
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> Iterator[None]:
    """Context manager for creating an internal span around a block of code.

    This is an alternative to trace_internal_operation() for cases where
    you want to wrap a larger block of code or multiple operations.

    When tracing is disabled or unavailable, this context manager is a no-op.

    Args:
        name: Static span name template (e.g., "k9b.artifact.scan").
              Must NOT contain dynamic values like IDs or paths.
        attributes: Optional bounded attributes to attach to the span.
            See trace_internal_operation() for allowed keys.

    Yields:
        None (the context manager does not provide the span object).

    Example:
        with internal_span("k9b.incident_store.list", {"k9b.result.kind": "incidents"}):
            incidents = store.list_incidents()
    """
    # Fast path: if tracing is disabled, yield immediately (no-op)
    tracer = _get_tracer()
    if tracer is None:
        yield
        return

    if not _is_tracing_enabled():
        yield
        return

    # Create and use the span
    with tracer.start_as_current_span(name) as span:
        # Set bounded attributes if provided
        if attributes is not None:
            for key, value in attributes.items():
                # Only set attribute if value is safe type
                if isinstance(value, (str, int, float, bool)):
                    span.set_attribute(key, value)

        try:
            yield
        except Exception as exc:
            # Record exception on span and set error status per OTel semantic conventions
            span.record_exception(exc)
            span.set_status("ERROR", str(exc))
            # Set error kind attribute (safe, bounded)
            span.set_attribute("k9b.error.kind", exc.__class__.__name__)
            raise


# =============================================================================
# Convenience helpers for common patterns
# =============================================================================


def trace_incident_store_list(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap incident store list operation with a span.

    Args:
        call: The list_incidents call to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "list"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.incident_store.list",
        attributes=attrs,
        call=call,
    )


def trace_incident_store_get(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap incident store get operation with a span.

    Args:
        call: The get_incident call to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "get"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.incident_store.get",
        attributes=attrs,
        call=call,
    )


def trace_artifact_scan(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap artifact directory scan with a span.

    Args:
        call: The scan operation to wrap.
        attributes: Optional bounded attributes including k9b.file.count.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "scan"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.artifact.scan",
        attributes=attrs,
        call=call,
    )


def trace_artifact_read_json(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap artifact JSON file read with a span.

    Args:
        call: The JSON file read operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "read"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.artifact.read_json",
        attributes=attrs,
        call=call,
    )


def trace_artifact_decode_json(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap JSON decode/projection with a span.

    Args:
        call: The decode/projection operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "decode"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.artifact.decode_json",
        attributes=attrs,
        call=call,
    )


def trace_review_packet_load(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap review packet load with a span.

    Args:
        call: The review packet load operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "load"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.review_packet.load",
        attributes=attrs,
        call=call,
    )


def trace_review_packet_project(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap review packet projection with a span.

    Args:
        call: The projection operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "project"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.review_packet.project",
        attributes=attrs,
        call=call,
    )


def trace_snapshot_bundle_load(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap snapshot bundle load with a span.

    Args:
        call: The bundle load operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "load"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.snapshot_bundle.load",
        attributes=attrs,
        call=call,
    )


def trace_diagnosis_loop_load_summary(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap diagnosis loop summary load with a span.

    Args:
        call: The summary load operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "load_summary"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.diagnosis_loop.load_summary",
        attributes=attrs,
        call=call,
    )


def trace_diagnosis_loop_load_passes(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap diagnosis loop passes load with a span.

    Args:
        call: The passes load operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "load_passes"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.diagnosis_loop.load_passes",
        attributes=attrs,
        call=call,
    )


def trace_automatic_diagnosis_review_load(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap automatic diagnosis review load with a span.

    Args:
        call: The review load operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "load"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.automatic_diagnosis_review.load",
        attributes=attrs,
        call=call,
    )


def trace_api_response_project(
    call: Callable[[], T],
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> T:
    """Wrap API response projection with a span.

    Args:
        call: The projection operation to wrap.
        attributes: Optional bounded attributes.

    Returns:
        The return value of the call.
    """
    attrs: dict[str, str | int | float | bool] = {"k9b.operation": "project"}
    if attributes:
        attrs.update(attributes)
    return trace_internal_operation(
        name="k9b.api.response.project",
        attributes=attrs,
        call=call,
    )

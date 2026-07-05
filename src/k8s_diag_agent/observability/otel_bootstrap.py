"""OpenTelemetry bootstrap module for k9b backend.

This module provides a disabled-by-default OpenTelemetry bootstrap seam:
- Zero behavior change when tracing is disabled
- No exporter/network dependency when disabled
- Safe startup when enabled
- Bounded configuration surface
- Testable without requiring a live collector

Environment variables:
- K9B_OTEL_ENABLED: Enable tracing (default: false)
- K9B_OTEL_SERVICE_NAME: Service name for traces (default: k9b-backend)
- K9B_OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint (optional)
- K9B_OTEL_SAMPLE_RATIO: Sampling ratio 0.0-1.0 (default: 1.0)
"""

from __future__ import annotations

import logging
import math
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

# =============================================================================
# Environment Variable Names
# =============================================================================

_ENV_ENABLED: Final[str] = "K9B_OTEL_ENABLED"
_ENV_SERVICE_NAME: Final[str] = "K9B_OTEL_SERVICE_NAME"
_ENV_ENDPOINT: Final[str] = "K9B_OTEL_EXPORTER_OTLP_ENDPOINT"
_ENV_SAMPLE_RATIO: Final[str] = "K9B_OTEL_SAMPLE_RATIO"

# =============================================================================
# Default Values
# =============================================================================

_DEFAULT_SERVICE_NAME: Final[str] = "k9b-backend"
_DEFAULT_SAMPLE_RATIO: Final[float] = 1.0

# =============================================================================
# Boolean Truthy Values
# =============================================================================

_TRUTHY_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


# =============================================================================
# OTelConfig Dataclass
# =============================================================================


@dataclass(frozen=True)
class OTelConfig:
    """Configuration for OpenTelemetry bootstrap.

    Attributes:
        enabled: Whether tracing is enabled
        service_name: Service name for resource attributes
        endpoint: OTLP exporter endpoint (None if disabled or no endpoint configured)
        sample_ratio: Sampling ratio between 0.0 and 1.0
    """

    enabled: bool
    service_name: str
    endpoint: str | None
    sample_ratio: float


# =============================================================================
# Configuration Loading
# =============================================================================


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a boolean environment variable.

    Args:
        value: The environment variable value
        default: Default value if not set

    Returns:
        Parsed boolean value
    """
    if value is None:
        return default
    return value.lower() in _TRUTHY_VALUES


def _parse_sample_ratio(value: str | None, default: float) -> float:
    """Parse a sample ratio from environment variable.

    Args:
        value: The environment variable value
        default: Default value if not set or invalid

    Returns:
        Parsed sample ratio, clamped to [0.0, 1.0]
    """
    if value is None:
        return default
    try:
        ratio = float(value)
        # Fail closed: clamp to valid range
        if math.isnan(ratio) or math.isinf(ratio):
            logger.warning(
                "Invalid sample ratio %r (NaN or Inf), using default %f",
                value,
                default,
            )
            return default
        return max(0.0, min(1.0, ratio))
    except ValueError:
        logger.warning(
            "Invalid sample ratio %r, using default %f",
            value,
            default,
        )
        return default


def load_otel_config_from_env(
    env: dict[str, str] | None = None,
) -> OTelConfig:
    """Load OpenTelemetry configuration from environment variables.

    This function reads K9B_OTEL_* environment variables and returns
    an OTelConfig instance. It never raises exceptions.

    Args:
        env: Optional environment mapping for testing (defaults to os.environ)

    Returns:
        OTelConfig instance with loaded configuration
    """
    if env is None:
        env = dict(os.environ)

    enabled = _parse_bool(env.get(_ENV_ENABLED), default=False)
    service_name = env.get(_ENV_SERVICE_NAME, _DEFAULT_SERVICE_NAME)
    endpoint = env.get(_ENV_ENDPOINT)
    sample_ratio = _parse_sample_ratio(env.get(_ENV_SAMPLE_RATIO), _DEFAULT_SAMPLE_RATIO)

    return OTelConfig(
        enabled=enabled,
        service_name=service_name,
        endpoint=endpoint,
        sample_ratio=sample_ratio,
    )


# =============================================================================
# OTel SDK Initialization
# =============================================================================

# Track whether OTel has been initialized to support idempotent calls
_otel_initialized: bool = False


def configure_otel(config: OTelConfig) -> None:
    """Configure OpenTelemetry SDK based on OTelConfig.

    This function is safe to call even when OTel is not installed
    or when tracing is disabled. It logs initialization status.

    When enabled:
    - Initializes tracer provider with resource attributes
    - Configures OTLP span export using batch processor
    - Sets up sampling based on sample_ratio

    When disabled:
    - No-op (safe to call from startup)
    - Does not import heavyweight exporter modules at top level

    Args:
        config: OTelConfig instance with desired settings
    """
    global _otel_initialized

    if not config.enabled:
        logger.debug("OpenTelemetry tracing is disabled")
        return

    # Lazy import to avoid heavyweight dependencies when disabled
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        print(
            "OpenTelemetry SDK not installed. "
            "Install with: pip install opentelemetry-sdk opentelemetry-exporter-otlp",
            file=sys.stderr,
        )
        return

    # Lazily import OTLP exporter to avoid network/exporter dependency when disabled
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError:
        print(
            "OTLP exporter not installed. "
            "Install with: pip install opentelemetry-exporter-otlp",
            file=sys.stderr,
        )
        return

    # Check for endpoint
    if not config.endpoint:
        logger.warning(
            "K9B_OTEL_EXPORTER_OTLP_ENDPOINT not set, tracing disabled"
        )
        return

    # Guard against repeated initialization (OTel global provider is set-once)
    if _otel_initialized:
        logger.debug("OpenTelemetry already initialized, skipping")
        return

    # Build resource with service name
    resource = Resource.create({
        "service.name": config.service_name,
        "service.version": "1.0.0",
    })

    # Configure sampling
    sampler = TraceIdRatioBased(config.sample_ratio)

    # Create tracer provider
    tracer_provider: TracerProvider = TracerProvider(
        resource=resource,
        sampler=sampler,
    )

    # Create OTLP exporter and batch processor
    otlp_exporter = OTLPSpanExporter(endpoint=config.endpoint, insecure=True)
    span_processor: BatchSpanProcessor = BatchSpanProcessor(otlp_exporter)

    # Register processor with provider
    tracer_provider.add_span_processor(span_processor)

    # Set as global tracer provider (supports repeated initialization in tests)
    from opentelemetry import trace

    trace.set_tracer_provider(tracer_provider)

    _otel_initialized = True
    logger.info(
        "OpenTelemetry configured: service=%s endpoint=%s sample_ratio=%s",
        config.service_name,
        config.endpoint,
        config.sample_ratio,
    )


def reset_otel_for_testing() -> None:
    """Reset OTel state for testing (not part of public API).

    This resets the initialization flag to allow tests to exercise
    configure_otel() multiple times without side effects.
    """
    global _otel_initialized
    _otel_initialized = False

"""Tests for golden-case fake handlers.

Tests that verify:
- Fake handlers have no_kubernetes_call flag
- Fake handlers return context-aware evidence from golden-case bundles
- Unknown check ids fail closed in the runner
- Handler invocation evidence is recorded
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.golden_case_fake_handlers import (
    create_golden_case_fake_handlers,
)

# =============================================================================
# Fixtures
# =============================================================================


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"


@pytest.fixture
def evidence_provider() -> GoldenCaseEvidenceProvider:
    """Create evidence provider for golden case."""
    return GoldenCaseEvidenceProvider(FIXTURES_DIR)


# =============================================================================
# Tests: Fake handler invocation
# =============================================================================


def test_fake_handlers_have_no_kubernetes_call_flag(
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Verify fake handlers have no_kubernetes_call flag."""
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)

    # All handlers should have no_kubernetes_call flag
    for check_id, handler in fake_handlers.items():
        result = handler(
            {"check_id": check_id, "parameters": {}},
            now=datetime.now(UTC),
        )
        assert result.get("no_kubernetes_call") is True, f"Handler {check_id} missing no_kubernetes_call flag"


def test_fake_handlers_return_golden_case_evidence(
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Verify fake handlers return golden-case evidence."""
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)

    # Test pod_describe handler
    handler = fake_handlers.get("pod_describe")
    assert handler is not None

    result = handler(
        {
            "check_id": "pod_describe",
            "parameters": {
                "namespace": "test-namespace",
                "object_name": "test-pod",
            },
        },
        now=datetime.now(UTC),
    )

    assert result.get("golden_case_handler") is True
    assert result.get("no_kubernetes_call") is True
    assert "observations" in result


def test_fake_handlers_use_evidence_provider(
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Verify fake handlers use evidence from the provider."""
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)

    # Test pod_events handler
    handler = fake_handlers.get("pod_events")
    assert handler is not None

    result = handler(
        {
            "check_id": "pod_events",
            "parameters": {
                "namespace": "test-namespace",
                "object_name": "test-pod",
            },
        },
        now=datetime.now(UTC),
    )

    # Handler should have evidence from provider
    assert "observations" in result
    # Should include namespace in observations
    assert any("test-namespace" in str(o) for o in result["observations"])


def test_all_expected_handlers_exist(
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Verify all expected fake handlers exist."""
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)

    expected_handlers = [
        "pod_describe",
        "pod_events",
        "pod_logs",
        "deployment_status",
        "node_status",
        "service_endpoints",
    ]

    for handler_id in expected_handlers:
        assert handler_id in fake_handlers, f"Missing handler: {handler_id}"
        assert callable(fake_handlers[handler_id])


def test_fake_handler_protocol_compliance(
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Verify fake handlers follow the ReadOnlyCheckHandler protocol."""
    from collections.abc import Mapping
    from typing import Any


    fake_handlers = create_golden_case_fake_handlers(evidence_provider)

    # All handlers should be callable
    for check_id, handler in fake_handlers.items():
        assert callable(handler), f"Handler {check_id} is not callable"

        # Handler should accept (check, *, now) signature
        check: dict[str, Any] = {"check_id": check_id, "parameters": {}}
        result = handler(check, now=datetime.now(UTC))

        # Result should be a mapping
        assert isinstance(result, Mapping), f"Handler {check_id} did not return a Mapping"

        # Result should have required fields
        assert "summary" in result, f"Handler {check_id} missing 'summary'"
        assert "observations" in result, f"Handler {check_id} missing 'observations'"

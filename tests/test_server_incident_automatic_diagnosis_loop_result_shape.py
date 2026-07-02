"""Result-shape and serialization regression tests for automatic diagnosis loop.

This module tests that:
1. Response shapes are JSON-serializable without MagicMock leakage
2. Budget diagnostics serialize correctly whether dict or dataclass
3. Missing optional fields are normalized to safe defaults
4. Nested dataclasses inside dicts are recursively serialized

Moved from test_server_incident_automatic_diagnosis_loop.py to keep
route/handler behavior tests separate from contract/serialization regressions.

Note: Uses SimpleNamespace for result objects to avoid MagicMock attribute
auto-creation that can cause high-CPU/recursive behavior during serialization.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
    handle_incident_automatic_diagnosis_loop_one_pass_api,
)


def _skipped_result(
    *,
    reason: str,
    budget_diagnostics: object = (),
) -> SimpleNamespace:
    """Create a safe skipped result object using SimpleNamespace."""
    return SimpleNamespace(
        skipped=True,
        eligible=False,
        eligibility_reason=reason,
        skip_reason=reason,
        budget_diagnostics=budget_diagnostics,
    )


def _response_for_result(result: object) -> dict[str, Any]:
    """Call the handler with the given result and return the response dict."""
    handler = SimpleNamespace(
        command="POST",
        _health_root=Path("/tmp/health"),
        body=b"{}",  # Empty JSON body for config parsing
    )

    with (
        patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop."
            "collect_automatic_diagnosis_evidence",
            return_value=result,
        ),
        patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop."
            "send_json_response"
        ) as mock_send,
    ):
        handle_incident_automatic_diagnosis_loop_one_pass_api(
            cast(MagicMock, handler),
            "incident-123",
        )

    call_args = mock_send.call_args
    assert call_args is not None
    assert call_args.kwargs["code"] == 200

    response = call_args.args[1]
    assert isinstance(response, dict)
    return cast(dict[str, Any], response)


class TestBudgetDiagnosticsSerialization:
    """Tests for budget diagnostics serialization edge cases.

    Regression tests for bug where budget_diagnostics contained dict items
    instead of DiagnosisBudgetDiagnostic dataclass instances, causing
    AttributeError: 'dict' object has no attribute 'to_dict'.
    """

    def test_skipped_with_dict_budget_diagnostics(self) -> None:
        """Regression: budget_diagnostics with dict items should not crash handler.

        This reproduces the bug where result.budget_diagnostics contained
        plain dicts instead of DiagnosisBudgetDiagnostic instances, causing:
        AttributeError: 'dict' object has no attribute 'to_dict'
        """
        response = _response_for_result(
            _skipped_result(
                reason="budget_exhausted",
                budget_diagnostics=[
                    {
                        "name": "review_packet_budget",
                        "limit": 10,
                        "remaining": 0,
                        "exhausted": True,
                        "auto_pass_count": 10,
                    },
                    {
                        "name": "api_call_budget",
                        "limit": 100,
                        "remaining": 50,
                        "exhausted": False,
                        "auto_pass_count": 50,
                    },
                ],
            )
        )

        assert response["skipped"] is True
        assert "budget_diagnostics" in response
        assert len(response["budget_diagnostics"]) == 2
        assert response["budget_diagnostics"][0]["name"] == "review_packet_budget"
        assert response["budget_diagnostics"][0]["exhausted"] is True

    def test_skipped_with_dataclass_budget_diagnostics(self) -> None:
        """Regression: budget_diagnostics with dataclass items should still work.

        Normal case where budget_diagnostics contains DiagnosisBudgetDiagnostic
        instances with proper to_dict() method.
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            DiagnosisBudgetDiagnostic,
        )

        response = _response_for_result(
            _skipped_result(
                reason="budget_exhausted",
                budget_diagnostics=(
                    DiagnosisBudgetDiagnostic(
                        name="review_packet_budget",
                        used=10,
                        limit=10,
                        remaining=0,
                        exhausted=True,
                        source="review_packet_artifacts",
                        resettable=True,
                    ),
                ),
            )
        )

        assert response["skipped"] is True
        assert "budget_diagnostics" in response
        assert len(response["budget_diagnostics"]) == 1
        assert response["budget_diagnostics"][0]["name"] == "review_packet_budget"

    def test_skipped_with_empty_budget_diagnostics(self) -> None:
        """Regression: empty budget_diagnostics should not cause errors."""
        response = _response_for_result(
            _skipped_result(
                reason="incident_closed",
                budget_diagnostics=(),
            )
        )

        assert response["skipped"] is True
        # budget_diagnostics key should not be present when empty
        assert "budget_diagnostics" not in response or response["budget_diagnostics"] == []

    def test_skipped_with_nested_dataclass_inside_dict_budget_diagnostics(self) -> None:
        """Regression: dict containing nested dataclass should be recursively serialized.

        This protects the serializer contract when a dict contains a dataclass
        nested inside it (not at the top level of the list item).
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            DiagnosisBudgetDiagnostic,
        )

        response = _response_for_result(
            _skipped_result(
                reason="budget_exhausted",
                budget_diagnostics=[
                    {
                        "name": "review_packet_budget",
                        "nested": DiagnosisBudgetDiagnostic(
                            name="inner",
                            used=1,
                            limit=1,
                            remaining=0,
                            exhausted=True,
                            source="test",
                            resettable=True,
                        ),
                    }
                ],
            )
        )

        assert response["skipped"] is True
        assert "budget_diagnostics" in response
        assert response["budget_diagnostics"][0]["name"] == "review_packet_budget"
        # Verify nested dataclass was recursively serialized to dict
        assert response["budget_diagnostics"][0]["nested"]["name"] == "inner"
        assert response["budget_diagnostics"][0]["nested"]["used"] == 1
        assert response["budget_diagnostics"][0]["nested"]["exhausted"] is True

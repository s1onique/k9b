"""Tests for model_review_enrichment module import compatibility and behavior.

Verifies that review-enrichment-related symbols remain importable from both:
- k8s_diag_agent.ui.model (backward compatibility)
- k8s_diag_agent.ui.model_review_enrichment (new modular location)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.model import (
    ReviewEnrichmentStatusView as Model_ReviewEnrichmentStatusView,
)
from k8s_diag_agent.ui.model import (
    ReviewEnrichmentView as Model_ReviewEnrichmentView,
)
from k8s_diag_agent.ui.model import (
    _build_review_enrichment_status_view as Model__build_review_enrichment_status_view,
)
from k8s_diag_agent.ui.model import (
    _build_review_enrichment_view as Model__build_review_enrichment_view,
)
from k8s_diag_agent.ui.model_alertmanager import AlertmanagerEvidenceReferenceView
from k8s_diag_agent.ui.model_review_enrichment import (
    ReviewEnrichmentStatusView,
    ReviewEnrichmentView,
    _build_review_enrichment_status_view,
    _build_review_enrichment_view,
)


class TestImportCompatibility(unittest.TestCase):
    """Verify symbols are importable from both locations."""

    def test_review_enrichment_status_view_importable_from_model_review_enrichment(self) -> None:
        """ReviewEnrichmentStatusView should be importable from model_review_enrichment."""
        assert ReviewEnrichmentStatusView is not None

    def test_review_enrichment_status_view_importable_from_model(self) -> None:
        """ReviewEnrichmentStatusView should be re-exported from model for backward compatibility."""
        assert Model_ReviewEnrichmentStatusView is not None

    def test_review_enrichment_view_importable_from_model_review_enrichment(self) -> None:
        """ReviewEnrichmentView should be importable from model_review_enrichment."""
        assert ReviewEnrichmentView is not None

    def test_review_enrichment_view_importable_from_model(self) -> None:
        """ReviewEnrichmentView should be re-exported from model for backward compatibility."""
        assert Model_ReviewEnrichmentView is not None

    def test_build_review_enrichment_view_importable_from_model_review_enrichment(self) -> None:
        """_build_review_enrichment_view should be importable from model_review_enrichment."""
        assert callable(_build_review_enrichment_view)

    def test_build_review_enrichment_view_importable_from_model(self) -> None:
        """_build_review_enrichment_view should be re-exported from model for backward compatibility."""
        assert callable(Model__build_review_enrichment_view)

    def test_build_review_enrichment_status_view_importable_from_model_review_enrichment(self) -> None:
        """_build_review_enrichment_status_view should be importable from model_review_enrichment."""
        assert callable(_build_review_enrichment_status_view)

    def test_build_review_enrichment_status_view_importable_from_model(self) -> None:
        """_build_review_enrichment_status_view should be re-exported from model for backward compatibility."""
        assert callable(Model__build_review_enrichment_status_view)


class TestReviewEnrichmentStatusViewDataclassBehavior(unittest.TestCase):
    """Verify ReviewEnrichmentStatusView dataclass behavior is preserved."""

    def test_review_enrichment_status_view_creation(self) -> None:
        """ReviewEnrichmentStatusView should be created with all required fields."""
        view = ReviewEnrichmentStatusView(
            status="active",
            reason="provider available",
            provider="openai",
            policy_enabled=True,
            provider_configured=True,
            adapter_available=True,
        )
        assert view.status == "active"
        assert view.reason == "provider available"
        assert view.policy_enabled is True
        assert view.provider_configured is True
        assert view.adapter_available is True

    def test_review_enrichment_status_view_with_optional_fields(self) -> None:
        """ReviewEnrichmentStatusView should accept optional fields."""
        view = ReviewEnrichmentStatusView(
            status="disabled",
            reason=None,
            provider=None,
            policy_enabled=False,
            provider_configured=False,
            adapter_available=None,
            run_enabled=True,
            run_provider="anthropic",
        )
        assert view.status == "disabled"
        assert view.run_enabled is True
        assert view.run_provider == "anthropic"

    def test_review_enrichment_status_view_frozen(self) -> None:
        """ReviewEnrichmentStatusView should be frozen."""
        view = ReviewEnrichmentStatusView(
            status="active",
            reason=None,
            provider=None,
            policy_enabled=True,
            provider_configured=True,
            adapter_available=None,
        )
        with self.assertRaises(Exception):  # dataclasses.FrozenInstanceError
            view.status = "modified"  # type: ignore[misc]


class TestReviewEnrichmentViewDataclassBehavior(unittest.TestCase):
    """Verify ReviewEnrichmentView dataclass behavior is preserved."""

    def test_review_enrichment_view_creation(self) -> None:
        """ReviewEnrichmentView should be created with all required fields."""
        view = ReviewEnrichmentView(
            status="completed",
            provider="openai",
            timestamp="2024-01-01T00:00:00Z",
            summary="Review enrichment completed",
            triage_order=("priority-1", "priority-2"),
            top_concerns=("concern1", "concern2"),
            evidence_gaps=("gap1",),
            next_checks=("check1",),
            focus_notes=("note1",),
            alertmanager_evidence_references=(),
            artifact_path="/path/to/enrichment",
            error_summary=None,
            skip_reason=None,
        )
        assert view.status == "completed"
        assert view.provider == "openai"
        assert len(view.triage_order) == 2
        assert len(view.top_concerns) == 2
        assert view.artifact_path == "/path/to/enrichment"

    def test_review_enrichment_view_frozen(self) -> None:
        """ReviewEnrichmentView should be frozen."""
        view = ReviewEnrichmentView(
            status="pending",
            provider=None,
            timestamp=None,
            summary=None,
            triage_order=(),
            top_concerns=(),
            evidence_gaps=(),
            next_checks=(),
            focus_notes=(),
            alertmanager_evidence_references=(),
            artifact_path=None,
            error_summary=None,
            skip_reason=None,
        )
        with self.assertRaises(Exception):  # dataclasses.FrozenInstanceError
            view.status = "modified"  # type: ignore[misc]

    def test_review_enrichment_view_with_alertmanager_references(self) -> None:
        """ReviewEnrichmentView should contain alertmanager evidence references."""
        am_ref = AlertmanagerEvidenceReferenceView(
            cluster="test-cluster",
            matched_dimensions=("alertname",),
            reason="Matching alert detected",
            used_for="next_check_prioritization",
        )
        view = ReviewEnrichmentView(
            status="completed",
            provider="openai",
            timestamp="2024-01-01T00:00:00Z",
            summary="Summary",
            triage_order=(),
            top_concerns=(),
            evidence_gaps=(),
            next_checks=(),
            focus_notes=(),
            alertmanager_evidence_references=(am_ref,),
            artifact_path=None,
            error_summary=None,
            skip_reason=None,
        )
        assert len(view.alertmanager_evidence_references) == 1
        assert view.alertmanager_evidence_references[0].cluster == "test-cluster"


class TestBuildReviewEnrichmentViewBehavior(unittest.TestCase):
    """Verify _build_review_enrichment_view behavior is preserved."""

    def test_build_review_enrichment_view_from_valid_mapping(self) -> None:
        """_build_review_enrichment_view should build ReviewEnrichmentView from raw mapping."""
        raw = {
            "status": "completed",
            "provider": "openai",
            "timestamp": "2024-01-01T00:00:00Z",
            "summary": "Enrichment summary",
            "triageOrder": ["priority-1", "priority-2"],
            "topConcerns": ["concern1", "concern2"],
            "evidenceGaps": ["gap1"],
            "nextChecks": ["check1"],
            "focusNotes": ["note1"],
            "artifactPath": "/path/to/enrichment",
        }
        result = _build_review_enrichment_view(raw)
        assert isinstance(result, ReviewEnrichmentView)
        assert result.status == "completed"
        assert result.provider == "openai"
        assert result.triage_order == ("priority-1", "priority-2")
        assert result.top_concerns == ("concern1", "concern2")
        assert result.evidence_gaps == ("gap1",)
        assert result.next_checks == ("check1",)
        assert result.focus_notes == ("note1",)

    def test_build_review_enrichment_view_with_snake_case_keys(self) -> None:
        """_build_review_enrichment_view should handle snake_case keys."""
        raw = {
            "status": "pending",
            "triage_order": ["p1"],
            "top_concerns": ["c1"],
            "evidence_gaps": ["g1"],
            "next_checks": ["nc1"],
            "focus_notes": ["fn1"],
        }
        result = _build_review_enrichment_view(raw)
        assert isinstance(result, ReviewEnrichmentView)
        assert result.status == "pending"
        assert result.triage_order == ("p1",)

    def test_build_review_enrichment_view_with_none_input(self) -> None:
        """_build_review_enrichment_view should return None for None input."""
        result = _build_review_enrichment_view(None)
        assert result is None

    def test_build_review_enrichment_view_with_non_mapping_input(self) -> None:
        """_build_review_enrichment_view should return None for non-Mapping input."""
        result = _build_review_enrichment_view("not a mapping")
        assert result is None

    def test_build_review_enrichment_view_with_non_mapping_input_list(self) -> None:
        """_build_review_enrichment_view should return None for list input."""
        result = _build_review_enrichment_view(["item1", "item2"])
        assert result is None

    def test_build_review_enrichment_view_with_missing_fields(self) -> None:
        """_build_review_enrichment_view should handle missing fields with defaults."""
        raw: dict = {}
        result = _build_review_enrichment_view(raw)
        assert isinstance(result, ReviewEnrichmentView)
        assert result.status == "-"
        assert result.provider is None
        assert result.triage_order == ()
        assert result.top_concerns == ()
        assert result.alertmanager_evidence_references == ()

    def test_build_review_enrichment_view_with_alertmanager_references(self) -> None:
        """_build_review_enrichment_view should build alertmanager evidence references."""
        raw = {
            "status": "completed",
            "alertmanagerEvidenceReferences": [
                {
                    "cluster": "test-cluster",
                    "matchedDimensions": ["alertname", "severity"],
                    "reason": "Matching alert detected",
                    "usedFor": "next_check_prioritization",
                },
                {
                    "cluster": "test-cluster",
                    "matchedDimensions": ["namespace"],
                    "reason": "Namespace alert",
                    "usedFor": "evidence_gap_identification",
                },
            ],
        }
        result = _build_review_enrichment_view(raw)
        assert isinstance(result, ReviewEnrichmentView)
        assert len(result.alertmanager_evidence_references) == 2
        assert result.alertmanager_evidence_references[0].cluster == "test-cluster"
        assert result.alertmanager_evidence_references[0].matched_dimensions == ("alertname", "severity")
        assert result.alertmanager_evidence_references[1].matched_dimensions == ("namespace",)

    def test_build_review_enrichment_view_skips_malformed_alertmanager_entries(self) -> None:
        """_build_review_enrichment_view should skip malformed alertmanager evidence entries."""
        raw = {
            "status": "completed",
            "alertmanagerEvidenceReferences": [
                "not a mapping",  # Should be skipped
                {"cluster": "test-cluster", "matched_dimensions": [], "reason": "ok", "used_for": "test"},
                42,  # Should be skipped
                {"cluster": "another-cluster", "matchedDimensions": [], "reason": "also ok", "usedFor": "test"},
            ],
        }
        result = _build_review_enrichment_view(raw)
        assert isinstance(result, ReviewEnrichmentView)
        assert len(result.alertmanager_evidence_references) == 2

    def test_build_review_enrichment_view_with_empty_alertmanager_references(self) -> None:
        """_build_review_enrichment_view should handle empty alertmanager references."""
        raw = {
            "status": "completed",
            "alertmanagerEvidenceReferences": [],
        }
        result = _build_review_enrichment_view(raw)
        assert isinstance(result, ReviewEnrichmentView)
        assert result.alertmanager_evidence_references == ()


class TestBuildReviewEnrichmentStatusViewBehavior(unittest.TestCase):
    """Verify _build_review_enrichment_status_view behavior is preserved."""

    def test_build_review_enrichment_status_view_from_valid_mapping(self) -> None:
        """_build_review_enrichment_status_view should build ReviewEnrichmentStatusView from raw mapping."""
        raw = {
            "status": "active",
            "reason": "provider available",
            "provider": "openai",
            "policyEnabled": True,
            "providerConfigured": True,
            "adapterAvailable": True,
        }
        result = _build_review_enrichment_status_view(raw)
        assert isinstance(result, ReviewEnrichmentStatusView)
        assert result.status == "active"
        assert result.reason == "provider available"
        assert result.provider == "openai"
        assert result.policy_enabled is True
        assert result.provider_configured is True
        assert result.adapter_available is True

    def test_build_review_enrichment_status_view_with_camel_case_keys(self) -> None:
        """_build_review_enrichment_status_view should handle camelCase keys."""
        raw = {
            "status": "disabled",
            "reason": None,
            "provider": None,
            "policyEnabled": False,
            "providerConfigured": False,
            "adapterAvailable": None,
            "runEnabled": True,
            "runProvider": "anthropic",
        }
        result = _build_review_enrichment_status_view(raw)
        assert isinstance(result, ReviewEnrichmentStatusView)
        assert result.status == "disabled"
        assert result.run_enabled is True
        assert result.run_provider == "anthropic"

    def test_build_review_enrichment_status_view_with_none_input(self) -> None:
        """_build_review_enrichment_status_view should return None for None input."""
        result = _build_review_enrichment_status_view(None)
        assert result is None

    def test_build_review_enrichment_status_view_with_non_mapping_input(self) -> None:
        """_build_review_enrichment_status_view should return None for non-Mapping input."""
        result = _build_review_enrichment_status_view("not a mapping")
        assert result is None

    def test_build_review_enrichment_status_view_with_non_mapping_input_list(self) -> None:
        """_build_review_enrichment_status_view should return None for list input."""
        result = _build_review_enrichment_status_view(["item1", "item2"])
        assert result is None

    def test_build_review_enrichment_status_view_with_missing_fields(self) -> None:
        """_build_review_enrichment_status_view should handle missing fields with defaults."""
        raw: dict = {}
        result = _build_review_enrichment_status_view(raw)
        assert isinstance(result, ReviewEnrichmentStatusView)
        assert result.status == "-"
        assert result.reason is None
        assert result.provider is None
        assert result.policy_enabled is False
        assert result.provider_configured is False
        assert result.adapter_available is None
        assert result.run_enabled is None
        assert result.run_provider is None


class TestEquivalenceAcrossModules(unittest.TestCase):
    """Verify that imported symbols from both modules are equivalent."""

    def test_review_enrichment_status_view_same_type(self) -> None:
        """ReviewEnrichmentStatusView from both modules should be same type."""
        assert ReviewEnrichmentStatusView is Model_ReviewEnrichmentStatusView

    def test_review_enrichment_view_same_type(self) -> None:
        """ReviewEnrichmentView from both modules should be same type."""
        assert ReviewEnrichmentView is Model_ReviewEnrichmentView

    def test_build_review_enrichment_view_same_function(self) -> None:
        """_build_review_enrichment_view from both modules should be same function."""
        assert _build_review_enrichment_view is Model__build_review_enrichment_view

    def test_build_review_enrichment_status_view_same_function(self) -> None:
        """_build_review_enrichment_status_view from both modules should be same function."""
        assert _build_review_enrichment_status_view is Model__build_review_enrichment_status_view


if __name__ == "__main__":
    unittest.main()

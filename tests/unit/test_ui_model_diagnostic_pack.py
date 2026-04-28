"""Tests for model_diagnostic_pack module import compatibility and behavior.

Verifies that diagnostic-pack-related symbols remain importable from both:
- k8s_diag_agent.ui.model (backward compatibility)
- k8s_diag_agent.ui.model_diagnostic_pack (new modular location)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.model import (
    DiagnosticPackReviewView as Model_DiagnosticPackReviewView,
)
from k8s_diag_agent.ui.model import (
    DiagnosticPackView as Model_DiagnosticPackView,
)
from k8s_diag_agent.ui.model import (
    _build_diagnostic_pack_review_view as Model__build_diagnostic_pack_review_view,
)
from k8s_diag_agent.ui.model import (
    _build_diagnostic_pack_view as Model__build_diagnostic_pack_view,
)
from k8s_diag_agent.ui.model_diagnostic_pack import (
    DiagnosticPackReviewView,
    DiagnosticPackView,
    _build_diagnostic_pack_review_view,
    _build_diagnostic_pack_view,
)


class TestImportCompatibility(unittest.TestCase):
    """Verify symbols are importable from both locations."""

    def test_diagnostic_pack_review_view_importable_from_model_diagnostic_pack(self) -> None:
        """DiagnosticPackReviewView should be importable from model_diagnostic_pack."""
        assert DiagnosticPackReviewView is not None

    def test_diagnostic_pack_review_view_importable_from_model(self) -> None:
        """DiagnosticPackReviewView should be re-exported from model for backward compatibility."""
        assert Model_DiagnosticPackReviewView is not None

    def test_diagnostic_pack_view_importable_from_model_diagnostic_pack(self) -> None:
        """DiagnosticPackView should be importable from model_diagnostic_pack."""
        assert DiagnosticPackView is not None

    def test_diagnostic_pack_view_importable_from_model(self) -> None:
        """DiagnosticPackView should be re-exported from model for backward compatibility."""
        assert Model_DiagnosticPackView is not None

    def test_build_diagnostic_pack_review_view_importable_from_model_diagnostic_pack(self) -> None:
        """_build_diagnostic_pack_review_view should be importable from model_diagnostic_pack."""
        assert callable(_build_diagnostic_pack_review_view)

    def test_build_diagnostic_pack_review_view_importable_from_model(self) -> None:
        """_build_diagnostic_pack_review_view should be re-exported from model for backward compatibility."""
        assert callable(Model__build_diagnostic_pack_review_view)

    def test_build_diagnostic_pack_view_importable_from_model_diagnostic_pack(self) -> None:
        """_build_diagnostic_pack_view should be importable from model_diagnostic_pack."""
        assert callable(_build_diagnostic_pack_view)

    def test_build_diagnostic_pack_view_importable_from_model(self) -> None:
        """_build_diagnostic_pack_view should be re-exported from model for backward compatibility."""
        assert callable(Model__build_diagnostic_pack_view)


class TestDiagnosticPackReviewViewDataclassBehavior(unittest.TestCase):
    """Verify DiagnosticPackReviewView dataclass behavior is preserved."""

    def test_diagnostic_pack_review_view_creation(self) -> None:
        """DiagnosticPackReviewView should be created with all required fields."""
        view = DiagnosticPackReviewView(
            timestamp="2024-01-01T00:00:00Z",
            summary="Review summary",
            major_disagreements=("disagreement1",),
            missing_checks=("check1",),
            ranking_issues=("issue1",),
            generic_checks=("generic1",),
            recommended_next_actions=("action1",),
            drift_misprioritized=False,
            confidence="high",
            provider_status="completed",
            provider_summary="Provider summary",
            provider_error_summary=None,
            provider_skip_reason=None,
            provider_review=None,
            artifact_path="/path/to/review",
        )
        assert view.timestamp == "2024-01-01T00:00:00Z"
        assert view.summary == "Review summary"
        assert view.drift_misprioritized is False
        assert view.artifact_path == "/path/to/review"

    def test_diagnostic_pack_review_view_frozen(self) -> None:
        """DiagnosticPackReviewView should be frozen."""
        view = DiagnosticPackReviewView(
            timestamp=None,
            summary=None,
            major_disagreements=(),
            missing_checks=(),
            ranking_issues=(),
            generic_checks=(),
            recommended_next_actions=(),
            drift_misprioritized=False,
            confidence=None,
            provider_status=None,
            provider_summary=None,
            provider_error_summary=None,
            provider_skip_reason=None,
            provider_review=None,
            artifact_path=None,
        )
        with self.assertRaises(Exception):  # dataclasses.FrozenInstanceError
            view.timestamp = "modified"  # type: ignore[misc]

    def test_diagnostic_pack_review_view_with_provider_review(self) -> None:
        """DiagnosticPackReviewView should accept provider_review mapping."""
        provider_review = {"key": "value", "nested": {"inner": 42}}
        view = DiagnosticPackReviewView(
            timestamp=None,
            summary=None,
            major_disagreements=(),
            missing_checks=(),
            ranking_issues=(),
            generic_checks=(),
            recommended_next_actions=(),
            drift_misprioritized=False,
            confidence=None,
            provider_status=None,
            provider_summary=None,
            provider_error_summary=None,
            provider_skip_reason=None,
            provider_review=provider_review,
            artifact_path=None,
        )
        assert view.provider_review == provider_review


class TestDiagnosticPackViewDataclassBehavior(unittest.TestCase):
    """Verify DiagnosticPackView dataclass behavior is preserved."""

    def test_diagnostic_pack_view_creation(self) -> None:
        """DiagnosticPackView should be created with all required fields."""
        view = DiagnosticPackView(
            path="/path/to/pack",
            timestamp="2024-01-01T00:00:00Z",
            label="My Pack",
            review_bundle_path="/path/to/bundle",
            review_input_14b_path="/path/to/input",
        )
        assert view.path == "/path/to/pack"
        assert view.label == "My Pack"
        assert view.review_bundle_path == "/path/to/bundle"

    def test_diagnostic_pack_view_with_optional_fields(self) -> None:
        """DiagnosticPackView should accept optional fields."""
        view = DiagnosticPackView(
            path="/path/to/pack",
            timestamp="2024-01-01T00:00:00Z",
            label="My Pack",
            review_bundle_path="/path/to/bundle",
            review_input_14b_path="/path/to/input",
            is_mirror=True,
            source_pack_path="/path/to/source/pack.zip",
        )
        assert view.is_mirror is True
        assert view.source_pack_path == "/path/to/source/pack.zip"

    def test_diagnostic_pack_view_frozen(self) -> None:
        """DiagnosticPackView should be frozen."""
        view = DiagnosticPackView(
            path=None,
            timestamp=None,
            label=None,
            review_bundle_path=None,
            review_input_14b_path=None,
        )
        with self.assertRaises(Exception):  # dataclasses.FrozenInstanceError
            view.path = "/modified"  # type: ignore[misc]


class TestBuildDiagnosticPackReviewViewBehavior(unittest.TestCase):
    """Verify _build_diagnostic_pack_review_view behavior is preserved."""

    def test_build_diagnostic_pack_review_view_from_valid_mapping(self) -> None:
        """_build_diagnostic_pack_review_view should build DiagnosticPackReviewView from raw mapping."""
        raw = {
            "timestamp": "2024-01-01T00:00:00Z",
            "summary": "Review summary",
            "majorDisagreements": ["disagreement1", "disagreement2"],
            "missingChecks": ["check1"],
            "rankingIssues": ["issue1"],
            "genericChecks": ["generic1"],
            "recommendedNextActions": ["action1"],
            "driftMisprioritized": True,
            "confidence": "high",
            "providerStatus": "completed",
            "providerSummary": "Provider summary",
            "artifactPath": "/path/to/review",
        }
        result = _build_diagnostic_pack_review_view(raw)
        assert isinstance(result, DiagnosticPackReviewView)
        assert result.timestamp == "2024-01-01T00:00:00Z"
        assert result.summary == "Review summary"
        assert result.major_disagreements == ("disagreement1", "disagreement2")
        assert result.drift_misprioritized is True

    def test_build_diagnostic_pack_review_view_with_snake_case_keys(self) -> None:
        """_build_diagnostic_pack_review_view should handle snake_case keys."""
        raw = {
            "timestamp": "2024-01-01T00:00:00Z",
            "major_disagreements": ["d1"],
            "missing_checks": ["c1"],
            "ranking_issues": ["i1"],
            "generic_checks": ["g1"],
            "recommended_next_actions": ["a1"],
            "drift_misprioritized": False,
        }
        result = _build_diagnostic_pack_review_view(raw)
        assert isinstance(result, DiagnosticPackReviewView)
        assert result.major_disagreements == ("d1",)
        assert result.drift_misprioritized is False

    def test_build_diagnostic_pack_review_view_with_none_input(self) -> None:
        """_build_diagnostic_pack_review_view should return None for None input."""
        result = _build_diagnostic_pack_review_view(None)
        assert result is None

    def test_build_diagnostic_pack_review_view_with_non_mapping_input(self) -> None:
        """_build_diagnostic_pack_review_view should return None for non-Mapping input."""
        result = _build_diagnostic_pack_review_view("not a mapping")
        assert result is None

    def test_build_diagnostic_pack_review_view_with_non_mapping_input_list(self) -> None:
        """_build_diagnostic_pack_review_view should return None for list input."""
        result = _build_diagnostic_pack_review_view(["item1", "item2"])
        assert result is None

    def test_build_diagnostic_pack_review_view_with_missing_fields(self) -> None:
        """_build_diagnostic_pack_review_view should handle missing fields with defaults."""
        raw: dict = {}
        result = _build_diagnostic_pack_review_view(raw)
        assert isinstance(result, DiagnosticPackReviewView)
        assert result.timestamp is None
        assert result.summary is None
        assert result.major_disagreements == ()
        assert result.drift_misprioritized is False

    def test_build_diagnostic_pack_review_view_with_provider_review_mapping(self) -> None:
        """_build_diagnostic_pack_review_view should accept provider_review as Mapping."""
        raw = {
            "timestamp": "2024-01-01T00:00:00Z",
            "providerReview": {"key": "value"},
        }
        result = _build_diagnostic_pack_review_view(raw)
        assert isinstance(result, DiagnosticPackReviewView)
        assert result.provider_review == {"key": "value"}

    def test_build_diagnostic_pack_review_view_with_provider_review_non_mapping(self) -> None:
        """_build_diagnostic_pack_review_view should coerce provider_review to None if not Mapping."""
        raw = {
            "timestamp": "2024-01-01T00:00:00Z",
            "providerReview": "not a mapping",
        }
        result = _build_diagnostic_pack_review_view(raw)
        assert isinstance(result, DiagnosticPackReviewView)
        assert result.provider_review is None


class TestBuildDiagnosticPackViewBehavior(unittest.TestCase):
    """Verify _build_diagnostic_pack_view behavior is preserved."""

    def test_build_diagnostic_pack_view_from_valid_mapping(self) -> None:
        """_build_diagnostic_pack_view should build DiagnosticPackView from raw mapping."""
        raw = {
            "path": "/path/to/pack",
            "timestamp": "2024-01-01T00:00:00Z",
            "label": "My Pack",
            "review_bundle_path": "/path/to/bundle",
            "review_input_14b_path": "/path/to/input",
        }
        result = _build_diagnostic_pack_view(raw)
        assert isinstance(result, DiagnosticPackView)
        assert result.path == "/path/to/pack"
        assert result.label == "My Pack"
        assert result.review_bundle_path == "/path/to/bundle"

    def test_build_diagnostic_pack_view_with_is_mirror_true(self) -> None:
        """_build_diagnostic_pack_view should handle isMirror=True."""
        raw = {
            "path": "/path/to/pack",
            "isMirror": True,
            "sourcePackPath": "/path/to/source/pack.zip",
        }
        result = _build_diagnostic_pack_view(raw)
        assert isinstance(result, DiagnosticPackView)
        assert result.is_mirror is True
        assert result.source_pack_path == "/path/to/source/pack.zip"

    def test_build_diagnostic_pack_view_with_is_mirror_false(self) -> None:
        """_build_diagnostic_pack_view should handle isMirror=False."""
        raw = {
            "path": "/path/to/pack",
            "isMirror": False,
        }
        result = _build_diagnostic_pack_view(raw)
        assert isinstance(result, DiagnosticPackView)
        assert result.is_mirror is False

    def test_build_diagnostic_pack_view_with_snake_case_keys(self) -> None:
        """_build_diagnostic_pack_view should handle snake_case keys."""
        raw = {
            "path": "/path/to/pack",
            "is_mirror": True,
            "source_pack_path": "/path/to/source/pack.zip",
        }
        result = _build_diagnostic_pack_view(raw)
        assert isinstance(result, DiagnosticPackView)
        assert result.is_mirror is True
        assert result.source_pack_path == "/path/to/source/pack.zip"

    def test_build_diagnostic_pack_view_with_none_input(self) -> None:
        """_build_diagnostic_pack_view should return None for None input."""
        result = _build_diagnostic_pack_view(None)
        assert result is None

    def test_build_diagnostic_pack_view_with_non_mapping_input(self) -> None:
        """_build_diagnostic_pack_view should return None for non-Mapping input."""
        result = _build_diagnostic_pack_view("not a mapping")
        assert result is None

    def test_build_diagnostic_pack_view_with_non_mapping_input_list(self) -> None:
        """_build_diagnostic_pack_view should return None for list input."""
        result = _build_diagnostic_pack_view(["item1", "item2"])
        assert result is None

    def test_build_diagnostic_pack_view_with_missing_fields(self) -> None:
        """_build_diagnostic_pack_view should handle missing fields with defaults."""
        raw: dict = {}
        result = _build_diagnostic_pack_view(raw)
        assert isinstance(result, DiagnosticPackView)
        assert result.path is None
        assert result.timestamp is None
        assert result.label is None
        assert result.is_mirror is None
        assert result.source_pack_path is None

    def test_build_diagnostic_pack_view_with_is_mirror_string_coercion(self) -> None:
        """_build_diagnostic_pack_view should coerce string isMirror values to bool."""
        raw = {
            "path": "/path/to/pack",
            "isMirror": "true",
        }
        result = _build_diagnostic_pack_view(raw)
        assert isinstance(result, DiagnosticPackView)
        assert result.is_mirror is True


class TestEquivalenceAcrossModules(unittest.TestCase):
    """Verify that imported symbols from both modules are equivalent."""

    def test_diagnostic_pack_review_view_same_type(self) -> None:
        """DiagnosticPackReviewView from both modules should be same type."""
        assert DiagnosticPackReviewView is Model_DiagnosticPackReviewView

    def test_diagnostic_pack_view_same_type(self) -> None:
        """DiagnosticPackView from both modules should be same type."""
        assert DiagnosticPackView is Model_DiagnosticPackView

    def test_build_diagnostic_pack_review_view_same_function(self) -> None:
        """_build_diagnostic_pack_review_view from both modules should be same function."""
        assert _build_diagnostic_pack_review_view is Model__build_diagnostic_pack_review_view

    def test_build_diagnostic_pack_view_same_function(self) -> None:
        """_build_diagnostic_pack_view from both modules should be same function."""
        assert _build_diagnostic_pack_view is Model__build_diagnostic_pack_view


if __name__ == "__main__":
    unittest.main()

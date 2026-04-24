"""Tests for model_proposals module import compatibility and behavior.

Verifies that proposal-related symbols remain importable from both:
- k8s_diag_agent.ui.model (backward compatibility)
- k8s_diag_agent.ui.model_proposals (new modular location)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.model import (
    ProposalStatusSummary as Model_ProposalStatusSummary,
)

# Import from model.py (backward compatibility - should re-export)
from k8s_diag_agent.ui.model import (
    ProposalView as Model_ProposalView,
)
from k8s_diag_agent.ui.model import (
    _build_lifecycle_history as Model_build_lifecycle_history,
)
from k8s_diag_agent.ui.model import (
    _build_proposal_status_summary as Model_build_proposal_status_summary,
)
from k8s_diag_agent.ui.model import (
    _build_proposal_view as Model_build_proposal_view,
)

# Import from the new module (canonical location)
from k8s_diag_agent.ui.model_proposals import (
    ProposalStatusSummary,
    ProposalView,
    _build_lifecycle_history,
    _build_proposal_status_summary,
    _build_proposal_view,
)


class TestImportCompatibility(unittest.TestCase):
    """Verify symbols are importable from both locations."""

    def test_proposal_view_importable_from_model_proposals(self) -> None:
        """ProposalView should be importable from model_proposals."""
        assert ProposalView is not None

    def test_proposal_view_importable_from_model(self) -> None:
        """ProposalView should be re-exported from model for backward compatibility."""
        assert Model_ProposalView is not None

    def test_proposal_status_summary_importable_from_model_proposals(self) -> None:
        """ProposalStatusSummary should be importable from model_proposals."""
        assert ProposalStatusSummary is not None

    def test_proposal_status_summary_importable_from_model(self) -> None:
        """ProposalStatusSummary should be re-exported from model for backward compatibility."""
        assert Model_ProposalStatusSummary is not None

    def test_build_proposal_view_importable_from_model_proposals(self) -> None:
        """_build_proposal_view should be importable from model_proposals."""
        assert callable(_build_proposal_view)

    def test_build_proposal_view_importable_from_model(self) -> None:
        """_build_proposal_view should be re-exported from model for backward compatibility."""
        assert callable(Model_build_proposal_view)

    def test_build_proposal_status_summary_importable_from_model_proposals(self) -> None:
        """_build_proposal_status_summary should be importable from model_proposals."""
        assert callable(_build_proposal_status_summary)

    def test_build_proposal_status_summary_importable_from_model(self) -> None:
        """_build_proposal_status_summary should be re-exported from model."""
        assert callable(Model_build_proposal_status_summary)

    def test_build_lifecycle_history_importable_from_model_proposals(self) -> None:
        """_build_lifecycle_history should be importable from model_proposals."""
        assert callable(_build_lifecycle_history)

    def test_build_lifecycle_history_importable_from_model(self) -> None:
        """_build_lifecycle_history should be re-exported from model."""
        assert callable(Model_build_lifecycle_history)


class TestProposalViewBehavior(unittest.TestCase):
    """Verify ProposalView dataclass behavior is preserved."""

    def test_proposal_view_creation(self) -> None:
        """ProposalView should be created with all required fields."""
        view = ProposalView(
            proposal_id="test-proposal-1",
            target="test-target",
            status="pending",
            confidence="medium",
            rationale="Test rationale",
            expected_benefit="Test benefit",
            source_run_id="test-run-1",
            latest_note=None,
            artifact_path="/path/to/proposal.json",
            review_path="/path/to/review.json",
            lifecycle_history=(),
            artifact_id=None,
        )
        assert view.proposal_id == "test-proposal-1"
        assert view.target == "test-target"
        assert view.status == "pending"
        assert view.artifact_id is None

    def test_proposal_view_with_artifact_id(self) -> None:
        """ProposalView should accept artifact_id field."""
        view = ProposalView(
            proposal_id="test-proposal-2",
            target="test-target",
            status="checked",
            confidence="high",
            rationale="Test rationale",
            expected_benefit="Test benefit",
            source_run_id="test-run-1",
            latest_note="Note text",
            artifact_path="/path/to/proposal.json",
            review_path="/path/to/review.json",
            lifecycle_history=(("proposed", "2026-04-24T00:00:00Z", None),),
            artifact_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        )
        assert view.artifact_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class TestBuildProposalViewBehavior(unittest.TestCase):
    """Verify _build_proposal_view behavior is preserved."""

    def test_build_proposal_view_from_mapping(self) -> None:
        """_build_proposal_view should build ProposalView from raw mapping."""
        raw = {
            "proposal_id": "test-proposal-1",
            "target": "test-target",
            "status": "pending",
            "confidence": "medium",
            "rationale": "Test rationale",
            "expected_benefit": "Test benefit",
            "source_run_id": "test-run-1",
            "lifecycle_history": [],
            "artifact_path": "/path/to/proposal.json",
            "review_artifact": "/path/to/review.json",
        }
        result = _build_proposal_view(raw)
        assert isinstance(result, ProposalView)
        assert result.proposal_id == "test-proposal-1"
        assert result.target == "test-target"
        assert result.status == "pending"

    def test_build_proposal_view_with_lifecycle_history(self) -> None:
        """_build_proposal_view should extract latest_note from lifecycle_history."""
        raw = {
            "proposal_id": "test-proposal-2",
            "target": "test-target",
            "status": "checked",
            "confidence": "high",
            "rationale": "Test rationale",
            "expected_benefit": "Test benefit",
            "source_run_id": "test-run-1",
            "lifecycle_history": [
                {"status": "proposed", "timestamp": "2026-04-24T00:00:00Z", "note": "Initial note"},
                {"status": "checked", "timestamp": "2026-04-24T01:00:00Z", "note": "Final note"},
            ],
            "artifact_path": "/path/to/proposal.json",
            "review_artifact": "/path/to/review.json",
        }
        result = _build_proposal_view(raw)
        assert isinstance(result, ProposalView)
        assert result.latest_note == "Final note"
        assert len(result.lifecycle_history) == 2

    def test_build_proposal_view_with_dash_note(self) -> None:
        """_build_proposal_view should treat '-' note as None."""
        raw = {
            "proposal_id": "test-proposal-3",
            "target": "test-target",
            "status": "pending",
            "confidence": "low",
            "rationale": "Test rationale",
            "expected_benefit": "Test benefit",
            "source_run_id": "test-run-1",
            "lifecycle_history": [
                {"status": "proposed", "timestamp": "2026-04-24T00:00:00Z", "note": "-"},
            ],
            "artifact_path": "/path/to/proposal.json",
            "review_artifact": "/path/to/review.json",
        }
        result = _build_proposal_view(raw)
        assert result.latest_note is None

    def test_build_proposal_view_with_artifact_id(self) -> None:
        """_build_proposal_view should extract artifact_id from raw data."""
        raw = {
            "proposal_id": "test-proposal-4",
            "target": "test-target",
            "status": "checked",
            "confidence": "high",
            "rationale": "Test rationale",
            "expected_benefit": "Test benefit",
            "source_run_id": "test-run-1",
            "lifecycle_history": [],
            "artifact_path": "/path/to/proposal.json",
            "review_artifact": "/path/to/review.json",
            "artifact_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        }
        result = _build_proposal_view(raw)
        assert result.artifact_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class TestBuildProposalStatusSummaryBehavior(unittest.TestCase):
    """Verify _build_proposal_status_summary behavior is preserved."""

    def test_build_from_empty_mapping(self) -> None:
        """_build_proposal_status_summary should handle empty input."""
        result = _build_proposal_status_summary(None)
        assert isinstance(result, ProposalStatusSummary)
        assert result.status_counts == ()

    def test_build_from_non_mapping(self) -> None:
        """_build_proposal_status_summary should handle non-Mapping input."""
        result = _build_proposal_status_summary("not a mapping")
        assert isinstance(result, ProposalStatusSummary)
        assert result.status_counts == ()

    def test_build_from_valid_mapping(self) -> None:
        """_build_proposal_status_summary should build from valid mapping."""
        raw = {
            "status_counts": [
                {"status": "pending", "count": 5},
                {"status": "checked", "count": 3},
            ]
        }
        result = _build_proposal_status_summary(raw)
        assert isinstance(result, ProposalStatusSummary)
        assert len(result.status_counts) == 2


class TestBuildLifecycleHistoryBehavior(unittest.TestCase):
    """Verify _build_lifecycle_history behavior is preserved."""

    def test_build_from_empty_input(self) -> None:
        """_build_lifecycle_history should handle empty input."""
        result = _build_lifecycle_history(None)
        assert result == ()

    def test_build_from_non_sequence(self) -> None:
        """_build_lifecycle_history should handle non-Sequence input."""
        result = _build_lifecycle_history("not a sequence")
        assert result == ()

    def test_build_from_valid_sequence(self) -> None:
        """_build_lifecycle_history should build from valid sequence."""
        raw = [
            {"status": "proposed", "timestamp": "2026-04-24T00:00:00Z", "note": "Initial"},
            {"status": "checked", "timestamp": "2026-04-24T01:00:00Z", "note": "Final"},
        ]
        result = _build_lifecycle_history(raw)
        assert len(result) == 2
        assert result[0] == ("proposed", "2026-04-24T00:00:00Z", "Initial")
        assert result[1] == ("checked", "2026-04-24T01:00:00Z", "Final")

    def test_build_with_dash_note(self) -> None:
        """_build_lifecycle_history should treat '-' note as None."""
        raw = [
            {"status": "proposed", "timestamp": "2026-04-24T00:00:00Z", "note": "-"},
        ]
        result = _build_lifecycle_history(raw)
        assert len(result) == 1
        assert result[0][2] is None

    def test_build_skips_non_mapping_entries(self) -> None:
        """_build_lifecycle_history should skip non-Mapping entries."""
        raw = [
            "not a mapping",
            {"status": "proposed", "timestamp": "2026-04-24T00:00:00Z", "note": "Valid"},
        ]
        result = _build_lifecycle_history(raw)
        assert len(result) == 1
        assert result[0][0] == "proposed"


class TestEquivalenceAcrossModules(unittest.TestCase):
    """Verify that imported symbols from both modules are equivalent."""

    def test_proposal_view_same_type(self) -> None:
        """ProposalView from model_proposals and model should be same type."""
        assert ProposalView is Model_ProposalView

    def test_proposal_status_summary_same_type(self) -> None:
        """ProposalStatusSummary from both modules should be same type."""
        assert ProposalStatusSummary is Model_ProposalStatusSummary

    def test_build_proposal_view_same_function(self) -> None:
        """_build_proposal_view from both modules should be same function."""
        assert _build_proposal_view is Model_build_proposal_view

    def test_build_proposal_status_summary_same_function(self) -> None:
        """_build_proposal_status_summary from both modules should be same function."""
        assert _build_proposal_status_summary is Model_build_proposal_status_summary

    def test_build_lifecycle_history_same_function(self) -> None:
        """_build_lifecycle_history from both modules should be same function."""
        assert _build_lifecycle_history is Model_build_lifecycle_history


if __name__ == "__main__":
    unittest.main()

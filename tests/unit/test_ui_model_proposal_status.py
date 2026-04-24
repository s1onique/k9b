"""Tests for model_proposal_status module import compatibility and behavior.

Verifies that proposal-status-summary symbols remain importable from both:
- k8s_diag_agent.ui.model (backward compatibility)
- k8s_diag_agent.ui.model_proposal_status (new modular location)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.model import (
    ProposalStatusSummary as Model_ProposalStatusSummary,
)
from k8s_diag_agent.ui.model import (
    _build_proposal_status_summary as Model__build_proposal_status_summary,
)
from k8s_diag_agent.ui.model_proposal_status import (
    ProposalStatusSummary,
    _build_proposal_status_summary,
)


class TestImportCompatibility(unittest.TestCase):
    """Verify symbols are importable from both locations."""

    def test_proposal_status_summary_importable_from_model_proposal_status(self) -> None:
        """ProposalStatusSummary should be importable from model_proposal_status."""
        assert ProposalStatusSummary is not None

    def test_proposal_status_summary_importable_from_model(self) -> None:
        """ProposalStatusSummary should be re-exported from model for backward compatibility."""
        assert Model_ProposalStatusSummary is not None

    def test_build_proposal_status_summary_importable_from_model_proposal_status(self) -> None:
        """_build_proposal_status_summary should be importable from model_proposal_status."""
        assert callable(_build_proposal_status_summary)

    def test_build_proposal_status_summary_importable_from_model(self) -> None:
        """_build_proposal_status_summary should be re-exported from model for backward compatibility."""
        assert callable(Model__build_proposal_status_summary)


class TestProposalStatusSummaryBehavior(unittest.TestCase):
    """Verify ProposalStatusSummary dataclass behavior is preserved."""

    def test_proposal_status_summary_creation(self) -> None:
        """ProposalStatusSummary should be created with status counts."""
        view = ProposalStatusSummary(
            status_counts=(("pending", 5), ("checked", 3)),
        )
        assert len(view.status_counts) == 2
        assert view.status_counts[0] == ("pending", 5)
        assert view.status_counts[1] == ("checked", 3)

    def test_proposal_status_summary_with_empty_values(self) -> None:
        """ProposalStatusSummary should accept empty tuples."""
        view = ProposalStatusSummary(
            status_counts=(),
        )
        assert view.status_counts == ()


class TestBuildProposalStatusSummaryBehavior(unittest.TestCase):
    """Verify _build_proposal_status_summary behavior is preserved."""

    def test_build_proposal_status_summary_from_valid_mapping(self) -> None:
        """_build_proposal_status_summary should build ProposalStatusSummary from raw mapping."""
        raw = {
            "status_counts": [
                {"status": "pending", "count": 5},
                {"status": "checked", "count": 3},
            ],
        }
        result = _build_proposal_status_summary(raw)
        assert isinstance(result, ProposalStatusSummary)
        assert len(result.status_counts) == 2
        assert result.status_counts[0] == ("pending", 5)
        assert result.status_counts[1] == ("checked", 3)

    def test_build_proposal_status_summary_with_none_input(self) -> None:
        """_build_proposal_status_summary should return empty summary for None input."""
        result = _build_proposal_status_summary(None)
        assert isinstance(result, ProposalStatusSummary)
        assert result.status_counts == ()

    def test_build_proposal_status_summary_with_non_mapping_input(self) -> None:
        """_build_proposal_status_summary should return empty summary for non-Mapping input (list)."""
        result = _build_proposal_status_summary(["not", "a", "mapping"])
        assert isinstance(result, ProposalStatusSummary)
        assert result.status_counts == ()

    def test_build_proposal_status_summary_with_non_mapping_input_string(self) -> None:
        """_build_proposal_status_summary should return empty summary for non-Mapping input (string)."""
        result = _build_proposal_status_summary("not a mapping")
        assert isinstance(result, ProposalStatusSummary)
        assert result.status_counts == ()

    def test_build_proposal_status_summary_with_missing_fields(self) -> None:
        """_build_proposal_status_summary should handle missing fields gracefully."""
        raw = {}
        result = _build_proposal_status_summary(raw)
        assert isinstance(result, ProposalStatusSummary)
        assert result.status_counts == ()

    def test_build_proposal_status_summary_with_empty_status_counts(self) -> None:
        """_build_proposal_status_summary should handle empty status_counts list."""
        raw = {
            "status_counts": [],
        }
        result = _build_proposal_status_summary(raw)
        assert isinstance(result, ProposalStatusSummary)
        assert result.status_counts == ()

    def test_build_proposal_status_summary_skips_non_mapping_entries(self) -> None:
        """_build_proposal_status_summary should skip non-Mapping status count entries."""
        raw = {
            "status_counts": [
                "not a mapping",
                {"status": "pending", "count": 5},
                42,
            ],
        }
        result = _build_proposal_status_summary(raw)
        assert isinstance(result, ProposalStatusSummary)
        assert len(result.status_counts) == 1
        assert result.status_counts[0] == ("pending", 5)

    def test_build_proposal_status_summary_coerces_values(self) -> None:
        """_build_proposal_status_summary should coerce status to str and count to int."""
        raw = {
            "status_counts": [
                {"status": 123, "count": "5"},
            ],
        }
        result = _build_proposal_status_summary(raw)
        assert isinstance(result, ProposalStatusSummary)
        assert result.status_counts[0] == ("123", 5)


class TestEquivalenceAcrossModules(unittest.TestCase):
    """Verify that imported symbols from both modules are equivalent."""

    def test_proposal_status_summary_same_type(self) -> None:
        """ProposalStatusSummary from model_proposal_status and model should be same type."""
        assert ProposalStatusSummary is Model_ProposalStatusSummary

    def test_build_proposal_status_summary_same_function(self) -> None:
        """_build_proposal_status_summary from both modules should be same function."""
        assert _build_proposal_status_summary is Model__build_proposal_status_summary


if __name__ == "__main__":
    unittest.main()

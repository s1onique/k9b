"""Tests for drilldown prompt boundary markers (REM-P4).

These tests verify that build_drilldown_prompt uses explicit boundary markers
to separate trusted instructions from untrusted cluster/artifact data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from k8s_diag_agent.llm.prompt_boundaries import (
    BEGIN_OUTPUT_SCHEMA,
    BEGIN_UNTRUSTED_CLUSTER_DATA,
    END_OUTPUT_SCHEMA,
    END_UNTRUSTED_CLUSTER_DATA,
)
from tests.helpers.prompt_boundary_helpers import (
    extract_boundary_sections,
    verify_boundary_structure,
)


class TestDrilldownPromptBoundaries:
    """Tests for build_drilldown_prompt boundary markers."""

    @staticmethod
    def _make_prompt() -> str:
        """Helper to create a test drilldown prompt."""
        from k8s_diag_agent.health.drilldown import DrilldownArtifact
        from k8s_diag_agent.llm.drilldown_prompts import build_drilldown_prompt

        artifact = MagicMock(spec=DrilldownArtifact)
        artifact.cluster_id = "test-cluster-001"
        artifact.run_id = "run-123"
        artifact.context = "test-context"
        artifact.label = "test-label"
        artifact.run_label = "test-run-label"
        artifact.affected_namespaces = []
        artifact.evidence_summary = None
        artifact.warning_events = []
        artifact.non_running_pods = []
        artifact.rollout_status = []
        artifact.pod_descriptions = {}
        artifact.snapshot_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        artifact.timestamp = datetime(2024, 1, 1, 12, 5, 0, tzinfo=UTC)
        artifact.trigger_reasons = []
        artifact.missing_evidence = []
        artifact.collection_timestamps = {}

        return build_drilldown_prompt(artifact)

    def test_drilldown_prompt_boundary_structure(self) -> None:
        """Verify drilldown prompt follows boundary convention exactly."""
        prompt = self._make_prompt()
        errors = verify_boundary_structure(prompt)
        assert not errors, f"Boundary structure errors: {errors}"

    def test_drilldown_prompt_contains_both_boundary_pairs(self) -> None:
        """Verify drilldown prompt contains all four boundary markers."""
        prompt = self._make_prompt()
        assert BEGIN_UNTRUSTED_CLUSTER_DATA in prompt
        assert END_UNTRUSTED_CLUSTER_DATA in prompt
        assert BEGIN_OUTPUT_SCHEMA in prompt
        assert END_OUTPUT_SCHEMA in prompt

    def test_drilldown_prompt_no_data_before_untrusted_boundary(self) -> None:
        """Verify no untrusted data appears before BEGIN_UNTRUSTED_CLUSTER_DATA."""
        prompt = self._make_prompt()
        sections = extract_boundary_sections(prompt)
        before = sections["before_untrusted"]

        # Only the instruction header should be before untrusted markers
        assert "Artifact summary:" not in before, (
            "Untrusted data 'Artifact summary:' should not appear before BEGIN_UNTRUSTED_CLUSTER_DATA"
        )
        assert "run_id:" not in before, (
            "Untrusted data 'run_id:' should not appear before BEGIN_UNTRUSTED_CLUSTER_DATA"
        )

    def test_drilldown_prompt_schema_inside_schema_markers(self) -> None:
        """Verify output schema content appears inside schema markers."""
        prompt = self._make_prompt()
        sections = extract_boundary_sections(prompt)
        inside_schema = sections["inside_schema"]

        # Schema content should be inside schema markers
        assert "observed_signals" in inside_schema or "Schema reminder" in prompt, (
            "Schema content should be inside OUTPUT_SCHEMA markers"
        )

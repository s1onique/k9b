"""Tests for OpenAICompatibleAdapter prompt boundary markers (REM-P4).

These tests verify that OpenAICompatibleAdapter._build_prompt uses explicit boundary
markers to separate trusted instructions from untrusted cluster/artifact data.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from k8s_diag_agent.external_analysis.adapter import ExternalAnalysisRequest
from k8s_diag_agent.external_analysis.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
)
from k8s_diag_agent.external_analysis.review_input import (
    AlertmanagerContext,
    ReviewEnrichmentInput,
    ReviewSelectionContext,
)
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


def _make_adapter_request() -> tuple[str, ExternalAnalysisRequest]:
    """Create a test review enrichment prompt using OpenAICompatibleAdapter.

    Returns:
        Tuple of (prompt, request) for testing.
    """
    # Build a minimal context with required run_id and review_path
    context = ReviewEnrichmentInput(
        run_id="test-run-001",
        review_path=Path("/tmp/test.json"),
        review={
            "run_id": "review-run-001",
            "review_version": "1.0",
            "metadata": {
                "name": "test-review",
                "namespace": "default",
            },
        },
        alertmanager_context=AlertmanagerContext(
            available=False,
            source="test",
            status="active",
            compact=None,
        ),
        selections=(
            ReviewSelectionContext(
                label="test-selection",
                context="test-context",
                entry={"item": "value"},
                drilldown=None,
                drilldown_path=None,
                assessment=None,
                assessment_path=None,
                snapshot=None,
                snapshot_path=None,
            ),
        ),
        missing_drilldowns=(),
        missing_assessments=(),
        missing_snapshots=(),
    )

    request = MagicMock(spec=ExternalAnalysisRequest)
    request.run_id = "adapter-run-001"
    request.cluster_label = "test-cluster"
    request.source_artifact = "/tmp/test.json"

    # Create adapter instance and call _build_prompt directly
    adapter = OpenAICompatibleAdapter.__new__(OpenAICompatibleAdapter)
    adapter._use_http = False
    adapter._command = None
    adapter._http_provider = None
    adapter._http_config_error = None
    adapter._http_only = False

    # Use _ for unused alias_mapping (returned for caller use).
    prompt, _ = adapter._build_prompt(request, context)
    return prompt, request


class TestOpenAICompatibleAdapterPromptBoundaries:
    """Tests for OpenAICompatibleAdapter._build_prompt boundary markers."""

    def test_openai_compatible_adapter_prompt_boundary_structure(self) -> None:
        """Verify OpenAICompatibleAdapter prompt follows boundary convention exactly."""
        prompt, _ = _make_adapter_request()
        errors = verify_boundary_structure(prompt)
        assert not errors, f"Boundary structure errors: {errors}"

    def test_openai_compatible_adapter_prompt_contains_both_boundary_pairs(self) -> None:
        """Verify OpenAICompatibleAdapter prompt contains all four boundary markers."""
        prompt, _ = _make_adapter_request()
        assert BEGIN_UNTRUSTED_CLUSTER_DATA in prompt
        assert END_UNTRUSTED_CLUSTER_DATA in prompt
        assert BEGIN_OUTPUT_SCHEMA in prompt
        assert END_OUTPUT_SCHEMA in prompt

    def test_openai_compatible_adapter_prompt_no_data_before_untrusted_boundary(
        self,
    ) -> None:
        """Verify no untrusted data appears before BEGIN_UNTRUSTED_CLUSTER_DATA."""
        prompt, _ = _make_adapter_request()
        sections = extract_boundary_sections(prompt)
        before = sections["before_untrusted"]

        # Only the header with run_id should be before untrusted markers
        # The actual review JSON with metadata should be inside untrusted
        assert '"name":' not in before, (
            "Untrusted data (review content) should not appear before BEGIN_UNTRUSTED_CLUSTER_DATA"
        )
        assert '"metadata":' not in before, (
            "Untrusted data (review content) should not appear before BEGIN_UNTRUSTED_CLUSTER_DATA"
        )

    def test_openai_compatible_adapter_cluster_label_sanitization(self) -> None:
        """OpenAICompatibleAdapter instruction header must not contain 'cluster_label=in-cluster'.

        Regression test for in-cluster marker leak into LLM prompts.
        When request.cluster_label is an internal marker, display_kube_cluster_label()
        should return None, and the prompt header should not contain 'cluster_label=in-cluster'.
        """
        # Build a minimal context
        context = ReviewEnrichmentInput(
            run_id="test-run-001",
            review_path=Path("/tmp/test.json"),
            review={"run_id": "review-run-001", "review_version": "1.0"},
            alertmanager_context=AlertmanagerContext(
                available=False,
                source="test",
                status="active",
                compact=None,
            ),
            selections=(),
            missing_drilldowns=(),
            missing_assessments=(),
            missing_snapshots=(),
        )

        # Create request with internal marker as cluster_label
        request = MagicMock(spec=ExternalAnalysisRequest)
        request.run_id = "adapter-run-001"
        request.cluster_label = "in-cluster"  # Internal marker - should be sanitized
        request.source_artifact = "/tmp/test.json"

        adapter = OpenAICompatibleAdapter.__new__(OpenAICompatibleAdapter)
        adapter._use_http = False
        adapter._command = None
        adapter._http_provider = None
        adapter._http_config_error = None
        adapter._http_only = False

        prompt, _ = adapter._build_prompt(request, context)

        # Verify the trusted instruction header does NOT contain raw "in-cluster" as cluster_label
        # Extract everything before BEGIN_UNTRUSTED_CLUSTER_DATA as the trusted header
        trusted_header = prompt.split(BEGIN_UNTRUSTED_CLUSTER_DATA, 1)[0]

        # Internal markers should NOT appear in the trusted header as cluster_label values
        assert "cluster_label=in-cluster" not in trusted_header, (
            f"Internal marker leaked into trusted instruction header: {trusted_header}"
        )
        assert "cluster_label=in_cluster" not in trusted_header, (
            f"Internal marker leaked into trusted instruction header: {trusted_header}"
        )

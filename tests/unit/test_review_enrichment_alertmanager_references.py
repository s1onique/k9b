"""Tests for alertmanagerEvidenceReferences projection path in review enrichment.

Covers the full backend projection path:
- health/ui._serialize_review_enrichment() serialization
- health/ui merge behavior for interpretation field
- ui/model._build_review_enrichment_view() parsing
- ui/api._serialize_review_enrichment() serialization
- End-to-end projection test
"""

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.health.ui import _serialize_review_enrichment
from k8s_diag_agent.ui.api import (
    AlertmanagerEvidenceReferencePayload,
    ReviewEnrichmentPayload,
    build_run_payload,
)
from k8s_diag_agent.ui.api import (
    _serialize_review_enrichment as api_serialize_review_enrichment,
)
from k8s_diag_agent.ui.model import (
    AlertmanagerEvidenceReferenceView,
    ReviewEnrichmentView,
    _build_review_enrichment_view,
    build_ui_context,
)
from tests.fixtures.ui_index_sample import sample_ui_index

# Sample alertmanager evidence reference data for testing
# NOTE: usedFor values must be valid per the bounded schema:
# top_concern, next_check, summary, triage_order, focus_note
_SAMPLE_AM_REFS: list[dict[str, object]] = [
    {
        "cluster": "cluster-alpha",
        "matchedDimensions": ["alertname", "severity"],
        "reason": "Fires during pod restart events",
        "usedFor": "top_concern",
    },
    {
        "cluster": "cluster-beta",
        "matchedDimensions": ["namespace"],
        "reason": "Indicates resource pressure",
        "usedFor": "next_check",
    },
]


def _sample_review_enrichment_artifact(
    alertmanager_refs: list[dict[str, object]] | None = None,
) -> ExternalAnalysisArtifact:
    """Create a sample review enrichment artifact with optional alertmanager refs."""
    interpretation: dict[str, object] = {}
    if alertmanager_refs is not None:
        interpretation["alertmanagerEvidenceReferences"] = alertmanager_refs

    return ExternalAnalysisArtifact(
        tool_name="llamacpp",
        run_id="test-run",
        run_label="test-run",
        cluster_label="test-run",
        summary="Review enrichment test summary",
        status=ExternalAnalysisStatus.SUCCESS,
        artifact_path="external-analysis/test-review-enrichment.json",
        provider="llamacpp",
        timestamp=datetime.now(UTC),
        duration_ms=100,
        purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
        payload={
            "triageOrder": ["cluster-b", "cluster-a"],
            "topConcerns": ["cpu pressure"],
        },
        interpretation=interpretation if interpretation else None,
    )


class HealthUISerializationTests(unittest.TestCase):
    """Tests for health/ui._serialize_review_enrichment() serialization."""

    def test_serialize_review_enrichment_includes_alertmanager_evidence_references(
        self,
    ) -> None:
        """Test that _serialize_review_enrichment() includes alertmanagerEvidenceReferences in output."""
        artifact = _sample_review_enrichment_artifact(alertmanager_refs=_SAMPLE_AM_REFS)
        root_dir = Path(tempfile.mkdtemp())

        result = _serialize_review_enrichment(
            artifacts=[artifact],
            root_dir=root_dir,
            run_id="test-run",
        )

        assert result is not None
        self.assertIn("alertmanagerEvidenceReferences", result)
        refs = cast("list[object]", result["alertmanagerEvidenceReferences"])
        self.assertIsInstance(refs, list)
        self.assertEqual(len(refs), 2)

    def test_serialize_review_enrichment_preserves_ref_fields(self) -> None:
        """Test that payload values are preserved correctly: cluster, matchedDimensions, reason, usedFor."""
        artifact = _sample_review_enrichment_artifact(alertmanager_refs=_SAMPLE_AM_REFS)
        root_dir = Path(tempfile.mkdtemp())

        result = _serialize_review_enrichment(
            artifacts=[artifact],
            root_dir=root_dir,
            run_id="test-run",
        )

        assert result is not None
        refs = result["alertmanagerEvidenceReferences"]
        assert isinstance(refs, list)
        self.assertEqual(len(refs), 2)

        # First reference
        ref1 = refs[0]
        self.assertEqual(ref1["cluster"], "cluster-alpha")
        self.assertEqual(ref1["matchedDimensions"], ["alertname", "severity"])
        self.assertEqual(ref1["reason"], "Fires during pod restart events")
        self.assertEqual(ref1["usedFor"], "top_concern")

        # Second reference
        ref2 = refs[1]
        self.assertEqual(ref2["cluster"], "cluster-beta")
        self.assertEqual(ref2["matchedDimensions"], ["namespace"])
        self.assertEqual(ref2["reason"], "Indicates resource pressure")
        self.assertEqual(ref2["usedFor"], "next_check")

    def test_serialize_review_enrichment_omits_field_when_none(self) -> None:
        """Test that alertmanagerEvidenceReferences is not present when no refs exist."""
        artifact = _sample_review_enrichment_artifact(alertmanager_refs=None)
        root_dir = Path(tempfile.mkdtemp())

        result = _serialize_review_enrichment(
            artifacts=[artifact],
            root_dir=root_dir,
            run_id="test-run",
        )

        assert result is not None
        self.assertNotIn("alertmanagerEvidenceReferences", result)


class HealthUIMergeBehaviorTests(unittest.TestCase):
    """Tests for health/ui merge behavior for interpretation field."""

    def test_interpretation_merged_additively(self) -> None:
        """Test that interpretation is merged additively into payload."""
        # Create artifact with payload that has triageOrder
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="test-run",
            run_label="test-run",
            cluster_label="test-run",
            summary="Test summary",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/test.json",
            provider="llamacpp",
            timestamp=datetime.now(UTC),
            duration_ms=100,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={
                "triageOrder": ["cluster-a"],
                "topConcerns": ["existing concern"],
            },
            interpretation={
                "alertmanagerEvidenceReferences": _SAMPLE_AM_REFS,
                "focusNotes": ["new note from interpretation"],
            },
        )
        root_dir = Path(tempfile.mkdtemp())

        result = _serialize_review_enrichment(
            artifacts=[artifact],
            root_dir=root_dir,
            run_id="test-run",
        )

        assert result is not None

        # Existing payload fields should remain
        self.assertEqual(result["triageOrder"], ["cluster-a"])

        # New fields from interpretation should be added
        self.assertIn("alertmanagerEvidenceReferences", result)
        self.assertIn("focusNotes", result)
        self.assertEqual(result["focusNotes"], ["new note from interpretation"])

    def test_existing_payload_keys_not_overwritten(self) -> None:
        """Test that existing payload keys are not overwritten by interpretation values."""
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="test-run",
            run_label="test-run",
            cluster_label="test-run",
            summary="Test summary",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/test.json",
            provider="llamacpp",
            timestamp=datetime.now(UTC),
            duration_ms=100,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={
                "focusNotes": "original focus note",
            },
            interpretation={
                "focusNotes": ["interpretation focus note"],
                "alertmanagerEvidenceReferences": _SAMPLE_AM_REFS,
            },
        )
        root_dir = Path(tempfile.mkdtemp())

        result = _serialize_review_enrichment(
            artifacts=[artifact],
            root_dir=root_dir,
            run_id="test-run",
        )

        assert result is not None

        # Payload value should NOT be overwritten by interpretation
        # focusNotes from payload is preserved (not overwritten by interpretation)
        self.assertEqual(result["focusNotes"], ["original focus note"])

        # But alertmanagerEvidenceReferences should still be surfaced
        self.assertIn("alertmanagerEvidenceReferences", result)

    def test_alertmanager_references_surfaced_when_in_interpretation(self) -> None:
        """Test that alertmanagerEvidenceReferences is surfaced when present in interpretation."""
        # Only interpretation has the field (not payload)
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="test-run",
            run_label="test-run",
            cluster_label="test-run",
            summary="Test summary",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/test.json",
            provider="llamacpp",
            timestamp=datetime.now(UTC),
            duration_ms=100,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={},  # Empty payload, refs only in interpretation
            interpretation={
                "alertmanagerEvidenceReferences": _SAMPLE_AM_REFS,
            },
        )
        root_dir = Path(tempfile.mkdtemp())

        result = _serialize_review_enrichment(
            artifacts=[artifact],
            root_dir=root_dir,
            run_id="test-run",
        )

        assert result is not None
        self.assertIn("alertmanagerEvidenceReferences", result)
        refs = result["alertmanagerEvidenceReferences"]
        assert isinstance(refs, list)
        self.assertEqual(len(refs), 2)


class UIModelParsingTests(unittest.TestCase):
    """Tests for ui/model._build_review_enrichment_view() parsing."""

    def test_build_review_enrichment_view_parses_alertmanager_evidence_references(
        self,
    ) -> None:
        """Test that _build_review_enrichment_view() parses alertmanagerEvidenceReferences."""
        raw: ReviewEnrichmentPayload = {
            "status": "success",
            "provider": "llamacpp",
            "timestamp": "2026-01-01T00:00:00Z",
            "summary": "Test summary",
            "alertmanagerEvidenceReferences": _SAMPLE_AM_REFS,
        }

        view = _build_review_enrichment_view(raw)

        assert view is not None
        self.assertIsInstance(view, ReviewEnrichmentView)
        self.assertEqual(len(view.alertmanager_evidence_references), 2)

    def test_build_review_enrichment_view_parses_ref_fields(self) -> None:
        """Test that ref fields are parsed correctly: cluster, matched_dimensions, reason, used_for."""
        raw: ReviewEnrichmentPayload = {
            "status": "success",
            "provider": "llamacpp",
            "timestamp": "2026-01-01T00:00:00Z",
            "alertmanagerEvidenceReferences": [
                {
                    "cluster": "cluster-alpha",
                    "matchedDimensions": ["alertname", "severity"],
                    "reason": "Fires during pod restart events",
                    "usedFor": "summary",
                }
            ],
        }

        view = _build_review_enrichment_view(raw)

        assert view is not None
        refs = view.alertmanager_evidence_references
        self.assertEqual(len(refs), 1)

        ref = refs[0]
        self.assertEqual(ref.cluster, "cluster-alpha")
        self.assertEqual(ref.matched_dimensions, ("alertname", "severity"))
        self.assertEqual(ref.reason, "Fires during pod restart events")
        self.assertEqual(ref.used_for, "summary")

    def test_build_review_enrichment_view_supports_snake_case_input(self) -> None:
        """Test that parsing supports snake_case variant (alertmanager_evidence_references)."""
        raw = {
            "status": "success",
            "provider": "llamacpp",
            "alertmanager_evidence_references": [
                {
                    "cluster": "cluster-gamma",
                    "matched_dimensions": ["severity"],
                    "reason": "Test reason",
                    "used_for": "focus_note",
                }
            ],
        }

        view = _build_review_enrichment_view(raw)

        assert view is not None
        self.assertEqual(len(view.alertmanager_evidence_references), 1)
        ref = view.alertmanager_evidence_references[0]
        self.assertEqual(ref.cluster, "cluster-gamma")
        self.assertEqual(ref.matched_dimensions, ("severity",))
        self.assertEqual(ref.reason, "Test reason")
        self.assertEqual(ref.used_for, "focus_note")

    def test_build_review_enrichment_view_handles_empty_refs(self) -> None:
        """Test that empty refs result in empty tuple."""
        raw: ReviewEnrichmentPayload = {
            "status": "success",
            "provider": "llamacpp",
            "alertmanagerEvidenceReferences": [],
        }

        view = _build_review_enrichment_view(raw)

        assert view is not None
        self.assertEqual(view.alertmanager_evidence_references, ())

    def test_build_review_enrichment_view_handles_missing_refs(self) -> None:
        """Test that missing refs field results in empty tuple."""
        raw: ReviewEnrichmentPayload = {
            "status": "success",
            "provider": "llamacpp",
        }

        view = _build_review_enrichment_view(raw)

        assert view is not None
        self.assertEqual(view.alertmanager_evidence_references, ())


class UIAPISerializationTests(unittest.TestCase):
    """Tests for ui/api._serialize_review_enrichment() serialization."""

    def test_api_serialize_review_enrichment_includes_refs(self) -> None:
        """Test that API serialization includes alertmanagerEvidenceReferences."""
        view = ReviewEnrichmentView(
            status="success",
            provider="llamacpp",
            timestamp="2026-01-01T00:00:00Z",
            summary="Test summary",
            triage_order=("cluster-a",),
            top_concerns=(),
            evidence_gaps=(),
            next_checks=(),
            focus_notes=(),
            alertmanager_evidence_references=(
                AlertmanagerEvidenceReferenceView(
                    cluster="cluster-alpha",
                    matched_dimensions=("alertname", "severity"),
                    reason="Fires during pod restart events",
                    used_for="triage_order",
                ),
            ),
            artifact_path=None,
            error_summary=None,
            skip_reason=None,
        )

        payload = api_serialize_review_enrichment(view)

        assert payload is not None
        self.assertIn("alertmanagerEvidenceReferences", payload)
        refs = payload["alertmanagerEvidenceReferences"]
        assert refs is not None
        self.assertEqual(len(refs), 1)

    def test_api_serialize_review_enrichment_preserves_ref_fields(self) -> None:
        """Test that API serialization preserves all ref fields."""
        view = ReviewEnrichmentView(
            status="success",
            provider="llamacpp",
            timestamp="2026-01-01T00:00:00Z",
            summary="Test summary",
            triage_order=(),
            top_concerns=(),
            evidence_gaps=(),
            next_checks=(),
            focus_notes=(),
            alertmanager_evidence_references=(
                AlertmanagerEvidenceReferenceView(
                    cluster="cluster-beta",
                    matched_dimensions=("namespace", "alertname"),
                    reason="Indicates resource pressure",
                    used_for="focus_note",
                ),
            ),
            artifact_path=None,
            error_summary=None,
            skip_reason=None,
        )

        payload = api_serialize_review_enrichment(view)

        assert payload is not None
        refs = payload["alertmanagerEvidenceReferences"]
        assert refs is not None
        self.assertEqual(len(refs), 1)

        ref = refs[0]
        self.assertEqual(ref["cluster"], "cluster-beta")
        self.assertEqual(ref["matchedDimensions"], ["namespace", "alertname"])
        self.assertEqual(ref["reason"], "Indicates resource pressure")
        self.assertEqual(ref["usedFor"], "focus_note")

    def test_api_serialize_review_enrichment_handles_empty_refs(self) -> None:
        """Test that empty refs serialize to None (omitted from output)."""
        view = ReviewEnrichmentView(
            status="success",
            provider="llamacpp",
            timestamp="2026-01-01T00:00:00Z",
            summary="Test summary",
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

        payload = api_serialize_review_enrichment(view)

        assert payload is not None
        # Empty tuple serializes to None (field is omitted)
        refs = payload.get("alertmanagerEvidenceReferences")
        self.assertIsNone(refs)


class EndToEndProjectionTests(unittest.TestCase):
    """End-to-end tests for alertmanagerEvidenceReferences projection path."""

    def test_end_to_end_from_artifact_to_api_payload(self) -> None:
        """Test that alertmanagerEvidenceReferences survives full path: artifact → health/ui → model → api."""
        # Step 1: Create artifact with alertmanager refs in interpretation
        artifact = _sample_review_enrichment_artifact(alertmanager_refs=_SAMPLE_AM_REFS)
        root_dir = Path(tempfile.mkdtemp())

        # Step 2: Serialize through health/ui
        ui_payload = _serialize_review_enrichment(
            artifacts=[artifact],
            root_dir=root_dir,
            run_id="test-run",
        )
        assert ui_payload is not None
        self.assertIn("alertmanagerEvidenceReferences", ui_payload)
        ui_refs = ui_payload["alertmanagerEvidenceReferences"]
        assert isinstance(ui_refs, list)

        # Step 3: Build view through ui/model
        raw = cast(ReviewEnrichmentPayload, ui_payload)
        view = _build_review_enrichment_view(raw)
        assert view is not None
        self.assertEqual(len(view.alertmanager_evidence_references), 2)
        self.assertEqual(len(ui_refs), len(view.alertmanager_evidence_references))

        # Step 4: Serialize back through ui/api
        api_payload = api_serialize_review_enrichment(view)
        assert api_payload is not None
        self.assertIn("alertmanagerEvidenceReferences", api_payload)

        # Step 5: Verify field survived intact
        api_refs = api_payload["alertmanagerEvidenceReferences"]
        assert api_refs is not None
        self.assertEqual(len(ui_refs), len(api_refs))

        # Verify content
        for ui_ref, api_ref in zip(ui_refs, api_refs):
            self.assertEqual(ui_ref["cluster"], api_ref["cluster"])
            self.assertEqual(ui_ref["matchedDimensions"], api_ref["matchedDimensions"])
            self.assertEqual(ui_ref["reason"], api_ref["reason"])
            self.assertEqual(ui_ref["usedFor"], api_ref["usedFor"])

    def test_end_to_end_through_build_ui_context(self) -> None:
        """Test that alertmanagerEvidenceReferences survives through build_ui_context."""
        # Create sample ui index with alertmanager refs in review_enrichment
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])

        # Add alertmanager refs to review_enrichment
        run_entry["review_enrichment"]["alertmanagerEvidenceReferences"] = cast(  # type: ignore[index]
            "list[AlertmanagerEvidenceReferencePayload]", _SAMPLE_AM_REFS
        )

        # Add deterministic next checks for valid context
        index["deterministic_next_checks"] = {
            "clusterCount": 1,
            "totalNextCheckCount": 1,
            "clusters": [
                {
                    "label": "cluster-a",
                    "context": "cluster-a",
                    "topProblem": "warning_event_threshold",
                    "deterministicNextCheckCount": 1,
                    "deterministicNextCheckSummaries": [
                        {
                            "description": "capture tcpdump",
                            "owner": "platform",
                            "method": "kubectl exec",
                            "evidenceNeeded": ["tcpdump"],
                            "workstream": "incident",
                            "urgency": "high",
                            "isPrimaryTriage": True,
                            "whyNow": "Immediate triage",
                        }
                    ],
                    "drilldownAvailable": True,
                    "assessmentArtifactPath": "assessments/cluster-a.json",
                    "drilldownArtifactPath": "drilldowns/cluster-a.json",
                }
            ],
        }

        # Build context
        context = build_ui_context(index)

        # Verify view was built correctly
        assert context.run.review_enrichment is not None
        view = context.run.review_enrichment
        assert view is not None
        self.assertEqual(len(view.alertmanager_evidence_references), 2)

        # Verify first reference
        ref = view.alertmanager_evidence_references[0]
        self.assertEqual(ref.cluster, "cluster-alpha")
        self.assertEqual(ref.matched_dimensions, ("alertname", "severity"))
        self.assertEqual(ref.reason, "Fires during pod restart events")
        self.assertEqual(ref.used_for, "top_concern")

    def test_end_to_end_through_build_run_payload(self) -> None:
        """Test that alertmanagerEvidenceReferences survives through build_run_payload."""
        # Create sample ui index with alertmanager refs
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])

        # Add alertmanager refs to review_enrichment
        run_entry["review_enrichment"]["alertmanagerEvidenceReferences"] = cast(  # type: ignore[index]
            "list[AlertmanagerEvidenceReferencePayload]", _SAMPLE_AM_REFS
        )

        # Add deterministic next checks for valid context
        index["deterministic_next_checks"] = {
            "clusterCount": 1,
            "totalNextCheckCount": 1,
            "clusters": [
                {
                    "label": "cluster-a",
                    "context": "cluster-a",
                    "topProblem": "warning_event_threshold",
                    "deterministicNextCheckCount": 1,
                    "deterministicNextCheckSummaries": [
                        {
                            "description": "capture tcpdump",
                            "owner": "platform",
                            "method": "kubectl exec",
                            "evidenceNeeded": ["tcpdump"],
                            "workstream": "incident",
                            "urgency": "high",
                            "isPrimaryTriage": True,
                            "whyNow": "Immediate triage",
                        }
                    ],
                    "drilldownAvailable": True,
                    "assessmentArtifactPath": "assessments/cluster-a.json",
                    "drilldownArtifactPath": "drilldowns/cluster-a.json",
                }
            ],
        }

        # Build context
        context = build_ui_context(index)

        # Build API payload
        payload = build_run_payload(context)

        # Verify alertmanager refs are in the payload
        review_enrichment = payload.get("reviewEnrichment")
        assert review_enrichment is not None
        assert isinstance(review_enrichment, dict)
        self.assertIn("alertmanagerEvidenceReferences", review_enrichment)

        refs = review_enrichment["alertmanagerEvidenceReferences"]
        assert refs is not None
        self.assertEqual(len(refs), 2)

        # Verify content
        ref1 = refs[0]
        self.assertEqual(ref1["cluster"], "cluster-alpha")
        self.assertEqual(ref1["matchedDimensions"], ["alertname", "severity"])
        self.assertEqual(ref1["reason"], "Fires during pod restart events")
        self.assertEqual(ref1["usedFor"], "top_concern")


if __name__ == "__main__":
    unittest.main()

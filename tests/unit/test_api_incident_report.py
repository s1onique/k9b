"""Unit tests for incident report payload construction.

Tests the core incident report payload building functionality.
"""

from __future__ import annotations

import unittest
from typing import cast

from k8s_diag_agent.ui.api import build_run_payload
from k8s_diag_agent.ui.api_incident_report import _build_incident_report_payload
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.ui_index_sample import sample_ui_index
from tests.unit.test_api_incident_report_helpers import _sample_freshness


class IncidentReportPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_degraded_run_produces_non_empty_incident_report(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["facts"])
        self.assertIn("cluster-a", str(payload["affectedScope"]))
        # Source artifact refs should be preserved
        self.assertTrue(payload["sourceArtifactRefs"])
        paths = {ref["path"] for ref in payload["sourceArtifactRefs"]}
        self.assertIn("assessments/cluster-a.json", paths)
        self.assertIn("drilldowns/cluster-a.json", paths)

    def test_healthy_run_produces_honest_empty_state(self) -> None:
        # Mutate fleet status and assessment to healthy, and strip provider-assisted data
        index = sample_ui_index()
        fs = cast(dict[str, object], index["fleet_status"])
        fs["rating_counts"] = [{"rating": "healthy", "count": 1}]
        fs["degraded_clusters"] = []
        # Also update the latest assessment so it doesn't contradict fleet status
        la = cast(dict[str, object], index["latest_assessment"])
        la["health_rating"] = "healthy"
        la["findings"] = []
        la["hypotheses"] = []
        la["missing_evidence"] = []
        # Remove provider-assisted content so we test the honest empty path
        run_entry = cast(dict[str, object], index["run"])
        run_entry["review_enrichment"] = None
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "healthy")
        # Healthy run should still have deterministic facts (assessment rating)
        self.assertTrue(payload["facts"])
        # No inferences or unknowns for a clean healthy run
        self.assertFalse(payload["inferences"])
        self.assertFalse(payload["unknowns"])

    def test_missing_evidence_surfaces_as_unknown(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        unknown_statements = [u["statement"] for u in payload["unknowns"]]
        self.assertTrue(unknown_statements)
        self.assertIn("Missing evidence: foo", unknown_statements)

    def test_provider_content_is_inference_not_fact(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        # Review enrichment summary should appear in inferences, not facts
        inference_statements = [i["statement"] for i in payload["inferences"]]
        self.assertIn("Review enrichment prioritized clusters.", inference_statements)
        # It must NOT appear in facts
        fact_statements = [f["statement"] for f in payload["facts"]]
        self.assertNotIn("Review enrichment prioritized clusters.", fact_statements)

    def test_stale_evidence_warning_when_freshness_delayed(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("delayed")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload["staleEvidenceWarnings"])
        self.assertIn("Run freshness is delayed", payload["staleEvidenceWarnings"][0])

    def test_stale_evidence_warning_when_freshness_stale(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("stale")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload["staleEvidenceWarnings"])
        self.assertIn("Run freshness is stale", payload["staleEvidenceWarnings"][0])

    def test_no_stale_warning_when_fresh(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertFalse(payload["staleEvidenceWarnings"])

    def test_build_run_payload_threads_incident_report(self) -> None:
        payload = build_run_payload(self.context)
        self.assertIn("incidentReport", payload)
        report = payload["incidentReport"]
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["status"], "degraded")

    def test_source_refs_deduped_and_omit_unknown(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        paths = [ref["path"] for ref in payload["sourceArtifactRefs"]]
        # "unknown" should be omitted
        self.assertNotIn("unknown", paths)
        # No duplicate paths
        self.assertEqual(len(paths), len(set(paths)))



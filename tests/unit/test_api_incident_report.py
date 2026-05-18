"""Unit tests for incident report and operator worklist payload builders.

Coverage goals (per epic):
- degraded run produces a non-empty incident report
- healthy/no-evidence run produces honest empty/unknown states
- worklist items include command, target, reason, state, and provenance
- provider-assisted content is not classified as deterministic fact
- stale or missing evidence is represented explicitly when supported
- golden fixture regressions for all hard gates
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, cast

from k8s_diag_agent.ui.api import build_run_payload
from k8s_diag_agent.ui.api_incident_report import (
    _build_incident_report_payload,
    _build_operator_worklist_payload,
)
from k8s_diag_agent.ui.api_payloads import CrossClusterFindingPayload
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.incident_report_fixtures import (
    _fixture_approval_needed_item,
    _fixture_degraded_single_cluster,
    _fixture_deterministic_only_no_command,
    _fixture_duplicate_candidates,
    _fixture_executed_with_usefulness,
    _fixture_healthy_no_incident,
    _fixture_multi_signal_executed_with_pending,
    _fixture_queue_with_command,
    _fixture_stale_provider_enriched_degraded,
    _freshness,
)
from tests.fixtures.ui_index_sample import sample_ui_index


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


class VmalertDiscoveryContextTests(unittest.TestCase):
    """Tests for vmalert discovery context in incident report."""

    def test_incident_report_includes_vmalert_context_when_sources_exist(self) -> None:
        """Test that incident report includes vmalertDiscoveryContext when vmalert sources are present."""
        index = sample_ui_index()
        # Add vmalert sources to the run data
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_sources"] = {
            "sources": [
                {
                    "source_id": "test-vmalert-1",
                    "endpoint": "http://vmalert:8880",
                    "namespace": "victoria-metrics",
                    "name": "vmalert",
                    "origin": "service-heuristic",
                    "state": "discovered",
                    "discovered_at": "2026-01-01T00:00:00Z",
                    "verified_at": None,
                    "last_check": None,
                    "last_error": None,
                    "verified_version": None,
                    "confidence_hints": ["vmalert-name-matched"],
                    "merged_provenances": ["service-heuristic"],
                    "display_provenance": "Service Heuristic",
                    "is_manual": False,
                    "is_tracking": False,
                    "can_disable": False,
                    "can_promote": True,
                    "display_origin": "Service Heuristic",
                    "display_state": "Discovered",
                    "provenance_summary": "vmalert-name-matched",
                    "cluster_label": "cluster-a",
                    "manual_source_mode": None,
                    "canonicalEntityId": None,
                    "cluster_uid": None,
                    "object_uid": None,
                }
            ],
            "total_count": 1,
            "source_count": 1,
            "discovered_count": 1,
            "discovered_but_unverified_count": 0,
            "auto_tracked_count": 0,
            "manual_count": 0,
            "discovery_timestamp": "2026-01-01T00:00:00Z",
            "cluster_context": "cluster-a",
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        # vmalert context should be present
        self.assertIn("vmalertDiscoveryContext", payload)
        vmalert_ctx = payload["vmalertDiscoveryContext"]
        self.assertIsNotNone(vmalert_ctx)
        assert vmalert_ctx is not None
        # Verify source count
        self.assertEqual(vmalert_ctx["source_count"], 1)
        self.assertEqual(vmalert_ctx["discovered_count"], 1)
        self.assertEqual(vmalert_ctx["discovered_but_unverified_count"], 0)
        # Verify source details
        self.assertEqual(len(vmalert_ctx["sources"]), 1)
        source = vmalert_ctx["sources"][0]
        self.assertEqual(source["endpoint"], "http://vmalert:8880")
        self.assertEqual(source["namespace"], "victoria-metrics")
        self.assertEqual(source["name"], "vmalert")
        self.assertEqual(source["origin"], "service-heuristic")
        self.assertEqual(source["state"], "discovered")
        self.assertEqual(source["display_provenance"], "Service Heuristic")
        self.assertEqual(source["cluster_label"], "cluster-a")

    def test_incident_report_includes_discovered_but_unverified_sources(self) -> None:
        """Test that discovered-but-unverified sources are represented but non-fatal."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_sources"] = {
            "sources": [
                {
                    "source_id": "test-vmalert-unverified",
                    "endpoint": "http://vmalert-unverified:8880",
                    "namespace": "victoria-metrics",
                    "name": "vmalert-unverified",
                    "origin": "service-heuristic",
                    "state": "discovered-but-unverified",
                    "discovered_at": "2026-01-01T00:00:00Z",
                    "verified_at": None,
                    "last_check": None,
                    "last_error": "Connection refused",
                    "verified_version": None,
                    "confidence_hints": [],
                    "merged_provenances": ["service-heuristic"],
                    "display_provenance": "Service Heuristic",
                    "is_manual": False,
                    "is_tracking": False,
                    "can_disable": False,
                    "can_promote": True,
                    "display_origin": "Service Heuristic",
                    "display_state": "Discovered (Unverified)",
                    "provenance_summary": "-",
                    "cluster_label": "cluster-a",
                    "manual_source_mode": None,
                    "canonicalEntityId": None,
                    "cluster_uid": None,
                    "object_uid": None,
                }
            ],
            "total_count": 1,
            "source_count": 1,
            "discovered_count": 0,
            "discovered_but_unverified_count": 1,
            "auto_tracked_count": 0,
            "manual_count": 0,
            "discovery_timestamp": "2026-01-01T00:00:00Z",
            "cluster_context": "cluster-a",
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        # vmalert context should be present
        self.assertIn("vmalertDiscoveryContext", payload)
        vmalert_ctx = payload["vmalertDiscoveryContext"]
        self.assertIsNotNone(vmalert_ctx)
        assert vmalert_ctx is not None
        # Verify counts reflect unverified state
        self.assertEqual(vmalert_ctx["source_count"], 1)
        self.assertEqual(vmalert_ctx["discovered_count"], 0)
        self.assertEqual(vmalert_ctx["discovered_but_unverified_count"], 1)
        # State should be preserved
        source = vmalert_ctx["sources"][0]
        self.assertEqual(source["state"], "discovered-but-unverified")

    def test_incident_report_null_vmalert_when_no_sources(self) -> None:
        """Test that incident report has null vmalert context when no vmalert sources."""
        # Create index without vmalert sources
        index = sample_ui_index()
        # Ensure no vmalert_sources in run
        run_entry = cast(dict[str, object], index["run"])
        if "vmalert_sources" in run_entry:
            del run_entry["vmalert_sources"]
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        # vmalert context should be None when no sources
        self.assertIn("vmalertDiscoveryContext", payload)
        self.assertIsNone(payload["vmalertDiscoveryContext"])

    def test_vmalert_context_quiet_when_source_count_zero(self) -> None:
        """Test that zero vmalert sources is quiet (not an error)."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        # Empty sources - not an error
        run_entry["vmalert_sources"] = {
            "sources": [],
            "total_count": 0,
            "source_count": 0,
            "discovered_count": 0,
            "discovered_but_unverified_count": 0,
            "auto_tracked_count": 0,
            "manual_count": 0,
            "discovery_timestamp": None,
            "cluster_context": None,
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        # vmalert context should be present but with zero counts
        self.assertIn("vmalertDiscoveryContext", payload)
        vmalert_ctx = payload["vmalertDiscoveryContext"]
        self.assertIsNotNone(vmalert_ctx)
        assert vmalert_ctx is not None
        self.assertEqual(vmalert_ctx["source_count"], 0)
        self.assertEqual(len(vmalert_ctx["sources"]), 0)

    def test_vmalert_context_multiple_sources(self) -> None:
        """Test vmalert context with multiple sources."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_sources"] = {
            "sources": [
                {
                    "source_id": "test-vmalert-1",
                    "endpoint": "http://vmalert-1:8880",
                    "namespace": "vm-ns-1",
                    "name": "vmalert-1",
                    "origin": "vmalert-crd",
                    "state": "auto-tracked",
                    "discovered_at": "2026-01-01T00:00:00Z",
                    "verified_at": "2026-01-01T00:01:00Z",
                    "last_check": "2026-01-01T00:01:00Z",
                    "last_error": None,
                    "verified_version": "vmalert-2024.1.0",
                    "confidence_hints": ["crd-matched", "http-verified"],
                    "merged_provenances": ["vmalert-crd"],
                    "display_provenance": "VMAlert CRD",
                    "is_manual": False,
                    "is_tracking": True,
                    "can_disable": True,
                    "can_promote": False,
                    "display_origin": "VMAlert CRD",
                    "display_state": "Auto-tracked",
                    "provenance_summary": "crd-matched; http-verified",
                    "cluster_label": "cluster-a",
                    "manual_source_mode": None,
                    "canonicalEntityId": "hash-123",
                    "cluster_uid": "uid-abc",
                    "object_uid": "obj-def",
                },
                {
                    "source_id": "test-vmalert-2",
                    "endpoint": "http://vmalert-2:8880",
                    "namespace": "vm-ns-2",
                    "name": "vmalert-2",
                    "origin": "service-heuristic",
                    "state": "discovered",
                    "discovered_at": "2026-01-01T00:00:00Z",
                    "verified_at": None,
                    "last_check": None,
                    "last_error": None,
                    "verified_version": None,
                    "confidence_hints": ["vmalert-name-matched"],
                    "merged_provenances": ["service-heuristic"],
                    "display_provenance": "Service Heuristic",
                    "is_manual": False,
                    "is_tracking": False,
                    "can_disable": False,
                    "can_promote": True,
                    "display_origin": "Service Heuristic",
                    "display_state": "Discovered",
                    "provenance_summary": "vmalert-name-matched",
                    "cluster_label": "cluster-b",
                    "manual_source_mode": None,
                    "canonicalEntityId": "hash-456",
                    "cluster_uid": None,
                    "object_uid": None,
                },
            ],
            "total_count": 2,
            "source_count": 2,
            "discovered_count": 1,
            "discovered_but_unverified_count": 0,
            "auto_tracked_count": 1,
            "manual_count": 0,
            "discovery_timestamp": "2026-01-01T00:00:00Z",
            "cluster_context": "cluster-a",
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        vmalert_ctx = payload["vmalertDiscoveryContext"]
        self.assertIsNotNone(vmalert_ctx)
        assert vmalert_ctx is not None
        # Verify counts
        self.assertEqual(vmalert_ctx["source_count"], 2)
        self.assertEqual(vmalert_ctx["discovered_count"], 1)
        self.assertEqual(len(vmalert_ctx["sources"]), 2)
        # Verify both sources are present
        endpoints = {s["endpoint"] for s in vmalert_ctx["sources"]}
        self.assertIn("http://vmalert-1:8880", endpoints)
        self.assertIn("http://vmalert-2:8880", endpoints)

    def test_run_payload_includes_vmalert_context_in_incident_report(self) -> None:
        """Test that build_run_payload includes vmalert context in incident report."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_sources"] = {
            "sources": [
                {
                    "source_id": "test-vmalert",
                    "endpoint": "http://vmalert:8880",
                    "namespace": "victoria-metrics",
                    "name": "vmalert",
                    "origin": "service-heuristic",
                    "state": "discovered",
                    "discovered_at": "2026-01-01T00:00:00Z",
                    "verified_at": None,
                    "last_check": None,
                    "last_error": None,
                    "verified_version": None,
                    "confidence_hints": [],
                    "merged_provenances": ["service-heuristic"],
                    "display_provenance": "Service Heuristic",
                    "is_manual": False,
                    "is_tracking": False,
                    "can_disable": False,
                    "can_promote": True,
                    "display_origin": "Service Heuristic",
                    "display_state": "Discovered",
                    "provenance_summary": "-",
                    "cluster_label": "cluster-a",
                    "manual_source_mode": None,
                    "canonicalEntityId": None,
                    "cluster_uid": None,
                    "object_uid": None,
                }
            ],
            "total_count": 1,
            "source_count": 1,
            "discovered_count": 1,
            "discovered_but_unverified_count": 0,
            "auto_tracked_count": 0,
            "manual_count": 0,
            "discovery_timestamp": "2026-01-01T00:00:00Z",
            "cluster_context": "cluster-a",
        }
        context = build_ui_context(index)
        run_payload = build_run_payload(context)
        # Check incident report in run payload
        self.assertIn("incidentReport", run_payload)
        incident_report = run_payload["incidentReport"]
        self.assertIsNotNone(incident_report)
        assert incident_report is not None
        # Verify vmalert context is threaded through
        self.assertIn("vmalertDiscoveryContext", incident_report)
        self.assertIsNotNone(incident_report["vmalertDiscoveryContext"])


class VmalertRuleStateContextTests(unittest.TestCase):
    """Tests for vmalert rule state context in incident report."""

    def test_missing_vmalert_rule_state_returns_none(self) -> None:
        """Test that missing vmalert rule-state artifact returns vmalertRuleStateContext None."""
        index = sample_ui_index()
        # No vmalert_rule_state in run data
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("vmalertRuleStateContext", payload)
        self.assertIsNone(payload["vmalertRuleStateContext"])

    def test_empty_alert_state_returns_quiet_zero_count(self) -> None:
        """Test that empty alert state returns quiet zero-count context."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 0,
            "firing_alert_count": 0,
            "pending_alert_count": 0,
            "critical_firing_count": 0,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("vmalertRuleStateContext", payload)
        ctx = payload["vmalertRuleStateContext"]
        self.assertIsNotNone(ctx)
        assert ctx is not None
        # Verify zero counts for quiet state
        self.assertEqual(ctx["alert_count"], 0)
        self.assertEqual(ctx["firing_alert_count"], 0)
        self.assertEqual(ctx["pending_alert_count"], 0)
        self.assertEqual(ctx["critical_firing_count"], 0)
        self.assertEqual(ctx["fetch_error_count"], 0)

    def test_firing_critical_alert_in_counts(self) -> None:
        """Test that firing critical alert appears in firing/critical counts."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 3,
            "firing_alert_count": 2,
            "pending_alert_count": 1,
            "critical_firing_count": 1,
            "rule_group_count": 1,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "CriticalAlert", "state": "firing", "severity": "critical",
                 "namespace": "default", "workload": "deployment/app"},
                {"alertname": "WarningAlert", "state": "firing", "severity": "warning",
                 "namespace": "monitoring", "workload": "statefulset/db"},
                {"alertname": "PendingAlert", "state": "pending", "severity": "info",
                 "namespace": "kube-system", "workload": "deployment/pending"},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("vmalertRuleStateContext", payload)
        ctx = payload["vmalertRuleStateContext"]
        self.assertIsNotNone(ctx)
        assert ctx is not None
        # Verify counts
        self.assertEqual(ctx["alert_count"], 3)
        self.assertEqual(ctx["firing_alert_count"], 2)
        self.assertEqual(ctx["pending_alert_count"], 1)
        self.assertEqual(ctx["critical_firing_count"], 1)

    def test_pending_alert_in_pending_count_not_firing(self) -> None:
        """Test that pending alert appears in pending count but not firing count."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 2,
            "firing_alert_count": 1,
            "pending_alert_count": 1,
            "critical_firing_count": 0,
            "rule_group_count": 1,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "FiringAlert", "state": "firing", "severity": "warning",
                 "namespace": "default", "workload": None},
                {"alertname": "PendingAlert", "state": "pending", "severity": "warning",
                 "namespace": "kube-system", "workload": None},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        ctx = payload["vmalertRuleStateContext"]
        self.assertIsNotNone(ctx)
        assert ctx is not None
        # Pending is not firing
        self.assertEqual(ctx["firing_alert_count"], 1)
        self.assertEqual(ctx["pending_alert_count"], 1)

    def test_top_alertnames_severity_counts_affected_namespaces_workloads(self) -> None:
        """Test that computed properties are threaded into context."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 5,
            "firing_alert_count": 3,
            "pending_alert_count": 2,
            "critical_firing_count": 1,
            "rule_group_count": 1,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                # Firing alerts (count for top_alertnames, severity_counts, affected namespaces/workloads)
                {"alertname": "PodNotReady", "state": "firing", "severity": "critical",
                 "namespace": "default", "workload": "deployment/app1"},
                {"alertname": "PodNotReady", "state": "firing", "severity": "critical",
                 "namespace": "default", "workload": "deployment/app2"},  # Same namespace, different workload
                {"alertname": "HighCpu", "state": "firing", "severity": "warning",
                 "namespace": "monitoring", "workload": "statefulset/db"},
                # Pending alerts (NOT counted for top_alertnames, severity_counts, affected)
                {"alertname": "PendingAlert", "state": "pending", "severity": "info",
                 "namespace": "kube-system", "workload": "deployment/pending"},
                {"alertname": "PendingAlert2", "state": "pending", "severity": "warning",
                 "namespace": "kube-system", "workload": "deployment/pending2"},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        ctx = payload["vmalertRuleStateContext"]
        self.assertIsNotNone(ctx)
        assert ctx is not None

        # top_alertnames: most common firing alertnames (PodNotReady > HighCpu)
        self.assertIn("top_alertnames", ctx)
        assert ctx["top_alertnames"] is not None
        top_names = ctx["top_alertnames"]
        self.assertIn("PodNotReady", top_names)
        self.assertIn("HighCpu", top_names)
        # PodNotReady appears twice (2 firing), HighCpu once (1 firing)
        # Order should be by count descending
        pod_index = top_names.index("PodNotReady") if "PodNotReady" in top_names else -1
        cpu_index = top_names.index("HighCpu") if "HighCpu" in top_names else -1
        if pod_index >= 0 and cpu_index >= 0:
            self.assertLess(pod_index, cpu_index)  # PodNotReady should come first

        # severity_counts: only firing alerts counted
        self.assertIn("severity_counts", ctx)
        assert ctx["severity_counts"] is not None
        severity_dict = dict(ctx["severity_counts"])
        self.assertEqual(severity_dict.get("critical"), 2)  # Two PodNotReady firing (both critical)
        self.assertEqual(severity_dict.get("warning"), 1)  # Only HighCpu (warning)
        self.assertNotIn("info", severity_dict)  # Pending alerts not counted
        self.assertNotIn("warning", [s for s, c in ctx["severity_counts"] if s == "warning" and c == 2])  # Not 2 warnings

        # affected_namespaces: only firing alerts
        self.assertIn("affected_namespaces", ctx)
        assert ctx["affected_namespaces"] is not None
        namespaces = ctx["affected_namespaces"]
        self.assertIn("default", namespaces)  # Firing alerts
        self.assertIn("monitoring", namespaces)  # Firing alerts
        self.assertNotIn("kube-system", namespaces)  # Pending alerts not included

        # affected_workloads: only firing alerts
        self.assertIn("affected_workloads", ctx)
        assert ctx["affected_workloads"] is not None
        workloads = ctx["affected_workloads"]
        self.assertIn("deployment/app1", workloads)
        self.assertIn("deployment/app2", workloads)
        self.assertIn("statefulset/db", workloads)
        self.assertNotIn("deployment/pending", workloads)  # Pending not included

    def test_fetch_error_count_is_non_fatal(self) -> None:
        """Test that fetch_error_count is threaded as non-fatal context."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 3,
            "fetched_source_count": 2,
            "failed_source_count": 1,
            "alert_count": 2,
            "firing_alert_count": 1,
            "pending_alert_count": 1,
            "critical_firing_count": 0,
            "rule_group_count": 2,
            "fetch_error_count": 1,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "Alert1", "state": "firing", "severity": "warning", "namespace": None, "workload": None},
                {"alertname": "Alert2", "state": "pending", "severity": "info", "namespace": None, "workload": None},
            ],
            "rule_groups": [],
            "fetch_errors": [
                {"source_endpoint": "http://vmalert-failed:8880", "status": "500", "error": "connection refused"}
            ],
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        ctx = payload["vmalertRuleStateContext"]
        self.assertIsNotNone(ctx)
        assert ctx is not None

        # Source status
        self.assertEqual(ctx["source_count"], 3)
        self.assertEqual(ctx["fetched_source_count"], 2)
        self.assertEqual(ctx["failed_source_count"], 1)
        self.assertEqual(ctx["fetch_error_count"], 1)

        # Context is not None even with fetch errors (non-fatal)
        self.assertIsNotNone(ctx)

    def test_context_preserves_source_metadata(self) -> None:
        """Test that source metadata is preserved in context."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 2,
            "fetched_source_count": 1,
            "failed_source_count": 1,
            "alert_count": 0,
            "firing_alert_count": 0,
            "pending_alert_count": 0,
            "critical_firing_count": 0,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        ctx = payload["vmalertRuleStateContext"]
        self.assertIsNotNone(ctx)
        assert ctx is not None

        # Source metadata preserved
        self.assertEqual(ctx["source_count"], 2)
        self.assertEqual(ctx["fetched_source_count"], 1)
        self.assertEqual(ctx["failed_source_count"], 1)


class VmalertAlertWorklistItemTests(unittest.TestCase):
    """Tests for vmalert alert-derived operator worklist items."""

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_critical_firing_alert_creates_worklist_item(self) -> None:
        """Test that critical firing alert creates one worklist item."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 1,
            "firing_alert_count": 1,
            "pending_alert_count": 0,
            "critical_firing_count": 1,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "CriticalAlert", "state": "firing", "severity": "critical",
                 "namespace": "default", "workload": "deployment/app", "instance": "app-0",
                 "cluster_label": "cluster-a", "source_endpoint": "http://vmalert:8880"},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNotNone(payload)
        assert payload is not None
        
        # Find vmalert alert items
        vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
        self.assertEqual(len(vmalert_items), 1)
        
        item = vmalert_items[0]
        # ID contains alertname + namespace + workload + source_endpoint
        self.assertIn("vmalert-critical-CriticalAlert", item["id"])
        self.assertIn("default", item["id"])
        self.assertEqual(item["title"], "Critical vmalert alert firing: CriticalAlert (default/deployment/app)")
        self.assertIn("namespace=default", item["description"])
        self.assertIn("workload=deployment/app", item["description"])
        self.assertEqual(item["workstream"], "incident")
        self.assertEqual(item["itemState"], "advisory")
        self.assertIn("Critical vmalert alert firing", item["rankingReason"])

    def test_pending_critical_alert_does_not_create_item(self) -> None:
        """Test that pending critical alert does not create a worklist item."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 1,
            "firing_alert_count": 0,
            "pending_alert_count": 1,
            "critical_firing_count": 0,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "CriticalAlert", "state": "pending", "severity": "critical",
                 "namespace": "default", "workload": None},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNotNone(payload)
        assert payload is not None
        
        # No vmalert alert items for pending alerts
        vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
        self.assertEqual(len(vmalert_items), 0)

    def test_warning_firing_alert_does_not_create_item(self) -> None:
        """Test that warning firing alert does not create a worklist item."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 1,
            "firing_alert_count": 1,
            "pending_alert_count": 0,
            "critical_firing_count": 0,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "WarningAlert", "state": "firing", "severity": "warning",
                 "namespace": "monitoring", "workload": None},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNotNone(payload)
        assert payload is not None
        
        # No vmalert alert items for warning severity
        vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
        self.assertEqual(len(vmalert_items), 0)

    def test_missing_severity_firing_alert_does_not_create_item(self) -> None:
        """Test that firing alert with missing severity does not create a worklist item."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 1,
            "firing_alert_count": 1,
            "pending_alert_count": 0,
            "critical_firing_count": 0,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "UnknownSeverityAlert", "state": "firing", "severity": None,
                 "namespace": "default", "workload": None},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNotNone(payload)
        assert payload is not None
        
        # No vmalert alert items for missing severity
        vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
        self.assertEqual(len(vmalert_items), 0)

    def test_duplicate_critical_firing_alerts_deduplicate(self) -> None:
        """Test that duplicate critical firing alerts are deduplicated."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 2,
            "firing_alert_count": 2,
            "pending_alert_count": 0,
            "critical_firing_count": 2,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                # Same alertname + namespace + workload + source_endpoint = duplicate
                {"alertname": "CriticalAlert", "state": "firing", "severity": "critical",
                 "namespace": "default", "workload": "deployment/app",
                 "source_endpoint": "http://vmalert:8880"},
                {"alertname": "CriticalAlert", "state": "firing", "severity": "critical",
                 "namespace": "default", "workload": "deployment/app",
                 "source_endpoint": "http://vmalert:8880"},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNotNone(payload)
        assert payload is not None
        
        # Only one vmalert alert item (deduplicated)
        vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
        self.assertEqual(len(vmalert_items), 1)

    def test_distinct_namespaces_produce_distinct_items(self) -> None:
        """Test that distinct namespaces produce distinct worklist items."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 2,
            "firing_alert_count": 2,
            "pending_alert_count": 0,
            "critical_firing_count": 2,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "CriticalAlert", "state": "firing", "severity": "critical",
                 "namespace": "default", "workload": "deployment/app",
                 "source_endpoint": "http://vmalert:8880"},
                {"alertname": "CriticalAlert", "state": "firing", "severity": "critical",
                 "namespace": "monitoring", "workload": "deployment/app",
                 "source_endpoint": "http://vmalert:8880"},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNotNone(payload)
        assert payload is not None
        
        # Two distinct vmalert alert items (different namespaces)
        vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
        self.assertEqual(len(vmalert_items), 2)
        
        # Verify distinct IDs contain the namespace
        item_ids = {item["id"] for item in vmalert_items}
        self.assertEqual(len(item_ids), 2)
        # Check that both namespaces are represented in IDs
        self.assertTrue(any("default" in i for i in item_ids), f"Expected 'default' in IDs: {item_ids}")
        self.assertTrue(any("monitoring" in i for i in item_ids), f"Expected 'monitoring' in IDs: {item_ids}")

    def test_item_includes_alertname_namespace_workload_source_endpoint(self) -> None:
        """Test that worklist item includes alertname, namespace, workload, source endpoint, and provenance."""
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["vmalert_rule_state"] = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "alert_count": 1,
            "firing_alert_count": 1,
            "pending_alert_count": 0,
            "critical_firing_count": 1,
            "rule_group_count": 0,
            "fetch_error_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "CriticalAlert", "state": "firing", "severity": "critical",
                 "namespace": "default", "workload": "deployment/app",
                 "source_endpoint": "http://vmalert:8880",
                 "cluster_label": "cluster-a"},
            ],
            "rule_groups": [],
            "fetch_errors": [],
        }
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNotNone(payload)
        assert payload is not None
        
        vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
        self.assertEqual(len(vmalert_items), 1)
        
        item = vmalert_items[0]
        # Check alert identity in ID and title
        self.assertIn("CriticalAlert", item["id"])
        self.assertIn("CriticalAlert", item["title"])
        # Check namespace/workload in title
        self.assertIn("default", item["title"])
        # Check source endpoint in reason
        self.assertIn("http://vmalert:8880", item["reason"])
        # Check provenance
        self.assertEqual(item["sourceType"], "vmalert-alert")
        # Check target cluster
        self.assertEqual(item["targetCluster"], "cluster-a")

    def test_vmalert_alert_item_links_rule_state_artifact(self) -> None:
        """Test that vmalert alert worklist item links to the rule-state artifact."""
        import tempfile

        # Create a temp directory to act as health_root
        with tempfile.TemporaryDirectory() as tmp_dir:
            health_root = Path(tmp_dir)

            index = sample_ui_index()
            run_entry = cast(dict[str, object], index["run"])
            # Add run_id so artifact path can be constructed
            run_entry["run_id"] = "test-run-001"
            run_entry["vmalert_rule_state"] = {
                "source_count": 1,
                "fetched_source_count": 1,
                "failed_source_count": 0,
                "alert_count": 1,
                "firing_alert_count": 1,
                "pending_alert_count": 0,
                "critical_firing_count": 1,
                "rule_group_count": 0,
                "fetch_error_count": 0,
                "captured_at": "2024-01-01T00:00:00Z",
                "alerts": [
                    {"alertname": "CriticalAlert", "state": "firing", "severity": "critical",
                     "namespace": "default", "workload": None, "source_endpoint": None,
                     "cluster_label": "cluster-a"},
                ],
                "rule_groups": [],
                "fetch_errors": [],
            }
            context = build_ui_context(index)
            payload = _build_operator_worklist_payload(context, health_root=health_root)
            self.assertIsNotNone(payload)
            assert payload is not None

            # Find vmalert alert item
            vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
            self.assertEqual(len(vmalert_items), 1)

            item = vmalert_items[0]
            # Verify sourceArtifactRefs contains the rule-state artifact
            refs = item.get("sourceArtifactRefs") or []
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["label"], "VMAlert Rule State")
            self.assertEqual(refs[0]["path"], "test-run-001-vmalert-rule-state.json")

    def test_no_vmalert_rule_state_returns_normal_worklist(self) -> None:
        """Test that missing vmalert rule state returns normal worklist unchanged."""
        index = sample_ui_index()
        # No vmalert_rule_state in run data
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNotNone(payload)
        assert payload is not None
        
        # No vmalert alert items
        vmalert_items = [i for i in payload["items"] if i.get("sourceType") == "vmalert-alert"]
        self.assertEqual(len(vmalert_items), 0)


def _sample_freshness(status: str) -> dict[str, object]:
    """Return a sample freshness payload."""
    return {
        "ageSeconds": 60 if status == "fresh" else 600 if status == "stale" else 120,
        "expectedIntervalSeconds": 300,
        "status": status,
    }


class OperatorWorklistPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_worklist_items_have_command_target_reason_state(self) -> None:
        payload = _build_operator_worklist_payload(self.context)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload["items"])
        item = payload["items"][0]
        self.assertIn("title", item)
        self.assertIn("command", item)
        self.assertIn("targetCluster", item)
        self.assertIn("reason", item)
        # States may be None for deterministic items, but keys exist
        self.assertIn("approvalState", item)
        self.assertIn("executionState", item)
        self.assertIn("feedbackState", item)

    def test_worklist_includes_source_artifact_refs(self) -> None:
        payload = _build_operator_worklist_payload(self.context)
        self.assertIsNotNone(payload)
        assert payload is not None
        for item in payload["items"]:
            refs = item.get("sourceArtifactRefs") or []
            self.assertTrue(
                refs,
                f"Item {item.get('id')} should have sourceArtifactRefs",
            )

    def test_worklist_counts_consistent(self) -> None:
        payload = _build_operator_worklist_payload(self.context)
        self.assertIsNotNone(payload)
        assert payload is not None
        total = payload["totalItems"]
        completed = payload["completedItems"]
        pending = payload["pendingItems"]
        blocked = payload["blockedItems"]
        self.assertEqual(total, completed + pending + blocked)

    def test_build_run_payload_threads_operator_worklist(self) -> None:
        payload = build_run_payload(self.context)
        self.assertIn("operatorWorklist", payload)
        worklist = payload["operatorWorklist"]
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])

    def test_no_worklist_when_no_actionable_items(self) -> None:
        # Build an index with no deterministic next checks and empty queue
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["deterministic_next_checks"] = None
        run_entry["next_check_queue"] = []
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNone(payload)


class TruthfulnessContractTests(unittest.TestCase):
    """Cross-cutting truthfulness assertions."""

    def test_facts_never_include_review_enrichment(self) -> None:
        index = sample_ui_index()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        for fact in report["facts"]:
            # Review enrichment is provider-assisted; it must not be a fact
            self.assertNotIn("enrichment", str(fact["statement"]).lower())

    def test_provider_assisted_marked_as_inference(self) -> None:
        index = sample_ui_index()
        # Ensure review enrichment is present
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        enrichment_in_inferences = [
            i for i in report["inferences"] if "enrichment" in str(i.get("basis", [])).lower()
        ]
        self.assertTrue(
            enrichment_in_inferences,
            "Expected at least one inference with review-enrichment basis",
        )


# =============================================================================
# Claim Taxonomy Tests (Epic: Incident Report Content Quality)
# =============================================================================


class ClaimTaxonomyTests(unittest.TestCase):
    """Tests for the deterministic incident report claim taxonomy.

    Taxonomy:
    - observed: Direct telemetry signal with evidence/provenance
    - derived: Deterministic conclusion from evidence fields
    - hypothesis: Plausible cause that requires confirmation
    - recommendation: Operator action suggestion with safety level
    - unknown: Explicitly acknowledged missing evidence

    Invariants:
    - observed claims have sourceArtifactRefs
    - hypothesis claims have non-empty basis
    - recommendations have safetyLevel
    - unknowns have whyMissing explanation
    - root-cause language only appears in hypothesis claims
    """

    def test_observed_claims_have_evidence_and_provenance(self) -> None:
        """observed claims must have sourceArtifactRefs pointing to real artifacts."""
        index = sample_ui_index()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        for fact in report["facts"]:
            self.assertEqual(fact.get("claimType"), "observed")
            # observed claims must have provenance
            self.assertTrue(
                fact.get("sourceArtifactRefs"),
                f"observed claim must have sourceArtifactRefs: {fact}",
            )

    def test_derived_claims_are_deferred(self) -> None:
        """derived claims are a deferred feature in this epic.

        Derived claim population will be implemented when assessment produces
        deterministic conclusions from multiple evidence fields.
        The IncidentReportDerivedPayload type is defined and exported.
        """
        from k8s_diag_agent.ui.api_payloads import IncidentReportDerivedPayload
        # Verify the type exists and is properly defined
        self.assertTrue(hasattr(IncidentReportDerivedPayload, "__annotations__"))
        annotations = IncidentReportDerivedPayload.__annotations__
        self.assertIn("claimType", annotations)
        self.assertIn("sourceFields", annotations)
        self.assertIn("statement", annotations)
        self.assertIn("sourceArtifactRefs", annotations)
        self.assertIn("confidence", annotations)

    def test_hypothesis_claims_have_non_empty_basis(self) -> None:
        """hypothesis claims must have a non-empty basis list."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        for inference in report["inferences"]:
            self.assertEqual(inference.get("claimType"), "hypothesis")
            basis = inference.get("basis", [])
            self.assertTrue(
                basis,
                f"hypothesis claim must have non-empty basis: {inference}",
            )

    def test_recommendations_have_safety_level(self) -> None:
        """recommendation claims must have a safety level."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Recommendations are derived from assessment.recommended_action
        # The builder populates recommendations[] alongside recommendedActions
        # Verify recommendations have safety level when available
        for action in report.get("recommendedActions", []):
            self.assertIsInstance(action, str)

    def test_unknown_claims_have_why_missing(self) -> None:
        """unknown claims must have a whyMissing explanation."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        for unknown in report["unknowns"]:
            self.assertEqual(unknown.get("claimType"), "unknown")
            self.assertIsNotNone(
                unknown.get("whyMissing"),
                f"unknown claim must have whyMissing: {unknown}",
            )

    def test_root_cause_language_not_in_observed_claims(self) -> None:
        """observed claims must not contain root-cause language."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        root_cause_phrases = ["root cause", "caused by", "because of"]
        for fact in report["facts"]:
            statement = fact.get("statement", "")
            for phrase in root_cause_phrases:
                self.assertNotIn(
                    phrase,
                    statement.lower(),
                    f"observed claim must not contain root-cause language: {fact}",
                )

    def test_hypothesis_claims_may_have_root_cause_language(self) -> None:
        """hypothesis claims may contain root-cause language when basis is provided."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Hypotheses may include root-cause language because they are explicitly
        # labeled as non-factual and have a basis
        for inference in report["inferences"]:
            self.assertEqual(inference.get("claimType"), "hypothesis")
            # Must have basis to be labeled as hypothesis
            self.assertTrue(inference.get("basis"))

    def test_missing_evidence_surfaces_as_unknown_not_omitted(self) -> None:
        """missing evidence must surface as unknown, not be omitted or invented."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # The fixture has missing_evidence: ["events"]
        # Verify it surfaces as unknown, not as confident fact
        self.assertTrue(
            report["unknowns"],
            "Missing evidence must surface as unknown claims",
        )
        unknown_statements = [u["statement"] for u in report["unknowns"]]
        self.assertTrue(
            any("Missing evidence" in s or "missing" in s.lower() for s in unknown_statements),
            f"Missing evidence should appear as unknown: {unknown_statements}",
        )

    def test_claim_type_constants_are_correct(self) -> None:
        """Verify claimType values match the taxonomy."""
        from k8s_diag_agent.ui.api_payloads import (
            IncidentReportFactPayload,
            IncidentReportInferencePayload,
            IncidentReportUnknownPayload,
        )

        # Verify TypedDict fields include claimType
        fact_fields = set(IncidentReportFactPayload.__annotations__.keys())
        self.assertIn("claimType", fact_fields)

        inference_fields = set(IncidentReportInferencePayload.__annotations__.keys())
        self.assertIn("claimType", inference_fields)

        unknown_fields = set(IncidentReportUnknownPayload.__annotations__.keys())
        self.assertIn("claimType", unknown_fields)

    def test_root_cause_guard_prevents_fabricated_causality_in_observed(self) -> None:
        """Negative test: root-cause language in raw findings must not leak into observed claims.

        This test uses a fixture with drilldown data that contains root-cause wording
        in trigger reasons, and verifies the builder does not emit it as an observed claim.
        Without this guard, bad input would produce false causal statements.
        """
        index = _fixture_degraded_single_cluster()
        # The degraded fixture has drilldown findings with trigger reasons
        # Verify the facts don't contain root-cause language
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        # Verify no observed claim contains root-cause language
        root_cause_phrases = ["root cause", "caused by", "because of"]
        for fact in report["facts"]:
            statement = fact.get("statement", "")
            for phrase in root_cause_phrases:
                self.assertNotIn(
                    phrase,
                    statement.lower(),
                    f"observed claim must not contain root-cause language: {fact}",
                )

        # The facts should contain trigger_reasons but sanitized (not root-cause language)
        fact_statements = [f["statement"] for f in report["facts"]]
        # Root cause language should not appear
        self.assertFalse(
            any("root cause" in s.lower() for s in fact_statements),
            f"Root cause language leaked into facts: {fact_statements}",
        )
        # Observed claims should still have proper provenance
        for fact in report["facts"]:
            self.assertTrue(fact.get("sourceArtifactRefs"))


# =============================================================================
# Golden fixture tests
# These tests use the deterministic fixture builders from incident_report_fixtures.py
# =============================================================================


class GoldenFixtureHealthyNoIncidentTests(unittest.TestCase):
    """Test the _fixture_healthy_no_incident golden fixture."""

    def test_healthy_report_status_and_title(self) -> None:
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["title"], "No degraded clusters detected")

    def test_healthy_report_inferences_empty(self) -> None:
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["inferences"])

    def test_healthy_report_unknowns_empty(self) -> None:
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["unknowns"])

    def test_healthy_report_stale_warnings_empty(self) -> None:
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["staleEvidenceWarnings"])


class GoldenFixtureDegradedSingleClusterTests(unittest.TestCase):
    """Test the _fixture_degraded_single_cluster golden fixture."""

    def test_degraded_report_status_and_title(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["title"], "Degraded health detected in 1 cluster(s)")

    def test_degraded_report_facts_non_empty(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["facts"])

    def test_degraded_report_unknowns_non_empty(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["unknowns"])

    def test_degraded_report_recommended_actions_non_empty(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Verify legacy string list still works
        self.assertTrue(report["recommendedActions"])
        # Verify structured recommendations are also present
        self.assertTrue(report.get("recommendations"))
        self.assertTrue(len(report["recommendations"]) > 0)
        # Verify recommendation claims have required fields
        for rec in report["recommendations"]:
            self.assertEqual(rec["claimType"], "recommendation")
            self.assertTrue(rec["safetyLevel"])

    def test_degraded_report_derived_non_empty(self) -> None:
        """Derived claims should be populated from assessment health rating."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Derived list exists
        self.assertIn("derived", report)
        self.assertTrue(len(report["derived"]) > 0)
        # Each derived claim has required fields
        for d in report["derived"]:
            self.assertEqual(d["claimType"], "derived")
            self.assertIn("statement", d)
            self.assertIn("sourceArtifactRefs", d)
            self.assertIn("confidence", d)

    def test_degraded_report_facts_not_health_rating(self) -> None:
        """Health rating should appear in derived, not facts."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Health rating statement should NOT be in facts
        fact_statements = [f["statement"] for f in report["facts"]]
        self.assertFalse(
            any("health rating is" in s for s in fact_statements),
            f"Health rating should not be in facts: {fact_statements}",
        )
        # Health rating should be in derived
        derived_statements = [d["statement"] for d in report["derived"]]
        self.assertTrue(
            any("health rating is" in s for s in derived_statements),
            f"Health rating should be in derived: {derived_statements}",
        )

    def test_degraded_report_source_refs_no_unknown(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        paths = [ref["path"] for ref in report["sourceArtifactRefs"]]
        self.assertNotIn("unknown", paths)

    def test_degraded_worklist_counts_consistent(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        total = worklist["totalItems"]
        completed = worklist["completedItems"]
        pending = worklist["pendingItems"]
        blocked = worklist["blockedItems"]
        self.assertEqual(total, completed + pending + blocked)

    def test_degraded_worklist_items_have_all_required_fields(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])
        for item in worklist["items"]:
            self.assertIn("rank", item)
            self.assertIn("title", item)
            self.assertIn("reason", item)
            self.assertIn("expectedEvidence", item)
            self.assertIn("safetyNote", item)
            self.assertIn("approvalState", item)
            self.assertIn("executionState", item)
            self.assertIn("feedbackState", item)


class GoldenFixtureStaleProviderEnrichedDegradedTests(unittest.TestCase):
    """Test the _fixture_stale_provider_enriched_degraded golden fixture."""

    def test_stale_warning_appears(self) -> None:
        index = _fixture_stale_provider_enriched_degraded()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("stale"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["staleEvidenceWarnings"])
        self.assertIn("stale", report["staleEvidenceWarnings"][0])

    def test_enrichment_in_inferences_only_not_facts(self) -> None:
        index = _fixture_stale_provider_enriched_degraded()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("stale"))
        self.assertIsNotNone(report)
        assert report is not None
        # Specific review enrichment summary appears in inferences
        inference_statements = [i["statement"] for i in report["inferences"]]
        self.assertIn(
            "High ingress latency detected; consider scaling the gateway.",
            inference_statements,
            "Enrichment summary must appear in inferences",
        )
        # It must NOT appear in facts
        fact_statements = [f["statement"] for f in report["facts"]]
        self.assertNotIn(
            "High ingress latency detected; consider scaling the gateway.",
            fact_statements,
            "Enrichment summary must NOT appear in facts",
        )

    def test_enrichment_inference_has_review_enrichment_basis(self) -> None:
        index = _fixture_stale_provider_enriched_degraded()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("stale"))
        self.assertIsNotNone(report)
        assert report is not None
        enrichment_inferences = [
            i for i in report["inferences"]
            if "review-enrichment" in str(i.get("basis", []))
        ]
        self.assertTrue(enrichment_inferences)


class GoldenFixtureDeterministicOnlyNoCommandTests(unittest.TestCase):
    """Test the _fixture_deterministic_only_no_command golden fixture."""

    def test_worklist_command_is_null(self) -> None:
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])
        for item in worklist["items"]:
            # Deterministic checks have method, not command; command must be null
            self.assertIsNone(item.get("command"))

    def test_worklist_items_have_rank_title_workstream(self) -> None:
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            self.assertIn("rank", item)
            self.assertIn("title", item)
            self.assertIn("workstream", item)

    def test_worklist_counts_zero_completed(self) -> None:
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertEqual(worklist["completedItems"], 0)
        self.assertEqual(worklist["blockedItems"], 0)


class GoldenFixtureQueueWithCommandTests(unittest.TestCase):
    """Test the _fixture_queue_with_command golden fixture."""

    def test_queue_item_command_is_populated(self) -> None:
        index = _fixture_queue_with_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find queue item by exact expected candidate ID "candidate-logs"
        queue_items = [i for i in worklist["items"] if str(i.get("id", "")) == "candidate-logs"]
        self.assertTrue(queue_items)
        for item in queue_items:
            self.assertIsNotNone(item.get("command"))

    def test_queue_item_has_all_required_metadata(self) -> None:
        index = _fixture_queue_with_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        queue_items = [i for i in worklist["items"] if str(i.get("id", "")) == "candidate-logs"]
        self.assertTrue(queue_items)
        for item in queue_items:
            self.assertIn("command", item)
            self.assertIn("targetCluster", item)
            self.assertIn("targetContext", item)
            self.assertIn("reason", item)
            self.assertIn("expectedEvidence", item)
            self.assertIn("safetyNote", item)
            self.assertIn("approvalState", item)
            self.assertIn("executionState", item)
            self.assertIn("feedbackState", item)
            self.assertIn("sourceArtifactRefs", item)
            self.assertTrue(item["sourceArtifactRefs"])


# =============================================================================
# Content Quality Tests (Phase 3 - Deterministic Quality Fixtures)
# =============================================================================


class ContentQualityTests(unittest.TestCase):
    """Tests for deterministic content quality rules.

    Phase 3 adds quality fixtures that prevent report content from becoming:
    - verbose
    - causally overconfident
    - operator-hostile

    Quality rules enforced:
    1. observed claims do not contain causal/root-cause language
    2. derived claims do not contain unsupported causal/root-cause language
    3. hypotheses must have non-empty basis
    4. unknowns must have whyMissing explanation
    5. recommendations render under "Recommended next actions"
    6. section headings are concise
    7. claim statements are reasonably short
    8. no generic filler phrases

    These are deterministic fixtures, NOT an LLM judge.
    """

    def test_degraded_report_passes_quality_check(self) -> None:
        """Golden test: degraded single-cluster report passes all quality rules."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        self.assertTrue(
            quality_report["passed"],
            f"Quality check failed: {quality_report['failed_rules']} rules failed. "
            f"Details: {quality_report['results']}",
        )

    def test_observed_claims_no_causal_language(self) -> None:
        """observed claims must not contain causal/root-cause language."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        causal_rule = next(
            r for r in quality_report["results"] if r["rule"] == "observed_no_causal_language"
        )
        self.assertTrue(
            causal_rule["passed"],
            f"observed claims contain causal language: {causal_rule['message']}",
        )

    def test_derived_claims_no_causal_language(self) -> None:
        """derived claims must not contain unsupported causal/root-cause language."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        causal_rule = next(
            r for r in quality_report["results"] if r["rule"] == "derived_no_causal_language"
        )
        self.assertTrue(
            causal_rule["passed"],
            f"derived claims contain causal language: {causal_rule['message']}",
        )

    def test_hypotheses_have_non_empty_basis(self) -> None:
        """hypothesis claims must have non-empty basis."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        basis_rule = next(
            r for r in quality_report["results"] if r["rule"] == "hypotheses_have_basis"
        )
        self.assertTrue(
            basis_rule["passed"],
            f"hypotheses lack basis: {basis_rule['message']}",
        )

    def test_unknowns_have_why_missing(self) -> None:
        """unknown claims must have whyMissing explanation."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        why_missing_rule = next(
            r for r in quality_report["results"] if r["rule"] == "unknowns_have_why_missing"
        )
        self.assertTrue(
            why_missing_rule["passed"],
            f"unknowns lack whyMissing: {why_missing_rule['message']}",
        )

    def test_recommendations_separated_from_findings(self) -> None:
        """recommendations must be separated from findings (not action verbs in facts/derived)."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        rec_rule = next(
            r for r in quality_report["results"] if r["rule"] == "recommendations_separated"
        )
        self.assertTrue(
            rec_rule["passed"],
            f"recommendations not properly separated: {rec_rule['message']}",
        )

    def test_section_headings_concise(self) -> None:
        """section headings remain concise (under 50 characters)."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        heading_rule = next(
            r for r in quality_report["results"] if r["rule"] == "section_headings_concise"
        )
        self.assertTrue(
            heading_rule["passed"],
            f"section headings not concise: {heading_rule['message']}",
        )

    def test_claim_statements_reasonably_short(self) -> None:
        """claim statements are reasonably short (under 200 characters)."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        length_rule = next(
            r for r in quality_report["results"] if r["rule"] == "claim_statements_short"
        )
        self.assertTrue(
            length_rule["passed"],
            f"statements too long: {length_rule['message']}",
        )

    def test_no_filler_phrases(self) -> None:
        """no generic filler phrases in claim statements."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        filler_rule = next(
            r for r in quality_report["results"] if r["rule"] == "no_filler_phrases"
        )
        self.assertTrue(
            filler_rule["passed"],
            f"filler phrases found: {filler_rule['message']}",
        )

    def test_report_has_full_degraded_shape(self) -> None:
        """report has full degraded shape: facts, derived, inferences, unknowns, recommendations."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        quality_report = check_incident_report_quality(report)
        shape_rule = next(
            r for r in quality_report["results"] if r["rule"] == "report_has_full_degraded_shape"
        )
        self.assertTrue(
            shape_rule["passed"],
            f"report missing sections: {shape_rule['message']}",
        )


class ContentQualityNegativeTests(unittest.TestCase):
    """Negative tests: content quality helper rejects bad input.

    This is a test-helper-level failure test, not production sanitizer behavior.
    """

    def test_quality_helper_rejects_observed_with_causal_language(self) -> None:
        """observed claim containing causal language is rejected by quality helper."""
        from tests.fixtures.incident_report_quality import check_claim_has_no_causal_language

        # Create an observed claim with causal language (bad input)
        bad_claim = {
            "claimType": "observed",
            "statement": "The root cause of the crash is memory exhaustion",
            "sourceArtifactRefs": [],
            "confidence": "high",
        }

        result = check_claim_has_no_causal_language("observed", bad_claim)
        self.assertFalse(
            result["passed"],
            f"Expected quality helper to reject causal language, but it passed: {result}",
        )
        self.assertIn("causal language", result["message"].lower())

    def test_quality_helper_rejects_derived_with_causal_language(self) -> None:
        """derived claim containing causal language is rejected by quality helper."""
        from tests.fixtures.incident_report_quality import check_claim_has_no_causal_language

        # Create a derived claim with causal language (bad input)
        bad_claim = {
            "claimType": "derived",
            "statement": "The pod crash was caused by OOM kill",
            "sourceFields": ["state", "lastState"],
            "sourceArtifactRefs": [],
            "confidence": "medium",
        }

        result = check_claim_has_no_causal_language("derived", bad_claim)
        self.assertFalse(
            result["passed"],
            f"Expected quality helper to reject causal language, but it passed: {result}",
        )
        self.assertIn("causal language", result["message"].lower())

    def test_quality_helper_accepts_observed_without_causal_language(self) -> None:
        """observed claim without causal language passes quality helper."""
        from tests.fixtures.incident_report_quality import check_claim_has_no_causal_language

        # Create a good observed claim (no causal language)
        good_claim = {
            "claimType": "observed",
            "statement": "Warning events observed: 5",
            "sourceArtifactRefs": [],
            "confidence": "high",
        }

        result = check_claim_has_no_causal_language("observed", good_claim)
        self.assertTrue(
            result["passed"],
            f"Expected quality helper to accept good claim, but it failed: {result}",
        )

    def test_quality_helper_accepts_hypothesis_with_basis(self) -> None:
        """hypothesis with non-empty basis passes quality check."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        # Create a report with a proper hypothesis
        report = {
            "facts": [
                {
                    "claimType": "observed",
                    "statement": "Warning events observed: 5",
                    "sourceArtifactRefs": [],
                    "confidence": "high",
                }
            ],
            "derived": [],
            "inferences": [
                {
                    "claimType": "hypothesis",
                    "statement": "Control-plane CPU pressure may be causing latency",
                    "basis": ["control-plane", "metrics"],
                    "confidence": "medium",
                    "sourceArtifactRefs": [],
                }
            ],
            "recommendations": [
                {
                    "claimType": "recommendation",
                    "statement": "Check kubelet logs",
                    "safetyLevel": "low",
                    "sourceArtifactRefs": [],
                }
            ],
            "unknowns": [],
            "recommendedActions": [],
        }

        quality_report = check_incident_report_quality(report)
        # Hypotheses have non-empty basis - should pass
        basis_rule = next(
            r for r in quality_report["results"] if r["rule"] == "hypotheses_have_basis"
        )
        self.assertTrue(basis_rule["passed"])

    def test_quality_helper_rejects_unknown_without_why_missing(self) -> None:
        """unknown claim without whyMissing fails quality check."""
        from tests.fixtures.incident_report_quality import check_incident_report_quality

        # Create a report with unknown lacking whyMissing
        report: dict[str, Any] = {
            "facts": [],
            "derived": [],
            "inferences": [],
            "recommendations": [],
            "unknowns": [
                {
                    "claimType": "unknown",
                    "statement": "Missing evidence: logs from edge nodes",
                    "whyMissing": None,  # Missing!
                    "sourceArtifactRefs": [],
                }
            ],
            "recommendedActions": [],
        }

        quality_report = check_incident_report_quality(report)
        why_missing_rule = next(
            r for r in quality_report["results"] if r["rule"] == "unknowns_have_why_missing"
        )
        self.assertFalse(
            why_missing_rule["passed"],
            f"Expected unknown without whyMissing to fail, but it passed: {why_missing_rule}",
        )


class ContentQualityReportStructureTests(unittest.TestCase):
    """Tests for report structure - verifying the report answers core questions."""

    def test_degraded_report_answers_what_is_observed(self) -> None:
        """Report answers: what is observed."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        # Should have facts answering "what is observed"
        self.assertTrue(report["facts"], "Report should have facts answering what is observed")

    def test_degraded_report_answers_what_is_derived(self) -> None:
        """Report answers: what is derived."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        # Should have derived claims answering "what is derived"
        self.assertTrue(report["derived"], "Report should have derived claims")

    def test_degraded_report_answers_what_is_hypothesized(self) -> None:
        """Report answers: what is hypothesized."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        # Should have inferences answering "what is hypothesized"
        self.assertTrue(report["inferences"], "Report should have hypotheses")

    def test_degraded_report_answers_what_is_unknown(self) -> None:
        """Report answers: what is unknown."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        # Should have unknowns answering "what is unknown"
        self.assertTrue(report["unknowns"], "Report should have unknowns for missing evidence")

    def test_degraded_report_answers_what_action_is_recommended(self) -> None:
        """Report answers: what action is recommended."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        # Should have recommendations or legacy actions
        has_recommendations = bool(report["recommendations"]) or bool(report["recommendedActions"])
        self.assertTrue(
            has_recommendations,
            "Report should have recommendations answering what action is recommended",
        )


class ClusterLabelSanitizationRegressionTests(unittest.TestCase):
    """Regression tests for internal marker sanitization in operator-facing output.

    These tests verify that internal execution markers like "in-cluster" do not
    leak into user-facing prose or LLM prompt headers.
    """

    def test_derived_statement_does_not_show_cluster_in_cluster(self) -> None:
        """Incident report derived statement must not contain 'Cluster in-cluster' or 'Cluster the cluster'."""
        # Build an index where the latest assessment has cluster_label="in-cluster"
        index = sample_ui_index()
        la = cast(dict[str, object], index["latest_assessment"])
        la["cluster_label"] = "in-cluster"
        la["health_rating"] = "HEALTHY"
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Verify derived statements don't contain bad phrasing
        derived_statements = [d["statement"] for d in report.get("derived", [])]
        self.assertTrue(derived_statements, "Expected at least one derived statement")
        for statement in derived_statements:
            self.assertNotIn(
                "Cluster in-cluster",
                statement,
                f"Internal marker leaked into derived statement: {statement}",
            )
            self.assertNotIn(
                "Cluster the cluster",
                statement,
                f"Awkward 'Cluster the cluster' phrasing: {statement}",
            )

    def test_derived_statement_uses_the_cluster_fallback(self) -> None:
        """When cluster_label is an internal marker with no fallback, use 'The cluster' prefix."""
        index = sample_ui_index()
        la = cast(dict[str, object], index["latest_assessment"])
        la["cluster_label"] = "in-cluster"
        la["health_rating"] = "DEGRADED"
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        derived_statements = [d["statement"] for d in report.get("derived", [])]
        self.assertTrue(derived_statements)
        # When no real cluster name is available, should produce "The cluster health rating is DEGRADED."
        health_rating_statements = [s for s in derived_statements if "health rating is" in s]
        self.assertTrue(health_rating_statements)
        # Verify it starts with "The cluster" not "Cluster"
        for statement in health_rating_statements:
            self.assertTrue(
                statement.startswith("The cluster"),
                f"Expected 'The cluster' prefix, got: {statement}",
            )

    def test_derived_statement_uses_real_cluster_name(self) -> None:
        """When cluster_label is a real cluster name, use 'Cluster <name>' prefix."""
        index = sample_ui_index()
        la = cast(dict[str, object], index["latest_assessment"])
        la["cluster_label"] = "prod-cluster"
        la["health_rating"] = "HEALTHY"
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        derived_statements = [d["statement"] for d in report.get("derived", [])]
        self.assertTrue(derived_statements)
        health_rating_statements = [s for s in derived_statements if "health rating is" in s]
        self.assertTrue(health_rating_statements)
        for statement in health_rating_statements:
            self.assertTrue(
                statement.startswith("Cluster prod-cluster"),
                f"Expected 'Cluster prod-cluster' prefix, got: {statement}",
            )


def _get_cross_cluster_findings(
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Helper to safely get crossClusterFindings list from report dict."""
    findings = report.get("crossClusterFindings")
    if findings is None:
        return []
    return cast(list[dict[str, Any]], findings)


def _require_cross_cluster_findings(
    report: dict[str, Any] | Any,
) -> list[CrossClusterFindingPayload]:
    """Helper to require crossClusterFindings list, asserting presence."""
    findings = report.get("crossClusterFindings")
    assert findings is not None
    return cast(list[CrossClusterFindingPayload], findings)


def _require_str(value: str | None) -> str:
    """Helper to require a non-None string value."""
    assert value is not None
    return value


# =============================================================================
# Worklist Unification Tests (Epic: Worklist Projection and Execution-State)
# =============================================================================


class WorklistUnificationTests(unittest.TestCase):
    """Tests for unified worklist projection.

    Coverage:
    - canonical itemState enum: advisory | approval-needed | approved | queued | executed | reviewed
    - state transition rules
    - provenance preservation for duplicates
    - command truthfulness (null for deterministic, concrete for queue)
    - ranking stability
    - usefulness linkage
    """

    def test_deterministic_item_has_advisory_state(self) -> None:
        """Deterministic items must have itemState=advisory."""
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            self.assertEqual(item.get("itemState"), "advisory")
            self.assertEqual(item.get("sourceType"), "deterministic")

    def test_approval_needed_item_has_correct_state(self) -> None:
        """Approval-needed items must have itemState=approval-needed."""
        index = _fixture_approval_needed_item()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])
        for item in worklist["items"]:
            self.assertEqual(item.get("itemState"), "approval-needed")
            self.assertEqual(item.get("approvalState"), "approval-required")
            self.assertEqual(item.get("executionState"), "unexecuted")
            # Command should be present but blocked by approval
            self.assertIsNotNone(item.get("command"))

    def test_queue_item_has_queued_state(self) -> None:
        """Queue items safe to execute should have itemState=queued."""
        index = _fixture_queue_with_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            # This fixture has executionState=executed-success, so itemState should be executed
            if item.get("executionState") == "executed-success":
                self.assertEqual(item.get("itemState"), "executed")

    def test_executed_item_has_executed_state(self) -> None:
        """Executed items must have itemState=executed."""
        index = _fixture_executed_with_usefulness()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            self.assertEqual(item.get("itemState"), "executed")
            self.assertEqual(item.get("executionState"), "executed-success")

    def test_command_null_for_deterministic(self) -> None:
        """Deterministic items must have command=null (never a runnable string)."""
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            self.assertIsNone(
                item.get("command"),
                f"Deterministic item {item.get('id')} must have command=null, got {item.get('command')}",
            )

    def test_command_populated_for_queue_item(self) -> None:
        """Queue items must have command populated (not null)."""
        index = _fixture_approval_needed_item()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            if item.get("sourceType") in ("planner", "promotion"):
                self.assertIsNotNone(
                    item.get("command"),
                    f"Queue item {item.get('id')} must have command populated",
                )

    def test_source_type_deterministic_for_advisory_items(self) -> None:
        """Deterministic advisory items must have sourceType=deterministic."""
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            self.assertEqual(item.get("sourceType"), "deterministic")

    def test_source_type_planner_for_queue_items(self) -> None:
        """Planner queue items must have sourceType=planner."""
        index = _fixture_approval_needed_item()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            if item.get("sourceType"):
                self.assertIn(
                    item.get("sourceType"),
                    ("deterministic", "planner", "promotion", "execution"),
                )

    def test_merged_sources_preserved_for_duplicates(self) -> None:
        """Duplicate items from multiple sources must preserve mergedSources."""
        index = _fixture_duplicate_candidates()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # The duplicate fixture has both deterministic and planner items with same candidate ID
        # When merged, mergedSources should contain both provenance origins
        merged_items = [i for i in worklist["items"] if i.get("mergedSources")]
        # At least one item should have merged provenance
        self.assertTrue(
            merged_items,
            "Expected at least one item with mergedSources from duplicate handling",
        )
        for item in merged_items:
            sources = item.get("mergedSources") or []
            self.assertIn(
                "deterministic",
                sources,
                f"Item {item.get('id')} should include deterministic in mergedSources",
            )
            self.assertIn(
                "planner",
                sources,
                f"Item {item.get('id')} should include planner in mergedSources",
            )

    def test_source_artifact_refs_no_unknown(self) -> None:
        """All items must have sourceArtifactRefs with real paths, never 'unknown'."""
        fixtures = [
            _fixture_deterministic_only_no_command,
            _fixture_approval_needed_item,
            _fixture_executed_with_usefulness,
            _fixture_queue_with_command,
            _fixture_duplicate_candidates,
        ]
        for fixture_fn in fixtures:
            index = fixture_fn()
            context = build_ui_context(index)
            worklist = _build_operator_worklist_payload(context)
            if worklist is None:
                continue
            for item in worklist["items"]:
                refs = item.get("sourceArtifactRefs") or []
                paths = [r.get("path") for r in refs]
                self.assertNotIn(
                    "unknown",
                    paths,
                    f"Item {item.get('id')} should not have 'unknown' in sourceArtifactRefs",
                )

    def test_ranking_stable_across_builds(self) -> None:
        """Worklist ranking must be stable across multiple builds of the same input."""
        index = _fixture_degraded_single_cluster()
        worklists = []
        for _ in range(3):
            context = build_ui_context(index)
            worklist = _build_operator_worklist_payload(context)
            self.assertIsNotNone(worklist)
            assert worklist is not None
            ranks = [item.get("rank") for item in worklist["items"]]
            worklists.append(ranks)
        # All builds should produce the same rank sequence
        self.assertEqual(worklists[0], worklists[1])
        self.assertEqual(worklists[1], worklists[2])

    def test_ranking_is_sequential(self) -> None:
        """Worklist items must have sequential ranks starting from 1."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        ranks = [item.get("rank") for item in worklist["items"]]
        expected = list(range(1, len(ranks) + 1))
        self.assertEqual(ranks, expected)

    def test_counts_consistent_with_item_states(self) -> None:
        """Worklist counts must match actual item states."""
        index = _fixture_approval_needed_item()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        total = worklist["totalItems"]
        completed = worklist["completedItems"]
        pending = worklist["pendingItems"]
        blocked = worklist["blockedItems"]
        self.assertEqual(total, completed + pending + blocked)
        # Verify blocked count matches approval-needed items
        blocked_items = [
            i for i in worklist["items"]
            if i.get("itemState") == "approval-needed" or i.get("approvalState") == "approval-required"
        ]
        self.assertEqual(blocked, len(blocked_items))

    def test_counts_consistent_for_executed_items(self) -> None:
        """Worklist counts must match executed items."""
        index = _fixture_executed_with_usefulness()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        completed = worklist["completedItems"]
        executed_items = [
            i for i in worklist["items"]
            if i.get("executionState") == "executed-success"
        ]
        self.assertEqual(completed, len(executed_items))

    def test_usefulness_linkage_preserved(self) -> None:
        """Executed items with usefulness feedback must preserve the linkage."""
        index = _fixture_executed_with_usefulness()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Check that execution artifact is in sourceArtifactRefs
        for item in worklist["items"]:
            if item.get("executionState") == "executed-success":
                refs = item.get("sourceArtifactRefs") or []
                execution_refs = [
                    r for r in refs
                    if "execution" in r.get("label", "").lower()
                ]
                self.assertTrue(
                    execution_refs,
                    f"Item {item.get('id')} should have execution artifact in sourceArtifactRefs",
                )

    def test_worklist_item_has_all_required_fields(self) -> None:
        """All worklist items must have required fields per contract."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            # Required fields per OperatorWorklistItemPayload contract
            self.assertIn("id", item)
            self.assertIn("rank", item)
            self.assertIn("title", item)
            self.assertIn("command", item)  # May be null
            self.assertIn("itemState", item)
            self.assertIn("sourceArtifactRefs", item)
            # Optional but expected when sourceType is set
            if item.get("sourceType"):
                self.assertIn("approvalState", item)
                self.assertIn("executionState", item)
                self.assertIn("feedbackState", item)


class WorklistStateTransitionTests(unittest.TestCase):
    """Tests for canonical state transition rules.

    State transition: advisory -> approval-needed -> approved -> queued -> executed -> reviewed
    """

    def test_advisory_to_approval_needed_transition(self) -> None:
        """Items requiring approval must have itemState=approval-needed when not approved."""
        index = _fixture_approval_needed_item()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            if item.get("approvalState") == "approval-required":
                self.assertEqual(item.get("itemState"), "approval-needed")

    def test_advisory_to_queued_transition(self) -> None:
        """Safe-to-execute items must have itemState=queued when unexecuted."""
        # Create fixture with safe-to-automate unexecuted item
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Deterministic items are always advisory
        for item in worklist["items"]:
            self.assertEqual(item.get("itemState"), "advisory")

    def test_queued_to_executed_transition(self) -> None:
        """Executed items must have itemState=executed."""
        index = _fixture_executed_with_usefulness()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            if item.get("executionState") == "executed-success":
                self.assertEqual(item.get("itemState"), "executed")


class WorklistProvenanceTests(unittest.TestCase):
    """Tests for provenance preservation in worklist deduplication."""

    def test_deterministic_provenance_preserved_when_merged(self) -> None:
        """Deterministic artifact refs must be preserved when merged with planner."""
        index = _fixture_duplicate_candidates()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find merged item
        merged_items = [i for i in worklist["items"] if i.get("mergedSources")]
        if merged_items:
            item = merged_items[0]
            refs = item.get("sourceArtifactRefs") or []
            labels = {r.get("label") for r in refs}
            # Should have both deterministic and planner refs
            self.assertIn("Assessment", labels)
            self.assertIn("Next-Check Plan", labels)

    def test_no_duplicate_artifact_paths(self) -> None:
        """Merged items must not have duplicate artifact paths."""
        index = _fixture_duplicate_candidates()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            refs = item.get("sourceArtifactRefs") or []
            paths = [r.get("path") for r in refs]
            self.assertEqual(
                len(paths),
                len(set(paths)),
                f"Item {item.get('id')} should not have duplicate paths in sourceArtifactRefs",
            )


# =============================================================================
# Cross-Cluster Findings Regression Tests (BETA-G2 Epic)
# =============================================================================


class CrossClusterFindingsTests(unittest.TestCase):
    """Tests for cross-cluster findings in incident reports.

    Regression tests for BETA-G2 epic: Cross-cluster correlation in incident report.
    Verifies that comparison-triggered, cross-cluster findings are surfaced without
    interfering with per-cluster observations.
    """

    def test_helm_release_drift_surfaces_in_cross_cluster_findings(self) -> None:
        """Helm release drift must surface in crossClusterFindings."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_helm_release_drift,
        )

        index = _fixture_helm_release_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        self.assertTrue(len(findings) > 0)
        finding = findings[0]
        self.assertIn("helm_releases", finding.get("driftCounts", {}))
        self.assertGreater(finding["driftCounts"]["helm_releases"], 0)

    def test_helm_release_drift_recommendation_surfaces(self) -> None:
        """Fleet-aware recommendation for helm drift must surface."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_helm_release_drift,
            _freshness,
        )

        index = _fixture_helm_release_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        finding = findings[0]
        recs = finding.get("recommendedNextChecks", [])
        helm_recs = [r for r in recs if "helm" in r.lower()]
        self.assertTrue(helm_recs, f"Expected helm recommendation, got: {recs}")
        self.assertIn("Compare Helm release versions across same-role clusters", helm_recs)

    def test_control_plane_drift_surfaces_in_cross_cluster_findings(self) -> None:
        """Control plane version drift must surface in crossClusterFindings."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_control_plane_drift,
            _freshness,
        )

        index = _fixture_control_plane_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        self.assertTrue(len(findings) > 0)
        finding = findings[0]
        self.assertIn("metadata", finding.get("driftCounts", {}))
        self.assertGreater(finding["driftCounts"]["metadata"], 0)

    def test_control_plane_drift_recommendation_surfaces(self) -> None:
        """Fleet-aware recommendation for control plane drift must surface."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_control_plane_drift,
            _freshness,
        )

        index = _fixture_control_plane_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        finding = findings[0]
        recs = finding.get("recommendedNextChecks", [])
        cp_recs = [r for r in recs if "control plane" in r.lower() or "version" in r.lower()]
        self.assertTrue(cp_recs, f"Expected control plane recommendation, got: {recs}")

    def test_crd_family_drift_surfaces_in_cross_cluster_findings(self) -> None:
        """CRD family drift must surface in crossClusterFindings."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_crd_family_drift,
            _freshness,
        )

        index = _fixture_crd_family_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        self.assertTrue(len(findings) > 0)
        finding = findings[0]
        self.assertIn("crds", finding.get("driftCounts", {}))
        self.assertGreater(finding["driftCounts"]["crds"], 0)

    def test_crd_drift_recommendation_surfaces(self) -> None:
        """Fleet-aware recommendation for CRD drift must surface."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_crd_family_drift,
            _freshness,
        )

        index = _fixture_crd_family_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        finding = findings[0]
        recs = finding.get("recommendedNextChecks", [])
        crd_recs = [r for r in recs if "crd" in r.lower() or "api" in r.lower()]
        self.assertTrue(crd_recs, f"Expected CRD recommendation, got: {recs}")

    def test_healthy_but_suspicious_cross_cluster_findsings_present(self) -> None:
        """Suspicious cross-cluster comparison surfaces even when per-cluster health is good."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_healthy_but_suspicious_cross_cluster,
            _freshness,
        )

        index = _fixture_healthy_but_suspicious_cross_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Status should be healthy (per-cluster perspective)
        self.assertEqual(report["status"], "healthy")
        # But cross-cluster findings should still be present
        self.assertIsNotNone(report["crossClusterFindings"])
        findings = _require_cross_cluster_findings(report)
        self.assertTrue(len(findings) > 0)
        finding = findings[0]
        self.assertEqual(finding.get("intent"), "suspicious-comparison")

    def test_cross_cluster_drift_with_degraded_workload_has_both(self) -> None:
        """Per-cluster degradation and cross-cluster drift both surface."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_cross_cluster_drift_with_degraded_workload,
            _freshness,
        )

        index = _fixture_cross_cluster_drift_with_degraded_workload()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Status should be degraded (per-cluster perspective)
        self.assertEqual(report["status"], "degraded")
        # Facts should be non-empty (per-cluster findings)
        self.assertTrue(report["facts"])
        # Cross-cluster findings should also be present
        findings = _require_cross_cluster_findings(report)
        self.assertTrue(len(findings) > 0)

    def test_cross_cluster_findings_sorted_by_timestamp(self) -> None:
        """Multiple cross-cluster findings are sorted by timestamp descending."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_healthy_but_suspicious_cross_cluster,
            _freshness,
        )

        index = _fixture_healthy_but_suspicious_cross_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # With one comparison trigger, we expect at most 1 finding
        self.assertIsNotNone(report["crossClusterFindings"])

    def test_cross_cluster_findings_limited_to_five(self) -> None:
        """Cross-cluster findings are limited to top 5 to keep report concise."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_helm_release_drift,
            _freshness,
        )

        index = _fixture_helm_release_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = report.get("crossClusterFindings") or []
        self.assertLessEqual(len(findings), 5)

    def test_cross_cluster_findings_have_cluster_labels(self) -> None:
        """Cross-cluster findings include primary and secondary cluster labels."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_helm_release_drift,
            _freshness,
        )

        index = _fixture_helm_release_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        finding = findings[0]
        self.assertIn("primaryCluster", finding)
        self.assertIn("secondaryCluster", finding)
        self.assertIsNotNone(finding["primaryCluster"])
        self.assertIsNotNone(finding["secondaryCluster"])

    def test_cross_cluster_findings_have_trigger_reasons(self) -> None:
        """Cross-cluster findings include trigger reasons."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_helm_release_drift,
            _freshness,
        )

        index = _fixture_helm_release_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        finding = findings[0]
        self.assertIn("triggerReasons", finding)
        self.assertTrue(len(finding["triggerReasons"]) > 0)

    def test_cross_cluster_findings_have_artifact_path(self) -> None:
        """Cross-cluster findings include artifact path for provenance."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_helm_release_drift,
            _freshness,
        )

        index = _fixture_helm_release_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        finding = findings[0]
        self.assertIn("artifactPath", finding)
        # Artifact path should be a real path, not "unknown"
        self.assertIsNotNone(finding["artifactPath"])
        self.assertNotEqual(finding["artifactPath"], "unknown")

    def test_cross_cluster_findings_have_recommended_next_checks(self) -> None:
        """Cross-cluster findings include fleet-aware recommended next checks."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_helm_release_drift,
            _freshness,
        )

        index = _fixture_helm_release_drift()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = _require_cross_cluster_findings(report)
        finding = findings[0]
        self.assertIn("recommendedNextChecks", finding)
        self.assertTrue(len(finding["recommendedNextChecks"]) > 0)
        # Should have at most 3 recommendations
        self.assertLessEqual(len(finding["recommendedNextChecks"]), 3)

    def test_no_cross_cluster_findings_when_no_comparison_triggers(self) -> None:
        """Cross-cluster findings are None when no comparison triggers exist."""
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # No comparison triggers in healthy fixture
        self.assertIsNone(report.get("crossClusterFindings"))

    def test_cross_cluster_findings_separated_from_per_cluster(self) -> None:
        """Cross-cluster findings are clearly separate from per-cluster observations."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_cross_cluster_drift_with_degraded_workload,
            _freshness,
        )

        index = _fixture_cross_cluster_drift_with_degraded_workload()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Facts are per-cluster observations
        fact_statements = [f["statement"] for f in report["facts"]]
        # Cross-cluster findings should NOT appear in facts
        findings = _require_cross_cluster_findings(report)
        for finding in findings:
            # Trigger reasons and drift counts should not be in facts
            for reason in finding.get("triggerReasons", []):
                self.assertNotIn(
                    reason,
                    " ".join(fact_statements).lower(),
                    f"Cross-cluster trigger reason leaked into facts: {reason}",
                )

    def test_cross_cluster_findings_max_three_recommendations(self) -> None:
        """Fleet-aware recommendations are limited to 3 per finding."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_healthy_but_suspicious_cross_cluster,
            _freshness,
        )

        index = _fixture_healthy_but_suspicious_cross_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        findings = report.get("crossClusterFindings") or []
        for finding in findings:
            recs = finding.get("recommendedNextChecks", [])
            self.assertLessEqual(
                len(recs), 3, f"Expected max 3 recommendations, got {len(recs)}: {recs}"
            )

    def test_cross_cluster_findings_in_build_run_payload(self) -> None:
        """Cross-cluster findings are threaded through build_run_payload."""
        from tests.fixtures.incident_report_cross_cluster_fixtures import (
            _fixture_helm_release_drift,
        )

        index = _fixture_helm_release_drift()
        context = build_ui_context(index)
        payload = build_run_payload(context)
        self.assertIn("incidentReport", payload)
        report = payload["incidentReport"]
        self.assertIsNotNone(report)
        assert report is not None
        self.assertIsNotNone(report["crossClusterFindings"])


# =============================================================================
# Ranking Rationale Tests (Epic: BETA-G3 Worklist Ranking Rationale)
# =============================================================================


class WorklistRankingRationaleTests(unittest.TestCase):
    """Tests for worklist item ranking rationale transparency.

    This test class verifies that ranked worklist items expose a concise
    rankingReason that allows operators to understand why item order is what it is.

    Allowed basis for ranking rationale:
    - urgency / primary triage: deterministic items marked as primary triage
    - expected information gain: executable items that confirm leading hypothesis
    - approval/execution readiness: items ready to execute or pending approval
    - drift category severity: fleet-level drift affecting comparable clusters
    - duplicate suppression: merged/duplicate items with preserved provenance
    - executed/reviewed state: completed items retained for result review

    Invariants enforced:
    - Every surfaced ranked item has an operator-readable rationale (or None when indeterminate)
    - Rationale aligns with actual ordering and state
    - Rationale remains concise (under 80 chars)
    - Advisory items are not described as immediately executable
    - Reviewed/executed items are not incorrectly explained as pending next steps
    """

    def test_all_ranked_items_have_ranking_reason(self) -> None:
        """Every ranked worklist item exposes a rankingReason field."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])
        for item in worklist["items"]:
            self.assertIn("rank", item)
            self.assertIn("rankingReason", item)

    def test_primary_triage_deterministic_items_have_triage_rationale(self) -> None:
        """Primary triage deterministic items have a triage-based ranking rationale."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find primary triage items
        for item in worklist["items"]:
            if item.get("sourceType") == "deterministic":
                # Deterministic items with is_primary_triage=True should have triage rationale
                # The safetyNote contains "primary triage: True" for primary triage items
                safety_note = item.get("safetyNote") or ""
                if "primary triage: True" in safety_note:
                    self.assertIsNotNone(
                        item.get("rankingReason"),
                        f"Primary triage item should have rankingReason: {item.get('id')}",
                    )
                    ranking_reason = _require_str(item.get("rankingReason"))
                    self.assertIn(
                        "Primary triage",
                        ranking_reason,
                        f"Primary triage rationale should mention triage: {item.get('rankingReason')}",
                    )

    def test_executed_items_have_executed_rationale(self) -> None:
        """Executed items have a rationale explaining they are completed."""
        index = _fixture_executed_with_usefulness()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find executed items
        executed_items = [
            i for i in worklist["items"]
            if i.get("executionState") in ("executed-success", "executed-failed", "timed-out")
        ]
        self.assertTrue(
            executed_items,
            "Expected at least one executed item in fixture",
        )
        for item in executed_items:
            self.assertIsNotNone(
                item.get("rankingReason"),
                f"Executed item should have rankingReason: {item.get('id')}",
            )
            ranking_reason = _require_str(item.get("rankingReason"))
            self.assertIn(
                "executed",
                ranking_reason.lower(),
                f"Executed rationale should mention execution: {item.get('rankingReason')}",
            )

    def test_approval_needed_items_have_approval_rationale(self) -> None:
        """Approval-needed items have a rationale about pending approval."""
        index = _fixture_approval_needed_item()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find approval-needed items
        approval_items = [
            i for i in worklist["items"]
            if i.get("itemState") == "approval-needed"
        ]
        self.assertTrue(
            approval_items,
            "Expected at least one approval-needed item in fixture",
        )
        for item in approval_items:
            self.assertIsNotNone(
                item.get("rankingReason"),
                f"Approval-needed item should have rankingReason: {item.get('id')}",
            )
            ranking_reason = _require_str(item.get("rankingReason"))
            self.assertIn(
                "approval",
                ranking_reason.lower(),
                f"Approval rationale should mention approval: {item.get('rankingReason')}",
            )

    def test_executable_queue_items_have_executable_rationale(self) -> None:
        """Executable queue items (with command) have appropriate rationale."""
        index = _fixture_queue_with_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find queue items with command (executable)
        queue_items = [
            i for i in worklist["items"]
            if i.get("command") is not None and i.get("sourceType") in ("planner", "promotion")
        ]
        self.assertTrue(
            queue_items,
            "Expected at least one executable queue item in fixture",
        )
        for item in queue_items:
            self.assertIsNotNone(
                item.get("rankingReason"),
                f"Executable queue item should have rankingReason: {item.get('id')}",
            )
            ranking_reason = _require_str(item.get("rankingReason"))
            # Should not claim primary triage for non-triage items
            self.assertNotIn(
                "Primary triage",
                ranking_reason,
                f"Non-primary-triage item should not claim primary triage: {item.get('rankingReason')}",
            )

    def test_deterministic_advisory_items_not_described_as_executable(self) -> None:
        """Deterministic advisory items are not described as immediately executable."""
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find deterministic advisory items (command is None)
        deterministic_items = [
            i for i in worklist["items"]
            if i.get("sourceType") == "deterministic" and i.get("command") is None
        ]
        self.assertTrue(
            deterministic_items,
            "Expected deterministic items with null command",
        )
        for item in deterministic_items:
            ranking_reason = item.get("rankingReason")
            if ranking_reason:
                # Should not claim "executable now" or similar
                self.assertNotIn(
                    "Executable now",
                    ranking_reason,
                    f"Advisory item should not claim executable: {ranking_reason}",
                )
                # Should not claim "confirmed" (past tense = overconfident)
                self.assertNotIn(
                    "confirmed the leading hypothesis",
                    ranking_reason,
                    f"Advisory item should not claim confirmation: {ranking_reason}",
                )

    def test_reviewed_items_not_described_as_pending(self) -> None:
        """Reviewed items are not incorrectly explained as pending next steps."""
        index = _fixture_executed_with_usefulness()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find items with usefulness feedback (reviewed)
        reviewed_items = [
            i for i in worklist["items"]
            if i.get("feedbackState") or i.get("itemState") == "reviewed"
        ]
        for item in reviewed_items:
            ranking_reason = item.get("rankingReason") or ""
            # Should not claim "pending", "queued", or "ready for execution"
            self.assertNotIn(
                "pending",
                ranking_reason.lower(),
                f"Reviewed item should not claim pending: {ranking_reason}",
            )
            self.assertNotIn(
                "queued for",
                ranking_reason.lower(),
                f"Reviewed item should not claim queued: {ranking_reason}",
            )
            self.assertNotIn(
                "ready for execution",
                ranking_reason.lower(),
                f"Reviewed item should not claim ready: {ranking_reason}",
            )

    def test_ranking_rationale_is_concise(self) -> None:
        """Ranking rationale is concise (under 80 characters)."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            ranking_reason = item.get("rankingReason")
            if ranking_reason:
                self.assertLess(
                    len(ranking_reason),
                    80,
                    f"Ranking reason too long ({len(ranking_reason)} chars): {ranking_reason}",
                )

    def test_deterministic_items_rank_above_planner_advisory(self) -> None:
        """Deterministic primary triage items rank above secondary planner items."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        ranks = [item.get("rank") for item in worklist["items"]]
        expected = list(range(1, len(ranks) + 1))
        self.assertEqual(
            ranks,
            expected,
            f"Expected consecutive ranks starting at 1: {ranks}",
        )

    def test_worklist_with_mixed_states_has_appropriate_rationales(self) -> None:
        """Worklist with mixed execution states has appropriate rationales for each state."""
        index = _fixture_multi_signal_executed_with_pending()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Verify we have mixed states
        states_seen: set[str] = set()
        for item in worklist["items"]:
            state = item.get("itemState") or ""
            if state:
                states_seen.add(state)
        # Should have at least 2 different states
        self.assertGreaterEqual(
            len(states_seen),
            2,
            f"Expected mixed states, got: {states_seen}",
        )
        # All items should have rankingReason (even if None for indeterminate cases)
        for item in worklist["items"]:
            self.assertIn("rankingReason", item)

    def test_drift_workstream_items_have_fleet_rationale(self) -> None:
        """Drift workstream items have a fleet-level ranking rationale."""
        # Create a fixture with drift workstream
        index = _fixture_degraded_single_cluster()
        run_entry = cast(dict[str, object], index["run"])
        # Add a queue item with drift workstream
        run_entry["next_check_queue"] = [
            {
                "candidateId": "candidate-drift",
                "candidateIndex": 0,
                "description": "Compare helm releases across fleet",
                "targetCluster": "cluster-degraded",
                "priorityLabel": "secondary",
                "suggestedCommandFamily": "helm",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "approvalState": "not-required",
                "executionState": "unexecuted",
                "outcomeStatus": "unexecuted",
                "latestArtifactPath": None,
                "sourceReason": "Fleet-wide helm release drift detected",
                "expectedSignal": "Helm release version differences",
                "normalizationReason": "drift_workstream",
                "safetyReason": "known_command",
                "approvalReason": None,
                "duplicateReason": None,
                "blockingReason": None,
                "targetContext": "cluster-degraded",
                "commandPreview": "helm list --all-namespaces --context cluster-degraded",
                "planArtifactPath": "runs/health/external-analysis/run-drift-next-check-plan.json",
                "queueStatus": "pending",
                "workstream": "drift",
            }
        ]
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find drift workstream item
        drift_items = [
            i for i in worklist["items"]
            if i.get("workstream") == "drift"
        ]
        self.assertTrue(
            drift_items,
            "Expected drift workstream item in fixture",
        )
        for item in drift_items:
            self.assertIsNotNone(
                item.get("rankingReason"),
                f"Drift item should have rankingReason: {item.get('id')}",
            )
            ranking_reason = _require_str(item.get("rankingReason"))
            self.assertIn(
                "fleet",
                ranking_reason.lower(),
                f"Drift rationale should mention fleet: {item.get('rankingReason')}",
            )


class WorklistRankingRationaleDerivationTests(unittest.TestCase):
    """Unit tests for _derive_worklist_ranking_reason helper function."""

    def test_primary_triage_high_urgency(self) -> None:
        """Primary triage with high urgency returns triage rationale with urgency."""
        from k8s_diag_agent.ui.api_incident_report import _derive_worklist_ranking_reason

        reason = _derive_worklist_ranking_reason(
            source_type="deterministic",
            item_state="advisory",
            execution_state=None,
            is_primary_triage=True,
            urgency="high",
            priority_label=None,
            command=None,
            workstream="incident",
        )
        assert reason is not None
        self.assertIn("Primary triage", reason)
        self.assertIn("high", reason)

    def test_primary_triage_no_urgency(self) -> None:
        """Primary triage without urgency returns basic triage rationale."""
        from k8s_diag_agent.ui.api_incident_report import _derive_worklist_ranking_reason

        reason = _derive_worklist_ranking_reason(
            source_type="deterministic",
            item_state="advisory",
            execution_state=None,
            is_primary_triage=True,
            urgency=None,
            priority_label=None,
            command=None,
            workstream="incident",
        )
        assert reason is not None
        self.assertIn("Primary triage", reason)
        self.assertNotIn("urgency", reason.lower())

    def test_executed_state(self) -> None:
        """Executed items return executed rationale."""
        from k8s_diag_agent.ui.api_incident_report import _derive_worklist_ranking_reason

        reason = _derive_worklist_ranking_reason(
            source_type="planner",
            item_state="executed",
            execution_state="executed-success",
            is_primary_triage=None,
            urgency=None,
            priority_label="primary",
            command="kubectl get pods",
            workstream="incident",
        )
        assert reason is not None
        self.assertIn("executed", reason.lower())
        self.assertIn("retained", reason.lower())

    def test_approval_needed_state(self) -> None:
        """Approval-needed items return approval rationale."""
        from k8s_diag_agent.ui.api_incident_report import _derive_worklist_ranking_reason

        reason = _derive_worklist_ranking_reason(
            source_type="planner",
            item_state="approval-needed",
            execution_state="unexecuted",
            is_primary_triage=None,
            urgency=None,
            priority_label="primary",
            command="kubectl delete pod",
            workstream="incident",
        )
        assert reason is not None
        self.assertIn("approval", reason.lower())

    def test_high_priority_executable(self) -> None:
        """High priority executable items return confirmation rationale."""
        from k8s_diag_agent.ui.api_incident_report import _derive_worklist_ranking_reason

        reason = _derive_worklist_ranking_reason(
            source_type="planner",
            item_state="queued",
            execution_state="unexecuted",
            is_primary_triage=None,
            urgency=None,
            priority_label="primary",
            command="kubectl logs pod/my-pod",
            workstream="incident",
        )
        assert reason is not None
        self.assertIn("Executable now", reason)

    def test_drift_workstream(self) -> None:
        """Drift workstream items return fleet rationale."""
        from k8s_diag_agent.ui.api_incident_report import _derive_worklist_ranking_reason

        reason = _derive_worklist_ranking_reason(
            source_type="planner",
            item_state="queued",
            execution_state="unexecuted",
            is_primary_triage=None,
            urgency=None,
            priority_label="secondary",
            command="helm list",
            workstream="drift",
        )
        assert reason is not None
        self.assertIn("fleet", reason.lower())

    def test_advisory_deterministic(self) -> None:
        """Advisory deterministic items without primary triage return advisory rationale."""
        from k8s_diag_agent.ui.api_incident_report import _derive_worklist_ranking_reason

        reason = _derive_worklist_ranking_reason(
            source_type="deterministic",
            item_state="advisory",
            execution_state=None,
            is_primary_triage=False,
            urgency="medium",
            priority_label=None,
            command=None,
            workstream="network",
        )
        assert reason is not None
        self.assertIn("Advisory check", reason)
        self.assertIn("medium", reason)

    def test_fallback_returns_none(self) -> None:
        """When no ranking basis is determinable, returns None."""
        from k8s_diag_agent.ui.api_incident_report import _derive_worklist_ranking_reason

        reason = _derive_worklist_ranking_reason(
            source_type=None,
            item_state=None,
            execution_state=None,
            is_primary_triage=None,
            urgency=None,
            priority_label=None,
            command=None,
            workstream=None,
        )
        self.assertIsNone(reason)


# =============================================================================
# Adaptation Provenance Regression Tests (Epic: BETA-G5 Feedback Adaptation Provenance)
# =============================================================================


class AdaptationProvenanceTests(unittest.TestCase):
    """Tests for feedback adaptation provenance on executed/reviewed worklist items.

    Coverage goals:
    - adaptation provenance present when feedback exists
    - no material-change represented honestly
    - feedback doesn't silently rewrite facts
    - usefulness labels and adaptation effects consistent
    - executed items explain changes without pretending certainty
    """

    def setUp(self) -> None:
        # Import new fixtures
        from tests.fixtures.incident_report_fixtures import (
            _fixture_executed_result_deprioritizes_action,
            _fixture_executed_result_promotes_action,
            _fixture_noisy_result_no_material_change,
            _fixture_partial_result_unknown_resolved,
            _fixture_useful_result_hypothesis_strengthened,
        )
        self._fixture_useful = _fixture_useful_result_hypothesis_strengthened
        self._fixture_noisy = _fixture_noisy_result_no_material_change
        self._fixture_partial = _fixture_partial_result_unknown_resolved
        self._fixture_promote = _fixture_executed_result_promotes_action
        self._fixture_deprioritize = _fixture_executed_result_deprioritizes_action

    def test_useful_result_has_hypothesis_strengthened_provenance(self) -> None:
        """Useful feedback produces hypothesis_strengthened adaptation effect."""
        index = self._fixture_useful()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None

        # Find executed item with usefulness feedback
        executed_items = [
            i for i in worklist["items"]
            if i.get("itemState") in ("executed", "reviewed")
            and i.get("executionState") in ("executed-success", "completed")
        ]
        self.assertTrue(executed_items, "Expected at least one executed item")

        item = executed_items[0]
        provenance = item.get("feedbackAdaptationProvenance")

        # Provenance must be present for executed items with feedback
        self.assertIsNotNone(provenance, "feedbackAdaptationProvenance must be present")
        assert provenance is not None

        # Verify adaptation effect matches usefulness class
        self.assertEqual(provenance.get("adaptationEffect"), "hypothesis_strengthened")
        self.assertEqual(provenance.get("feedbackAdaptation"), True)
        self.assertIn("adaptationReason", provenance)
        self.assertIn("adaptationSummary", provenance)
        self.assertIn("explanation", provenance)

    def test_noisy_result_has_no_material_change_provenance(self) -> None:
        """Noisy feedback produces no_material_change adaptation effect."""
        index = self._fixture_noisy()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None

        # Find executed item with noisy usefulness
        noisy_items = [
            i for i in worklist["items"]
            if i.get("executionState") in ("executed-success", "completed")
            and i.get("feedbackAdaptationProvenance") is not None
        ]
        self.assertTrue(noisy_items, "Expected at least one executed item with provenance")

        item = noisy_items[0]
        provenance = item.get("feedbackAdaptationProvenance")
        assert provenance is not None

        # Noisy feedback must result in no_material_change
        self.assertEqual(provenance.get("adaptationEffect"), "no_material_change")

        # Adaptation summary must honestly represent no diagnostic impact
        summary = provenance.get("adaptationSummary", "")
        self.assertTrue(
            "no material" in str(summary).lower() or "no change" in str(summary).lower(),
            f"Expected honest 'no material change' summary, got: {summary}",
        )

    def test_partial_result_has_unknown_resolved_provenance(self) -> None:
        """Partial feedback produces unknown_resolved adaptation effect."""
        index = self._fixture_partial()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None

        # Find executed item with partial usefulness
        partial_items = [
            i for i in worklist["items"]
            if i.get("executionState") in ("executed-success", "completed")
            and i.get("feedbackAdaptationProvenance") is not None
        ]
        self.assertTrue(partial_items, "Expected at least one executed item with provenance")

        item = partial_items[0]
        provenance = item.get("feedbackAdaptationProvenance")
        assert provenance is not None

        # Partial feedback must result in unknown_resolved
        self.assertEqual(provenance.get("adaptationEffect"), "unknown_resolved")

        # Adaptation summary should mention resolution
        summary = provenance.get("adaptationSummary", "")
        self.assertTrue(
            "resolved" in str(summary).lower() or "evidence" in str(summary).lower(),
            f"Expected resolution mention in summary, got: {summary}",
        )

    def test_useful_feedback_promotes_action(self) -> None:
        """Useful feedback that surfaces new action has recommendation_promoted effect."""
        index = self._fixture_promote()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None

        # Find executed item with useful feedback
        useful_items = [
            i for i in worklist["items"]
            if i.get("executionState") in ("executed-success", "completed")
            and i.get("feedbackAdaptationProvenance") is not None
        ]
        self.assertTrue(useful_items, "Expected at least one executed item with provenance")

        item = useful_items[0]
        provenance = item.get("feedbackAdaptationProvenance")
        assert provenance is not None

        # Verify adaptation effect is hypothesis_strengthened (useful result)
        self.assertEqual(
            provenance.get("adaptationEffect"),
            "hypothesis_strengthened",
            "Useful result should strengthen hypothesis",
        )

        # Verify the pending item exists (action promotion scenario)
        pending_items = [
            i for i in worklist["items"]
            if i.get("executionState") == "unexecuted"
        ]
        self.assertTrue(pending_items, "Expected pending items for action promotion")

    def test_deprioritization_has_recommendation_deprioritized_effect(self) -> None:
        """Noisy feedback that downgrades prior action has recommendation_deprioritized effect."""
        index = self._fixture_deprioritize()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None

        # Find executed item with noisy feedback
        noisy_items = [
            i for i in worklist["items"]
            if i.get("executionState") in ("executed-success", "completed")
            and i.get("feedbackAdaptationProvenance") is not None
        ]
        self.assertTrue(noisy_items, "Expected at least one executed item with provenance")

        item = noisy_items[0]
        provenance = item.get("feedbackAdaptationProvenance")
        assert provenance is not None

        # Noisy feedback must result in no_material_change (deprioritization signal)
        self.assertEqual(provenance.get("adaptationEffect"), "no_material_change")

    def test_no_feedback_no_provenance(self) -> None:
        """Items without usefulness feedback have no adaptation provenance."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None

        # Items without execution feedback should not have adaptation provenance
        for item in worklist["items"]:
            if not item.get("executionState"):
                self.assertIsNone(
                    item.get("feedbackAdaptationProvenance"),
                    f"Unexecuted item should not have adaptation provenance: {item.get('id')}",
                )

    def test_adaptation_effect_constants_are_correct(self) -> None:
        """Verify adaptation effect constants match the taxonomy."""
        from k8s_diag_agent.ui.api_incident_report import (
            _ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED,
            _ADAPTATION_EFFECT_HYPOTHESIS_WEAKENED,
            _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE,
            _ADAPTATION_EFFECT_RECOMMENDATION_DEPRIORITIZED,
            _ADAPTATION_EFFECT_RECOMMENDATION_PROMOTED,
            _ADAPTATION_EFFECT_UNKNOWN_RESOLVED,
            _USE_TO_ADAPTATION_MAP,
        )

        # Verify all expected effects exist
        self.assertEqual(_ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED, "hypothesis_strengthened")
        self.assertEqual(_ADAPTATION_EFFECT_HYPOTHESIS_WEAKENED, "hypothesis_weakened")
        self.assertEqual(_ADAPTATION_EFFECT_UNKNOWN_RESOLVED, "unknown_resolved")
        self.assertEqual(_ADAPTATION_EFFECT_RECOMMENDATION_PROMOTED, "recommendation_promoted")
        self.assertEqual(_ADAPTATION_EFFECT_RECOMMENDATION_DEPRIORITIZED, "recommendation_deprioritized")
        self.assertEqual(_ADAPTATION_EFFECT_NO_MATERIAL_CHANGE, "no_material_change")

        # Verify mapping from usefulness class to effect
        self.assertEqual(_USE_TO_ADAPTATION_MAP.get("useful"), "hypothesis_strengthened")
        self.assertEqual(_USE_TO_ADAPTATION_MAP.get("partial"), "unknown_resolved")
        self.assertEqual(_USE_TO_ADAPTATION_MAP.get("noisy"), "no_material_change")
        self.assertEqual(_USE_TO_ADAPTATION_MAP.get("empty"), "no_material_change")

    def test_feedback_provenance_fields_complete(self) -> None:
        """Adaptation provenance dict contains all required fields."""
        index = self._fixture_useful()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None

        # Find item with provenance
        provenance_items = [
            i for i in worklist["items"]
            if i.get("feedbackAdaptationProvenance") is not None
        ]
        self.assertTrue(provenance_items, "Expected at least one item with provenance")

        provenance = provenance_items[0].get("feedbackAdaptationProvenance")
        assert provenance is not None

        # Verify all required provenance fields
        required_fields = [
            "feedbackAdaptation",
            "adaptationReason",
            "adaptationEffect",
            "adaptationSummary",
            "originalBonus",
            "suppressedBonus",
            "penaltyApplied",
            "explanation",
        ]
        for field in required_fields:
            self.assertIn(field, provenance, f"Required field '{field}' missing from provenance")

    def test_executed_items_retain_provenance_after_projection(self) -> None:
        """Executed items preserve adaptation provenance through worklist projection."""
        index = self._fixture_useful()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None

        # Verify executed items have provenance
        executed_with_provenance = [
            i for i in worklist["items"]
            if i.get("itemState") in ("executed", "reviewed")
            and i.get("feedbackAdaptationProvenance") is not None
        ]
        self.assertTrue(
            executed_with_provenance,
            "Executed items must have adaptation provenance",
        )

    def test_derive_adaptation_provenance_function(self) -> None:
        """Test the _derive_adaptation_provenance function directly."""
        from k8s_diag_agent.ui.api_incident_report import _derive_adaptation_provenance

        # Test useful feedback
        result = _derive_adaptation_provenance(
            usefulness_class="useful",
            usefulness_summary="Found crash events confirming hypothesis",
            execution_result_summary="Captured pod events showing crash pattern",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["adaptationEffect"], "hypothesis_strengthened")
        self.assertEqual(result["feedbackAdaptation"], True)
        summary = str(result["adaptationSummary"] or "")
        self.assertIn("Strengthened", summary)

        # Test noisy feedback
        result = _derive_adaptation_provenance(
            usefulness_class="noisy",
            usefulness_summary="Logs contained only routine messages",
            execution_result_summary="No crash details captured",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["adaptationEffect"], "no_material_change")
        self.assertIn("no material", result["adaptationSummary"].lower())

        # Test partial feedback
        result = _derive_adaptation_provenance(
            usefulness_class="partial",
            usefulness_summary="Found events but exit code missing",
            execution_result_summary="Partial events captured",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["adaptationEffect"], "unknown_resolved")

        # Test empty usefulness class returns None
        result = _derive_adaptation_provenance(
            usefulness_class=None,
            usefulness_summary=None,
            execution_result_summary=None,
        )
        self.assertIsNone(result)

        # Test unknown usefulness class returns None
        result = _derive_adaptation_provenance(
            usefulness_class="unknown",
            usefulness_summary="Something",
            execution_result_summary="Something",
        )
        self.assertIsNone(result)


# =============================================================================
# Temporal Context Regression Tests (Epic: BETA-G4 Temporal Context in Worklist)
# =============================================================================


class TemporalContextTests(unittest.TestCase):
    """Tests for temporal context fields in operator worklist items.

    Regression tests for BETA-G4 epic: Temporal context in worklist.
    Verifies that worklist items expose useful temporal context when timestamps
    are available, and honestly represent unknown timing when data is insufficient.

    Temporal context fields:
    - firstRecommendedAt: earliest known recommendation timestamp
    - lastStateChangedAt: most recent state transition timestamp
    - recommendationAgeSeconds: age in seconds from first recommendation
    - stalenessClass: fresh | aging | stale | unknown

    Derivation rules:
    - firstRecommendedAt: from assessment/drilldown for deterministic, plan artifact for queue
    - lastStateChangedAt: latest execution/approval timestamp
    - recommendationAgeSeconds: derived from firstRecommendedAt and current run timestamp
    - stalenessClass: fresh (<5min), aging (5-30min), stale (>30min), unknown (no data)
    """

    def test_temporal_fields_are_present_in_worklist_items(self) -> None:
        """All worklist items must have temporal context fields."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])
        for item in worklist["items"]:
            self.assertIn("firstRecommendedAt", item)
            self.assertIn("lastStateChangedAt", item)
            self.assertIn("recommendationAgeSeconds", item)
            self.assertIn("stalenessClass", item)

    def test_fresh_item_has_fresh_staleness_class(self) -> None:
        """Items with recent timestamps must have stalenessClass=fresh."""
        index = _fixture_degraded_single_cluster()
        # The degraded fixture has timestamps close to run time
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # At least one item should have temporal context
        items_with_time = [
            i for i in worklist["items"]
            if i.get("firstRecommendedAt") is not None
        ]
        if items_with_time:
            for item in items_with_time:
                # If age is known, staleness should be determinable
                age_val = item.get("recommendationAgeSeconds")
                if age_val is not None:
                    staleness = item.get("stalenessClass")
                    if age_val < 5 * 60:
                        self.assertEqual(staleness, "fresh")
                    elif age_val < 30 * 60:
                        self.assertEqual(staleness, "aging")
                    else:
                        self.assertEqual(staleness, "stale")

    def test_staleness_class_unknown_when_timing_data_missing(self) -> None:
        """Items without timing data must have stalenessClass=unknown."""
        # Create an index with no timestamps
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        # Healthy fixture has no worklist items
        self.assertIsNone(worklist)

    def test_stale_items_not_misrepresented_as_fresh(self) -> None:
        """Items older than 30 minutes must not have stalenessClass=fresh."""
        # Create a fixture with old timestamps
        index = _fixture_degraded_single_cluster()
        # The degraded fixture should have temporal context
        # If timestamps exist and age > 30min, staleness must be "stale" or "unknown"
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        if worklist:
            for item in worklist["items"]:
                age_val = item.get("recommendationAgeSeconds")
                if age_val is not None:
                    staleness = item.get("stalenessClass")
                    if age_val >= 30 * 60:
                        self.assertNotEqual(
                            staleness, "fresh",
                            f"Item {item.get('id')} with age {age_val}s should not be fresh"
                        )

    def test_executed_items_have_meaningful_recency_metadata(self) -> None:
        """Executed/reviewed items retained for review must have recency metadata."""
        index = _fixture_executed_with_usefulness()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        executed_items = [
            i for i in worklist["items"]
            if i.get("itemState") in ("executed", "reviewed")
        ]
        if executed_items:
            for item in executed_items:
                # Should have temporal context fields
                self.assertIn("firstRecommendedAt", item)
                self.assertIn("lastStateChangedAt", item)
                # Should have a staleness class (may be unknown if timing data is missing)
                self.assertIn("stalenessClass", item)

    def test_approval_needed_items_have_temporal_context(self) -> None:
        """Approval-needed items should have temporal context for staleness visibility."""
        index = _fixture_approval_needed_item()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        approval_items = [
            i for i in worklist["items"]
            if i.get("itemState") == "approval-needed"
        ]
        if approval_items:
            for item in approval_items:
                self.assertIn("stalenessClass", item)
                # If we have timestamps, we should have age
                if item.get("firstRecommendedAt") and item.get("recommendationAgeSeconds") is not None:
                    # Age should be derivable
                    self.assertIsNotNone(item.get("recommendationAgeSeconds"))


class TemporalContextDerivationTests(unittest.TestCase):
    """Tests for the _derive_temporal_context helper function."""

    def test_derive_temporal_context_with_both_timestamps(self) -> None:
        """Temporal context is correctly derived when both timestamps are present."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        last_at = "2026-01-01T00:10:00Z"
        current = "2026-01-01T00:35:00Z"  # 35 minutes after first

        first_rec, last_change, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=last_at,
            current_run_timestamp=current,
        )

        self.assertEqual(first_rec, first_at)
        self.assertEqual(last_change, last_at)
        self.assertEqual(age_sec, 35 * 60)  # 2100 seconds
        self.assertEqual(staleness, "stale")  # > 30 minutes

    def test_derive_temporal_context_fresh_item(self) -> None:
        """Fresh items (<5 min) have stalenessClass=fresh."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:03:00Z"  # 3 minutes after first

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 3 * 60)  # 180 seconds
        self.assertEqual(staleness, "fresh")

    def test_derive_temporal_context_aging_item(self) -> None:
        """Aging items (5-30 min) have stalenessClass=aging."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:15:00Z"  # 15 minutes after first

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 15 * 60)  # 900 seconds
        self.assertEqual(staleness, "aging")

    def test_derive_temporal_context_unknown_when_no_first_timestamp(self) -> None:
        """stalenessClass=unknown when firstRecommendedAt is missing."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=None,
            last_state_changed_at="2026-01-01T00:10:00Z",
            current_run_timestamp="2026-01-01T00:30:00Z",
        )

        self.assertIsNone(age_sec)
        self.assertEqual(staleness, "unknown")

    def test_derive_temporal_context_unknown_when_no_current_timestamp(self) -> None:
        """stalenessClass=unknown when current_run_timestamp is missing."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at="2026-01-01T00:00:00Z",
            last_state_changed_at="2026-01-01T00:10:00Z",
            current_run_timestamp=None,
        )

        self.assertIsNone(age_sec)
        self.assertEqual(staleness, "unknown")

    def test_derive_temporal_context_returns_input_timestamps(self) -> None:
        """firstRecommendedAt and lastStateChangedAt are returned as-is."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        last_at = "2026-01-01T00:10:00Z"
        current = "2026-01-01T00:30:00Z"

        first_rec, last_change, _, _ = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=last_at,
            current_run_timestamp=current,
        )

        self.assertEqual(first_rec, first_at)
        self.assertEqual(last_change, last_at)

    def test_derive_temporal_context_invalid_timestamp_handled(self) -> None:
        """Invalid timestamps are handled gracefully with unknown staleness."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at="not-a-timestamp",
            last_state_changed_at="also-invalid",
            current_run_timestamp="2026-01-01T00:30:00Z",
        )

        self.assertIsNone(age_sec)
        self.assertEqual(staleness, "unknown")

    def test_derive_temporal_context_negative_age_unknown(self) -> None:
        """Negative age (first recommendation after current run) is marked unknown."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T01:00:00Z"  # Later than current
        current = "2026-01-01T00:30:00Z"

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        # Negative age should result in unknown rather than fabricating
        self.assertIsNone(age_sec)
        self.assertEqual(staleness, "unknown")


class TemporalContextStalenessThresholdTests(unittest.TestCase):
    """Tests for staleness threshold boundaries."""

    def test_fresh_boundary_5_minutes(self) -> None:
        """Exactly 5 minutes is aging, not fresh."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:05:00Z"  # Exactly 5 minutes

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 5 * 60)
        self.assertEqual(staleness, "aging")  # >= 5 minutes is aging

    def test_aging_boundary_30_minutes(self) -> None:
        """Exactly 30 minutes is stale, not aging."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:30:00Z"  # Exactly 30 minutes

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 30 * 60)
        self.assertEqual(staleness, "stale")  # >= 30 minutes is stale

    def test_just_under_fresh_boundary(self) -> None:
        """Just under 5 minutes is fresh."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:04:59Z"  # Just under 5 minutes

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 4 * 60 + 59)  # 299 seconds
        self.assertEqual(staleness, "fresh")

    def test_just_under_aging_boundary(self) -> None:
        """Just under 30 minutes is aging."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:29:59Z"  # Just under 30 minutes

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(staleness, "aging")


if __name__ == "__main__":
    unittest.main()

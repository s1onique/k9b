"""Unit tests for evidence ownership derivation in unknown/missing-evidence items.

Epic: BETA-G6 Unknown Evidence Owner
Purpose: Verify that unknown/missing-evidence items include ownership/routing hints
that help operators understand who should collect the missing signal.

Coverage goals:
- ownership hints appear when derivable from method/evidence_needed/layer/owner/workstream
- ambiguous cases remain honestly "unknown" instead of fabricated
- routing hints stay concise and operator-readable
- ownership hints are consistent with probable layer / evidence-needed signals
- unknown evidence continues to preserve truthfulness and does not become a fake fact
- cross-cluster/fleet evidence hints at platform or fleet owner
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.api_incident_report import (
    _build_incident_report_payload,
)
from k8s_diag_agent.ui.api_incident_report_ownership import (
    derive_evidence_ownership,
    format_ownership_fields,
)
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.incident_report_fixtures import _freshness


class DeriveEvidenceOwnershipTests(unittest.TestCase):
    """Tests for the derive_evidence_ownership derivation function."""

    # =============================================================================
    # Platform ownership tests
    # =============================================================================

    def test_platform_ownership_from_method(self) -> None:
        """method containing 'kubelet' should derive platform ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="kubectl kubelet logs",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "platform")
        assert hint is not None
        self.assertIn("platform", hint.lower())

    def test_platform_ownership_from_node_layer(self) -> None:
        """probable_layer=node should derive platform ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer="node",
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "platform")

    def test_platform_ownership_from_control_plane_method(self) -> None:
        """method containing 'control-plane' should derive platform ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="check control-plane version",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "platform")

    def test_platform_ownership_from_owner_field(self) -> None:
        """owner field containing 'platform' should derive platform ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer=None,
            owner="platform-engineer",
            workstream=None,
        )
        self.assertEqual(owner, "platform")

    # =============================================================================
    # Application ownership tests
    # =============================================================================

    def test_application_ownership_from_pod_method(self) -> None:
        """method containing 'pod' should derive application ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="kubectl get pods",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "application")

    def test_application_ownership_from_workload_layer(self) -> None:
        """probable_layer=workload should derive application ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer="workload",
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "application")

    def test_application_ownership_from_evidence_needed(self) -> None:
        """evidence_needed containing 'container' should derive application ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("kubectl describe container",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "application")

    def test_application_ownership_from_deployment_evidence(self) -> None:
        """evidence_needed containing 'deployment' should derive application ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("kubectl get deployment",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "application")

    # =============================================================================
    # Networking ownership tests
    # =============================================================================

    def test_networking_ownership_from_ingress_method(self) -> None:
        """method containing 'ingress' should derive networking ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="kubectl get ingress",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "networking")

    def test_networking_ownership_from_dns_evidence(self) -> None:
        """evidence_needed containing 'dns' should derive networking ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("kubectl get dns", "kubectl logs -n kube-system coredns"),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "networking")

    def test_networking_ownership_from_service_mesh_evidence(self) -> None:
        """evidence_needed containing 'istio' should derive networking ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("kubectl get virtualservice",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "networking")

    # =============================================================================
    # Storage ownership tests
    # =============================================================================

    def test_storage_ownership_from_pvc_evidence(self) -> None:
        """evidence_needed containing 'pvc' should derive storage ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("kubectl describe pvc",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "storage")

    def test_storage_ownership_from_volume_evidence(self) -> None:
        """evidence_needed containing 'volume' should derive storage ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("kubectl get pv", "kubectl describe volume"),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "storage")

    def test_storage_ownership_from_storageclass_evidence(self) -> None:
        """evidence_needed containing 'storageclass' should derive storage ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("kubectl get storageclass",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "storage")

    # =============================================================================
    # Security ownership tests
    # =============================================================================

    def test_security_ownership_from_rbac_method(self) -> None:
        """method containing 'auth can-i' should derive security ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="kubectl auth can-i",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "security")

    def test_security_ownership_from_certificate_evidence(self) -> None:
        """evidence_needed containing 'certificate' should derive security ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("kubectl get certificate",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "security")

    # =============================================================================
    # Observability ownership tests
    # =============================================================================

    def test_observability_ownership_from_prometheus_method(self) -> None:
        """method containing 'prometheus' should derive observability ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="prometheus query",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "observability")

    def test_observability_ownership_from_prometheus_evidence(self) -> None:
        """evidence_needed containing 'prometheus' should derive observability ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("prometheus query",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "observability")

    # =============================================================================
    # Unknown/Ambiguous ownership tests
    # =============================================================================

    def test_unknown_ownership_when_no_signals(self) -> None:
        """no signals should result in unknown ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "unknown")
        self.assertEqual(confidence, 0.0)

    def test_unknown_ownership_for_ambiguous_evidence(self) -> None:
        """ambiguous evidence that doesn't match any pattern should be unknown."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=("some generic check",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertEqual(owner, "unknown")

    def test_ambiguous_cases_not_fabricated(self) -> None:
        """ambiguous cases should not be assigned confident ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="custom command",
            evidence_needed=("arbitrary thing",),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        # Should not claim high confidence when signals are ambiguous
        self.assertLessEqual(confidence, 0.75)
        if owner != "unknown":
            # If we derived something, confidence should be low
            self.assertLess(confidence, 0.8)

    # =============================================================================
    # Cross-cluster/Fleet ownership tests
    # =============================================================================

    def test_cross_cluster_defaults_to_platform(self) -> None:
        """cross-cluster scope should hint at platform ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
            is_cross_cluster=True,
        )
        self.assertEqual(owner, "platform")

    def test_drift_workstream_hints_platform(self) -> None:
        """drift workstream should hint at platform ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream="drift",
        )
        self.assertEqual(owner, "platform")

    def test_network_workstream_hints_networking(self) -> None:
        """network workstream should hint at networking ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream="network",
        )
        self.assertEqual(owner, "networking")

    # =============================================================================
    # Confidence score tests
    # =============================================================================

    def test_high_confidence_from_owner_field(self) -> None:
        """owner field match should have high confidence (0.9)."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer=None,
            owner="platform-engineer",
            workstream=None,
        )
        self.assertGreaterEqual(confidence, 0.8)

    def test_medium_confidence_from_method(self) -> None:
        """method match should have high confidence (0.75)."""
        owner, hint, confidence = derive_evidence_ownership(
            method="kubectl get pods",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertGreaterEqual(confidence, 0.7)

    def test_low_confidence_from_workstream(self) -> None:
        """workstream match should have low confidence (0.4)."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream="drift",
        )
        self.assertLessEqual(confidence, 0.5)
        self.assertGreaterEqual(confidence, 0.3)

    # =============================================================================
    # Routing hint tests
    # =============================================================================

    def test_routing_hint_present_for_platform(self) -> None:
        """routing hint should be present for platform ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="kubelet",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertTrue(len(hint) > 0)
        self.assertIn("platform", hint.lower())

    def test_routing_hint_present_for_application(self) -> None:
        """routing hint should be present for application ownership."""
        owner, hint, confidence = derive_evidence_ownership(
            method="kubectl get pods",
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertTrue(len(hint) > 0)

    def test_routing_hint_concise_for_unknown(self) -> None:
        """routing hint for unknown should be concise."""
        owner, hint, confidence = derive_evidence_ownership(
            method=None,
            evidence_needed=(),
            probable_layer=None,
            owner=None,
            workstream=None,
        )
        self.assertIsNotNone(hint)
        assert hint is not None
        # Routing hint should be honest about insufficient signal
        self.assertIn("insufficient", hint.lower())


class FormatOwnershipFieldsTests(unittest.TestCase):
    """Tests for the format_ownership_fields function."""

    def test_platform_fields_formatted(self) -> None:
        """platform ownership should format correctly."""
        fields = format_ownership_fields("platform", "Contact platform team", 0.9)
        self.assertEqual(fields["evidenceOwner"], "platform")
        self.assertEqual(fields["routingHint"], "Contact platform team")
        self.assertEqual(fields["ownershipConfidence"], "high")

    def test_application_fields_formatted(self) -> None:
        """application ownership should format correctly."""
        fields = format_ownership_fields("application", "Contact app team", 0.75)
        self.assertEqual(fields["evidenceOwner"], "application")
        self.assertEqual(fields["routingHint"], "Contact app team")
        self.assertEqual(fields["ownershipConfidence"], "medium")

    def test_unknown_ownership_no_routing_hint(self) -> None:
        """unknown ownership should not include routing hint."""
        fields = format_ownership_fields("unknown", "Insufficient signal", 0.0)
        self.assertEqual(fields["evidenceOwner"], "unknown")
        self.assertNotIn("routingHint", fields)

    def test_ownership_confidence_high_threshold(self) -> None:
        """confidence >= 0.8 should be high."""
        fields = format_ownership_fields("platform", "Hint", 0.85)
        self.assertEqual(fields["ownershipConfidence"], "high")

    def test_ownership_confidence_medium_threshold(self) -> None:
        """confidence >= 0.6 and < 0.8 should be medium."""
        fields = format_ownership_fields("platform", "Hint", 0.65)
        self.assertEqual(fields["ownershipConfidence"], "medium")

    def test_ownership_confidence_low_threshold(self) -> None:
        """confidence >= 0.4 and < 0.6 should be low."""
        fields = format_ownership_fields("platform", "Hint", 0.45)
        self.assertEqual(fields["ownershipConfidence"], "low")

    def test_ownership_confidence_unknown_threshold(self) -> None:
        """confidence < 0.4 should be unknown."""
        fields = format_ownership_fields("unknown", "Hint", 0.3)
        self.assertEqual(fields["ownershipConfidence"], "unknown")

    def test_zero_confidence_omits_confidence_field(self) -> None:
        """zero confidence should not include ownershipConfidence field."""
        fields = format_ownership_fields("unknown", "Hint", 0.0)
        # When confidence is 0, ownershipConfidence field is not included
        self.assertNotIn("ownershipConfidence", fields)


class UnknownOwnershipIntegrationTests(unittest.TestCase):
    """Integration tests for ownership in unknown claims within incident reports."""

    def _build_fixture_with_missing_evidence_and_next_checks(
        self,
        missing_evidence: list[str],
        next_checks: list[dict[str, object]],
        probable_layer: str | None = None,
    ) -> dict[str, object]:
        """Helper to build a fixture with missing evidence and next checks."""
        return {
            "run": {
                "run_id": "run-test",
                "run_label": "health-run",
                "timestamp": "2026-01-01T00:00:00Z",
                "collector_version": "1.0",
                "cluster_count": 1,
                "drilldown_count": 1,
                "proposal_count": 0,
                "external_analysis_count": 0,
                "notification_count": 0,
                "scheduler_interval_seconds": 300,
                "llm_stats": {
                    "totalCalls": 0,
                    "successfulCalls": 0,
                    "failedCalls": 0,
                    "lastCallTimestamp": None,
                    "p50LatencyMs": None,
                    "p95LatencyMs": None,
                    "p99LatencyMs": None,
                    "providerBreakdown": [],
                    "scope": "current_run",
                },
                "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
                "llm_policy": None,
                "review_enrichment": None,
                "review_enrichment_status": None,
                "provider_execution": None,
                "auto_drilldown_config": None,
                "review_enrichment_config": None,
                "next_check_plan": None,
                "planner_availability": None,
                "next_check_queue": [],
                "next_check_execution_history": [],
                "deterministic_next_checks": None,
                "diagnostic_pack_review": None,
                "diagnostic_pack": None,
            },
            "run_stats": {
                "last_run_duration_seconds": 30,
                "total_runs": 1,
                "p50_run_duration_seconds": 30,
                "p95_run_duration_seconds": 30,
                "p99_run_duration_seconds": 30,
            },
            "clusters": [
                {
                    "label": "cluster-test",
                    "context": "cluster-test",
                    "cluster_class": "prod",
                    "cluster_role": "primary",
                    "baseline_cohort": "fleet",
                    "node_count": 3,
                    "control_plane_version": "v1.28.0",
                    "health_rating": "degraded",
                    "warnings": 2,
                    "non_running_pods": 1,
                    "baseline_policy_path": "policy.json",
                    "missing_evidence": [],
                    "artifact_paths": {
                        "snapshot": "snapshots/cluster-test.json",
                        "assessment": "assessments/cluster-test.json",
                        "drilldown": "drilldowns/cluster-test.json",
                    },
                }
            ],
            "proposals": [],
            "fleet_status": {
                "rating_counts": [{"rating": "degraded", "count": 1}],
                "degraded_clusters": ["cluster-test"],
            },
            "proposal_status_summary": {"status_counts": []},
            "latest_drilldown": {
                "label": "cluster-test",
                "context": "cluster-test",
                "trigger_reasons": ["non_running_pods"],
                "warning_events": 2,
                "non_running_pods": 1,
                "summary": {},
                "rollout_status": [],
                "pattern_details": {"pattern": "crashloop"},
                "artifact_path": "drilldowns/cluster-test.json",
            },
            "latest_assessment": {
                "cluster_label": "cluster-test",
                "context": "cluster-test",
                "timestamp": "2026-01-01T00:00:00Z",
                "health_rating": "degraded",
                "missing_evidence": missing_evidence,
                "findings": [],
                "hypotheses": [],
                "next_evidence_to_collect": next_checks,
                "recommended_action": {
                    "type": "observation",
                    "description": "Investigate pod crash",
                    "references": [],
                    "safety_level": "low-risk",
                },
                "overall_confidence": "medium",
                "probable_layer_of_origin": probable_layer,
                "artifact_path": "assessments/cluster-test.json",
                "snapshot_path": "snapshots/cluster-test.json",
            },
            "drilldown_availability": {
                "total_clusters": 1,
                "available": 1,
                "missing": 0,
                "coverage": [
                    {
                        "label": "cluster-test",
                        "context": "cluster-test",
                        "available": True,
                        "timestamp": "2026-01-01T00:00:00Z",
                        "artifact_path": "drilldowns/cluster-test.json",
                    }
                ],
                "missing_clusters": [],
            },
            "notification_history": [],
            "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
            "auto_drilldown_interpretations": {},
        }

    def test_missing_evidence_includes_platform_ownership(self) -> None:
        """missing evidence with kubelet method should include platform ownership."""
        index = self._build_fixture_with_missing_evidence_and_next_checks(
            missing_evidence=["kubelet logs"],
            next_checks=[
                {
                    "description": "Collect kubelet logs",
                    "owner": "platform-engineer",
                    "method": "kubectl kubelet logs",
                    "evidence_needed": ["kubectl logs kubelet"],
                    "workstream": "incident",
                }
            ],
        )
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))

        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["unknowns"])

        # Find the unknown for kubelet logs
        kubelet_unknown = next(
            (u for u in report["unknowns"] if "kubelet" in u["statement"].lower()),
            None,
        )
        self.assertIsNotNone(kubelet_unknown)
        assert kubelet_unknown is not None
        self.assertEqual(kubelet_unknown.get("evidenceOwner"), "platform")

    def test_missing_evidence_includes_application_ownership(self) -> None:
        """missing evidence with pod method should include application ownership."""
        index = self._build_fixture_with_missing_evidence_and_next_checks(
            missing_evidence=["pod logs"],
            next_checks=[
                {
                    "description": "Collect pod logs",
                    "owner": "app-team",
                    "method": "kubectl logs pod",
                    "evidence_needed": ["kubectl logs pod"],
                    "workstream": "incident",
                }
            ],
        )
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))

        self.assertIsNotNone(report)
        assert report is not None

        pod_unknown = next(
            (u for u in report["unknowns"] if "pod" in u["statement"].lower()),
            None,
        )
        self.assertIsNotNone(pod_unknown)
        assert pod_unknown is not None
        self.assertEqual(pod_unknown.get("evidenceOwner"), "application")

    def test_missing_evidence_includes_networking_ownership(self) -> None:
        """missing evidence with service method should include networking ownership."""
        index = self._build_fixture_with_missing_evidence_and_next_checks(
            missing_evidence=["service endpoints"],
            next_checks=[
                {
                    "description": "Check service endpoints",
                    "owner": "networking-team",
                    "method": "kubectl get endpoints",
                    "evidence_needed": ["kubectl get endpoints"],
                    "workstream": "network",
                }
            ],
        )
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))

        self.assertIsNotNone(report)
        assert report is not None

        svc_unknown = next(
            (u for u in report["unknowns"] if "service" in u["statement"].lower()),
            None,
        )
        self.assertIsNotNone(svc_unknown)
        assert svc_unknown is not None
        self.assertEqual(svc_unknown.get("evidenceOwner"), "networking")

    def test_missing_evidence_includes_storage_ownership(self) -> None:
        """missing evidence with PVC method should include storage ownership."""
        index = self._build_fixture_with_missing_evidence_and_next_checks(
            missing_evidence=["PVC status"],
            next_checks=[
                {
                    "description": "Check PVC status",
                    "owner": "storage-team",
                    "method": "kubectl describe pvc",
                    "evidence_needed": ["kubectl describe pvc"],
                    "workstream": "storage",
                }
            ],
        )
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))

        self.assertIsNotNone(report)
        assert report is not None

        pvc_unknown = next(
            (u for u in report["unknowns"] if "pvc" in u["statement"].lower()),
            None,
        )
        self.assertIsNotNone(pvc_unknown)
        assert pvc_unknown is not None
        self.assertEqual(pvc_unknown.get("evidenceOwner"), "storage")

    def test_missing_evidence_includes_routing_hint(self) -> None:
        """unknown items should include routing hints when derivable."""
        index = self._build_fixture_with_missing_evidence_and_next_checks(
            missing_evidence=["node status"],
            next_checks=[
                {
                    "description": "Check node status",
                    "owner": "platform-engineer",
                    "method": "kubectl get nodes",
                    "evidence_needed": ["kubectl get nodes"],
                    "workstream": "incident",
                }
            ],
        )
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))

        self.assertIsNotNone(report)
        assert report is not None

        node_unknown = next(
            (u for u in report["unknowns"] if "node" in u["statement"].lower()),
            None,
        )
        self.assertIsNotNone(node_unknown)
        assert node_unknown is not None
        self.assertIn("routingHint", node_unknown)
        self.assertIsNotNone(node_unknown["routingHint"])

    def test_missing_evidence_includes_ownership_confidence(self) -> None:
        """unknown items should include ownership confidence."""
        index = self._build_fixture_with_missing_evidence_and_next_checks(
            missing_evidence=["pod status"],
            next_checks=[
                {
                    "description": "Check pod status",
                    "owner": "app-team",
                    "method": "kubectl get pods",
                    "evidence_needed": ["kubectl get pods"],
                    "workstream": "incident",
                }
            ],
        )
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))

        self.assertIsNotNone(report)
        assert report is not None

        pod_unknown = next(
            (u for u in report["unknowns"] if "pod" in u["statement"].lower()),
            None,
        )
        self.assertIsNotNone(pod_unknown)
        assert pod_unknown is not None
        self.assertIn("ownershipConfidence", pod_unknown)
        self.assertIsNotNone(pod_unknown["ownershipConfidence"])

    def test_truthfulness_preserved_for_unknowns(self) -> None:
        """unknown items must preserve truthfulness: not become confident facts."""
        index = self._build_fixture_with_missing_evidence_and_next_checks(
            missing_evidence=["some unclear signal"],
            next_checks=[
                {
                    "description": "Check unclear signal",
                    "owner": "unknown",
                    "method": "custom-check",
                    "evidence_needed": ["custom command"],
                    "workstream": None,
                }
            ],
            probable_layer=None,
        )
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))

        self.assertIsNotNone(report)
        assert report is not None

        for unknown in report["unknowns"]:
            # Unknown must have whyMissing
            self.assertIsNotNone(unknown.get("whyMissing"))
            # Unknown must not have fabricated high confidence
            confidence = unknown.get("ownershipConfidence", "unknown")
            if confidence != "unknown":
                # If confidence is set, it should not claim high when signals are ambiguous
                self.assertIn(
                    confidence,
                    ("low", "medium"),
                    "Ambiguous signals should not claim high ownership confidence",
                )

    def test_cross_cluster_unknowns_hint_platform(self) -> None:
        """cross-cluster (multi-cluster) unknowns should hint at platform ownership."""
        index = self._build_fixture_with_missing_evidence_and_next_checks(
            missing_evidence=["cluster-wide metrics"],
            next_checks=[
                {
                    "description": "Collect cluster metrics",
                    "owner": "platform-engineer",
                    "method": "kubectl top nodes",
                    "evidence_needed": ["kubectl top nodes"],
                    "workstream": "drift",
                }
            ],
        )
        # Update to simulate multi-cluster
        run_entry: dict[str, object] = index["run"]  # type: ignore[assignment]
        run_entry["cluster_count"] = 3
        index["clusters"] = [
            {
                "label": f"cluster-{i}",
                "context": f"cluster-{i}",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": f"snapshots/cluster-{i}.json",
                    "assessment": f"assessments/cluster-{i}.json",
                    "drilldown": f"drilldowns/cluster-{i}.json",
                },
            }
            for i in range(3)
        ]
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))

        self.assertIsNotNone(report)
        assert report is not None

        cluster_unknown = next(
            (u for u in report["unknowns"] if "cluster" in u["statement"].lower()),
            None,
        )
        self.assertIsNotNone(cluster_unknown)
        assert cluster_unknown is not None
        # Cross-cluster should hint at platform ownership
        self.assertEqual(cluster_unknown.get("evidenceOwner"), "platform")


if __name__ == "__main__":
    unittest.main()

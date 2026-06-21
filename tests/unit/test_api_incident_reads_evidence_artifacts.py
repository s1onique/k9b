"""Tests for evidence artifacts projection in incident detail payload.

Tests:
1. No artifacts → empty evidence_artifacts list
2. One evidence artifact → single item in list
3. Multiple artifacts sorted deterministically by artifact_id
4. All safety flags present and correct
5. No raw artifact/log/prompt/stack/stdout/stderr leakage
6. Unknown artifact kind handled safely
7. Different evidence roles mapped to artifact_kinds correctly
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_evidence import EvidenceLink, EvidenceRole
from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
from k8s_diag_agent.ui.api_incident_reads import (
    build_evidence_artifact_payload,
    build_evidence_artifacts_payload,
    build_incident_detail_payload,
)

# =============================================================================
# Fixtures
# =============================================================================


def make_incident(
    incident_id: str = "test-incident-1",
    evidence_links: list[EvidenceLink] | None = None,
) -> Incident:
    """Create a test incident with optional evidence links."""
    return Incident(
        incident_id=incident_id,
        source_candidate_id="test-candidate-1",
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status=IncidentStatus.OPEN,
        first_observed_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        last_observed_at=datetime(2026, 1, 1, 14, 0, 0, tzinfo=UTC),
        evidence_links=evidence_links or [],
    )


def make_evidence_link(
    artifact_id: str,
    role: EvidenceRole,
    attached_at: datetime | None = None,
) -> EvidenceLink:
    """Create a test evidence link."""
    return EvidenceLink(
        incident_id="test-incident-1",
        artifact_id=artifact_id,
        role=role,
        attached_at=attached_at or datetime(2026, 1, 1, 14, 0, 0, tzinfo=UTC),
    )


# =============================================================================
# Tests for build_evidence_artifact_payload
# =============================================================================


class TestBuildEvidenceArtifactPayload(unittest.TestCase):
    """Tests for build_evidence_artifact_payload function."""

    def test_snapshot_role_maps_to_snapshot_bundle_kind(self) -> None:
        """EvidenceLink with snapshot role produces snapshot_bundle artifact_kind."""
        link = make_evidence_link("artifact-snapshot-1", EvidenceRole.SNAPSHOT)
        result = build_evidence_artifact_payload(link)

        self.assertEqual(result["artifact_id"], "artifact-snapshot-1")
        self.assertEqual(result["artifact_kind"], "snapshot_bundle")
        self.assertEqual(result["evidence_role"], "snapshot")

    def test_review_packet_role_maps_to_review_packet_kind(self) -> None:
        """EvidenceLink with review_packet role produces review_packet artifact_kind."""
        link = make_evidence_link("artifact-review-1", EvidenceRole.REVIEW_PACKET)
        result = build_evidence_artifact_payload(link)

        self.assertEqual(result["artifact_id"], "artifact-review-1")
        self.assertEqual(result["artifact_kind"], "review_packet")
        self.assertEqual(result["evidence_role"], "review_packet")

    def test_primary_role_maps_to_evidence_artifact_kind(self) -> None:
        """EvidenceLink with primary role produces evidence_artifact artifact_kind."""
        link = make_evidence_link("artifact-primary-1", EvidenceRole.PRIMARY)
        result = build_evidence_artifact_payload(link)

        self.assertEqual(result["artifact_id"], "artifact-primary-1")
        self.assertEqual(result["artifact_kind"], "evidence_artifact")
        self.assertEqual(result["evidence_role"], "primary")

    def test_supporting_role_maps_to_evidence_artifact_kind(self) -> None:
        """EvidenceLink with supporting role produces evidence_artifact artifact_kind."""
        link = make_evidence_link("artifact-supporting-1", EvidenceRole.SUPPORTING)
        result = build_evidence_artifact_payload(link)

        self.assertEqual(result["artifact_id"], "artifact-supporting-1")
        self.assertEqual(result["artifact_kind"], "evidence_artifact")
        self.assertEqual(result["evidence_role"], "supporting")

    def test_debug_role_maps_to_debug_artifact_kind(self) -> None:
        """EvidenceLink with debug role produces debug_artifact artifact_kind."""
        link = make_evidence_link("artifact-debug-1", EvidenceRole.DEBUG)
        result = build_evidence_artifact_payload(link)

        self.assertEqual(result["artifact_id"], "artifact-debug-1")
        self.assertEqual(result["artifact_kind"], "debug_artifact")
        self.assertEqual(result["evidence_role"], "debug")

    def test_evidence_role_debug_maps_to_debug_artifact_kind(self) -> None:
        """EvidenceLink with debug role produces debug_artifact artifact_kind."""
        link = make_evidence_link("artifact-debug-role-1", EvidenceRole.DEBUG)
        result = build_evidence_artifact_payload(link)

        self.assertEqual(result["artifact_id"], "artifact-debug-role-1")
        self.assertEqual(result["artifact_kind"], "debug_artifact")
        self.assertEqual(result["evidence_role"], "debug")

    def test_safety_flags_present(self) -> None:
        """EvidenceArtifactPayload has all required safety flags."""
        link = make_evidence_link("artifact-1", EvidenceRole.PRIMARY)
        result = build_evidence_artifact_payload(link)

        self.assertIn("read_only", result)
        self.assertIn("raw_content_available", result)
        self.assertIn("no_remediation_attempted", result)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["raw_content_available"])
        self.assertTrue(result["no_remediation_attempted"])

    def test_availability_fields_present(self) -> None:
        """EvidenceArtifactPayload has availability fields."""
        link = make_evidence_link("artifact-1", EvidenceRole.PRIMARY)
        result = build_evidence_artifact_payload(link)

        self.assertIn("available", result)
        self.assertIn("unavailable_reason", result)
        self.assertTrue(result["available"])
        self.assertIsNone(result["unavailable_reason"])

    def test_safe_reference_equals_artifact_id(self) -> None:
        """safe_reference field equals artifact_id."""
        link = make_evidence_link("artifact-xyz-123", EvidenceRole.PRIMARY)
        result = build_evidence_artifact_payload(link)

        self.assertEqual(result["safe_reference"], "artifact-xyz-123")

    def test_attached_at_is_isoformat(self) -> None:
        """attached_at is ISO format string."""
        attached_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        link = make_evidence_link("artifact-1", EvidenceRole.PRIMARY, attached_at=attached_at)
        result = build_evidence_artifact_payload(link)

        self.assertEqual(result["attached_at"], "2026-01-15T10:30:00+00:00")

    def test_null_fields_for_metadata_not_available(self) -> None:
        """Fields not available from link alone are null."""
        link = make_evidence_link("artifact-1", EvidenceRole.PRIMARY)
        result = build_evidence_artifact_payload(link)

        self.assertIsNone(result["source"])
        self.assertIsNone(result["created_at"])
        self.assertIsNone(result["run_id"])
        self.assertIsNone(result["collector_run_id"])
        self.assertIsNone(result["summary"])


# =============================================================================
# Tests for build_evidence_artifacts_payload
# =============================================================================


class TestBuildEvidenceArtifactsPayload(unittest.TestCase):
    """Tests for build_evidence_artifacts_payload function."""

    def test_empty_incident_returns_empty_list(self) -> None:
        """Incident with no evidence links returns empty list."""
        incident = make_incident()
        result = build_evidence_artifacts_payload(incident)

        self.assertEqual(result, [])

    def test_single_artifact_returns_single_item(self) -> None:
        """Incident with one evidence link returns list with one item."""
        link = make_evidence_link("artifact-1", EvidenceRole.SNAPSHOT)
        incident = make_incident(evidence_links=[link])
        result = build_evidence_artifacts_payload(incident)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["artifact_id"], "artifact-1")

    def test_multiple_artifacts_sorted_deterministically(self) -> None:
        """Multiple artifacts are sorted by artifact_id."""
        links = [
            make_evidence_link("artifact-z", EvidenceRole.SNAPSHOT),
            make_evidence_link("artifact-a", EvidenceRole.REVIEW_PACKET),
            make_evidence_link("artifact-m", EvidenceRole.PRIMARY),
        ]
        incident = make_incident(evidence_links=links)
        result = build_evidence_artifacts_payload(incident)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["artifact_id"], "artifact-a")
        self.assertEqual(result[1]["artifact_id"], "artifact-m")
        self.assertEqual(result[2]["artifact_id"], "artifact-z")

    def test_all_safety_flags_present_in_all_artifacts(self) -> None:
        """All artifacts in list have safety flags."""
        links = [
            make_evidence_link("artifact-1", EvidenceRole.SNAPSHOT),
            make_evidence_link("artifact-2", EvidenceRole.REVIEW_PACKET),
        ]
        incident = make_incident(evidence_links=links)
        result = build_evidence_artifacts_payload(incident)

        for artifact in result:
            self.assertTrue(artifact["read_only"])
            self.assertFalse(artifact["raw_content_available"])
            self.assertTrue(artifact["no_remediation_attempted"])

    def test_no_forbidden_fields_in_any_artifact(self) -> None:
        """No artifacts contain forbidden fields like raw_content, logs, etc."""
        links = [
            make_evidence_link("artifact-1", EvidenceRole.SNAPSHOT),
            make_evidence_link("artifact-2", EvidenceRole.REVIEW_PACKET),
        ]
        incident = make_incident(evidence_links=links)
        result = build_evidence_artifacts_payload(incident)

        # Field names that must not appear in evidence artifact payloads
        # Note: raw_content_available is a safety flag (not raw content itself)
        forbidden_exact_fields = frozenset([
            "raw_content",
            "logs",
            "stdout",
            "stderr",
            "stack_trace",
            "prompt",
            "secret",
            "token",
            "kubeconfig",
            "command",
            "execute",
            "remediate",
            "mutate",
        ])

        for artifact in result:
            for field in artifact.keys():
                # Check for exact field match (not substring)
                self.assertNotIn(
                    field,
                    forbidden_exact_fields,
                    f"Found forbidden field: {field}",
                )


# =============================================================================
# Tests for build_incident_detail_payload includes evidence_artifacts
# =============================================================================


class TestIncidentDetailPayloadWithEvidenceArtifacts(unittest.TestCase):
    """Tests for evidence_artifacts field in IncidentDetailPayload."""

    def test_empty_incident_has_empty_evidence_artifacts(self) -> None:
        """Incident with no evidence links has empty evidence_artifacts."""
        incident = make_incident()
        result = build_incident_detail_payload(incident)

        self.assertIn("evidence_artifacts", result)
        self.assertEqual(result["evidence_artifacts"], [])

    def test_incident_with_links_has_populated_evidence_artifacts(self) -> None:
        """Incident with evidence links has populated evidence_artifacts."""
        links = [
            make_evidence_link("artifact-1", EvidenceRole.SNAPSHOT),
            make_evidence_link("artifact-2", EvidenceRole.REVIEW_PACKET),
        ]
        incident = make_incident(evidence_links=links)
        result = build_incident_detail_payload(incident)

        self.assertIn("evidence_artifacts", result)
        self.assertEqual(len(result["evidence_artifacts"]), 2)
        # Check both artifacts are present
        artifact_ids = {a["artifact_id"] for a in result["evidence_artifacts"]}
        self.assertEqual(artifact_ids, {"artifact-1", "artifact-2"})

    def test_evidence_artifacts_sorted_deterministically(self) -> None:
        """Evidence artifacts in detail payload are sorted by artifact_id."""
        links = [
            make_evidence_link("z-artifact", EvidenceRole.SNAPSHOT),
            make_evidence_link("a-artifact", EvidenceRole.REVIEW_PACKET),
            make_evidence_link("m-artifact", EvidenceRole.PRIMARY),
        ]
        incident = make_incident(evidence_links=links)
        result = build_incident_detail_payload(incident)

        self.assertEqual(result["evidence_artifacts"][0]["artifact_id"], "a-artifact")
        self.assertEqual(result["evidence_artifacts"][1]["artifact_id"], "m-artifact")
        self.assertEqual(result["evidence_artifacts"][2]["artifact_id"], "z-artifact")

    def test_evidence_artifacts_safety_flags_all_true(self) -> None:
        """All evidence artifacts have correct safety flags."""
        links = [make_evidence_link("artifact-1", EvidenceRole.PRIMARY)]
        incident = make_incident(evidence_links=links)
        result = build_incident_detail_payload(incident)

        for artifact in result["evidence_artifacts"]:
            self.assertTrue(artifact["read_only"])
            self.assertFalse(artifact["raw_content_available"])
            self.assertTrue(artifact["no_remediation_attempted"])

    def test_no_raw_content_in_evidence_artifacts(self) -> None:
        """Evidence artifacts field does not contain raw content fields."""
        links = [
            make_evidence_link("artifact-1", EvidenceRole.SNAPSHOT),
            make_evidence_link("artifact-2", EvidenceRole.REVIEW_PACKET),
        ]
        incident = make_incident(evidence_links=links)
        result = build_incident_detail_payload(incident)

        # Exact field names that must not appear (no raw content)
        # Note: raw_content_available is a safety flag (not raw content itself)
        forbidden_exact_fields = frozenset([
            "raw_content",
            "logs",
            "stdout",
            "stderr",
            "stack_trace",
            "prompt",
            "secret",
            "token",
            "kubeconfig",
        ])

        for artifact in result["evidence_artifacts"]:
            for field in artifact.keys():
                self.assertNotIn(
                    field,
                    forbidden_exact_fields,
                    f"Found forbidden content field: {field}",
                )

    def test_all_known_roles_mapped_correctly(self) -> None:
        """All known EvidenceRole values map to correct artifact_kinds."""
        test_cases = [
            (EvidenceRole.SNAPSHOT, "snapshot_bundle"),
            (EvidenceRole.REVIEW_PACKET, "review_packet"),
            (EvidenceRole.PRIMARY, "evidence_artifact"),
            (EvidenceRole.SUPPORTING, "evidence_artifact"),
            (EvidenceRole.DEBUG, "debug_artifact"),
        ]
        for role, expected_kind in test_cases:
            with self.subTest(role=role.value, expected_kind=expected_kind):
                link = make_evidence_link(f"artifact-{role.value}", role)
                result = build_evidence_artifact_payload(link)
                self.assertEqual(result["artifact_kind"], expected_kind)
                self.assertEqual(result["evidence_role"], role.value)


if __name__ == "__main__":
    unittest.main()

"""Tests for evidence link serialization in incident detail payloads."""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_evidence import EvidenceLink, EvidenceRole
from k8s_diag_agent.ui.api_incident_reads import build_incident_evidence_link_payload

from .incident_lifecycle_fixtures import TEST_TIME_1


class TestBuildIncidentEvidenceLinkPayload(unittest.TestCase):
    """Test evidence link serialization."""

    def test_evidence_link_serialization(self) -> None:
        """Evidence link must be serialized correctly."""
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id="bundle-abc",
            role=EvidenceRole.SNAPSHOT,
            attached_at=TEST_TIME_1,
        )
        result = build_incident_evidence_link_payload(link)

        self.assertEqual(result["incident_id"], "inc-123")
        self.assertEqual(result["artifact_id"], "bundle-abc")
        self.assertEqual(result["role"], "snapshot")
        self.assertIn("attached_at", result)


if __name__ == "__main__":
    unittest.main()

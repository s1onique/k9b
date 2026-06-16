"""Tests for incident review packet markdown content and wording.

These tests verify:
- Packet content correctness
- Section ordering
- k9b-native evidence capture wording
- No sentinel patterns
- No placeholder text
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_review_packet import (
    generate_incident_review_packet,
)

from .incident_review_packet_fixtures import make_test_bundle


class TestPacketContent(unittest.TestCase):
    """Test packet content correctness."""

    def test_packet_format_is_markdown(self) -> None:
        """Packet should be valid markdown."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        # Check for markdown formatting elements
        self.assertTrue(packet.startswith("# k9b Incident Review Packet"))
        self.assertIn("## ", packet)  # Section headers
        self.assertIn("|", packet)  # Tables

    def test_packet_no_sentinel_patterns(self) -> None:
        """Packet must not contain sentinel patterns."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        sentinels = [
            "KUBE_SECRET_TOKEN_abc123",
            "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "api_key=sk-abcdefghijk",
            "client_secret=super_secret_value",
            "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        ]

        for sentinel in sentinels:
            self.assertNotIn(
                sentinel,
                packet,
                f"Packet contains sentinel: {sentinel}",
            )

    def test_packet_no_undefined_or_object_object(self) -> None:
        """Packet must not contain 'undefined' or '[object Object]'."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertNotIn("undefined", packet.lower())
        self.assertNotIn("[object Object]", packet)

    def test_packet_includes_self_contained_constraint(self) -> None:
        """Packet must include self-contained k9b-only constraint."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Self-Contained k9b-Only Constraint", packet)
        self.assertIn("Cline", packet)

    def test_packet_states_pod_logs_not_included(self) -> None:
        """Packet must explicitly state pod logs are not included."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Pod logs are NOT included", packet)

    def test_packet_states_evidence_not_root_cause(self) -> None:
        """Packet must state that evidence is NOT root cause."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Evidence is NOT root cause", packet)


if __name__ == "__main__":
    unittest.main()

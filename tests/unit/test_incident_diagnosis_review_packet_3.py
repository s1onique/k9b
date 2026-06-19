"""Unit tests for incident_diagnosis_review_packet module - lookup functions.

Tests cover:
- find_latest_review_packet function
- load_review_packet_summary function
- Bounded summary fields

These tests do NOT:
- Include raw artifact contents
- Include absolute paths
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    find_latest_review_packet,
    load_review_packet_summary,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_external_dir():
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# =============================================================================
# Lookup Tests
# =============================================================================


class TestFindLatestReviewPacket:
    """Tests for find_latest_review_packet function."""

    def test_returns_none_for_nonexistent_dir(self, temp_external_dir):
        """Prove function returns None for nonexistent directory."""
        result = find_latest_review_packet(temp_external_dir / "nonexistent", "test-incident")
        assert result is None

    def test_returns_none_for_no_packets(self, temp_external_dir):
        """Prove function returns None when no packets exist."""
        result = find_latest_review_packet(temp_external_dir, "test-incident")
        assert result is None

    def test_finds_existing_packet(self, temp_external_dir):
        """Prove function finds existing packet for incident."""
        # Write a test packet
        run_id = "auto-test-incident-20260619-080000-abc123"
        packet_path = temp_external_dir / f"{run_id}-diagnosis-review-packet.json"
        packet_path.write_text('{"schema_version": "1.0"}', encoding="utf-8")

        result = find_latest_review_packet(temp_external_dir, "test-incident")

        assert result is not None
        assert result["incident_id"] == "test-incident"
        assert result["name"] == f"{run_id}-diagnosis-review-packet.json"


class TestLoadReviewPacketSummary:
    """Tests for load_review_packet_summary function."""

    def test_returns_none_for_no_packets(self, temp_external_dir):
        """Prove function returns None when no packets exist."""
        result = load_review_packet_summary(temp_external_dir, "test-incident")
        assert result is None

    def test_loads_bounded_summary(self, temp_external_dir):
        """Prove function loads bounded summary fields."""
        # Write a test packet
        run_id = "auto-test-incident-20260619-080000-abc123"
        packet_path = temp_external_dir / f"{run_id}-diagnosis-review-packet.json"

        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "test-incident",
            "run_id": run_id,
            "collector_run_id": "collector-1",
            "generated_at": "2026-06-19T08:00:00+00:00",
            "eligibility": {
                "eligible": True,
                "reason": "active_incident",
            },
            "loop_result": {
                "decision": "run_allowed_read_only_checks",
                "checks_requested": 3,
                "checks_run": 3,
                "checks_skipped": 0,
                "checks_rejected": 0,
            },
        }
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = load_review_packet_summary(temp_external_dir, "test-incident")

        assert result is not None
        assert result["incident_id"] == "test-incident"
        assert result["run_id"] == run_id
        assert result["decision"] == "run_allowed_read_only_checks"
        assert result["checks_requested"] == 3
        assert result["checks_run"] == 3
        assert result["eligible"] is True
        assert result["eligibility_reason"] == "active_incident"

    def test_summary_does_not_include_raw_contents(self, temp_external_dir):
        """Prove summary does not include raw case file or runner results."""
        # Write a test packet with raw contents
        run_id = "auto-test-incident-20260619-080000-abc123"
        packet_path = temp_external_dir / f"{run_id}-diagnosis-review-packet.json"

        packet_data = {
            "schema_version": "1.0",
            "incident_id": "test-incident",
            "run_id": run_id,
            "collector_run_id": "collector-1",
            "generated_at": "2026-06-19T08:00:00+00:00",
            "eligibility": {
                "eligible": True,
                "reason": "active_incident",
            },
            "loop_result": {
                "decision": "run_allowed_read_only_checks",
                "checks_requested": 3,
                "checks_run": 3,
                "checks_skipped": 0,
                "checks_rejected": 0,
            },
            "raw_case_file": {"secret_data": "should_not_appear"},
            "runner_result": {"secret_result": "should_not_appear"},
        }
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = load_review_packet_summary(temp_external_dir, "test-incident")

        assert result is not None
        # Summary should only have expected fields
        assert "raw_case_file" not in result
        assert "runner_result" not in result

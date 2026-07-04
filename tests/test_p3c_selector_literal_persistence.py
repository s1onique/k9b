"""Tests for P3c selector_literal persistence from P2b injection.

These tests verify that P3c correctly reads P2b injection evidence
and populates the selector_literal for P4c root-cause extraction.

This fixes the contract leak where P4c receives generic scheduler messages
but cannot prove the exact injected selector key/value.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.k9b_otel_demo_lab_k8s_detection_phase import (
    _populate_selector_literal_from_p2b,
)


class TestPopulateSelectorLiteralFromP2b:
    """Test _populate_selector_literal_from_p2b helper."""

    def test_populates_selector_from_p2b_evidence(self, tmp_path: Path) -> None:
        """Populates selector_literal from P2b injection-evidence.json."""
        # Create P2b injection evidence
        p2b_dir = tmp_path / "phase2-injected" / "p2b-k8s-injection"
        p2b_dir.mkdir(parents=True)

        injection_evidence = {
            "scenario": "unschedulable-shipping-rollout",
            "method": "nodeSelector_patch",
            "node_selector": {
                "k9b.dev/otel-lab-node": "missing",
            },
        }
        (p2b_dir / "injection-evidence.json").write_text(json.dumps(injection_evidence))

        # Call the helper
        evidence: dict[str, Any] = {}
        _populate_selector_literal_from_p2b(tmp_path, evidence)

        # Verify selector populated
        assert evidence["selector_literal"] == "k9b.dev/otel-lab-node=missing"
        assert evidence["selector_key"] == "k9b.dev/otel-lab-node"
        assert evidence["selector_value"] == "missing"
        assert evidence["selector_source"] == "p2b_injection"

    def test_handles_missing_p2b_evidence_gracefully(self, tmp_path: Path) -> None:
        """Handles missing P2b evidence gracefully."""
        evidence: dict[str, Any] = {}
        _populate_selector_literal_from_p2b(tmp_path, evidence)

        assert evidence["selector_literal"] is None
        assert evidence["selector_key"] is None
        assert evidence["selector_value"] is None
        assert evidence["selector_source"] is None

    def test_handles_invalid_json_gracefully(self, tmp_path: Path) -> None:
        """Handles invalid JSON in P2b evidence gracefully."""
        p2b_dir = tmp_path / "phase2-injected" / "p2b-k8s-injection"
        p2b_dir.mkdir(parents=True)
        (p2b_dir / "injection-evidence.json").write_text("invalid json{{{")

        evidence: dict[str, Any] = {}
        _populate_selector_literal_from_p2b(tmp_path, evidence)

        assert evidence["selector_literal"] is None
        assert evidence["selector_source"] is None

    def test_handles_empty_node_selector(self, tmp_path: Path) -> None:
        """Handles empty node_selector in P2b evidence with fallback to constants."""
        p2b_dir = tmp_path / "phase2-injected" / "p2b-k8s-injection"
        p2b_dir.mkdir(parents=True)

        injection_evidence = {
            "scenario": "unschedulable-shipping-rollout",
            "method": "nodeSelector_patch",
            "node_selector": {},
        }
        (p2b_dir / "injection-evidence.json").write_text(json.dumps(injection_evidence))

        evidence: dict[str, Any] = {}
        _populate_selector_literal_from_p2b(tmp_path, evidence)

        # Falls back to constants
        assert evidence["selector_literal"] == "k9b.dev/otel-lab-node=missing"
        assert evidence["selector_key"] == "k9b.dev/otel-lab-node"
        assert evidence["selector_value"] == "missing"
        assert evidence["selector_source"] == "p2b_injection"

    def test_uses_exact_key_from_constants(self, tmp_path: Path) -> None:
        """Uses the exact key from constants, not from node_selector dict."""
        # Even if the dict has a different key, we use the constant
        p2b_dir = tmp_path / "phase2-injected" / "p2b-k8s-injection"
        p2b_dir.mkdir(parents=True)

        injection_evidence = {
            "scenario": "unschedulable-shipping-rollout",
            "node_selector": {
                "k9b.dev/otel-lab-node": "missing",
            },
        }
        (p2b_dir / "injection-evidence.json").write_text(json.dumps(injection_evidence))

        evidence: dict[str, Any] = {}
        _populate_selector_literal_from_p2b(tmp_path, evidence)

        # Should use constant key
        assert evidence["selector_key"] == "k9b.dev/otel-lab-node"
        assert evidence["selector_value"] == "missing"

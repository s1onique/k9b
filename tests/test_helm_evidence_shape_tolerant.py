#!/usr/bin/env python3
"""Tests for shape-tolerant Helm status parsing in k9b_cnpg_live_lab_helm_evidence.py.

Tests the fix for the bug where collect_helm_evidence crashed with:
    AttributeError: 'str' object has no attribute 'get'
when Helm status JSON had info.status as a string (e.g., "deployed")
instead of a nested dict.

The Helm v3 status JSON shape:
    {"info": {"status": "deployed"}}  # string form (normal)

NOT the legacy/incorrect shape:
    {"info": {"status": {"status": "deployed"}}}  # nested dict form
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.k9b_cnpg_live_lab_helm_evidence import (
    _extract_helm_release_status,
    _extract_helm_revision,
)


class TestExtractHelmReleaseStatus:
    """Tests for shape-tolerant Helm release status extraction."""

    def test_extracts_string_status(self) -> None:
        """Should extract status when info.status is a string (Helm v3 normal form)."""
        status_data: dict[str, object] = {"info": {"status": "deployed"}}
        assert _extract_helm_release_status(status_data) == "deployed"

    def test_extracts_string_status_pending_install(self) -> None:
        """Should extract pending-install status."""
        status_data: dict[str, object] = {"info": {"status": "pending-install"}}
        assert _extract_helm_release_status(status_data) == "pending-install"

    def test_extracts_string_status_failed(self) -> None:
        """Should extract failed status."""
        status_data: dict[str, object] = {"info": {"status": "failed"}}
        assert _extract_helm_release_status(status_data) == "failed"

    def test_extracts_nested_dict_status(self) -> None:
        """Should extract status when info.status is a nested dict with 'status' key."""
        status_data: dict[str, object] = {"info": {"status": {"status": "deployed"}}}
        assert _extract_helm_release_status(status_data) == "deployed"

    def test_extracts_nested_dict_code(self) -> None:
        """Should extract status when info.status is a nested dict with 'code' key."""
        status_data: dict[str, object] = {"info": {"status": {"code": "deployed"}}}
        assert _extract_helm_release_status(status_data) == "deployed"

    def test_extracts_nested_dict_prefers_status_over_code(self) -> None:
        """Should prefer 'status' key over 'code' when both present."""
        status_data: dict[str, object] = {"info": {"status": {"status": "deployed", "code": "superseded"}}}
        assert _extract_helm_release_status(status_data) == "deployed"

    def test_returns_none_for_missing_info(self) -> None:
        """Should return None when info key is missing."""
        status_data: dict[str, object] = {}
        assert _extract_helm_release_status(status_data) is None

    def test_returns_none_for_non_dict_info(self) -> None:
        """Should return None when info is not a dict (e.g., string, number)."""
        status_data: dict[str, object] = {"info": "not-a-dict"}
        assert _extract_helm_release_status(status_data) is None

    def test_returns_none_for_missing_status(self) -> None:
        """Should return None when info.status is missing."""
        status_data: dict[str, object] = {"info": {"other": "value"}}
        assert _extract_helm_release_status(status_data) is None

    def test_returns_none_for_none_status(self) -> None:
        """Should return None when info.status is explicitly None."""
        status_data: dict[str, object] = {"info": {"status": None}}
        assert _extract_helm_release_status(status_data) is None

    def test_handles_empty_info(self) -> None:
        """Should return None when info is empty dict."""
        status_data: dict[str, object] = {"info": {}}
        assert _extract_helm_release_status(status_data) is None

    def test_handles_real_helm_status_output(self) -> None:
        """Should handle real Helm status JSON output (string form)."""
        # Real Helm v3 status output
        status_data: dict[str, object] = {
            "name": "k9b",
            "namespace": "default",
            "revision": "1",
            "status": "deployed",
            "info": {
                "first_deployed": "2024-01-15T10:00:00.000Z",
                "last_deployed": "2024-01-15T10:00:00.000Z",
                "deleted": "",
                "status": "deployed",
                "resources": "",
                "notes": "k9b backend installed successfully."
            }
        }
        assert _extract_helm_release_status(status_data) == "deployed"


class TestExtractHelmRevision:
    """Tests for Helm revision extraction."""

    def test_extracts_revision_from_last_deployed(self) -> None:
        """Should extract revision from last_deployed.Revision."""
        status_data: dict[str, object] = {
            "info": {
                "last_deployed": {"Revision": 3}
            }
        }
        assert _extract_helm_revision(status_data) == 3

    def test_extracts_revision_from_first_charted(self) -> None:
        """Should extract revision from first_charted.Revision when last_deployed absent."""
        status_data: dict[str, object] = {
            "info": {
                "first_charted": {"Revision": 5}
            }
        }
        assert _extract_helm_revision(status_data) == 5

    def test_prefers_last_deployed_over_first_charted(self) -> None:
        """Should prefer last_deployed over first_charted when both present."""
        status_data: dict[str, object] = {
            "info": {
                "last_deployed": {"Revision": 3},
                "first_charted": {"Revision": 1}
            }
        }
        assert _extract_helm_revision(status_data) == 3

    def test_extracts_string_revision(self) -> None:
        """Should handle revision as string (some Helm versions)."""
        status_data: dict[str, object] = {
            "info": {
                "last_deployed": {"Revision": "2"}
            }
        }
        assert _extract_helm_revision(status_data) == 2

    def test_returns_none_for_missing_info(self) -> None:
        """Should return None when info is missing."""
        status_data: dict[str, object] = {}
        assert _extract_helm_revision(status_data) is None

    def test_returns_none_for_missing_revision(self) -> None:
        """Should return None when neither last_deployed nor first_charted have Revision."""
        status_data: dict[str, object] = {
            "info": {
                "last_deployed": {"other": "value"}
            }
        }
        assert _extract_helm_revision(status_data) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

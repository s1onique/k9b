#!/usr/bin/env python3
"""Tests for image preflight node operations.

Tests:
- Node pull event classification
- TLS error classification
- Node pull result structures
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from k9b_cnpg_image_preflight_node import classify_pull_failure
from k9b_cnpg_image_preflight_types import (
    FAIL_NODE_IMAGE_MISSING,
    FAIL_NODE_NETWORK,
    FAIL_NODE_PULL_BACKOFF,
    FAIL_NODE_TLS,
    FAIL_NODE_UNAUTHORIZED,
    NodePullResult,
)


class TestNodePullResult:
    """Tests for NodePullResult data class."""

    def test_to_dict_contains_all_fields(self) -> None:
        """Should serialize all fields to dict."""
        result = NodePullResult(
            component="frontend",
            image_ref="registry.spbnix.com/gitinsky/k9b-frontend:ecacd81",
            pod_name="img-preflight-frontend-123456",
            success=False,
            failure_class=FAIL_NODE_PULL_BACKOFF,
            pod_phase="Failed",
            container_waiting_reason="ImagePullBackOff",
            container_waiting_message="failed to pull image",
            events_summary='[{"reason": "Failed"}]',
            timestamp="2026-06-23T08:00:00Z",
        )
        d = result.to_dict()
        assert d["component"] == "frontend"
        assert d["image_ref"] == "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81"
        assert d["pod_name"] == "img-preflight-frontend-123456"
        assert d["success"] is False
        assert d["failure_class"] == FAIL_NODE_PULL_BACKOFF

    def test_to_dict_truncates_events_summary(self) -> None:
        """Should truncate events_summary to 500 chars."""
        long_events = "x" * 1000
        result = NodePullResult(
            component="frontend",
            image_ref="registry.spbnix.com/gitinsky/k9b-frontend:ecacd81",
            pod_name="test",
            success=True,
            events_summary=long_events,
            timestamp="2026-06-23T08:00:00Z",
        )
        d = result.to_dict()
        assert len(d["events_summary"]) <= 500


class TestNodePullEventClassification:
    """Tests for node pull failure event classification."""

    def test_parses_imagepullbackoff_with_manifest_unknown(self) -> None:
        """Should detect manifest unknown in ImagePullBackOff."""
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "failed to pull and unpack image: failed to resolve reference: registry.spbnix.com/gitinsky/k9b-frontend:ecacd81: manifest unknown",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_IMAGE_MISSING
        assert "manifest unknown" in message.lower()

    def test_parses_errimagepull_with_not_found(self) -> None:
        """Should detect not found in ErrImagePull."""
        events = {
            "items": [{
                "reason": "ErrImagePull",
                "message": "image not found in registry",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_IMAGE_MISSING

    def test_parses_unauthorized(self) -> None:
        """Should detect unauthorized."""
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "unauthorized: authentication required",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_UNAUTHORIZED

    def test_parses_forbidden(self) -> None:
        """Should detect forbidden/denied."""
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "access denied or forbidden",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_UNAUTHORIZED

    def test_parses_tls_error(self) -> None:
        """Should detect TLS/certificate failures."""
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "x509: certificate signed by unknown authority",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_TLS

    def test_parses_network_error(self) -> None:
        """Should detect network/DNS failures exactly as node_registry_network_error."""
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "dial tcp: lookup registry.spbnix.com: no such host",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_NETWORK, f"Expected {FAIL_NODE_NETWORK}, got {failure_class}"

    def test_defaults_to_pull_backoff(self) -> None:
        """Should default to node_image_pull_backoff for unknown reasons."""
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "some pull error",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_PULL_BACKOFF


class TestNodePullDescribeClassification:
    """Tests for kubectl describe output classification."""

    def test_parses_imagepullbackoff(self) -> None:
        """Should parse ImagePullBackOff from describe output."""
        describe = """
Name:             img-preflight-frontend-123
Namespace:        k9b-cnpg-lab-123
Status:           Failed
Conditions:
  Type           Status
  Init Container Ready  True
Ready:            False
Containers:
  test:
    State:          Waiting
      Reason:       ImagePullBackOff
    Message:        Back-off pulling image "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81"
"""
        failure_class, message = classify_pull_failure({"items": []}, "test", describe)
        assert failure_class == FAIL_NODE_PULL_BACKOFF

    def test_parses_errimagepull_with_manifest_unknown(self) -> None:
        """Should parse ErrImagePull with manifest unknown."""
        describe = """
Name:             img-preflight-frontend-123
Status:           Failed
Containers:
  test:
    State:          Waiting
      Reason:       ErrImagePull
    Message:        failed to resolve reference: manifest unknown
"""
        failure_class, message = classify_pull_failure({"items": []}, "test", describe)
        assert failure_class in (FAIL_NODE_IMAGE_MISSING, FAIL_NODE_PULL_BACKOFF)

    def test_no_match_for_empty_output(self) -> None:
        """Should return empty for empty/nomatch output."""
        describe = "No events."
        failure_class, message = classify_pull_failure({"items": []}, "test", describe)
        assert failure_class == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

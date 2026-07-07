"""Unit tests for alertmanager_source_probe module.

Tests the _parse_status_response function with both live Alertmanager shapes
and wrapped shapes to ensure correct parsing of /api/v2/status responses.

Run with: python -m pytest tests/unit/test_alertmanager_source_probe.py -v
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.alertmanager_source_probe import (
    _compute_config_sha256,
    _parse_status_response,
)


class TestParseStatusResponseLiveShape(unittest.TestCase):
    """Tests for top-level (live) Alertmanager /api/v2/status shape.

    Live Alertmanager returns:
    {
        "cluster": {...},
        "config": {...},
        "uptime": "12345s",
        "versionInfo": {...}
    }
    """

    def test_live_shape_extracts_version(self) -> None:
        """Live shape must extract version from versionInfo."""
        response = {
            "cluster": {
                "status": "ready",
                "peers": [
                    {"name": "peer-1", "address": "10.0.0.1:9094"},
                    {"name": "peer-2", "address": "10.0.0.2:9094"},
                ]
            },
            "config": {
                "original": "route:\n  receiver: default\nreceivers:\n- name: default"
            },
            "uptime": "12345s",
            "versionInfo": {
                "version": "0.31.1",
                "revision": "abc123",
                "branch": "HEAD",
                "buildUser": "",
                "buildDate": "",
                "goVersion": "go1.21"
            }
        }
        result = _parse_status_response(response)

        self.assertEqual(result["version"], "0.31.1")

    def test_live_shape_extracts_cluster_status(self) -> None:
        """Live shape must extract cluster status."""
        response = {
            "cluster": {
                "status": "ready",
                "peers": [
                    {"name": "peer-1", "address": "10.0.0.1:9094"},
                    {"name": "peer-2", "address": "10.0.0.2:9094"},
                ]
            },
            "config": {
                "original": "route:\n  receiver: default\nreceivers:\n- name: default"
            },
            "versionInfo": {
                "version": "0.31.1"
            }
        }
        result = _parse_status_response(response)

        self.assertEqual(result["cluster_status"], "ready")

    def test_live_shape_extracts_peer_count(self) -> None:
        """Live shape must extract correct peer count."""
        response = {
            "cluster": {
                "status": "ready",
                "peers": [
                    {"name": "peer-1", "address": "10.0.0.1:9094"},
                    {"name": "peer-2", "address": "10.0.0.2:9094"},
                ]
            },
            "config": {"original": "route:\n  receiver: default"},
            "versionInfo": {"version": "0.31.1"}
        }
        result = _parse_status_response(response)

        self.assertEqual(result["peer_count"], 2)

    def test_live_shape_extracts_config_sha256(self) -> None:
        """Live shape must compute config_sha256 without emitting raw config."""
        response = {
            "cluster": {"status": "ready", "peers": []},
            "config": {
                "original": "route:\n  receiver: default\nreceivers:\n- name: default"
            },
            "versionInfo": {"version": "0.31.1"}
        }
        result = _parse_status_response(response)

        self.assertIsNotNone(result["config_sha256"])
        self.assertIsInstance(result["config_sha256"], str)
        self.assertEqual(len(result["config_sha256"]), 16)  # Truncated to 16 chars

    def test_live_shape_extracts_uptime(self) -> None:
        """Live shape must extract uptime when present."""
        response = {
            "cluster": {"status": "ready", "peers": []},
            "config": {"original": "route:\n  receiver: default"},
            "uptime": "123456s",
            "versionInfo": {"version": "0.31.1"}
        }
        result = _parse_status_response(response)

        self.assertEqual(result["uptime"], "123456s")

    def test_live_shape_no_raw_config_in_result(self) -> None:
        """Result must not contain raw config data."""
        response = {
            "cluster": {"status": "ready", "peers": []},
            "config": {
                "original": "route:\n  receiver: default\nreceivers:\n- name: default\n- name: bot\n  webhook_configs:\n  - url: https://example.com/bot_token=abc123&chat_id=12345"
            },
            "versionInfo": {"version": "0.31.1"}
        }
        result = _parse_status_response(response)

        # Must not contain raw config
        self.assertNotIn("config", result)
        self.assertNotIn("original", result)
        self.assertNotIn("route:", str(result))
        self.assertNotIn("receivers:", str(result))
        self.assertNotIn("bot_token", str(result))
        self.assertNotIn("chat_id", str(result))

    def test_live_shape_no_peers_returns_zero_count(self) -> None:
        """Empty peers list must return 0 peer_count."""
        response = {
            "cluster": {"status": "ready", "peers": []},
            "config": {"original": "route:\n  receiver: default"},
            "versionInfo": {"version": "0.31.1"}
        }
        result = _parse_status_response(response)

        self.assertEqual(result["peer_count"], 0)


class TestParseStatusResponseWrappedShape(unittest.TestCase):
    """Tests for wrapped Alertmanager /api/v2/status shape.

    Wrapped shape returns:
    {
        "data": {
            "cluster": {...},
            "config": {...},
            "uptime": "12345s",
            "versionInfo": {...}
        }
    }
    """

    def test_wrapped_shape_extracts_version(self) -> None:
        """Wrapped shape must extract version from data.versionInfo."""
        response = {
            "data": {
                "cluster": {
                    "status": "ready",
                    "peers": [
                        {"name": "peer-1", "address": "10.0.0.1:9094"},
                        {"name": "peer-2", "address": "10.0.0.2:9094"},
                    ]
                },
                "config": {
                    "original": "route:\n  receiver: default\nreceivers:\n- name: default"
                },
                "uptime": "12345s",
                "versionInfo": {
                    "version": "0.31.1",
                    "revision": "abc123"
                }
            }
        }
        result = _parse_status_response(response)

        self.assertEqual(result["version"], "0.31.1")

    def test_wrapped_shape_extracts_cluster_status(self) -> None:
        """Wrapped shape must extract cluster status from data.cluster."""
        response = {
            "data": {
                "cluster": {"status": "ready", "peers": []},
                "config": {"original": "route:\n  receiver: default"},
                "versionInfo": {"version": "0.31.1"}
            }
        }
        result = _parse_status_response(response)

        self.assertEqual(result["cluster_status"], "ready")

    def test_wrapped_shape_extracts_peer_count(self) -> None:
        """Wrapped shape must extract correct peer count."""
        response = {
            "data": {
                "cluster": {
                    "status": "ready",
                    "peers": [
                        {"name": "peer-1", "address": "10.0.0.1:9094"},
                        {"name": "peer-2", "address": "10.0.0.2:9094"},
                    ]
                },
                "config": {"original": "route:\n  receiver: default"},
                "versionInfo": {"version": "0.31.1"}
            }
        }
        result = _parse_status_response(response)

        self.assertEqual(result["peer_count"], 2)

    def test_wrapped_shape_extracts_config_sha256(self) -> None:
        """Wrapped shape must compute config_sha256 without emitting raw config."""
        response = {
            "data": {
                "cluster": {"status": "ready", "peers": []},
                "config": {
                    "original": "route:\n  receiver: default\nreceivers:\n- name: default"
                },
                "versionInfo": {"version": "0.31.1"}
            }
        }
        result = _parse_status_response(response)

        self.assertIsNotNone(result["config_sha256"])
        self.assertIsInstance(result["config_sha256"], str)

    def test_wrapped_shape_no_raw_config_in_result(self) -> None:
        """Result must not contain raw config data."""
        response = {
            "data": {
                "cluster": {"status": "ready", "peers": []},
                "config": {
                    "original": "route:\n  receiver: default\nreceivers:\n- name: bot\n  webhook_configs:\n  - url: https://example.com/bot_token=secret&chat_id=12345"
                },
                "versionInfo": {"version": "0.31.1"}
            }
        }
        result = _parse_status_response(response)

        # Must not contain raw config
        self.assertNotIn("config", result)
        self.assertNotIn("original", result)
        self.assertNotIn("route:", str(result))
        self.assertNotIn("bot_token", str(result))


class TestParseStatusResponseEdgeCases(unittest.TestCase):
    """Edge case tests for _parse_status_response."""

    def test_missing_cluster_returns_defaults(self) -> None:
        """Missing cluster info must return None/0 defaults."""
        response = {
            "versionInfo": {"version": "0.31.1"}
        }
        result = _parse_status_response(response)

        self.assertIsNone(result.get("cluster_status"))
        self.assertEqual(result.get("peer_count", 0), 0)

    def test_missing_version_info_returns_none(self) -> None:
        """Missing versionInfo must return None for version."""
        response = {
            "cluster": {"status": "ready", "peers": []}
        }
        result = _parse_status_response(response)

        self.assertIsNone(result.get("version"))

    def test_missing_config_returns_none_hash(self) -> None:
        """Missing config must return None for config_sha256."""
        response = {
            "cluster": {"status": "ready", "peers": []},
            "versionInfo": {"version": "0.31.1"}
        }
        result = _parse_status_response(response)

        self.assertIsNone(result.get("config_sha256"))

    def test_empty_config_original_returns_none_hash(self) -> None:
        """Empty config.original must return None for config_sha256."""
        response = {
            "cluster": {"status": "ready", "peers": []},
            "config": {"original": ""},
            "versionInfo": {"version": "0.31.1"}
        }
        result = _parse_status_response(response)

        self.assertIsNone(result.get("config_sha256"))

    def test_invalid_response_returns_empty_dict(self) -> None:
        """Invalid response must return empty dict with defaults."""
        response: dict[str, object] = {}
        result = _parse_status_response(response)

        self.assertEqual(result.get("version"), None)
        self.assertEqual(result.get("peer_count", 0), 0)


class TestComputeConfigSha256(unittest.TestCase):
    """Tests for _compute_config_sha256 function."""

    def test_same_config_produces_same_hash(self) -> None:
        """Same config must produce identical hash."""
        config1 = "route:\n  receiver: default"
        config2 = "route:\n  receiver: default"
        hash1 = _compute_config_sha256(config1)
        hash2 = _compute_config_sha256(config2)

        self.assertEqual(hash1, hash2)

    def test_different_config_produces_different_hash(self) -> None:
        """Different configs must produce different hashes."""
        config1 = "route:\n  receiver: default"
        config2 = "route:\n  receiver: other"
        hash1 = _compute_config_sha256(config1)
        hash2 = _compute_config_sha256(config2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_is_16_chars(self) -> None:
        """Hash must be truncated to 16 characters."""
        config = "route:\n  receiver: default"
        hash_val = _compute_config_sha256(config)

        self.assertEqual(len(hash_val), 16)

    def test_none_input_returns_hash(self) -> None:
        """None input produces a hash (json.dumps converts None to 'null')."""
        result = _compute_config_sha256(None)

        # json.dumps(None) returns "null", so we get a hash of "null"
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 16)

    def test_sensitive_strings_not_in_hash(self) -> None:
        """Sensitive config strings must not appear in hash input (they're in config, not hash)."""
        # The hash is computed from the config string, so it will contain those chars
        # But the hash itself is a hex string, so we check it doesn't contain 'route:' etc.
        config = "route:\n  receiver: bot\n  webhook_configs:\n  - url: https://example.com/bot_token=abc123&chat_id=12345"
        hash_val = _compute_config_sha256(config)

        # The hash is just hex chars, so it won't contain 'route:' etc
        self.assertNotIn("route", hash_val)
        self.assertNotIn("token", hash_val)


class TestLiveStatusFixtures(unittest.TestCase):
    """Tests using fixture shapes from alertmanager-operated and kube-prometheus-stack.

    These tests verify the ACT-K9B-ALERTMANAGER-LIVE-IDENTITY-EVIDENCE01 acceptance criteria:
    - Probe packet shows alertmanager_version: "0.31.1"
    - Probe packet shows cluster_status: "ready"
    - Probe packet shows peer_count: 2
    - Probe packet shows non-null config_sha256
    - Raw config strings are NOT emitted in packet JSON
    """

    def test_alertmanager_operated_fixture(self) -> None:
        """Simulated alertmanager-operated live status response."""
        # This represents the live status from alertmanager-operated service
        response = {
            "cluster": {
                "status": "ready",
                "peers": [
                    {"name": "alertmanager-operated-0", "address": "10.1.0.5:9094"},
                    {"name": "alertmanager-operated-1", "address": "10.1.0.6:9094"},
                ]
            },
            "config": {
                "original": "route:\n  receiver: default\nreceivers:\n- name: default"
            },
            "uptime": "864000s",
            "versionInfo": {
                "version": "0.31.1",
                "revision": "ae07e2fd6af675b2f8e41f38324d8096f6a9b6cf",
                "branch": "HEAD",
                "buildUser": "root@b5f8a5a1f514",
                "buildDate": "20241220-15:50:44",
                "goVersion": "go1.22.10"
            }
        }
        result = _parse_status_response(response)

        # Acceptance criteria
        self.assertEqual(result["version"], "0.31.1")
        self.assertEqual(result["cluster_status"], "ready")
        self.assertEqual(result["peer_count"], 2)
        self.assertIsNotNone(result["config_sha256"])

        # Must NOT emit raw config
        self.assertNotIn("config", result)
        self.assertNotIn("original", result)
        self.assertNotIn("route:", str(result))

    def test_kube_prometheus_stack_alertmanager_fixture(self) -> None:
        """Simulated kube-prometheus-stack-alertmanager live status response.

        This should have the same cluster identity as alertmanager-operated
        (same cluster.name, same peers, same version revision, same config).
        """
        response = {
            "cluster": {
                "status": "ready",
                "peers": [
                    {"name": "alertmanager-operated-0", "address": "10.1.0.5:9094"},
                    {"name": "alertmanager-operated-1", "address": "10.1.0.6:9094"},
                ]
            },
            "config": {
                "original": "route:\n  receiver: default\nreceivers:\n- name: default"
            },
            "uptime": "863950s",  # Slightly different uptime (different pod)
            "versionInfo": {
                "version": "0.31.1",
                "revision": "ae07e2fd6af675b2f8e41f38324d8096f6a9b6cf",  # Same revision
                "branch": "HEAD",
                "buildUser": "root@b5f8a5a1f514",
                "buildDate": "20241220-15:50:44",
                "goVersion": "go1.22.10"
            }
        }
        result = _parse_status_response(response)

        # Acceptance criteria
        self.assertEqual(result["version"], "0.31.1")
        self.assertEqual(result["cluster_status"], "ready")
        self.assertEqual(result["peer_count"], 2)
        self.assertIsNotNone(result["config_sha256"])

        # Must NOT emit raw config
        self.assertNotIn("config", result)
        self.assertNotIn("original", result)
        self.assertNotIn("route:", str(result))

    def test_same_alertmanager_cluster_same_config_hash(self) -> None:
        """Both sources pointing to same Alertmanager cluster must have same config_sha256."""
        config = "route:\n  receiver: default\nreceivers:\n- name: default"

        # alertmanager-operated response
        response1 = {
            "cluster": {"status": "ready", "peers": [{"name": "am-0"}, {"name": "am-1"}]},
            "config": {"original": config},
            "versionInfo": {"version": "0.31.1", "revision": "abc123"}
        }

        # kube-prometheus-stack-alertmanager response (same config)
        response2 = {
            "cluster": {"status": "ready", "peers": [{"name": "am-0"}, {"name": "am-1"}]},
            "config": {"original": config},
            "versionInfo": {"version": "0.31.1", "revision": "abc123"}
        }

        result1 = _parse_status_response(response1)
        result2 = _parse_status_response(response2)

        # Both should have same config_sha256
        self.assertEqual(result1["config_sha256"], result2["config_sha256"])


if __name__ == "__main__":
    unittest.main()

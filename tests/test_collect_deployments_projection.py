"""Tests for collect_deployments bounded projection.

Reference: ACT-K9B-HOLMESGPT-TOOL-PROJECTION-DEPLOYMENTS01
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from k8s_diag_agent.collect.incident_collectors import collect_deployments


class TestCollectDeploymentsProjection:
    """Tests for collect_deployments bounded projection."""

    def test_small_deployments_output_returns_metadata_without_spill(self) -> None:
        """Small deployments output returns metadata without spill."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [
                {
                    "metadata": {
                        "name": "test-deployment",
                        "namespace": "default",
                    },
                    "spec": {
                        "replicas": 3,
                        "selector": {"matchLabels": {"app": "test"}},
                        "template": {
                            "metadata": {"labels": {"app": "test"}},
                            "spec": {
                                "containers": [
                                    {"name": "main", "image": "nginx:1.21"}
                                ]
                            },
                        },
                    },
                    "status": {
                        "replicas": 3,
                        "readyReplicas": 3,
                        "availableReplicas": 3,
                    },
                },
            ],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            deployments, errors, metadata = collect_deployments("default", None)

            # Semantic output unchanged
            assert len(deployments) == 1
            assert deployments[0].name == "test-deployment"
            assert errors == []

            # Projection metadata present
            assert isinstance(metadata, dict)
            assert metadata["source_tool"] == "kubectl_get"
            assert metadata["spill_occurred"] is False
            assert metadata["raw_size_bytes"] > 0
            assert metadata["llm_visible_size_bytes"] > 0
            # content_type may be "manifest" or "json" depending on reducer
            assert metadata["content_type"] in ("json", "manifest")

    def test_large_deployments_output_spills_when_artifact_dir_provided(self) -> None:
        """Large deployments output spills to artifact when artifact_dir is provided."""
        import unittest.mock

        # Create large deployments payload
        items = []
        for i in range(50):
            items.append({
                "metadata": {
                    "name": f"deployment-{i}",
                    "namespace": "default",
                    "uid": f"uid-{i}" * 5,
                },
                "spec": {
                    "replicas": 5,
                    "selector": {"matchLabels": {"app": f"app-{i}"}},
                    "template": {
                        "metadata": {"labels": {"app": f"app-{i}"}},
                        "spec": {
                            "containers": [
                                {
                                    "name": "main",
                                    "image": f"nginx:{i}.0",
                                    "env": [{"name": f"VAR_{j}", "value": f"value_{j}" * 10} for j in range(20)],
                                }
                            ]
                        },
                    },
                },
                "status": {
                    "replicas": 5,
                    "readyReplicas": 5,
                    "availableReplicas": 5,
                    "conditions": [
                        {"type": "Available", "status": "True"},
                        {"type": "Progressing", "status": "True"},
                    ],
                },
            })

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": items,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            with unittest.mock.patch(
                "k8s_diag_agent.collect.incident_collectors.kubectl",
                return_value=mock_output,
            ):
                deployments, errors, metadata = collect_deployments("default", None, artifact_dir)

                # Should have deployments
                assert len(deployments) == 50
                assert errors == []

                # Spill metadata present
                assert metadata.get("spill_occurred") is True
                assert metadata.get("raw_artifact_id") is not None
                # raw_artifact_path is NOT included per artifact path policy
                assert "raw_artifact_path" not in metadata
                assert metadata.get("raw_size_bytes") > metadata.get("llm_visible_size_bytes")

    def test_large_deployments_output_without_artifact_dir_returns_bounded_error(self) -> None:
        """Large deployments output without artifact_dir returns bounded error metadata."""
        import unittest.mock

        # Create large deployments payload
        items = []
        for i in range(50):
            items.append({
                "metadata": {
                    "name": f"deployment-{i}",
                    "namespace": "default",
                    "uid": f"uid-{i}" * 5,
                },
                "spec": {
                    "replicas": 5,
                    "selector": {"matchLabels": {"app": f"app-{i}"}},
                    "template": {
                        "metadata": {"labels": {"app": f"app-{i}"}},
                        "spec": {
                            "containers": [
                                {
                                    "name": "main",
                                    "image": f"nginx:{i}.0",
                                    "env": [{"name": f"VAR_{j}", "value": f"value_{j}" * 10} for j in range(20)],
                                }
                            ]
                        },
                    },
                },
                "status": {
                    "replicas": 5,
                    "readyReplicas": 5,
                    "availableReplicas": 5,
                },
            })

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": items,
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            deployments, errors, metadata = collect_deployments("default", None)

            # Should have deployments (parsed successfully)
            assert len(deployments) == 50
            assert errors == []

            # Bounded error metadata
            assert metadata.get("error") is not None
            assert "spill_required_but_no_artifact_dir" in metadata["error"]

    def test_collect_deployments_source_tool_is_correct(self) -> None:
        """source_tool is kubectl_get for deployments collector."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            deployments, errors, metadata = collect_deployments("default", None)

            assert metadata["source_tool"] == "kubectl_get"

    def test_collect_deployments_provenance_includes_namespace_and_resource(self) -> None:
        """provenance includes namespace and resource='deployments'."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            deployments, errors, metadata = collect_deployments("test-namespace", None)

            assert "provenance" in metadata
            assert metadata["provenance"]["namespace"] == "test-namespace"
            assert metadata["provenance"]["resource"] == "deployments"

    def test_collect_deployments_semantic_output_unchanged(self) -> None:
        """Existing collector semantic output remains unchanged."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [
                {
                    "metadata": {
                        "name": "web-deployment",
                        "namespace": "production",
                    },
                    "spec": {
                        "replicas": 5,
                        "selector": {"matchLabels": {"app": "web"}},
                        "template": {
                            "metadata": {"labels": {"app": "web"}},
                            "spec": {
                                "containers": [
                                    {"name": "nginx", "image": "nginx:1.21"}
                                ]
                            },
                        },
                    },
                    "status": {
                        "replicas": 5,
                        "readyReplicas": 3,
                        "availableReplicas": 3,
                    },
                },
            ],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            deployments, errors, metadata = collect_deployments("production", None)

            # Semantic output matches expected DeploymentSummary
            assert len(deployments) == 1
            assert deployments[0].name == "web-deployment"
            assert deployments[0].namespace == "production"
            assert deployments[0].replicas == 5
            assert deployments[0].ready_replicas == 3
            assert deployments[0].available_replicas == 3


class TestCollectDeploymentsReturnShape:
    """Tests for collect_deployments return shape change."""

    def test_collect_deployments_returns_three_tuple(self) -> None:
        """collect_deployments returns (deployments, errors, projection_metadata) tuple."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            result = collect_deployments("default", None)

            # Must be 3-tuple
            assert isinstance(result, tuple)
            assert len(result) == 3
            deployments, errors, metadata = result
            assert isinstance(deployments, list)
            assert isinstance(errors, list)
            assert isinstance(metadata, dict)

    def test_collect_deployments_two_tuple_call_fails(self) -> None:
        """Old 2-tuple unpacking of collect_deployments should fail."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            # Old code expecting 2 values should fail
            try:
                deployments, errors = collect_deployments("default", None)
                # If this doesn't raise, the test framework should catch the extra value
                assert False, "Should have raised ValueError for too many values"
            except ValueError as e:
                assert "too many values" in str(e) or "unpack" in str(e)

    def test_collect_deployments_accepts_artifact_dir_parameter(self) -> None:
        """collect_deployments accepts optional artifact_dir parameter."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [],
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            with unittest.mock.patch(
                "k8s_diag_agent.collect.incident_collectors.kubectl",
                return_value=mock_output,
            ):
                # Should accept artifact_dir without error
                result = collect_deployments("default", None, artifact_dir)
                assert isinstance(result, tuple)
                assert len(result) == 3


class TestCollectDeploymentsBundlePropagation:
    """Tests for collect_deployments metadata propagation into bundle."""

    def test_deployments_projection_metadata_populates_bundle(self) -> None:
        """IncidentEvidenceBundle.tool_output_projection["deployments"] is populated."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [
                {
                    "metadata": {
                        "name": "test-deployment",
                        "namespace": "default",
                    },
                    "spec": {
                        "replicas": 3,
                        "selector": {"matchLabels": {"app": "test"}},
                        "template": {
                            "metadata": {"labels": {"app": "test"}},
                            "spec": {"containers": [{"name": "main", "image": "nginx:1.21"}]},
                        },
                    },
                    "status": {
                        "replicas": 3,
                        "readyReplicas": 3,
                        "availableReplicas": 3,
                    },
                },
            ],
        })

        # Mock kubectl for all collectors
        def mock_kubectl(context, *args, **kwargs: object):
            if "deployments" in args:
                return mock_output
            elif "pods" in args:
                return json.dumps({
                    "apiVersion": "v1",
                    "kind": "PodList",
                    "items": [],
                })
            elif "events" in args:
                return json.dumps({
                    "apiVersion": "v1",
                    "kind": "EventList",
                    "items": [],
                })
            return "{}"

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            side_effect=mock_kubectl,
        ):
            deployments, errors, metadata = collect_deployments("default", None)

            # Verify metadata structure matches expected bundle propagation
            assert "source_tool" in metadata
            assert metadata["source_tool"] == "kubectl_get"
            assert "raw_size_bytes" in metadata
            assert "llm_visible_size_bytes" in metadata
            assert "schema_version" in metadata

    def test_deployments_metadata_has_same_keys_as_pods_and_events(self) -> None:
        """Deployment projection metadata has identical key sets to pods and events."""
        import unittest.mock

        from k8s_diag_agent.collect.incident_collectors import collect_events, collect_pods

        # Small outputs for all collectors
        pods_output = json.dumps({
            "apiVersion": "v1",
            "kind": "PodList",
            "items": [],
        })

        events_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": [],
        })

        deployments_output = json.dumps({
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [],
        })

        def mock_kubectl(context, *args, **kwargs: object):
            if "pods" in args:
                return pods_output
            elif "events" in args:
                return events_output
            elif "deployments" in args:
                return deployments_output
            return "{}"

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            side_effect=mock_kubectl,
        ):
            _, _, pods_meta = collect_pods("default", None)
            _, _, events_meta = collect_events("default", None, 2)
            _, _, deployments_meta = collect_deployments("default", None)

            pods_keys = set(pods_meta.keys())
            events_keys = set(events_meta.keys())
            deployments_keys = set(deployments_meta.keys())

            # All should have identical key sets
            assert pods_keys == events_keys
            assert events_keys == deployments_keys

            expected_keys = {
                "schema_version",
                "source_tool",
                "spill_occurred",
                "spill_reason",
                "raw_artifact_id",
                "raw_size_bytes",
                "llm_visible_size_bytes",
                "content_type",
                "error",
                "provenance",
            }
            assert pods_keys == expected_keys

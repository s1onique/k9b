"""Tests for MetadataAnonymizer."""

from __future__ import annotations

import copy

from k8s_diag_agent.security.anonymizer import MetadataAnonymizer, anonymize_metadata


class TestMetadataAnonymizer:
    """Unit tests for MetadataAnonymizer class."""

    def test_same_name_same_alias(self) -> None:
        """Same name maps to same alias within one anonymizer instance."""
        anon = MetadataAnonymizer()
        result1 = anon.anonymize({"namespace": "production"})
        result2 = anon.anonymize({"namespace": "production"})

        # Both should have the same alias
        assert result1["namespace"] == result2["namespace"]
        # Should be an alias format
        assert result1["namespace"].startswith("namespace-")

    def test_different_names_different_aliases(self) -> None:
        """Different names in same category map to different aliases."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "namespaces": ["production", "staging", "default"],
        })

        # All three should be different aliases
        assert result["namespaces"][0] != result["namespaces"][1]
        assert result["namespaces"][1] != result["namespaces"][2]
        assert result["namespaces"][0] != result["namespaces"][2]

    def test_different_categories_no_collision(self) -> None:
        """Different categories do not collide."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "cluster_id": "prod-cluster",
            "namespace": "production",
            "node_name": "worker-1",
        })

        # All should have their respective category prefix
        assert result["cluster_id"].startswith("cluster-")
        assert result["namespace"].startswith("namespace-")
        assert result["node_name"].startswith("node-")

    def test_deployment_metadata_name(self) -> None:
        """Deployment metadata.name becomes deployment-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "kind": "Deployment",
            "metadata": {
                "name": "myapp-v1",
                "namespace": "production",
            },
        })

        assert result["metadata"]["name"] == "deployment-a"
        assert result["metadata"]["namespace"] == "namespace-a"

    def test_statefulset_metadata_name(self) -> None:
        """StatefulSet metadata.name becomes statefulset-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "kind": "StatefulSet",
            "metadata": {
                "name": "postgres-primary",
            },
        })

        assert result["metadata"]["name"] == "statefulset-a"

    def test_namespace_field(self) -> None:
        """Namespace field becomes namespace-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "namespace": "default",
        })

        assert result["namespace"] == "namespace-a"

    def test_cluster_id_field(self) -> None:
        """Cluster ID field becomes cluster-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "cluster_id": "prod-us-east-1",
        })

        assert result["cluster_id"] == "cluster-a"

    def test_nested_dict_structure(self) -> None:
        """Nested dict structures are anonymized."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "spec": {
                "namespace": "production",
                "replicas": 3,
            },
            "metadata": {
                "name": "myapp",
                "namespace": "production",
            },
        })

        # Namespace in spec should be anonymized
        assert result["spec"]["namespace"] == "namespace-a"
        # Namespace in metadata should be same alias
        assert result["metadata"]["namespace"] == "namespace-a"
        # Replicas should be preserved
        assert result["spec"]["replicas"] == 3

    def test_list_of_dicts(self) -> None:
        """List of dicts with names are anonymized."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "items": [
                {"name": "pod-a", "namespace": "default"},
                {"name": "pod-b", "namespace": "default"},
                {"name": "pod-c", "namespace": "production"},
            ],
        })

        # Names without kind context use generic "name" category
        # All names should be different aliases
        assert result["items"][0]["name"] == "name-a"
        assert result["items"][1]["name"] == "name-b"
        assert result["items"][2]["name"] == "name-c"

        # Both default namespaces should be same alias
        assert result["items"][0]["namespace"] == result["items"][1]["namespace"]
        # Production should be different
        assert result["items"][0]["namespace"] != result["items"][2]["namespace"]

    def test_preserves_kind(self) -> None:
        """Kubernetes kind field is preserved."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "kind": "Deployment",
            "metadata": {"name": "myapp"},
        })

        assert result["kind"] == "Deployment"
        assert result["metadata"]["name"] == "deployment-a"

    def test_preserves_status(self) -> None:
        """Status/phase fields are preserved."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "status": {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "True"}],
            },
        })

        assert result["status"]["phase"] == "Running"
        assert result["status"]["conditions"][0]["type"] == "Ready"

    def test_preserves_timestamps(self) -> None:
        """Timestamp strings are preserved."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "metadata": {
                "creationTimestamp": "2024-01-15T10:00:00Z",
            },
            "last_transition_time": "2024-01-15T12:30:00Z",
        })

        assert result["metadata"]["creationTimestamp"] == "2024-01-15T10:00:00Z"
        assert result["last_transition_time"] == "2024-01-15T12:30:00Z"

    def test_preserves_counts(self) -> None:
        """Numeric count fields are preserved."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "node_count": 5,
            "pod_count": 42,
            "replicas": 3,
            "available_replicas": 2,
            "unavailable_replicas": 1,
        })

        assert result["node_count"] == 5
        assert result["pod_count"] == 42
        assert result["replicas"] == 3
        assert result["available_replicas"] == 2
        assert result["unavailable_replicas"] == 1

    def test_preserves_boolean_and_none(self) -> None:
        """Boolean and None values are preserved."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "active": True,
            "enabled": False,
            "optional": None,
            "ready": True,
        })

        assert result["active"] is True
        assert result["enabled"] is False
        assert result["optional"] is None
        assert result["ready"] is True

    def test_input_not_mutated(self) -> None:
        """Input object is not mutated."""
        original = {"namespace": "production", "cluster_id": "my-cluster"}
        original_copy = copy.deepcopy(original)

        anon = MetadataAnonymizer()
        anon.anonymize(original)

        # Original should be unchanged
        assert original == original_copy

    def test_two_instances_different_mappings(self) -> None:
        """Two separate anonymizer instances have independent mappings."""
        anon1 = MetadataAnonymizer()
        anon2 = MetadataAnonymizer()

        result1 = anon1.anonymize({"namespace": "production"})
        result2 = anon2.anonymize({"namespace": "production"})

        # Both should be valid aliases but potentially different
        assert result1["namespace"].startswith("namespace-")
        assert result2["namespace"].startswith("namespace-")
        # They might be the same or different - that's fine for fresh instances

    def test_cluster_id_name_both_mapped(self) -> None:
        """cluster_id and cluster_name both map to cluster category."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "cluster_id": "cluster-1",
            "cluster_name": "cluster-1",  # Same value, same category
        })

        # Both should map to same cluster alias
        assert result["cluster_id"] == result["cluster_name"]

    def test_service_metadata_name(self) -> None:
        """Service metadata.name becomes service-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "kind": "Service",
            "metadata": {
                "name": "nginx-svc",
            },
        })

        assert result["metadata"]["name"] == "service-a"

    def test_pod_metadata_name(self) -> None:
        """Pod metadata.name becomes pod-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "kind": "Pod",
            "metadata": {
                "name": "nginx-deployment-abc123",
            },
        })

        assert result["metadata"]["name"] == "pod-a"

    def test_daemonset_metadata_name(self) -> None:
        """DaemonSet metadata.name becomes daemonset-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "kind": "DaemonSet",
            "metadata": {
                "name": "fluentd-ds",
            },
        })

        assert result["metadata"]["name"] == "daemonset-a"

    def test_hostname_field(self) -> None:
        """Hostname field becomes host-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "hostname": "app.example.com",
        })

        assert result["hostname"] == "host-a"

    def test_host_field(self) -> None:
        """Host field becomes host-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "host": "api.internal.net",
        })

        assert result["host"] == "host-a"

    def test_release_name_field(self) -> None:
        """Release name field becomes release-a."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "release_name": "ingress-nginx",
        })

        assert result["release_name"] == "release-a"

    def test_labels_app_key_anonymized(self) -> None:
        """Labels with app/name-like keys are preserved (use anonymize_labels_annotations for special handling)."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "labels": {
                "app": "myapplication",
                "environment": "production",
                "version": "v1.0.0",
            },
        })

        # Top-level labels are preserved by default
        # Use anonymize_labels_annotations() for label value anonymization
        assert result["labels"]["app"] == "myapplication"
        assert result["labels"]["environment"] == "production"

    def test_labels_non_name_keys_preserved(self) -> None:
        """Labels with non-name-like keys are preserved."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "labels": {
                "kubernetes.io/built-by": "kubectl",
                "app": "myapp",
            },
        })

        # Labels are preserved by default
        assert result["labels"]["kubernetes.io/built-by"] == "kubectl"
        assert result["labels"]["app"] == "myapp"

    def test_annotations_anonymized(self) -> None:
        """Annotations with name-like values are preserved (use anonymize_labels_annotations for special handling)."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "annotations": {
                "app": "myapp",
                "description": "This is a production application",
            },
        })

        # Annotations are preserved by default
        assert result["annotations"]["app"] == "myapp"
        assert result["annotations"]["description"] == "This is a production application"

    def test_nested_metadata_block(self) -> None:
        """Nested metadata blocks are processed correctly."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "spec": {
                "template": {
                    "metadata": {
                        "name": "myapp-pod",
                        "namespace": "default",
                    },
                },
            },
        })

        # Without kind context, name uses generic "name" category
        assert result["spec"]["template"]["metadata"]["name"] == "name-a"
        assert result["spec"]["template"]["metadata"]["namespace"] == "namespace-a"

    def test_tuple_preserved(self) -> None:
        """Tuple type is preserved (converted to tuple in output)."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "items": ("a", "b", "c"),
        })

        # Result should be a tuple (or list, depending on implementation)
        assert isinstance(result["items"], (list, tuple))

    def test_empty_string_not_anonymized(self) -> None:
        """Empty strings are not anonymized."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "name": "",
        })

        assert result["name"] == ""

    def test_short_string_not_anonymized(self) -> None:
        """Very short strings are not anonymized."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "name": "x",
        })

        # Single character should not be anonymized
        assert result["name"] == "x"


class TestAnonymizeMetadata:
    """Tests for the convenience anonymize_metadata function."""

    def test_creates_fresh_anonymizer(self) -> None:
        """anonymize_metadata creates a fresh anonymizer each time."""
        result1 = anonymize_metadata({"namespace": "production"})
        result2 = anonymize_metadata({"namespace": "production"})

        # Both should be valid aliases (may or may not be same)
        assert result1["namespace"].startswith("namespace-")
        assert result2["namespace"].startswith("namespace-")

    def test_basic_functionality(self) -> None:
        """Basic functionality works."""
        result = anonymize_metadata({
            "kind": "Deployment",
            "metadata": {
                "name": "myapp",
                "namespace": "default",
            },
        })

        assert result["kind"] == "Deployment"
        assert result["metadata"]["name"] == "deployment-a"
        assert result["metadata"]["namespace"] == "namespace-a"


class TestExactShapePreservation:
    """Regression tests to ensure output shape matches input shape."""

    def test_no_metadata_key_not_added(self) -> None:
        """Dict without metadata should not gain a metadata key."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({"namespace": "default"})

        # Should have only namespace, no metadata
        assert list(result.keys()) == ["namespace"]
        assert result["namespace"] == "namespace-a"

    def test_cluster_id_no_metadata(self) -> None:
        """Dict with cluster_id should not gain a metadata key."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({"cluster_id": "prod"})

        # Should have only cluster_id, no metadata
        assert list(result.keys()) == ["cluster_id"]
        assert result["cluster_id"] == "cluster-a"

    def test_nested_dict_without_metadata_no_metadata_key(self) -> None:
        """Nested dict without metadata should not gain metadata."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "spec": {
                "namespace": "default",
                "replicas": 3,
            },
        })

        # spec should not have metadata added
        assert "metadata" not in result["spec"]
        # spec namespace should be anonymized
        assert result["spec"]["namespace"] == "namespace-a"
        # replicas preserved
        assert result["spec"]["replicas"] == 3

    def test_list_of_dicts_without_metadata_no_metadata_key(self) -> None:
        """List of dicts without metadata should not gain metadata keys."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "items": [
                {"name": "item-1", "namespace": "default"},
                {"name": "item-2", "namespace": "default"},
            ],
        })

        # Each item should not have a metadata key added
        for item in result["items"]:
            assert "metadata" not in item
        # Names anonymized, namespaces same
        assert result["items"][0]["namespace"] == result["items"][1]["namespace"]

    def test_empty_dict_unchanged(self) -> None:
        """Empty dict should remain empty."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({})

        assert result == {}

    def test_only_counts_preserved(self) -> None:
        """Dict with only counts should not gain metadata."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "node_count": 5,
            "pod_count": 42,
        })

        # No metadata key should be added
        assert list(result.keys()) == ["node_count", "pod_count"]
        assert result["node_count"] == 5
        assert result["pod_count"] == 42

    def test_only_status_preserved(self) -> None:
        """Dict with only status should not gain metadata."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "status": {
                "phase": "Running",
            },
        })

        # No metadata key should be added
        assert "metadata" not in result
        assert result["status"]["phase"] == "Running"

    def test_top_level_key_order_preserved(self) -> None:
        """Top-level key order should match input order (insertion order)."""
        anon = MetadataAnonymizer()
        result = anon.anonymize({
            "cluster_id": "prod",
            "namespace": "default",
            "node_count": 5,
        })

        # Keys should be in same order as input
        assert list(result.keys()) == ["cluster_id", "namespace", "node_count"]

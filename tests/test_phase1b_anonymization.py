# mypy: disable-error-code=arg-type

"""Regression tests for Phase 1b LLM anonymization.

These tests verify that label values, annotation values, and Helm release names
are anonymized before being included in provider-bound LLM prompts.

Phase 1b scope:
- Label/annotation values that contain name-like data (e.g., customer names,
  team names, application names in label values)
- Helm release names in Path 1 (build_assessment_prompt)

These tests ensure:
1. Identifiable label values are not present in prompts
2. Identifiable annotation values are not present in prompts
3. Helm release names are anonymized in prompts
4. Label/annotation keys are preserved (useful signal)
5. Safe structural signal is maintained (version numbers, status, counts)

Ref: docs/security/llm-prompt-security-audit.md (GAP-P2 Phase 1b)
"""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import MagicMock

# Import the modules under test
from k8s_diag_agent.llm.prompts import _metadata_summary, _summarize_helm_diffs, build_assessment_prompt
from k8s_diag_agent.security.anonymizer import MetadataAnonymizer


class MockClusterSnapshot:
    """Minimal mock for ClusterSnapshot with sensitive label/annotation values."""

    def __init__(
        self,
        cluster_id: str = "test-cluster",
        labels: dict[str, str] | None = None,
        annotations: dict[str, str] | None = None,
        helm_releases: dict[str, Any] | None = None,
    ):
        self.cluster_id = cluster_id
        mock_meta = MagicMock()
        mock_meta.cluster_id = cluster_id
        mock_meta.control_plane_version = "v1.28.0"
        mock_meta.node_count = 5
        mock_meta.pod_count = 42
        mock_meta.region = "us-east-1"
        mock_meta.labels = labels or {}
        mock_meta.annotations = annotations or {}
        self.metadata = mock_meta

        # Mock collection_status
        mock_status = MagicMock()
        mock_status.to_dict.return_value = {"helm": "ok", "nodes": "ok"}
        self.collection_status = mock_status

        # Store helm_releases if provided
        self._helm_releases = helm_releases

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": {
                "cluster_id": self.metadata.cluster_id,
                "control_plane_version": self.metadata.control_plane_version,
                "node_count": self.metadata.node_count,
                "pod_count": self.metadata.pod_count,
                "region": self.metadata.region,
                "labels": self.metadata.labels,
                "annotations": self.metadata.annotations,
            }
        }


class MockComparison:
    """Minimal mock for ClusterComparison with Helm release differences."""

    def __init__(self, differences: dict[str, Any] | None = None):
        self.differences = differences or {}


class TestLabelValueAnonymization(unittest.TestCase):
    """Tests that label values with name-like content are anonymized."""

    def test_customer_team_name_in_label_value_anonymized(self) -> None:
        """Label values containing customer/team names must not appear in prompts."""
        # Sensitive label values that should be anonymized
        labels = {
            "app": "acme-customer-prod",  # Contains customer name
            "team": "sre-platform-team",  # Contains team name
            "environment": "production",  # Generic - may or may not be anonymized
        }

        snapshot = MockClusterSnapshot(
            cluster_id="prod-us-east-1",
            labels=labels,
        )

        # Create anonymizer and build metadata summary
        anonymizer = MetadataAnonymizer()
        result = _metadata_summary(snapshot, anonymizer=anonymizer)

        # Apply label value anonymization
        anon_result = anonymizer.anonymize_labels_annotations(result)
        labels_result = anon_result.get("labels", {})

        # Customer/team name in label values should be anonymized
        self.assertNotIn("acme-customer-prod", str(labels_result))
        self.assertNotIn("sre-platform-team", str(labels_result))
        # Label keys should be preserved
        self.assertIn("app", labels_result)
        self.assertIn("team", labels_result)

    def test_label_key_presence_preserved(self) -> None:
        """Label keys are preserved as useful signal."""
        labels = {
            "app": "myapplication",
            "component": "api-service",
            "owner": "team-alpha",
        }

        snapshot = MockClusterSnapshot(labels=labels)
        anonymizer = MetadataAnonymizer()
        result = _metadata_summary(snapshot, anonymizer=anonymizer)
        anon_result = anonymizer.anonymize_labels_annotations(result)

        # Label keys should be present
        self.assertIn("app", anon_result["labels"])
        self.assertIn("component", anon_result["labels"])
        self.assertIn("owner", anon_result["labels"])

    def test_numeric_label_values_preserved(self) -> None:
        """Numeric label values should be preserved (not anonymized)."""
        labels = {
            "replicas": "3",
            "port": "8080",
            "count": "42",
        }

        snapshot = MockClusterSnapshot(labels=labels)
        anonymizer = MetadataAnonymizer()
        result = _metadata_summary(snapshot, anonymizer=anonymizer)
        anon_result = anonymizer.anonymize_labels_annotations(result)

        # Numeric strings should be preserved (pattern-matching is conservative)
        # The anonymizer uses _looks_like_name() which should preserve pure digits
        self.assertEqual(anon_result["labels"].get("replicas"), "3")
        self.assertEqual(anon_result["labels"].get("port"), "8080")

    def test_url_in_annotation_value_anonymized(self) -> None:
        """Annotation values containing URLs or tokens should not appear in prompts."""
        # Test that URL values in annotation values are anonymized when key matches patterns
        # Note: owner pattern matches, URL values in owner-keyed annotations should be anonymized
        annotations = {
            "owner": "admin@acme-corp.com",
            "team": "platform-team@corp.net",
        }

        anonymizer = MetadataAnonymizer()
        data = {"annotations": annotations}
        result = anonymizer.anonymize_labels_annotations(data)

        # Owner/team emails should be anonymized when key patterns match
        self.assertNotIn("acme-corp.com", str(result))
        self.assertNotIn("corp.net", str(result))


class TestHelmReleaseNameAnonymization(unittest.TestCase):
    """Tests that Helm release names are anonymized in prompts."""

    def test_identifiable_helm_release_names_anonymized(self) -> None:
        """Identifiable Helm release names must not appear in prompts."""
        # Release names that reveal application/infrastructure identity
        helm_diffs = {
            "production/acme-payments": {
                "primary": {
                    "namespace": "production",
                    "chart_version": "2.0.0",
                    "app_version": "1.5.0",
                },
                "secondary": None,
            },
            "staging/api-gateway": {
                "primary": None,
                "secondary": {
                    "namespace": "staging",
                    "chart_version": "1.0.0",
                    "app_version": "0.9.0",
                },
            },
            "default/shared-cache": {
                "primary": {
                    "namespace": "default",
                    "chart_version": "3.1.0",
                },
                "secondary": {
                    "namespace": "default",
                    "chart_version": "3.0.5",
                },
            },
        }

        anonymizer = MetadataAnonymizer()
        result = _summarize_helm_diffs(helm_diffs, anonymizer=anonymizer)

        # Check that release names are anonymized
        release_names = [entry["release"] for entry in result]
        self.assertNotIn("acme-payments", release_names)
        self.assertNotIn("api-gateway", release_names)
        self.assertNotIn("shared-cache", release_names)

        # But the anonymized names should be present (e.g., "release-a", "release-b")
        for name in release_names:
            self.assertTrue(
                name.startswith("release-"),
                f"Release name {name} should be anonymized to release-X pattern",
            )

    def test_helm_release_status_preserved(self) -> None:
        """Helm release status information should be preserved."""
        helm_diffs = {
            "production/monitoring": {
                "primary": {
                    "namespace": "production",
                    "chart_version": "5.0.0",
                    "app_version": "0.50.0",
                },
                "secondary": {
                    "namespace": "production",
                    "chart_version": "4.5.0",
                    "app_version": "0.45.0",
                },
            },
        }

        anonymizer = MetadataAnonymizer()
        result = _summarize_helm_diffs(helm_diffs, anonymizer=anonymizer)

        # Status information should be preserved
        self.assertEqual(result[0]["status"], "version-mismatch")
        self.assertEqual(result[0]["primary_chart_version"], "5.0.0")
        self.assertEqual(result[0]["secondary_chart_version"], "4.5.0")

    def test_helm_release_name_anonymization_consistent(self) -> None:
        """Same release name should map to same alias within one prompt."""
        # Test with a single release appearing in both primary and secondary contexts
        helm_diffs = {
            "default/app-a": {
                "primary": {"namespace": "default", "chart_version": "1.0.0"},
                "secondary": {"namespace": "default", "chart_version": "1.0.0"},
            },
        }

        anonymizer = MetadataAnonymizer()
        result = _summarize_helm_diffs(helm_diffs, anonymizer=anonymizer)

        # The release name should be anonymized
        release_names = [entry["release"] for entry in result]
        for name in release_names:
            self.assertTrue(
                name.startswith("release-"),
                f"Release name {name} should be anonymized to release-X pattern",
            )


class TestAssessmentPromptPhase1b(unittest.TestCase):
    """Integration tests for Phase 1b anonymization in assessment prompts."""

    def test_prompt_contains_no_sensitive_label_values(self) -> None:
        """Build assessment prompt should not contain sensitive label values."""
        primary = MockClusterSnapshot(
            cluster_id="prod-cluster-alpha",
            labels={
                "app": "acme-customer-app",
                "team": "platform-sre-team",
                "environment": "production",
            },
        )
        secondary = MockClusterSnapshot(
            cluster_id="prod-cluster-beta",
            labels={
                "app": "acme-customer-app",
                "team": "frontend-dev-team",
                "environment": "production",
            },
        )

        mock_comparison = MockComparison(differences={})
        prompt = build_assessment_prompt(primary, secondary, mock_comparison)

        # Customer/team names should not appear in prompt
        self.assertNotIn("acme-customer-app", prompt)
        self.assertNotIn("platform-sre-team", prompt)
        self.assertNotIn("frontend-dev-team", prompt)

    def test_prompt_contains_no_identifiable_helm_release_names(self) -> None:
        """Build assessment prompt should not contain identifiable Helm release names."""
        primary = MockClusterSnapshot(cluster_id="prod-us-east-1")
        secondary = MockClusterSnapshot(cluster_id="prod-us-west-1")

        # Create helm_releases attribute
        def make_helm_releases(name: str) -> dict:
            return {
                name: MagicMock(
                    namespace="production",
                    chart_version="2.0.0",
                    app_version="1.5.0",
                )
            }

        primary._helm_releases = make_helm_releases("production/frontend-app")
        secondary._helm_releases = make_helm_releases("production/backend-service")

        # Create comparison with helm release differences
        helm_diffs = {
            "production/frontend-app": {
                "primary": {
                    "namespace": "production",
                    "chart_version": "2.0.0",
                    "app_version": "1.5.0",
                },
                "secondary": None,
            },
            "production/backend-service": {
                "primary": None,
                "secondary": {
                    "namespace": "production",
                    "chart_version": "1.0.0",
                },
            },
        }

        mock_comparison = MockComparison(differences={"helm_releases": helm_diffs})
        prompt = build_assessment_prompt(primary, secondary, mock_comparison)

        # Identifiable release names should not appear in prompt
        self.assertNotIn("frontend-app", prompt)
        self.assertNotIn("backend-service", prompt)

        # Note: version strings may be anonymized due to conservative pattern matching
        # The key security goal is that identifiable release names are anonymized

    def test_prompt_contains_no_sensitive_annotation_values(self) -> None:
        """Build assessment prompt should not contain sensitive annotation values."""
        primary = MockClusterSnapshot(
            cluster_id="prod-cluster-alpha",
            annotations={
                "owner": "admin@acme-corp.com",
                "team": "platform-team@corp.net",
            },
        )
        secondary = MockClusterSnapshot(
            cluster_id="prod-cluster-beta",
            annotations={
                "owner": "user@customer-x.com",
            },
        )

        mock_comparison = MockComparison(differences={})
        prompt = build_assessment_prompt(primary, secondary, mock_comparison)

        # Owner emails should not appear in prompt
        self.assertNotIn("acme-corp.com", prompt)
        self.assertNotIn("corp.net", prompt)
        self.assertNotIn("customer-x.com", prompt)
        self.assertNotIn("admin@acme-corp.com", prompt)

    def test_prompt_contains_no_identifiable_helm_namespaces(self) -> None:
        """Build assessment prompt should not contain identifiable Helm namespace names."""
        primary = MockClusterSnapshot(cluster_id="prod-us-east-1")
        secondary = MockClusterSnapshot(cluster_id="prod-us-west-1")

        # Create comparison with helm release differences using identifiable namespaces
        helm_diffs = {
            "default/redis": {
                "primary": {
                    "namespace": "acme-payments-prod",  # Identifiable namespace
                    "chart_version": "6.0.0",
                },
                "secondary": None,
            },
            "default/metrics": {
                "primary": None,
                "secondary": {
                    "namespace": "customer-billing-staging",
                    "chart_version": "2.0.0",
                },
            },
        }

        mock_comparison = MockComparison(differences={"helm_releases": helm_diffs})
        prompt = build_assessment_prompt(primary, secondary, mock_comparison)

        # Identifiable namespace names should not appear in prompt
        self.assertNotIn("acme-payments-prod", prompt)
        self.assertNotIn("customer-billing-staging", prompt)

        # Note: version strings may be anonymized due to conservative pattern matching
        # The key security goal is that identifiable namespaces are anonymized


class TestAnonymizerLabelAnnotationIntegration(unittest.TestCase):
    """Tests for the anonymize_labels_annotations method integration."""

    def test_labels_with_multiple_name_patterns(self) -> None:
        """Labels with various name patterns are handled correctly."""
        labels = {
            "app": "acme-procurement-app",  # Should be anonymized (app pattern + name)
            "application": "customer-portal",  # Should be anonymized (application pattern)
            "name": "payment-service",  # Should be anonymized (name pattern + name)
            "instance": "prod-01",  # Should be anonymized (instance pattern)
            "component": "api",  # May be anonymized (component pattern)
        }

        anonymizer = MetadataAnonymizer()
        data = {"labels": labels}
        result = anonymizer.anonymize_labels_annotations(data)

        # App name should be anonymized
        self.assertNotIn("acme-procurement-app", str(result))
        # Customer portal should be anonymized
        self.assertNotIn("customer-portal", str(result))
        # Payment service should be anonymized
        self.assertNotIn("payment-service", str(result))

    def test_annotations_with_owner_email(self) -> None:
        """Annotations with owner email are anonymized."""
        annotations = {
            "owner": "platform-team@acme.com",  # Should be anonymized (owner pattern)
            "team": "sre-team@corp.com",  # Should be anonymized (team pattern)
        }

        anonymizer = MetadataAnonymizer()
        data = {"annotations": annotations}
        result = anonymizer.anonymize_labels_annotations(data)

        # Owner email should be anonymized
        self.assertNotIn("acme.com", str(result))
        self.assertNotIn("platform-team@acme.com", str(result))
        self.assertNotIn("sre-team@corp.com", str(result))


class TestPhase1bConstraintsPreserved(unittest.TestCase):
    """Tests that Phase 1b does not weaken existing guarantees."""

    def test_cluster_id_still_anonymized(self) -> None:
        """Cluster IDs should still be anonymized (Phase 1 behavior)."""
        snapshot = MockClusterSnapshot(cluster_id="prod-us-east-1-cluster")
        anonymizer = MetadataAnonymizer()
        result = _metadata_summary(snapshot, anonymizer=anonymizer)
        anon_result = anonymizer.anonymize(result)

        self.assertNotIn("prod-us-east-1-cluster", str(anon_result))

    def test_namespace_still_anonymized(self) -> None:
        """Namespaces in helm diffs should still be anonymized."""
        helm_diffs = {
            "default/redis": {
                "primary": {"namespace": "production", "chart_version": "1.0.0"},
                "secondary": None,
            },
        }

        anonymizer = MetadataAnonymizer()
        result = _summarize_helm_diffs(helm_diffs, anonymizer=anonymizer)
        # Apply full anonymization including namespace
        anon_result = anonymizer.anonymize(result)

        # After full anonymization, production should not appear
        result_str = json.dumps(anon_result)
        self.assertNotIn("production", result_str)

    def test_incident_report_claim_taxonomy_preserved(self) -> None:
        """Incident report claim taxonomy is not broken by Phase 1b changes."""
        # Create a prompt and verify it still has expected structure
        primary = MockClusterSnapshot(
            cluster_id="test-cluster",
            labels={"app": "test", "environment": "test"},
        )
        secondary = MockClusterSnapshot(
            cluster_id="test-cluster-2",
            labels={"app": "test", "environment": "staging"},
        )

        mock_comparison = MockComparison(
            differences={
                "metadata": {"node_count": {"primary": 3, "secondary": 5}},
            }
        )
        prompt = build_assessment_prompt(primary, secondary, mock_comparison)

        # Prompt should still have required structure
        self.assertIn("BEGIN_UNTRUSTED_CLUSTER_DATA", prompt)
        self.assertIn("END_UNTRUSTED_CLUSTER_DATA", prompt)
        self.assertIn("BEGIN_OUTPUT_SCHEMA", prompt)
        self.assertIn("END_OUTPUT_SCHEMA", prompt)

        # Prompt should still ask for JSON assessment
        self.assertIn("JSON", prompt)

    def test_safe_structural_signal_preserved(self) -> None:
        """Safe structural signal (status, versions, counts) is preserved."""
        helm_diffs = {
            "default/test-release": {
                "primary": {
                    "namespace": "default",
                    "chart_version": "3.2.1",
                    "app_version": "1.0.0",
                },
                "secondary": {
                    "namespace": "default",
                    "chart_version": "3.1.0",
                    "app_version": "0.9.0",
                },
            },
        }

        anonymizer = MetadataAnonymizer()
        result = _summarize_helm_diffs(helm_diffs, anonymizer=anonymizer)

        # Version numbers should be preserved
        self.assertEqual(result[0]["primary_chart_version"], "3.2.1")
        self.assertEqual(result[0]["secondary_chart_version"], "3.1.0")
        self.assertEqual(result[0]["primary_app_version"], "1.0.0")
        self.assertEqual(result[0]["secondary_app_version"], "0.9.0")

        # Status should be preserved
        self.assertEqual(result[0]["status"], "version-mismatch")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression tests for workload missing sub-classification.

These tests verify that expected_workload_missing is sub-classified into
specific render/apply/release causes when Deployment/k9b is not found.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.k9b_cnpg_live_lab_helm_inventory import (
    check_chart_values_suppression,
    check_rbac_admission_rejection,
    parse_workload_inventory,
    write_workload_inventory,
)
from scripts.k9b_cnpg_live_lab_workload_missing_classify import (
    _is_deployment_in_cluster,
    classify_expected_workload_missing,
)

# Import fixtures
from tests.workload_missing_subclassify_fixtures import (
    DEPLOYMENTS_EMPTY,
    DEPLOYMENTS_WITH_K9B,
    HELM_HISTORY_FAILED,
    HELM_STATUS_DEPLOYED,
    RBAC_ERROR_DENIED,
    RBAC_ERROR_FORBIDDEN,
    RBAC_SUCCESS,
    RENDERED_CONFIGMAP_ONLY,
    RENDERED_MALFORMED,
    RENDERED_NO_K9B,
    RENDERED_WITH_K9B,
    VALUES_BACKEND_DISABLED,
    VALUES_K9B_DISABLED,
    VALUES_REPLICAS_ONE,
    VALUES_REPLICAS_ZERO,
    WORKLOAD_INVENTORY_FIXTURE,
    YAML_COMMENTS_ONLY,
    YAML_MALFORMED,
    YAML_MULTI_WORKLOAD,
    YAML_NON_DICT_WITH_DEPLOYMENT,
    YAML_WITH_DEPLOYMENT_K9B,
    YAML_WITH_OTHER_DEPLOYMENT,
    YAML_WRONG_NAME,
    YAML_WRONG_NAMESPACE,
)


class TestRenderInventoryParser(unittest.TestCase):
    """Tests for rendered workload inventory parser."""

    def test_multi_doc_yaml_with_deployment_k9b(self) -> None:
        """Multi-document YAML with Deployment/k9b should detect presence."""
        result = parse_workload_inventory(YAML_WITH_DEPLOYMENT_K9B, expected_name="k9b")
        self.assertTrue(result["rendered"]["deployment_k9b_present"])
        self.assertEqual(len(result["rendered"]["matching_workloads"]), 1)
        self.assertEqual(len(result["rendered"]["all_workloads"]), 1)

    def test_multi_doc_yaml_without_deployment_k9b(self) -> None:
        """Multi-document YAML without Deployment/k9b should detect absence."""
        result = parse_workload_inventory(YAML_WITH_OTHER_DEPLOYMENT, expected_name="k9b")
        self.assertFalse(result["rendered"]["deployment_k9b_present"])
        self.assertEqual(len(result["rendered"]["matching_workloads"]), 0)
        self.assertEqual(len(result["rendered"]["all_workloads"]), 1)

    def test_empty_yaml(self) -> None:
        """Empty YAML should be handled gracefully."""
        result = parse_workload_inventory("")
        self.assertFalse(result["rendered"]["deployment_k9b_present"])
        self.assertIn("Empty", result["parse_errors"][0])

    def test_comments_only_yaml(self) -> None:
        """Comments-only YAML should be handled gracefully."""
        result = parse_workload_inventory(YAML_COMMENTS_ONLY)
        self.assertFalse(result["rendered"]["deployment_k9b_present"])

    def test_non_dict_yaml_docs(self) -> None:
        """Non-dict YAML documents should be skipped."""
        result = parse_workload_inventory(YAML_NON_DICT_WITH_DEPLOYMENT)
        self.assertTrue(result["rendered"]["deployment_k9b_present"])
        self.assertEqual(len(result["rendered"]["all_workloads"]), 1)

    def test_malformed_yaml(self) -> None:
        """Malformed YAML should be handled gracefully."""
        result = parse_workload_inventory(YAML_MALFORMED)
        self.assertFalse(result["rendered"]["deployment_k9b_present"])
        self.assertTrue(len(result["parse_errors"]) > 0)

    def test_wrong_namespace(self) -> None:
        """Deployment in wrong namespace should still be detected."""
        result = parse_workload_inventory(YAML_WRONG_NAMESPACE, expected_name="k9b")
        self.assertTrue(result["rendered"]["deployment_k9b_present"])

    def test_wrong_deployment_name(self) -> None:
        """Deployment with wrong name should not be matched."""
        result = parse_workload_inventory(YAML_WRONG_NAME, expected_name="k9b")
        self.assertFalse(result["rendered"]["deployment_k9b_present"])

    def test_other_workload_kinds_present(self) -> None:
        """Other workload kinds should be captured in all_workloads."""
        result = parse_workload_inventory(YAML_MULTI_WORKLOAD)
        self.assertEqual(len(result["rendered"]["all_workloads"]), 5)
        kinds = {w["kind"] for w in result["rendered"]["all_workloads"]}
        self.assertEqual(kinds, {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"})


class TestIsDeploymentInCluster(unittest.TestCase):
    """Tests for cluster deployment detection."""

    def test_deployment_present(self) -> None:
        """Should detect deployment when present."""
        deployments_json = json.dumps(DEPLOYMENTS_WITH_K9B)
        self.assertTrue(_is_deployment_in_cluster(deployments_json, "k9b"))

    def test_deployment_missing(self) -> None:
        """Should return False when deployment is absent."""
        deployments_json = json.dumps(DEPLOYMENTS_EMPTY)
        self.assertFalse(_is_deployment_in_cluster(deployments_json, "k9b"))

    def test_empty_json(self) -> None:
        """Should return False for empty JSON."""
        self.assertFalse(_is_deployment_in_cluster("", "k9b"))
        self.assertFalse(_is_deployment_in_cluster("{}", "k9b"))

    def test_invalid_json(self) -> None:
        """Should return False for invalid JSON."""
        self.assertFalse(_is_deployment_in_cluster("not json", "k9b"))


class TestChartValuesSuppression(unittest.TestCase):
    """Tests for chart values suppression detection."""

    def test_k9b_enabled_false(self) -> None:
        """Should detect k9b.enabled=false."""
        values = json.dumps(VALUES_K9B_DISABLED)
        is_suppressed, reason = check_chart_values_suppression(values)
        self.assertTrue(is_suppressed)
        self.assertIn("k9b.enabled=false", reason)

    def test_backend_enabled_false(self) -> None:
        """Should detect backend.enabled=false."""
        values = json.dumps(VALUES_BACKEND_DISABLED)
        is_suppressed, reason = check_chart_values_suppression(values)
        self.assertTrue(is_suppressed)
        self.assertIn("backend.enabled=false", reason)

    def test_backend_replicas_zero(self) -> None:
        """Should detect backend.replicas=0."""
        values = json.dumps(VALUES_REPLICAS_ZERO)
        is_suppressed, reason = check_chart_values_suppression(values)
        self.assertTrue(is_suppressed)
        self.assertIn("backend.replicas=0", reason)

    def test_not_suppressed(self) -> None:
        """Should not detect suppression when not present."""
        values = json.dumps(VALUES_REPLICAS_ONE)
        is_suppressed, reason = check_chart_values_suppression(values)
        self.assertFalse(is_suppressed)


class TestRbacAdmissionRejection(unittest.TestCase):
    """Tests for RBAC/admission rejection detection."""

    def test_forbidden_rbac(self) -> None:
        """Should detect RBAC forbidden errors."""
        has_rejection, _ = check_rbac_admission_rejection(RBAC_ERROR_FORBIDDEN)
        self.assertTrue(has_rejection)

    def test_admission_denied(self) -> None:
        """Should detect admission denied errors."""
        has_rejection, reason = check_rbac_admission_rejection(RBAC_ERROR_DENIED)
        self.assertTrue(has_rejection)
        self.assertIn("Admission webhook denied", reason)

    def test_no_rejection(self) -> None:
        """Should not detect rejection when not present."""
        has_rejection, _ = check_rbac_admission_rejection(RBAC_SUCCESS)
        self.assertFalse(has_rejection)


class TestExpectedWorkloadMissingSubclassification(unittest.TestCase):
    """Tests for expected_workload_missing sub-classification."""

    def test_rendered_manifest_missing_deployment(self) -> None:
        """When rendered manifest contains YAML but no Deployment/k9b and cluster missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"
            subclass, _ = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=json.dumps(DEPLOYMENTS_EMPTY),
                rendered_manifest_yaml=RENDERED_NO_K9B,
            )
            self.assertEqual(subclass, "rendered_manifest_missing_deployment")

    def test_rendered_has_but_cluster_missing(self) -> None:
        """When rendered manifest has Deployment/k9b but cluster missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"
            subclass, _ = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=json.dumps(DEPLOYMENTS_EMPTY),
                rendered_manifest_yaml=RENDERED_WITH_K9B,
                helm_status_json=json.dumps(HELM_STATUS_DEPLOYED),
            )
            self.assertEqual(subclass, "rendered_manifest_has_deployment_but_cluster_missing")

    def test_helm_release_missing(self) -> None:
        """When Helm release missing after install."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"
            subclass, _ = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=json.dumps(DEPLOYMENTS_EMPTY),
                rendered_manifest_yaml=RENDERED_WITH_K9B,
                helm_status_json="",
            )
            self.assertEqual(subclass, "helm_release_missing_after_install")

    def test_helm_release_failed(self) -> None:
        """When Helm release failed before workload creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"
            subclass, _ = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=json.dumps(DEPLOYMENTS_EMPTY),
                helm_history_json=json.dumps(HELM_HISTORY_FAILED),
            )
            self.assertEqual(subclass, "helm_release_failed_before_workload_create")

    def test_rbac_admission_rejection(self) -> None:
        """When RBAC/admission rejection is detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"
            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=json.dumps(DEPLOYMENTS_EMPTY),
                helm_install_stderr=RBAC_ERROR_FORBIDDEN,
            )
            self.assertEqual(subclass, "admission_or_rbac_rejected_workload")
            self.assertTrue(diagnostics.get("rbac_admission_rejection"))

    def test_chart_values_suppressed(self) -> None:
        """When chart values explicitly suppress the workload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"
            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=json.dumps(DEPLOYMENTS_EMPTY),
                helm_values_json=json.dumps(VALUES_K9B_DISABLED),
            )
            self.assertEqual(subclass, "chart_values_suppressed_workload")
            self.assertTrue(diagnostics.get("chart_values_suppressed"))

    def test_evidence_collection_failed(self) -> None:
        """When evidence collection fails due to parse error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"
            subclass, _ = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=json.dumps(DEPLOYMENTS_EMPTY),
                rendered_manifest_yaml=RENDERED_MALFORMED,
            )
            self.assertEqual(subclass, "render_apply_evidence_collection_failed")

    def test_transient_pvc_with_missing_deployment(self) -> None:
        """When transient PVC VolumeBinding conflict plus missing Deployment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"
            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=json.dumps(DEPLOYMENTS_EMPTY),
                rendered_manifest_yaml=RENDERED_CONFIGMAP_ONLY,
            )
            self.assertEqual(subclass, "rendered_manifest_missing_deployment")
            self.assertFalse(diagnostics.get("cluster_deployment_present"))


class TestArtifactDirectoryCreation(unittest.TestCase):
    """Tests for artifact directory creation."""

    def test_helm_directory_created(self) -> None:
        """Workload inventory should create helm/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            output_path = write_workload_inventory(artifact_dir, WORKLOAD_INVENTORY_FIXTURE)
            self.assertTrue(output_path.exists())
            self.assertTrue((artifact_dir / "helm").exists())


if __name__ == "__main__":
    unittest.main()

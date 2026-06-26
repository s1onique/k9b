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

# Import from scripts module using repo conventions
from scripts.k9b_cnpg_live_lab_workload_missing_classify import (
    _is_deployment_in_cluster,
    classify_expected_workload_missing,
)


class TestRenderInventoryParser(unittest.TestCase):
    """Tests for rendered workload inventory parser."""

    def test_multi_doc_yaml_with_deployment_k9b(self) -> None:
        """Multi-document YAML with Deployment/k9b should detect presence."""
        yaml_content = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
  namespace: test-ns
spec:
  replicas: 1
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config
"""
        result = parse_workload_inventory(yaml_content, expected_name="k9b")
        self.assertTrue(result["rendered"]["deployment_k9b_present"])
        self.assertEqual(len(result["rendered"]["matching_workloads"]), 1)
        self.assertEqual(len(result["rendered"]["all_workloads"]), 1)

    def test_multi_doc_yaml_without_deployment_k9b(self) -> None:
        """Multi-document YAML without Deployment/k9b should detect absence."""
        yaml_content = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: other-deployment
  namespace: test-ns
---
apiVersion: v1
kind: Service
metadata:
  name: service
"""
        result = parse_workload_inventory(yaml_content, expected_name="k9b")
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
        yaml_content = """# This is a comment
# Another comment
---
# Another comment block
"""
        result = parse_workload_inventory(yaml_content)
        self.assertFalse(result["rendered"]["deployment_k9b_present"])
        # No error for comments-only

    def test_non_dict_yaml_docs(self) -> None:
        """Non-dict YAML documents should be skipped."""
        yaml_content = """---
- item1
- item2
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
"""
        result = parse_workload_inventory(yaml_content)
        self.assertTrue(result["rendered"]["deployment_k9b_present"])
        self.assertEqual(len(result["rendered"]["all_workloads"]), 1)

    def test_malformed_yaml(self) -> None:
        """Malformed YAML should be handled gracefully."""
        yaml_content = """apiVersion: apps/v1
kind: Deployment
  metadata:
    name: k9b
  invalid indent
"""
        result = parse_workload_inventory(yaml_content)
        self.assertFalse(result["rendered"]["deployment_k9b_present"])
        self.assertTrue(len(result["parse_errors"]) > 0)

    def test_wrong_namespace(self) -> None:
        """Deployment in wrong namespace should still be detected."""
        yaml_content = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
  namespace: wrong-namespace
"""
        result = parse_workload_inventory(yaml_content, expected_name="k9b")
        self.assertTrue(result["rendered"]["deployment_k9b_present"])

    def test_wrong_deployment_name(self) -> None:
        """Deployment with wrong name should not be matched."""
        yaml_content = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: other-deployment
"""
        result = parse_workload_inventory(yaml_content, expected_name="k9b")
        self.assertFalse(result["rendered"]["deployment_k9b_present"])

    def test_other_workload_kinds_present(self) -> None:
        """Other workload kinds should be captured in all_workloads."""
        yaml_content = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deployment-1
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: statefulset-1
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: daemonset-1
---
apiVersion: batch/v1
kind: Job
metadata:
  name: job-1
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cronjob-1
"""
        result = parse_workload_inventory(yaml_content)
        self.assertEqual(len(result["rendered"]["all_workloads"]), 5)
        kinds = {w["kind"] for w in result["rendered"]["all_workloads"]}
        self.assertEqual(kinds, {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"})


class TestIsDeploymentInCluster(unittest.TestCase):
    """Tests for cluster deployment detection."""

    def test_deployment_present(self) -> None:
        """Should detect deployment when present."""
        deployments_json = json.dumps({
            "items": [
                {"metadata": {"name": "k9b"}}
            ]
        })
        self.assertTrue(_is_deployment_in_cluster(deployments_json, "k9b"))

    def test_deployment_missing(self) -> None:
        """Should return False when deployment is absent."""
        deployments_json = json.dumps({
            "items": []
        })
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
        values = json.dumps({"k9b": {"enabled": False}})
        is_suppressed, reason = check_chart_values_suppression(values)
        self.assertTrue(is_suppressed)
        self.assertIn("k9b.enabled=false", reason)

    def test_backend_enabled_false(self) -> None:
        """Should detect backend.enabled=false."""
        values = json.dumps({"backend": {"enabled": False}})
        is_suppressed, reason = check_chart_values_suppression(values)
        self.assertTrue(is_suppressed)
        self.assertIn("backend.enabled=false", reason)

    def test_backend_replicas_zero(self) -> None:
        """Should detect backend.replicas=0."""
        values = json.dumps({"backend": {"replicas": 0}})
        is_suppressed, reason = check_chart_values_suppression(values)
        self.assertTrue(is_suppressed)
        self.assertIn("backend.replicas=0", reason)

    def test_not_suppressed(self) -> None:
        """Should not detect suppression when not present."""
        values = json.dumps({"backend": {"replicas": 1}})
        is_suppressed, reason = check_chart_values_suppression(values)
        self.assertFalse(is_suppressed)


class TestRbacAdmissionRejection(unittest.TestCase):
    """Tests for RBAC/admission rejection detection."""

    def test_forbidden_rbac(self) -> None:
        """Should detect RBAC forbidden errors."""
        output = "Error: admission webhook denied: forbbiden"
        has_rejection, reason = check_rbac_admission_rejection(output)
        self.assertTrue(has_rejection)

    def test_admission_denied(self) -> None:
        """Should detect admission denied errors."""
        output = "Error: admission webhook denied: some resource"
        has_rejection, reason = check_rbac_admission_rejection(output)
        self.assertTrue(has_rejection)
        self.assertIn("Admission webhook denied", reason)

    def test_no_rejection(self) -> None:
        """Should not detect rejection when not present."""
        output = "Release deployed successfully"
        has_rejection, reason = check_rbac_admission_rejection(output)
        self.assertFalse(has_rejection)


class TestExpectedWorkloadMissingSubclassification(unittest.TestCase):
    """Tests for expected_workload_missing sub-classification."""

    def test_rendered_manifest_missing_deployment(self) -> None:
        """When rendered manifest contains YAML but no Deployment/k9b and cluster missing.
        
        Expected: rendered_manifest_missing_deployment
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"

            # Rendered manifest with YAML but no k9b deployment
            rendered_manifest = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config
"""
            deployments_json = json.dumps({"items": []})

            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                rendered_manifest_yaml=rendered_manifest,
            )

            self.assertEqual(subclass, "rendered_manifest_missing_deployment")

    def test_rendered_has_but_cluster_missing(self) -> None:
        """When rendered manifest has Deployment/k9b but cluster missing.
        
        Expected: rendered_manifest_has_deployment_but_cluster_missing
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"

            # Rendered manifest has k9b
            rendered_manifest = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
"""
            # Cluster has no k9b
            deployments_json = json.dumps({"items": []})

            # Helm release exists (partial evidence of apply attempt)
            helm_status_json = json.dumps({
                "name": "k9b",
                "info": {"status": {"status": "deployed"}}
            })

            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                rendered_manifest_yaml=rendered_manifest,
                helm_status_json=helm_status_json,
            )

            self.assertEqual(subclass, "rendered_manifest_has_deployment_but_cluster_missing")

    def test_helm_release_missing(self) -> None:
        """When Helm release missing after install.
        
        Expected: helm_release_missing_after_install
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"

            rendered_manifest = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
"""
            deployments_json = json.dumps({"items": []})

            # No Helm release (status fails)
            helm_status_json = ""

            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                rendered_manifest_yaml=rendered_manifest,
                helm_status_json=helm_status_json,
            )

            self.assertEqual(subclass, "helm_release_missing_after_install")

    def test_helm_release_failed(self) -> None:
        """When Helm release failed before workload creation.
        
        Expected: helm_release_failed_before_workload_create
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"

            deployments_json = json.dumps({"items": []})
            helm_history_json = json.dumps([
                {"revision": 1, "status": "failed", "description": "Install failed"}
            ])

            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                helm_history_json=helm_history_json,
            )

            self.assertEqual(subclass, "helm_release_failed_before_workload_create")

    def test_rbac_admission_rejection(self) -> None:
        """When RBAC/admission rejection is detected.
        
        Expected: admission_or_rbac_rejected_workload
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"

            deployments_json = json.dumps({"items": []})
            helm_stderr = "Error: admission webhook denied: forbbiden"

            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                helm_install_stderr=helm_stderr,
            )

            self.assertEqual(subclass, "admission_or_rbac_rejected_workload")
            self.assertTrue(diagnostics.get("rbac_admission_rejection"))

    def test_chart_values_suppressed(self) -> None:
        """When chart values explicitly suppress the workload.
        
        Expected: chart_values_suppressed_workload
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"

            deployments_json = json.dumps({"items": []})
            values_json = json.dumps({"k9b": {"enabled": False}})

            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                helm_values_json=values_json,
            )

            self.assertEqual(subclass, "chart_values_suppressed_workload")
            self.assertTrue(diagnostics.get("chart_values_suppressed"))

    def test_evidence_collection_failed(self) -> None:
        """When evidence collection fails due to parse error.
        
        Expected: render_apply_evidence_collection_failed
        
        Note: Empty rendered manifest is classified as rendered_manifest_missing_deployment,
        not evidence_collection_failed. This test uses malformed YAML to trigger parse failure.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"

            deployments_json = json.dumps({"items": []})

            # Malformed YAML that will fail to parse
            rendered_manifest = """
apiVersion: apps/v1
kind: Deployment
  metadata:
    name: k9b
  invalid: indent
"""

            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                rendered_manifest_yaml=rendered_manifest,
            )

            self.assertEqual(subclass, "render_apply_evidence_collection_failed")

    def test_transient_pvc_with_missing_deployment(self) -> None:
        """When transient PVC VolumeBinding conflict plus missing Deployment.
        
        Expected: primary is expected_workload_missing (subclass),
                  PVC conflict remains secondary diagnostics.
        
        Note: Empty rendered_manifest_yaml indicates evidence collection failure,
        not rendered_manifest_missing_deployment. The test provides actual YAML content.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            namespace = "test-ns"

            # Empty cluster - deployment never appeared
            deployments_json = json.dumps({"items": []})
            
            # Provide actual YAML content (empty cluster but manifest was rendered)
            rendered_manifest = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: some-config
"""

            subclass, diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                rendered_manifest_yaml=rendered_manifest,
            )

            # Primary should be expected_workload_missing sub-classified
            self.assertEqual(subclass, "rendered_manifest_missing_deployment")
            self.assertFalse(diagnostics.get("cluster_deployment_present"))


class TestArtifactDirectoryCreation(unittest.TestCase):
    """Tests for artifact directory creation."""

    def test_helm_directory_created(self) -> None:
        """Workload inventory should create helm/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            inventory = {
                "expected": {"kind": "Deployment", "name": "k9b"},
                "rendered": {"deployment_k9b_present": True, "all_workloads": []},
                "parse_errors": [],
            }

            output_path = write_workload_inventory(artifact_dir, inventory)

            self.assertTrue(output_path.exists())
            self.assertTrue((artifact_dir / "helm").exists())


if __name__ == "__main__":
    unittest.main()

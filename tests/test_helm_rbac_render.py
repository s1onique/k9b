"""Tests for Helm chart RBAC rendering.

These tests verify that the Helm chart correctly renders:
- ClusterRole with nodes and monitoring CRDs when clusterScoped=true
- Role with namespace-scoped resources when clusterScoped=false

Uses `helm template` for rendering (subprocess, no SDK dependency).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


def render_manifest(chart_path: Path, values: dict[str, Any]) -> list[dict[str, Any]]:
    """Render the chart manifest using `helm template`.

    Args:
        chart_path: Path to the Helm chart
        values: Helm values dict

    Returns:
        List of parsed YAML documents

    Raises:
        RuntimeError: If helm template fails
    """
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        import json

        json.dump(values, f)
        values_file = f.name

    try:
        result = subprocess.run(
            [
                "helm",
                "template",
                "k9b",
                str(chart_path),
                "-f",
                values_file,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"helm template failed: {exc.stderr}"
        ) from exc
    finally:
        Path(values_file).unlink(missing_ok=True)

    docs: list[Any] = list(yaml.safe_load_all(result.stdout))
    return docs


def get_cluster_role(docs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Get ClusterRole from rendered documents."""
    for doc in docs:
        if doc.get("kind") == "ClusterRole":
            return doc
    return None


def get_role(docs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Get Role from rendered documents."""
    for doc in docs:
        if doc.get("kind") == "Role":
            return doc
    return None


def get_role_rules(role: dict[str, Any]) -> list[dict[str, Any]]:
    """Get rules from ClusterRole or Role."""
    return role.get("rules") or []


def get_resources_in_rule(rule: dict[str, Any]) -> list[str]:
    """Get resources from a rule."""
    return rule.get("resources") or []


class TestClusterScopedRBAC:
    """Test cluster-scoped RBAC rendering (clusterScoped=true)."""

    @pytest.fixture
    def cluster_scoped_docs(self) -> list[dict[str, Any]]:
        """Render chart with clusterScoped=true."""
        chart_path = Path(__file__).resolve().parents[1] / "charts" / "k9b"
        values = {"rbac": {"create": True, "clusterScoped": True}}
        return render_manifest(chart_path, values)

    def test_renders_cluster_role(self, cluster_scoped_docs: list[dict[str, Any]]) -> None:
        """Should render ClusterRole when clusterScoped=true."""
        cluster_role = get_cluster_role(cluster_scoped_docs)
        assert cluster_role is not None, "Should render ClusterRole"
        assert cluster_role.get("kind") == "ClusterRole"

    def test_cluster_role_has_nodes(self, cluster_scoped_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should include nodes resource."""
        cluster_role = get_cluster_role(cluster_scoped_docs)
        assert cluster_role is not None
        rules = get_role_rules(cluster_role)

        all_resources = []
        for rule in rules:
            all_resources.extend(get_resources_in_rule(rule))

        assert "nodes" in all_resources, "ClusterRole should include nodes resource"

    def test_cluster_role_has_monitoring_coreos_crd(
        self, cluster_scoped_docs: list[dict[str, Any]]
    ) -> None:
        """ClusterRole should include monitoring.coreos.com CRDs."""
        cluster_role = get_cluster_role(cluster_scoped_docs)
        assert cluster_role is not None
        rules = get_role_rules(cluster_role)

        # Find rules for monitoring.coreos.com
        monitoring_rules = [
            r for r in rules if r.get("apiGroups", []) and "monitoring.coreos.com" in r["apiGroups"]
        ]
        assert len(monitoring_rules) > 0, "ClusterRole should have monitoring.coreos.com rules"

        # Check for alertmanagers resource
        all_resources = []
        for rule in monitoring_rules:
            all_resources.extend(get_resources_in_rule(rule))
        assert "alertmanagers" in all_resources, "Should include alertmanagers CRD"

    def test_cluster_role_has_victoriametrics_crd(
        self, cluster_scoped_docs: list[dict[str, Any]]
    ) -> None:
        """ClusterRole should include operator.victoriametrics.com CRDs."""
        cluster_role = get_cluster_role(cluster_scoped_docs)
        assert cluster_role is not None
        rules = get_role_rules(cluster_role)

        # Find rules for operator.victoriametrics.com
        vm_rules = [
            r
            for r in rules
            if r.get("apiGroups", []) and "operator.victoriametrics.com" in r["apiGroups"]
        ]
        assert len(vm_rules) > 0, "ClusterRole should have operator.victoriametrics.com rules"

        # Check for vmalerts resource
        all_resources = []
        for rule in vm_rules:
            all_resources.extend(get_resources_in_rule(rule))
        assert "vmalerts" in all_resources, "Should include vmalerts CRD"

    def test_no_role_when_cluster_scoped(
        self, cluster_scoped_docs: list[dict[str, Any]]
    ) -> None:
        """Should NOT render Role when clusterScoped=true."""
        role = get_role(cluster_scoped_docs)
        assert role is None, "Should NOT render Role when clusterScoped=true"


class TestNamespaceScopedRBAC:
    """Test namespace-scoped RBAC rendering (clusterScoped=false)."""

    @pytest.fixture
    def namespace_scoped_docs(self) -> list[dict[str, Any]]:
        """Render chart with clusterScoped=false."""
        chart_path = Path(__file__).resolve().parents[1] / "charts" / "k9b"
        values = {"rbac": {"create": True, "clusterScoped": False}}
        return render_manifest(chart_path, values)

    def test_renders_role(self, namespace_scoped_docs: list[dict[str, Any]]) -> None:
        """Should render Role when clusterScoped=false."""
        role = get_role(namespace_scoped_docs)
        assert role is not None, "Should render Role"
        assert role.get("kind") == "Role"

    def test_role_has_no_nodes_in_core_resources(self, namespace_scoped_docs: list[dict[str, Any]]) -> None:
        """Role should NOT include nodes in core API group resources (cluster-scoped)."""
        role = get_role(namespace_scoped_docs)
        assert role is not None
        rules = get_role_rules(role)

        # Check core API group rules (where nodes would be problematic for namespace-scoped RBAC)
        core_rules = [r for r in rules if r.get("apiGroups", []) == [""]]
        assert len(core_rules) > 0, "Role should have core API group rules"

        for rule in core_rules:
            resources = get_resources_in_rule(rule)
            assert "nodes" not in resources, (
                "Role should NOT include nodes in core API group (namespace-scoped)"
            )

    def test_role_has_no_monitoring_crds(
        self, namespace_scoped_docs: list[dict[str, Any]]
    ) -> None:
        """Role should NOT include monitoring CRDs (cluster-scoped)."""
        role = get_role(namespace_scoped_docs)
        assert role is not None
        rules = get_role_rules(role)

        # Check for monitoring.coreos.com
        for rule in rules:
            api_groups = rule.get("apiGroups", [])
            assert "monitoring.coreos.com" not in api_groups, (
                "Role should NOT include monitoring.coreos.com (cluster-scoped)"
            )

    def test_no_cluster_role_when_namespace_scoped(
        self, namespace_scoped_docs: list[dict[str, Any]]
    ) -> None:
        """Should NOT render ClusterRole when clusterScoped=false."""
        cluster_role = get_cluster_role(namespace_scoped_docs)
        assert cluster_role is None, "Should NOT render ClusterRole when clusterScoped=false"


class TestLiveLabValuesRBAC:
    """Test that values-live-lab.yaml renders cluster-scoped RBAC."""

    @pytest.fixture
    def live_lab_docs(self) -> list[dict[str, Any]]:
        """Render chart with values-live-lab.yaml."""
        chart_path = Path(__file__).resolve().parents[1] / "charts" / "k9b"
        values_path = Path(__file__).resolve().parents[1] / "charts" / "k9b" / "values-live-lab.yaml"

        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(values_path.read_text())
            values_file = f.name

        try:
            result = subprocess.run(
                [
                    "helm",
                    "template",
                    "k9b",
                    str(chart_path),
                    "-f",
                    values_file,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"helm template failed: {exc.stderr}"
            ) from exc
        finally:
            Path(values_file).unlink(missing_ok=True)

        docs: list[Any] = list(yaml.safe_load_all(result.stdout))
        return docs

    def test_live_lab_uses_cluster_scoped_rbac(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """values-live-lab.yaml should use cluster-scoped RBAC."""
        cluster_role = get_cluster_role(live_lab_docs)
        assert cluster_role is not None, (
            "values-live-lab.yaml should render ClusterRole (clusterScoped: true)"
        )

    def test_live_lab_cluster_role_has_nodes(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole from values-live-lab.yaml should include nodes."""
        cluster_role = get_cluster_role(live_lab_docs)
        assert cluster_role is not None
        rules = get_role_rules(cluster_role)

        all_resources = []
        for rule in rules:
            all_resources.extend(get_resources_in_rule(rule))

        assert "nodes" in all_resources, (
            "values-live-lab.yaml ClusterRole should include nodes for snapshot collection"
        )

    def test_live_lab_cluster_role_has_monitoring_crds(
        self, live_lab_docs: list[dict[str, Any]]
    ) -> None:
        """ClusterRole from values-live-lab.yaml should include monitoring CRDs."""
        cluster_role = get_cluster_role(live_lab_docs)
        assert cluster_role is not None
        rules = get_role_rules(cluster_role)

        # Check for monitoring.coreos.com
        monitoring_api_groups = [
            r["apiGroups"] for r in rules if "monitoring.coreos.com" in r.get("apiGroups", [])
        ]
        assert len(monitoring_api_groups) > 0, (
            "values-live-lab.yaml ClusterRole should include monitoring.coreos.com"
        )


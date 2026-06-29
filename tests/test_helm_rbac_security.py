"""Security hardening tests for Helm chart RBAC rendering.

These tests verify the rendered ClusterRole does NOT have dangerous
permissions that could expand access beyond what is needed.

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


def get_role_rules(role: dict[str, Any]) -> list[dict[str, Any]]:
    """Get rules from ClusterRole or Role."""
    return role.get("rules") or []


class TestLiveLabSecurityHardening:
    """Negative security assertions for live-lab ClusterRole.

    These tests verify the rendered ClusterRole does NOT have dangerous
    permissions that could expand access beyond what is needed.
    """

    # Dangerous verbs that should never appear in read-only RBAC
    WRITE_VERBS = {
        "create",
        "update",
        "patch",
        "delete",
        "deletecollection",
        "impersonate",
        "escalate",
        "bind",
    }

    # Dangerous resources that could lead to privilege escalation
    DANGEROUS_RESOURCES = {
        "secrets",
        "pods/exec",
        "pods/portforward",
        "nodes/proxy",
    }

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

    def _get_all_rules(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract all rules from ClusterRole."""
        cluster_role = get_cluster_role(docs)
        if cluster_role is None:
            return []
        return get_role_rules(cluster_role)

    def _get_all_verbs(self, docs: list[dict[str, Any]]) -> set[str]:
        """Collect all verbs used across all rules."""
        verbs: set[str] = set()
        for rule in self._get_all_rules(docs):
            verbs.update(rule.get("verbs", []))
        return verbs

    def _get_all_resources(self, docs: list[dict[str, Any]]) -> list[str]:
        """Collect all resources across all rules."""
        resources: list[str] = []
        for rule in self._get_all_rules(docs):
            resources.extend(rule.get("resources", []))
        return resources

    def _get_all_api_groups(self, docs: list[dict[str, Any]]) -> list[str]:
        """Collect all apiGroups across all rules."""
        api_groups: list[str] = []
        for rule in self._get_all_rules(docs):
            api_groups.extend(rule.get("apiGroups", []))
        return api_groups

    def test_no_wildcard_api_groups(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should not use wildcard apiGroups."""
        api_groups = self._get_all_api_groups(live_lab_docs)
        assert "*" not in api_groups, (
            "ClusterRole should not use wildcard apiGroups: found '*'"
        )

    def test_no_wildcard_resources(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should not use wildcard resources."""
        resources = self._get_all_resources(live_lab_docs)
        assert "*" not in resources, (
            "ClusterRole should not use wildcard resources: found '*'"
        )

    def test_no_wildcard_verbs(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should not use wildcard verbs."""
        verbs = self._get_all_verbs(live_lab_docs)
        assert "*" not in verbs, (
            "ClusterRole should not use wildcard verbs: found '*'"
        )

    def test_only_read_verbs(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should only use get/list/watch verbs (read-only)."""
        verbs = self._get_all_verbs(live_lab_docs)
        write_verbs_found = verbs & self.WRITE_VERBS
        assert not write_verbs_found, (
            f"ClusterRole should not use write verbs. Found: {write_verbs_found}"
        )

    def test_no_secrets(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should not have secrets permissions."""
        resources = self._get_all_resources(live_lab_docs)
        assert "secrets" not in resources, (
            "ClusterRole should not have secrets permission (credential exfiltration risk)"
        )

    def test_no_pods_exec(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should not have pods/exec permission."""
        resources = self._get_all_resources(live_lab_docs)
        assert "pods/exec" not in resources, (
            "ClusterRole should not have pods/exec permission (container escape risk)"
        )

    def test_no_pods_portforward(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should not have pods/portforward permission."""
        resources = self._get_all_resources(live_lab_docs)
        assert "pods/portforward" not in resources, (
            "ClusterRole should not have pods/portforward permission"
        )

    def test_no_nodes_proxy(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRole should not have nodes/proxy permission."""
        resources = self._get_all_resources(live_lab_docs)
        assert "nodes/proxy" not in resources, (
            "ClusterRole should not have nodes/proxy permission (node takeover risk)"
        )

    def test_cluster_role_binding_exists(self, live_lab_docs: list[dict[str, Any]]) -> None:
        """ClusterRoleBinding should be rendered."""
        for doc in live_lab_docs:
            if doc.get("kind") == "ClusterRoleBinding":
                return  # Found
        assert False, "ClusterRoleBinding should be rendered"

    def test_cluster_role_binding_references_k9b_cluster_role(
        self, live_lab_docs: list[dict[str, Any]]
    ) -> None:
        """ClusterRoleBinding roleRef should point to the k9b ClusterRole."""
        cluster_role_name = None
        for doc in live_lab_docs:
            if doc.get("kind") == "ClusterRole":
                cluster_role_name = doc.get("metadata", {}).get("name")
                break

        assert cluster_role_name is not None, "Should have a ClusterRole"

        for doc in live_lab_docs:
            if doc.get("kind") == "ClusterRoleBinding":
                role_ref = doc.get("roleRef", {})
                assert role_ref.get("kind") == "ClusterRole", (
                    "ClusterRoleBinding roleRef should be ClusterRole"
                )
                assert role_ref.get("name") == cluster_role_name, (
                    f"ClusterRoleBinding should reference ClusterRole '{cluster_role_name}'"
                )
                return

        assert False, "ClusterRoleBinding should be rendered"

    def test_cluster_role_binding_subject_is_service_account(
        self, live_lab_docs: list[dict[str, Any]]
    ) -> None:
        """ClusterRoleBinding subject should be a ServiceAccount."""
        for doc in live_lab_docs:
            if doc.get("kind") == "ClusterRoleBinding":
                subjects = doc.get("subjects", [])
                assert len(subjects) > 0, "ClusterRoleBinding should have subjects"
                for subject in subjects:
                    assert subject.get("kind") == "ServiceAccount", (
                        "ClusterRoleBinding subject should be ServiceAccount"
                    )
                return

        assert False, "ClusterRoleBinding should be rendered"

    def test_cluster_role_binding_subject_matches_deployment_sa(
        self, live_lab_docs: list[dict[str, Any]]
    ) -> None:
        """ClusterRoleBinding subject SA should match scheduler deployment SA."""
        # Find the ServiceAccount name used by the scheduler deployment
        sa_name = None
        for doc in live_lab_docs:
            if doc.get("kind") == "ServiceAccount":
                sa_name = doc.get("metadata", {}).get("name")
                break

        assert sa_name is not None, "Should have a ServiceAccount"

        # Find the ClusterRoleBinding subject
        for doc in live_lab_docs:
            if doc.get("kind") == "ClusterRoleBinding":
                subjects = doc.get("subjects", [])
                sa_subjects = [s for s in subjects if s.get("kind") == "ServiceAccount"]
                assert len(sa_subjects) > 0, "ClusterRoleBinding should have ServiceAccount subject"
                for subject in sa_subjects:
                    assert subject.get("name") == sa_name, (
                        f"ClusterRoleBinding should reference ServiceAccount '{sa_name}'"
                    )
                return

        assert False, "ClusterRoleBinding should be rendered"

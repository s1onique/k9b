#!/usr/bin/env python3
"""Tests for fixture namespace renderer and verifier."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

from tests.fixtures.test_cnpg_live_lab_fixture_fixtures import (
    FIXTURE_CLUSTER_SCOPED,
    FIXTURE_MIXED_RESOURCES,
    FIXTURE_NAMESPACE_OBJECT_WRONG,
    FIXTURE_NO_NAMESPACE,
    FIXTURE_WITH_CORRECT_NAMESPACE,
    FIXTURE_WITH_HARDCODED_NAMESPACE,
)

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from k9b_cnpg_live_lab_fixture_render import (
    cmd_render,
    cmd_verify,
    cmd_verify_all,
    is_cluster_scoped,
    is_namespaced_kind,
    parse_yaml_documents,
    render_fixture,
    verify_fixture,
)


class TestIsClusterScoped:
    def test_namespace_is_cluster_scoped(self) -> None:
        assert is_cluster_scoped("Namespace") is True

    def test_node_is_cluster_scoped(self) -> None:
        assert is_cluster_scoped("Node") is True

    def test_persistentvolume_is_cluster_scoped(self) -> None:
        assert is_cluster_scoped("PersistentVolume") is True

    def test_clusterrole_is_cluster_scoped(self) -> None:
        assert is_cluster_scoped("ClusterRole") is True

    def test_clusterrolebinding_is_cluster_scoped(self) -> None:
        assert is_cluster_scoped("ClusterRoleBinding") is True

    def test_pod_is_not_cluster_scoped(self) -> None:
        assert is_cluster_scoped("Pod") is False

    def test_service_is_not_cluster_scoped(self) -> None:
        assert is_cluster_scoped("Service") is False

    def test_configmap_is_not_cluster_scoped(self) -> None:
        assert is_cluster_scoped("ConfigMap") is False

    def test_deployment_is_not_cluster_scoped(self) -> None:
        assert is_cluster_scoped("Deployment") is False

    def test_unknown_kind_is_not_cluster_scoped(self) -> None:
        assert is_cluster_scoped("CustomKind") is False


class TestIsNamespacedKind:
    def test_pod_is_namespaced_kind(self) -> None:
        assert is_namespaced_kind("Pod") is True

    def test_service_is_namespaced_kind(self) -> None:
        assert is_namespaced_kind("Service") is True

    def test_configmap_is_namespaced_kind(self) -> None:
        assert is_namespaced_kind("ConfigMap") is True

    def test_deployment_is_namespaced_kind(self) -> None:
        assert is_namespaced_kind("Deployment") is True

    def test_namespace_is_not_namespaced_kind(self) -> None:
        assert is_namespaced_kind("Namespace") is False

    def test_node_is_not_namespaced_kind(self) -> None:
        assert is_namespaced_kind("Node") is False

    def test_unknown_kind_returns_false(self) -> None:
        assert is_namespaced_kind("CustomKind") is False


class TestParseYamlDocuments:
    def test_parse_single_document(self) -> None:
        docs = parse_yaml_documents(FIXTURE_WITH_HARDCODED_NAMESPACE)
        assert len(docs) == 1
        assert docs[0]["kind"] == "Pod"
        assert docs[0]["metadata"]["name"] == "failing-app"

    def test_parse_multiple_documents(self) -> None:
        docs = parse_yaml_documents(FIXTURE_MIXED_RESOURCES)
        assert len(docs) == 3
        assert docs[0]["kind"] == "Namespace"
        assert docs[1]["kind"] == "Pod"
        assert docs[2]["kind"] == "ConfigMap"

    def test_parse_empty_content(self) -> None:
        docs = parse_yaml_documents("")
        assert len(docs) == 0

    def test_parse_comments_only(self) -> None:
        docs = parse_yaml_documents("# just a comment\n# another comment")
        assert len(docs) == 0


class TestVerifyFixture:
    def test_fixture_with_hardcoded_namespace_fails(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        fixture_path.write_text(FIXTURE_WITH_HARDCODED_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        is_compliant, violations = verify_fixture(fixture_path, target_ns)
        assert is_compliant is False
        assert len(violations) == 1
        assert violations[0]["fixture_namespace"] == "cnpg-lab"

    def test_fixture_with_correct_namespace_passes(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        fixture_path.write_text(FIXTURE_WITH_CORRECT_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        is_compliant, violations = verify_fixture(fixture_path, target_ns)
        assert is_compliant is True
        assert len(violations) == 0

    def test_fixture_without_namespace_passes(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        fixture_path.write_text(FIXTURE_NO_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        is_compliant, violations = verify_fixture(fixture_path, target_ns)
        assert is_compliant is True
        assert len(violations) == 0

    def test_fixture_not_found(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "nonexistent.yaml"
        target_ns = "k9b-cnpg-lab-12345678"
        is_compliant, violations = verify_fixture(fixture_path, target_ns)
        assert is_compliant is False
        assert "not found" in violations[0]["error"].lower()


class TestRenderFixture:
    def test_render_fixes_hardcoded_namespace(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "rendered.yaml"
        fixture_path.write_text(FIXTURE_WITH_HARDCODED_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        success, issues = render_fixture(fixture_path, output_path, target_ns)
        assert success is True  # Normalizable, not fatal
        assert len(issues) == 1
        assert output_path.exists()
        rendered = output_path.read_text()
        assert target_ns in rendered

    def test_render_preserves_correct_namespace(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "rendered.yaml"
        fixture_path.write_text(FIXTURE_WITH_CORRECT_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        success, issues = render_fixture(fixture_path, output_path, target_ns)
        assert success is True
        assert len(issues) == 0
        assert output_path.exists()

    def test_render_sets_missing_namespace(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "rendered.yaml"
        fixture_path.write_text(FIXTURE_NO_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        success, issues = render_fixture(fixture_path, output_path, target_ns)
        assert success is True
        assert output_path.exists()
        rendered = output_path.read_text()
        assert target_ns in rendered

    def test_render_preserves_cluster_scoped_when_allowed(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "rendered.yaml"
        fixture_path.write_text(FIXTURE_CLUSTER_SCOPED)
        target_ns = "k9b-cnpg-lab-12345678"
        success, issues = render_fixture(fixture_path, output_path, target_ns, allow_cluster_scoped=True)
        assert success is True
        assert output_path.exists()

    def test_render_rejects_cluster_scoped_by_default(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "rendered.yaml"
        fixture_path.write_text(FIXTURE_CLUSTER_SCOPED)
        target_ns = "k9b-cnpg-lab-12345678"
        success, issues = render_fixture(fixture_path, output_path, target_ns, allow_cluster_scoped=False)
        assert success is False
        assert len(issues) == 1
        assert issues[0]["problem"] == "cluster_scoped_resource"

    def test_render_namespace_object_wrong_name_fails(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "rendered.yaml"
        fixture_path.write_text(FIXTURE_NAMESPACE_OBJECT_WRONG)
        target_ns = "k9b-cnpg-lab-12345678"
        success, issues = render_fixture(fixture_path, output_path, target_ns)
        assert success is False
        assert len(issues) == 1
        assert issues[0]["problem"] == "namespace_object_mismatch"

    def test_render_creates_output_directory(self, tmp_path: Path) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "subdir" / "rendered.yaml"
        fixture_path.write_text(FIXTURE_NO_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        success, issues = render_fixture(fixture_path, output_path, target_ns)
        assert success is True
        assert output_path.exists()


class TestCmdVerify:
    def test_cmd_verify_fails_on_hardcoded_namespace(self, tmp_path: Path, capsys: object) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        fixture_path.write_text(FIXTURE_WITH_HARDCODED_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        exit_code = cmd_verify(str(fixture_path), target_ns)
        assert exit_code == 1

    def test_cmd_verify_passes_on_correct_namespace(self, tmp_path: Path, capsys: object) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        fixture_path.write_text(FIXTURE_WITH_CORRECT_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        exit_code = cmd_verify(str(fixture_path), target_ns)
        assert exit_code == 0


class TestCmdVerifyAll:
    def test_cmd_verify_all_finds_violations(self, tmp_path: Path, capsys: object) -> None:
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        (fixtures_dir / "good.yaml").write_text(FIXTURE_WITH_CORRECT_NAMESPACE)
        (fixtures_dir / "bad.yaml").write_text(FIXTURE_WITH_HARDCODED_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        exit_code = cmd_verify_all(str(fixtures_dir), target_ns)
        assert exit_code == 1

    def test_cmd_verify_all_passes_when_all_compliant(self, tmp_path: Path, capsys: object) -> None:
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        (fixtures_dir / "good1.yaml").write_text(FIXTURE_WITH_CORRECT_NAMESPACE)
        (fixtures_dir / "good2.yaml").write_text(FIXTURE_NO_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        exit_code = cmd_verify_all(str(fixtures_dir), target_ns)
        assert exit_code == 0


class TestCmdRender:
    def test_cmd_render_writes_result_artifact(self, tmp_path: Path, capsys: object) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "rendered.yaml"
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()
        fixture_path.write_text(FIXTURE_WITH_HARDCODED_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        exit_code = cmd_render(str(fixture_path), str(output_path), target_ns, str(artifact_dir))
        assert exit_code == 0  # Normalizable now
        result_path = artifact_dir / "fixture-render-result.json"
        assert result_path.exists()
        result = json.loads(result_path.read_text())
        assert result["success"] is True

    def test_cmd_render_success_writes_result_artifact(self, tmp_path: Path, capsys: object) -> None:
        fixture_path = tmp_path / "fixture.yaml"
        output_path = tmp_path / "rendered.yaml"
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()
        fixture_path.write_text(FIXTURE_NO_NAMESPACE)
        target_ns = "k9b-cnpg-lab-12345678"
        exit_code = cmd_render(str(fixture_path), str(output_path), target_ns, str(artifact_dir))
        assert exit_code == 0


class TestLiveLabFixture:
    def test_actual_live_lab_fixture_has_hardcoded_namespace(self) -> None:
        fixture_path = Path(__file__).parent.parent / "fixtures" / "lab" / "live" / "pod-failure" / "injected-change.yaml"
        if not fixture_path.exists():
            pytest.skip(f"Live lab fixture not found at {fixture_path}")
        content = fixture_path.read_text()
        docs = parse_yaml_documents(content)
        pod_docs = [d for d in docs if d.get("kind") == "Pod"]
        assert len(pod_docs) >= 1
        pod = pod_docs[0]
        assert pod["metadata"]["namespace"] == "cnpg-lab"

    def test_actual_live_lab_fixture_fails_verification(self) -> None:
        fixture_path = Path(__file__).parent.parent / "fixtures" / "lab" / "live" / "pod-failure" / "injected-change.yaml"
        if not fixture_path.exists():
            pytest.skip(f"Live lab fixture not found at {fixture_path}")
        target_ns = "k9b-cnpg-lab-28015830396"
        is_compliant, violations = verify_fixture(fixture_path, target_ns)
        assert is_compliant is False
        assert len(violations) >= 1
        ns_violations = [v for v in violations if v.get("fixture_namespace") == "cnpg-lab"]
        assert len(ns_violations) >= 1

    def test_actual_live_lab_fixture_can_be_rendered(self) -> None:
        fixture_path = Path(__file__).parent.parent / "fixtures" / "lab" / "live" / "pod-failure" / "injected-change.yaml"
        if not fixture_path.exists():
            pytest.skip(f"Live lab fixture not found at {fixture_path}")
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "rendered.yaml"
            target_ns = "k9b-cnpg-lab-28015830396"
            success, issues = render_fixture(fixture_path, output_path, target_ns)
            assert success is True
            assert output_path.exists()
            rendered = output_path.read_text()
            assert target_ns in rendered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

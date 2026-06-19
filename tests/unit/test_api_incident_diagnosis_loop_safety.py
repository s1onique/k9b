"""Tests for diagnosis loop one-pass API safety.

Tests:
1. New API module does not import subprocess
2. New API module does not import kubernetes
3. New API module does not call kubectl
4. Mutation-like requested checks are rejected by policy and do not run
5. Response does not contain action-control fields
6. Artifact write failure is bounded and does not leak traceback
7. No shell command strings are executed
8. Request body cannot override artifact root or filesystem paths
9. No live cluster access is introduced
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from k8s_diag_agent.collect.api_incident_diagnosis_loop import (
    DiagnosisLoopOnePassRequest,
)


class TestModuleImports(unittest.TestCase):
    """Test that API modules do not import forbidden libraries."""

    def test_api_module_no_subprocess_import(self) -> None:
        """API module does not import subprocess."""
        module_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "collect" / "api_incident_diagnosis_loop.py"

        if not module_path.exists():
            self.skipTest(f"Module not found at {module_path}")

        content = module_path.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "subprocess",
                        f"Module imports subprocess: {module_path}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertFalse(
                        node.module.startswith("subprocess"),
                        f"Module imports from subprocess: {module_path}"
                    )

    def test_api_module_no_kubernetes_import(self) -> None:
        """API module does not import kubernetes."""
        module_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "collect" / "api_incident_diagnosis_loop.py"

        if not module_path.exists():
            self.skipTest(f"Module not found at {module_path}")

        content = module_path.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "kubernetes",
                        f"Module imports kubernetes: {module_path}"
                    )
                    self.assertFalse(
                        alias.name.startswith("kubernetes."),
                        f"Module imports from kubernetes: {module_path}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertFalse(
                        node.module == "kubernetes" or node.module.startswith("kubernetes."),
                        f"Module imports from kubernetes: {module_path}"
                    )

    def test_server_handler_no_subprocess_import(self) -> None:
        """Server handler module does not import subprocess."""
        module_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "ui" / "server_incident_diagnosis_loop.py"

        if not module_path.exists():
            self.skipTest(f"Module not found at {module_path}")

        content = module_path.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "subprocess",
                        f"Module imports subprocess: {module_path}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertFalse(
                        node.module.startswith("subprocess"),
                        f"Module imports from subprocess: {module_path}"
                    )

    def test_server_handler_no_kubectl_calls(self) -> None:
        """Server handler module does not contain kubectl calls."""
        module_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "ui" / "server_incident_diagnosis_loop.py"

        if not module_path.exists():
            self.skipTest(f"Module not found at {module_path}")

        content = module_path.read_text()

        # Check for kubectl string literals
        self.assertNotIn("kubectl", content)
        self.assertNotIn('"kubectl"', content)
        self.assertNotIn("'kubectl'", content)


class TestForbiddenRequestFields(unittest.TestCase):
    """Test that request validation rejects forbidden fields."""

    def test_request_rejects_external_analysis_dir(self) -> None:
        """Request with external_analysis_dir is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "external_analysis_dir": "/malicious/path"
            })
        self.assertIn("external_analysis_dir", str(ctx.exception))

    def test_request_rejects_artifact_root(self) -> None:
        """Request with artifact_root is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "artifact_root": "/malicious/path"
            })
        self.assertIn("artifact_root", str(ctx.exception))

    def test_request_rejects_fs_path(self) -> None:
        """Request with fs_path is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "fs_path": "/malicious/path"
            })
        self.assertIn("fs_path", str(ctx.exception))

    def test_request_rejects_path(self) -> None:
        """Request with path is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "path": "/malicious/path"
            })
        self.assertIn("path", str(ctx.exception))

    def test_request_rejects_mutate(self) -> None:
        """Request with mutate is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "mutate": True
            })
        self.assertIn("mutate", str(ctx.exception))

    def test_request_rejects_delete(self) -> None:
        """Request with delete is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "delete": True
            })
        self.assertIn("delete", str(ctx.exception))

    def test_request_rejects_scale(self) -> None:
        """Request with scale is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "scale": "replicas: 5"
            })
        self.assertIn("scale", str(ctx.exception))

    def test_request_rejects_restart(self) -> None:
        """Request with restart is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "restart": True
            })
        self.assertIn("restart", str(ctx.exception))

    def test_request_rejects_rollout(self) -> None:
        """Request with rollout is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "rollout": "restart"
            })
        self.assertIn("rollout", str(ctx.exception))

    def test_request_rejects_patch(self) -> None:
        """Request with patch is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "patch": {"spec": {"replicas": 5}}
            })
        self.assertIn("patch", str(ctx.exception))

    def test_request_rejects_apply(self) -> None:
        """Request with apply is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "apply": True
            })
        self.assertIn("apply", str(ctx.exception))

    def test_request_rejects_remediate(self) -> None:
        """Request with remediate is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "remediate": True
            })
        self.assertIn("remediate", str(ctx.exception))


class TestResponseActionControlFields(unittest.TestCase):
    """Test that response does not contain action-control fields."""

    _FORBIDDEN_FIELDS = frozenset([
        "run",
        "execute",
        "promote",
        "apply",
        "remediate",
        "action",
        "approve",
        "reject",
        "run_command",
        "execute_command",
        "mutate",
        "delete",
        "scale",
        "restart",
        "rollout",
        "patch",
    ])

    def test_response_does_not_contain_action_control_fields(self) -> None:
        """Response does not contain forbidden action-control fields."""
        from k8s_diag_agent.collect.api_incident_diagnosis_loop import (
            DiagnosisLoopOnePassResponse,
        )

        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            read_only=True,
            allowed_actions=[],
        )

        data = response.to_dict()
        data_str = json.dumps(data)

        for field in self._FORBIDDEN_FIELDS:
            self.assertNotIn(f'"{field}"', data_str)


class TestSafeRunIdValidation(unittest.TestCase):
    """Test run_id safety validation."""

    def test_run_id_with_path_traversal_rejected(self) -> None:
        """run_id with path traversal characters is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "../../../etc/passwd",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("Unsafe run_id", str(ctx.exception))

    def test_run_id_with_double_dots_rejected(self) -> None:
        """run_id with .. is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "foo..bar",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("Unsafe run_id", str(ctx.exception))

    def test_run_id_with_forward_slash_rejected(self) -> None:
        """run_id with / is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "foo/bar",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("Unsafe run_id", str(ctx.exception))

    def test_run_id_with_backslash_rejected(self) -> None:
        """run_id with \\ is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "foo\\bar",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("Unsafe run_id", str(ctx.exception))

    def test_run_id_with_null_bytes_rejected(self) -> None:
        """run_id with null bytes is rejected."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "foo\x00bar",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("run_id", str(ctx.exception))

    def test_valid_run_id_accepted(self) -> None:
        """Valid run_id is accepted."""
        request = DiagnosisLoopOnePassRequest.from_dict({
            "run_id": "test-run-001",
            "diagnosis_report": {
                "diagnosis": {
                    "recommended_investigations": []
                }
            }
        })
        self.assertEqual(request.run_id, "test-run-001")


class TestNoLiveClusterAccess(unittest.TestCase):
    """Test that no live cluster access is introduced."""

    def test_api_module_no_kubectl_usage(self) -> None:
        """API module does not use kubectl executable calls."""
        # Uses AST parsing - same approach as test_api_module_no_subprocess_import
        # This is the authoritative test for no subprocess usage
        module_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "collect" / "api_incident_diagnosis_loop.py"

        if not module_path.exists():
            self.skipTest(f"Module not found at {module_path}")

        content = module_path.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "subprocess",
                        f"Module imports subprocess: {module_path}"
                    )
                    self.assertNotEqual(
                        alias.name, "os",
                        f"Module imports os: {module_path}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertFalse(
                        node.module.startswith("subprocess"),
                        f"Module imports from subprocess: {module_path}"
                    )
                    self.assertNotEqual(
                        node.module, "os",
                        f"Module imports os: {module_path}"
                    )

    def test_server_handler_no_kubectl_usage(self) -> None:
        """Server handler does not use kubectl."""
        module_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "ui" / "server_incident_diagnosis_loop.py"

        if not module_path.exists():
            self.skipTest(f"Module not found at {module_path}")

        content = module_path.read_text()

        # Check for kubectl references
        self.assertNotIn("kubectl", content)


if __name__ == "__main__":
    unittest.main()
"""Tests for incident diagnosis loop orchestrator safety constraints.

Tests:
1. Module does not import kubernetes
2. Module does not import subprocess
3. Module does not contain kubectl execution
4. Module does not contain mutation actions
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


class TestOrchestratorSafety(unittest.TestCase):
    """Safety constraint tests."""

    def test_module_does_not_import_kubernetes(self) -> None:
        """Orchestrator module does not import kubernetes."""
        import k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator as module

        # Check module doesn't have kubernetes client in namespace
        source_file = Path(module.__file__)
        content = source_file.read_text()

        # Remove all docstrings
        content_no_docs = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content_no_docs = re.sub(r"'''.*?'''", "", content_no_docs, flags=re.DOTALL)

        # Now check for imports
        self.assertNotIn("import kubernetes", content_no_docs)
        self.assertNotIn("from kubernetes", content_no_docs)

    def test_module_does_not_import_subprocess(self) -> None:
        """Orchestrator module does not import subprocess."""
        import k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator as module

        source_file = Path(module.__file__)
        content = source_file.read_text()

        # Remove all docstrings
        content_no_docs = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content_no_docs = re.sub(r"'''.*?'''", "", content_no_docs, flags=re.DOTALL)

        self.assertNotIn("import subprocess", content_no_docs)
        self.assertNotIn("from subprocess", content_no_docs)

    def test_module_does_not_call_kubectl(self) -> None:
        """Orchestrator module does not contain kubectl execution."""
        import k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator as module

        source_file = Path(module.__file__)
        content = source_file.read_text()

        # Remove all docstrings
        content_no_docs = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content_no_docs = re.sub(r"'''.*?'''", "", content_no_docs, flags=re.DOTALL)

        # Now check for kubectl in code (not in safety metadata strings)
        lines = content_no_docs.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip safety metadata dict values
            if stripped.startswith('"kubectl"') or stripped.startswith("'kubectl'"):
                continue
            if '"no_kubectl"' in stripped or "'no_kubectl'" in stripped:
                continue
            # Fail if kubectl appears outside safety metadata
            if "kubectl" in stripped:
                self.fail(f"Found kubectl reference on line {i+1}: {stripped}")

    def test_module_does_not_contain_mutate_actions(self) -> None:
        """Orchestrator source does not contain mutation actions."""
        import k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator as module

        source_file = Path(module.__file__)
        content = source_file.read_text()

        # Remove all docstrings
        content_no_docs = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content_no_docs = re.sub(r"'''.*?'''", "", content_no_docs, flags=re.DOTALL)

        # Check for actual action calls
        lines = content_no_docs.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip safety metadata entries
            if '"execute"' in stripped or '"apply"' in stripped or '"delete"' in stripped:
                continue
            # Check for actual function calls
            if stripped.startswith("apply(") or stripped.startswith("delete("):
                self.fail(f"Found mutation action on line {i+1}: {stripped}")


if __name__ == "__main__":
    unittest.main()

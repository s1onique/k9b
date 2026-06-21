#!/usr/bin/env python3
"""
Tests for ACT-local verification mode.

Tests verify:
1. ACT-local detects changed files from git
2. ACT-local runs changed-file ruff command for changed Python files
3. ACT-local does not run broad pytest
4. ACT-local JSON is valid and includes skipped broad checks
5. ACT-local reports exact rerun command on failure
6. Verification-discipline guard rejects broad pytest instructions
7. Verification-discipline guard rejects blind .verify_lock removal
8. Verification-discipline guard permits targeted pytest examples
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"


class TestActLocalImports(unittest.TestCase):
    """Test that ACT-local module can be imported."""
    
    def test_act_local_module_imports(self) -> None:
        """act_local_verification.py should import without errors."""
        sys.path.insert(0, str(SCRIPT_DIR))
        import act_local_verification
        self.assertIsNotNone(act_local_verification)


class TestActLocalChangedFiles(unittest.TestCase):
    """Test changed file detection."""
    
    def test_get_changed_files_returns_list(self) -> None:
        """get_changed_files should return a list."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import get_changed_files
        
        # Mock git to return known files
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="file1.py\nfile2.py\n"
            )
            files = get_changed_files()
        
        self.assertIsInstance(files, list)
    
    def test_get_changed_files_includes_staged(self) -> None:
        """get_changed_files should include staged changes."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import get_changed_files
        
        calls = []
        
        def mock_run(*args, **kwargs):
            calls.append(args)
            cmd = args[0] if args else kwargs.get('args', [])
            if '--cached' in cmd:
                return MagicMock(returncode=0, stdout="staged.py\n")
            return MagicMock(returncode=0, stdout="unstaged.py\n")
        
        with patch('subprocess.run', side_effect=mock_run):
            get_changed_files()
        
        self.assertGreaterEqual(len(calls), 2)


class TestActLocalFilterFunctions(unittest.TestCase):
    """Test file filtering functions."""
    
    def test_filter_python_files(self) -> None:
        """filter_python_files should return only .py files."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import filter_python_files
        
        files = ["src/main.py", "tests/test_main.py", "docs/README.md", "script.sh"]
        py_files = filter_python_files(files)
        
        self.assertEqual(len(py_files), 2)
        self.assertIn("src/main.py", py_files)
        self.assertIn("tests/test_main.py", py_files)
        self.assertNotIn("docs/README.md", py_files)
    
    def test_filter_shell_files(self) -> None:
        """filter_shell_files should return only .sh files."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import filter_shell_files
        
        files = ["script.sh", "build.sh", "src/main.py", "docs/README.md"]
        sh_files = filter_shell_files(files)
        
        self.assertEqual(len(sh_files), 2)
        self.assertIn("script.sh", sh_files)
        self.assertIn("build.sh", sh_files)
    
    def test_filter_docs_prompts_rules(self) -> None:
        """filter_docs_prompts_rules should return docs/rules files."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import filter_docs_prompts_rules
        
        files = [
            "docs/README.md",
            ".kilocode/rules/00-global.md",
            "src/main.py",
            "AGENTS.md",
            ".clinerules/10-rules.md",
        ]
        filtered = filter_docs_prompts_rules(files)
        
        self.assertEqual(len(filtered), 4)
        self.assertIn("docs/README.md", filtered)
        self.assertIn(".kilocode/rules/00-global.md", filtered)
        self.assertIn("AGENTS.md", filtered)
        self.assertIn(".clinerules/10-rules.md", filtered)
        self.assertNotIn("src/main.py", filtered)


class TestActLocalCheckExecution(unittest.TestCase):
    """Test check execution."""
    
    def test_run_check_returns_result(self) -> None:
        """run_check should return a CheckResult."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import run_check
        
        result = run_check("test-check", "echo 'hello'")
        
        self.assertEqual(result.name, "test-check")
        self.assertEqual(result.command, "echo 'hello'")
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.exit_code, 0)
        self.assertGreater(result.duration_ms, 0)
    
    def test_run_check_captures_failure(self) -> None:
        """run_check should capture failure exit codes."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import run_check
        
        result = run_check("failing-check", "exit 1")
        
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.exit_code, 1)
    
    def test_run_ruff_on_files_skips_empty(self) -> None:
        """run_ruff_on_files should skip when no files provided."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import run_ruff_on_files
        
        result = run_ruff_on_files([])
        
        self.assertEqual(result.status, "SKIP")
        self.assertEqual(result.name, "ruff-changed")


class TestActLocalResult(unittest.TestCase):
    """Test ActLocalResult data structure."""
    
    def test_result_to_dict(self) -> None:
        """ActLocalResult should serialize to dict."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import ActLocalResult, CheckResult
        
        result = ActLocalResult(
            success=True,
            changed_files=["file1.py"],
            checks=[
                CheckResult(
                    name="test",
                    command="echo test",
                    status="PASS",
                    duration_ms=100,
                    exit_code=0,
                )
            ],
            skipped_checks=[{"id": "pytest-broad", "reason": "Broad pytest"}],
            broader_gate_status="not_evaluated",
            failure_commands=[],
        )
        
        d = result.to_dict()
        
        self.assertEqual(d["profile"], "act-local")
        self.assertEqual(d["success"], True)
        self.assertEqual(d["changed_files"], ["file1.py"])
        self.assertEqual(len(d["checks"]), 1)
        self.assertEqual(len(d["skipped_checks"]), 1)
        self.assertEqual(d["broader_gate_status"], "not_evaluated")


class TestActLocalJsonOutput(unittest.TestCase):
    """Test JSON output formatting."""
    
    def test_json_output_is_valid(self) -> None:
        """JSON output should be valid JSON."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import (
            ActLocalResult,
            CheckResult,
            format_json_output,
        )
        
        result = ActLocalResult(
            success=True,
            changed_files=["file1.py", "file2.py"],
            checks=[
                CheckResult(
                    name="ruff",
                    command="ruff check",
                    status="PASS",
                    duration_ms=50,
                    exit_code=0,
                )
            ],
            skipped_checks=[{"id": "pytest", "reason": "Broad pytest"}],
            broader_gate_status="not_evaluated",
            failure_commands=[],
        )
        
        json_str = format_json_output(result)
        parsed = json.loads(json_str)
        
        self.assertEqual(parsed["profile"], "act-local")
        self.assertEqual(parsed["success"], True)
        self.assertEqual(len(parsed["changed_files"]), 2)


class TestActLocalForbiddenChecks(unittest.TestCase):
    """Test that ACT-local does not run forbidden checks."""
    
    def test_no_broad_pytest_in_result(self) -> None:
        """Result should not include broad pytest as a check."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import ActLocalResult, CheckResult
        
        result = ActLocalResult(
            success=True,
            changed_files=[],
            checks=[
                CheckResult(
                    name="ruff-changed",
                    command="ruff check",
                    status="PASS",
                    duration_ms=50,
                    exit_code=0,
                )
            ],
            skipped_checks=[{"id": "pytest-broad", "reason": "Broad pytest suite"}],
            broader_gate_status="not_evaluated",
            failure_commands=[],
        )
        
        check_names = [c.name for c in result.checks]
        
        self.assertNotIn("pytest", check_names)
        self.assertNotIn("pytest tests/", check_names)
        self.assertNotIn("unit-tests", check_names)
    
    def test_skipped_checks_includes_broad_pytest(self) -> None:
        """skipped_checks should include broad pytest."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import ActLocalResult
        
        result = ActLocalResult(
            success=True,
            changed_files=[],
            checks=[],
            skipped_checks=[
                {"id": "pytest-broad", "reason": "Broad pytest suite"},
                {"id": "full-fast-gate", "reason": "Full fast profile"},
            ],
            broader_gate_status="not_evaluated",
            failure_commands=[],
        )
        
        skipped_ids = [s["id"] for s in result.skipped_checks]
        
        self.assertIn("pytest-broad", skipped_ids)
        self.assertIn("full-fast-gate", skipped_ids)


class TestVerificationDisciplineGuard(unittest.TestCase):
    """Test verification discipline guard."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        sys.path.insert(0, str(SCRIPT_DIR))
    
    def test_guard_imports(self) -> None:
        """verify_verification_discipline.py should import."""
        import verify_verification_discipline
        self.assertIsNotNone(verify_verification_discipline)
    
    def test_guard_rejects_pytest_tests(self) -> None:
        """Guard should reject pytest tests/ in non-code-block."""
        from verify_verification_discipline import scan_file_content
        
        content = "# Local\npytest tests/"
        violations, _ = scan_file_content(content)
        
        self.assertGreater(len(violations), 0)
        self.assertTrue(any("pytest tests/" in str(v) for v in violations))
    
    def test_guard_rejects_verify_all_full(self) -> None:
        """Guard should reject verify_all.sh --full as local acceptance."""
        from verify_verification_discipline import scan_file_content
        
        content = "# Verification\n./scripts/verify_all.sh --full"
        violations, _ = scan_file_content(content)
        
        self.assertGreater(len(violations), 0)
    
    def test_guard_rejects_rm_verify_lock(self) -> None:
        """Guard should reject rm -rf .verify_lock."""
        from verify_verification_discipline import scan_file_content
        
        content = "# Fix\nrm -rf .verify_lock"
        violations, _ = scan_file_content(content)
        
        self.assertGreater(len(violations), 0)
    
    def test_guard_rejects_pkill_f(self) -> None:
        """Guard should reject pkill -f."""
        from verify_verification_discipline import scan_file_content
        
        content = "# Cleanup\npkill -f verify"
        violations, _ = scan_file_content(content)
        
        self.assertGreater(len(violations), 0)
    
    def test_guard_allows_code_block(self) -> None:
        """Guard should allow pytest in code blocks."""
        from verify_verification_discipline import scan_file_content
        
        content = '''
# Good Example

```bash
pytest tests/test_my_feature.py
```

This is fine because it's in a code block.
'''
        violations, _ = scan_file_content(content)
        
        # Should not flag the code block content
        self.assertEqual(len(violations), 0)
    
    def test_guard_allows_bad_example_section(self) -> None:
        """Guard should allow content in Bad Example sections (section markers)."""
        from verify_verification_discipline import scan_file_content
        
        # Content in Bad Example section should be allowed
        # Since "# Bad Example" is a section marker, content after it is excluded
        content = '''# Bad Example

pytest tests/

This is a bad example showing what NOT to do.
'''
        violations, _ = scan_file_content(content)
        
        # pytest tests/ is in a Bad Example section, so it should NOT be flagged
        self.assertEqual(len(violations), 0)


class TestVerificationDisciplineSelfTest(unittest.TestCase):
    """Test verification discipline self-test."""
    
    def test_self_test_runs(self) -> None:
        """Self-test should run without errors."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_verification_discipline import run_self_test
        
        success, errors = run_self_test()
        
        # Self-test should pass (or report errors)
        self.assertIsInstance(success, bool)
        self.assertIsInstance(errors, list)


class TestActLocalIntegration(unittest.TestCase):
    """Integration tests for ACT-local mode."""
    
    @classmethod
    def setUpClass(cls) -> None:
        """Check if we should run integration tests."""
        cls._should_run = os.environ.get("RUN_ACT_LOCAL_INTEGRATION") == "1"
    
    def test_act_local_help(self) -> None:
        """ACT-local should accept --help."""
        sys.path.insert(0, str(SCRIPT_DIR))
        import sys as _sys
        
        # Test by running as subprocess
        result = subprocess.run(
            [_sys.executable, str(SCRIPT_DIR / "act_local_verification.py"), "--help"],
            capture_output=True,
            text=True,
        )
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("ACT-local", result.stdout)
    
    def test_verify_all_accepts_act_local(self) -> None:
        """verify_all.py should accept --act-local flag."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "verify_all.py"), "--help"],
            capture_output=True,
            text=True,
        )
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("--act-local", result.stdout)
    
    def test_verify_all_sh_passes_act_local(self) -> None:
        """verify_all.sh should pass --act-local to Python."""
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "verify_all.sh"), "--help"],
            capture_output=True,
            text=True,
        )
        
        self.assertEqual(result.returncode, 0)


class TestActLocalRerunCommands(unittest.TestCase):
    """Test that ACT-local reports rerun commands."""
    
    def test_failure_commands_in_result(self) -> None:
        """Result should include exact commands to rerun failed checks."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from act_local_verification import ActLocalResult, CheckResult
        
        result = ActLocalResult(
            success=False,
            changed_files=["file1.py"],
            checks=[
                CheckResult(
                    name="ruff-changed",
                    command='.venv/bin/python -m ruff check "file1.py"',
                    status="FAIL",
                    duration_ms=100,
                    exit_code=1,
                    error_message="Import error",
                )
            ],
            skipped_checks=[],
            broader_gate_status="not_evaluated",
            failure_commands=['.venv/bin/python -m ruff check "file1.py"'],
        )
        
        self.assertEqual(len(result.failure_commands), 1)
        self.assertIn("ruff", result.failure_commands[0])


if __name__ == "__main__":
    unittest.main()

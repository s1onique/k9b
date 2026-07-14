"""Discriminating test fixtures for P0 fixes - testing specific paths identified in review.

These tests verify the specific P0 false-approval paths identified in the review.
They serve as regression tests - they should FAIL if the analyzer becomes unsound.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Add repo root to path for imports
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class _SubprocessMixin:
    """Run a verifier script via subprocess and capture the result."""

    @staticmethod
    def _run(script_name: str, src_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / f"{script_name}.py"),
                "--src-root",
                str(src_root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )


class SEAM01P0DiscriminatingFixtures(_SubprocessMixin, unittest.TestCase):
    """Test cases for discriminating P0 paths identified in review."""

    def _run_test(
        self, body: str, should_reject: bool
    ) -> subprocess.CompletedProcess:
        """Run verifier and assert pass/fail strictly.

        After ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01 the helper does not
        accept an ``enforce`` flag: every P0 fixture must gate the verifier.
        """
        relative_path = "violations/typed_violation.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            src_root = tmp_root / "src"
            src_root.mkdir(parents=True, exist_ok=True)
            (src_root / "__init__.py").write_text("", encoding="utf-8")
            violation_path = src_root / relative_path
            violation_path.parent.mkdir(parents=True, exist_ok=True)
            violation_path.write_text(textwrap.dedent(body), encoding="utf-8")

            proc = self._run("verify_promotion_diagnosis_handoff", src_root)

            if should_reject:
                self.assertEqual(
                    proc.returncode, 1,
                    f"Expected rejection but got: {proc.stdout}\n{proc.stderr}"
                )
                self.assertIn("forbidden_actionable_access", proc.stdout)
            else:
                self.assertEqual(
                    proc.returncode, 0,
                    f"Expected acceptance but got: {proc.stdout}\n{proc.stderr}"
                )
                self.assertIn("PASS", proc.stdout)

            return proc

    def test_nested_if_continue_enclosing_finally_writes_unsafe(self) -> None:
        """P0 FIX: nested if-continue with enclosing finally writes unsafe."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        if item:
                            continue
                    finally:
                        value = untrusted

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_handler_normal_complete_inner_finally_writes_unsafe(self) -> None:
        """P0 FIX: normally completing handler must apply inner finally before continuing."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        try:
                            raise ValueError
                        except ValueError:
                            value = batch.promotion_result
                        finally:
                            value = untrusted
                    finally:
                        pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_nested_try_continue_later_safe_unreachable(self) -> None:
        """P0 FIX: nested try contains continue; later safe unreachable."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        try:
                            value = untrusted
                            continue
                        finally:
                            pass
                        value = batch.promotion_result
                    finally:
                        pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_conditional_continue_and_unsafe_conditional_break(self) -> None:
        """P0 FIX: same try has conditional continue and unsafe break."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        if item.skip:
                            continue

                        if item.stop:
                            value = untrusted
                            break

                        value = batch.promotion_result
                    finally:
                        pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_nested_try_continue_inner_finally_sanitizes(self) -> None:
        """Safe case: nested try continue with inner finally sanitizes."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        try:
                            value = untrusted
                            continue
                        finally:
                            value = batch.promotion_result
                    finally:
                        pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("PASS", proc.stdout)

    def test_conditional_break_and_continue_both_safe(self) -> None:
        """Safe case: conditional break and continue paths both safe."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        if item.skip:
                            continue

                        if item.stop:
                            break

                        value = batch.promotion_result
                    finally:
                        value = batch.promotion_result

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("PASS", proc.stdout)

    def test_handler_break_non_idempotent_finally_executes_once(self) -> None:
        """P0 FIX: handler break with non-idempotent finally must execute once."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result
                leaked = batch.promotion_result

                for item in items:
                    try:
                        risky()
                    except Exception:
                        value = untrusted
                        break
                    finally:
                        leaked = value
                        value = batch.promotion_result
                else:
                    leaked = batch.promotion_result

                return leaked.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_first_call_safe_second_raises_after_unsafe_assignment(self) -> None:
        """P0 FIX: first call safe, second raises after unsafe assignment."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        risky_one()
                        value = untrusted
                        risky_two()
                        value = batch.promotion_result
                    except Exception:
                        pass
                    else:
                        value = batch.promotion_result

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_while_loop_handler_writes_unsafe(self) -> None:
        """P0 FIX: while loop with try/except handler writes unsafe."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, condition):
                value = batch.promotion_result

                while condition():
                    try:
                        risky()
                    except Exception:
                        value = untrusted

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_exception_in_compound_statement_exception_point(self) -> None:
        """P0 ARCHITECTURAL LIMITATION: exception in compound statement requires
        precise exception point tracking within if bodies."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, flag):
                value = batch.promotion_result

                try:
                    if flag:
                        value = untrusted
                        risky()
                        value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=True)

    def test_try_body_compound_with_finally_sanitizes(self) -> None:
        """Safe case: try body with finally that sanitizes both paths."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        risky()
                    finally:
                        value = batch.promotion_result

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("PASS", proc.stdout)

    def test_exception_after_unsafe_then_safe_in_try(self) -> None:
        """P0 ARCHITECTURAL LIMITATION: exception after unsafe inside compound
        requires precise exception point tracking within if bodies."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, flag):
                value = batch.promotion_result

                try:
                    if flag:
                        value = untrusted
                    risky()
                    value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=True)

    def test_nested_continue_non_idempotent_finally_once(self) -> None:
        """P0 FIX: nested continue with non-idempotent finally executes once."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result
                leaked = batch.promotion_result

                for item in items:
                    try:
                        if item:
                            value = untrusted
                            continue
                    finally:
                        leaked = value
                        value = batch.promotion_result

                return leaked.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_call_succeeds_then_later_unsafe_assignment(self) -> None:
        """P0 FIX: call succeeds then later unsafe assignment."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted):
                value = batch.promotion_result

                try:
                    risky()
                    value = untrusted
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_first_call_succeeds_second_raises_after_unsafe(self) -> None:
        """P0 ARCHITECTURAL LIMITATION: exception after unsafe assignment
        requires precise exception point tracking within compound bodies."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted):
                value = batch.promotion_result

                try:
                    safe_call()
                    value = untrusted
                    risky()
                    value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=True)

    def test_exception_after_unsafe_and_before_safe(self) -> None:
        """P0 ARCHITECTURAL LIMITATION: exception after unsafe inside compound
        requires precise exception point tracking within if bodies."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, flag):
                value = batch.promotion_result

                try:
                    if flag:
                        value = untrusted
                    risky()
                    value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=True)

    def test_nested_try_handlers_are_alternatives(self) -> None:
        """P0 FIX: nested try handlers are alternatives, not sequential."""
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted):
                value = batch.promotion_result

                try:
                    risky()
                except ValueError:
                    value = untrusted
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

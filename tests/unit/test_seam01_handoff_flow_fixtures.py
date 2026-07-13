"""SEAM01 flow analysis fixtures for the promotion-diagnosis handoff verifier.

Tests prove the verifier correctly handles control flow patterns like
try/except, loops, break, and statement ordering.

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01HandoffFlowFixtures(_SubprocessMixin, unittest.TestCase):
    """SEAM01: Flow analysis fixtures for the promotion-diagnosis handoff verifier."""

    # P0 fix: Tests for try/except conservative join bypass
    # The try body path may not execute, so the handler's safe assignment
    # doesn't guarantee safety. The verifier must conservatively require ALL paths to be safe.

    def test_bypass_via_try_except_conservative_join_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids after try/except must be flagged.
        
        The exception handler assigns value = batch.promotion_result, but if
        no exception occurs, value remains untrusted. A sound verifier must
        consider the zero-exception path as unsafe.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                value = untrusted
                try:
                    risky_operation()
                except Exception:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_try_except_conservative_join.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_try_else_execution_path_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids after try/else must be flagged.
        
        The else suite runs only when the try suite completes without an exception.
        Exception-handler paths never execute it.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                value = untrusted
                try:
                    risky()
                except Exception:
                    pass
                else:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_try_else_path.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # P0 fix: Tests for for loop conservative join bypass
    # The loop body may never execute (zero-iteration path), so the safe
    # assignment inside the loop doesn't guarantee safety.

    def test_bypass_via_for_loop_conservative_join_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids after for loop must be flagged.
        
        The loop assigns value = batch.promotion_result inside the body, but if
        possibly_empty is empty, the loop never executes and value remains untrusted.
        A sound verifier must consider the zero-iteration path as unsafe.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, possibly_empty):
                value = untrusted
                for _ in possibly_empty:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_for_loop_conservative_join.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_loop_break_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids after for/break/else must be flagged.
        
        Python executes a loop's else only when the loop finishes without break.
        A break skips the else suite.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, items):
                value = untrusted
                for item in items:
                    if item:
                        break
                else:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_loop_break.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # P0 fix: Tests for statement-ordering bypass
    # Previously, a later safe assignment could sanitize an earlier unsafe access.

    def test_bypass_via_later_safe_assignment_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids before value = batch.promotion_result must be flagged.
        
        The final provenance says 'value' came from batch.promotion_result,
        but the EARLIER access is still a violation.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                value = untrusted
                leak = value.actionable_incident_ids
                value = batch.promotion_result
                return leak
            """
        )
        with _FixtureTree(
            "violation/bypass_via_later_sanitization.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_nested_statement_ordering_is_rejected(self) -> None:
        """P0 fix: Access inside if True: where safe assignment occurs after unsafe access must be flagged.
        
        The outer if begins at line 2, which is before the target line (line 5).
        The tracker processes the entire if body including the later safe assignment
        (line 6: value = batch.promotion_result), but the unsafe access (line 5)
        occurs before the safe assignment.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                if True:
                    value = untrusted
                    leak = value.actionable_incident_ids
                    value = batch.promotion_result
                return leak
            """
        )
        with _FixtureTree(
            "violation/bypass_via_nested_statement_ordering.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # P0 fix: Tests for branch merging bypass
    # Previously, the final state after if/else could appear safe even though one path was unsafe.

    def test_bypass_via_branch_merge_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids after if/else must be flagged.
        
        At a control-flow join, provenance must be considered safe only when
        ALL reachable definitions have the approved origin.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, condition):
                if condition:
                    value = untrusted
                else:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_branch_merge.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # P0 fix: Tests for same-line ordering
    # Statements on the same line must be ordered by column offset.

    def test_bypass_via_same_line_ordering_is_rejected(self) -> None:
        """P0 fix: Multiple statements on same line must be ordered by column offset.
        
        The access happens before the safe assignment, even though both are on line 3.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                result = batch.promotion_result; return untrusted.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_same_line_ordering.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_allowed_same_line_safe_access_is_accepted(self) -> None:
        """P0 fix: Safe same-line access where safe assignment comes BEFORE access.
        
        The safe assignment happens at col_offset=0, and the access happens at col_offset=38.
        This should be accepted.
        """
        body = textwrap.dedent(
            """
            def allowed(batch):
                result = batch.promotion_result; return result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "allowed/same_line_safe_access.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)

    def test_bypass_via_loop_break_inverse_polarity_is_rejected(self) -> None:
        """P0 fix: Inverse-polarity loop-else - safe on break path, unsafe on exhaustion path.
        
        The break path leaves value = batch.promotion_result (safe),
        but the exhaustion path runs the else which assigns value = untrusted (unsafe).
        Since both paths are possible, the merged result must be unsafe.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, items):
                value = batch.promotion_result
                for item in items:
                    if item:
                        break
                else:
                    value = untrusted
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_loop_break_inverse.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_nested_loop_break_does_not_affect_outer_else(self) -> None:
        """P0 fix: Inner loop break should NOT prevent outer loop's else from running.
        
        The inner loop's break exits only the inner loop.
        The outer loop's else should still execute when the outer loop exhausts.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, values, other_values):
                value = untrusted
                for outer in values:
                    for inner in other_values:
                        if inner:
                            break
                else:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/nested_loop_break.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

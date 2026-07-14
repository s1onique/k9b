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

    # =========================================================================
    # P0 fix: Tests for try/except conservative join bypass
    # The try body path may not execute, so the handler's safe assignment
    # doesn't guarantee safety. The verifier must conservatively require ALL paths to be safe.
    # =========================================================================

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
        """P0 fix: value.actionable_incident_ids after try/else with conflict must be flagged.

        The else suite runs only when the try suite completes without an exception.
        Exception-handler paths never execute it.

        This test has BOTH paths assigning different values - unsafe because:
        - Exception path: value = untrusted (unsafe)
        - Normal path: value = batch.promotion_result (safe)
        Merge returns unknown, which is unsafe.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                value = untrusted
                try:
                    risky()
                except Exception:
                    value = untrusted
                else:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_try_else_conflict.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0 fix: Tests for for loop conservative join bypass
    # The loop body may never execute (zero-iteration path), so the safe
    # assignment inside the loop doesn't guarantee safety.
    # =========================================================================

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
        """P0 fix: value.actionable_incident_ids after for loop with break must be flagged.

        The break statement exits the loop early, so the safe assignment
        might never execute. A sound verifier must conservatively handle this.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, items):
                value = untrusted
                for item in items:
                    if item.flag:
                        break
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

    # =========================================================================
    # P0 fix: Tests for statement-ordering bypass
    # Previously, a later safe assignment could sanitize an earlier unsafe access.
    # =========================================================================

    def test_bypass_via_later_safe_assignment_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids after later safe assignment must be flagged.

        The unsafe access happens BEFORE the safe assignment in source order.
        A sound verifier must consider the access position, not the final state.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                value = untrusted
                ids = value.actionable_incident_ids  # UNSAFE: before safe assignment
                value = batch.promotion_result  # safe assignment here doesn't help
                return ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_later_safe_assignment.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_nested_statement_ordering_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids after nested statements must be flagged.

        Nested statements with assignments must also respect ordering.
        The unsafe access happens before the safe assignment.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                value = untrusted
                with get_context() as ctx:
                    ids = value.actionable_incident_ids  # UNSAFE
                value = batch.promotion_result
                return ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_nested_statement_ordering.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0 fix: Tests for branch merging bypass
    # Previously, the final state after if/else could appear safe even though one path was unsafe.
    # =========================================================================

    def test_bypass_via_branch_merge_is_rejected(self) -> None:
        """P0 fix: value.actionable_incident_ids after branch merge must be flagged.

        The if branch assigns value = untrusted (unsafe), while the else
        branch assigns value = batch.promotion_result (safe).
        Merging these paths conservatively returns UNKNOWN, which is unsafe.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, condition):
                if condition:
                    value = untrusted  # unsafe path
                else:
                    value = batch.promotion_result  # safe path
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_branch_merge.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0 fix: Tests for same-line ordering
    # Statements on the same line must be ordered by column offset.
    # =========================================================================

    def test_bypass_via_same_line_ordering_is_rejected(self) -> None:
        """P0 fix: Statements on the same line must be ordered by column offset.

        The unsafe access has a smaller column offset, so it happens first.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted):
                value = untrusted; ids = value.actionable_incident_ids
                return ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_same_line_ordering.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_allowed_same_line_safe_access_is_accepted(self) -> None:
        """P0 fix: Safe assignment before unsafe access on same line is allowed.

        The safe assignment has smaller column offset, so it happens first.
        R21: Requires typed PromotionBatch parameter and canonical import.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def allowed(batch: PromotionBatch, untrusted):
                value = batch.promotion_result; ids = value.actionable_incident_ids
                return ids
            """
        )
        with _FixtureTree(
            "allowed/same_line_safe_access.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)

    # =========================================================================
    # P0 fix: Additional loop break edge cases
    # =========================================================================

    def test_bypass_via_loop_break_inverse_polarity_is_rejected(self) -> None:
        """P0 fix: Break in if inside loop creates unsafe path.

        If the condition is True, we break before safe assignment.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, items):
                value = untrusted
                for item in items:
                    if not item:
                        break
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_loop_break_inverse_polarity.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_nested_loop_break_outer_else_is_allowed(self) -> None:
        """Break inside nested loop doesn't suppress outer loop's safe assignment.

        The inner loop's break exits only the innermost loop.
        Python explicitly defines break as exiting the innermost enclosing loop.
        The outer loop's safe assignment in its else clause executes,
        so value.actionable_incident_ids is safe when batch is typed PromotionBatch.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def allowed(
                batch: PromotionBatch,
                outer_items,
                inner_items,
            ):
                for outer in outer_items:
                    for inner in inner_items:
                        if inner.flag:
                            break  # exits only inner loop
                    value = batch.promotion_result  # outer safe assignment
                else:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "ok/nested_loop_break_outer_else.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)

    def test_bypass_via_break_path_unreachable_sanitization_is_rejected(self) -> None:
        """P0 fix: Safe assignment after break is unreachable if break executes.

        The break path exits before the safe assignment, creating an unsafe path.
        """
        body = textwrap.dedent(
            """
            def bypass(batch, untrusted, items):
                value = untrusted
                for item in items:
                    if item:
                        break
                    value = batch.promotion_result
                else:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_break_unreachable_sanitization.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

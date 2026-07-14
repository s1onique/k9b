"""P0 unsoundness verification tests.

These tests verify the specific P0 bypass patterns identified in the review:
1. Nested compound break handling (assignment INSIDE nested if before break)
2. try/handler break handling (unreachable safe after break)
3. Exception handler start state (handler from completed try state)
4. continue handling (continue skips later statements)
5. Loop-else normal exhaustion (else applied to raw normal_exhaustion)

These tests serve as regression tests - they should FAIL if the analyzer
becomes unsound, and PASS once the issues are fixed.
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01P0UnsoundnessVerification(_SubprocessMixin, unittest.TestCase):
    """P0: Verify specific bypass patterns are blocked."""

    # =========================================================================
    # P0-1: Nested compound break - assignment INSIDE nested if before break
    # =========================================================================

    def test_p0_nested_if_unsafe_assignment_before_break_rejected(self) -> None:
        """P0: Assignment INSIDE nested if before break must be flagged.
        
        The review's specific bypass:
            for item in items:
                if item.enabled:
                    if item.stop:
                        value = untrusted  # INSIDE inner if, before break
                        break
        
        The existing test_typed_nested_if_break_false_path_unsafe_rejected only
        covers assignment AFTER the inner if. This test covers assignment
        INSIDE the inner if before break.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item.enabled:
                        if item.stop:
                            value = untrusted  # INSIDE inner if, before break
                            break
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_nested_if_unsafe_before_break.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-2: try/handler break handling - unreachable safe after break
    # =========================================================================

    def test_p0_try_body_unreachable_safe_after_break_rejected(self) -> None:
        """P0: Unreachable safe assignment after break in try body must be flagged.
        
        The review's specific bypass:
            for item in items:
                try:
                    value = untrusted
                    break
                    value = batch.promotion_result  # unreachable after break
                finally:
                    audit()
        
        The unreachable safe assignment should NOT overwrite the actual
        unsafe break environment.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        value = untrusted
                        break
                        value = batch.promotion_result  # unreachable after break
                    finally:
                        pass  # audit()

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_try_unreachable_safe_after_break.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-3: Exception handler start state - handler from completed try state
    # =========================================================================

    def test_p0_exception_before_later_safe_assignment_handler_breaks_rejected(self) -> None:
        """P0: Exception before later safe assignment, handler breaks → must reject.
        
        The review's specific bypass:
            for item in items:
                try:
                    value = untrusted
                    risky()
                    value = batch.promotion_result  # never runs if risky() raises
                except Exception:
                    break  # handler breaks with value=untrusted
        
        When risky() raises, the second assignment never runs and the handler
        breaks with value=untrusted. The analyzer must NOT process the completed
        try body state when starting the handler.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        value = untrusted
                        risky()
                        value = batch.promotion_result  # never runs if risky() raises
                    except Exception:
                        break

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_exception_before_later_safe_handler_breaks.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-4: continue handling - continue skips later statements
    # =========================================================================

    def test_p0_continue_skips_later_safe_assignment_rejected(self) -> None:
        """P0: continue skips later safe assignment → must reject.
        
        The review's specific bypass:
            for item in items:
                value = untrusted
                if item:
                    continue
                value = batch.promotion_result  # skipped when item is true
        
        On the item-true path, the safe assignment is skipped.
        The analyzer must NOT continue past continue and sanitize that path.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    value = untrusted
                    if item:
                        continue
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_continue_skips_later_safe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-6: Explicit else with continue in else branch - if.body path is normal
    # =========================================================================

    def test_p0_explicit_else_continue_else_body_is_normal_path(self) -> None:
        """P0: if item: value = untrusted else: continue → must reject.
        
        The review's specific bypass:
            for item in items:
                if item:
                    value = untrusted
                else:
                    continue
            
            return value.actionable_incident_ids
        
        The if.body (value = untrusted) is a NORMAL path when condition is true
        and item is truthy. The continue is ONLY in the else branch.
        The analyzer must track both paths separately.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item:
                        value = untrusted
                    else:
                        continue

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_explicit_else_continue_else_branch.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-7: Continue nested inside try/if - continue is inside compound statement
    # =========================================================================

    def test_p0_continue_nested_in_try_if_inside_try(self) -> None:
        """P0: continue nested inside if inside try → must reject.
        
        The review's specific bypass:
            for item in items:
                try:
                    value = untrusted
                    if item:
                        continue
                    value = batch.promotion_result
                finally:
                    pass
            
            return value.actionable_incident_ids
        
        When item is truthy, the continue is executed and the safe assignment
        never runs. The analyzer must detect the nested continue.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        value = untrusted

                        if item:
                            continue

                        value = batch.promotion_result
                    finally:
                        pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_continue_nested_in_try_if.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-8: Assigned call as exception point
    # =========================================================================

    def test_p0_assigned_call_raises_exception_handler_breaks(self) -> None:
        """P0: result = risky() where risky() raises → must reject.
        
        The review's specific bypass:
            for item in items:
                try:
                    value = untrusted
                    result = risky()
                    value = batch.promotion_result
                except Exception:
                    break
            
            return value.actionable_incident_ids
        
        When risky() raises, the safe assignment never runs and the handler
        breaks with value = untrusted. The analyzer must treat the assignment
        call as an exception point.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        value = untrusted
                        result = risky()
                        value = batch.promotion_result
                    except Exception:
                        break

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_assigned_call_raises_exception.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-5: Loop-else normal exhaustion - else applied to raw normal_exhaustion
    # =========================================================================

    def test_p0_loop_else_unconditional_safe_in_else_sanitizes_both_paths_accepted(self) -> None:
        """P0: Loop-else with unconditional safe in else must accept.
        
        The review says the current code executes else against zero_iter_else
        but merges raw normal_exhaustion without executing else on it.
        
        This test verifies that an unconditional safe assignment in else
        sanitizes BOTH zero-iteration and normal-exhaustion paths.
        
        Code:
            for item in items:
                value = untrusted
            else:
                value = batch.promotion_result  # unconditional safe in else
            return value.actionable_incident_ids
        
        The else runs on both paths, so this should be SAFE.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def allowed(batch: PromotionBatch, untrusted, items):
                value = untrusted

                for item in items:
                    value = untrusted
                else:
                    value = batch.promotion_result  # unconditional safe in else

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "ok/p0_loop_else_unconditional_safe_sanitizes_both.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)

    def test_p0_loop_else_safe_only_in_body_not_else_rejected(self) -> None:
        """P0: Loop-else with safe only in body (not else) → must reject.
        
        This is the inverse: safe is ONLY in body, not in else.
        Both zero-iteration and normal-exhaustion paths reach else, which
        doesn't have the safe assignment.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = untrusted

                for item in items:
                    value = batch.promotion_result  # safe only in body
                else:
                    pass  # no safe assignment in else

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_loop_else_safe_only_in_body.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-9: For-else where continue eventually reaches safe loop else
    # =========================================================================

    def test_p0_for_else_continue_eventually_reaches_safe_else_accepted(self) -> None:
        """P0: for-else with continue that eventually reaches safe else → must accept.
        
        This is a POSITIVE test case: when a continue eventually leads to the
        safe loop else (on normal exhaustion), the final state is safe.
        
        Code:
            for item in items:
                if not item.valid:
                    continue
                value = batch.promotion_result
            else:
                value = batch.promotion_result  # safe else
            
            return value.actionable_incident_ids
        
        When the loop exhausts normally, the safe else sanitizes.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def allowed(batch: PromotionBatch, items):
                for item in items:
                    if not item.valid:
                        continue
                    # process item
                else:
                    value = batch.promotion_result  # safe else on normal exhaustion

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "ok/p0_for_else_continue_reaches_safe_else.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()

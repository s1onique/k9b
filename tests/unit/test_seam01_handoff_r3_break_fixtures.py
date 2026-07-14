"""R3 typed fixtures for SEAM01 break path sensitivity.

Tests the 6 new break handling cases identified by reviewer R3:
1. Assignment inside if immediately before break, with safe else → reject
2. Unsafe break path, safe continuation, no loop else → reject
3. Break in if.orelse → reject
4. Break in exception handler after unsafe assignment → reject
5. Break inside try/finally → preserve finally semantics
6. Two break sites, first unsafe and second safe → reject

Required by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01 R3 review
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01HandoffR3BreakFixtures(_SubprocessMixin, unittest.TestCase):
    """R3: Typed polarity fixtures for advanced break path sensitivity."""

    # =========================================================================
    # R3-1: Assignment INSIDE if immediately before break
    # =========================================================================

    def test_r3_assignment_inside_if_before_break_rejected(self) -> None:
        """R3-1: value = untrusted INSIDE if before break, safe else → must reject.
        
        The key case: assignments inside the if body (before break) are part
        of the break path and must be captured. Both break and else paths
        must be merged conservatively.
        
        Code pattern:
            for item in items:
                if item:
                    value = untrusted  # <-- INSIDE if, before break
                    break
            else:
                value = batch.promotion_result  # safe else
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item:
                        value = untrusted
                        break
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_assignment_inside_if_before_break.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_r3_while_assignment_inside_if_before_break_rejected(self) -> None:
        """R3-1: Same as above but for while loop."""
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, condition):
                value = batch.promotion_result

                while condition():
                    if should_break:
                        value = untrusted
                        break
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_while_assignment_inside_if_before_break.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # R3-2: Unsafe break path, safe continuation, NO loop else
    # =========================================================================

    def test_r3_unsafe_break_no_else_rejected(self) -> None:
        """R3-2: Unsafe break path, safe continuation, no loop else → must reject.

        When loop has NO else clause, break path must still be included
        in the final merge. The break path may be unsafe even if some
        iterations are safe.

        Code pattern:
            for item in items:
                if item:
                    value = untrusted; break  # unsafe if condition is true
                value = batch.promotion_result  # safe when false
            # no else!
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item:
                        value = untrusted
                        break
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_unsafe_break_no_else.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # R3-3: Break in if.orelse (not if.body)
    # =========================================================================

    def test_r3_break_in_if_orelse_rejected(self) -> None:
        """R3-3: Break in if.orelse (not if.body) → must reject.
        
        The break detection must check BOTH if.body AND if.orelse.
        If the break is in the else branch, it should still count.
        
        Code pattern:
            for item in items:
                if item:
                    pass
                else:
                    value = untrusted
                    break
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item:
                        pass
                    else:
                        value = untrusted
                        break

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_break_in_if_orelse.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # R3-4: Break in exception handler
    # =========================================================================

    def test_r3_break_in_exception_handler_rejected(self) -> None:
        """R3-4: Break in exception handler after unsafe assignment → reject.
        
        Break detection must check try handlers, not just try body.
        
        Code pattern:
            for item in items:
                try:
                    value = untrusted
                    operation()
                except Exception:
                    break  # break is in handler
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        value = untrusted
                        operation()
                    except Exception:
                        break

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_break_in_exception_handler.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # R3-5: Break inside try/finally (preserve finally semantics)
    # =========================================================================

    def test_r3_break_in_try_finally_preserves_finally(self) -> None:
        """R3-5: Break inside try/finally → finally runs before break exits.
        
        Python semantics: finally runs BEFORE break exits the loop.
        The analyzer must apply finally effects to the break environment.
        
        Code pattern:
            for item in items:
                try:
                    value = untrusted
                    break
                finally:
                    value = batch.promotion_result  # this runs before break
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def allowed(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        value = untrusted
                        break
                    finally:
                        value = batch.promotion_result  # runs before break

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "ok/r3_break_in_try_finally.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)

    def test_r3_break_in_try_finally_unsafe_after_finally(self) -> None:
        """R3-5 variant: If finally assigns untrusted, still unsafe after finally."""
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        operation()
                        break
                    finally:
                        value = untrusted  # finally assigns untrusted

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_break_in_try_finally_unsafe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # R3-6: Two break sites, first unsafe and second safe
    # =========================================================================

    def test_r3_two_break_sites_first_unsafe_rejected(self) -> None:
        """R3-6: Two break sites, first unsafe and second safe → must reject.
        
        The analyzer must NOT overwrite the first break path with the second.
        Both break paths must be collected and merged.
        
        Code pattern:
            for item in items:
                value = untrusted  # unsafe
                if item.first:
                    break  # first break is unsafe
                value = batch.promotion_result  # safe
                if item.second:
                    break  # second break is safe
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    value = untrusted
                    if item.first:
                        break
                    value = batch.promotion_result
                    if item.second:
                        break

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_two_break_sites_first_unsafe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

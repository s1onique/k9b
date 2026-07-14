"""P0 unsoundness verification tests - Round 2.

These tests verify additional P0 bypass patterns:
- Continue path handling (feed through loop head/exhaustion model)
- Try if-continue handling (track both continue and normal paths)
- Exception handler alternatives (independent environments)

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


class SEAM01P0UnsoundnessVerificationR2(_SubprocessMixin, unittest.TestCase):
    """P0 Round 2: Additional flow analysis bypass patterns."""

    # =========================================================================
    # P0-10: Continue writes unsafe; loop later exhausts; else is no-op → reject
    # =========================================================================

    def test_p0_continue_writes_unsafe_loop_exhausts_else_noop_rejected(self) -> None:
        """P0: value = untrusted before continue, loop later exhausts, else is no-op → must reject.
        
        For items == [True]:
        1. value becomes untrusted
        2. continue starts next iteration
        3. Iterator exhausts
        4. Loop else runs (no-op)
        5. value remains untrusted
        
        The continue environment must be fed through the loop head/exhaustion model.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item:
                        value = untrusted
                        continue
                else:
                    pass  # no safe assignment

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_continue_writes_unsafe_loop_exhausts.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-11: Try if-continue true; explicit else writes unsafe → reject
    # =========================================================================

    def test_p0_try_if_continue_true_else_writes_unsafe_rejected(self) -> None:
        """P0: try with if-continue (true path), explicit else writes unsafe → must reject.
        
        The true branch continues safely, but the false branch completes normally
        with an untrusted value. Both paths must be tracked.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        if item:
                            continue
                        else:
                            value = untrusted
                    finally:
                        pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_try_if_continue_else_writes_unsafe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-12: First handler safe; second matching handler no-op → reject
    # =========================================================================

    def test_p0_first_handler_safe_second_noop_rejected(self) -> None:
        """P0: First handler assigns safe; second handler is no-op → must reject.
        
        Exception handlers are alternatives, not a sequence. Only the first
        matching handler executes. The TypeError path leaves value untrusted.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = untrusted

                for item in items:
                    try:
                        risky()
                    except ValueError:
                        value = batch.promotion_result
                    except TypeError:
                        pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_first_handler_safe_second_noop.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-13: flag and risky() raises before later safe assignment → reject
    # =========================================================================

    def test_p0_and_risky_raises_before_safe_assignment_rejected(self) -> None:
        """P0: result = flag and risky() raises before safe assignment → must reject.
        
        For 'and': if flag is true, risky() is evaluated and may raise.
        The safe assignment after it is unreachable on the exception path.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, flag, items):
                value = untrusted

                for item in items:
                    try:
                        result = flag and risky()
                        value = batch.promotion_result
                    except Exception:
                        break

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_and_risky_raises.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0-14: flag or risky() raises before later safe assignment → reject
    # =========================================================================

    def test_p0_or_risky_raises_before_safe_assignment_rejected(self) -> None:
        """P0: result = flag or risky() raises before safe assignment → must reject.
        
        For 'or': if flag is false, risky() is evaluated and may raise.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, flag, items):
                value = untrusted

                for item in items:
                    try:
                        result = flag or risky()
                        value = batch.promotion_result
                    except Exception:
                        break

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/p0_or_risky_raises.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

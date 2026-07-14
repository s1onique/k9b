"""P0 unsoundness verification tests - Round 3.

These tests verify the four remaining P0 bypass patterns:
1. Mixed break/continue loops dropping continue paths
2. Try if-continue without else implicit false branch
3. Exception handlers sequential instead of independent
4. BoolOp exception detection only checking first operand

These tests serve as regression tests - they should FAIL if the analyzer
becomes unsound, and PASS once the issues are fixed.

R3 fixtures are designed to be discriminating - they test ONLY the
claimed feature and do NOT rely on other safety mechanisms.
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01P0UnsoundnessVerificationR3(_SubprocessMixin, unittest.TestCase):
    """P0 Round 3: Four remaining flow analysis bypass patterns."""

    # =========================================================================
    # R3-1: Loop has both break and continue; unsafe continue later exhausts → reject
    # =========================================================================

    def test_r3_mixed_break_continue_loop_unsafe_continue_exhausts_rejected(self) -> None:
        """R3: Loop with both break and continue; unsafe continue later exhausts → must reject.

        The review's specific bypass:
            for item in items:
                if item.stop:
                    break
                value = untrusted
                if item.skip:
                    continue
                value = batch.promotion_result
            else:
                pass
            return value.actionable_incident_ids

        When item.stop == False and item.skip == True:
        1. value becomes untrusted
        2. continue starts the next iteration
        3. Iterator exhausts
        4. Loop else executes as a no-op
        5. value remains untrusted

        The analyzer must NOT discard continue-derived exhaustion paths
        just because there are break paths.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item.stop:
                        break
                    value = untrusted
                    if item.skip:
                        continue
                    value = batch.promotion_result
                else:
                    pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_mixed_break_continue_loop.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # R3-2: Try has if-continue without else; false path writes unsafe → reject
    # =========================================================================

    def test_r3_try_if_continue_no_else_false_path_unsafe_rejected(self) -> None:
        """R3: Try has if-continue without else; false path writes unsafe → must reject.

        The review's specific bypass:
            for item in items:
                try:
                    if item:
                        continue
                    value = untrusted
                finally:
                    pass

        When item is falsey:
        1. The continue path is skipped (item is falsey)
        2. value = untrusted executes
        3. value remains untrusted

        The implicit false-branch (no explicit else) must be tracked
        as a normal path with the untrusted value.
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
                        value = untrusted
                    finally:
                        pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_try_if_continue_no_else.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # R3-3: First handler safe-break; second handler unsafe-break → reject
    # =========================================================================

    def test_r3_first_handler_safe_second_unsafe_break_rejected(self) -> None:
        """R3: First handler safe-break; second handler unsafe-break → must reject.

        The review's specific bypass:
            for item in items:
                try:
                    value = untrusted
                    risky()
                except ValueError:
                    value = batch.promotion_result
                    break
                except TypeError:
                    break

        Exception handlers are alternatives - only the first matching handler
        executes. When TypeError is raised, the ValueError handler never runs,
        so value remains untrusted when the break happens.

        The analyzer must NOT process handlers sequentially, where the first
        handler's safe assignment would "leak" into subsequent handler analysis.
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
                    except ValueError:
                        value = batch.promotion_result
                        break
                    except TypeError:
                        break
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_handler_independence.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # R3-4: Safe initial/else paths; later BoolOp operand raises → reject
    # =========================================================================

    def test_r3_boolop_and_later_operand_raises_unsafe_break_rejected(self) -> None:
        """R3: Safe initial; flag and risky() raises; handler breaks → must reject.

        The key insight: value is assigned BEFORE the try block. When risky() raises
        inside the try, the safe assignment inside the try never runs. The exception
        handler breaks with value still safe (from before try). This is actually SAFE.

        For an UNSAFE case, we need value to be unsafe before the try, so when the
        exception prevents the safe assignment, value remains unsafe.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, flag, items):
                value = untrusted  # unsafe before try

                for item in items:
                    try:
                        result = flag and risky()
                        value = batch.promotion_result  # safe, but exception prevents this
                    except Exception:
                        break  # breaks with value=untrusted
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_boolop_and_raises.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_r3_boolop_or_later_operand_raises_unsafe_break_rejected(self) -> None:
        """R3: Safe initial; flag or risky() raises; handler breaks → must reject.

        Same as the 'and' test: value is unsafe before try, safe assignment inside
        try is prevented by exception, handler breaks with value=untrusted.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, flag, items):
                value = untrusted  # unsafe before try

                for item in items:
                    try:
                        result = flag or risky()
                        value = batch.promotion_result  # safe, but exception prevents this
                    except Exception:
                        break  # breaks with value=untrusted
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_boolop_or_raises.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_r3_finally_sanitizes_both_paths_accepted(self) -> None:
        """R3: Finally sanitizes both continue and normal paths → must accept.

        The finally clause runs when control leaves the try, sanitizing
        value on all outgoing paths. This should be accepted.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def allowed(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        if item:
                            continue
                        value = untrusted
                    finally:
                        value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "safe/r3_finally_sanitizes_both.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)

    def test_r3_first_handler_safe_second_unsafe_continue_rejected(self) -> None:
        """R3: First handler safe-continue; second handler unsafe-continue → reject.

        Exception handlers are alternatives, not sequential. The TypeError
        handler continues with value=untrusted, which must be rejected.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        risky()
                    except ValueError:
                        value = batch.promotion_result
                        continue
                    except TypeError:
                        value = untrusted
                        continue
                    finally:
                        pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_first_safe_second_unsafe_continue.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_r3_nested_if_before_continue_unsafe_rejected(self) -> None:
        """R3: Assignment inside nested if immediately before continue → must reject.

        The continue path must carry the unsafe assignment, not the pre-if state.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        if item:
                            value = untrusted
                            continue
                    finally:
                        pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_nested_if_before_continue.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_r3_exception_before_safe_assignment_handler_continues_rejected(self) -> None:
        """R3: Exception before later safe assignment; handler continues → must reject.

        When risky() raises, the later safe assignment never runs. Handler continues
        with value=untrusted.
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
                        value = batch.promotion_result
                    except ValueError:
                        continue

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_exception_before_safe_continue.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_r3_unsafe_normal_and_safe_handler_normal_rejected(self) -> None:
        """R3: Unsafe normal try completion AND safe handler normal → must reject.

        Normal try completion leaves value untrusted. Handler completes normally
        with safe value. Both paths must be tracked - the unsafe one must cause rejection.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        value = untrusted
                    except ValueError:
                        value = batch.promotion_result
                    except TypeError:
                        value = batch.promotion_result
                        continue

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_unsafe_normal_safe_handler.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_r3_try_else_writes_unsafe_on_normal_completion_rejected(self) -> None:
        """R3: try.else writes unsafe on normal completion → must reject.

        try.else runs only when try body completes normally (no exception).
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
                    except Exception:
                        value = batch.promotion_result
                    else:
                        value = untrusted
                    finally:
                        pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/r3_try_else_unsafe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

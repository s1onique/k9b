"""SEAM01 typed polarity fixtures for break path sensitivity.

Tests prove the verifier correctly handles typed PromotionBatch with break patterns.
These are separate from the base flow fixtures to stay under the 500-line limit.

Required by reviewer: Typed fixtures that import and annotate canonical
PromotionBatch to prove break handling correctness.

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01HandoffTypedBreakFixtures(_SubprocessMixin, unittest.TestCase):
    """SEAM01: Typed polarity fixtures for break path sensitivity."""

    # =========================================================================
    # Break path: unsafe assignment before break, safe else
    # =========================================================================

    def test_typed_break_unsafe_before_safe_else_rejected(self) -> None:
        """P0 R2: value = untrusted before break, safe else → must reject.
        
        When item.flag is True, break executes BEFORE safe assignment.
        The else path is skipped. Merge of break-at-untrusted and else-safe
        must be unknown (rejected).
        
        Requires typed PromotionBatch to avoid false rejection for unrelated
        unknown-provenance reasons.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    value = untrusted
                    if item.flag:
                        break
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_break_unsafe_before_safe_else.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_typed_while_break_unsafe_before_safe_else_rejected(self) -> None:
        """P0 R2: Same as above but for while loop."""
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, condition):
                value = batch.promotion_result

                while condition:
                    value = untrusted
                    if some_flag:
                        break
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_while_break_unsafe_before_safe_else.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # Conditional break: false path reaches unsafe assignment
    # =========================================================================

    def test_typed_conditional_break_false_path_unsafe_rejected(self) -> None:
        """P0 R2: if item: break; value = untrusted → must reject.
        
        When item is False, the break is NOT taken, value becomes untrusted.
        The analyzer must preserve the non-break continuation path.
        
        The reviewer example:
            for item in items:
                if item:
                    break
                value = untrusted
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item:
                        break
                    value = untrusted

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_conditional_break_false_path_unsafe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_typed_while_conditional_break_false_path_unsafe_rejected(self) -> None:
        """P0 R2: Same as above but for while loop."""
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, condition):
                value = batch.promotion_result

                while condition:
                    if should_break:
                        break
                    value = untrusted

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_while_conditional_break_false_path_unsafe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # Safe paths: should be accepted with typed PromotionBatch
    # =========================================================================

    def test_typed_identical_batch_through_unrelated_if_accepted(self) -> None:
        """Typed PromotionBatch through unrelated if should be accepted.
        
        The if has nothing to do with batch provenance - should pass.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def allowed(batch: PromotionBatch, condition):
                value = batch.promotion_result
                if condition:
                    pass  # unrelated
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "ok/typed_identical_batch_through_unrelated_if.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)

    def test_typed_variable_assigned_only_inside_if_no_else_rejected(self) -> None:
        """Variable assigned only in if-body without else → must reject.
        
        The variable may not be assigned (false path), so accessing it is unsafe.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, condition):
                if condition:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_if_no_else_only_in_body.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_typed_safe_try_body_safe_handler_no_finally_accepted(self) -> None:
        """Safe try body + safe handler (no finally) should be accepted.
        
        Both paths assign from typed PromotionBatch → safe.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def allowed(batch: PromotionBatch, condition):
                try:
                    value = batch.promotion_result
                except Exception:
                    value = batch.promotion_result
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "ok/typed_safe_try_safe_handler.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)

    # =========================================================================
    # P0 POLARITY FIXTURES: empty for/while + else, safe only in body
    # =========================================================================

    def test_typed_empty_for_else_safe_only_in_body_rejected(self) -> None:
        """P0: empty for + else, safe only in body → must reject.
        
        When items is empty, body never executes, but else still runs.
        The safe value is never assigned, so accessing actionable_incident_ids is unsafe.
        
        Python semantics: for-else runs when iterator exhausts WITHOUT break.
        Zero-iteration means iterator exhausted immediately → else runs.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = untrusted

                for item in items:
                    value = batch.promotion_result
                else:
                    pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_empty_for_else_safe_only_in_body.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_typed_initially_false_while_else_safe_only_in_body_rejected(self) -> None:
        """P0: initially-false while + else, safe only in body → must reject.
        
        When condition is initially false, body never executes, but else still runs.
        The safe value is never assigned, so accessing actionable_incident_ids is unsafe.
        
        Python semantics: while-else runs when condition becomes false WITHOUT break.
        Zero-iteration means condition was initially false → else runs.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, condition):
                value = untrusted

                while condition():
                    value = batch.promotion_result
                else:
                    pass

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_initially_false_while_else_safe_only_in_body.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0 POLARITY FIXTURES: nested if-break false path reaches unsafe
    # =========================================================================

    def test_typed_nested_if_break_false_path_unsafe_rejected(self) -> None:
        """P0: nested if-break, false path reaches unsafe assignment → must reject.
        
        When item.stop is False, the inner if's break is NOT taken,
        and the outer if's condition (item.enabled) might be True,
        allowing the unsafe assignment to execute.
        
        The nested if-break must preserve both true and false paths.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    if item.enabled:
                        if item.stop:
                            break
                        value = untrusted

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_nested_if_break_false_path_unsafe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # =========================================================================
    # P0 POLARITY FIXTURES: try/except unsafe paths
    # =========================================================================

    def test_typed_safe_try_body_unsafe_handler_rejected(self) -> None:
        """P0: safe try body, unsafe handler → must reject.
        
        When no exception occurs, value is safe.
        When exception occurs, handler assigns untrusted → unsafe.
        The analyzer must track all exception paths.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted):
                try:
                    value = batch.promotion_result
                except Exception:
                    value = untrusted

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_safe_try_unsafe_handler.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_typed_safe_handlers_unsafe_try_else_rejected(self) -> None:
        """P0: safe handlers, unsafe try-else → must reject.
        
        When exception occurs, handlers assign safe value.
        When no exception occurs, try-else assigns untrusted → unsafe.
        The analyzer must track the else path.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted):
                try:
                    value = batch.promotion_result
                except Exception:
                    value = batch.promotion_result
                else:
                    value = untrusted

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_safe_handlers_unsafe_try_else.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_typed_try_with_break_later_unsafe_rejected(self) -> None:
        """P0: try with possible break, later unsafe loop-body statement → must reject.
        
        The try contains a conditional break, but if condition is false,
        the loop continues and reaches the unsafe assignment after the try.
        The analyzer must preserve the non-break continuation path.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                for item in items:
                    try:
                        if item.stop:
                            break
                    except Exception:
                        pass

                    value = untrusted

                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/typed_try_with_break_later_unsafe.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

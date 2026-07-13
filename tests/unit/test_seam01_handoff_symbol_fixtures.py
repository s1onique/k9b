"""SEAM01 symbol analysis fixtures for the promotion-diagnosis handoff verifier.

Tests prove the verifier correctly handles symbol resolution, annotations,
and import identity verification.

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01HandoffSymbolFixtures(_SubprocessMixin, unittest.TestCase):
    """SEAM01: Symbol analysis fixtures for the promotion-diagnosis handoff verifier."""

    # P0 fix: Tests for attr_chain bypass
    # Previously, any non-None attr_chain was accepted as trusted.
    # Now only chains starting with "promotion_result" are accepted.

    def test_bypass_via_non_promotion_result_attr_chain_is_rejected(self) -> None:
        """P0 fix: Accessing batch.error_messages.actionable_incident_ids must be flagged.
        
        The attr_chain=("error_messages",) should NOT be trusted - only
        chains starting with "promotion_result" are safe.
        """
        body = textwrap.dedent(
            """
            def bypass(batch):
                value = batch.error_messages
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_non_promotion_attr.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_promotion_result_descendant_chained_access_is_rejected(self) -> None:
        """P0 fix: batch.promotion_result.error_messages.actionable_incident_ids must be flagged.
        
        The attr_chain for batch.promotion_result.error_messages is
        ("promotion_result", "error_messages"). Accessing .actionable_incident_ids
        from this descendant is NOT safe - the immediate receiver is the result
        object's error_messages field, not the result itself.
        """
        body = textwrap.dedent(
            """
            def bypass(batch):
                return batch.promotion_result.error_messages.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_promotion_result_descendant_chained.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_promotion_result_descendant_via_variable_is_rejected(self) -> None:
        """P0 fix: value = batch.promotion_result.error_messages; value.actionable_incident_ids must be flagged.
        
        Even when assigned to a variable, the provenance chain is still
        ("promotion_result", "error_messages") - NOT ("promotion_result",).
        The safe chain must terminate directly at the result, not at a child field.
        """
        body = textwrap.dedent(
            """
            def bypass(batch):
                value = batch.promotion_result.error_messages
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_promotion_result_descendant_var.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # P0 fix: Tests for return annotation bypass
    # Previously, a function's return annotation could bless arbitrary local receivers.

    def test_bypass_via_return_annotation_is_rejected(self) -> None:
        """P0 fix: untrusted.actionable_incident_ids in function returning IncidentPromotionResult must be flagged.
        
        A function's return annotation says nothing about the type of a local receiver.
        """
        body = textwrap.dedent(
            """
            def bypass(untrusted) -> "IncidentPromotionResult":
                return untrusted.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_return_annotation.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    # P1 fix: Tests for annotation name without import identity
    # Previously, the annotation string was trusted without verifying it refers to the canonical class.

    def test_bypass_via_local_class_shadowing_is_rejected(self) -> None:
        """P1 fix: Local IncidentPromotionResult class should not bless access.
        
        The verifier should verify that the annotation refers to the canonical
        imported class, not a local shadow.
        """
        body = textwrap.dedent(
            """
            class IncidentPromotionResult:
                pass

            def bypass(value: "IncidentPromotionResult"):
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_local_class_shadowing.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_local_class_shadowing_unquoted_is_rejected(self) -> None:
        """P1 fix: Local IncidentPromotionResult class without import should not bless access.
        
        The annotation is not quoted, but the class is locally defined, not imported
        from the canonical module. The verifier should require import identity verification.
        """
        body = textwrap.dedent(
            """
            class IncidentPromotionResult:
                pass

            def bypass(value: IncidentPromotionResult):
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_local_class_shadowing_unquoted.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_imported_class_shadowing_is_rejected(self) -> None:
        """P1 fix: IncidentPromotionResult imported from fake_module should not bless access.
        
        The class is imported from a non-canonical module. Import identity verification
        should ensure the annotation refers to the actual canonical class from the
        k8s_diag_agent.collect.incident_promotion_dispatch module.
        """
        body = textwrap.dedent(
            """
            from fake_module import IncidentPromotionResult

            def bypass(value: IncidentPromotionResult):
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_imported_class_shadowing.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_local_run_accumulator_shadowing_is_rejected(self) -> None:
        """P1 fix: Local RunPromotionAccumulator class should not bless .canonical_incident_ids() call.
        
        The verifier should verify that annotations refer to the canonical imported class,
        not a local shadow definition.
        """
        body = textwrap.dedent(
            """
            class RunPromotionAccumulator:
                pass

            def bypass(value: RunPromotionAccumulator):
                return value.canonical_incident_ids()
            """
        )
        with _FixtureTree(
            "violation/bypass_via_local_run_accumulator_shadowing.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_canonical_call", proc.stdout)

    # P1 fix: Tests for deprecated canonical_incident_ids() bypass
    # Previously, batch.promotion_result.canonical_incident_ids() was allowed.

    def test_bypass_via_deprecated_canonical_call_is_rejected(self) -> None:
        """P1 fix: batch.promotion_result.canonical_incident_ids() must be flagged.
        
        The deprecated canonical_incident_ids() result API should not remain
        an allowed production handoff path. It should only be callable on
        RunPromotionAccumulator receivers.
        """
        body = textwrap.dedent(
            """
            def bypass(batch):
                return batch.promotion_result.canonical_incident_ids()
            """
        )
        with _FixtureTree(
            "violation/bypass_via_deprecated_canonical.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_canonical_call", proc.stdout)

    # P1 fix: Tests for name-based bypass patterns
    # Previously the verifier had a parameter-name allowlist that allowed
    # any parameter named 'result', 'typed', etc. to access .actionable_incident_ids.

    def test_bypass_via_result_parameter_is_rejected(self) -> None:
        """P1 fix: Any parameter named 'result' accessing .actionable_incident_ids must be flagged."""
        body = textwrap.dedent(
            """
            def bypass(result):
                return result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_result_param.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_typed_parameter_is_rejected(self) -> None:
        """P1 fix: Any parameter named 'typed' accessing .actionable_incident_ids must be flagged."""
        body = textwrap.dedent(
            """
            def bypass(typed):
                return typed.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_typed_param.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_promotion_result_parameter_is_rejected(self) -> None:
        """P1 fix: Parameter named 'promotion_result' accessing .actionable_incident_ids must be flagged."""
        body = textwrap.dedent(
            """
            def bypass(promotion_result):
                return promotion_result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_promotion_result_param.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_bypass_via_fake_accumulator_parameter_is_rejected(self) -> None:
        """P1 fix: Fake accumulator parameter calling .canonical_incident_ids() must be flagged."""
        body = textwrap.dedent(
            """
            def bypass(accumulator):
                return accumulator.canonical_incident_ids()
            """
        )
        with _FixtureTree(
            "violation/bypass_via_fake_accumulator.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_canonical_call", proc.stdout)

    # P0 fix: Tests for annotated assignment blessing bypass
    # An annotation alone does not prove the runtime value originated from the
    # canonical result seam.

    def test_bypass_via_annotated_assignment_is_rejected(self) -> None:
        """P0 fix: value: IncidentPromotionResult = untrusted; value.actionable_incident_ids must be flagged.
        
        The annotation does not prove provenance - untrusted could be any type at runtime.
        A sound verifier must require both:
        1. Annotation resolves to canonical imported symbol; AND
        2. Assigned expression has compatible proven provenance.
        """
        body = textwrap.dedent(
            """
            def bypass(untrusted):
                value: IncidentPromotionResult = untrusted
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/bypass_via_annotated_assignment.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

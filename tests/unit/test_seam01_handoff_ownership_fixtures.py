"""SEAM01 ownership fixtures for the promotion-diagnosis handoff verifier.

Tests prove the verifier correctly handles class ownership for
.actionable_incident_ids and .canonical_incident_ids access patterns.

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01HandoffOwnershipFixtures(_SubprocessMixin, unittest.TestCase):
    """SEAM01: Ownership-based fixtures for the promotion-diagnosis handoff verifier."""

    # P1 fix: Tests for local class shadowing bypass
    # The verifier should verify that classes were imported from canonical modules,
    # not locally defined with the same name.

    def test_local_incident_promotion_result_shadow_is_rejected(self) -> None:
        """P1 fix: Local IncidentPromotionResult class should not bless access via self."""
        body = textwrap.dedent(
            """
            class IncidentPromotionResult:
                def bypass(self):
                    return self.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/local_incident_promotion_result_shadow.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_local_promotion_propagation_result_shadow_is_rejected(self) -> None:
        """P1 fix: Local PromotionPropagationResult class should not bless access via self."""
        body = textwrap.dedent(
            """
            class PromotionPropagationResult:
                def bypass(self):
                    return self.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/local_promotion_propagation_result_shadow.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_local_incident_promotion_result_dispatch_shadow_is_rejected(self) -> None:
        """P1 fix: Local IncidentPromotionResultDispatch class should not bless access via self."""
        body = textwrap.dedent(
            """
            class IncidentPromotionResultDispatch:
                def bypass(self):
                    return self.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/local_incident_promotion_result_dispatch_shadow.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_local_run_promotion_accumulator_shadow_is_rejected(self) -> None:
        """P1 fix: Local RunPromotionAccumulator class should not bless .canonical_incident_ids() call."""
        body = textwrap.dedent(
            """
            class RunPromotionAccumulator:
                def bypass(self):
                    return self.canonical_incident_ids()
            """
        )
        with _FixtureTree(
            "violation/local_run_promotion_accumulator_shadow.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_canonical_call", proc.stdout)

    def test_local_class_shadowing_via_import_is_rejected(self) -> None:
        """P1 fix: IncidentPromotionResult imported from fake_module should not bless access."""
        body = textwrap.dedent(
            """
            from fake_module import IncidentPromotionResult

            def bypass(value: IncidentPromotionResult):
                return value.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/fake_module_import_shadow.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

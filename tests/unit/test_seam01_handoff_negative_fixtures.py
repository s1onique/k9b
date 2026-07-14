"""SEAM01 negative fixtures for the promotion-diagnosis handoff verifier.

Tests prove the verifier catches forbidden access patterns to
PromotionBatch properties and methods.

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01HandoffVerifierNegativeFixtures(_SubprocessMixin, unittest.TestCase):
    """SEAM01: Negative fixtures for the promotion-diagnosis handoff verifier."""

    def test_batch_actionable_incident_ids_property_is_rejected(self) -> None:
        """PromotionBatch with actionable_incident_ids property must be flagged."""
        body = textwrap.dedent(
            """
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class PromotionBatch:
                promotion_result: object

                @property
                def actionable_incident_ids(self):
                    return self.promotion_result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/batch_with_actionable_property.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_property", proc.stdout)

    def test_batch_canonical_incident_ids_method_is_rejected(self) -> None:
        """PromotionBatch with canonical_incident_ids() method must be flagged."""
        body = textwrap.dedent(
            """
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class PromotionBatch:
                promotion_result: object

                def canonical_incident_ids(self):
                    return self.promotion_result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/batch_with_canonical_method.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_method", proc.stdout)

    def test_direct_batch_actionable_access_is_rejected(self) -> None:
        """Direct batch.actionable_incident_ids access must be flagged."""
        body = textwrap.dedent(
            """
            def process_batch(batch):
                ids = batch.actionable_incident_ids
                return ids
            """
        )
        with _FixtureTree(
            "violation/direct_actionable_access.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_laundering_via_annotated_object_promotion_result_is_rejected(self) -> None:
        """P0: Annotated object.promotion_result cannot become INCIDENT_PROMOTION_RESULT.

        The transition from PROMOTION_BATCH to INCIDENT_PROMOTION_RESULT
        only applies when the base provenance is verified PROMOTION_BATCH.
        Any other annotated type (like object) cannot be laundered through
        .promotion_result access.
        """
        body = textwrap.dedent(
            """
            def bypass(value: object):
                result = value.promotion_result
                return result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/laundering_via_annotated_object.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_direct_batch_canonical_call_is_rejected(self) -> None:
        """Direct batch.canonical_incident_ids() call must be flagged."""
        body = textwrap.dedent(
            """
            def process_batch(batch):
                ids = batch.canonical_incident_ids()
                return ids
            """
        )
        with _FixtureTree(
            "violation/direct_canonical_call.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_canonical_call", proc.stdout)

    def test_getattr_bypass_is_rejected(self) -> None:
        """getattr(..., 'actionable_incident_ids') must be flagged."""
        body = textwrap.dedent(
            """
            def check_batch(batch):
                return getattr(batch, "actionable_incident_ids", None)
            """
        )
        with _FixtureTree(
            "violation/getattr_bypass.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("getattr_bypass", proc.stdout)

    def test_hasattr_bypass_is_rejected(self) -> None:
        """hasattr(..., 'canonical_incident_ids') must be flagged."""
        body = textwrap.dedent(
            """
            def check_batch(batch):
                return hasattr(batch, "canonical_incident_ids")
            """
        )
        with _FixtureTree(
            "violation/hasattr_bypass.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("forbidden_dynamic_access", proc.stdout)

class SEAM01HandoffVerifierPositiveFixtures(_SubprocessMixin, unittest.TestCase):
    """SEAM01: Positive fixtures for the promotion-diagnosis handoff verifier.

    These tests prove that legitimate access patterns are NOT flagged.
    R21: Legitimate batch.promotion_result.actionable_incident_ids with typed PromotionBatch.
    """

    def test_legitimate_batch_promotion_result_access_is_allowed(self) -> None:
        """Legitimate batch.promotion_result.actionable_incident_ids with typed PromotionBatch."""
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def process_batch(batch: PromotionBatch):
                return batch.promotion_result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "ok/legitimate_batch_access.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("FAIL", proc.stdout)

    def test_legitimate_batch_promotion_result_via_variable_is_allowed(self) -> None:
        """Legitimate batch.promotion_result via variable assignment with typed PromotionBatch.

        The transition to INCIDENT_PROMOTION_RESULT happens when assigning
        batch.promotion_result to a variable, and that variable can safely
        access actionable_incident_ids.
        """
        body = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def process_batch(batch: PromotionBatch):
                result = batch.promotion_result
                return result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "ok/legitimate_batch_via_variable.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main()

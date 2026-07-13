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
            self.assertIn("direct_access", proc.stdout)

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
            self.assertIn("direct_access", proc.stdout)

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
            self.assertIn("hasattr_bypass", proc.stdout)

    def test_legitimate_promotion_result_access_is_allowed(self) -> None:
        """Legitimate batch.promotion_result.actionable_incident_ids is allowed."""
        body = textwrap.dedent(
            """
            def process_batch(batch):
                ids = batch.promotion_result.actionable_incident_ids
                return ids
            """
        )
        with _FixtureTree(
            "ok/legitimate_access.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()

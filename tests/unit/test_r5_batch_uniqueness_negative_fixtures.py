"""R5 negative fixtures for the AST promotion batch uniqueness verifier.

Tests prove the strengthened verifier catches every violation shape.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R5
"""

from __future__ import annotations

import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _load_verifier,
    _SubprocessMixin,
)

VERIFY_BATCH_UNIQUENESS = _load_verifier("verify_promotion_batch_uniqueness")


class PromotionBatchUniquenessNegativeFixtures(_SubprocessMixin, unittest.TestCase):
    """Each fixture proves a different violation shape is reported."""

    def test_protocol_subclass_is_rejected(self) -> None:
        """A ``class PromotionBatch(Protocol): ...`` must be flagged."""
        body = "from typing import Protocol\nclass PromotionBatch(Protocol):\n    pass\n"
        with _FixtureTree("violation/promotion_batch_protocol.py", body) as src_root:
            exit_code = VERIFY_BATCH_UNIQUENESS.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(
                exit_code,
                1,
                msg=(
                    "verifier must reject Protocol-based PromotionBatch "
                    "definition; current check gates only on dataclass "
                    "decorator"
                ),
            )
            proc = self._run("verify_promotion_batch_uniqueness", src_root)
            self.assertEqual(proc.returncode, 1)

    def test_typed_dict_subclass_is_rejected(self) -> None:
        """A ``class PromotionBatch(TypedDict): ...`` must be flagged."""
        body = "from typing import TypedDict\nclass PromotionBatch(TypedDict):\n    pass\n"
        with _FixtureTree(
            "violation/promotion_batch_typeddict.py", body
        ) as src_root:
            exit_code = VERIFY_BATCH_UNIQUENESS.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(exit_code, 1)
            proc = self._run("verify_promotion_batch_uniqueness", src_root)
            self.assertEqual(proc.returncode, 1)

    def test_plain_class_is_rejected(self) -> None:
        """A bare ``class PromotionBatch: ...`` must be flagged."""
        body = "class PromotionBatch:\n    pass\n"
        with _FixtureTree(
            "violation/promotion_batch_plain.py", body
        ) as src_root:
            exit_code = VERIFY_BATCH_UNIQUENESS.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(
                exit_code,
                1,
                msg="plain PromotionBatch must be flagged (was silently accepted)",
            )
            proc = self._run("verify_promotion_batch_uniqueness", src_root)
            self.assertEqual(proc.returncode, 1)

    def test_clean_src_root_does_not_flag(self) -> None:
        """Imports alone must not produce a definition entry."""
        with _FixtureTree(
            "ok/safe_alias.py",
            "from .incident_promotion_batch import PromotionBatch\n",
        ) as src_root:
            definitions = VERIFY_BATCH_UNIQUENESS.discover_owner(src_root)
            self.assertEqual(
                definitions,
                [],
                msg="a fixture that only imports PromotionBatch must NOT be a definition",
            )

    def test_neighbour_class_name_is_ignored(self) -> None:
        """``PromotionBatchLike`` must NOT be flagged."""
        body = "@dataclass(frozen=True)\nclass PromotionBatchLike:\n    pass\n"
        with _FixtureTree(
            "ok/neighbour.py", body
        ) as src_root:
            definitions = VERIFY_BATCH_UNIQUENESS.discover_owner(src_root)
            self.assertEqual(
                definitions,
                [],
                msg="PromotionBatchLike must not be classified as PromotionBatch",
            )


if __name__ == "__main__":
    unittest.main()

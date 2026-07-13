"""R6 negative fixtures for the AST promotion helper polymorphism verifier.

Tests prove the verifier catches every violation shape for forbidden
calls to the legacy promotion helper module.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R5
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _load_verifier,
    _SubprocessMixin,
)

VERIFY_HELPER_POLYMORPHISM = _load_verifier("verify_promotion_helper_polymorphism")


class HelperPolymorphismNegativeFixtures(_SubprocessMixin, unittest.TestCase):
    """Each fixture proves a different violation shape is reported."""

    def test_module_qualified_call_is_rejected(self) -> None:
        """``incident_store_promotion_helpers.<helper>(...)`` must fail."""
        aliased_module_body = textwrap.dedent(
            """
            from . import incident_store_promotion_helpers as helpers

            def run(it):
                return helpers.promote_candidates_with_records(*it)
            """
        )
        with _FixtureTree(
            "violation/qualified_call.py", aliased_module_body
        ) as src_root:
            exit_code = VERIFY_HELPER_POLYMORPHISM.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(
                exit_code,
                1,
                msg=(
                    "module alias + attribute call must be flagged. "
                    "R6 strengthens the verifier so this case is "
                    "reported even when the call shape alone would "
                    "not match the legacy module-name check."
                ),
            )

        exact_module_body = textwrap.dedent(
            """
            from . import incident_store_promotion_helpers

            def run(it):
                return (
                    incident_store_promotion_helpers
                    .promote_candidates_with_records(*it)
                )
            """
        )
        with _FixtureTree(
            "violation/exact_module_call.py", exact_module_body
        ) as src_root:
            exit_code = VERIFY_HELPER_POLYMORPHISM.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(
                exit_code,
                1,
                msg=(
                    "exact-module-name attribute call must be flagged "
                    "in its own isolated tree."
                ),
            )

    def test_import_as_helper_module_is_rejected(self) -> None:
        """``import incident_store_promotion_helpers as helpers`` must fail."""
        body = textwrap.dedent(
            """
            import incident_store_promotion_helpers as helpers

            def run(it):
                return helpers.promote_candidates_with_records(*it)
            """
        )
        with _FixtureTree(
            "violation/import_as_module.py", body
        ) as src_root:
            exit_code = VERIFY_HELPER_POLYMORPHISM.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(
                exit_code,
                1,
                msg=(
                    "import-as alias for the helper module must be "
                    "reported as a polymorphic-boundary bypass."
                ),
            )

    def test_aliased_import_then_call_is_rejected(self) -> None:
        """An aliased import followed by a call to the alias must fail."""
        body = textwrap.dedent(
            """
            from .incident_store_promotion_helpers import (
                promote_candidates_with_records as _legacy,
            )

            def run(it):
                return _legacy(*it)
            """
        )
        with _FixtureTree(
            "violation/aliased_call.py", body
        ) as src_root:
            exit_code = VERIFY_HELPER_POLYMORPHISM.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(
                exit_code,
                1,
                msg="aliased import + call must be flagged",
            )

    def test_direct_from_import_is_rejected(self) -> None:
        """``from ... import promote_candidates_with_records`` is a smell."""
        body = textwrap.dedent(
            """
            from .incident_store_promotion_helpers import (
                promote_candidates_with_records,
            )
            """
        )
        with _FixtureTree(
            "violation/direct_import.py", body
        ) as src_root:
            exit_code = VERIFY_HELPER_POLYMORPHISM.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(
                exit_code,
                1,
                msg="direct from-import is itself a violation",
            )

    def test_polymorphic_call_remains_allowed(self) -> None:
        """``store.promote_candidates_with_records(...)`` is the seam."""
        body = textwrap.dedent(
            """
            def run(store, it):
                return store.promote_candidates_with_records(*it)
            """
        )
        with _FixtureTree(
            "ok/polymorphic.py", body
        ) as src_root:
            exit_code = VERIFY_HELPER_POLYMORPHISM.main(
                ["--src-root", str(src_root)]
            )
            self.assertEqual(
                exit_code,
                0,
                msg="polymorphic call must remain allowed",
            )


if __name__ == "__main__":
    unittest.main()

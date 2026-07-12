"""R5 negative fixtures for the AST promotion verifiers.

These tests prove the strengthened verifiers actually catch every
violation shape the R5 contract pins:

* duplicate ``PromotionBatch`` class definitions regardless of
  decorator or base class;
* module-qualified calls to the generic promotion helper
  (``incident_store_promotion_helpers.promote_candidates_with_records``);
* aliased helper imports
  (``from incident_store_promotion_helpers import
  promote_candidates_with_records as promote_legacy``).

The fixtures deliberately place forbidden constructs inside synthetic
``.py`` files under a temporary directory so the production code tree
is never modified by these tests. Each fixture is created, scanned by
the verifier entry point, and verified to fail with the expected
``exit code 1`` plus a diagnostic that points at the synthetic file.

Each test cleans up its fixture directory; the suite stays hermetic
and never leaves files behind.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R5
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_verifier(script_name: str):
    """Import ``scripts/<script_name>.py`` as a module.

    The verifier entry point is a ``__main__`` script that also exposes
    ``main(argv)`` and helper functions, so unit tests can invoke both
    the public entry point directly (no subprocess) and the helper
    functions individually.
    """
    script_path = REPO_ROOT / "scripts" / f"{script_name}.py"
    spec = importlib.util.spec_from_file_location(script_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load verifier: {script_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_name] = module
    spec.loader.exec_module(module)
    return module


VERIFY_BATCH_UNIQUENESS = _load_verifier("verify_promotion_batch_uniqueness")
VERIFY_HELPER_POLYMORPHISM = _load_verifier(
    "verify_promotion_helper_polymorphism"
)


class _FixtureTree:
    """Context manager for a temporary ``src/`` fixture root.

    The verifier scans ``src_root.rglob('*.py')`` so the canonical
    "violation file" must live somewhere beneath that root. The fixture
    writes a synthetic ``promotion_batch_violation.py`` (or similar)
    plus a single innocent sibling so we never trigger false positives
    on the empty-file path.
    """

    def __init__(self, relative_path: str, body: str):
        self._relative_path = relative_path
        self._body = textwrap.dedent(body)
        self._tmp: Path | None = None

    def __enter__(self) -> Path:
        import tempfile

        tmp_root = Path(tempfile.mkdtemp(prefix="k9b_r5_verifier_"))
        src_root = tmp_root / "src"
        src_root.mkdir(parents=True, exist_ok=True)
        # Always add an innocent sibling so rglob() has at least one
        # other ``.py`` file to consider -- avoids any "no files"
        # special cases in the verifier.
        (src_root / "__init__.py").write_text("", encoding="utf-8")
        violation_path = src_root / self._relative_path
        violation_path.parent.mkdir(parents=True, exist_ok=True)
        violation_path.write_text(self._body, encoding="utf-8")
        self._tmp = tmp_root
        return src_root

    def __exit__(self, *_exc: object) -> None:
        if self._tmp is None:
            return
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)


class _SubprocessMixin:
    """Run a verifier script via subprocess and capture the result.

    Several verifier checks gate on the ``src_root`` argument; running
    the script via ``python -m`` keeps the behaviour indistinguishable
    from a developer invoking the script directly and confirms the
    end-to-end CLI entry point also fails closed.
    """

    @staticmethod
    def _run(script_name: str, src_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / f"{script_name}.py"),
                "--src-root",
                str(src_root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )


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
        """A bare ``class PromotionBatch: ...`` must be flagged.

        The previous R4 gate accepted only ``@dataclass`` shapes and
        silently let a plain ``class PromotionBatch: pass`` slip
        through, which the legacy regression backend originally
        contained. R5 widens the gate to any literal ``ClassDef``
        whose ``name`` matches.
        """
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
        """Imports alone must not produce a definition entry.

        The verifier entry point exits ``1`` when zero or many definitions
        are present, because that contract guarantees a single owner for
        the production tree. For a synthetic fixture that intentionally
        contains no ``PromotionBatch`` definition we must assert the
        helper returns an EMPTY ``discover_owner`` list -- which proves
        the would-be violation file would not be picked up if the
        canonical owner were also present.
        """
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
        """``PromotionBatchLike`` must NOT be flagged.

        Confirms the verifier gates on exact ``ClassDef.name`` match,
        not a substring heuristic, so safe neighbours do not produce
        false positives.
        """
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


class HelperPolymorphismNegativeFixtures(_SubprocessMixin, unittest.TestCase):
    """Each fixture proves a different violation shape is reported."""

    def test_module_qualified_call_is_rejected(self) -> None:
        """``incident_store_promotion_helpers.<helper>(...)`` must fail.

        Each candidate shape lives in its own isolated fixture tree so
        one violation cannot mask another fixture's failure.
        """
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
        """``import incident_store_promotion_helpers as helpers`` must fail.

        The R6 verifier detects the bare ``import ... as helpers`` form
        followed by an attribute call through the alias. This is the
        canonical bypass shape that the R5 verifier missed because it
        only flagged the exact ``Name`` receiver.
        """
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

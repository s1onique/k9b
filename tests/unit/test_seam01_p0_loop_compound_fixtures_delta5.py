"""Delta-5 fixtures: for/with target binding regression tests.

These tests verify that for-target and with-as-target bindings are
applied BEFORE body exception capture, so the precise exception-env
model sees the untrusted iterator value or context-manager return.
"""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class _SubprocessMixin:
    """Run a verifier script via subprocess and capture the result."""

    @staticmethod
    def _run(script_name, src_root) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / f"{script_name}.py"),
             "--src-root", str(src_root)],
            capture_output=True, text=True, check=False,
        )

    def _run_test(self, body: str, should_reject: bool) -> subprocess.CompletedProcess:
        relative_path = "violations/typed_violation.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            src_root = tmp_root / "src"
            src_root.mkdir(parents=True, exist_ok=True)
            (src_root / "__init__.py").write_text("", encoding="utf-8")
            violation_path = src_root / relative_path
            violation_path.parent.mkdir(parents=True, exist_ok=True)
            violation_path.write_text(textwrap.dedent(body), encoding="utf-8")
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            if should_reject:
                assert proc.returncode == 1, f"Expected rejection but got: {proc.stdout}\n{proc.stderr}"
                assert "forbidden_actionable_access" in proc.stdout
            else:
                assert proc.returncode == 0, f"Expected acceptance but got: {proc.stdout}\n{proc.stderr}"
                assert "PASS" in proc.stdout
            return proc


class SEAM01P0LoopCompoundFixturesDelta5(_SubprocessMixin, unittest.TestCase):
    def test_loop_backedge_for_target_overwrites_protected(self) -> None:
        """REVIEWER-MANDATED FOR-TARGET FIXTURE (gating, delta-5):

        The for-loop's iteration target rebinds the protected value
        BEFORE each iteration's body executes.  The first-iteration
        exception must therefore be captured with the target marked
        UNKNOWN (because the iterator yields a value we have no
        static provenance for).  The for-else only runs on normal
        exhaustion, so it does not save us when the exception
        escapes mid-iteration.

        Expected: REJECT.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, items):
                value = batch.promotion_result

                try:
                    for value in items:
                        risky()
                    else:
                        value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)


    def test_loop_backedge_for_target_outer_handler_sanitizes(self) -> None:
        """REVIEWER-MANDATED FOR-TARGET POLARITY (gating, delta-5):

        Same for-target rebind, but the outer handler
        unconditionally sanitises value.  Verifier accepts.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, items):
                value = batch.promotion_result

                try:
                    for value in items:
                        risky()
                    else:
                        value = batch.promotion_result
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=False)


    def test_loop_backedge_with_as_target_becomes_unsafe(self) -> None:
        """REVIEWER-MANDATED WITH-AS-TARGET FIXTURE (gating, delta-5):

        ``with manager as value`` rebinds `value` to the result of
        ``manager.__enter__()``.  If that result is untrusted and
        ``risky()`` raises before the later safe assignment, the
        protected access observes the untrusted binding.

        Expected: REJECT.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, manager):
                value = batch.promotion_result

                try:
                    with manager as value:
                        risky()
                        value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)


    def test_loop_backedge_with_as_target_finally_sanitizes(self) -> None:
        """REVIEWER-MANDATED WITH-AS-TARGET POLARITY (gating, delta-5):

        Same with-as rebind, but the finally suite sanitises value.
        Verifier accepts.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, manager):
                value = batch.promotion_result

                try:
                    with manager as value:
                        risky()
                except Exception:
                    pass
                finally:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=False)


    def test_loop_backedge_destructured_target_contains_protected(self) -> None:
        """REVIEWER-MANDATED DESTRUCTURING FIXTURE (gating, delta-5):

        ``for (item, value) in items`` rebinds `value` to one element
        of each tuple.  The unpacked binding must be tracked.

        Expected: REJECT.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, items):
                value = batch.promotion_result

                try:
                    for item, value in items:
                        risky()
                    else:
                        value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)



    def test_loop_backedge_with_as_target_inside_try(self) -> None:
        """REVIEWER-MANDATED DELTA-6 FIXTURE (gating):

        \`with manager as value:\` rebinds the protected value inside a
        try nested in an outer loop.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, outer_items, manager):
                value = batch.promotion_result

                for _ in outer_items:
                    try:
                        with manager as value:
                            risky()
                        value = batch.promotion_result
                    except Exception:
                        pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_loop_backedge_with_second_context_raises_after_first_binding(self) -> None:
        """REVIEWER-MANDATED DELTA-6 FIXTURE (gating):

        Multi-item \`with first_manager as value, risky_manager():\`
        rebinds value when first_manager.__enter__() succeeds, then
        the second context expression raises.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, first_manager, risky_manager):
                value = batch.promotion_result

                try:
                    with first_manager as value, risky_manager():
                        value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)


if __name__ == "__main__":
    unittest.main()

"""Loop compound exception point fixtures (regression tests for R1 of the closure delta).

These tests verify that ``process_try_body`` and friends route through the
canonical precise-exception analyzer (``capture_exception_envs_no_target``)
instead of using the legacy pre-statement ``_stmt_may_raise`` snapshot.

The mandated fixtures cover two architectural requirements:

1. The compound-if case (reviewer-issued): the loop wrapper records
   the exception environment at the pre-IF snapshot OR the canonical
   per-operation snapshot.  The handler does nothing; the snapshot at
   the exception point must reflect branch-local ``value = untrusted``
   even though the loop body continues with ``value = safe`` on the
   normal branch.

2. The loop-backedge case (reviewer-issued): first-iteration state
   must propagate to second-iteration exception events.  Without the
   bounded fixed-point in ``_capture_loop_exception_envs_no_target``,
   the iter-2 ``risky() raises`` snapshot would inherit the iter-0
   safe provenance and the for-else exhaustion path would mask the
   unsafe value.

Suggested by: ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01 closure delta.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Add repo root to path for imports
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class _SubprocessMixin:
    """Run a verifier script via subprocess and capture the result."""

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


class SEAM01P0LoopCompoundFixtures(_SubprocessMixin, unittest.TestCase):
    """Loop-wrapped try-compound fixtures (precise-exception-flow regression).

    These tests prove that the canonical precise-exception analyzer is the
    sole authority for handler-entry environments, even inside loop
    wrappers.  The handler does nothing; the snapshot at the exception
    point must reflect branch-local ``value = untrusted`` even though
    the loop body's normal branch continues with ``value = safe``.
    """

    def _run_test(
        self, body: str, should_reject: bool
    ) -> subprocess.CompletedProcess:
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
                self.assertEqual(
                    proc.returncode, 1,
                    f"Expected rejection but got: {proc.stdout}\n{proc.stderr}"
                )
                self.assertIn("forbidden_actionable_access", proc.stdout)
            else:
                self.assertEqual(
                    proc.returncode, 0,
                    f"Expected acceptance but got: {proc.stdout}\n{proc.stderr}"
                )
                self.assertIn("PASS", proc.stdout)

            return proc

    def test_loop_with_compound_branch_exception_point(self) -> None:
        """MANDATED LOOP FIXTURE (reviewer-issued):

        A try wrapped in a for loop with compound-statement exception
        point.  The handler does nothing, but the snapshot at the
        exception point must reflect branch-local ``value = untrusted``
        even though the loop body continues with ``value = safe`` on the
        normal branch.  The verifier must reject this case (rc=1,
        ``forbidden_actionable_access`` in stdout).

        Sequence:
            flag = True
            value = untrusted              # branch-local mutation
            risky() raises                 # → handler with no-op body
            (value = batch.promotion_result skipped)
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items, flag):
                value = batch.promotion_result

                for item in items:
                    try:
                        if flag:
                            value = untrusted
                            risky()
                            value = batch.promotion_result
                    except Exception:
                        pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)








    def test_loop_backedge_handler_sanitizes_value(self) -> None:
        """MANDATED LOOP-BACKEDGE FIXTURE (reviewer-issued, gating).

        First-iteration write of ``value = untrusted`` after a successful
        call must be visible to a second-iteration exception event at
        the same call site.  The handler is a no-op; the loop's
        ``else`` only sanitizes on normal exhaustion.

        Without the bounded fixed-point in loop exception-env capture,
        the iter-2 ``risky() raises`` snapshot inherits the iter-0
        safe provenance and the for-else (exhaustion path) keeps
        value=safe, so the conservative merge incorrectly reports a
        safe-only join.

        The fast-containment rule in
        ``analyze_try_to_target`` (ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01
        delta 2) demotes exception-env provenances to UNKNOWN when
        the loop body both contains a potentially-raising operation
        AND mutates a relevant var.  Rejected (rc=1).
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                try:
                    for item in items:
                        risky()
                        value = untrusted
                    else:
                        value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_loop_backedge_handler_sanitizes_value_polarity(self) -> None:
        """MANDATED LOOP-BACKEDGE POSITIVE POLARITY (reviewer-issued).

        Same loop-backedge shape as the negative twin, but the
        exception handler sanitises ``value`` so every reachable
        path converges on a safe value.  The verifier accepts.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untrusted, items):
                value = batch.promotion_result

                try:
                    for item in items:
                        risky()
                        value = untrusted
                    else:
                        value = batch.promotion_result
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=False)






    def test_loop_backedge_first_handler_sanitizes_second_noop(self) -> None:
        """REVIEWER-MANDATED HANDLER POLARITY (gating):

        First matching handler sanitises value; second matching
        handler is a no-op.  Python executes only the first matching
        handler per exception event.

        Expected: REJECT.  The TypeError handler leaves value as
        UNKNOWN; the conservative merge correctly reports UNSAFE.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untracked, items):
                value = batch.promotion_result

                try:
                    for item in items:
                        risky()
                        value = untracked
                    else:
                        value = batch.promotion_result
                except ValueError:
                    value = batch.promotion_result
                except TypeError:
                    pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_loop_backedge_handler_conditional_sanitization(self) -> None:
        """REVIEWER-MANDATED HANDLER POLARITY (gating):

        Handler contains a conditional sanitisation.  The branch that
        does not execute preserves the demoted (UNKNOWN) value, so
        the conservative merge correctly reports UNSAFE.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untracked, items):
                value = batch.promotion_result

                try:
                    for item in items:
                        risky()
                        value = untracked
                    else:
                        value = batch.promotion_result
                except Exception:
                    if value.__class__.__name__ == 'int':
                        value = batch.promotion_result

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_loop_backedge_all_handler_paths_unconditional_sanitize(self) -> None:
        """REVIEWER-MANDATED HANDLER POLARITY (gating, polarity):

        Single handler that unconditionally sanitises value.  After
        the demote-before-handlers containment rule, the handler
        runs against UNKNOWN and writes safe; merge gives safe.

        Expected: ACCEPT.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untracked, items):
                value = batch.promotion_result

                try:
                    for item in items:
                        risky()
                        value = untracked
                    else:
                        value = batch.promotion_result
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=False)



    def test_loop_backedge_nested_try_assignment(self) -> None:
        """REVIEWER-MANDATED NESTED-TRY FIXTURE (gating, delta-4):

        Loop body contains a nested try that mutates a var.  The
        fast-containment writer must descend into the nested try
        (body / handlers / else / finalbody) to discover the
        mutation, otherwise the second-iter exception is captured
        from the iter-0 safe environment and the verifier
        incorrectly approves the post-try access.

        Iteration 1: risky() succeeds, value = untracked.
        Iteration 2: risky() raises BEFORE the nested assignment.
        The outer handler is a no-op; the for-else (which would
        sanitise) only runs on normal exhaustion, but the
        exception escapes before exhaustion.

        Expected: REJECT.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untracked, items):
                value = batch.promotion_result

                try:
                    for item in items:
                        risky()
                        try:
                            value = untracked
                        finally:
                            pass
                    else:
                        value = batch.promotion_result
                except Exception:
                    pass

                return value.actionable_incident_ids
        """
        proc = self._run_test(body, should_reject=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("forbidden_actionable_access", proc.stdout)

    def test_loop_backedge_nested_try_outer_handler_sanitizes(self) -> None:
        """REVIEWER-MANDATED NESTED-TRY POSITIVE POLARITY (gating, delta-4):

        Same nested-try mutation shape, but the outer handler
        unconditionally sanitises value.  Verifier accepts.
        """
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untracked, items):
                value = batch.promotion_result

                try:
                    for item in items:
                        risky()
                        try:
                            value = untracked
                        finally:
                            pass
                    else:
                        value = batch.promotion_result
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run_test(body, should_reject=False)

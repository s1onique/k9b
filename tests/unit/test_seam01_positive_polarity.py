"""Positive polarity twin tests for SEAM01 precise exception flow.

These tests verify that the precise-exception analyzer does NOT
over-reject: when the handler or finalbody sanitizes the unsafe value,
or when no unsafe value can reach the post-try access, the analyzer
must accept the program.

Suggested by: ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class _SubprocessMixin:
    """Run the verifier in a subprocess and assert the verdict."""

    @staticmethod
    def _run(body: str, should_reject: bool) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            src_root = tmp_root / "src"
            src_root.mkdir(parents=True, exist_ok=True)
            (src_root / "__init__.py").write_text("", encoding="utf-8")
            violation_dir = src_root / "violations"
            violation_dir.mkdir(parents=True, exist_ok=True)
            violation_path = violation_dir / "typed_violation.py"
            violation_path.write_text(textwrap.dedent(body), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "verify_promotion_diagnosis_handoff.py"),
                    "--src-root",
                    str(src_root),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        if should_reject:
            assert proc.returncode == 1, (
                f"Expected rejection but got rc={proc.returncode}\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr}"
            )
            assert "forbidden_actionable_access" in proc.stdout
        else:
            assert proc.returncode == 0, (
                f"Expected acceptance but got rc={proc.returncode}\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr}"
            )
            assert "PASS" in proc.stdout
        return proc


class SEAM01PositivePolarity1BodyNormalPathWithUnsafe(
    _SubprocessMixin, unittest.TestCase
):
    """Positive 1: the ACT's stated "handler sanitizes" pattern is rejected.

    The body assigns ``value = untracked`` before ``risky()``.  If
    ``risky()`` succeeds the body completes normally and ``value`` is
    unsafe.  The handler only runs on exception, so it cannot sanitize
    the body-normal path.  The verifier must reject this case -- a
    conservative join over body-normal + handler-completion paths is
    UNKNOWN.  This is consistent with
    ``test_bypass_via_try_except_conservative_join_is_rejected`` in
    :mod:`test_seam01_handoff_flow_fixtures`.
    """

    def test_body_normal_path_unsafe_overrides_handler_sanitize(self) -> None:
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def bypass(batch: PromotionBatch, untracked):
                value = batch.promotion_result

                try:
                    value = untracked
                    risky()
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run(body, should_reject=True)


class SEAM01PositivePolarity2FinallySanitizes(
    _SubprocessMixin, unittest.TestCase
):
    """Positive 2: finally that sets the value back to safe must accept."""

    def test_finally_sanitizes_after_branch_exception(self) -> None:
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untrusted, flag):
                value = batch.promotion_result

                try:
                    if flag:
                        value = untrusted
                        risky()
                except Exception:
                    pass
                finally:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run(body, should_reject=False)


class SEAM01PositivePolarity3ExceptionBeforeUnsafeAssignment(
    _SubprocessMixin, unittest.TestCase
):
    """Positive 3: exception before the unsafe assignment is safe."""

    def test_exception_before_unsafe_assignment(self) -> None:
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untrusted):
                value = batch.promotion_result

                try:
                    risky()
                    value = untrusted
                except Exception:
                    value = batch.promotion_result
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run(body, should_reject=False)


class SEAM01PositivePolarity4MultipleCallsAllSanitized(
    _SubprocessMixin, unittest.TestCase
):
    """Positive 4: multiple calls with all outgoing states sanitized."""

    def test_multiple_calls_sanitized(self) -> None:
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untrusted):
                value = batch.promotion_result

                try:
                    first_call()
                    value = untrusted
                    second_call()
                except Exception:
                    value = batch.promotion_result
                else:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run(body, should_reject=False)


class SEAM01PositivePolarity5BothBranchesSanitize(
    _SubprocessMixin, unittest.TestCase
):
    """Positive 5 (mandated twin): both branches sanitize value.

    The ACT's mandated positive case is::

        try:
            value = untrusted
            risky()
            value = batch.promotion_result
        except Exception:
            value = batch.promotion_result

    Both outgoing paths sanitize ``value``:
      - call raises → handler sanitizes via the exception assignment;
      - call succeeds → the post-call assignment sanitizes.

    The verifier must accept (rc=0, ``PASS`` in stdout).
    """

    def test_body_normal_and_handler_both_sanitize(self) -> None:
        body = """
            from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch

            def safe_function(batch: PromotionBatch, untrusted):
                value = batch.promotion_result

                try:
                    value = untrusted
                    risky()
                    value = batch.promotion_result
                except Exception:
                    value = batch.promotion_result

                return value.actionable_incident_ids
        """
        self._run(body, should_reject=False)



if __name__ == "__main__":
    unittest.main()
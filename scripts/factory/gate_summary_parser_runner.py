"""Canonical parser runner for the gate-summary producer.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION11-
RANGE-BOUND-EVIDENCE-TRUTH-AND-LLM-CAP01:

Extracted from :mod:`scripts.factory.populate_gate_summary` so the
producer stays under the LLM-friendly 500-line cap.  This module owns
the **parser invocation result extraction** responsibility:

* :func:`parse_parser_verdict` -- extract the ``decode_status`` and
  ``acceptance_status`` typed verdict from the canonical parser's
  stdout;
* :func:`run_parser_and_capture_verdict` -- run the parser subprocess
  **exactly once** and return the outcome plus the typed verdict.

The parser is now invoked a single time.  Both the
:class:`CheckOutcome` and the typed ``(decode_status, acceptance_status)``
verdict are derived from the SAME captured bytes so the producer
cannot double-count or drift from the parser's contract.

A module-level counter (:data:`PARSER_INVOCATION_COUNT`) is exposed
so the test surface can assert the parser was invoked exactly once
per producer call.
"""

from __future__ import annotations

import shlex
import subprocess
import time

from scripts.factory.gate_summary_command_env import (
    SCRIPT_REPO,
    CheckOutcome,
    CommandSpec,
)

# ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION11:
# Single parser-invocation invariant.  A mutable list is used so the
# counter survives ``from ... import`` rebinding in the test surface.
# The test surface MUST use :func:`parser_invocation_count` and
# :func:`reset_parser_invocation_count` so it reads the live counter.
_PARSER_INVOCATION_BOX: list[int] = [0]


def parser_invocation_count() -> int:
    """Return the live parser invocation count."""
    return _PARSER_INVOCATION_BOX[0]


def reset_parser_invocation_count() -> None:
    """Reset the parser invocation counter for test isolation."""
    _PARSER_INVOCATION_BOX[0] = 0


def parse_parser_verdict(stdout_text: str) -> tuple[str, str]:
    """Extract the ``decode_status`` and ``acceptance_status`` from the
    canonical parser's stdout.

    The parser emits one ``key=value`` line per verdict field.  This
    helper is the single source of truth for the verdict extraction so
    the producer cannot silently drift from the parser's contract.
    Unknown fields are ignored.  Missing fields default to ``"fail"``
    because the parser never emits a partial verdict.
    """
    decode_status = "fail"
    acceptance_status = "fail"
    for line in stdout_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("decode_status="):
            decode_status = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("acceptance_status="):
            acceptance_status = stripped.split("=", 1)[1].strip()
    return decode_status, acceptance_status


def _derive_check_outcome(
    spec: CommandSpec,
    exit_code: int,
    elapsed_ms: int,
    error_output: str,
) -> CheckOutcome:
    """Derive a :class:`CheckOutcome` from a single parser execution.

    Centralises the verdict mapping so the single parser invocation
    in :func:`run_parser_and_capture_verdict` cannot drift between the
    recorded outcome and the verdict.
    """
    ok = (exit_code == 0) == spec.expect_zero
    return CheckOutcome(
        name=spec.name,
        status="pass" if ok else "fail",
        duration_ms=elapsed_ms,
        error_message=None if ok else error_output[:1000],
        command=shlex.join(spec.argv),
        exit_code=exit_code,
    )


def run_parser_and_capture_verdict(
    parser_spec: CommandSpec,
) -> tuple[CheckOutcome, str, str]:
    """Run the canonical parser subprocess **once** and capture the verdict.

    Returns ``(outcome, decode_status, acceptance_status)``.  The
    parser is invoked exactly once; both the recorded
    :class:`CheckOutcome` and the typed ``(decode_status,
    acceptance_status)`` verdict are derived from the SAME captured
    bytes so the parser cannot run twice and cannot drift from the
    canonical contract.

    Any :class:`OSError` or :class:`subprocess.TimeoutExpired` is
    caught and recorded as ``exit_code=127`` (or ``124`` for a
    timeout) with ``decode_status=fail`` so the producer never
    crashes on a transient parser failure.
    """
    _PARSER_INVOCATION_BOX[0] += 1

    decode_status = "fail"
    acceptance_status = "fail"
    started = time.time()
    try:
        proc = subprocess.run(
            parser_spec.argv,
            capture_output=True,
            text=True,
            cwd=str(parser_spec.cwd or SCRIPT_REPO),
            env=parser_spec.env,
            timeout=120,
            check=False,
        )
        exit_code = proc.returncode
        elapsed_ms = int((time.time() - started) * 1000)
        error_output = (proc.stderr or "") + (proc.stdout or "")
        decode_status, acceptance_status = parse_parser_verdict(
            proc.stdout or ""
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        exit_code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 127
        elapsed_ms = int((time.time() - started) * 1000)
        error_output = str(exc)
    outcome = _derive_check_outcome(
        parser_spec, exit_code, elapsed_ms, error_output
    )
    return outcome, decode_status, acceptance_status


__all__ = [
    "parser_invocation_count",
    "parse_parser_verdict",
    "reset_parser_invocation_count",
    "run_parser_and_capture_verdict",
]

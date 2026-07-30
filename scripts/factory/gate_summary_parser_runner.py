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
  and return the outcome plus the typed verdict.

The producer imports these helpers instead of inlining the parser
subprocess machinery; the responsibility is single-owner and the
verdict-extraction contract has exactly one canonical implementation.
"""

from __future__ import annotations

import subprocess  # noqa: F401  (used by run_parser_and_capture_verdict)

from scripts.factory.gate_summary_command_env import (
    SCRIPT_REPO,
    CheckOutcome,
    CommandSpec,
    run_subprocess,
)


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


def run_parser_and_capture_verdict(
    parser_spec: CommandSpec,
) -> tuple[CheckOutcome, str, str]:
    """Run the canonical parser subprocess and capture the verdict.

    Returns ``(outcome, decode_status, acceptance_status)``.  The
    parser is invoked with the same argv and environment as the
    recorded :class:`CommandSpec`.  Any :class:`OSError` or
    :class:`subprocess.TimeoutExpired` is caught and recorded as
    ``decode_status=fail`` so the producer never crashes on a
    transient parser failure.
    """
    outcome = run_subprocess(parser_spec)
    decode_status = "fail"
    acceptance_status = "fail"
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
        decode_status, acceptance_status = parse_parser_verdict(
            proc.stdout or ""
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    return outcome, decode_status, acceptance_status


__all__ = [
    "parse_parser_verdict",
    "run_parser_and_capture_verdict",
]

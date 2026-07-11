#!/usr/bin/env python3
"""
ACT-Local Verification Mode.

Bounded verification for local agent ACT work:
- Checks changed files precisely
- Preserves cheap global safety gates
- Reports broader repo failures separately
- Never runs broad pytest or full local verification unless explicitly requested
- Gives actionable per-step commands and failure attribution

Usage:
    python scripts/act_local_verification.py [--json]

This module is the thin CLI orchestrator that imports from act_local_* modules.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from act_local_changed_files import filter_python_files, get_changed_files
from act_local_checks import (
    run_doctrine_check,
    run_gate_summary_parser_check,
    run_json_contract_check,
    run_llm_friendly_on_files,
    run_mypy_on_files,
    run_no_new_llm_allowlist_check,
    run_ruff_on_files,
    run_shell_containment_on_files,
    run_verification_discipline_check,
    run_workflow_check,
)
from act_local_contract import ActLocalResult, CheckResult
from act_local_frontend_checks import run_frontend_one_pass_diagnosis_check

# Import directly from submodules to avoid unused-import warnings
from act_local_golden_case_checks import (
    run_golden_case_check,
    run_golden_case_privacy_check,
    run_provenance_golden_case_check,
)
from act_local_incident_api_checks import (
    run_incident_api_one_pass_diagnosis_check,
    run_incident_api_route_one_pass_diagnosis_check,
)
from act_local_output import format_human_output, format_json_output
from act_local_provider_checks import run_provider_artifact_verifier_check
from act_local_runtime_checks import run_runtime_structured_logs_check
from act_local_small_provider_checks import (
    run_small_provider_artifact_verifier_check,
    run_small_provider_smoke_check,
)

# All entries in ``DEFAULT_CHECK_REGISTRY`` MUST accept the uniform
# signature ``(python_files: list[str], changed_files: list[str]) ->
# CheckResult``. This eliminates the brittle ``except TypeError``
# dispatch (which used to mask real ``TypeError`` failures and could
# invoke a check twice). Legacy no-argument checks are wrapped via
# :func:`noarg` before being inserted into the registry.
CheckCallable = Callable[[list[str], list[str]], "CheckResult"]


def noarg(check: Callable[[], CheckResult]) -> CheckCallable:
    """Adapt a zero-argument check into the uniform ``CheckCallable`` shape.

    This wrapper exists so ACT-local can iterate the registry without
    exception-driven dispatch: every entry exposes the same signature,
    so ``run_act_local_verification`` can call each one exactly once
    and surface any ``TypeError`` raised inside the check as a real
    failure instead of silently re-invoking the callable.
    """

    def run(
        _python_files: list[str],
        _changed_files: list[str],
    ) -> CheckResult:
        return check()

    return run


def _build_default_check_registry() -> list[CheckCallable]:
    return [
        # Language-specific static checks (changed files only).
        lambda py_files, _changed: run_ruff_on_files(py_files),
        lambda py_files, _changed: run_mypy_on_files(py_files),
        # Repository-wide bounded checks (always run; cheap & deterministic).
        noarg(run_no_new_llm_allowlist_check),
        # LLM-friendly and shell-containment checks on changed files.
        lambda _py_files, changed: run_llm_friendly_on_files(changed),
        lambda _py_files, changed: run_shell_containment_on_files(changed),
        noarg(run_doctrine_check),
        noarg(run_verification_discipline_check),
        noarg(run_json_contract_check),
        noarg(run_workflow_check),
        # Golden-case and provenance checks (use checked-in fixtures).
        noarg(run_golden_case_check),
        noarg(run_provenance_golden_case_check),
        noarg(run_golden_case_privacy_check),
        # Incident API one-pass diagnosis wiring verification.
        noarg(run_incident_api_one_pass_diagnosis_check),
        noarg(run_incident_api_route_one_pass_diagnosis_check),
        # Frontend one-pass diagnosis UI check (vitest).
        noarg(run_frontend_one_pass_diagnosis_check),
        # Provider artifact verifier and structured-logs checks.
        noarg(run_provider_artifact_verifier_check),
        noarg(run_runtime_structured_logs_check),
        # Small-provider smoke and artifact verifier checks.
        noarg(run_small_provider_smoke_check),
        noarg(run_small_provider_artifact_verifier_check),
    ]


DEFAULT_CHECK_REGISTRY: list[CheckCallable] = _build_default_check_registry()

# =============================================================================
# ACT-Local Verification
# =============================================================================

def run_act_local_verification(
    json_mode: bool = False,
    skip_gate_summary: bool = False,
    *,
    check_registry: list[Callable[..., CheckResult]] | None = None,
    changed_files: list[str] | None = None,
    python_files: list[str] | None = None,
    include_gate_summary_parser: bool | None = None,
    gate_summary_artifact_path: Path | None = None,
) -> ActLocalResult:
    """
    Run ACT-local verification.

    This runs bounded checks on changed files only:
    - ruff on changed Python files
    - mypy on changed Python files
    - LLM-friendly checks on changed files
    - shell containment on changed shell files
    - doctrine checks
    - verification discipline guard
    - gate-summary-parser (skipped when ``skip_gate_summary`` is True;
      this is set by ``verify_all.py --skip-gate-summary`` to break the
      populate -> verify -> populate circular dependency)

    Forbidden by default:
    - pytest (broad)
    - full fast profile
    - expensive frontend suite

    Args:
        json_mode: Emit JSON output (only honored by the CLI wrapper).
        skip_gate_summary: When True, the gate-summary-parser check is
            omitted and recorded as a ``skipped_check`` instead. This is
            used by ``populate_gate_summary.py`` to break the populate ->
            verify -> populate circular dependency.
        check_registry: Override the registry of checks to run. Each
            entry must be a callable accepting ``(python_files,
            changed_files)`` and returning a ``CheckResult``. When
            ``None``, ``DEFAULT_CHECK_REGISTRY`` is used.
        changed_files: Pre-computed changed-files list. When ``None``,
            ``get_changed_files()`` is invoked. Tests that need a
            hermetic runtime pass an explicit list to avoid ``git``
            subprocess side effects.
        python_files: Pre-computed Python-files list. When ``None``,
            ``filter_python_files(changed_files)`` is computed lazily.
        include_gate_summary_parser: When set, overrides the
            ``skip_gate_summary`` flag for the purpose of deciding
            whether to append the gate-summary-parser check. This lets
            callers drive a controlled registry (e.g. a unit test) that
            only includes the parser check.
        gate_summary_artifact_path: Override path to the gate-summary
            artifact. When ``None``, the production
            ``.factory/gate-summary.json`` is used. Tests pass a
            ``tmp_path`` so they never rename or delete the real tracked
            artifact.
    """
    checks: list[CheckResult] = []
    failure_commands: list[str] = []

    if changed_files is None:
        changed_files = get_changed_files()

    if python_files is None:
        python_files = filter_python_files(changed_files)

    registry = (
        DEFAULT_CHECK_REGISTRY
        if check_registry is None
        else list(check_registry)
    )

    for check_callable in registry:
        # Invoke every check through the uniform ``CheckCallable``
        # interface. No ``except TypeError`` fallback: a real
        # ``TypeError`` raised inside a check is a bug, not a signal to
        # re-invoke the callable with a different signature.
        result = check_callable(python_files, changed_files)
        checks.append(result)
        if result.status == "FAIL":
            failure_commands.append(result.command)

    # Run the gate-summary-parser check unless explicitly skipped or
    # the caller is driving a custom registry and chose to omit it.
    if include_gate_summary_parser is None:
        should_run_gate_summary = not skip_gate_summary
    else:
        should_run_gate_summary = include_gate_summary_parser

    if should_run_gate_summary:
        gate_summary_result = run_gate_summary_parser_check(
            artifact_path=gate_summary_artifact_path,
        )
        checks.append(gate_summary_result)
        if gate_summary_result.status == "FAIL":
            failure_commands.append(gate_summary_result.command)

    # Determine overall success (all non-skipped checks must pass)
    non_skipped = [c for c in checks if c.status != "SKIP"]
    success = all(c.status == "PASS" for c in non_skipped) if non_skipped else True

    # Build skipped checks list
    skipped_checks: list[dict[str, str]] = [
        {"id": "pytest-broad", "reason": "Broad pytest suite - use targeted pytest for changed tests"},
        {"id": "full-fast-gate", "reason": "Full fast profile - not evaluated by ACT-local"},
        {"id": "frontend-suite", "reason": "Frontend suite - not evaluated by ACT-local"},
        {"id": "expensive-docs", "reason": "Expensive docs checks - not evaluated by ACT-local"},
    ]
    if not should_run_gate_summary:
        skipped_checks.append(
            {
                "id": "gate-summary-parser",
                "reason": (
                    "Skipped via --skip-gate-summary to break populate -> verify -> populate "
                    "circular dependency."
                ),
            }
        )

    return ActLocalResult(
        success=success,
        changed_files=changed_files,
        checks=checks,
        skipped_checks=skipped_checks,
        broader_gate_status="not_evaluated",
        failure_commands=failure_commands,
    )


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    """Main entry point."""
    # Handle --help
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
ACT-Local Verification Mode

Bounded verification for local agent ACT work.

Usage:
    python scripts/act_local_verification.py [--json]

Options:
    --json    Emit JSON output to stdout

ACT-local runs bounded checks on changed files only:
- ruff on changed Python files
- mypy on changed Python files
- LLM-friendly checks
- shell containment
- doctrine checks
- verification discipline guard

It SKIPS:
- broad pytest
- full fast profile
- expensive frontend suite
""")
        return 0
    
    json_mode = "--json" in sys.argv
    skip_gate_summary = "--skip-gate-summary" in sys.argv

    try:
        result = run_act_local_verification(
            json_mode=json_mode,
            skip_gate_summary=skip_gate_summary,
        )
        
        if json_mode:
            print(format_json_output(result))
        else:
            print(format_human_output(result))
        
        return 0 if result.success else 1
        
    except Exception as e:
        if json_mode:
            import json
            print(json.dumps({
                "profile": "act-local",
                "success": False,
                "error": str(e),
            }))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

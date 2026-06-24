"""Enforcement rules for golden-case fake-handler execution.

This module provides fail-closed enforcement rules that verify:
- Fake handlers are properly executed
- Handler invocations are recorded
- All invocations have proper flags
- Unknown check IDs fail closed
"""

from __future__ import annotations

from typing import Any


class FakeHandlerExecutionError(Exception):
    """Raised when fake handlers are not properly executed."""

    pass


def enforce_fake_handlers(
    *,
    loop_result: dict[str, Any],
    runner_result_dict: dict[str, Any],
    read_only_checks_sidecar: dict[str, Any],
    fake_handlers: dict[str, Any],
    enforce: bool = True,
    allow_zero_checks: bool = False,
) -> None:
    """Enforce fake-handler execution rules.

    This function enforces fail-closed rules for golden-case fake-handler execution:

    1. checks_run must be > 0 (unless allow_zero_checks=True)
    2. If checks_run > 0, must have recorded invocations
    3. All invocations must have golden_case_handler=true
    4. All invocations must have no_kubernetes_call=true
    5. Unknown check IDs must fail closed

    Args:
        loop_result: The loop result from orchestrator
        runner_result_dict: The runner_result portion
        read_only_checks_sidecar: The sidecar with handler invocations
        fake_handlers: The known fake handlers
        enforce: Whether to enforce (can disable for testing)
        allow_zero_checks: For ACT-local proof path, require checks_run > 0.
            This proves fake handlers are actually exercised.

    Raises:
        FakeHandlerExecutionError: If enforce=True and any rule is violated
    """
    if not enforce:
        return

    enforcement_errors: list[str] = []
    checks_run = runner_result_dict.get("checks_run", 0)

    # Rule 1: For ACT-local proof path, require checks_run > 0
    # This proves fake handlers are actually exercised, not just available
    if not allow_zero_checks:
        if checks_run <= 0:
            enforcement_errors.append(
                f"Fake-handler enforcement failed: checks_run={checks_run}. "
                "The ACT-local proof path requires checks_run > 0 to prove "
                "fake handlers are actually exercised. "
                "A stop-without-checks is valid product behavior but does not "
                "prove this ACT."
            )

    # Rule 2: If we ran checks, must have recorded invocations
    if checks_run > 0 and not read_only_checks_sidecar["handler_invocations"]:
        enforcement_errors.append(
            "Fake-handler enforcement failed: checks_run > 0 but handler_invocations is empty. "
            "When checks are run, the orchestrator must record handler invocations."
        )

    # Rule 3: All invocations must have golden_case_handler=true
    for invocation in read_only_checks_sidecar["handler_invocations"]:
        if not invocation.get("golden_case_handler"):
            enforcement_errors.append(
                f"Fake-handler enforcement failed: check_id={invocation.get('check_id')} "
                "has golden_case_handler=false (expected true)."
            )

    # Rule 4: All invocations must have no_kubernetes_call=true
    for invocation in read_only_checks_sidecar["handler_invocations"]:
        if not invocation.get("no_kubernetes_call"):
            enforcement_errors.append(
                f"Fake-handler enforcement failed: check_id={invocation.get('check_id')} "
                "has no_kubernetes_call=false (expected true)."
            )

    # Rule 5: Fail on unknown check IDs (not in expected handler list)
    known_handler_ids = set(fake_handlers.keys())
    for invocation in read_only_checks_sidecar["handler_invocations"]:
        check_id = invocation.get("check_id", "")
        if check_id not in known_handler_ids:
            enforcement_errors.append(
                f"Fake-handler enforcement failed: unknown check_id='{check_id}'. "
                "Only golden-case fake handlers are allowed. "
                "Policy: unknown check IDs must fail closed."
            )

    if enforcement_errors:
        raise FakeHandlerExecutionError(
            "Fake-handler execution enforcement failed:\n" +
            "\n".join(f"  - {e}" for e in enforcement_errors)
        )

"""Aggregate self-test runner for the redaction verifier."""

from __future__ import annotations

from collections.abc import Callable

from scripts.incident_lifecycle_boundary.redaction_self_test_aliases import (
    run_aliases_self_test,
    run_factory_exception_omission_self_test,
)
from scripts.incident_lifecycle_boundary.redaction_self_test_boundaries import (
    run_boundary_self_test,
)
from scripts.incident_lifecycle_boundary.redaction_self_test_constructors import (
    run_constructor_self_test,
)
from scripts.incident_lifecycle_boundary.redaction_self_test_projection import (
    run_projector_serializer_self_test,
)
from scripts.incident_lifecycle_boundary.redaction_self_test_serialization import (
    run_serializer_multi_return_self_test,
)

SelfTestRunner = Callable[[], tuple[int, int, int]]


def run_self_tests() -> tuple[int, int, int]:
    """Run every verifier subsystem self-test via production check functions."""
    print("=" * 70)
    print("REDUCTION TYPES VERIFIER SUBSYSTEM SELF-TESTS")
    print("=" * 70)

    total_accepted = total_rejected = total_failed = 0
    runners: tuple[SelfTestRunner, ...] = (
        run_aliases_self_test,
        run_factory_exception_omission_self_test,
        run_projector_serializer_self_test,
        run_constructor_self_test,
        run_boundary_self_test,
        run_serializer_multi_return_self_test,
    )
    for runner in runners:
        accepted, rejected, failed = runner()
        total_accepted += accepted
        total_rejected += rejected
        total_failed += failed

    print("\n" + "=" * 70)
    print(
        f"SELF-TEST SUMMARY: accepted={total_accepted}, rejected={total_rejected}, failed={total_failed}",
    )
    print("=" * 70)
    return total_accepted, total_rejected, total_failed

"""Import-only regression tests for automatic diagnosis loop modules."""

from __future__ import annotations


def test_automatic_diagnosis_loop_modules_import_without_cycles() -> None:
    """Verify both orchestration modules can be imported without circular dependency."""
    import k8s_diag_agent.collect.incident_diagnosis_auto_loop  # noqa: F401
    import k8s_diag_agent.collect.incident_diagnosis_auto_loop_entrypoints  # noqa: F401


def test_automatic_diagnosis_loop_public_symbols_importable() -> None:
    """Verify public symbols are importable from leaf and orchestration modules."""
    from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
        run_automatic_diagnosis_loop_evidence_collection,
    )
    from k8s_diag_agent.collect.incident_diagnosis_auto_loop_entrypoints import (
        collect_automatic_diagnosis_evidence,
    )
    from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
        collect_automatic_diagnosis_evidence as leaf_collect,
    )
    from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
        run_automatic_diagnosis_loop_evidence_collection as leaf_run,
    )

    assert callable(run_automatic_diagnosis_loop_evidence_collection)
    assert callable(collect_automatic_diagnosis_evidence)
    assert callable(leaf_collect)
    assert callable(leaf_run)


def test_automatic_diagnosis_loop_modules_import_in_reverse_order() -> None:
    """Verify both orchestration modules can be imported in reverse order.

    This catches cycles that only appear depending on initial import order.
    """
    # ruff: noqa: I001  # intentional reverse order for cycle detection
    import k8s_diag_agent.collect.incident_diagnosis_auto_loop_entrypoints  # noqa: F401
    import k8s_diag_agent.collect.incident_diagnosis_auto_loop  # noqa: F401

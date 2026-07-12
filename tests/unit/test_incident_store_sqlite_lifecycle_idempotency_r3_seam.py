"""R3 regression tests for SQLite lifecycle idempotency (capability seam).

Closes R3-4 from the
``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:

* **R3-4** — the implementation must use the canonical write
  context, not raw ``store._write_lock`` / ``store._connect()`` /
  ``store._incidents`` / ``store._snapshot_incident()`` access.

Companion files:

* ``test_incident_store_sqlite_lifecycle_idempotency_r3.py`` — R3-1,
  R3-2, R3-5, R3-6.
* ``test_incident_store_sqlite_lifecycle_idempotency_r3_events.py``
  — R3-3 hash chain.

The tests rely on the canonical
:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`
path that the R2 module now delegates to.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R3)
"""

from __future__ import annotations

import ast
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import TestCase, mock

from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
    apply_lifecycle_transition_atomic,
)

from .incident_store_sqlite_seam_helpers import make_candidate

_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)


def _populate(store: SQLiteIncidentStore) -> str:
    """Create one incident and return its id."""
    candidate = make_candidate(name="diag-loop-test-pod")
    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    incidents = store.promote_candidates([candidate], observed_at)
    return str(incidents[0].incident_id)


def _payload_completed() -> dict[str, object]:
    return {
        "review_packet_name": "review.json",
        "checks_requested": 1,
        "checks_run": 1,
        "checks_rejected": 0,
        "decision": "stop_root_cause_found",
    }


class TestR3CapabilitySeam(TestCase):
    """R3-4: The lifecycle apply must go through
    ``SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently``.
    No raw ``_write_lock`` / ``_connect`` / ``_incidents`` /
    ``_snapshot_incident`` access from outside the seam.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_apply_uses_canonical_write_context_method(self) -> None:
        from k8s_diag_agent.collect import (
            incident_store_sqlite_context as context_module,
        )

        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)

        captured = {"called": False}

        def _spy_apply(self: Any, *args: Any, **kwargs: Any) -> Any:
            captured["called"] = True
            return _original_apply(self, *args, **kwargs)

        _original_apply = (
            context_module.SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently
        )

        with mock.patch.object(
            context_module.SQLiteWriteContext,
            "apply_diagnosis_lifecycle_idempotently",
            _spy_apply,
        ):
            apply_lifecycle_transition_atomic(
                store,
                transition="completed",
                incident_id=incident_id,
                run_id="run-seam",
                collector_run_id="collector-seam",
                fingerprint="fp-seam",
                occurred_at=_OCCURRED_AT,
                payload=_payload_completed(),
            )

        self.assertTrue(
            captured["called"],
            "apply_lifecycle_transition_atomic must invoke the canonical context method",
        )

    def test_adapter_module_does_not_reach_into_private_store_state(self) -> None:
        """Static AST check: the adapter module must not call
        ``store._write_lock``, ``store._connect(...)``,
        ``store._incidents``, ``store._snapshot_incident(...)``, or
        ``store._state_to_incident(...)``. The check inspects the
        parsed AST (not the docstring) so module documentation
        that mentions these names for context does NOT count as a
        violation.
        """
        from k8s_diag_agent.collect import (
            incident_store_sqlite_lifecycle_idempotency as adapter,
        )

        source = Path(adapter.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)

        forbidden_attrs = (
            "_write_lock",
            "_incidents",
            "_snapshot_incident",
            "_state_to_incident",
        )
        forbidden_calls = ("_connect",)
        violations: list[str] = []

        def _walk(node: ast.AST) -> None:
            for child in ast.iter_child_nodes(node):
                # Detect ``store._connect(...)`` calls.
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr in forbidden_calls
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "store"
                ):
                    violations.append(
                        f"call store.{child.func.attr}(...) at line {child.lineno}"
                    )
                # Detect ``store._write_lock`` etc. attribute reads.
                if (
                    isinstance(child, ast.Attribute)
                    and child.attr in forbidden_attrs
                    and isinstance(child.value, ast.Name)
                    and child.value.id == "store"
                ):
                    violations.append(
                        f"access store.{child.attr} at line {child.lineno}"
                    )
                _walk(child)

        _walk(tree)
        self.assertEqual(
            violations,
            [],
            "adapter must not reach into private store members: "
            + "; ".join(violations),
        )


__all__ = [
    "TestR3CapabilitySeam",
]
"""Production mypy fixtures for the backend incident-detail outcome contract.

This file mirrors :mod:`test_redaction_r9_mypy_fixtures` for the
``BackendIncidentFound`` contract added in
ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01-R1:

* The **positive** fixture constructs every supported outcome variant
  and proves that mypy accepts them.
* The **negative** fixture constructs a deliberately-widened
  ``BackendIncidentFound(..., incident={"incident_id": "x"})`` call
  so mypy can demonstrate it is statically rejected. The runtime
  dataclass would accept ``object`` for the ``incident`` field if the
  annotation were widened, but a real type checker MUST prove the
  widening is impossible by typing ``incident: Incident``.

The verifier suites and unit tests rely on this fixture; the negative
fixture is the actual evidence that the dataclass field annotation
is doing real static work (not just metadata).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

VENV_BIN_PYTHON = Path(__file__).parent.parent.parent / ".venv" / "bin" / "python"
REPO_ROOT = Path(__file__).parent.parent.parent
REPO_SRC = REPO_ROOT / "src"
MYPY_CONFIG = REPO_ROOT / "mypy.ini"

# Positive fixture: every supported variant constructs cleanly under mypy.
MYPY_POSITIVE_FIXTURE = """\
from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentFound,
    BackendIncidentLookupFailed,
    BackendIncidentLookupFailureCode,
    BackendIncidentLookupSource,
    BackendIncidentNotFound,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentStatus,
)
from k8s_diag_agent.domain.incident_lifecycle import IncidentId


def build_positive_outcomes() -> tuple[
    BackendIncidentFound,
    BackendIncidentNotFound,
    BackendIncidentLookupFailed,
]:
    incident = Incident(
        incident_id="incident-abc",
        source_candidate_id="candidate-1",
        namespace="default",
        object_kind="Pod",
        object_name="nginx-pod",
        raw_object_kind=None,
        candidate_class="PodCrashLoop",
        severity="high",
        status=IncidentStatus.OPEN,
        first_observed_at=datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC),
        last_observed_at=datetime(2026, 7, 12, 10, 30, 0, tzinfo=UTC),
        signal_count=1,
        evidence_count=0,
    )

    found = BackendIncidentFound(
        requested_incident_id=IncidentId("incident-abc"),
        incident=incident,
        source=BackendIncidentLookupSource.BACKEND_API,
        http_status=200,
        payload_schema_version=1,
        payload_type="incident-internal-detail",
    )

    not_found = BackendIncidentNotFound(
        requested_incident_id=IncidentId("incident-abc"),
        source=BackendIncidentLookupSource.BACKEND_API,
        http_status=404,
    )

    failed = BackendIncidentLookupFailed(
        requested_incident_id=IncidentId("incident-abc"),
        failure_code=BackendIncidentLookupFailureCode.INVALID_JSON,
        detail="non-JSON body",
        http_status=200,
    )

    return found, not_found, failed
"""


# Negative fixture: deliberately calls
# ``BackendIncidentFound(..., incident={"incident_id": "x"})`` with a
# raw ``dict`` for the ``incident`` field. A real type checker MUST
# reject this with an ``incompatible type`` diagnostic for the
# ``incident`` argument.
MYPY_NEGATIVE_FIXTURE = """\
from __future__ import annotations

from typing import reveal_type

from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentFound,
    BackendIncidentLookupSource,
)
from k8s_diag_agent.domain.incident_lifecycle import IncidentId


reveal_type(BackendIncidentFound)
reveal_type(BackendIncidentLookupSource)

# Negative construction: ``incident`` is annotated as the canonical
# ``Incident`` aggregate, so passing a raw ``dict`` MUST be rejected
# by mypy. This is the proof that the field annotation is doing real
# static work, not just runtime metadata.
BackendIncidentFound(
    requested_incident_id=IncidentId("x"),
    incident={"incident_id": "x"},
    source=BackendIncidentLookupSource.BACKEND_API,
    http_status=200,
    payload_schema_version=1,
    payload_type="incident-internal-detail",
)
"""


def _run_mypy(target: Path) -> tuple[int, str]:
    """Run mypy with the real project source path and configuration."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_SRC)
    env["MYPYPATH"] = str(REPO_SRC)
    proc = subprocess.run(
        [
            str(VENV_BIN_PYTHON),
            "-m",
            "mypy",
            "--config-file",
            str(MYPY_CONFIG),
            "--no-incremental",
            "--cache-dir=/dev/null",
            "--follow-imports=normal",
            str(target),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


class TestMypyPositiveFixture:
    """Positive fixture compiles cleanly under mypy.

    Every supported outcome variant is constructible with the public
    kwargs; the canonical ``Incident`` aggregate must satisfy the
    ``BackendIncidentFound.incident`` field.
    """

    def test_positive_fixture_typechecks(self, tmp_path: Path) -> None:
        fixture = tmp_path / "mypy_positive_fixture.py"
        fixture.write_text(MYPY_POSITIVE_FIXTURE, encoding="utf-8")
        rc, output = _run_mypy(fixture)
        assert rc == 0, output


class TestMypyNegativeFixture:
    """Negative fixture proves the ``incident`` field is statically ``Incident``.

    Concretely: constructing
    ``BackendIncidentFound(..., incident={"incident_id": "x"})`` MUST be
    rejected by mypy. This is the static-typedness proof for the
    ``BackendIncidentFound`` dataclass field annotation added in
    ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01-R1.
    """

    def test_negative_fixture_imports_production_contract(self) -> None:
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentFound,
            BackendIncidentLookupSource,
        )
        from k8s_diag_agent.domain.incident_lifecycle import IncidentId

        assert BackendIncidentFound.__module__.startswith(
            "k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes",
        )
        assert BackendIncidentLookupSource.__module__.startswith(
            "k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes",
        )
        assert IncidentId.__module__.startswith(
            "k8s_diag_agent.domain.incident_lifecycle",
        )

    def test_negative_fixture_mypy_rejects_incompatible_incident_argument(
        self,
        tmp_path: Path,
    ) -> None:
        fixture = tmp_path / "mypy_negative_fixture.py"
        fixture.write_text(MYPY_NEGATIVE_FIXTURE, encoding="utf-8")

        rc, output = _run_mypy(fixture)
        assert rc != 0, (
            "mypy must reject the negative fixture, but it exited 0.\n"
            f"Output:\n{output}"
        )
        # The diagnostic must reference the ``incident`` argument and
        # mention incompatibility (the ``BackendIncidentFound.incident``
        # field is annotated as ``Incident``).
        assert "incident" in output, (
            f"mypy output should mention the ``incident`` argument, got:\n{output}"
        )
        assert "incompatible" in output or "expected" in output, (
            f"mypy output should declare type incompatibility, got:\n{output}"
        )

"""Production mypy fixtures for privacy-state boundaries."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

VENV_BIN_PYTHON = Path(__file__).parent.parent.parent / ".venv" / "bin" / "python"
REPO_ROOT = Path(__file__).parent.parent.parent
REPO_SRC = REPO_ROOT / "src"
MYPY_CONFIG = REPO_ROOT / "mypy.ini"

MYPY_POSITIVE_FIXTURE = """\
from __future__ import annotations

from k8s_diag_agent.collect.incident_evidence_llm_safe import (
    RedactedEvidenceSummary,
    evidence_artifact_to_llm_safe_summary,
)
from k8s_diag_agent.collect.incident_evidence_redaction import (
    RawEvidenceText,
    project_raw_evidence_text_for_llm,
)
from k8s_diag_agent.collect.incident_evidence_types import (
    ArtifactId,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceRole,
    LLMSafeArtifactRef,
    SafeRelativeArtifactPath,
)


def build_positive_summary(
    artifact_id: ArtifactId,
    kind: EvidenceKind,
    role: EvidenceRole,
    raw_text: str,
) -> RedactedEvidenceSummary:
    safe = project_raw_evidence_text_for_llm(
        RawEvidenceText(raw_text),
        max_chars=200,
    )
    artifact = EvidenceArtifact(
        artifact_id=artifact_id,
        kind=kind,
        storage_ref=SafeRelativeArtifactPath("incidents/x/log.json"),
    )
    return evidence_artifact_to_llm_safe_summary(
        artifact=artifact,
        safe_ref=LLMSafeArtifactRef("incidents/x/log.json"),
        summary=safe,
    )
"""

MYPY_NEGATIVE_FIXTURE = """\
from typing import reveal_type

from k8s_diag_agent.collect.incident_evidence_llm_safe import (
    RedactedEvidenceSummary,
    evidence_artifact_to_llm_safe_summary,
)
from k8s_diag_agent.collect.incident_evidence_redaction import (
    RedactedEvidenceText,
)
from k8s_diag_agent.collect.incident_evidence_types import (
    ArtifactId,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceRole,
    SafeRelativeArtifactPath,
)

artifact_id = ArtifactId("art-1")
kind = EvidenceKind.LOG_EXCERPT
role = EvidenceRole.SUPPORTING
artifact = EvidenceArtifact(
    artifact_id=artifact_id,
    kind=kind,
    storage_ref=SafeRelativeArtifactPath("incidents/x/log.json"),
)

reveal_type(RedactedEvidenceText)
reveal_type(RedactedEvidenceSummary)
reveal_type(evidence_artifact_to_llm_safe_summary)

redacted = RedactedEvidenceText("already redacted")

RedactedEvidenceSummary(
    artifact_id=artifact_id,
    kind=kind,
    role=role,
    summary=redacted,
)

evidence_artifact_to_llm_safe_summary(
    artifact=artifact,
    safe_ref=None,
    summary=redacted,
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
    """Positive fixture compiles cleanly under mypy."""

    def test_positive_fixture_typechecks(self, tmp_path: Path) -> None:
        fixture = tmp_path / "mypy_positive_fixture.py"
        fixture.write_text(MYPY_POSITIVE_FIXTURE, encoding="utf-8")
        rc, output = _run_mypy(fixture)
        assert rc == 0, output


class TestMypyNegativeFixture:
    """Negative fixture proves RedactedEvidenceText is not LLMSafeEvidenceText."""

    def test_negative_fixture_imports_production_contract(self) -> None:
        from k8s_diag_agent.collect.incident_evidence_llm_safe import (
            RedactedEvidenceSummary,
            evidence_artifact_to_llm_safe_summary,
        )
        from k8s_diag_agent.collect.incident_evidence_redaction import (
            RedactedEvidenceText,
        )

        assert RedactedEvidenceText.__module__.startswith(
            "k8s_diag_agent.collect.incident_evidence_redaction",
        )
        assert RedactedEvidenceSummary.__module__.startswith(
            "k8s_diag_agent.collect.incident_evidence_llm_safe",
        )
        assert evidence_artifact_to_llm_safe_summary.__module__.startswith(
            "k8s_diag_agent.collect.incident_evidence_llm_safe",
        )

    def test_negative_fixture_mypy_rejects_both_production_call_sites(
        self,
        tmp_path: Path,
    ) -> None:
        fixture = tmp_path / "mypy_negative_fixture.py"
        fixture.write_text(MYPY_NEGATIVE_FIXTURE, encoding="utf-8")

        rc, output = _run_mypy(fixture)
        assert rc != 0, output
        assert 'Revealed type is "Any"' not in output
        assert "RedactedEvidenceText" in output
        assert "LLMSafeEvidenceText" in output
        assert 'Argument "summary" to "RedactedEvidenceSummary" has incompatible type' in output
        assert ('Argument "summary" to "evidence_artifact_to_llm_safe_summary" has incompatible type') in output

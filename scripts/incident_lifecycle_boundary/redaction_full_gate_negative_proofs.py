"""Full gate negative proofs for redaction privacy-state verifier violations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYTHON = REPO / ".venv" / "bin" / "python"
POPULATE = REPO / "scripts" / "factory" / "populate_gate_summary.py"
PARSER = REPO / "scripts" / "factory" / "parse_gate_summary.py"

Mutation = Callable[[Path], None]


def _copy_base_tree(root: Path) -> None:
    collect = root / "k8s_diag_agent" / "collect"
    collect.mkdir(parents=True, exist_ok=True)
    for name in (
        "incident_evidence_redaction.py",
        "incident_evidence_llm_safe.py",
        "incident_evidence_types.py",
    ):
        shutil.copyfile(REPO / "src" / "k8s_diag_agent" / "collect" / name, collect / name)
    (root / "k8s_diag_agent" / "__init__.py").write_text("", encoding="utf-8")
    (collect / "__init__.py").write_text("", encoding="utf-8")
    (collect / "incident_evidence.py").write_text(
        "from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText, RawEvidenceText, RedactedEvidenceText, SafeEvidenceExcerpt,\n)\n",
        encoding="utf-8",
    )


def _facade_constructor(root: Path) -> None:
    (root / "k8s_diag_agent" / "collect" / "incident_prompt_builder.py").write_text(
        "import k8s_diag_agent.collect.incident_evidence as facade\ndef make() -> str:\n    return facade.LLMSafeEvidenceText('unsafe')\n",
        encoding="utf-8",
    )


def _protected_annotation(root: Path) -> None:
    (root / "k8s_diag_agent" / "collect" / "incident_case_file.py").write_text(
        "from __future__ import annotations\nimport k8s_diag_agent.collect.incident_evidence as evidence\nclass CaseFile:\n    summary: evidence.RedactedEvidenceText\n",
        encoding="utf-8",
    )


def _serializer_omission(root: Path) -> None:
    path = root / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace('            "summary": str(self.summary),\n', "")
    path.write_text(text, encoding="utf-8")


def _projector_redacted_summary(root: Path) -> None:
    path = root / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "    summary: LLMSafeEvidenceText,\n) -> RedactedEvidenceSummary:",
        "    summary: RedactedEvidenceText,\n) -> RedactedEvidenceSummary:",
        1,
    )
    path.write_text(text, encoding="utf-8")


VIOLATIONS: tuple[tuple[str, Mutation], ...] = (
    ("illegal facade-qualified trusted constructor", _facade_constructor),
    ("protected qualified RedactedEvidenceText annotation", _protected_annotation),
    ("serializer branch omitting summary", _serializer_omission),
    ("projector summary typed as RedactedEvidenceText", _projector_redacted_summary),
)


def _run_populate(repo_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["K9B_R12_FULL_GATE_PROOF_CHILD"] = "1"
    target = repo_root / ".factory" / "gate-summary.json"
    return subprocess.run(
        [str(PYTHON), str(POPULATE), "--repo-root", str(repo_root), "--target", str(target)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _run_parser(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON), str(PARSER), "--target", str(repo_root / ".factory" / "gate-summary.json"), "--quiet"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _check_named_failure(repo_root: Path) -> bool:
    data = json.loads((repo_root / ".factory" / "gate-summary.json").read_text(encoding="utf-8"))
    checks = data.get("checks", [])
    if not isinstance(checks, list):
        return False
    for check in checks:
        if isinstance(check, dict) and check.get("name") == "full-gate-negative-proofs":
            return check.get("status") == "fail"
    return False


def _make_tree(mutation: Mutation | None = None) -> tuple[str, Path]:
    temp_dir = tempfile.mkdtemp(prefix="r12_full_gate_negative_")
    root = Path(temp_dir)
    _copy_base_tree(root)
    if mutation is not None:
        mutation(root)
    return temp_dir, root


def main() -> int:
    failures: list[str] = []
    for label, mutation in VIOLATIONS:
        temp_dir, root = _make_tree(mutation)
        try:
            proc = _run_populate(root)
            if proc.returncode == 0:
                failures.append(f"{label}: full gate unexpectedly passed")
            if not _check_named_failure(root):
                failures.append(f"{label}: full-gate-negative-proofs check was not failed")
            parser = _run_parser(root)
            if parser.returncode == 0:
                failures.append(f"{label}: parser unexpectedly passed failed artifact")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        clean_dir, clean_root = _make_tree()
        try:
            clean = _run_populate(clean_root)
            if clean.returncode != 0:
                failures.append(f"{label}: clean temp tree rerun failed: {clean.stdout}{clean.stderr}")
            clean_parser = _run_parser(clean_root)
            if clean_parser.returncode != 0:
                failures.append(f"{label}: clean temp tree parser failed: {clean_parser.stdout}{clean_parser.stderr}")
        finally:
            shutil.rmtree(clean_dir, ignore_errors=True)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: full gate negative proofs fail closed and clean reruns pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())

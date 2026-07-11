"""Protected-boundary self-tests for the redaction verifier."""

from __future__ import annotations

from scripts.incident_lifecycle_boundary.redaction_boundaries import (
    check_protected_boundary_imports,
)
from scripts.incident_lifecycle_boundary.redaction_types_self_test import (
    cleanup_temp_repo_tree,
    create_temp_repo_tree,
)


def run_boundary_self_test() -> tuple[int, int, int]:
    """Run protected boundary checks through production verifier."""
    accepted = rejected = failed = 0
    print("\n[5] Protected boundaries subsystem (production checker on temp trees):")

    positive_files = {
        "k8s_diag_agent/collect/incident_case_file.py": ("from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText,\n)\nclass CaseFile:\n    summary: LLMSafeEvidenceText\n"),
        "k8s_diag_agent/collect/incident_evidence_redaction.py": (
            "from typing import NewType\nRawEvidenceText = NewType('RawEvidenceText', str)\nRedactedEvidenceText = NewType('RedactedEvidenceText', str)\nLLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
        ),
    }
    temp_dir, repo_root = create_temp_repo_tree(positive_files, source_dir=".")
    try:
        errors = check_protected_boundary_imports(repo_root)
        passed = errors == []
        print(f"  [{'PASS' if passed else 'FAIL'}] accepted: protected module uses LLMSafeEvidenceText only")
    finally:
        cleanup_temp_repo_tree(temp_dir)
    accepted += 1
    failed += 0 if passed else 1

    negative_files = {
        "k8s_diag_agent/collect/incident_case_file.py": """\
from __future__ import annotations
import k8s_diag_agent.collect.incident_evidence as evidence

class CaseFile:
    summary: "RedactedEvidenceText"
    alt: "list[RedactedEvidenceText]"
    qualified: "evidence.RawEvidenceText"
    nested: "dict[str, evidence.RawEvidenceText]"
""",
        "k8s_diag_agent/collect/incident_evidence_redaction.py": (
            "from typing import NewType\nRawEvidenceText = NewType('RawEvidenceText', str)\nRedactedEvidenceText = NewType('RedactedEvidenceText', str)\nLLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
        ),
        "k8s_diag_agent/collect/incident_evidence.py": ("from k8s_diag_agent.collect.incident_evidence_redaction import (\n    RawEvidenceText,\n    RedactedEvidenceText,\n    LLMSafeEvidenceText,\n)\n"),
    }
    temp_dir, repo_root = create_temp_repo_tree(negative_files, source_dir=".")
    try:
        errors = check_protected_boundary_imports(repo_root)
        passed = bool(errors) and any("RawEvidenceText" in e for e in errors)
        passed = passed and any("RedactedEvidenceText" in e for e in errors)
        print(f"  [{'PASS' if passed else 'FAIL'}] rejected: postponed + qualified protected annotations ({len(errors)} diagnostics)")
    finally:
        cleanup_temp_repo_tree(temp_dir)
    rejected += 1
    failed += 0 if passed else 1
    return accepted, rejected, failed

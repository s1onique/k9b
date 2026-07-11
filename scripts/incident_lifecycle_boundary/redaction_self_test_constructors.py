"""Constructor provenance self-tests for the redaction verifier."""

from __future__ import annotations

from scripts.incident_lifecycle_boundary.redaction_constructors import (
    check_trusted_constructor_usage,
)
from scripts.incident_lifecycle_boundary.redaction_types_self_test import (
    cleanup_temp_repo_tree,
    create_temp_repo_tree,
)


def run_constructor_self_test() -> tuple[int, int, int]:
    """Run constructor checks through production verifier on temp trees."""
    accepted = rejected = failed = 0
    print("\n[4] Constructor subsystem (production checker on temp trees):")

    positive_files = {
        "collect/incident_evidence_redaction.py": (
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            "def _use(value):\n"
            "    return LLMSafeEvidenceText(value)\n"
        ),
        "collect/incident_caller.py": ("from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText,\n)\nx: LLMSafeEvidenceText\n"),
    }
    temp_dir, repo_root = create_temp_repo_tree(positive_files, source_dir="k8s_diag_agent")
    try:
        errors = check_trusted_constructor_usage(repo_root, source_dir="k8s_diag_agent")
        passed = not errors
        print(f"  [{'PASS' if passed else 'FAIL'}] accepted: caller uses type annotation only")
    finally:
        cleanup_temp_repo_tree(temp_dir)
    accepted += 1
    failed += 0 if passed else 1

    fixture_files = {
        "collect/incident_prompt_builder.py": ("from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText,\n)\nvalue = LLMSafeEvidenceText('x')\n"),
        "collect/incident_alias_caller.py": ("from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText as Safe,\n)\nvalue = Safe('x')\n"),
        "collect/incident_module_qualified.py": ("import k8s_diag_agent.collect.incident_evidence_redaction as redaction\nvalue = redaction.LLMSafeEvidenceText('x')\n"),
        "collect/incident_facade_qualified.py": ("import k8s_diag_agent.collect.incident_evidence as facade\nvalue = facade.LLMSafeEvidenceText('x')\n"),
        "collect/incident_evidence_redaction.py": (
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        ),
    }
    temp_dir, repo_root = create_temp_repo_tree(fixture_files, source_dir="k8s_diag_agent")
    try:
        errors = check_trusted_constructor_usage(repo_root, source_dir="k8s_diag_agent")
        passed = bool(errors) and all("Direct constructor call" in e for e in errors)
        for filename in (
            "incident_prompt_builder.py",
            "incident_alias_caller.py",
            "incident_module_qualified.py",
            "incident_facade_qualified.py",
        ):
            passed = passed and any(filename in e for e in errors)
        print(f"  [{'PASS' if passed else 'FAIL'}] rejected: 4 required rejected forms ({len(errors)} diagnostics)")
    finally:
        cleanup_temp_repo_tree(temp_dir)
    rejected += 1
    failed += 0 if passed else 1
    return accepted, rejected, failed

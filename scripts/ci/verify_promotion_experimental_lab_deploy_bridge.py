#!/usr/bin/env python3
"""Structural verifier for experimental lab deploy bridge workflow."""
from __future__ import annotations

import re
import sys
from pathlib import Path

JOB_LEVEL_CALL = re.compile(r"^\s+uses:\s+.+reusable-promotion-deploy\.yml")


class BridgeError(Exception):
    """Raised on structural violation."""


def check_github_scripts_absent() -> list[str]:
    """Reject any Python under .github/scripts."""
    errors = []
    scripts_dir = Path(".github/scripts")
    if scripts_dir.exists():
        for py_file in scripts_dir.glob("*.py"):
            if py_file.name != "__init__.py":
                errors.append(f".github/scripts/{py_file.name} must be deleted")
    return errors


def check_scripts_ci_authority() -> list[str]:
    """Accept exactly three bridge authorities."""
    ci_dir = Path("scripts/ci")
    errors = []
    expected = {
        "promotion_experimental_lab_artifact.py",
        "promotion_experimental_lab_authorization.py",
        "verify_promotion_experimental_lab_deploy_bridge.py",
    }
    actual = {p.name for p in ci_dir.glob("*.py")}
    actual = {n for n in actual if "promotion_experimental_lab" in n}
    missing = expected - actual
    extra = actual - expected
    if missing:
        errors.append(f"Missing CI authorities: {missing}")
    if extra:
        errors.append(f"Extra CI authorities: {extra}")
    return errors


def check_workflow_caller_grammar(workflow_path: Path) -> list[str]:
    """Verify job-level reusable workflow call and no forbidden patterns."""
    errors = []
    content = workflow_path.read_text()

    deploy_match = re.search(r"^  deploy:\s*\n((?:    .+\n)*)", content, re.MULTILINE)
    if deploy_match:
        deploy_block = deploy_match.group(1)
        if "runs-on:" in deploy_block:
            errors.append("deploy job must not have runs-on")
        if "steps:" in deploy_block:
            errors.append("deploy job must not have steps")
        if "uses:" not in deploy_block:
            errors.append("deploy job must have job-level uses: call")
        if not re.search(r"^\s+uses:\s+.*reusable-promotion-deploy\.yml", deploy_block, re.MULTILINE):
            errors.append("deploy job must call reusable-promotion-deploy.yml")
    else:
        errors.append("deploy job not found")

    return errors


def check_gh_token_on_all_gh_commands(workflow_path: Path) -> list[str]:
    """Ensure GH_TOKEN is set on every gh command."""
    errors = []
    content = workflow_path.read_text()
    lines = content.split("\n")

    in_gh_step = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("gh "):
            in_gh_step = True
        elif in_gh_step:
            if "env:" in line:
                if "GH_TOKEN:" not in line:
                    errors.append(f"gh command at line {i+1} missing GH_TOKEN env")
            elif stripped.startswith("-"):
                in_gh_step = False
        elif stripped.startswith("uses:"):
            in_gh_step = False

    return errors


def check_unsupported_gh_api_output_flag(workflow_path: Path) -> list[str]:
    """Reject unsupported gh api -o flag."""
    errors = []
    content = workflow_path.read_text()
    if re.search(r"gh\s+api\s+[^|>\n]*\s+-o\s", content):
        errors.append("Unsupported gh api -o flag detected")
    return errors


def check_exact_artifact_selection(workflow_path: Path) -> list[str]:
    """Reject prefix/substring artifact matching."""
    errors = []
    content = workflow_path.read_text()
    if re.search(r"name.*contains\(", content):
        errors.append("Substring artifact selection not allowed")
    if re.search(r"name.*startswith\(", content):
        errors.append("Prefix artifact selection not allowed")
    return errors


def check_supported_artifact_transfer(workflow_path: Path) -> list[str]:
    """Reject unsupported REST artifact upload."""
    errors = []
    content = workflow_path.read_text()
    if re.search(r"gh\s+api\s+.*actions/artifacts.*POST", content):
        errors.append("Unsupported REST artifact upload")
    return errors


def check_literal_github_output(ci_files: list[Path]) -> list[str]:
    """Reject literal $GITHUB_OUTPUT filename."""
    errors = []
    for fpath in ci_files:
        content = fpath.read_text()
        if '"$GITHUB_OUTPUT"' in content or "'$GITHUB_OUTPUT'" in content:
            errors.append(f"Literal $GITHUB_OUTPUT in {fpath}")
    return errors


def check_no_fake_digest(workflow_path: Path) -> list[str]:
    """Reject artifact_digest=verified placeholder."""
    errors = []
    content = workflow_path.read_text()
    if re.search(r'artifact_digest\s*=\s*["\']?verified["\']?', content):
        errors.append("Fake artifact_digest=verified placeholder not allowed")
    return errors


def check_second_barrier_main_recheck(workflow_path: Path) -> list[str]:
    """Ensure second barrier re-checks main SHA."""
    errors = []
    content = workflow_path.read_text()

    if "authorize-latest:" in content:
        auth_block = content.split("authorize-latest:")[1].split("\njobs:")[0] if "\njobs:" in content else ""
        if "current_main" not in auth_block and "main" not in auth_block:
            errors.append("Second barrier missing main SHA recheck")
    return errors


def check_no_copied_outputs(workflow_path: Path) -> list[str]:
    """Ensure second barrier emits from downloaded record, not first job."""
    errors = []
    content = workflow_path.read_text()

    lines = content.split("\n")
    auth_block_lines = []
    in_auth_block = False

    for line in lines:
        if line.startswith("  authorize-latest:"):
            in_auth_block = True
            auth_block_lines.append(line)
            continue
        if in_auth_block:
            if line.startswith("  deploy:"):
                break
            auth_block_lines.append(line)

    auth_block = "\n".join(auth_block_lines)

    in_outputs = False
    for line in auth_block.split("\n"):
        stripped = line.strip()
        if stripped.startswith("outputs:"):
            in_outputs = True
        elif in_outputs and (stripped.startswith("if:") or stripped.startswith("steps:")):
            in_outputs = False
        if in_outputs and "needs.validate-upstream.outputs" in line:
            errors.append("authorize-latest outputs must not copy validate-upstream outputs")
            break

    if "steps.confirm.outputs" not in auth_block:
        errors.append("authorize-latest missing steps.confirm.outputs")
    return errors


def check_static_scope(ci_files: list[Path]) -> list[str]:
    """Verify all bridge Python is under scripts/ci."""
    errors = []
    for fpath in ci_files:
        if ".github/scripts" in str(fpath):
            errors.append(f"Python under .github/scripts not allowed: {fpath}")
    return errors


def verify_bridge() -> list[str]:
    """Run all structural checks."""
    all_errors: list[str] = []

    workflow_path = Path(".github/workflows/promotion-experimental-lab-deploy.yml")
    ci_files = list(Path("scripts/ci").glob("promotion_experimental_lab_*.py"))

    all_errors.extend(check_github_scripts_absent())
    all_errors.extend(check_scripts_ci_authority())
    all_errors.extend(check_workflow_caller_grammar(workflow_path))
    all_errors.extend(check_gh_token_on_all_gh_commands(workflow_path))
    all_errors.extend(check_unsupported_gh_api_output_flag(workflow_path))
    all_errors.extend(check_exact_artifact_selection(workflow_path))
    all_errors.extend(check_supported_artifact_transfer(workflow_path))
    all_errors.extend(check_literal_github_output(ci_files))
    all_errors.extend(check_no_fake_digest(workflow_path))
    all_errors.extend(check_second_barrier_main_recheck(workflow_path))
    all_errors.extend(check_no_copied_outputs(workflow_path))
    all_errors.extend(check_static_scope(ci_files))

    return all_errors


def main() -> None:
    errors = verify_bridge()
    if errors:
        for e in errors:
            print(f"FATAL: {e}")
        sys.exit(1)
    print("STRUCTURAL_VERIFIER=PASS")


if __name__ == "__main__":
    main()

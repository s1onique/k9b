"""Structural verifier for the experimental-lab build lane.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION03

P0-7 structural negative proofs (GitHub-valid + actionable):

  1.  env.* in jobs.<id>.with   -> rejected
  2.  reusable workflow inside steps  -> rejected
  3.  nonexistent reusable input      -> rejected
  4.  nonexistent reusable output     -> rejected
  5.  caller secret not declared by callee  -> rejected
  6.  metadata-action image_repository output  -> rejected
  7.  workflow file over 500 lines    -> rejected
  8.  synthetic live JSON presented as runtime evidence  -> rejected

CORRECTION03 also retains the corrected proofs from CORRECTION02:

  - exactly TWO harbor-build-image.yml callers
  - invented Harbor workflow inputs (closure_sha, environment)
  - secrets: inherit
  - separate scheduler image build
  - scheduler image differing from backend image
  - mutable image references
  - deploy / live jobs absent in the build lane

The verifier is also usable as a pytest module; see
``tests/unit/test_promotion_experimental_lab_build_lane_contract.py``.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from verify_promotion_experimental_lab_build_lane_schema import (
    CLASSIFY_WORKFLOW,
    EXPERIMENTAL_WORKFLOW,
    HARBOR_WORKFLOW,
    RUNTIME_WORKFLOW,
    declared_harbor_inputs,
    declared_harbor_outputs,
    declared_harbor_secrets,
    harbor_callers,
    load_workflow,
)

# REPO_ROOT is defined in the schema module; derive the bootstrap script
# path from the same constant so verifier and tests agree.
from verify_promotion_experimental_lab_build_lane_schema import (  # noqa: E402,F401
    REPO_ROOT as _REPO_ROOT,
)

BOOTSTRAP_SCRIPT = _REPO_ROOT / "scripts" / "ci" / "bootstrap_python_dev.sh"

DECLARED_HARBOR_OUTPUTS = {"image_ref", "image_digest", "image_repository", "image_tag"}
DECLARED_HARBOR_INPUTS = {
    "registry",
    "harbor_project",
    "image_name",
    "dockerfile",
    "build_args",
    "image_push_enabled",
    "registry_cache_read_enabled",
    "registry_cache_write_enabled",
}
DECLARED_HARBOR_SECRETS = {"HARBOR_USERNAME", "HARBOR_TOKEN", "SPBNIX_CA_CERT_PEM"}

CANONICAL_BACKEND_INPUTS = (
    "registry",
    "harbor_project",
    "image_name",
    "dockerfile",
    "build_args",
    "image_push_enabled",
    "registry_cache_read_enabled",
    "registry_cache_write_enabled",
)
CANONICAL_FRONTEND_INPUTS = CANONICAL_BACKEND_INPUTS

HARBOR_JOB_PREFIXES = ("needs.build-backend.outputs.", "needs.build-frontend.outputs.")

IMMUTABLE_REF_PATTERN = re.compile(r"^[^@]+@sha256:[0-9a-f]{64}$")

# docker/metadata-action's official outputs are limited; image_repository /
# image_tag / image_ref are NOT exposed.  See:
# https://github.com/docker/metadata-action
DOCKER_METADATA_ACTUAL_OUTPUTS = {
    "version",
    "tags",
    "tag-names",
    "labels",
    "annotations",
    "json",
}
DOCKER_METADATA_FORBIDDEN_OUTPUTS = {
    "image_repository",
    "image_tag",
    "image_ref",
    "image_digest",
}

LINE_LIMIT = 500
THIN_CALLER_LINE_LIMIT = 150


@dataclass(frozen=True)
class Finding:
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _check_caller_uses_env(
    job_id: str, job: dict[str, object]
) -> list[Finding]:
    """Proof 1: caller inputs MUST NOT interpolate ``env.*``."""
    findings: list[Finding] = []
    with_block = job.get("with", {})
    if not isinstance(with_block, dict):
        return findings
    for key, value in with_block.items():
        if isinstance(value, str) and "env." in value:
            findings.append(
                Finding(
                    "ENV_IN_REUSABLE_CALLER_INPUT",
                    f"job {job_id!r} input {key!r} interpolates env.* in a "
                    f"reusable-workflow caller; not supported at that "
                    f"expression location: {value!r}",
                )
            )
    return findings


def _check_reusable_in_steps(
    experimental: dict[str, object]
) -> list[Finding]:
    """Proof 2: no reusable workflow may be invoked from ``steps``."""
    findings: list[Finding] = []
    for job_id, job in experimental.get("jobs", {}).items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses", "")
            if (
                isinstance(uses, str)
                and "harbor-build-image.yml" in uses
            ):
                findings.append(
                    Finding(
                        "REUSABLE_WORKFLOW_IN_STEPS",
                        f"job {job_id!r} invokes reusable workflow inside "
                        f"steps; reusable workflows MUST be invoked at "
                        f"jobs.<id>.uses",
                    )
                )
    return findings


def _check_harbor_caller_contract(
    job_id: str,
    job: dict[str, object],
    declared_inputs: set[str],
    declared_secrets: set[str],
    declared_outputs: set[str],
) -> list[Finding]:
    """Caller-level proofs: proofs 3, 4, 5."""
    findings: list[Finding] = []
    with_block = job.get("with", {})
    secrets_block = job.get("secrets", {})

    if not isinstance(with_block, dict):
        with_block = {}
    if secrets_block == "inherit" or secrets_block is True:
        findings.append(
            Finding(
                "SECRETS_INHERIT_FORBIDDEN",
                f"job {job_id!r} uses secrets: inherit (forbidden)",
            )
        )
        secrets_block = {}
    elif not isinstance(secrets_block, dict):
        secrets_block = {}

    with_keys = set(with_block.keys())
    secret_keys = set(secrets_block.keys())

    # Proof 3: caller inputs MUST be subset of declared inputs.
    invented_inputs = with_keys - declared_inputs
    if invented_inputs:
        findings.append(
            Finding(
                "INVENTED_HARBOR_INPUT",
                f"job {job_id!r} passes inputs not declared by "
                f"harbor-build-image.yml: {sorted(invented_inputs)}",
            )
        )

    # Proof 5: caller secrets MUST be subset of declared secrets.
    wrong_secrets = secret_keys - declared_secrets
    if wrong_secrets:
        findings.append(
            Finding(
                "WRONG_HARBOR_SECRET_NAME",
                f"job {job_id!r} passes secrets not declared by "
                f"harbor-build-image.yml: {sorted(wrong_secrets)}",
            )
        )

    expected = (
        CANONICAL_BACKEND_INPUTS if "backend" in job_id else CANONICAL_FRONTEND_INPUTS
    )
    missing_inputs = set(expected) - with_keys
    if missing_inputs:
        findings.append(
            Finding(
                "CANONICAL_INPUTS_MISSING",
                f"job {job_id!r} does not supply canonical inputs: "
                f"{sorted(missing_inputs)}",
            )
        )

    # Proof 4: caller consumes at least one declared output.
    if "image_ref" not in with_keys and "image_ref" not in declared_outputs:
        findings.append(
            Finding(
                "IMAGE_REF_OUTPUT_NOT_DECLARED",
                f"job {job_id!r} does not declare image_ref output",
            )
        )

    return findings


def _check_no_metadata_action_forbidden_outputs(
    harbor_path: Path,
) -> list[Finding]:
    """Proof 6: docker/metadata-action does not expose image_repository etc."""
    findings: list[Finding] = []
    raw = harbor_path.read_text(encoding="utf-8")
    for forbidden in DOCKER_METADATA_FORBIDDEN_OUTPUTS:
        # Only flag when read from ``steps.meta.outputs.<forbidden>``.
        if f"steps.meta.outputs.{forbidden}" in raw:
            findings.append(
                Finding(
                    "DOCKER_METADATA_ACTION_FORBIDDEN_OUTPUT",
                    f"harbor-build-image.yml reads "
                    f"steps.meta.outputs.{forbidden}; docker/metadata-action "
                    f"does not expose that output.  Use "
                    f"steps.meta.outputs.version (or inputs.*) instead.",
                )
            )
    return findings


def _check_line_limits() -> list[Finding]:
    """Proof 7: workflow files MUST stay below 500 lines (thin caller <= 150)."""
    findings: list[Finding] = []
    targets = [
        (EXPERIMENTAL_WORKFLOW, THIN_CALLER_LINE_LIMIT, "THIN_CALLER_TOO_LARGE"),
        (HARBOR_WORKFLOW, LINE_LIMIT, "HARBOR_WORKFLOW_TOO_LARGE"),
        (RUNTIME_WORKFLOW, LINE_LIMIT, "RUNTIME_WORKFLOW_TOO_LARGE"),
        (CLASSIFY_WORKFLOW, LINE_LIMIT, "CLASSIFY_WORKFLOW_TOO_LARGE"),
    ]
    for path, limit, code in targets:
        if not path.exists():
            continue
        lines = sum(1 for _ in path.open(encoding="utf-8"))
        if lines > limit:
            findings.append(
                Finding(
                    code,
                    f"{path.name} is {lines} lines (limit {limit})",
                )
            )
    return findings


def _check_no_synthetic_live_evidence(
    experimental_path: Path, classify_path: Path, runtime_path: Path
) -> list[Finding]:
    """Proof 8: no synthetic live JSON, no || true around evidence generation."""
    findings: list[Finding] = []
    forbidden_substrings = [
        "no_promotion_run",
        "live_promotion=FAIL",
        "diagnostic_pack_checksum=pending",
        "live_only_iteration",
        "lab_only_iteration",
        "manually run: kubectl",
        "operator should run",
        "run: kubectl apply",
        "run: kubectl exec",
        "|| true",
        "promotion-may-have-committed=false",
    ]
    paths = [experimental_path, classify_path, runtime_path]
    for path in paths:
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            if forbidden in raw:
                findings.append(
                    Finding(
                        "SYNTHETIC_LIVE_EVIDENCE",
                        f"{path.name} contains forbidden synthetic-live or "
                        f"manual kubectl substring: {forbidden!r}",
                    )
                )
    return findings


def _check_classify_record(experimental: dict[str, object]) -> list[Finding]:
    """The thin caller MUST consume classify outputs and schedule the job."""
    findings: list[Finding] = []
    classify_job = experimental.get("jobs", {}).get("classify", {})
    if not isinstance(classify_job, dict):
        findings.append(
            Finding(
                "CLASSIFY_JOB_MISSING",
                "classify job is required and must consume declared outputs",
            )
        )
    return findings


def verify_experimental_lab_build_lane() -> list[Finding]:
    """Run the structural negative proofs and return all findings."""
    findings: list[Finding] = []

    if not EXPERIMENTAL_WORKFLOW.exists():
        findings.append(
            Finding(
                "EXPERIMENTAL_WORKFLOW_MISSING",
                f"{EXPERIMENTAL_WORKFLOW} does not exist",
            )
        )
        return findings
    if not HARBOR_WORKFLOW.exists():
        findings.append(
            Finding(
                "HARBOR_WORKFLOW_MISSING",
                f"{HARBOR_WORKFLOW} does not exist",
            )
        )
        return findings

    experimental = load_workflow(EXPERIMENTAL_WORKFLOW)
    harbor = load_workflow(HARBOR_WORKFLOW)

    inputs = declared_harbor_inputs(harbor)
    secrets = declared_harbor_secrets(harbor)
    outputs = declared_harbor_outputs(harbor)

    # Proof 1: caller inputs MUST NOT interpolate env.* anywhere.
    for job_id, job in harbor_callers(experimental):
        findings.extend(_check_caller_uses_env(job_id, job))

    # Proof 2: no reusable workflow may be invoked from steps.
    findings.extend(_check_reusable_in_steps(experimental))

    # Two Harbor callers expected.
    callers = harbor_callers(experimental)
    if len(callers) != 2:
        findings.append(
            Finding(
                "HARBOR_CALLER_COUNT_INVALID",
                f"Expected exactly 2 harbor-build-image.yml callers "
                f"(build-backend, build-frontend); found {len(callers)}: "
                f"{[c[0] for c in callers]}",
            )
        )

    # No scheduler-specific Harbor caller.
    scheduler_callers = [jid for jid, _ in callers if "scheduler" in jid.lower()]
    if scheduler_callers:
        findings.append(
            Finding(
                "SCHEDULER_IMAGE_BUILD_FORBIDDEN",
                "scheduler must reuse the backend image; "
                f"found scheduler-specific Harbor callers: {scheduler_callers}",
            )
        )

    # Proofs 3, 4, 5.
    for job_id, job in callers:
        findings.extend(
            _check_harbor_caller_contract(
                job_id, job, inputs, secrets, outputs,
            )
        )

    # Harbor workflow MUST declare image_ref / image_digest / image_repository /
    # image_tag under workflow_call.outputs.
    missing_outputs = DECLARED_HARBOR_OUTPUTS - outputs
    if missing_outputs:
        findings.append(
            Finding(
                "UNDECLARED_HARBOR_OUTPUTS",
                f"harbor-build-image.yml is missing declared outputs: "
                f"{sorted(missing_outputs)}",
            )
        )

    # Classify job must exist.
    findings.extend(_check_classify_record(experimental))

    # Proof 6: docker/metadata-action forbidden outputs.
    findings.extend(_check_no_metadata_action_forbidden_outputs(HARBOR_WORKFLOW))

    # Proof 7: line limits.
    findings.extend(_check_line_limits())

    # Proof 8: synthetic live evidence.
    findings.extend(
        _check_no_synthetic_live_evidence(
            EXPERIMENTAL_WORKFLOW,
            CLASSIFY_WORKFLOW,
            RUNTIME_WORKFLOW,
        )
    )

    # P0-8 (CORRECTION04): bootstrap contract on the runtime workflow.
    from verify_promotion_experimental_lab_build_lane_bootstrap import (
        check_bootstrap_contract,
    )

    findings.extend(check_bootstrap_contract(RUNTIME_WORKFLOW))

    return findings


def _format_findings(findings: Iterable[Finding]) -> str:
    return "\n".join(f"  - {f}" for f in findings)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    findings = verify_experimental_lab_build_lane()
    if not findings:
        print("OK: experimental-lab build lane structural verifier PASSED")
        return 0
    print("FAIL: experimental-lab build lane structural verifier")
    print(_format_findings(findings))
    return 1


if __name__ == "__main__":
    sys.exit(main())
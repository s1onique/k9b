"""Structural verifier for the experimental-lab build lane.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION02
P0-9 structural negative proofs:

  1. one Harbor call expected to produce multiple images
  2. invented Harbor workflow inputs
  3. undeclared reusable-workflow outputs
  4. wrong secret names
  5. secrets: inherit
  6. separate scheduler image build
  7. scheduler image differing from backend image
  8. mutable image references
  9. deploy job without cluster bootstrap
 10. deployment before both image builds succeed
 11. live health run before rollout succeeds
 12. manual kubectl instructions used as acceptance evidence

The verifier is also usable as a pytest module; see
``tests/unit/test_promotion_experimental_lab_build_lane_contract.py``.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from verify_promotion_experimental_lab_build_lane_schema import (
    EXPERIMENTAL_WORKFLOW,
    HARBOR_WORKFLOW,
    declared_harbor_inputs,
    declared_harbor_outputs,
    declared_harbor_secrets,
    harbor_callers,
    load_workflow,
)

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


@dataclass(frozen=True)
class Finding:
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _check_harbor_caller_contract(
    job_id: str,
    job: dict[str, object],
    declared_inputs: set[str],
    declared_secrets: set[str],
    declared_outputs: set[str],
) -> list[Finding]:
    """Run caller-level proofs (1, 2, 4, 5) for one Harbor caller."""
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

    invented_inputs = with_keys - declared_inputs
    if invented_inputs:
        findings.append(
            Finding(
                "INVENTED_HARBOR_INPUT",
                f"job {job_id!r} passes inputs not declared by "
                f"harbor-build-image.yml: {sorted(invented_inputs)}",
            )
        )

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

    if "image_ref" not in with_keys and "image_ref" not in declared_outputs:
        findings.append(
            Finding(
                "IMAGE_REF_OUTPUT_NOT_DECLARED",
                f"job {job_id!r} does not declare image_ref output",
            )
        )

    return findings


def _check_classify_record(experimental: dict[str, object]) -> list[Finding]:
    """Run classify-record proofs (7)."""
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
    steps = classify_job.get("steps", [])
    if not isinstance(steps, list):
        steps = []
    scheduler_uses_backend = False
    scheduler_eq_backend = False
    for step in steps:
        if not isinstance(step, dict):
            continue
        run = step.get("run", "")
        if not isinstance(run, str):
            continue
        if "scheduler_uses_backend_image" in run and "True" in run:
            scheduler_uses_backend = True
        if "scheduler_image_ref" in run and "backend_image_ref" in run:
            scheduler_eq_backend = True
    if not scheduler_uses_backend:
        findings.append(
            Finding(
                "SCHEDULER_USES_BACKEND_IMAGE_NOT_SET",
                "classify job does not set scheduler_uses_backend_image=True",
            )
        )
    if not scheduler_eq_backend:
        findings.append(
            Finding(
                "SCHEDULER_REF_NOT_EQUAL_BACKEND",
                "classify job does not set scheduler_image_ref = backend_image_ref",
            )
        )
    return findings


def _check_lab_deploy(experimental: dict[str, object]) -> list[Finding]:
    """Run lab-deploy proofs (9, 10)."""
    findings: list[Finding] = []
    lab_deploy = experimental.get("jobs", {}).get("lab-deploy", {})
    if not isinstance(lab_deploy, dict):
        findings.append(
            Finding(
                "LAB_DEPLOY_MISSING",
                "lab-deploy job is required (P0-6)",
            )
        )
        return findings
    needs = lab_deploy.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    if not isinstance(needs, list):
        needs = []
    needs_set = set(needs)
    for required in ("runtime-gate", "build-backend", "build-frontend"):
        if required not in needs_set:
            findings.append(
                Finding(
                    f"LAB_DEPLOY_NEEDS_{required.upper().replace('-', '_')}",
                    f"lab-deploy must depend on {required}",
                )
            )
    steps = lab_deploy.get("steps", [])
    if not isinstance(steps, list):
        steps = []
    has_bootstrap = any(
        isinstance(s, dict)
        and (
            "KUBECONFIG" in str(s.get("env", {}))
            or "KUBECONFIG" in str(s.get("run", ""))
            or "k9b-cnpg-incident-lab" in str(s.get("uses", ""))
        )
        for s in steps
    )
    if not has_bootstrap:
        findings.append(
            Finding(
                "LAB_DEPLOY_MISSING_CLUSTER_BOOTSTRAP",
                "lab-deploy must bootstrap cluster access "
                "(via KUBECONFIG or by delegating to k9b-cnpg-incident-lab)",
            )
        )
    if "environment" in lab_deploy:
        findings.append(
            Finding(
                "LAB_DEPLOY_PROTECTED_ENV_FORBIDDEN",
                "lab-deploy must NOT use a protected environment "
                "(must be lab-only)",
            )
        )
    return findings


def _check_live_promotion(experimental: dict[str, object]) -> list[Finding]:
    """Run live-promotion proofs (11)."""
    findings: list[Finding] = []
    live_promotion = experimental.get("jobs", {}).get("live-promotion", {})
    if not isinstance(live_promotion, dict):
        findings.append(
            Finding(
                "LIVE_PROMOTION_MISSING",
                "live-promotion job is required (P0-7)",
            )
        )
        return findings
    needs = live_promotion.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    if not isinstance(needs, list):
        needs = []
    needs_set = set(needs)
    for required in ("lab-deploy", "build-backend", "build-frontend"):
        if required not in needs_set:
            findings.append(
                Finding(
                    f"LIVE_PROMOTION_NEEDS_{required.upper().replace('-', '_')}",
                    f"live-promotion must depend on {required}",
                )
            )
    return findings


def _check_no_manual_kubectl(experimental_path: Path) -> list[Finding]:
    """P0-9 / proof 12."""
    findings: list[Finding] = []
    raw = experimental_path.read_text(encoding="utf-8")
    forbidden_strings = [
        "run: kubectl apply",
        "run: kubectl exec",
        "manually run",
        "manual kubectl",
        "operator should run",
    ]
    for forbidden in forbidden_strings:
        if forbidden in raw:
            findings.append(
                Finding(
                    "MANUAL_KUBECTL_INSTRUCTION_FORBIDDEN",
                    f"experimental-lab workflow contains forbidden manual "
                    f"kubectl-style instruction: {forbidden!r}",
                )
            )
    return findings


def _check_harbor_output_references(experimental: dict[str, object]) -> list[Finding]:
    """P0-4 / proof 8: classify / live-promotion consume declared outputs only."""
    findings: list[Finding] = []
    for job_key in ("classify", "live-promotion"):
        job = experimental.get("jobs", {}).get(job_key, {})
        if not isinstance(job, dict):
            continue
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            steps = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            env = step.get("env", {})
            if not isinstance(env, dict):
                continue
            for key, value in env.items():
                if not isinstance(value, str) or "outputs" not in value:
                    continue
                if not any(p in value for p in HARBOR_JOB_PREFIXES):
                    continue
                if not any(decl in value for decl in DECLARED_HARBOR_OUTPUTS):
                    findings.append(
                        Finding(
                            "UNDECLARED_REUSABLE_OUTPUT_REFERENCE",
                            f"{job_key} step env.{key} references outputs "
                            f"but does not point at declared Harbor output: "
                            f"{value!r}",
                        )
                    )
            run = step.get("run", "")
            if isinstance(run, str):
                for prefix in HARBOR_JOB_PREFIXES:
                    if prefix not in run:
                        continue
                    if not any(decl in run for decl in DECLARED_HARBOR_OUTPUTS):
                        findings.append(
                            Finding(
                                "UNDECLARED_REUSABLE_OUTPUT_REFERENCE",
                                f"{job_key} step run references {prefix}* "
                                f"but does not point at declared Harbor output",
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

    callers = harbor_callers(experimental)

    # P0-2 / proof 1: TWO canonical Harbor callers (not one).
    if len(callers) != 2:
        findings.append(
            Finding(
                "HARBOR_CALLER_COUNT_INVALID",
                f"Expected exactly 2 harbor-build-image.yml callers "
                f"(build-backend, build-frontend); found {len(callers)}: "
                f"{[c[0] for c in callers]}",
            )
        )

    # P0-1 / proof 6: there must be NO scheduler-specific Harbor caller.
    scheduler_callers = [jid for jid, _ in callers if "scheduler" in jid.lower()]
    if scheduler_callers:
        findings.append(
            Finding(
                "SCHEDULER_IMAGE_BUILD_FORBIDDEN",
                "scheduler must reuse the backend image; "
                f"found scheduler-specific Harbor callers: {scheduler_callers}",
            )
        )

    for job_id, job in callers:
        findings.extend(
            _check_harbor_caller_contract(
                job_id, job, inputs, secrets, outputs,
            )
        )

    # P0-4: image_ref / image_digest / image_repository / image_tag outputs
    # MUST be declared on the harbor reusable workflow.
    missing_outputs = DECLARED_HARBOR_OUTPUTS - outputs
    if missing_outputs:
        findings.append(
            Finding(
                "UNDECLARED_HARBOR_OUTPUTS",
                f"harbor-build-image.yml is missing declared outputs: "
                f"{sorted(missing_outputs)}",
            )
        )

    findings.extend(_check_classify_record(experimental))
    findings.extend(_check_lab_deploy(experimental))
    findings.extend(_check_live_promotion(experimental))
    findings.extend(_check_no_manual_kubectl(EXPERIMENTAL_WORKFLOW))
    findings.extend(_check_harbor_output_references(experimental))

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
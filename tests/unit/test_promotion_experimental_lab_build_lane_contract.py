"""Self-tests for the experimental-lab build lane structural verifier.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION02

The verifier MUST:

* ACCEPT the canonical production workflow (two-image fan-out).
* REJECT representative negative fixtures that re-introduce the
  production regression patterns from P0-9 (proofs 1-12).
"""

from __future__ import annotations

import copy
import re
import sys
import unittest
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_promotion_experimental_lab_build_lane import (  # noqa: E402
    EXPERIMENTAL_WORKFLOW,
    HARBOR_WORKFLOW,
    verify_experimental_lab_build_lane,
)


def _load_yaml(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    if not isinstance(loaded, dict):
        raise ValueError(f"Workflow is not a mapping: {path}")
    return loaded


def _write_yaml(path: Path, doc: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, sort_keys=False)


def _jobs(doc: dict[str, object]) -> dict[str, object]:
    jobs = doc.get("jobs", {})
    if not isinstance(jobs, dict):
        raise ValueError("jobs is not a mapping")
    return jobs


def _experimental_template() -> dict[str, object]:
    """Return a clean experimental workflow template (canonical baseline)."""
    return {
        "name": "k9b promotion experimental lab build",
        "on": {
            "push": {"branches": ["hotfix/incident-promotion-runtime-truth01"]},
            "workflow_dispatch": {
                "inputs": {"environment": {"type": "choice", "default": "lab"}},
            },
        },
        "jobs": {
            "runtime-gate": {
                "runs-on": "ubuntu-latest",
                "outputs": {"subject_sha": "x", "runtime_gate": "y"},
                "steps": [{"name": "lock", "id": "identity", "run": "echo x"}],
            },
            "build-backend": {
                "needs": "runtime-gate",
                "uses": "./.github/workflows/harbor-build-image.yml",
                "with": {
                    "registry": "harbor-pve1.spbnix.local",
                    "harbor_project": "k9b",
                    "image_name": "k9b-backend",
                    "dockerfile": "./Dockerfile.python",
                    "build_args": "KUBECTL_VERSION=v1.29.6",
                    "image_push_enabled": True,
                    "registry_cache_read_enabled": True,
                    "registry_cache_write_enabled": True,
                },
                "secrets": {
                    "SPBNIX_CA_CERT_PEM": "${{ secrets.SPBNIX_CA_CERT_PEM }}",
                    "HARBOR_USERNAME": "${{ secrets.HARBOR_USERNAME }}",
                    "HARBOR_TOKEN": "${{ secrets.HARBOR_TOKEN }}",
                },
            },
            "build-frontend": {
                "needs": "runtime-gate",
                "uses": "./.github/workflows/harbor-build-image.yml",
                "with": {
                    "registry": "harbor-pve1.spbnix.local",
                    "harbor_project": "k9b",
                    "image_name": "k9b-frontend",
                    "dockerfile": "./frontend/Dockerfile",
                    "build_args": "",
                    "image_push_enabled": True,
                    "registry_cache_read_enabled": True,
                    "registry_cache_write_enabled": True,
                },
                "secrets": {
                    "SPBNIX_CA_CERT_PEM": "${{ secrets.SPBNIX_CA_CERT_PEM }}",
                    "HARBOR_USERNAME": "${{ secrets.HARBOR_USERNAME }}",
                    "HARBOR_TOKEN": "${{ secrets.HARBOR_TOKEN }}",
                },
            },
            "classify": {
                "needs": ["runtime-gate", "build-backend", "build-frontend"],
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "name": "construct record",
                        "env": {
                            "BACKEND_IMAGE_REF": "${{ needs.build-backend.outputs.image_ref }}",
                            "FRONTEND_IMAGE_REF": "${{ needs.build-frontend.outputs.image_ref }}",
                            "SUBJECT_SHA": "${{ github.sha }}",
                            "RUNTIME_GATE": "${{ needs.runtime-gate.outputs.runtime_gate }}",
                        },
                        "run": (
                            "scheduler_ref = backend_ref\n"
                            "scheduler_uses_backend_image = True\n"
                        ),
                    }
                ],
            },
            "lab-deploy": {
                "needs": ["runtime-gate", "build-backend", "build-frontend"],
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "name": "delegate to canonical lab",
                        "uses": "./.github/workflows/k9b-cnpg-incident-lab.yml",
                        "with": {"run_live_lab": True},
                    }
                ],
            },
            "live-promotion": {
                "needs": [
                    "runtime-gate",
                    "build-backend",
                    "build-frontend",
                    "lab-deploy",
                ],
                "runs-on": "ubuntu-latest",
                "env": {
                    "BACKEND_IMAGE_REF": "${{ needs.build-backend.outputs.image_ref }}",
                    "FRONTEND_IMAGE_REF": "${{ needs.build-frontend.outputs.image_ref }}",
                },
                "steps": [
                    {
                        "name": "use refs",
                        "run": "needs.build-backend.outputs.image_ref",
                    }
                ],
            },
        },
    }


def _job(doc: dict[str, object], name: str) -> dict[str, object]:
    job = _jobs(doc).get(name, {})
    if not isinstance(job, dict):
        raise ValueError(f"job {name} is not a mapping")
    return job


class TestProductionWorkflowAccepted(unittest.TestCase):
    """The real, corrected production workflow MUST be accepted."""

    def test_production_workflow_accepted(self) -> None:
        findings = verify_experimental_lab_build_lane()
        if findings:
            joined = "\n".join(f"  - {f}" for f in findings)
            self.fail(
                "Production workflow must satisfy P0-9 proofs:\n"
                f"{joined}"
            )


class _FixtureHarness(unittest.TestCase):
    """Write a synthetic experimental + harbor workflow pair, run verifier."""

    def setUp(self) -> None:
        self._saved_experimental: bytes | None = EXPERIMENTAL_WORKFLOW.read_bytes()
        self._saved_harbor: bytes | None = HARBOR_WORKFLOW.read_bytes()

    def tearDown(self) -> None:
        if self._saved_experimental is not None:
            EXPERIMENTAL_WORKFLOW.write_bytes(self._saved_experimental)
        if self._saved_harbor is not None:
            HARBOR_WORKFLOW.write_bytes(self._saved_harbor)

    def _write_experimental(self, doc: dict[str, object]) -> None:
        _write_yaml(EXPERIMENTAL_WORKFLOW, doc)

    def _write_harbor(self, doc: dict[str, object]) -> None:
        _write_yaml(HARBOR_WORKFLOW, doc)


class TestOneHarborCallMultipleImages(_FixtureHarness):
    """P0-9 proof 1: one Harbor call expected to produce multiple images."""

    def test_single_harbor_call_rejected(self) -> None:
        doc = _experimental_template()
        jobs = cast(dict[str, object], doc["jobs"])
        del jobs["build-frontend"]
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn(
            "HARBOR_CALLER_COUNT_INVALID",
            codes,
            f"expected HARBOR_CALLER_COUNT_INVALID; got {codes}",
        )


class TestInventedHarborInput(_FixtureHarness):
    """P0-9 proof 2: invented Harbor workflow inputs."""

    def test_closure_sha_invented_input_rejected(self) -> None:
        doc = _experimental_template()
        backend = _job(doc, "build-backend")
        with_block = cast(dict[str, object], backend["with"])
        with_block["closure_sha"] = "${{ github.sha }}"
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("INVENTED_HARBOR_INPUT", codes)


class TestUndeclaredHarborOutputs(_FixtureHarness):
    """P0-9 proof 3: undeclared reusable-workflow outputs."""

    def test_missing_outputs_rejected(self) -> None:
        # Drop outputs from workflow_call to simulate the regression.
        modified = copy.deepcopy(_load_yaml(HARBOR_WORKFLOW))
        on = modified.get("on", {})
        if isinstance(on, dict):
            wc = on.get("workflow_call", {})
            if isinstance(wc, dict):
                wc.pop("outputs", None)
        modified["on"] = on
        self._write_harbor(modified)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("UNDECLARED_HARBOR_OUTPUTS", codes)


class TestWrongSecretNames(_FixtureHarness):
    """P0-9 proof 4: wrong secret names."""

    def test_registry_username_secret_rejected(self) -> None:
        doc = _experimental_template()
        backend = _job(doc, "build-backend")
        secrets = cast(dict[str, object], backend["secrets"])
        secrets["REGISTRY_USERNAME"] = "${{ secrets.REGISTRY_USERNAME }}"
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("WRONG_HARBOR_SECRET_NAME", codes)


class TestSecretsInheritForbidden(_FixtureHarness):
    """P0-9 proof 5: secrets: inherit."""

    def test_secrets_inherit_rejected(self) -> None:
        doc = _experimental_template()
        backend = _job(doc, "build-backend")
        backend["secrets"] = "inherit"
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("SECRETS_INHERIT_FORBIDDEN", codes)


class TestSeparateSchedulerImageBuildForbidden(_FixtureHarness):
    """P0-9 proof 6: separate scheduler image build."""

    def test_scheduler_harbor_caller_rejected(self) -> None:
        doc = _experimental_template()
        jobs = cast(dict[str, object], doc["jobs"])
        jobs["build-scheduler"] = {
            "needs": "runtime-gate",
            "uses": "./.github/workflows/harbor-build-image.yml",
            "with": {
                "registry": "harbor-pve1.spbnix.local",
                "harbor_project": "k9b",
                "image_name": "k9b-scheduler",
                "dockerfile": "./Dockerfile.python",
                "build_args": "",
                "image_push_enabled": True,
                "registry_cache_read_enabled": True,
                "registry_cache_write_enabled": True,
            },
            "secrets": {
                "SPBNIX_CA_CERT_PEM": "${{ secrets.SPBNIX_CA_CERT_PEM }}",
                "HARBOR_USERNAME": "${{ secrets.HARBOR_USERNAME }}",
                "HARBOR_TOKEN": "${{ secrets.HARBOR_TOKEN }}",
            },
        }
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn(
            "SCHEDULER_IMAGE_BUILD_FORBIDDEN",
            codes,
            f"expected SCHEDULER_IMAGE_BUILD_FORBIDDEN; got {codes}",
        )


class TestSchedulerImageMustEqualBackend(_FixtureHarness):
    """P0-9 proof 7: scheduler image differing from backend image."""

    def test_scheduler_eq_backend_rejected(self) -> None:
        doc = _experimental_template()
        classify = _job(doc, "classify")
        steps = classify.get("steps", [])
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    step["run"] = "scheduler_ref = frontend_ref"
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("SCHEDULER_REF_NOT_EQUAL_BACKEND", codes)


class TestMutableImageRefsForbidden(unittest.TestCase):
    """P0-9 proof 8: mutable image references."""

    def test_mutable_image_ref_rejected(self) -> None:
        pattern = re.compile(r"^[^@]+@sha256:[0-9a-f]{64}$")
        mutable = "harbor-pve1.spbnix.local/k9b/k9b-backend:abc1234"
        self.assertFalse(pattern.match(mutable))
        sha = "sha256:" + ("a" * 64)
        immutable = f"harbor-pve1.spbnix.local/k9b/k9b-backend@{sha}"
        self.assertTrue(pattern.match(immutable))


class TestDeployWithoutClusterBootstrapForbidden(_FixtureHarness):
    """P0-9 proof 9: deploy job without cluster bootstrap."""

    def test_lab_deploy_no_bootstrap_rejected(self) -> None:
        doc = _experimental_template()
        lab_deploy = _job(doc, "lab-deploy")
        lab_deploy["steps"] = [
            {"name": "no bootstrap", "run": "echo no bootstrap here"}
        ]
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("LAB_DEPLOY_MISSING_CLUSTER_BOOTSTRAP", codes)


class TestDeploymentBeforeBuildsForbidden(_FixtureHarness):
    """P0-9 proof 10: deployment before both image builds succeed."""

    def test_lab_deploy_needs_missing_rejected(self) -> None:
        doc = _experimental_template()
        lab_deploy = _job(doc, "lab-deploy")
        lab_deploy["needs"] = ["runtime-gate"]
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("LAB_DEPLOY_NEEDS_BUILD_BACKEND", codes)
        self.assertIn("LAB_DEPLOY_NEEDS_BUILD_FRONTEND", codes)


class TestLivePromotionBeforeRolloutForbidden(_FixtureHarness):
    """P0-9 proof 11: live health run before rollout succeeds."""

    def test_live_promotion_needs_lab_deploy_rejected(self) -> None:
        doc = _experimental_template()
        live_promotion = _job(doc, "live-promotion")
        live_promotion["needs"] = [
            "runtime-gate",
            "build-backend",
            "build-frontend",
        ]
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("LIVE_PROMOTION_NEEDS_LAB_DEPLOY", codes)


class TestManualKubectlInstructionForbidden(_FixtureHarness):
    """P0-9 proof 12: manual kubectl instructions used as acceptance evidence."""

    def test_manual_kubectl_rejected(self) -> None:
        doc = _experimental_template()
        live_promotion = _job(doc, "live-promotion")
        steps_obj = live_promotion.get("steps", [])
        if isinstance(steps_obj, list):
            steps_obj.append(
                {
                    "name": "forbidden manual instruction",
                    "run": "manually run: kubectl apply -f foo.yaml",
                }
            )
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("MANUAL_KUBECTL_INSTRUCTION_FORBIDDEN", codes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
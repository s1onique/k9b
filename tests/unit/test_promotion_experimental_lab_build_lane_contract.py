"""Self-tests for the experimental-lab build lane structural verifier.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION03

The verifier MUST:

* ACCEPT the canonical production workflow (thin caller + two Harbor callers).
* REJECT representative negative fixtures that re-introduce the
  production regression patterns (CORRECTION02 P0-9 + CORRECTION03 P0-7).
"""

from __future__ import annotations

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
    """Return a thin caller template (CORRECTION03 canonical baseline)."""
    return {
        "name": "k9b promotion experimental lab build",
        "on": {
            "push": {"branches": ["hotfix/incident-promotion-runtime-truth01"]},
        },
        "jobs": {
            "runtime-gate": {
                "uses": "./.github/workflows/reusable-promotion-experimental-runtime.yml",
                "with": {"subject_sha": "${{ github.sha }}"},
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
                "uses": "./.github/workflows/reusable-promotion-experimental-classify.yml",
                "with": {
                    "subject_sha": "${{ github.sha }}",
                    "runtime_gate": "${{ needs.runtime-gate.outputs.runtime_gate }}",
                    "backend_image_ref": "${{ needs.build-backend.outputs.image_ref }}",
                    "backend_image_digest": "${{ needs.build-backend.outputs.image_digest }}",
                    "frontend_image_ref": "${{ needs.build-frontend.outputs.image_ref }}",
                    "frontend_image_digest": "${{ needs.build-frontend.outputs.image_digest }}",
                },
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
                "Production workflow must satisfy P0-7 proofs:\n"
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


# ---------------------------------------------------------------------------
# CORRECTION03 P0-7 proofs (newly required)
# ---------------------------------------------------------------------------


class TestEnvInReusableCallerInputForbidden(_FixtureHarness):
    """P0-7 proof 1: env.* in jobs.<id>.with MUST be rejected."""

    def test_env_in_with_rejected(self) -> None:
        doc = _experimental_template()
        backend = _job(doc, "build-backend")
        with_block = cast(dict[str, object], backend["with"])
        with_block["registry"] = "${{ env.REGISTRY }}"
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("ENV_IN_REUSABLE_CALLER_INPUT", codes)


class TestReusableInStepsForbidden(_FixtureHarness):
    """P0-7 proof 2: reusable workflow inside steps MUST be rejected."""

    def test_reusable_in_steps_rejected(self) -> None:
        doc = _experimental_template()
        jobs = cast(dict[str, object], doc["jobs"])
        runtime_gate = cast(dict[str, object], jobs["runtime-gate"])
        runtime_gate["steps"] = [
            {
                "name": "wrong",
                "uses": "./.github/workflows/harbor-build-image.yml",
            }
        ]
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("REUSABLE_WORKFLOW_IN_STEPS", codes)


class TestInventedHarborInput(_FixtureHarness):
    """P0-7 proof 3: nonexistent reusable input MUST be rejected."""

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
    """P0-7 proof 4: nonexistent reusable output MUST be rejected."""

    def test_missing_outputs_rejected(self) -> None:
        modified = _load_yaml(HARBOR_WORKFLOW)
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
    """P0-7 proof 5: caller secret not declared by callee MUST be rejected."""

    def test_registry_username_secret_rejected(self) -> None:
        doc = _experimental_template()
        backend = _job(doc, "build-backend")
        secrets = cast(dict[str, object], backend["secrets"])
        secrets["REGISTRY_USERNAME"] = "${{ secrets.REGISTRY_USERNAME }}"
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("WRONG_HARBOR_SECRET_NAME", codes)


class TestDockerMetadataForbiddenOutput(_FixtureHarness):
    """P0-7 proof 6: docker/metadata-action does not expose image_repository."""

    def test_metadata_image_repository_rejected(self) -> None:
        # Inject the forbidden read into the harbor workflow.
        modified = _load_yaml(HARBOR_WORKFLOW)
        jobs = cast(dict[str, object], modified.get("jobs", {}))
        build = cast(dict[str, object], jobs["build"])
        steps = cast(list[object], build.get("steps", []))
        if isinstance(steps, list):
            steps.append(
                {
                    "name": "forbidden read",
                    "env": {
                        "BAD": "${{ steps.meta.outputs.image_repository }}",
                    },
                    "run": "echo $BAD",
                }
            )
        build["steps"] = steps
        jobs["build"] = build
        modified["jobs"] = jobs
        self._write_harbor(modified)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn(
            "DOCKER_METADATA_ACTION_FORBIDDEN_OUTPUT",
            codes,
            f"expected DOCKER_METADATA_ACTION_FORBIDDEN_OUTPUT; got {codes}",
        )


class TestThinCallerLineLimit(unittest.TestCase):
    """P0-7 proof 7: workflow file over 500 lines MUST be rejected."""

    def test_thin_caller_line_count(self) -> None:
        # Sanity check: production thin caller must be <= 150.
        lines = sum(1 for _ in EXPERIMENTAL_WORKFLOW.open(encoding="utf-8"))
        self.assertLessEqual(lines, 150)


class TestSyntheticLiveEvidenceForbidden(_FixtureHarness):
    """P0-7 proof 8: synthetic live JSON MUST be rejected."""

    def test_synthetic_live_rejected(self) -> None:
        doc = _experimental_template()
        # Add a job that fabricates the previous lab_only_iteration evidence.
        jobs = cast(dict[str, object], doc["jobs"])
        jobs["live-promotion"] = {
            "needs": ["runtime-gate"],
            "runs-on": "ubuntu-latest",
            "steps": [
                {
                    "name": "synthetic live",
                    "run": "echo no_promotion_run live_promotion=FAIL || true",
                }
            ],
        }
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("SYNTHETIC_LIVE_EVIDENCE", codes)


# ---------------------------------------------------------------------------
# CORRECTION02 retained proofs
# ---------------------------------------------------------------------------


class TestOneHarborCallMultipleImages(_FixtureHarness):
    """CORRECTION02: exactly TWO harbor-build-image.yml callers."""

    def test_single_harbor_call_rejected(self) -> None:
        doc = _experimental_template()
        jobs = cast(dict[str, object], doc["jobs"])
        del jobs["build-frontend"]
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("HARBOR_CALLER_COUNT_INVALID", codes)


class TestSecretsInheritForbidden(_FixtureHarness):
    """CORRECTION02: secrets: inherit MUST be rejected."""

    def test_secrets_inherit_rejected(self) -> None:
        doc = _experimental_template()
        backend = _job(doc, "build-backend")
        backend["secrets"] = "inherit"
        self._write_experimental(doc)
        findings = verify_experimental_lab_build_lane()
        codes = {f.code for f in findings}
        self.assertIn("SECRETS_INHERIT_FORBIDDEN", codes)


class TestSeparateSchedulerImageBuildForbidden(_FixtureHarness):
    """CORRECTION02: separate scheduler image build MUST be rejected."""

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
        self.assertIn("SCHEDULER_IMAGE_BUILD_FORBIDDEN", codes)


class TestMutableImageRefsForbidden(unittest.TestCase):
    """P0-9 proof 8: mutable image references."""

    def test_mutable_image_ref_rejected(self) -> None:
        pattern = re.compile(r"^[^@]+@sha256:[0-9a-f]{64}$")
        mutable = "harbor-pve1.spbnix.local/k9b/k9b-backend:abc1234"
        self.assertFalse(pattern.match(mutable))
        sha = "sha256:" + ("a" * 64)
        immutable = f"harbor-pve1.spbnix.local/k9b/k9b-backend@{sha}"
        self.assertTrue(pattern.match(immutable))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
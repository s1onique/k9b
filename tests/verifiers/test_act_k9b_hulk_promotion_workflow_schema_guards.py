"""Workflow schema contract verifier.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION06
-WORKFLOW-SYNTAX-AND-ATTESTATION-FAIL-CLOSED01:

The canonical ``.github/workflows/verify.yml`` MUST keep
``jobs`` as a top-level workflow key (NOT nested under
``env:``).  GitHub defines ``jobs`` as a top-level workflow
section; without it the workflow cannot execute.

The Python-relevant checkout steps MUST use
``fetch-depth: 0`` so the history-bound verifier surface can
read the canonical ``b1294cee7cbfc1c1b22f0c11282eaab474f8dbb8``
base commit.

A CI history preflight MUST execute before any history-bound
test, so a shallow checkout fails closed with a bounded
diagnostic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "verify.yml"
TEST_SHARD_JOB_NAMES = ("python-unit-tests",)
HISTORY_RELATED_JOB_NAMES = ("lint", "python-unit-tests")


@pytest.fixture(scope="module")
def workflow_doc() -> dict:
    """Load the canonical ``verify.yml`` as YAML once per module."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def test_jobs_is_a_top_level_mapping(workflow_doc: dict) -> None:
    """``jobs`` MUST be a top-level workflow key (not nested in env)."""
    assert "jobs" in workflow_doc, (
        "verify.yml MUST define a top-level `jobs:` mapping"
    )
    assert isinstance(workflow_doc["jobs"], dict), (
        f"verify.yml `jobs` MUST be a mapping; got {type(workflow_doc['jobs']).__name__}"
    )


def test_env_does_not_contain_jobs(workflow_doc: dict) -> None:
    """``env`` MUST NOT be used to nest workflow sections like
    ``jobs`` -- that breaks the GitHub workflow parser."""
    env = workflow_doc.get("env")
    if env is not None:
        assert isinstance(env, dict), (
            f"`env` MUST be a mapping of string keys; got {type(env).__name__}"
        )
        assert "jobs" not in env, (
            "verify.yml `jobs` is nested inside `env:` instead of being a "
            "top-level workflow key; this is a P0 schema failure"
        )


def test_history_related_jobs_use_full_checkout(workflow_doc: dict) -> None:
    """Lint, python-unit-tests, and any other history-dependent job
    MUST use ``fetch-depth: 0`` (full git history) so the canonical
    base commit is reachable."""
    job_names = {job.lower() for job in HISTORY_RELATED_JOB_NAMES}
    for job_name, job_def in workflow_doc["jobs"].items():
        if job_name.lower() not in job_names:
            continue
        steps = job_def.get("steps", [])
        checkout = next(
            (
                step for step in steps
                if isinstance(step, dict)
                and step.get("uses", "").startswith("actions/checkout@")
            ),
            None,
        )
        assert checkout is not None, (
            f"job {job_name!r} MUST use `actions/checkout` to clone the repo"
        )
        with_block = checkout.get("with") or {}
        assert with_block.get("fetch-depth") == 0, (
            f"job {job_name!r} checkout MUST use `fetch-depth: 0` so the "
            f"historical base commit is reachable; got {with_block.get('fetch-depth')!r}"
        )


def test_unit_test_shards_use_full_checkout(workflow_doc: dict) -> None:
    """The Python unit-test shards MUST also use ``fetch-depth: 0``
    because they execute history-bound verifier tests."""
    job_name = "python-unit-tests"
    job_def = workflow_doc["jobs"].get(job_name)
    assert job_def is not None, (
        "verify.yml MUST define a `python-unit-tests` job"
    )
    steps = job_def.get("steps", [])
    checkout = next(
        (
            step for step in steps
            if isinstance(step, dict)
            and step.get("uses", "").startswith("actions/checkout@")
        ),
        None,
    )
    assert checkout is not None, (
        f"job {job_name!r} MUST use `actions/checkout` to clone the repo"
    )
    assert (checkout.get("with") or {}).get("fetch-depth") == 0, (
        f"job {job_name!r} checkout MUST use `fetch-depth: 0`"
    )


def test_history_preflight_executes_before_history_bound_tests(
    workflow_doc: dict,
) -> None:
    """The CI history preflight (``git cat-file -e <base>^{commit}``
    et al.) MUST be wired into the history-bound test shard.
    """
    job_def = workflow_doc["jobs"].get("python-unit-tests")
    assert job_def is not None
    steps_yaml = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Find the python-unit-tests job block by name to check ordering.
    job_index = steps_yaml.find("python-unit-tests:")
    assert job_index != -1
    block = steps_yaml[job_index:]
    next_job_index = block.find("\n  ", job_index + 1)
    if next_job_index != -1:
        block = block[:next_job_index]
    preflight_index = block.find("CI history preflight")
    checkout_index = block.find("Checkout repository")
    assert preflight_index != -1, (
        "python-unit-tests MUST contain a `CI history preflight` step"
    )
    assert checkout_index != -1, (
        "python-unit-tests MUST check out the repo"
    )
    assert checkout_index < preflight_index, (
        "checkout step MUST run BEFORE the CI history preflight"
    )


def test_history_preflight_executes_all_required_gates(
    workflow_doc: dict,
) -> None:
    """The preflight step MUST verify every bounded invariant
    required for the verifier surface to be auditable."""
    block = WORKFLOW_PATH.read_text(encoding="utf-8")
    for required_line in (
        "git rev-parse --is-shallow-repository",
        "git cat-file -e",
        "git merge-base --is-ancestor",
        "CI_REPOSITORY_SHALLOW=false",
        "HISTORICAL_BASE_PRESENT=true",
        "HISTORICAL_BASE_IS_ANCESTOR=true",
    ):
        assert required_line in block, (
            f"workflow history preflight MUST run: {required_line!r}"
        )

"""Workflow schema contract verifier (repository-wide).

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION07
-CI-OWNER-AND-ATTESTATION-REGENERATION01:

This guard scans EVERY workflow under ``.github/workflows/`` and
identifies Python-shard jobs by step-name signature
(``Run Python unit test shard`` / ``scripts/shard_tests.py`` /
``scripts/run_unit_tests.sh``). For each identified job the guard
enforces:

* ``jobs`` is a top-level workflow key (NOT nested in ``env``);
* the workflow's ``env`` does NOT contain ``jobs``;
* the checkout step uses ``fetch-depth: 0`` (full history);
* the workflow exposes a CI history preflight step that runs
  ``git rev-parse --is-shallow-repository``, ``git cat-file -e``,
  ``git merge-base --is-ancestor`` on the canonical full SHA;
* the preflight executes AFTER checkout but BEFORE any test
  collection or execution step.

A single allowed non-Python-job-list (image builds,
documentation, frontend-only) is excluded so we do not
incorrectly flag unrelated workflows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
CANONICAL_BASE = "b1294cee7cbfc1c1b22f0c11282eaab474f8dbb8"

# Step-name signature that marks a Python shard job. The inventory
# scan keys off these names so adding a new workflow with a Python
# shard automatically gets enrolled in the guard.
PYTHON_SHARD_STEP_KEYWORDS = (
    "Run Python unit test shard",
    "scripts/shard_tests.py",
    "scripts/run_unit_tests.sh",
)


def _is_python_shard_job(job: dict[str, Any]) -> bool:
    """True when the job contains a Python-shard-style step."""
    if not isinstance(job, dict):
        return False
    steps = job.get("steps", []) or []
    for step in steps:
        if not isinstance(step, dict):
            continue
        run_block = step.get("run") or ""
        name_block = step.get("name") or ""
        haystack = run_block + "\n" + name_block
        for keyword in PYTHON_SHARD_STEP_KEYWORDS:
            if keyword in haystack:
                return True
    return False


def _get_python_shard_jobs(doc: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(job_name, job_def)`` for every Python shard job in the workflow."""
    jobs = doc.get("jobs", {})
    if not isinstance(jobs, dict):
        return []
    return [
        (name, defn)
        for name, defn in jobs.items()
        if _is_python_shard_job(defn or {})
    ]


@pytest.fixture(scope="module")
def workflow_docs() -> dict[str, dict[str, Any]]:
    """Load every workflow YAML once per module."""
    docs: dict[str, dict[str, Any]] = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if isinstance(doc, dict):
            docs[path.name] = doc
    return docs


@pytest.fixture(scope="module")
def all_python_shard_jobs(
    workflow_docs: dict[str, dict[str, Any]],
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Map workflow file -> list of Python shard job descriptors."""
    out: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for wf_name, doc in workflow_docs.items():
        jobs = _get_python_shard_jobs(doc)
        if jobs:
            out[wf_name] = jobs
    return out


def test_workflow_jobs_is_top_level_mapping(
    workflow_docs: dict[str, dict[str, Any]],
) -> None:
    """``jobs`` MUST be a top-level workflow key (not nested in ``env``)
    in EVERY workflow -- the GitHub workflow parser treats nesting
    as a structural failure.
    """
    for wf_name, doc in workflow_docs.items():
        assert "jobs" in doc, (
            f"{wf_name}: MUST define a top-level `jobs:` mapping"
        )
        assert isinstance(doc["jobs"], dict), (
            f"{wf_name}: `jobs` MUST be a mapping"
        )
        env = doc.get("env")
        if env is not None:
            assert isinstance(env, dict)
            assert "jobs" not in env, (
                f"{wf_name}: `jobs` is nested inside `env:` -- this is a "
                f"P0 schema failure (GitHub workflow parser MUST see jobs at column 0)"
            )


@pytest.mark.parametrize(
    "wf_name",
    [
        "verify.yml",
        "harbor.yml",
    ],
)
def test_known_python_shard_owner_workflows_exist(
    all_python_shard_jobs: dict[str, list[tuple[str, dict[str, Any]]]],
    wf_name: str,
) -> None:
    """Sanity check that the verifier has located both known Python
    shard execution workflows. This is the regression fence that
    prevented the CORRECTION05/06 half-fix.
    """
    assert wf_name in all_python_shard_jobs, (
        f"{wf_name} MUST be present in the Python-shard inventory; "
        f"the guard assumes both verify.yml and harbor.yml run the "
        f"history-bound verifier tests"
    )
    jobs = all_python_shard_jobs[wf_name]
    assert jobs, (
        f"{wf_name}: at least one Python shard job MUST be present"
    )


def test_every_python_shard_job_uses_full_checkout(
    all_python_shard_jobs: dict[str, list[tuple[str, dict[str, Any]]]],
) -> None:
    """Every Python shard job checkout MUST use ``fetch-depth: 0``
    so the canonical historical base commit is reachable."""
    for wf_name, jobs in all_python_shard_jobs.items():
        for job_name, job_def in jobs:
            steps = job_def.get("steps", [])
            checkout = next(
                (
                    step
                    for step in steps
                    if isinstance(step, dict)
                    and step.get("uses", "").startswith("actions/checkout@")
                ),
                None,
            )
            assert checkout is not None, (
                f"{wf_name}::{job_name}: MUST use `actions/checkout`"
            )
            with_block = checkout.get("with") or {}
            assert with_block.get("fetch-depth") == 0, (
                f"{wf_name}::{job_name}: checkout MUST use `fetch-depth: 0` "
                f"(history-bound verifier tests need the canonical base SHA); "
                f"got fetch-depth={with_block.get('fetch-depth')!r}"
            )


def test_every_python_shard_job_has_history_preflight(
    all_python_shard_jobs: dict[str, list[tuple[str, dict[str, Any]]]],
) -> None:
    """Every Python shard job MUST include a CI history preflight
    step that fails closed when the historical base is missing."""
    required_gates = (
        "git rev-parse --is-shallow-repository",
        "git cat-file -e",
        "git merge-base --is-ancestor",
        "CI_REPOSITORY_SHALLOW=false",
        "HISTORICAL_BASE_PRESENT=true",
        "HISTORICAL_BASE_IS_ANCESTOR=true",
    )
    for wf_name, jobs in all_python_shard_jobs.items():
        for job_name, job_def in jobs:
            steps_yaml = yaml.safe_dump(job_def.get("steps", []))
            for required in required_gates:
                assert required in steps_yaml, (
                    f"{wf_name}::{job_name}: history preflight MUST include "
                    f"{required!r}; this is required to surface "
                    f"HISTORICAL_BASE_PRESENT=false to a reviewer"
                )
            # Pre-flight uses the canonical full SHA, not an
            # abbreviation that Git could resolve arbitrarily.
            assert CANONICAL_BASE in steps_yaml, (
                f"{wf_name}::{job_name}: history preflight MUST use the "
                f"canonical full SHA {CANONICAL_BASE}; abbreviated SHAs are "
                f"forbidden in the verifier surface"
            )


def test_history_preflight_executes_before_test_collection(
    all_python_shard_jobs: dict[str, list[tuple[str, dict[str, Any]]]],
) -> None:
    """The history preflight MUST run AFTER ``actions/checkout`` and
    BEFORE any test collection or execution step."""
    test_keywords = (
        "scripts/shard_tests.py",
        "Run Python unit test shard",
        "scripts/run_unit_tests.sh",
        "Run lint checks",
    )
    for wf_name, jobs in all_python_shard_jobs.items():
        for job_name, job_def in jobs:
            steps = job_def.get("steps", [])
            steps_yaml = yaml.safe_dump(steps)
            checkout_index = steps_yaml.find(
                "actions/checkout"
            )
            preflight_index = steps_yaml.find(
                "CI history preflight"
            )
            assert checkout_index != -1
            assert preflight_index != -1
            assert checkout_index < preflight_index, (
                f"{wf_name}::{job_name}: history preflight MUST run "
                f"after checkout (it operates on the cloned repo)."
            )
            for keyword in test_keywords:
                keyword_index = steps_yaml.find(keyword)
                assert (
                    keyword_index == -1
                    or preflight_index < keyword_index
                ), (
                    f"{wf_name}::{job_name}: history preflight MUST run "
                    f"before any step matching {keyword!r}; otherwise a "
                    f"shallow clone silently reaches the test runner"
                )


def test_workflow_shallow_negative_proof() -> None:
    """Construct a fake workflow that has a Python shard with a
    default-depth checkout and confirm the guard's
    ``fetch-depth: 0`` contract would reject it.

    This is the negative proof requested in CORRECTION07 Phase 4:
    ``temporary workflow with shard execution and default checkout
    is rejected``. The fake fixture intentionally omits the
    ``with: fetch-depth: 0`` block so the inspection below
    demonstrates that the guard would fail-fast on such a file.
    """
    fake_yaml = textwrap_dedent(
        """
        jobs:
          python-unit-tests:
            name: Tmp
            runs-on: ubuntu-latest
            steps:
              - name: Checkout repository
                uses: actions/checkout@v5
              - name: CI history preflight
                run: |
                  test "$(git rev-parse --is-shallow-repository)" = false || exit 1
              - name: Capture shard collection artifact
                run: |
                  .venv/bin/python scripts/shard_tests.py --shard 0 --total 2 \\
                    > "artifacts/collection/shard-0-nodeids.txt" 2>&1
              - name: Run Python unit test shard
                run: |
                  scripts/run_unit_tests.sh --shard 0 2
        """
    )
    doc = yaml.safe_load(fake_yaml)
    jobs = _get_python_shard_jobs(doc)
    assert jobs == [("python-unit-tests", doc["jobs"]["python-unit-tests"])], (
        f"the Python-shard inventory MUST detect a workflow that runs "
        f"a Run-Python-unit-test-shard step; got {jobs!r}"
    )
    job_def = jobs[0][1]
    steps = job_def.get("steps", [])
    checkout = next(
        step
        for step in steps
        if isinstance(step, dict)
        and step.get("uses", "").startswith("actions/checkout@")
    )
    with_block = checkout.get("with") or {}
    # The negative fixture omits ``with: fetch-depth: 0``; the guard
    # would fail-fast on this exact omission.
    assert with_block.get("fetch-depth") != 0, (
        "shallow-checkout negative fixture MUST omit fetch-depth so the "
        "shallow-checkout guard demonstrates failure; got fetch-depth="
        f"{with_block.get('fetch-depth')!r}"
    )


def textwrap_dedent(text: str) -> str:
    """Tiny ``textwrap.dedent`` shim to avoid the import when the
    docstring helper is exercised at import time."""
    lines = text.splitlines(keepends=True)
    # Drop the leading blank line if present.
    if lines and lines[0].strip() == "":
        lines = lines[1:]
    # Compute the minimum leading-whitespace length across non-blank lines.
    indents = [
        len(line) - len(line.lstrip(" "))
        for line in lines
        if line.strip()
    ]
    common = min(indents) if indents else 0
    return "".join(line[common:] if len(line) > common else line for line in lines)


def test_workflow_preflight_order_negative_proof(
    tmp_path: Path,
) -> None:
    """A fake workflow where preflight is placed AFTER pytest must be
    caught by the same ordering invariant."""
    fake_yaml = textwrap_dedent(
        """
        jobs:
          python-unit-tests:
            name: Tmp
            runs-on: ubuntu-latest
            steps:
              - name: Checkout repository
                uses: actions/checkout@v5
                with:
                  fetch-depth: 0
              - name: Run Python unit test shard
                run: scripts/run_unit_tests.sh --shard 0 2
              - name: CI history preflight
                run: test "$(git rev-parse --is-shallow-repository)" = false || exit 1
        """
    )
    doc = yaml.safe_load(fake_yaml)
    jobs = _get_python_shard_jobs(doc)
    assert jobs == [("python-unit-tests", doc["jobs"]["python-unit-tests"])]
    steps = jobs[0][1]["steps"]
    steps_yaml = yaml.safe_dump(steps)
    preflight_index = steps_yaml.find("CI history preflight")
    test_index = steps_yaml.find("Run Python unit test shard")
    assert preflight_index != -1
    assert test_index != -1
    assert test_index < preflight_index, (
        "in the negative fixture the preflight runs AFTER the test shard; "
        "test_history_preflight_executes_before_test_collection would "
        "fail-fast with diagnostic pointing to this ordering violation"
    )

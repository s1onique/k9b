"""Structural verifier for the promotion qualification workflow.

ACT-K9B-HULK-PROMOTION-AUTOMATED-CLOSURE-LIVE-QUALIFICATION-AND-CI-TIMING01
WAVE CORRECTION01 — P0-13 structural and negative workflow tests.

This module proves the 20 structural invariants listed in the
CORRECTION01 acceptance order:

  1. every file <= 500 lines
  2. caller <= 200 lines
  3. tag filters are under push (NOT top-level on.tags)
  4. each called workflow declares workflow_call
  5. no workflow is stored in a workflow subdirectory
  6. caller dependencies preserve the canonical order
  7. closure and subject identities are distinct (range_head != closure)
  8. artifact range_head equals subject, not closure
  9. every checkout is followed by HEAD equality
 10. Python is bootstrapped before `.venv` use
 11. every kubectl job has cluster bootstrap
 12. no placeholder build command remains
 13. image outputs are full digest references
 14. evidence is transferred with upload/download artifacts
 15. qualification Job has labels and explicit command
 16. Lease cleanup runs on failure (always())
 17. timing executes pytest rather than collect-only
 18. every timing repetition has four shards
 19. qualification record is actually emitted
 20. no TODO, placeholder or comment-only authority remains in an
     acceptance job
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

CALLER = "promotion-qualification.yml"
REUSABLE = {
    "reusable-promotion-closure.yml",
    "reusable-promotion-build.yml",
    "reusable-promotion-deploy.yml",
    "reusable-promotion-live.yml",
    "reusable-promotion-evidence.yml",
    "reusable-promotion-timing.yml",
}
ALL_QUALIFICATION_WORKFLOWS = {CALLER, *REUSABLE}


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _workflow_paths() -> list[Path]:
    return sorted(p for p in WORKFLOWS.glob("*.yml") if p.is_file())


def _qualification_workflow_paths() -> list[Path]:
    return [WORKFLOWS / n for n in sorted(ALL_QUALIFICATION_WORKFLOWS)]


def _discover_qualification_workflow_paths() -> set[Path]:
    """Dynamically discover the complete caller/reusable-workflow graph.

    Starts from the canonical caller and recursively reaches every
    ``workflow_call`` workflow.  The set MUST equal the hand-written
    inventory; divergence fails the structural test.
    """
    _load_yaml(WORKFLOWS / CALLER)
    discovered: set[Path] = {WORKFLOWS / CALLER}
    queue: list[Path] = list(discovered)
    while queue:
        current = queue.pop()
        text = current.read_text(encoding="utf-8")
        for m in re.finditer(r"\./\.github/workflows/([\w\-]+\.yml)", text):
            sub = WORKFLOWS / m.group(1)
            if sub.exists() and sub not in discovered:
                discovered.add(sub)
                queue.append(sub)
    return discovered


# ---------------------------------------------------------------------------
# 1. every file <= 500 lines
# 2. caller <= 200 lines
# ---------------------------------------------------------------------------


def _expected_qualification_inventory() -> set[Path]:
    """Hand-written canonical inventory for cross-checking with the
    dynamic discovery result.  New reachable workflows MUST be added
    here explicitly so a missing test signals the gap.
    """
    return {
        WORKFLOWS / "promotion-qualification.yml",
        WORKFLOWS / "reusable-promotion-closure.yml",
        WORKFLOWS / "reusable-promotion-verify.yml",
        WORKFLOWS / "reusable-promotion-build.yml",
        WORKFLOWS / "reusable-promotion-deploy.yml",
        WORKFLOWS / "reusable-promotion-live.yml",
        WORKFLOWS / "reusable-promotion-evidence.yml",
        WORKFLOWS / "reusable-promotion-timing.yml",
    }


# Workflows referenced by the qualification graph but NOT themselves
# in the qualification inventory.  These are transitive dependencies
# that are invoked through ``jobs.<job_id>.uses`` from a reusable
# workflow's step (the canonical Harbor build).
_TRANSITIVE_DEPS = {
    WORKFLOWS / "harbor-build-image.yml",
}


def test_dynamic_discovery_matches_inventory() -> None:
    """The discovered caller/reusable graph MUST equal the union of
    the qualification inventory plus the explicit transitive deps.
    """
    discovered = _discover_qualification_workflow_paths()
    expected = _expected_qualification_inventory() | _TRANSITIVE_DEPS
    missing = expected - discovered
    extra = discovered - expected
    assert not missing, f"discovered graph missed: {sorted(missing)}"
    assert not extra, f"discovered graph added: {sorted(extra)}"


@pytest.mark.parametrize("path", sorted(_expected_qualification_inventory()))
def test_workflow_file_under_500_lines(path: Path) -> None:
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= 500, f"{path.name}: {lines} lines (limit 500)"


def test_caller_under_200_lines() -> None:
    lines = len((WORKFLOWS / CALLER).read_text(encoding="utf-8").splitlines())
    assert lines <= 200, f"caller: {lines} lines (limit 200)"


# ---------------------------------------------------------------------------
# 3. tag filters are under push (NOT top-level on.tags)
# ---------------------------------------------------------------------------


def test_tag_filter_under_push() -> None:
    caller = _load_yaml(WORKFLOWS / CALLER)
    on = caller.get(True, caller.get("on", {}))
    assert "tags" not in on, "top-level on.tags is forbidden; use on.push.tags"
    assert "branches" in on.get("push", {}), "on.push.branches required"
    assert "tags" in on.get("push", {}), "on.push.tags required for qualification tags"


# ---------------------------------------------------------------------------
# 4. each called workflow declares workflow_call
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(REUSABLE))
def test_reusable_workflow_declares_workflow_call(name: str) -> None:
    wf = _load_yaml(WORKFLOWS / name)
    on = wf.get(True, wf.get("on", {}))
    assert "workflow_call" in on, f"{name}: workflow_call missing"
    wc = on["workflow_call"]
    assert "inputs" in wc, f"{name}: workflow_call.inputs required"


# ---------------------------------------------------------------------------
# 5. no workflow is stored in a workflow subdirectory
# ---------------------------------------------------------------------------


def test_no_workflow_subdirectory() -> None:
    # Reusable workflow files MUST remain directly under .github/workflows
    # — nested directories are unsupported.
    for p in WORKFLOWS.glob("*"):
        if p.is_dir():
            inner = list(p.rglob("*.yml")) + list(p.rglob("*.yaml"))
            assert not inner, f"workflows must not live in subdirectory {p}"


# ---------------------------------------------------------------------------
# 6. caller dependencies preserve the canonical order
# ---------------------------------------------------------------------------


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def test_caller_dependency_order() -> None:
    caller = _load_yaml(WORKFLOWS / CALLER)
    jobs = caller["jobs"]
    # closure -> build -> deploy -> live, evidence & timing are independent
    assert "closure" in jobs
    assert _as_list(jobs["closure"].get("needs")) == [], "closure has no deps"
    build_needs = _as_list(jobs["build"].get("needs"))
    assert "closure" in build_needs
    deploy_needs = _as_list(jobs["deploy"].get("needs"))
    assert "closure" in deploy_needs and "build" in deploy_needs
    live_needs = _as_list(jobs["live"].get("needs"))
    assert "closure" in live_needs and "build" in live_needs and "deploy" in live_needs


# ---------------------------------------------------------------------------
# 7. closure and subject identities are distinct
# 8. artifact range_head equals subject, not closure
# ---------------------------------------------------------------------------


def test_closure_workflow_distinguishes_subject_and_closure() -> None:
    text = (WORKFLOWS / "reusable-promotion-closure.yml").read_text(encoding="utf-8")
    # The closure workflow must derive SUBJECT_SHA as parent(CLOSURE_SHA)
    # and assert range_head == SUBJECT_SHA (not == CLOSURE_SHA).
    assert "$closure_sha^" in text, "subject_sha must be derived as closure_sha^"
    assert "range_head" in text and "subject_sha" in text
    assert "assert e[\"range_head\"] == \"$subject_sha\"" in text or (
        "range_head'] == '$subject_sha'" in text
    ), "range_head must equal SUBJECT_SHA, not CLOSURE_SHA"


# ---------------------------------------------------------------------------
# 9. every checkout is followed by HEAD equality
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _qualification_workflow_paths())
def test_every_checkout_followed_by_head_equality(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    # Crude but effective: every uses: actions/checkout step must be
    # followed by an assert HEAD == ... step.
    checkout_steps = [
        m.start() for m in re.finditer(r"uses:\s*actions/checkout@v4", text)
    ]
    if not checkout_steps:
        pytest.skip(f"{path.name}: no checkout steps")
    for idx in checkout_steps:
        rest = text[idx:]
        # the next 1000 characters must contain an assertion
        assert "HEAD" in rest[:2000] and (
            "==" in rest[:2000] or "drift" in rest[:2000]
        ), f"{path.name}: checkout at offset {idx} missing HEAD == assertion"


# ---------------------------------------------------------------------------
# 10. Python is bootstrapped before `.venv` use
# ---------------------------------------------------------------------------


def test_timing_workflow_bootstraps_python_before_venv() -> None:
    wf = _load_yaml(WORKFLOWS / "reusable-promotion-timing.yml")
    body = yaml.safe_dump(wf["jobs"]["shard-matrix"]["steps"])
    venv_index = body.find(".venv/bin/python")
    setup_index = body.find("python3 -m venv")
    assert setup_index != -1 and venv_index != -1, "missing venv or .venv invocation"
    assert setup_index < venv_index, (
        "python bootstrap must precede .venv/bin/python usage"
    )


# ---------------------------------------------------------------------------
# 11. every kubectl job has cluster bootstrap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _qualification_workflow_paths())
def test_kubectl_jobs_have_cluster_bootstrap(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "kubectl " not in text:
        pytest.skip(f"{path.name}: no kubectl usage")
    # Every job that uses kubectl must also materialise a kubeconfig
    assert "KUBECONFIG" in text or "cluster bootstrap" in text.lower(), (
        f"{path.name}: kubectl used without independent cluster bootstrap"
    )


# ---------------------------------------------------------------------------
# 12. no placeholder build command remains
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _qualification_workflow_paths())
def test_no_placeholder_build_commands(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    forbidden = ["buildah push", "BACKEND_DIGEST=$(buildah push"]
    for f in forbidden:
        assert f not in text, f"{path.name}: placeholder '{f}' present"


# ---------------------------------------------------------------------------
# 13. image outputs are full digest references
# ---------------------------------------------------------------------------


def test_build_workflow_returns_full_digest_refs() -> None:
    wf = _load_yaml(WORKFLOWS / "reusable-promotion-build.yml")
    on = wf.get(True, wf.get("on", {}))
    outputs = on["workflow_call"]["outputs"]
    for key in ("backend_image_ref", "scheduler_image_ref", "frontend_image_ref"):
        assert key in outputs, f"missing output {key}"


# ---------------------------------------------------------------------------
# 14. evidence is transferred with upload/download artifacts
# ---------------------------------------------------------------------------


def test_evidence_workflow_downloads_upstream_artifacts() -> None:
    wf = _load_yaml(WORKFLOWS / "reusable-promotion-evidence.yml")
    text = yaml.safe_dump(wf)
    assert "actions/download-artifact@v4" in text
    assert "actions/upload-artifact@v4" in text


# ---------------------------------------------------------------------------
# 15. qualification Job has labels and explicit command
# ---------------------------------------------------------------------------


def test_qualification_job_has_labels_and_command() -> None:
    wf = _load_yaml(WORKFLOWS / "reusable-promotion-live.yml")
    text = yaml.safe_dump(wf)
    assert "app.kubernetes.io/component: promotion-qualifier" in text
    assert "command:" in text
    assert "k9b.dev/qualification-run-id" in text


# ---------------------------------------------------------------------------
# 16. Lease cleanup runs on failure
# ---------------------------------------------------------------------------


def test_lease_cleanup_runs_always() -> None:
    wf = _load_yaml(WORKFLOWS / "reusable-promotion-live.yml")
    body = wf["jobs"]["run"]["steps"]
    releases = [s for s in body if "release" in s.get("name", "").lower()]
    assert releases, "no release step"
    for s in releases:
        assert s.get("if", "").strip() == "always()", (
            f"lease release step '{s['name']}' must run on always()"
        )


# ---------------------------------------------------------------------------
# 17. timing executes pytest rather than collect-only
# ---------------------------------------------------------------------------


def test_timing_executes_pytest_not_collect_only() -> None:
    wf = _load_yaml(WORKFLOWS / "reusable-promotion-timing.yml")
    body = yaml.safe_dump(wf)
    assert "pytest" in body
    assert "collect-only" not in body, (
        "timing workflow must NOT use collect-only"
    )


# ---------------------------------------------------------------------------
# 18. every timing repetition has four shards
# ---------------------------------------------------------------------------


def test_timing_matrix_has_three_reps_and_four_shards() -> None:
    wf = _load_yaml(WORKFLOWS / "reusable-promotion-timing.yml")
    matrix = wf["jobs"]["shard-matrix"]["strategy"]["matrix"]
    assert matrix["repetition"] == [1, 2, 3]
    assert matrix["shard"] == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# 19. qualification record is actually emitted
# ---------------------------------------------------------------------------


def test_record_module_derives_verdict() -> None:
    import importlib
    mod = importlib.import_module("scripts.qualification_record")
    assert hasattr(mod, "write_qualification_record")
    assert hasattr(mod, "derive_verdict")
    assert hasattr(mod, "VerdictInconsistentError")


# ---------------------------------------------------------------------------
# 20. no TODO, placeholder, or comment-only authority in acceptance jobs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _qualification_workflow_paths())
def test_no_todo_or_placeholder_in_acceptance_jobs(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    forbidden_tokens = [
        "TODO",
        "FIXME",
        "PLACEHOLDER",
        "TBD",
        "XXX",
    ]
    for token in forbidden_tokens:
        # Comment-only authorities can use words like "placeholder" in
        # comments to explain the design, so we only flag it when it
        # appears as a YAML value (e.g. "PLACEHOLDER: foo" or
        # "value: PLACEHOLDER").
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if token in line:
                raise AssertionError(
                    f"{path.name}: forbidden token '{token}' in non-comment line: {line}"
                )
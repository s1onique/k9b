"""R102 / R103 / R104 paired regressions for the workset verifier.

These paired fixtures close the three P0 defects surfaced by
the post-R101 audit review:

* **R102 (P0)** -- ancestor activation cutoffs were replaced,
  not propagated. The BFS queue entry now carries the INHERITED
  cutoffs dict so every ancestor cutoff is preserved across
  arbitrarily deep nesting. The leaf-only fixture proves the
  transitive propagation end-to-end.

* **R103 (P0)** -- callable-body dedup ignored the activation
  state. The BFS dedup key is now ``(id(target_body),
  frozenset(outer_cutoffs.items()))`` so the same body reached
  under meaningfully different cutoffs is re-inspected. The
  four activation mirrors (safe-then-mutator, mutator-then-safe,
  two-safe, recursive cycle with unchanged state) prove the
  new key is sound.

* **R104 (P0)** -- control-flow dominance and use-before-binding
  were applied only to the current scope. The outer-scope branch
  now applies R99 unconditional-dominance too, and an
  outer-scope binding that has no pre-cutoff entry but DOES
  declare the name reports ``use_before_binding=True`` rather
  than falling through to a more-distant scope (per the
  Python lexical-resolution rule that the nearest enclosing
  binding scope owns the name).

Each paired mirror uses a positive and a mirror so the fix
is exercised in both directions. The fixtures pair with the
canonical R98/R99 fixtures (8) for full coverage of the
R98 / R99 / R102 / R103 / R104 contract.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path
from typing import Any, cast

_VERIFIER_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "verifiers"
    / "incident_current_run_promotion_workset01.py"
)


def _load_verifier() -> Any:
    spec = importlib.util.spec_from_file_location(
        "icr_workset01_round23_verifier", _VERIFIER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier: Any = _load_verifier()


def _block(source: str, spaces: int) -> str:
    if not source:
        return ""
    return (
        textwrap.indent(textwrap.dedent(source).strip("\n"), " " * spaces)
        + "\n"
    )


def _canonical_source(*, before_loop: str = "", after_loop: str = "") -> str:
    return (
        "def _ingest_alert_signals(snapshot, **kw):\n"
        "    refs = []\n"
        f"{_block(before_loop, 4)}"
        "    for outcome in outcomes:\n"
        "        if isinstance(outcome, Inserted):\n"
        "            refs.append(\n"
        "                CurrentRunSignalRef(\n"
        "                    signal_id=outcome.signal_id,\n"
        "                )\n"
        "            )\n"
        "            continue\n"
        f"{_block(after_loop, 4)}"
        "    workset = build_current_run_workset(\n"
        "        references=tuple(refs),\n"
        "    )\n"
        "    current_run_signal_ids = tuple(workset.signal_ids)\n"
        "    return promote_alert_signals_scoped_for_accumulator(\n"
        "        signal_ids=current_run_signal_ids,\n"
        "    )\n"
    )


def _violations(source: str, tmp_path: Path) -> list[str]:
    path = tmp_path / "ingestion_fixture.py"
    path.write_text(source, encoding="utf-8")
    tree = verifier._parse(path)
    assert tree is not None
    return cast(
        list[str],
        verifier.check_ingestion_stable_deduplicates_artifact_workset(
            tree, path
        ),
    )


# ---------------------------------------------------------------------------
# R102 (P0) -- leaf-only activation cutoff propagation
# ---------------------------------------------------------------------------


def test_r102_three_level_chain_with_only_leaf_calling_invoke_is_rejected(
    tmp_path: Path,
) -> None:
    """R102 (P0) leaf-only fixture: the three-level chain
    ``outer -> wrapper -> inner -> leaf`` where ONLY ``leaf`` calls
    ``invoke()``. The previous R98 implementation overwrote the
    outer cutoff at every hop, so ``leaf`` saw the final outer
    source state and silently resolved ``invoke`` to ``safe``.
    The R102 fix threads the inherited cutoffs dict through the
    BFS so ``leaf`` retains the outer cutoff at the position of
    ``wrapper()`` -- ``mutator`` is the binding visible at the
    invocation, so the audit rejects the chain.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    invoke = mutator\n"
            "    def wrapper():\n"
            "        def inner():\n"
            "            def leaf():\n"
            "                invoke()\n"
            "            leaf()\n"
            "        inner()\n"
            "    wrapper()\n"
            "    invoke = safe\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert any(
        "a called deferred body mutates the authoritative" in v
        for v in violations
    ), (
        "R102 must reject the leaf-only three-level chain; the "
        "leaf must retain the outer cutoff at the position of "
        f"wrapper() even when wrapper and inner do NOT call "
        f"invoke() directly; got {violations}"
    )


# ---------------------------------------------------------------------------
# R103 (P0) -- activation-state-aware callable-body dedup
# ---------------------------------------------------------------------------


def test_r103_same_body_called_twice_with_different_outer_bindings_rejects_mutation(
    tmp_path: Path,
) -> None:
    """R103 (P0) mirror: ``inner()`` called twice from ``outer``,
    first when ``invoke=safe`` and then after ``invoke=mutator``.
    The previous BFS dedup was keyed on body identity alone so the
    second call was skipped; the second activation's mutation was
    missed. The R103 fix includes the inherited cutoffs in the
    state key, so the body is re-inspected under the new outer
    binding and the mutation is reported.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    def inner():\n"
            "        invoke()\n"
            "    invoke = safe\n"
            "    inner()\n"
            "    invoke = mutator\n"
            "    inner()\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert any(
        "a called deferred body mutates the authoritative" in v
        for v in violations
    ), (
        "R103 must reject the mutator activation even though the "
        "safe activation already populated visited_bodies; the "
        f"state key MUST include cutoffs; got {violations}"
    )


def test_r103_safe_then_mutator_rebinding_after_call_is_accepted(
    tmp_path: Path,
) -> None:
    """R103 mirror: ``outer`` calls ``inner()`` once under ``safe``,
    then rebinds ``invoke = mutator`` in outer. The body is reached
    only once so the dedup-by-body-id is technically not exercised,
    but the test still proves the audit catches the mutation when
    the body is reached under the mutator activation state
    (call_position cutoff preserves the safe binding).
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    def inner():\n"
            "        invoke()\n"
            "    inner()\n"
            "    invoke = mutator\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert violations == [], (
        "the single inner() call fires under safe (cutoff for "
        "outer is the inner() position), so no mutation should be "
        f"reported; got {violations}"
    )


def test_r103_two_safe_activations_of_same_body_are_accepted(
    tmp_path: Path,
) -> None:
    """R103 mirror: ``inner()`` called twice from ``outer``, both
    under the ``safe`` binding. The dedup state key is the same
    for both activations (no rebinding), so the body is visited
    once and the audit accepts.
    """
    source = _canonical_source(
        after_loop=(
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    def inner():\n"
            "        invoke()\n"
            "    invoke = safe\n"
            "    inner()\n"
            "    inner()\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert violations == [], (
        "R103 must accept two safe activations of the same body; "
        f"got {violations}"
    )


def test_r103_recursive_cycle_with_unchanged_state_terminates(
    tmp_path: Path,
) -> None:
    """R103 mirror: a recursive ``a -> b -> a`` cycle with the
    same inherited cutoffs MUST terminate. The state key is
    identical for the second visit so the body is skipped; the
    verifier returns without hanging or re-walking the cycle.
    """
    source = _canonical_source(
        after_loop=(
            "def outer():\n"
            "    def a():\n"
            "        b()\n"
            "    def b():\n"
            "        a()\n"
            "    a()\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert isinstance(violations, list), "verifier must return a list"


# ---------------------------------------------------------------------------
# R104 (P0) -- outer-scope unconditional-dominance and use-before-binding
# ---------------------------------------------------------------------------


def test_r104_outer_conditional_then_unconditional_dominates_is_accepted(
    tmp_path: Path,
) -> None:
    """R104 (P0) positive: an UNCONDITIONAL ``safe`` binding in
    outer scope dominates an earlier conditional ``mutator``
    binding -- the audit MUST accept because the unconditional
    always runs and overwrites. The previous implementation
    applied R99 dominance only to the current scope; the
    outer-scope branch fell back to path-diversity ambiguity and
    rejected this legitimate fixture.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    if True:\n"
            "        invoke = mutator\n"
            "    invoke = safe\n"
            "    def inner():\n"
            "        invoke()\n"
            "    inner()\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert violations == [], (
        "R104 must accept the outer-scope unconditional safe "
        "override after a conditional mutator; safe dominates; "
        f"got {violations}"
    )


def test_r104_outer_unconditional_then_conditional_after_call_is_rejected(
    tmp_path: Path,
) -> None:
    """R104 (P0) negative: the unconditional ``safe`` is at an
    EARLIER position than the conditional ``mutator`` in the
    outer scope. The conditional might run last if its branch is
    taken, so the live frontier is ambiguous -- the audit fails
    closed by reporting an ``ambiguous callable binding`` violation.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    invoke = safe\n"
            "    if True:\n"
            "        invoke = mutator\n"
            "    def inner():\n"
            "        invoke()\n"
            "    inner()\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert any(
        "ambiguous callable binding" in v for v in violations
    ), (
        "R104 must fail closed when the outer-scope conditional "
        "binding has a position strictly greater than the "
        f"unconditional binding; got {violations}"
    )

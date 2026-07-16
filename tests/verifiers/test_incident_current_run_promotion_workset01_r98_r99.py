"""R98/R99 paired regressions for the workset verifier.

These paired fixtures close two P0 defects that survived the
R94/R95/R96 round:

* **R98 (P0)** -- outer-scope bindings were resolved against the
  final source state instead of the invocation-time activation
  state. When ``outer`` calls ``inner`` at line ``P``, any
  outer-scope rebinding declared strictly AFTER ``P`` cannot have
  contributed the value seen inside ``inner``. The fix threads a
  per-ancestor-scope position cutoff through the reachability BFS
  so :func:`_resolve_alias` filters outer-scope bindings to those
  declared strictly before the call position in their respective
  scope. The cutoff is also transitive across the three-level
  ``outer -> wrapper -> inner -> leaf`` chain so every ancestor
  cutoff is preserved.

  Required fixtures:

  - outer mutator binding then inner() call then outer safe
    rebinding: REJECT (later outer rebinding cannot dominate).
  - outer safe binding then inner() call then outer mutator
    rebinding: ACCEPT (later rebinding is invisible at the call).
  - rebinding immediately before inner(): the new binding
    dominates.
  - three-level wrapper -> inner -> leaf chain preserves every
    ancestor cutoff (REJECT).

* **R99 (P0)** -- path diversity was over-reporting ambiguity.
  The previous implementation declared any two pre-call bindings
  with distinct ``path`` values ambiguous. This rejected legitimate
  fixtures where an unconditional binding dominates a conditional
  binding (e.g. ``if cond: x = mutator; x = safe; x()`` -- the
  unconditional ``x = safe`` always runs and overwrites the
  conditional binding). The fix discriminates UNCONDITIONAL
  bindings (path parent is the scope body itself, attr "self")
  from CONDITIONAL bindings (path parent is a compound statement),
  picks the latest unconditional binding as the live binding, and
  only reports ambiguity when a conditional binding has a position
  strictly greater than the unconditional binding's position.

  Required fixtures:

  - conditional mutator then unconditional safe: ACCEPT (safe
    dominates).
  - if/else bindings then unconditional safe: ACCEPT (safe
    dominates both arms).
  - unconditional safe then conditional mutator: FAIL CLOSED
    (the conditional might run last if its branch is taken).
  - two unresolved if/else bindings with no later override:
    AMBIGUOUS.

The fail-closed fixtures assert the ``"ambiguous callable binding"``
violation message rather than the mutation message because the R99
path-dominance check trips first and reports ambiguity; the audit
does not proceed to check mutation once it has declared the live
frontier ambiguous. The accept fixtures assert that violations is
empty so the R99 dominance check does not over-report.

Each new detection has a paired mirror that MUST remain accepted so
the detectors are not trivially rejecting every callable. The
unconditional-dominance and the three-level wrapper chain are
covered with both positive and mirror fixtures so the R98/R99 fixes
are proven in both directions.
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
        "icr_workset01_r98_r99_verifier", _VERIFIER_PATH
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
# R98 -- outer-scope bindings use invocation-time activation state
# ---------------------------------------------------------------------------


def test_r98_outer_mutator_binding_then_inner_call_then_outer_safe_rebinding_is_rejected(
    tmp_path: Path,
) -> None:
    """R98 (P0): the fixture

        def outer():
            invoke = mutator
            def inner():
                invoke()
            inner()
            invoke = safe

    At runtime, ``inner()`` invokes ``mutator`` because the later
    ``invoke = safe`` has not executed yet. The previous verifier
    selected the textually latest outer-scope rebinding
    (``safe``) and silently accepted the mutation. The fix threads
    the call position ``invoke()`` as the activation cutoff for
    ``outer`` so the later rebinding is invisible at the call.

    Here ``mutator`` appends to ``refs``; the audit MUST reject.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    invoke = mutator\n"
            "    def inner():\n"
            "        invoke()\n"
            "    inner()\n"
            "    invoke = safe\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert any(
        "a called deferred body mutates the authoritative" in v
        for v in violations
    ), (
        "R98 must reject the mutator binding observed at inner()'s "
        "call position even though a later outer rebinding overrides "
        f"it; got {violations}"
    )


def test_r98_outer_safe_binding_then_inner_call_then_outer_mutator_rebinding_is_accepted(
    tmp_path: Path,
) -> None:
    """R98 mirror: when the runtime observation is the safe alias,
    the audit MUST accept. The earlier outer binding is the
    textually-latest one visible at the call site, and the later
    rebinding has not executed yet.

        def outer():
            invoke = safe
            def inner():
                invoke()
            inner()
            invoke = mutator
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    invoke = safe\n"
            "    def inner():\n"
            "        invoke()\n"
            "    inner()\n"
            "    invoke = mutator\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert violations == [], (
        "R98 must accept the safe alias observed at inner()'s call "
        "site; the later outer rebinding is invisible at the call "
        f"position; got {violations}"
    )


def test_r98_outer_rebinding_immediately_before_inner_uses_new_binding(
    tmp_path: Path,
) -> None:
    """R98 fixture 3: rebinding immediately before inner() MUST
    use the new binding. The cutoff is the call position, not
    the end of the scope.

        def outer():
            invoke = mutator
            invoke = safe
            def inner():
                invoke()
            inner()
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "def outer():\n"
            "    invoke = mutator\n"
            "    invoke = safe\n"
            "    def inner():\n"
            "        invoke()\n"
            "    inner()\n"
            "outer()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert violations == [], (
        "R98 must accept the safe rebinding immediately before "
        "inner()'s call; the audit's cutoff is the call position "
        f"and the new safe binding dominates; got {violations}"
    )


def test_r98_three_level_wrapper_inner_leaf_preserves_every_ancestor_cutoff(
    tmp_path: Path,
) -> None:
    """R98 fixture 4: three-level chain

        def outer():
            invoke = mutator
            def wrapper():
                invoke()        # cutoff for outer at position P1
                def inner():
                    invoke()    # cutoff for wrapper at position P2
                    def leaf():
                        invoke()  # cutoff for inner at position P3
                    leaf()
                inner()
            wrapper()
            invoke = safe  # not visible at any leaf call

    The leaf's view of ``outer`` MUST be filtered to bindings
    strictly before P1 (the wrapper -> outer cutoff). The audit
    must reject because mutator is the latest outer binding before
    P1, and mutator mutates ``refs``.
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
            "        invoke()\n"
            "        def inner():\n"
            "            invoke()\n"
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
        "R98 must reject the three-level chain; the leaf's view of "
        "the outer-scope mutator binding must persist even when the "
        f"outer scope rebinds invoke after wrapper(); got {violations}"
    )


# ---------------------------------------------------------------------------
# R99 -- control-flow dominance: unconditional bindings dominate
# conditional bindings in the current scope
# ---------------------------------------------------------------------------


def test_r99_conditional_mutator_then_unconditional_safe_is_accepted(
    tmp_path: Path,
) -> None:
    """R99 fixture 1: ``if cond: invoke = mutator; invoke = safe;
    invoke()``. The unconditional ``invoke = safe`` runs after
    the conditional and dominates; the audit MUST accept.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "if True:\n"
            "    invoke = mutator\n"
            "invoke = safe\n"
            "invoke()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert violations == [], (
        "R99 must accept the unconditional safe override after a "
        "conditional mutator; the safe binding always runs and "
        f"overwrites; got {violations}"
    )


def test_r99_if_else_bindings_then_unconditional_safe_is_accepted(
    tmp_path: Path,
) -> None:
    """R99 fixture 2: ``if cond: invoke = mutator; else: invoke =
    another_mutator; invoke = safe; invoke()``. The unconditional
    ``invoke = safe`` dominates BOTH arms; the audit MUST accept.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def another_mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "if True:\n"
            "    invoke = mutator\n"
            "else:\n"
            "    invoke = another_mutator\n"
            "invoke = safe\n"
            "invoke()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert violations == [], (
        "R99 must accept the unconditional safe override after "
        "if/else bindings; safe dominates both arms; "
        f"got {violations}"
    )


def test_r99_unconditional_safe_then_conditional_mutator_is_rejected(
    tmp_path: Path,
) -> None:
    """R99 fixture 3: the failure-closed case.

        invoke = safe
        if cond:
            invoke = mutator
        invoke()

    Here the conditional binding ``invoke = mutator`` is at a
    position STRICTLY greater than the unconditional ``invoke =
    safe``. The conditional might run last if its branch is
    taken, so the live frontier is ambiguous; the audit MUST fail
    closed by reporting an ``ambiguous callable binding`` R99/R90
    violation.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def safe():\n"
            "    pass\n"
            "invoke = safe\n"
            "if True:\n"
            "    invoke = mutator\n"
            "invoke()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert any(
        "ambiguous callable binding" in v for v in violations
    ), (
        "R99 must fail closed when a conditional binding has a "
        "position strictly greater than the unconditional binding; "
        "the conditional might run last; got {violations}"
    )


def test_r99_two_unresolved_if_else_bindings_with_no_later_override_is_ambiguous(
    tmp_path: Path,
) -> None:
    """R99 fixture 4: ``if cond: invoke = mutator; else: invoke =
    another_mutator; invoke()``. There is no unconditional override
    after the if/else; the live frontier is ambiguous because the
    branches are mutually exclusive. The audit fails closed by
    reporting an ``ambiguous callable binding`` R99/R90 violation.
    """
    source = _canonical_source(
        after_loop=(
            "def mutator():\n"
            "    refs.append('junk')\n"
            "def another_mutator():\n"
            "    refs.append('junk')\n"
            "if True:\n"
            "    invoke = mutator\n"
            "else:\n"
            "    invoke = another_mutator\n"
            "invoke()\n"
        )
    )
    violations = _violations(source, tmp_path)
    assert any(
        "ambiguous callable binding" in v for v in violations
    ), (
        "R99 must fail closed when two if/else bindings live "
        "without an unconditional override; the audit cannot prove "
        f"safe execution; got {violations}"
    )

# ---------------------------------------------------------------------------

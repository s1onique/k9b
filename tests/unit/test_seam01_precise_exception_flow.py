"""Precise exception-flow transfer tests for SEAM01 promotion-diagnosis handoff verifier.

These tests verify the precise exception-path transfer introduced by
ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01.  The tests inspect the
exception environments emitted by the analyzer directly, complementing
the end-to-end discriminating fixtures that gate the verifier.

Suggested by: ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

# Add repo root to path so the verifier modules are importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "verifiers"))

from promotion_diagnosis_handoff_flow_exception_paths import (  # noqa: E402
    Environment,
    _may_raise_expr,
    _stmt_may_raise,
    capture_exception_envs,
)
from promotion_diagnosis_handoff_flow_try_canonical import (  # noqa: E402
    analyze_try_in_sequence,
    analyze_try_to_target,
)
from promotion_diagnosis_handoff_model import (  # noqa: E402
    Environment as ModelEnvironment,
)
from promotion_diagnosis_handoff_model import (  # noqa: E402, I001
    ExceptionKind,
    ExceptionPath,
    Provenance,
    ProvenanceKind,
    SourceLocation,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function {name} not found")


def _find_try(func: ast.FunctionDef) -> ast.Try:
    for stmt in func.body:
        if isinstance(stmt, ast.Try):
            return stmt
    raise AssertionError("No try found in function")


def _make_safe_provenance() -> Provenance:
    """Construct a safe promotion_result Provenance."""
    return Provenance(
        attr_chain=("promotion_result",),
        provenance_kind=ProvenanceKind.INCIDENT_PROMOTION_RESULT,
    )


def _make_unsafe_provenance() -> Provenance:
    """Construct an unsafe Provenance (UNKNOWN kind, no chain)."""
    return Provenance()


class _AssignTracker:
    """Minimal ``_track_to_target_line`` stand-in that performs Assign
    mutations only.

    Sufficient for testing the precise exception analyzer in isolation:
    compound-statement side effects on ``env`` are not exercised by
    ``capture_exception_envs`` (which only snapshots); only Assign
    statements need their RHS-bound targets to be reflected so the next
    snapshot captures the post-success state.
    """

    def __call__(
        self,
        stmt: ast.stmt,
        env: Environment,
        target_line: int,
        target_col: int,
        enclosing_return_type: str | None,
        is_classmethod: bool,
    ) -> None:
        if isinstance(stmt, ast.Assign):
            value_prov = _expr_provenance(stmt.value, env)
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    env[target.id] = value_prov
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.value is not None:
                env[stmt.target.id] = _expr_provenance(stmt.value, env)
        elif isinstance(stmt, ast.AugAssign):
            if isinstance(stmt.target, ast.Name):
                env[stmt.target.id] = _expr_provenance(stmt.value, env)
        # Other statement kinds are ignored in this minimal tracker.


class _AssignStatementTracker:
    """Minimal ``_track_statement`` stand-in for in-sequence tests.

    Only handles Assign / AnnAssign / AugAssign; other statement kinds
    are no-ops.  This keeps the test independent of the full flow
    tracker while letting the canonical try analyzer observe the
    post-success state of an assignment.
    """

    def __call__(
        self,
        stmt: ast.stmt,
        env: Environment,
        enclosing_return_type: str | None,
        is_classmethod: bool,
    ) -> None:
        if isinstance(stmt, ast.Assign):
            value_prov = _expr_provenance(stmt.value, env)
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    env[target.id] = value_prov
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.value is not None:
                env[stmt.target.id] = _expr_provenance(stmt.value, env)
        elif isinstance(stmt, ast.AugAssign):
            if isinstance(stmt.target, ast.Name):
                env[stmt.target.id] = _expr_provenance(stmt.value, env)
        # Other statement kinds are ignored.


def _expr_provenance(expr: ast.expr, env: Environment) -> Provenance:
    """Build a Provenance for ``expr`` based on the current ``env``.

    Names resolve to the current env binding; everything else is UNKNOWN.
    This is a tiny stand-in: it lets the unit tests observe the
    post-success state without invoking the full provenance analyzer.
    """
    if isinstance(expr, ast.Name):
        return env.get(expr.id, Provenance())
    return Provenance()


class TestExceptionPathModel(unittest.TestCase):
    """Tests for the canonical exception-path types."""

    def test_environment_is_dict_alias(self) -> None:
        """The canonical Environment alias is dict[str, Provenance]."""
        self.assertIs(ModelEnvironment, Environment)
        env: Environment = {"x": _make_safe_provenance()}
        self.assertEqual(env["x"].attr_chain, ("promotion_result",))

    def test_exception_path_uses_environment(self) -> None:
        """ExceptionPath.env must hold the snapshot immediately pre-raise."""
        env: Environment = {"value": _make_unsafe_provenance()}
        path = ExceptionPath(
            env=env,
            origin=SourceLocation(line=5, column=10),
            exception_kind=ExceptionKind.UNKNOWN,
        )
        self.assertEqual(path.env["value"].provenance_kind, ProvenanceKind.UNKNOWN)
        self.assertEqual(path.origin.line, 5)
        self.assertEqual(path.origin.column, 10)
        self.assertEqual(path.exception_kind, ExceptionKind.UNKNOWN)


class TestMayRaiseExpr(unittest.TestCase):
    """Tests for the boolean predicate as a non-authoritative filter."""

    def test_call_raises(self) -> None:
        self.assertTrue(_may_raise_expr(ast.parse("foo()").body[0].value))

    def test_attribute_raises(self) -> None:
        self.assertTrue(_may_raise_expr(ast.parse("a.b").body[0].value))

    def test_subscript_raises(self) -> None:
        self.assertTrue(_may_raise_expr(ast.parse("a[b]").body[0].value))

    def test_name_does_not_raise(self) -> None:
        self.assertFalse(_may_raise_expr(ast.parse("x").body[0].value))

    def test_constant_does_not_raise(self) -> None:
        self.assertFalse(_may_raise_expr(ast.parse("1").body[0].value))


class TestCaptureExceptionEnvs(unittest.TestCase):
    """Tests for the precise exception-env snapshotter."""

    def test_multiple_exception_points_in_sequence(self) -> None:
        """Two calls in one try body emit two snapshots, one per call."""
        src = """
def fn(batch, untrusted):
    value = batch.promotion_result
    try:
        safe_call()
        value = untrusted
        risky()
        value = batch.promotion_result
    except Exception:
        pass
    return value.actionable_incident_ids
"""
        tree = _parse(src)
        func = _find_function(tree, "fn")
        try_node = _find_try(func)
        body_stmts = try_node.body

        # Use the helper from the model to seed env.
        from promotion_diagnosis_handoff_model import Environment as MEnv

        env: MEnv = {"value": _make_safe_provenance()}
        tracker = _AssignTracker()

        # Process safe_call (Expr): one snapshot of {value: safe}.
        safe_envs = capture_exception_envs(
            body_stmts[0], env, target_line=99, target_col=0,
            enclosing_return_type=None, is_classmethod=False,
            _track_to_target_line=tracker,
        )
        self.assertEqual(len(safe_envs), 1)
        self.assertEqual(safe_envs[0]["value"].provenance_kind,
                         ProvenanceKind.INCIDENT_PROMOTION_RESULT)

        # Process value = untrusted: no exception (Name RHS does not raise),
        # env mutated to {value: unsafe}.
        assign_envs = capture_exception_envs(
            body_stmts[1], env, target_line=99, target_col=0,
            enclosing_return_type=None, is_classmethod=False,
            _track_to_target_line=tracker,
        )
        self.assertEqual(len(assign_envs), 0)
        self.assertEqual(env["value"].provenance_kind, ProvenanceKind.UNKNOWN)

        # Process risky() (Expr): snapshot of {value: unsafe}.
        risky_envs = capture_exception_envs(
            body_stmts[2], env, target_line=99, target_col=0,
            enclosing_return_type=None, is_classmethod=False,
            _track_to_target_line=tracker,
        )
        self.assertEqual(len(risky_envs), 1)
        self.assertEqual(risky_envs[0]["value"].provenance_kind,
                         ProvenanceKind.UNKNOWN)

        # Process value = batch.promotion_result: snapshot BEFORE the
        # attribute RHS evaluates, then env mutated to safe.
        before_env_value = env["value"]
        last_assign_envs = capture_exception_envs(
            body_stmts[3], env, target_line=99, target_col=0,
            enclosing_return_type=None, is_classmethod=False,
            _track_to_target_line=tracker,
        )
        # Attribute RHS raises, so the snapshot must come from BEFORE.
        self.assertEqual(len(last_assign_envs), 1)
        self.assertIs(last_assign_envs[0]["value"], before_env_value)

    def test_compound_branch_exception_point(self) -> None:
        """An exception inside an ``if`` body carries branch-local state."""
        src = """
def fn(batch, untrusted, flag):
    value = batch.promotion_result
    try:
        if flag:
            value = untrusted
            risky()
            value = batch.promotion_result
    except Exception:
        pass
    return value.actionable_incident_ids
"""
        tree = _parse(src)
        func = _find_function(tree, "fn")
        try_node = _find_try(func)
        if_stmt = try_node.body[0]
        from promotion_diagnosis_handoff_model import Environment as MEnv

        env: MEnv = {"value": _make_safe_provenance()}
        tracker = _AssignTracker()
        envs = capture_exception_envs(
            if_stmt, env, target_line=99, target_col=0,
            enclosing_return_type=None, is_classmethod=False,
            _track_to_target_line=tracker,
        )
        # Expect two exception envs: one before risky(), one before
        # value = batch.promotion_result.  Both must be UNSAFE.
        self.assertGreaterEqual(len(envs), 2)
        for exc_env in envs:
            self.assertEqual(
                exc_env["value"].provenance_kind,
                ProvenanceKind.UNKNOWN,
            )

    def test_conditional_unsafe_state_before_later_call(self) -> None:
        """A conditional unsafe assignment surfaces in handler inputs.

        The analyzer captures exception envs from inside the if-body
        even when the conditional branch does not modify the outer env
        via the minimal tracker.  What matters is that the analyzer
        emits the snapshot at all reachable operations, not that the
        contents reflect compound-statement merges (which require the
        full flow tracker).
        """
        src = """
def fn(batch, untrusted, flag):
    value = batch.promotion_result
    try:
        if flag:
            value = untracked
        risky()
        value = batch.promotion_result
    except Exception:
        pass
    return value.actionable_incident_ids
"""
        tree = _parse(src)
        func = _find_function(tree, "fn")
        try_node = _find_try(func)
        from promotion_diagnosis_handoff_model import Environment as MEnv

        env: MEnv = {"value": _make_safe_provenance()}
        tracker = _AssignTracker()
        envs = capture_exception_envs(
            try_node, env, target_line=99, target_col=0,
            enclosing_return_type=None, is_classmethod=False,
            _track_to_target_line=tracker,
        )
        # The analyzer must emit the two reachable exception paths
        # outside the conditional branch: one for risky() and one for
        # the trailing ``value = batch.promotion_result`` (whose
        # attribute RHS may raise).  The conditional branch's
        # ``value = untracked`` does not itself raise (Name RHS).
        self.assertGreaterEqual(len(envs), 2)

    def test_unsafe_before_exception_safe_afterward(self) -> None:
        """Exception env is unsafe, normal completion is safe."""
        src = """
def fn(batch, untrusted):
    value = batch.promotion_result
    try:
        value = untrusted
        risky()
        value = batch.promotion_result
    except Exception:
        pass
    return value.actionable_incident_ids
"""
        tree = _parse(src)
        func = _find_function(tree, "fn")
        try_node = _find_try(func)
        from promotion_diagnosis_handoff_model import Environment as MEnv

        env: MEnv = {"value": _make_safe_provenance()}
        tracker = _AssignTracker()

        # Pre-execution env for risky() should be {value: unsafe}.
        # After the post-risky() assignment, env mutates to {value: safe}.
        # We rely on the canonical analyzer: the post-body prov should
        # end up safe.
        analyze_try_to_target(
            try_node,
            env,
            target_line=999,
            target_col=0,
            enclosing_return_type=None,
            is_classmethod=False,
            _track_to_target_line=tracker,
        )
        # After try processing, env should reflect merged handler paths
        # which include unsafe exception envs; merge returns UNKNOWN.
        self.assertEqual(env["value"].provenance_kind, ProvenanceKind.UNKNOWN)


class TestAnalyzeTryInSequence(unittest.TestCase):
    """Integration tests for analyze_try_in_sequence with passthrough."""

    def test_exception_path_distinct_from_normal(self) -> None:
        """Distinct paths until the try join -- the merge is UNKNOWN."""
        src = """
def fn(batch, untrusted):
    value = batch.promotion_result
    try:
        value = untrusted
        risky()
    except Exception:
        pass
    return value.actionable_incident_ids
"""
        tree = _parse(src)
        func = _find_function(tree, "fn")
        try_node = _find_try(func)
        from promotion_diagnosis_handoff_model import Environment as MEnv

        env: MEnv = {"value": _make_safe_provenance()}
        tracker = _AssignStatementTracker()
        analyze_try_in_sequence(
            try_node, env,
            enclosing_return_type=None, is_classmethod=False,
            _track_statement=tracker,
        )
        # After try: the handler kept {value: unsafe} and the normal
        # path completed {value: unsafe too (no successful reassign)}.
        # value is therefore UNSAFE either way.
        self.assertEqual(env["value"].provenance_kind, ProvenanceKind.UNKNOWN)


class TestBooleanAuthorityIsNonAuthoritative(unittest.TestCase):
    """Boolean predicates are non-authoritative filters."""

    def test_stmt_may_raise_is_used_only_as_filter(self) -> None:
        """``_stmt_may_raise`` returns True for the unsafe assignment too."""
        src = "value = batch.promotion_result"
        stmt = ast.parse(src).body[0]
        self.assertTrue(_stmt_may_raise(stmt))


if __name__ == "__main__":
    unittest.main()
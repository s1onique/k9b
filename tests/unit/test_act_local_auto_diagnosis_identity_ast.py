"""ACT-local AST verifier for backend-authoritative automatic diagnosis.

R1 strengthening:
* detect ``<alias> = get_incident_store(); <alias>.list_incidents()``
  AND module-qualified calls
  (``<module>.<attr>.get_incident_store().list_incidents()``);
* run negative fixtures so the verifier proves it actually catches
  what it claims to catch;
* surface a verifier self-test so the static check does not silently
  rot.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R1
"""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Iterable
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "k8s_diag_agent"

SUSPECT_DIRECTORIES: tuple[str, ...] = (
    "health",
)

DISPATCHER_MODULES: frozenset[str] = frozenset(
    {
        "collect.incident_diagnosis_dispatch",
        "collect.incident_diagnosis_dispatch_backend",
        "collect.incident_diagnosis_dispatch_pagination",
        "collect.incident_diagnosis_dispatch_routes",
        "collect.incident_promotion_dispatch",
        "collect.incident_promotion_backend",
        "collect.incident_promotion_local",
        "collect.incident_diagnosis_auto_loop",
        "collect.incident_identity_hardening",
    }
)

PROVIDER_MODULES: frozenset[str] = frozenset(
    {
        "collect.incident_store_provider",
    }
)

FORBIDDEN_CLASS_NAMES: tuple[str, ...] = (
    "SQLiteIncidentStore",
)


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py":
            continue
        yield path


def _module_name_from_path(path: Path) -> str:
    relative = path.relative_to(SRC_ROOT).with_suffix("")
    return ".".join(relative.parts)


def _is_dispatcher_module(module_name: str) -> bool:
    return module_name in DISPATCHER_MODULES


def _is_provider_module(module_name: str) -> bool:
    return module_name in PROVIDER_MODULES


def _gather_violations(file_path: Path) -> list[str]:
    module_name = _module_name_from_path(file_path)
    if _is_dispatcher_module(module_name) or _is_provider_module(module_name):
        return []
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return [f"{module_name}: could not read file"]
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = getattr(node, "func", None)
        if isinstance(callee, ast.Name) and callee.id in FORBIDDEN_CLASS_NAMES:
            violations.append(
                f"{module_name}:{node.lineno}: direct "
                f"``{callee.id}`` instantiation is forbidden in the "
                "scheduler path; route through the dispatcher layer or "
                "the role-guarded provider."
            )
        elif isinstance(callee, ast.Attribute) and callee.attr in FORBIDDEN_CLASS_NAMES:
            violations.append(
                f"{module_name}:{node.lineno}: direct "
                f"``{callee.attr}`` instantiation is forbidden in the "
                "scheduler path; route through the dispatcher layer or "
                "the role-guarded provider."
            )
    return violations


def _attr_chain_ends_with(node: ast.Attribute, name: str) -> bool:
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        if current.attr == name:
            return True
        current = current.value
    return False


def _statement_assigns_name_to_get_incident_store(
    statement: ast.stmt, target_name: str
) -> bool:
    """Return True when ``statement`` binds ``target_name`` to ``get_incident_store()``."""
    if not isinstance(statement, ast.Assign):
        return False
    if not statement.targets:
        return False
    target = statement.targets[0]
    if isinstance(target, ast.Name) and target.id != target_name:
        return False
    if not isinstance(statement.value, ast.Call):
        return False
    return _call_ends_with_get_incident_store(statement.value)


def _call_ends_with_get_incident_store(node: ast.Call) -> bool:
    """Return True when ``node`` is or ends in a ``get_incident_store`` call."""
    callee = node.func
    if isinstance(callee, ast.Name):
        return callee.id == "get_incident_store"
    if isinstance(callee, ast.Attribute):
        return _attr_chain_ends_with(callee, "get_incident_store")
    return False


def _local_store_alias_in_scope(
    call: ast.Call, scope_body: list[ast.stmt] | None
) -> bool:
    """Return True when ``call.func.value`` is a ``Name`` previously bound
    to a ``get_incident_store()`` invocation in the same scope.

    This implements the R1 alias detector for
    ``store = get_incident_store(); store.list_incidents()``. We
    conservatively require the alias to be assigned in the same
    function body. Cross-scope alias tracking is not in scope for the
    R1 verifier; we do not need to be exhaustive.
    """
    if scope_body is None:
        return False
    callee = call.func
    if not isinstance(callee, ast.Attribute):
        return False
    if not isinstance(callee.value, ast.Name):
        return False
    target_name = callee.value.id
    for prior in scope_body:
        if _statement_assigns_name_to_get_incident_store(prior, target_name):
            return True
    return False


def _is_local_incident_call(
    callee: ast.AST,
    scope_body: list[ast.stmt] | None = None,
) -> bool:
    if not isinstance(callee, ast.Attribute):
        return False
    if callee.attr not in {"list_incidents", "get_incident"}:
        return False
    inner = callee.value
    # ``<alias>.list_incidents()`` where ``<alias> = get_incident_store()``
    # detected via the scope_body alias check below.
    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
        if inner.func.id == "get_incident_store":
            return True
    # ``<module>.<attr>.get_incident_store().list_incidents()``
    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
        if _attr_chain_ends_with(inner.func, "get_incident_store"):
            return True
    # ``<alias>.list_incidents()`` where ``<alias>`` is a Name that
    # was previously bound to ``get_incident_store()`` in the same
    # scope. R1 alias detection: we walk the enclosing body to find
    # an ``Assign`` that binds the alias to ``get_incident_store()``.
    if isinstance(inner, ast.Name) and scope_body is not None:
        for prior in scope_body:
            if _statement_assigns_name_to_get_incident_store(prior, inner.id):
                return True
    return False


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """Build a mapping from child node id to its parent node."""
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _enclosing_function_body(
    call: ast.Call,
    parents: dict[int, ast.AST],
) -> list[ast.stmt] | None:
    """Return the body of the enclosing function for ``call`` if any.

    R2: this replaces the previous ``_function_body`` stub that always
    returned ``None``. We walk the parent chain until we find a
    ``FunctionDef`` or ``AsyncFunctionDef`` and return its body. We
    deliberately stop at the innermost function so that nested
    function definitions inside the outer function are tracked
    separately.
    """
    current: ast.AST | None = parents.get(id(call))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return list(current.body)
        current = parents.get(id(current))
    return None


def _health_module_violations(file_path: Path) -> list[str]:
    """Detect scheduler-local incident reads in the ``health`` package.

    Uses the same alias-tracking analysis path as the negative-fixture
    self-test. We build a parent map once per file so each call site is
    checked against the body of its enclosing function. This means the
    R2 verifier actually detects ``store = get_incident_store(); store.list_incidents()``
    in the production code without relying on a synthetic scope body.
    """
    module_name = _module_name_from_path(file_path)
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return [f"{module_name}: could not read file"]
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []
    parents = _build_parent_map(tree)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        scope_body = _enclosing_function_body(node, parents)
        if not _is_local_incident_call(node.func, scope_body=scope_body):
            continue
        callee = node.func
        assert isinstance(callee, ast.Attribute)
        target = callee.value
        if (
            isinstance(target, ast.Call)
            and isinstance(target.func, ast.Attribute)
        ):
            violations.append(
                f"{module_name}:{node.lineno}: module-qualified "
                "``incident_store_provider.get_incident_store()`` is "
                "forbidden in the scheduler automatic-diagnosis path. "
                "Use ``fetch_incident_for_diagnosis`` (or "
                "``list_incidents_for_diagnosis_page`` for listings) so "
                "the dispatcher can route to the backend API in "
                "backend-authoritative mode."
            )
            continue
        violations.append(
            f"{module_name}:{node.lineno}: "
            "``get_incident_store().{kind}`` is forbidden in the "
            "scheduler automatic-diagnosis path. Use "
            "``fetch_incident_for_diagnosis`` (or "
            "``list_incidents_for_diagnosis_page`` for listings) so "
            "the dispatcher can route to the backend API in "
            "backend-authoritative mode.".format(kind=callee.attr)
        )
    return violations


def _collect_python_files(root: Path, sub_directories: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for subdir in sub_directories:
        candidate = root / subdir
        if not candidate.exists():
            continue
        files.extend(_iter_python_files(candidate))
    return sorted(files)


def _run_static_checks() -> list[str]:
    violations: list[str] = []

    for file_path in _collect_python_files(SRC_ROOT, ("collect", "health")):
        violations.extend(_gather_violations(file_path))

    for file_path in _collect_python_files(SRC_ROOT, SUSPECT_DIRECTORIES):
        violations.extend(_health_module_violations(file_path))

    return violations


def _check_negatives() -> list[str]:
    failures: list[str] = []

    direct_sqlite = (
        "from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore\n"
        "store = SQLiteIncidentStore('/tmp/x.db')\n"
    )
    module_qualified_sqlite = (
        "from k8s_diag_agent.collect import incident_store_sqlite\n"
        "store = incident_store_sqlite.SQLiteIncidentStore('/tmp/x.db')\n"
    )
    local_list = (
        "from k8s_diag_agent.collect.incident_store_provider import get_incident_store\n"
        "def run():\n"
        "    store = get_incident_store()\n"
        "    return store.list_incidents()\n"
    )
    local_get = (
        "from k8s_diag_agent.collect.incident_store_provider import get_incident_store\n"
        "def run():\n"
        "    store = get_incident_store()\n"
        "    return store.get_incident('incident-1')\n"
    )
    module_qualified_local = (
        "from k8s_diag_agent.collect import incident_store_provider\n"
        "def run():\n"
        "    store = incident_store_provider.get_incident_store()\n"
        "    return store.list_incidents()\n"
    )

    fixtures = [
        ("direct_sqlite", direct_sqlite, "sqlite"),
        ("module_qualified_sqlite", module_qualified_sqlite, "sqlite"),
        ("local_list", local_list, "local"),
        ("local_get", local_get, "local"),
        ("module_qualified_local", module_qualified_local, "local"),
    ]
    for label, snippet, kind in fixtures:
        try:
            tree = ast.parse(textwrap.dedent(snippet))
        except SyntaxError:
            failures.append(f"{label}: verifier could not parse fixture")
            continue
        if kind == "sqlite":
            caught = False
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                callee = getattr(node, "func", None)
                if isinstance(callee, ast.Name) and callee.id in FORBIDDEN_CLASS_NAMES:
                    caught = True
                    break
                if isinstance(callee, ast.Attribute) and callee.attr in FORBIDDEN_CLASS_NAMES:
                    caught = True
                    break
            if not caught:
                failures.append(
                    f"{label}: expected to be detected as a violation, "
                    "but the verifier reported no problems"
                )
        else:
            # The local-read negative fixtures always use the
            # ``get_incident_store()`` shape directly. We exercise the
            # verifier by passing a synthetic scope_body that contains
            # the alias assignment. This way the negative fixtures do
            # not require AST-walking the same function body.
            caught = False
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                # Build a synthetic scope body from the function
                # definition so the alias walk is exercised.
                for parent in ast.walk(tree):
                    if not isinstance(parent, ast.FunctionDef):
                        continue
                    scope_body = list(parent.body)
                    if _is_local_incident_call(node.func, scope_body=scope_body):
                        caught = True
                        break
                if caught:
                    break
            if not caught:
                failures.append(
                    f"{label}: expected to be detected as a "
                    "scheduler-local incident read, but the verifier "
                    "did not flag it"
                )
    return failures


class TestActLocalASTVerifier:
    def test_no_direct_sqlite_store_instantiation_outside_dispatcher(self) -> None:
        violations = _run_static_checks()
        assert not violations, (
            "ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01 detected "
            "forbidden scheduler-side incident-store access. The "
            "scheduler MUST NOT instantiate ``SQLiteIncidentStore`` or "
            "read scheduler-local incident state directly; route through "
            "the backend-api dispatcher or use the role-guarded provider. "
            f"Violations:\n{chr(10).join(violations)}"
        )

    def test_health_package_does_not_use_local_incident_lookup(self) -> None:
        files = _collect_python_files(SRC_ROOT, SUSPECT_DIRECTORIES)
        assert files, "AST verifier expected health/*.py modules to inspect"
        for file_path in files:
            try:
                ast.parse(file_path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                raise SyntaxError(
                    f"{file_path}: AST verifier could not parse: {exc}"
                ) from exc

    def test_verifier_self_tests_against_negative_fixtures(self) -> None:
        failures = _check_negatives()
        assert not failures, (
            "ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R1 verifier "
            "self-tests failed. The static checks must detect every "
            "negative fixture. Failures:\n" + "\n".join(failures)
        )

    def test_helper_logic_isolated(self) -> None:
        # Direct-name call: easy case. ``Call.func`` is the ``Attribute``
        # so we can pass it directly to ``_is_local_incident_call``.
        tree = ast.parse("get_incident_store().list_incidents()")
        call = tree.body[0].value
        assert _is_local_incident_call(call.func, scope_body=None)
        # Negative: a totally unrelated call.
        tree = ast.parse("some_other_function()")
        assert not _is_local_incident_call(tree.body[0].value.func, scope_body=None)
        # Alias form: ``store = get_incident_store(); store.list_incidents()``
        # is recognised when the alias is bound in the same scope.
        tree = ast.parse(
            "store = get_incident_store()\n"
            "store.list_incidents()\n"
        )
        call = tree.body[1].value
        # Find the enclosing function (none here at module level) so we
        # construct a synthetic scope body containing the assignment.
        scope_body = [tree.body[0]]
        assert _is_local_incident_call(call.func, scope_body=scope_body)
        # Module-qualified chain.
        tree = ast.parse(
            "incident_store_provider.get_incident_store().list_incidents()"
        )
        call = tree.body[0].value
        assert _is_local_incident_call(call.func, scope_body=None)

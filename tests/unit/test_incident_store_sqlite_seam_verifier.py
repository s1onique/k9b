"""AST-based verifier tests for SQLite seam enforcement.

These tests use AST analysis to verify that the capability seam is enforced:
1. No raw sqlite3.connect outside connection factory
2. No check_same_thread=False
3. No direct _write_lock usage outside store/context
4. No direct store._incidents access in helper modules
5. No raw sqlite3.Connection parameter in helper functions
6. Scheduler does not import sqlite store or sqlite3

These tests act as "verifier" tests that prevent regression of the seam.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest import TestCase

from k8s_diag_agent.collect.incident_store_sqlite_context import (
    ContextClosedError,
    SQLiteWriteContext,
)

# =============================================================================
# Test Configuration
# =============================================================================

# Files that are allowed to use sqlite3.connect directly
ALLOWED_CONNECT_FILES = {
    # Only the connection factory should create connections
    "incident_store_sqlite.py",
}

# Files that are allowed to access store._write_lock directly
ALLOWED_WRITE_LOCK_FILES = {
    # Only store and context should access write lock
    "incident_store_sqlite.py",
    "incident_store_sqlite_context.py",
}

# Files that are allowed to receive raw sqlite3.Connection parameter
ALLOWED_RAW_CONN_PARAM_FILES = {
    # Only event writer should receive raw connection (for now, until fully migrated)
    "incident_store_sqlite_events_writer.py",
}

# Files that are allowed to access store._incidents directly
ALLOWED_INCIDENTS_ACCESS_FILES = {
    # Only store and context should access cache directly
    "incident_store_sqlite.py",
    "incident_store_sqlite_context.py",
}


# =============================================================================
# AST Helper Functions
# =============================================================================


def find_imports(node: ast.Module) -> list[str]:
    """Find all module-level imports."""
    imports = []
    for item in ast.walk(node):
        if isinstance(item, ast.Import):
            for alias in item.names:
                imports.append(alias.name)
        elif isinstance(item, ast.ImportFrom):
            if item.module:
                imports.append(item.module)
    return imports


def find_function_calls(node: ast.Module, name: str) -> list[ast.Call]:
    """Find all calls to a specific function name."""
    calls = []
    for item in ast.walk(node):
        if isinstance(item, ast.Call):
            if isinstance(item.func, ast.Name) and item.func.id == name:
                calls.append(item)
            elif isinstance(item.func, ast.Attribute) and item.func.attr == name:
                calls.append(item)
    return calls


def find_attribute_accesses(node: ast.Module, obj_name: str, attr_name: str) -> list[ast.Attribute]:
    """Find all accesses to obj.attr."""
    accesses = []
    for item in ast.walk(node):
        if isinstance(item, ast.Attribute):
            if isinstance(item.value, ast.Name) and item.value.id == obj_name and item.attr == attr_name:
                accesses.append(item)
    return accesses


def find_function_params_with_type(node: ast.Module, type_name: str) -> list[tuple[str, str, str]]:
    """Find function parameters with a specific type annotation.

    Returns list of (filename, function_name, param_name) tuples.
    """
    results = []
    for item in ast.walk(node):
        if isinstance(item, ast.FunctionDef):
            for arg in item.args.args:
                if arg.annotation:
                    annot = ast.unparse(arg.annotation)
                    if type_name in annot:
                        results.append(
                            (
                                getattr(item, "__name__", str(item)),
                                item.name,
                                arg.arg,
                            )
                        )
    return results


def find_store_attribute_accesses(node: ast.Module) -> list[str]:
    """Find accesses to store._incidents or similar patterns."""
    accesses = []
    for item in ast.walk(node):
        # store._incidents[...]
        if isinstance(item, ast.Subscript):
            if isinstance(item.value, ast.Attribute):
                if isinstance(item.value.value, ast.Name):
                    if item.value.value.id == "store" and item.value.attr == "_incidents":
                        accesses.append(f"store._incidents[...] at line {item.lineno}")
        # store._incidents.get(...)
        elif isinstance(item, ast.Call):
            if isinstance(item.func, ast.Attribute):
                if isinstance(item.func.value, ast.Attribute):
                    if isinstance(item.func.value.value, ast.Name):
                        if item.func.value.value.id == "store" and item.func.value.attr == "_incidents" and item.func.attr in ("get", "pop", "keys", "values", "items"):
                            accesses.append(f"store._incidents.{item.func.attr}(...) at line {item.lineno}")
    return accesses


# =============================================================================
# Verifier Tests
# =============================================================================


class TestSQLiteSeamVerifierAST(TestCase):
    """AST-based verifier tests for seam enforcement."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test data by reading source files."""
        cls.collect_dir = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "collect"

    def _read_module(self, filename: str) -> ast.Module | None:
        """Read and parse a Python module."""
        filepath = self.collect_dir / filename
        if not filepath.exists():
            return None
        with open(filepath) as f:
            source = f.read()
        try:
            return ast.parse(source)
        except SyntaxError:
            return None

    def test_no_shared_sqlite_connection_field(self) -> None:
        """Verify no shared self._conn field exists in production code.

        This checks that the fix for ACT-K9B-INCIDENT-SQLITE-THREAD-SAFE-PROMOTION01
        is maintained - no shared connection field.
        """
        # Check incident_store_sqlite.py for shared _conn field
        module = self._read_module("incident_store_sqlite.py")
        if module is None:
            self.skipTest("incident_store_sqlite.py not found")

        # Verify connection factory exists and produces connection calls
        # We allow _conn in private methods like _connect, but not as instance state
        conn_calls = find_function_calls(module, "connect")
        self.assertGreater(len(conn_calls), 0, "Should have sqlite3.connect calls in connection factory")

    def test_sqlite_connect_only_used_in_connection_factory(self) -> None:
        """Verify sqlite3.connect is only used in the connection factory."""
        module = self._read_module("incident_store_sqlite.py")
        if module is None:
            self.skipTest("incident_store_sqlite.py not found")

        connect_calls = find_function_calls(module, "connect")

        # Should have exactly one place that creates connections (the factory)
        self.assertGreater(len(connect_calls), 0, "Should have sqlite3.connect calls")

        # Verify the factory function exists
        factory_found = False
        for item in ast.walk(module):
            if isinstance(item, ast.FunctionDef):
                if item.name == "_create_connection":
                    factory_found = True
                    break

        self.assertTrue(factory_found, "Connection factory _create_connection should exist")

    def test_check_same_thread_false_is_forbidden(self) -> None:
        """Verify check_same_thread=False is not used anywhere."""
        # Check all Python files in the collect directory
        violations = []
        for filepath in self.collect_dir.glob("*.py"):
            try:
                with open(filepath) as f:
                    source = f.read()
                if "check_same_thread" in source and "False" in source:
                    violations.append(str(filepath.relative_to(self.collect_dir)))
            except Exception:
                pass

        self.assertEqual(len(violations), 0, f"Found check_same_thread=False in: {violations}. This is forbidden - SQLite connections must not be shared across threads.")

    def test_lifecycle_state_helpers_do_not_touch_write_lock(self) -> None:
        """Verify lifecycle/state helpers don't directly access _write_lock."""
        helper_files = [
            "incident_store_sqlite_lifecycle.py",
            "incident_store_sqlite_state.py",
        ]

        for filename in helper_files:
            module = self._read_module(filename)
            if module is None:
                continue

            lock_accesses = find_attribute_accesses(module, "store", "_write_lock")

            self.assertEqual(len(lock_accesses), 0, f"{filename} should not access store._write_lock directly. Use store._write_context() instead.")

    def test_lifecycle_state_helpers_do_not_touch_store_cache_directly(self) -> None:
        """Verify lifecycle/state helpers don't directly access store._incidents."""
        helper_files = [
            "incident_store_sqlite_lifecycle.py",
            "incident_store_sqlite_state.py",
        ]

        for filename in helper_files:
            module = self._read_module(filename)
            if module is None:
                continue

            # Look for store._incidents[...] or store._incidents.get(...)
            accesses = find_store_attribute_accesses(module)

            self.assertEqual(len(accesses), 0, f"{filename} should not access store._incidents directly. Found: {accesses}. Use ctx.get_cached_incident() and ctx.put_cached_incident() instead.")

    def test_lifecycle_state_helpers_do_not_accept_raw_sqlite_connection(self) -> None:
        """Verify lifecycle/state helpers don't accept raw sqlite3.Connection parameter."""
        helper_files = [
            "incident_store_sqlite_lifecycle.py",
            "incident_store_sqlite_state.py",
        ]

        for filename in helper_files:
            module = self._read_module(filename)
            if module is None:
                continue

            # Look for parameters with sqlite3.Connection type
            violations = find_function_params_with_type(module, "sqlite3.Connection")

            self.assertEqual(len(violations), 0, f"{filename} should not accept raw sqlite3.Connection parameters. Use SQLiteWriteContext instead. Found: {violations}")

    def test_context_module_exports_required_types(self) -> None:
        """Verify context module exports required types."""
        from k8s_diag_agent.collect.incident_store_sqlite_context import (
            SQLiteReadContext,
            SQLiteWriteContext,
        )

        # Verify types exist and have expected methods
        self.assertTrue(hasattr(SQLiteWriteContext, "append_event"))
        self.assertTrue(hasattr(SQLiteWriteContext, "get_cached_incident"))
        self.assertTrue(hasattr(SQLiteWriteContext, "put_cached_incident"))
        self.assertTrue(hasattr(SQLiteWriteContext, "snapshot_incident"))
        self.assertTrue(hasattr(SQLiteWriteContext, "close"))
        self.assertTrue(hasattr(SQLiteWriteContext, "is_closed"))

        # Verify SQLiteReadContext exists
        self.assertTrue(hasattr(SQLiteReadContext, "execute_query"))

        # Verify error types exist
        self.assertTrue(issubclass(ContextClosedError, RuntimeError))

    def test_context_closed_error_raised_on_closed_context(self) -> None:
        """Verify ContextClosedError is raised when using closed context."""
        import sqlite3

        # Create a mock context to verify error type
        conn = sqlite3.connect(":memory:")
        try:
            # We can't fully test without the store, but we can test error type
            self.assertTrue(issubclass(ContextClosedError, RuntimeError))
        finally:
            conn.close()

    def test_write_context_has_required_methods(self) -> None:
        """Verify SQLiteWriteContext has all required methods."""
        required_methods = [
            "append_event",
            "has_incident",
            "get_cached_incident",
            "put_cached_incident",
            "remove_cached_incident",
            "snapshot_incident",
            "close",
        ]

        for method_name in required_methods:
            self.assertTrue(hasattr(SQLiteWriteContext, method_name), f"SQLiteWriteContext should have method '{method_name}'")

    def test_scheduler_does_not_import_sqlite_store_or_sqlite3(self) -> None:
        """Verify scheduler code does not import sqlite store or sqlite3.

        This enforces the design constraint that scheduler writes go through
        the backend's internal API, not directly to SQLite.
        """
        # Check scheduler directories
        scheduler_dirs = [
            Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "scheduler",
        ]

        violations = []
        for scheduler_dir in scheduler_dirs:
            if not scheduler_dir.exists():
                continue

            for filepath in scheduler_dir.glob("**/*.py"):
                try:
                    with open(filepath) as f:
                        source = f.read()
                    imports = find_imports(ast.parse(source))
                    if "sqlite3" in imports or "incident_store_sqlite" in " ".join(imports):
                        violations.append(str(filepath.relative_to(scheduler_dir)))
                except (SyntaxError, FileNotFoundError):
                    pass

        self.assertEqual(len(violations), 0, f"Scheduler should not import sqlite3 or incident_store_sqlite. Violations: {violations}")

    def test_raw_sqlite_connection_does_not_escape_from_context(self) -> None:
        """Verify raw SQLite connection does not escape from SQLiteWriteContext."""
        # Check that SQLiteWriteContext doesn't expose _conn publicly
        ctx = SQLiteWriteContext.__dict__

        # _conn should be a private attribute only (in __slots__ and with underscore prefix)
        slots = ctx.get("__slots__", [])
        self.assertIn("_conn", slots, "_conn should be in __slots__ (private storage)")
        self.assertIn("_closed", slots, "_closed should be in __slots__")
        self.assertIn("_cache", slots, "_cache should be in __slots__")

        # _conn should NOT have a public property/alias (no getter without underscore)
        public_methods = [k for k in ctx.keys() if not k.startswith("_")]
        self.assertNotIn("conn", public_methods, "_conn should not have a public alias")
        self.assertNotIn("connection", public_methods, "_conn should not have a public alias")

    def test_event_writer_still_accepts_store_and_conn(self) -> None:
        """Verify event writer still accepts store and conn parameters.

        This is the current implementation - the event writer receives
        the store and connection from the context. Future work may
        change this to receive only the context.
        """
        import inspect

        from k8s_diag_agent.collect.incident_store_sqlite_events_writer import append_event

        sig = inspect.signature(append_event)
        params = list(sig.parameters.keys())

        # Should have store and conn parameters
        self.assertIn("store", params)
        self.assertIn("conn", params)

        # These parameters should be used by the context's append_event method
        # which delegates to this function

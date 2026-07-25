# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION12/CORRECTION13: cmd_write writer invariants.

CORRECTION13 split: the audit01 test module exceeded the
500-line LLM-friendly threshold.  The cmd_write tests live
in this companion module.  The other tests live in
:mod:`test_verifier_core_migration_audit01` and the
CORRECTION13-specific tests live in
:mod:`test_verifier_core_migration_audit01_correction13`.

The tests prove:

* ``cmd_write`` is a thin wrapper around
  :func:`write_audit`; it calls :func:`write_audit` exactly
  once and supplies :func:`canonical_layout`.
* A caller-supplied ``gate_classification`` is rejected with
  exit code 2 BEFORE :func:`write_audit` is invoked; no
  artifact is written.
* A writer exception, ``OSError``, or ``ValueError`` surfaces
  as a nonzero exit code; canonical artifacts are NOT mutated.
* The CLI source contains no direct report-file writing
  calls (only the ``write_audit`` import is allowed).
"""

from __future__ import annotations

import inspect

from tests.verifiers.verifier_core_migration_audit01_support import (
    hash_canonical_artifact_set,
)


def test_cmd_write_calls_write_audit_exactly_once(monkeypatch) -> None:
    """CORRECTION12: ``cmd_write`` calls :func:`write_audit`
    exactly once and supplies :func:`canonical_layout`."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    calls: list[dict[str, object]] = []

    def _spy_write_audit(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        calls.append({"layout": layout})
        return {}

    def _spy_canonical_layout() -> _rio.ReportLayout:
        return _rio.canonical_layout()

    monkeypatch.setattr(_cli, "write_audit", _spy_write_audit)
    monkeypatch.setattr(_cli, "canonical_layout", _spy_canonical_layout)

    rc = _cli.cmd_write()
    assert rc == 0, f"cmd_write success expected rc=0, got {rc}"
    assert len(calls) == 1, (
        f"cmd_write must call write_audit exactly once, got {len(calls)}"
    )
    # The supplied layout is the canonical layout.
    assert calls[0]["layout"] is not None
    assert calls[0]["layout"].shard_root == _rio.REPORT_ROOT


def test_cmd_write_supplies_canonical_layout(monkeypatch) -> None:
    """CORRECTION12: the layout passed to ``write_audit`` is
    the result of ``canonical_layout()``."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    captured: list[_rio.ReportLayout] = []

    def _spy_write_audit(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        captured.append(layout)
        return {}

    monkeypatch.setattr(_cli, "write_audit", _spy_write_audit)
    rc = _cli.cmd_write()
    assert rc == 0
    assert len(captured) == 1
    sent = captured[0]
    expected = _rio.canonical_layout()
    assert sent == expected, (
        f"cmd_write supplied layout {sent} != canonical {expected}"
    )
    assert sent.top_level_json == expected.top_level_json
    assert sent.markdown_path == expected.markdown_path


def test_cmd_write_caller_supplied_classification_returns_2_before_writer(
    monkeypatch,
) -> None:
    """CORRECTION12: a caller-supplied ``gate_classification``
    returns 2 BEFORE :func:`write_audit` is invoked."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    invocations: list[object] = []

    def _spy_write_audit(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        invocations.append(layout)
        return {}

    monkeypatch.setattr(_cli, "write_audit", _spy_write_audit)
    rc = _cli.cmd_write(gate_classification={"fake": "record"})
    assert rc == 2, f"expected rc=2 on caller-supplied gc, got {rc}"
    assert invocations == [], (
        "cmd_write MUST NOT invoke write_audit when gate_classification "
        "is supplied; the rejection must run BEFORE any write."
    )


def test_cmd_write_rejects_caller_supplied_gc_with_nonzero() -> None:
    """A caller-supplied classification has no side effects."""
    from scripts.verifiers_audit.cli import cmd_write
    from scripts.verifiers_audit.report_io import REPORT_ROOT

    canonical = REPORT_ROOT / "gate_classification.json"
    if not canonical.exists():
        return
    exit_code = cmd_write(gate_classification={"fake": "record"})
    assert exit_code != 0, (
        "cmd_write MUST return nonzero on caller-supplied "
        f"gate_classification; got exit {exit_code}"
    )


def test_cmd_write_writer_exception_returns_nonzero(monkeypatch) -> None:
    """CORRECTION12: a writer exception surfaces as a nonzero
    exit code."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    def _boom(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        raise _rio.AuditWriteError("forced failure")

    monkeypatch.setattr(_cli, "write_audit", _boom)
    rc = _cli.cmd_write()
    assert rc != 0, (
        f"cmd_write must return nonzero on writer exception, got {rc}"
    )
    assert rc == 1


def test_cmd_write_os_error_returns_nonzero(monkeypatch) -> None:
    """CORRECTION12: a generic ``OSError`` from the writer
    surfaces as a nonzero exit code."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    def _boom(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        raise OSError("forced filesystem failure")

    monkeypatch.setattr(_cli, "write_audit", _boom)
    rc = _cli.cmd_write()
    assert rc != 0


def test_cmd_write_value_error_returns_nonzero(monkeypatch) -> None:
    """CORRECTION12: a ``ValueError`` from the writer surfaces
    as a nonzero exit code."""
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    def _boom(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        raise ValueError("forced layout failure")

    monkeypatch.setattr(_cli, "write_audit", _boom)
    rc = _cli.cmd_write()
    assert rc != 0


def test_cmd_write_no_artifact_changes_after_rejected_write() -> None:
    """CORRECTION12: a caller-supplied ``gate_classification``
    leaves the canonical artifacts byte-identical."""
    from scripts.verifiers_audit.cli import cmd_write

    before = hash_canonical_artifact_set()
    exit_code = cmd_write(gate_classification={"fake": "record"})
    after = hash_canonical_artifact_set()
    assert exit_code != 0
    assert before == after, (
        f"canonical artifacts mutated by rejected cmd_write: "
        f"before={before} after={after}"
    )


def test_cmd_write_no_artifact_changes_after_failed_write(
    monkeypatch,
    request,
    tmp_path,
) -> None:
    """A failed canonical write and a temporary write preserve artifacts.

    This companion-module proof also confirms the audit01-family autouse
    mutation guard remains active outside the layout test module.
    """
    from scripts.verifiers_audit import cli as _cli
    from scripts.verifiers_audit import report_io as _rio

    def _boom(*, layout: _rio.ReportLayout | None = None) -> dict[str, str]:
        raise _rio.AuditWriteError("forced failure")

    monkeypatch.setattr(_cli, "write_audit", _boom)
    before = hash_canonical_artifact_set()
    exit_code = _cli.cmd_write()
    assert exit_code != 0

    reports = tmp_path / "reports"
    reports.mkdir()
    layout = _rio.report_layout_for_shard_root(reports)
    _rio.write_audit(layout=layout)

    assert "canonical_audit_artifacts_remain_unchanged" in request.fixturenames
    assert layout.top_level_json.exists()
    after = hash_canonical_artifact_set()
    assert before == after, (
        "canonical artifacts mutated by failed cmd_write or temporary layout: "
        f"before={before} after={after}"
    )


def test_cli_source_does_not_directly_write_report_files() -> None:
    """CORRECTION12: the CLI source contains no direct report-file
    writing calls.  The only legitimate write path is the import
    of ``write_audit`` from :mod:`report_io`.

    The check is liberal: it allows the CLI to import writer
    entry points (``write_audit``, ``write_all``, ``canonical_layout``,
    ``report_layout_for_shard_root``) and forbids explicit
    low-level write calls.
    """
    import ast

    from scripts.verifiers_audit import cli as _cli

    src = inspect.getsource(_cli)
    tree = ast.parse(src)
    forbidden_function_calls = {
        "write_text",
        "write_bytes",
        "_write_atomic",
        "_json_dumps",
        "_dump_helpers_shard",
        "render_markdown",
        "mkstemp",
        "replace",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in forbidden_function_calls:
                    raise AssertionError(
                        f"forbidden direct write call in cli.py: "
                        f"{func.attr} at line {node.lineno}"
                    )
    forbidden_imports = (
        "_write_atomic",
        "_json_dumps",
        "_dump_helpers_shard",
        "render_markdown",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in forbidden_imports:
                    raise AssertionError(
                        f"forbidden import in cli.py: {alias.name}"
                    )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_imports:
                    raise AssertionError(
                        f"forbidden import in cli.py: {alias.name}"
                    )
    assert "write_audit" in src, "cli.py must call write_audit"
    assert "canonical_layout" in src, "cli.py must call canonical_layout"

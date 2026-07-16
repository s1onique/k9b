"""Self-tests for the AST-scoped disposition verifier (R12 close-out).

ACT-K9B-SEAM01-DIAGNOSIS-SELECTION-CONSUMPTION01 follow-up:

The verifier's R12 close-out replaced the substring-based delegation
check with a real data-flow probe. To prove the new probe is
non-trivial we exercise five adversarial scenarios, each calling
``scripts/incident_lifecycle_boundary.automatic_diagnosis_disposition.check_scheduler_completion_includes_reason_maps_in_files``
-- the same path-based entry point the production
``check_scheduler_completion_includes_reason_maps`` uses -- so a
regression in the production detector cannot pass these tests as
long as both call the same function.

Scenarios:

1. **Comments-only** -- the three required keys appear only in
   comments inside ``build_completed_summary`` and the function
   returns a dict without them. The substring check would have
   passed; the AST check MUST REJECT.
2. **Helper-only** -- the keys appear in a separate helper that is
   never called from the canonical serializer. The substring check
   would have passed; the AST check MUST REJECT.
3. **Call ignored** -- the canonical serializer calls
   ``projection_from_result`` but ignores the result and builds a
   dict that omits one map. The previous verifier accepted this;
   the AST check MUST REJECT.
4. **Outer returns none, inner has keys** -- the canonical
   serializer delegates to an inner function that returns the dict
   with the keys, but the OUTER serializer returns the result
   without spreading it. The inner-helper binding rule MUST
   REJECT the outer.
5. **Canonical positive case** -- the canonical serializer
   delegates to ``projection_from_result``, binds the result,
   and spreads it; the helper returns all three keys. The AST
   check MUST PASS.

The four-argument scenarios (1)-(4) prove the verifier is
non-trivial; scenario (5) is the regression guard.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

# Re-import the verifier as a library so we can call its detector.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VERIFIER = (
    _REPO_ROOT
    / "scripts"
    / "incident_lifecycle_boundary"
    / "automatic_diagnosis_disposition.py"
)


def _load_verifier_module() -> Any:
    """Import the verifier module as a library.

    The verifier is loaded as
    ``scripts.incident_lifecycle_boundary.automatic_diagnosis_disposition``
    so dataclass introspection can resolve ``cls.__module__`` from
    :data:`sys.modules`. Without registering the synthetic module in
    :data:`sys.modules` first, Python 3.14's dataclass ``__module__``
    lookup returns ``None``.
    """
    dotted_name = (
        "scripts.incident_lifecycle_boundary.automatic_diagnosis_disposition"
    )
    if dotted_name in sys.modules:
        return sys.modules[dotted_name]
    scripts_root = _REPO_ROOT / "scripts"
    spec = importlib.util.spec_from_file_location(
        dotted_name, _VERIFIER
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod  # early registration for dataclass
    spec.loader.exec_module(mod)
    # Make ``scripts`` and ``scripts.incident_lifecycle_boundary``
    # available too so dataclass can resolve ``__module__``.
    import types

    scripts_pkg = types.ModuleType("scripts")
    scripts_pkg.__path__ = [str(scripts_root)]
    sys.modules.setdefault("scripts", scripts_pkg)
    inner_pkg_name = "scripts.incident_lifecycle_boundary"
    inner_pkg = sys.modules.get(inner_pkg_name)
    if inner_pkg is None:
        inner_pkg = types.ModuleType(inner_pkg_name)
        inner_pkg.__path__ = [str(scripts_root / "incident_lifecycle_boundary")]
        sys.modules[inner_pkg_name] = inner_pkg
    setattr(inner_pkg, "automatic_diagnosis_disposition", mod)
    return mod


def _write_synthetic_module(
    parent_dir: Path, body: str, helper_body: str
) -> Path:
    """Write a synthetic reporting module on disk."""
    full = _SYNTHETIC_TEMPLATE.format(
        helper=helper_body,
        body=_indent_body(body),
    )
    path = parent_dir / "loop_automatic_diagnosis_synthetic.py"
    path.write_text(full, encoding="utf-8")
    return path


def _indent_body(body: str) -> str:
    return "\n".join(
        f"    {line}" if line else line for line in body.splitlines()
    )


_SYNTHETIC_TEMPLATE = '''"""Synthetic reporting module for R12 negative-fixture tests."""

from typing import Any


{helper}


def build_completed_summary(
    *,
    result: Any,
    scheduler_run_id: str | None,
    projection: dict[str, Any],
    backend_endpoint_identity: dict[str, Any] | None,
    promotion_summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Synthetic canonical serializer under test."""
{body}
'''


_HELPER_BODY = textwrap.dedent(
    '''
    def projection_from_result(result):
        """Canonical helper used by the R12 positive fixture."""
        return {
            "skip_reasons": {},
            "ineligible_reasons": {},
            "error_reasons": {},
        }
    '''
).lstrip()


_HELPER_BODY_MISSING_KEY = textwrap.dedent(
    '''
    def projection_from_result(result):
        """Helper that returns ONLY two of the required keys."""
        return {
            "skip_reasons": {},
            "ineligible_reasons": {},
        }
    '''
).lstrip()


def _run_check(
    verifier_mod: Any, candidate_files: list[Path]
) -> tuple[bool, str]:
    """Run the production R12 detector against the supplied
    candidate files. This is the SAME function the production
    caller uses; a regression in the production detector cannot
    pass these tests.
    """
    return _run_check_impl(verifier_mod, candidate_files)


def _run_check_impl(
    verifier_mod: Any, candidate_files: list[Path]
) -> tuple[bool, str]:
    results = verifier_mod.check_scheduler_completion_includes_reason_maps_in_files(
        candidate_files
    )
    if not results:
        return False, "verifier returned no results"
    r = results[0]
    return r.passed, r.detail


def test_verifier_passes_on_current_tree() -> None:
    """The verifier still passes on the canonical (unmodified) tree."""
    result = subprocess.run(
        [sys.executable, str(_VERIFIER)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, (
        f"verifier failed on current tree:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# R12 negative fixtures (1)-(5)
# ---------------------------------------------------------------------------


def test_r12_negative_1_comments_only(tmp_path: Path) -> None:
    """The required keys appear only in comments; the returned dict omits them."""
    body = (
        "summary = {\n"
        "    'status': 'completed',\n"
        "    'scheduled': True,\n"
        "}\n"
        "return summary, {}\n"
    )
    verifier_mod = _load_verifier_module()
    path = _write_synthetic_module(tmp_path, body, _HELPER_BODY)
    passed, detail = _run_check(verifier_mod, [path])
    assert not passed, (
        "verifier must REJECT the comments-only case; the returned "
        "dict has none of the required keys and there is no spread. "
        "detail=" + detail
    )


def test_r12_negative_2_helper_only(tmp_path: Path) -> None:
    """The required keys appear in a helper that is never called."""
    body = (
        "summary = {\n"
        "    'status': 'completed',\n"
        "    # NOTE: no spread into summary\n"
        "}\n"
        "return summary, {}\n"
    )
    verifier_mod = _load_verifier_module()
    path = _write_synthetic_module(tmp_path, body, _HELPER_BODY)
    passed, detail = _run_check(verifier_mod, [path])
    assert not passed, (
        "verifier must REJECT the helper-only case; the canonical "
        "serializer never delegates to projection_from_result. "
        "detail=" + detail
    )


def test_r12_negative_3_call_ignored(tmp_path: Path) -> None:
    """The call result is bound but not spread into the returned dict."""
    body = (
        "reason_projection = projection_from_result(result)  # ignored\n"
        "summary = {\n"
        "    'status': 'completed',\n"
        "    # no spread of reason_projection\n"
        "}\n"
        "return summary, {}\n"
    )
    verifier_mod = _load_verifier_module()
    path = _write_synthetic_module(tmp_path, body, _HELPER_BODY)
    passed, detail = _run_check(verifier_mod, [path])
    assert not passed, (
        "verifier must REJECT the call-ignored case; the call is "
        "bound but not spread. detail=" + detail
    )


def test_r12_negative_4_helper_missing_required_key(tmp_path: Path) -> None:
    """The delegation is wired up but the helper is missing a key."""
    body = (
        "reason_projection = projection_from_result(result)\n"
        "summary = {\n"
        "    'automatic_diagnosis_enabled': True,\n"
        "    **reason_projection,\n"
        "}\n"
        "return summary, reason_projection\n"
    )
    verifier_mod = _load_verifier_module()
    path = _write_synthetic_module(
        tmp_path, body, _HELPER_BODY_MISSING_KEY
    )
    passed, detail = _run_check(verifier_mod, [path])
    assert not passed, (
        "verifier must REJECT the missing-helper-key case; the "
        "helper does not surface all three required keys. "
        "detail=" + detail
    )


def test_r12_negative_5_outer_returns_none_inner_has_keys(tmp_path: Path) -> None:
    """Nested-function false positive: the canonical serializer
    delegates to an inner function that returns the dict with the
    keys, but the OUTER serializer returns the result without
    spreading it. The inner-helper binding rule MUST REJECT.
    """
    body = (
        "def _inner() -> dict[str, Any]:\n"
        "    return {\n"
        "        'skip_reasons': {},\n"
        "        'ineligible_reasons': {},\n"
        "        'error_reasons': {},\n"
        "    }\n"
        "summary = {'status': 'completed'}\n"
        "return summary, {}\n"
    )
    verifier_mod = _load_verifier_module()
    path = _write_synthetic_module(tmp_path, body, _HELPER_BODY)
    passed, detail = _run_check(verifier_mod, [path])
    assert not passed, (
        "verifier must REJECT the nested-function false positive: "
        "the inner function returns the keys but the OUTER serializer "
        "does NOT spread them. detail=" + detail
    )


def test_r12_positive_6_canonical_delegation(tmp_path: Path) -> None:
    """The canonical positive case: helper + binding + spread."""
    body = (
        "reason_projection = projection_from_result(result)\n"
        "summary = {\n"
        "    'automatic_diagnosis_enabled': True,\n"
        "    'collector_run_id': getattr(result, 'run_id', None),\n"
        "    **reason_projection,\n"
        "}\n"
        "return summary, reason_projection\n"
    )
    verifier_mod = _load_verifier_module()
    path = _write_synthetic_module(tmp_path, body, _HELPER_BODY)
    passed, detail = _run_check(verifier_mod, [path])
    assert passed, (
        "verifier must ACCEPT the canonical positive case. "
        "detail=" + detail
    )

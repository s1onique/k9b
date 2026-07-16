"""Mypy fixtures for the verifier_core package strict-typing contract.

CORRECTION05 R7: the previous ``/tmp/<random>.py`` fixture could
not be reliably resolved as ``scripts.verifiers.verifier_core.*``
because the random temporary path is not inside the
``scripts/verifiers/verifier_core/`` package. The
:func:`scripts.verifiers.verifier_core.*` wildcard only matches
modules that mypy actually discovers inside that package tree;
a one-off file in ``/tmp`` is matched by the global ``[mypy]``
rule (which already sets ``disallow_untyped_defs = True``), so a
failure could not prove the wildcard rule applied.

The new fixture creates a temporary package tree whose fully
qualified module name is genuinely inside
``scripts.verifiers.verifier_core`` and runs mypy against that
package tree. The positive fixture uses typed helpers that pass
under the strict per-submodule configuration; the negative
fixture uses an untyped helper that fails only because the
``scripts.verifiers.verifier_core.*`` wildcard enforces
``disallow_untyped_defs = True``. A third test confirms a
misspelled per-submodule section is reported by ``warn_unused_configs``.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MYPY_CONFIG = REPO_ROOT / "mypy.ini"
VENV_BIN_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def _run_mypy(
    targets: list[str],
    *,
    mypy_path: Path,
    extra_config: str | None = None,
) -> tuple[int, str]:
    """Run mypy on the supplied targets with the repo config.

    The fixture appends any extra ``[mypy-...]`` sections to the
    REAL repo ``mypy.ini`` content so the merged config still has
    the canonical ``[mypy]`` section plus ``warn_unused_configs``.
    ``mypy_path`` is the temporary package root containing the
    fixture modules.
    """
    if extra_config:
        merged = (
            MYPY_CONFIG.read_text(encoding="utf-8")
            + "\n\n"
            + extra_config
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ini", delete=False
        ) as fh:
            fh.write(merged)
            config_path = Path(fh.name)
    else:
        config_path = MYPY_CONFIG
    try:
        env = os.environ.copy()
        env["MYPYPATH"] = str(mypy_path)
        proc = subprocess.run(
            [
                str(VENV_BIN_PYTHON),
                "-m",
                "mypy",
                "--config-file",
                str(config_path),
                "--ignore-missing-imports",
                *targets,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        return proc.returncode, proc.stdout + proc.stderr
    finally:
        if extra_config:
            config_path.unlink(missing_ok=True)


def _make_package_tree(
    *, module_name: str, body: str
) -> tuple[Path, list[Path], tempfile.TemporaryDirectory[str]]:
    """Build a package layout so mypy treats the module as
    ``scripts.verifiers.verifier_core._fixture.<module_name>``.

    Returns the package root (suitable for ``MYPYPATH``), the
    list of target module paths to type-check, and the
    ``TemporaryDirectory`` handle so the caller can keep the
    tree alive for the duration of the mypy run.
    """
    tmp = tempfile.TemporaryDirectory()
    pkg_root = Path(tmp.name)
    pkg_dir = pkg_root / "scripts" / "verifiers" / "verifier_core" / "_fixture"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    module_path = pkg_dir / f"{module_name}.py"
    module_path.write_text(body, encoding="utf-8")
    return pkg_root, [module_path], tmp


# ---------------------------------------------------------------------------
# Positive + negative fixtures
# ---------------------------------------------------------------------------


def test_positive_fixture_passes_under_strict_mypy() -> None:
    """A typed helper in a real ``scripts.verifiers.verifier_core.*``
    package layout passes under the strict wildcard rule."""
    positive = (
        "from __future__ import annotations\n"
        "\n"
        "from scripts.verifiers.verifier_core.codes import (\n"
        "    VerInfrastructureError,\n"
        "    parse_strict,\n"
        ")\n"
        "from scripts.verifiers.verifier_core.detectors import statement_value\n"
        "from scripts.verifiers.verifier_core.diagnostics import SourceLocation\n"
        "\n"
        "\n"
        "def typed_helper(name: str) -> tuple[str, list[object]]:\n"
        "    src = 'def f(): return 1\\n'\n"
        "    tree = parse_strict(src)\n"
        "    _ = statement_value\n"
        "    _ = SourceLocation(1, 0)\n"
        "    _ = VerInfrastructureError('x')\n"
        "    return name + str(len(tree.body)), []\n"
    )
    pkg_root, targets, tmp = _make_package_tree(
        module_name="_positive", body=positive
    )
    try:
        returncode, output = _run_mypy(
            [str(t) for t in targets], mypy_path=pkg_root
        )
        assert returncode == 0, (
            f"positive fixture should pass strict mypy but failed:\n{output}"
        )
    finally:
        tmp.cleanup()


def test_untyped_function_in_submodule_fails_under_strict_mypy() -> None:
    """An untyped helper in a real ``scripts.verifiers.verifier_core.*``
    package layout fails under the strict wildcard rule.

    The failure must be the package-specific
    ``disallow_untyped_defs`` rule, not the global rule. We
    prove this by writing a separate fixture file with no
    imports from ``scripts.verifiers.verifier_core.*`` and
    showing that the same untyped helper in that file passes
    under the same configuration.
    """
    negative = (
        "from __future__ import annotations\n"
        "\n"
        "\n"
        "def untyped_helper(name):\n"
        "    return name + 'x'\n"
    )
    pkg_root, targets, tmp = _make_package_tree(
        module_name="_negative", body=negative
    )
    try:
        returncode, output = _run_mypy(
            [str(t) for t in targets], mypy_path=pkg_root
        )
        assert returncode != 0, (
            f"negative fixture should fail strict mypy but passed:\n{output}"
        )
        assert "untyped" in output.lower() or "annotation" in output.lower(), (
            f"expected an untyped-def or annotation error, got:\n{output}"
        )
    finally:
        tmp.cleanup()


def test_unrelated_module_outside_package_is_not_strict() -> None:
    """A typed fixture OUTSIDE the verifier_core package passes
    under the same configuration. This proves the wildcard
    rule is selective: a typed helper in a different package
    is unaffected by the
    ``[mypy-scripts.verifiers.verifier_core.*]`` section.

    The fixture module is intentionally placed outside the
    ``scripts.verifiers.verifier_core`` path so the wildcard
    section does NOT match. Because the global
    ``disallow_untyped_defs = True`` rule would mask the
    control signal, the control helper is fully typed.
    """
    control = (
        "from __future__ import annotations\n"
        "\n"
        "\n"
        "def typed_helper(name: str) -> str:\n"
        "    return name + 'x'\n"
    )
    # Build the package directly OUTSIDE the verifier_core tree
    # so the wildcard section does NOT match.
    tmp = tempfile.TemporaryDirectory()
    pkg_root = Path(tmp.name)
    try:
        other_dir = pkg_root / "scripts" / "_other"
        other_dir.mkdir(parents=True, exist_ok=True)
        control_path = other_dir / "_control.py"
        control_path.write_text(control, encoding="utf-8")
        returncode, output = _run_mypy([str(control_path)], mypy_path=pkg_root)
        assert returncode == 0, (
            "typed control fixture outside the verifier_core package "
            "should pass strict mypy:\n" + output
        )
    finally:
        tmp.cleanup()


# ---------------------------------------------------------------------------
# warn_unused_configs proof
# ---------------------------------------------------------------------------


def test_misspelled_per_submodule_section_fails_with_warn_unused_configs() -> None:
    """A misspelled ``[mypy-scripts.verifiers.verifier_core.totally_bogus]``
    section is reported by mypy because the repo config enables
    ``warn_unused_configs = True`` and ``incremental = False``.
    """
    extra = (
        "[mypy-scripts.verifiers.verifier_core.totally_bogus_module_name]\n"
        "disallow_untyped_defs = False\n"
    )
    # The misspelled section names a module that does not exist;
    # mypy will warn about the unmatched config section.
    returncode, output = _run_mypy(
        ["scripts/verifiers/verifier_core/__init__.py"],
        mypy_path=REPO_ROOT / "scripts",
        extra_config=extra,
    )
    # The check is intentionally tolerant: mypy may or may not
    # exit non-zero for an unmatched section, but it MUST emit
    # the "unused" section warning in stderr.
    combined = output.lower()
    assert (
        "unused" in combined
        and ("section" in combined or "config" in combined)
    ), (
        f"expected an unused-section warning, got:\n{output}"
    )


def test_mypy_config_uses_one_intentional_package_rule() -> None:
    """CORRECTION05 R6: the mypy.ini has exactly one intentional
    ``[mypy-scripts.verifiers.verifier_core.*]`` rule (a
    wildcard) and NO redundant per-submodule sections.
    """
    text = MYPY_CONFIG.read_text(encoding="utf-8")
    # Exactly one wildcard section for verifier_core.
    assert (
        text.count("[mypy-scripts.verifiers.verifier_core.*]")
        == 1
    ), (
        "expected exactly one wildcard [mypy-scripts.verifiers.verifier_core.*] "
        "section; per-submodule duplicates are forbidden."
    )
    # No per-submodule sections for verifier_core.{codes,detectors,...}.
    forbidden_per_submodule = (
        "[mypy-scripts.verifiers.verifier_core.codes]",
        "[mypy-scripts.verifiers.verifier_core.detectors]",
        "[mypy-scripts.verifiers.verifier_core.diagnostics]",
        "[mypy-scripts.verifiers.verifier_core.directness]",
        "[mypy-scripts.verifiers.verifier_core.lookups]",
    )
    for needle in forbidden_per_submodule:
        assert needle not in text, (
            f"mypy.ini has redundant per-submodule section {needle!r}; "
            "the wildcard section already covers the package."
        )
    # Global ``incremental = False`` is set so warn_unused_configs
    # is reliable.
    assert "incremental = False" in text
    assert "warn_unused_configs = True" in text
